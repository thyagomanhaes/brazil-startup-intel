# Spec: brazil-startup-intel

Status: draft v0.1, 2026-10-27. Items marked (AD-xxx) are agent defaults that Thyago has not confirmed yet. See `decisions.md`.

## 1. Purpose

A multi-source data platform about Brazilian startups that raise money through regulated crowdfunding. It turns public government files, PDFs, scraped offer pages and provider webhooks into trusted company and funding records, and serves them to an API and a public dashboard.

The problem is the one company research platforms face: track companies, investors, funding activity and people from many sources that arrive in different shapes and at different speeds.

## 2. Business questions (D-016)

In build order (AD-018):

1. Which startups are raising money right now, and who are their partners?
2. How much did each crowdfunding platform raise per year?
3. Which companies raised money more than once?

Definitions:

- **Raising now:** the offer page showed the offer as open at the last successful scrape, and that scrape is less than 2 hours old (AD-015).
- **Raised more than once:** the issuer CNPJ appears in two or more distinct offers since 2022-07-01. Exact CNPJ match until wave 3 (AD-016).

## 3. Consumers (D-013)

| Consumer | Where it runs | Reads from | Contract |
|---|---|---|---|
| Query API (FastAPI, read-only) | Docker, laptop (D-015) | Postgres `curated` schema | OpenAPI schema, versioned |
| Public dashboard (Looker Studio) | Google, public link (D-014) | BigQuery copy of curated tables | Table and column names of the curated marts |

API endpoints (AD-014):

| Endpoint | Answers |
|---|---|
| `GET /startups/raising` | Question 1 |
| `GET /platforms/{cnpj}/raised?year=` | Question 2 |
| `GET /companies/repeat-raisers` | Question 3 |
| `GET /companies/{cnpj}` | Company detail with offers and partners |

Partner names appear in the API only. The public dashboard shows companies, offers and totals (AD-017).

## 4. Sources

| Source | Intake type | Cadence | Volume | Notes |
|---|---|---|---|---|
| Receita Federal open CNPJ data (companies, establishments, partners) | Files | Monthly | Large. Multiple zipped CSVs per month | ISO-8859-1, semicolon separated. Layout has changed in the past |
| CVM open data: crowdfunding platform registry | Provider files/API | Daily snapshot | Small | Defines which platforms are in scope (D-017) |
| CVM annual reports of crowdfunding platforms | PDFs, LLM structured extraction | Yearly per platform | Tens of PDFs | Gemini on Vertex, Pydantic schema (D-005) |
| Public offer pages of crowdfunding platforms | Web scraping | Hourly | Hundreds of pages | Public pages only, robots.txt and terms respected (D-010), max 30 requests per minute per domain (D-007) |
| Simulated enrichment provider | Webhooks | Event-driven | Low | Exercises signature checks, retries, DLQ and replay |

History starts at 2022-07-01, when CVM Resolution 88 took effect (D-017). CNPJ history starts at 2023-05, the oldest release on the Receita share (A-004, checked 2026-11-04).

## 5. Architecture

```
                    GCP                                          Laptop (Docker)
┌──────────────────────────────────────────────┐   ┌──────────────────────────────────────┐
│ Cloud Tasks queue (30 req/min/domain)        │   │ Airflow (hourly, catchup on)         │
│   → Cloud Run scraper → GCS raw/html         │   │   1. list new GCS objects for hour   │
│                                              │   │   2. load to Postgres raw schema     │
│ Webhook → Cloud Run receiver                 │   │      (idempotent upsert)             │
│   → Pub/Sub topic → Cloud Run worker         │   │   3. dbt build: standardized,        │
│   → GCS raw/webhooks                         │   │      curated                         │
│   dead-letter topic + replay by seek         │   │   4. export curated → GCS Parquet    │
│                                              │◄──┤   5. load BigQuery (full replace)    │
│ Cloud Run extractor (Gemini on Vertex)       │   │                                      │
│   → GCS raw/extractions                      │   │ Postgres: raw, standardized, curated │
│                                              │   │ FastAPI (read-only, curated)         │
│ GCS: raw payloads, kept as received          │   └──────────────────────────────────────┘
│ BigQuery: copy of curated → Looker Studio    │
└──────────────────────────────────────────────┘
```

