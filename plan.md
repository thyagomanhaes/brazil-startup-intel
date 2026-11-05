# Plan: Wave 1 (files and batch)

Status: draft v0.5, 2026-11-03. Covers the setup in week 1 and wave 1 in weeks 2 and 3 (2026-11-02 to 2026-11-21). Items marked (AD-xxx) are agent defaults Thyago has not confirmed. See `decisions.md`.

## Goal

Two sources end to end: Receita Federal CNPJ files and the CVM crowdfunding platform registry. Raw payloads in GCS, idempotent loads into Postgres, an hourly Airflow DAG with catchup, and dbt building standardized and curated layers.

**Wave 1 is done when:**

- [ ] The same hour loaded twice gives identical row counts in every raw, standardized and curated table.
- [ ] 3 CNPJ months are backfilled, and one of them re-run with no duplicates.
- [ ] `dbt build` passes, including the test that fails if masked CPF or age bracket reach standardized (D-018).
- [ ] The architecture diagram is drawn from memory and matches the repo.

## Time budget

| Slot | Length | Use |
|---|---|---|
| Weekday lab | 15 min | One small task with its test |
| Saturday lab | 100 min | Integration, the DAG run, the end-to-end check |
| Saturday writing | 30 min | `decisions.md` updates and the weekly post |

Thyago raised the Saturday block to 3 hours (A-001). The plan uses 80% of it: 10 min DataDojo, 100 min lab, 30 min writing.

A weekday task that does not fit in 15 minutes moves to Saturday. It does not spill into the next weekday.

## Repository layout

```
brazil-startup-intel/
├── docker-compose.yml        # Airflow + data Postgres (+ FastAPI in wave 2) (D-028)
├── .env.example
├── dags/
│   ├── ingest_cnpj_monthly.py
│   ├── ingest_cvm_registry.py
│   └── load_raw_hourly.py
├── src/bsi/
│   ├── gcs_ingest.py          # streaming upload, manifest, skip-if-same-checksum
│   ├── cnpj_loader.py         # zip stream, watchlist filter, COPY, upsert
│   └── cvm_registry.py
├── sql/raw/                   # DDL for raw schema and watchlist
├── dbt/                       # standardized and curated models
├── tests/
├── docs/
│   ├── sources/cnpj.md
│   └── sources/cvm.md
├── spec.md
├── plan.md
└── decisions.md
```

## Week 1: setup (2026-11-02 to 2026-11-07)

Week 1 covers account and repository setup. P1 and P2 were both done on 2026-11-03.

| Day | Task | Done when |
|---|---|---|
| Tue 03/11 (moved up from Thu 05/11) | **P1.** Create the GCP account (personal Google account, free trial) and project `brazil-startup-intel`. Create a US$ 25/month alerts-only budget on gross cost before enabling any API (D-036, D-037, D-038) | Done 2026-11-03. Budget R$ 1,000/month, promotional credits excluded, alerts to billing admins and project owners. Trial ends 2027-02-02 (D-041) |
| Tue 03/11 (moved up from Fri 06/11) | **P2.** Raw bucket `brazil-startup-intel-513701-raw` in `us-central1`. Service account `bsi-ingest` with Object Creator and Object Viewer on that bucket only. Key outside the repo. Public repo with the docs (D-042 to D-048) | Done 2026-11-03. https://github.com/thyagomanhaes/brazil-startup-intel |

## Week 2: raw ingestion (2026-11-09 to 2026-11-14)

Each task starts with a failing test.