GCS is the hand-off between cloud workers and the laptop (D-006). Every payload lands in GCS before anything transforms it.

## 6. Data layers

| Layer | Where | Content | Rule |
|---|---|---|---|
| Raw (GCS) | `gs://<bucket>/raw/<source>/<yyyy>/<mm>/<dd>/<hh>/` | Files, HTML, webhook JSON and LLM outputs exactly as received | Write once. Never edited. Object metadata records source, fetch time and checksum |
| Raw (Postgres) | `raw` schema | One table per source, loaded from GCS | Idempotent upsert on natural key plus source object ID |
| Standardized | `standardized` schema, dbt | Typed, renamed, deduplicated. Partner document, age bracket, and legal representative CPF and name dropped (D-018, D-052) | dbt tests on keys and accepted values |
| Curated | `curated` schema, dbt | Marts for the three business questions and the company detail | dbt model contracts enforced |

## 7. Reliability requirements

Thresholds in this table are agent defaults (AD-019) until Thyago confirms them.

| Requirement | Mechanism | Acceptance test |
|---|---|---|
| Idempotent loads | Upsert on natural key. Each Airflow run loads only its data interval | Run the same hour twice. Row counts in every curated table are identical |
| Backfill | Airflow catchup from 2022-07-01, max_active_runs capped (D-011) | Backfill 3 months, then re-run one of them. No duplicates |
| Retries | Cloud Tasks retry config. Backoff with jitter. Respect Retry-After | A forced 429 is retried and succeeds without manual action |
| Dead-letter queue | Pub/Sub dead-letter topic with max delivery attempts | A poison message lands in the DLQ after N attempts and fires an alert |
| Controlled replay | Pub/Sub seek to snapshot or timestamp. Runbook in `docs/runbook.md` | Replay one hour of webhooks. Curated row counts unchanged |
| Failure alerts | Cloud Monitoring on DLQ depth and oldest unacked message age | Alert fires within 10 minutes of a message reaching the DLQ |
| Freshness | dbt source freshness per source | Build warns when a source is more than 2 hours late (scraping, webhooks) or more than 35 days late (CNPJ) |

## 8. Data contracts and quality

- dbt model contracts on every curated model. A column type or name change fails the build.
- Pydantic schema for LLM extraction output. Invalid outputs go to a quarantine table with the raw PDF reference, never into standardized.
- A test fails the build if `partner_document`, `legal_rep_document`, `legal_rep_name` or `age_bracket` appear in any standardized or curated model (D-018, D-052).
- Row count reconciliation between Postgres curated and BigQuery after each copy (D-014).

## 9. Out of scope (D-017)

- Personal data beyond the partner name from the CNPJ files.
- History before 2022-07-01.
- Crowdfunding platforms not in the CVM registry.
- Entity resolution by fuzzy name matching, until wave 3 (D-008).
- A public API URL. The API runs locally (D-015).

## 10. Cost guardrails

- Budget alert on the GCP project, configured before any resource is created (D-009).
- Paid surface: Cloud Run, Pub/Sub, Cloud Tasks, GCS, Vertex AI, BigQuery. Airflow, Postgres and the API run locally (D-003, D-004, D-015).
- Cost per LLM extraction measured in week 6 and written in the README.

## 11. Success criteria

- [ ] All three business questions answered by both the API and the dashboard.
- [ ] Every reliability acceptance test in section 7 passes and is documented.
- [ ] A public Looker Studio link that anyone can open.
- [ ] README with architecture, three trade-offs from `decisions.md`, and measured cost.

## 12. Open questions

- AD-013 to AD-018 in `decisions.md`.
- Thyago's own rationale for D-001, D-002 and D-014.
- Saturday study block size (A-001).
- Current CNPJ partner file layout (A-003), to check in week 2.