| Day | Task | Test first | Decisions |
|---|---|---|---|
| Tue 03/11 (moved up from Mon 09/11) | **T1.** `docker-compose.yml` from the official Airflow file, plus a data Postgres service. `pytest` wired up | A smoke test connects to the data Postgres and runs `SELECT 1` | Done 2026-11-04. D-049 to D-051, AD-036 to AD-040 |
| Wed 04/11 (moved up from Tue 10/11) | **T2.** Check the Receita download page and the layout PDF. Write `docs/sources/cnpj.md` | No code. Closes A-003 (partner columns) and A-004 (months back to 2022-07) | Done 2026-11-04. A-004 failed: CNPJ history starts at 2023-05. D-052, AD-041 to AD-043 |
| Wed 11/11 | **T3.** `object_path(source, period, fetched_at, filename)` and `sha256_stream()` | Path matches `raw/cnpj/2026-10/fetched=2026-11-09T140300Z/Empresas0.zip`. Checksum of known bytes matches. The stream is read in bounded chunks | D-030, D-046, D-053, D-054 |
| Thu 12/11 | **T4.** `upload_if_changed(url, path)`: resumable upload, manifest entry, skip when an object with the same checksum exists, new fetch-date path when the checksum differs | Uploading the same fixture twice creates one object and one manifest entry. A changed fixture creates a second object and never overwrites the first | D-027, D-030, D-043, D-046 |
| Fri 13/11 | **T5.** `cvm_registry.fetch()` writes the daily registry snapshot to `raw/cvm_registry/<date>/` | The fetch on the same day twice creates one object | D-002 |
| Sat 14/11 | **T6.** DAGs `ingest_cnpj_monthly` (latest 3 months, D-029) and `ingest_cvm_registry` (daily). Run both, then run both again | Second run uploads zero new objects. Manifest row count unchanged | D-027, D-029 |

**Week 2 deliverable:** PR with the ingestion code and the run-twice test. Post #2 (store the provider payload before you transform it).

## Week 3: load, orchestrate, transform (2026-11-16 to 2026-11-21)

| Day | Task | Test first | Decisions |
|---|---|---|---|
| Mon 16/11 | **T7.** DDL for the `raw` schema with natural keys and `competencia`. `watchlist` table seeded from the CVM registry CNPJs | Inserting a duplicate natural key fails. Watchlist count equals registry count | D-031, D-033 |
| Tue 17/11 | **T8.** `cnpj_loader.load(object)`: stream the zip from GCS, filter by watchlist, COPY to a temp table, `INSERT ... ON CONFLICT DO UPDATE` | Loading the same fixture twice leaves the same row count. A row outside the watchlist never lands | D-026, D-032 |
| Wed 18/11 | **T9.** DAG `load_raw_hourly`: each run loads the GCS objects created in its data interval. `catchup=True`, `max_active_runs` capped | Clearing and re-running one interval leaves counts unchanged | D-006, D-011 |
| Thu 19/11 | **T10.** dbt project on Postgres. Sources with freshness. Standardized models that drop masked CPF and age bracket. A test that fails if either column appears | `dbt build` passes. Adding the CPF column back to a model fails the build | D-018, AD-019 |
| Fri 20/11 | **T11.** First curated model: platforms with company data and partner names | Curated row count equals the watchlist rows found in CNPJ | D-016, D-024 |
| Sat 21/11 | **T12.** End to end: backfill 3 months through the hourly DAG, re-run one month, compare counts. Draw the diagram from memory | All four "done when" boxes at the top are checked | All of wave 1 |

20/11 is a national holiday (Consciência Negra). It stays a normal study day unless Thyago marks it off.

**Week 3 deliverable:** wave 1 closed. Post #3 (a backfill you can run twice). Stage 2 consolidated summary written in `decisions.md`.

## Checks that can change this plan

| Check | When | If it fails |
|---|---|---|
| A-003: partner file still has masked CPF and age bracket columns | T2 | Update D-018 and the leak test to the real column names |
| A-004: Receita still publishes months back to 2022-07 | T2 | CNPJ history starts at the oldest month available. CVM data keeps the 2022-07-01 cutoff |
| One CNPJ month downloads in one evening | T6 | Reopen D-027 and move the download to a Cloud Run job |
| Watchlist filter keeps Postgres small | T8 | Review D-026 |

## Not in wave 1

Webhooks, Pub/Sub, Cloud Tasks, scraping, LLM extraction, the API, BigQuery and Looker Studio. They start in wave 2 (week 4).
