# Decision Log: brazil-startup-intel

A multi-source company and funding data platform on GCP, built with public Brazilian data. This file is the public, technical decision log of the project.

How to read this file:

- **Decided by Thyago**: Thyago made the call. The rationale is his, quoted or paraphrased from his answer.
- **Agent default**: the agent picked this without an explicit answer. Thyago must review it before it counts as his decision.
- **Assumption**: something the agent took as true because nobody confirmed it. It can be wrong.
- **Open question**: asked, not answered yet.

Every stage closes with a consolidated summary in the format: context → alternatives → choice → expected consequence → how I would know I was wrong.

---

## Stage 0: Scoping (2026-10-27)

### D-002: Project domain and data sources (was AD-001)

- **Status:** Decided by Thyago, 2026-10-27. He chose "Keep it" when asked.
- **Question asked by the agent:** Keep the domain of Brazilian companies (CNPJ), CVM crowdfunding data and scraping of offer pages, or switch to sports and betting data?
- **Choice:** Brazilian companies and startup funding, using public data:
  - Receita Federal open CNPJ data (companies, establishments, partners). Monthly files.
  - CVM open data: registry of crowdfunding platforms.
  - CVM annual reports of crowdfunding platforms, published as PDFs.
  - Public offer pages of crowdfunding platforms, scraped.
  - A simulated enrichment provider that sends webhooks.
- **Rationale presented by the agent, accepted by Thyago:** It models a company research product (companies, investors, funding activity, people) and covers every intake type the platform needs: files, provider APIs, PDFs for LLM extraction, scraped pages and webhooks. Monthly CNPJ files give a real reason for backfills.
- **Thyago's own rationale (added 2026-10-27):** The topic fits the kind of company and funding data platform the project is meant to model.
- **Option not chosen:** Sports and betting data. Not chosen. A plausible reason, unconfirmed by Thyago: betting data would not model company and funding records.
- **Trade-off:**
  - Cost: the data is free.
  - Latency: CNPJ files are large and slow to download, so the first full load takes time.
  - Maintenance: CNPJ layouts have changed in the past, so the parser must fail loudly on schema drift.
  - Operational complexity: each scraping target has its own terms of use to check.

### D-003: Airflow runs locally (was AD-002)

- **Status:** Decided by Thyago, 2026-10-27. He chose "Local (Docker/Astro)".
- **Choice:** Airflow in Docker or Astro CLI on Thyago's machine, using the same Google provider operators.
- **Rationale presented by the agent, accepted by Thyago:** Near-zero cost. The DAG code and operators are the same as on Cloud Composer.
- **Thyago's own rationale:** Not stated beyond the choice.
- **Option not chosen:** Cloud Composer. Closer to production. Rejected option carried a standing monthly cost.
- **Trade-off:**
  - Cost: near zero.
  - Latency: no difference at this volume.
  - Maintenance: DAGs only run while the laptop is on. Scheduled runs need the machine available.
  - Operational complexity: lower. The cost is that the project shows no managed environment, IAM for Composer or environment upgrades.

### D-004: PostgreSQL runs in Docker locally (was AD-003)

- **Status:** Decided by Thyago, 2026-10-27. He chose "Docker local".
- **Choice:** PostgreSQL in a Docker container next to Airflow.
- **Rationale presented by the agent, accepted by Thyago:** Zero cost.
- **Thyago's own rationale:** Not stated beyond the choice.
- **Options not chosen:**
  - Cloud SQL for PostgreSQL. Closer to production, with managed backups and IAM. Bills while the instance is on.
  - Docker first, then Cloud SQL in wave 2 to show a deploy. Not chosen.
- **Trade-off:**
  - Cost: zero.
  - Latency: Cloud Run workers on GCP cannot write to a Postgres on a laptop without a tunnel. See the consequence below.
  - Maintenance: backups are manual. Data loss on the laptop means reloading from GCS raw, which the design supports.
  - Operational complexity: low.
- **Consequence the agent flags for review:** With Postgres local and workers on Cloud Run (AD-004), the cloud workers land data in GCS, and a local Airflow DAG loads GCS into Postgres. This makes GCS the hand-off point between cloud and local. It also follows the rule to preserve payloads in GCS first. Thyago has not confirmed this flow yet. Logged as **AD-009** below.

### D-005: Gemini on Vertex AI for structured extraction (was AD-006)

- **Status:** Decided by Thyago, 2026-10-27. He chose "Gemini on Vertex".
- **Choice:** Gemini on Vertex AI, with output validated against a Pydantic schema.
- **Rationale presented by the agent, accepted by Thyago:** Stays inside GCP, next to the rest of the stack.
- **Thyago's own rationale:** Not stated beyond the choice.
- **Options not chosen:**
  - Claude API with structured output through tool use. A different provider, which would mean a second set of credentials and billing.
  - Deciding later, in week 6.
- **Trade-off:**
  - Cost: per token. Measured in week 6 and written in the README.
  - Latency: one model call per PDF. Fine for batch.
  - Maintenance: model versions change, so the model ID is pinned in config.
  - Operational complexity: one cloud, one IAM model.

### D-006: Hourly freshness, with GCS as the hand-off to local Postgres (was AD-009)

- **Status:** Decided by Thyago, 2026-10-27. He chose "Hourly" as the freshness target.
- **Question asked by the agent:** Cloud Run workers write raw payloads to GCS. A local Airflow DAG loads GCS into Postgres. What freshness target is acceptable for curated data: hourly, daily, or near real-time (which would reopen D-004)?
- **Choice:** Curated data in Postgres is at most about one hour behind GCS. The Airflow load DAG runs hourly.
- **About the hand-off flow itself:** Thyago first answered inside the proposed flow (workers to GCS, Airflow to Postgres) without objecting. He confirmed the GCS hand-off explicitly on 2026-10-27 ("Eu confirmo").
- **Thyago's own rationale:** Not stated beyond the choice.
- **Options not chosen:**
  - Daily. Simplest. The laptop only needs to be on once a day.
  - Near real-time. Would need a tunnel or Cloud SQL, which reopens D-004.
- **Trade-off:**
  - Cost: none extra. Hourly GCS listing and loads are cheap.
  - Latency: up to about one hour from event to curated table, plus DAG runtime.
  - Maintenance: the laptop must be on for hourly runs. When it is off, runs are missed.
  - Operational complexity: missed runs have to be caught up. The agent proposes using Airflow catchup with idempotent upserts, so a laptop that was off for a day replays 24 runs safely. This doubles as the backfill and idempotency demo. Logged as **AD-010** below.

### D-007: Scraping rate cap of 30 requests per minute per domain (was part of AD-005)

- **Status:** Decided by Thyago, 2026-10-27. He chose "30 per minute".
- **Choice:** Each scraped domain gets at most 30 requests per minute. Enforced by the Cloud Tasks queue rate limit, plus a per-domain semaphore in the worker.
- **Thyago's own rationale:** Not stated beyond the choice.
- **Option not chosen:** 10 per minute. More conservative, lower block risk, slower backfill.
- **Trade-off:**
  - Cost: more requests per minute means more Cloud Run invocations, still small.
  - Latency: a backfill of N pages takes about N/30 minutes per domain instead of N/10.
  - Maintenance: higher chance of 429s or blocks on small crowdfunding sites.
  - Operational complexity: the failure path has to be solid: backoff with jitter, respect Retry-After, and route repeated failures to the dead-letter queue.
- **How I would know I was wrong:** 429 or 403 responses above a few percent of requests on any domain in the first week.

### D-008: Entity resolution stays the cuttable wave 3 (was AD-007)

- **Status:** Decided by Thyago, 2026-10-27. He chose "Yes, cuttable".
- **Choice:** Entity resolution is wave 3. If the schedule slips, it is the first thing cut.
- **Rationale presented by the agent, accepted by Thyago:** Entity resolution is a nice to have for this kind of platform. Event-driven intake and idempotent loading are core.
- **Thyago's own rationale:** Not stated beyond the choice.
- **Option not chosen:** Make entity resolution core and cut something else.
- **Trade-off:** If cut, the project shows exact CNPJ joins only, and entity resolution stays out of scope.

### D-009: Event-driven pieces run on real GCP (was AD-004)

- **Choice:** Cloud Run, Pub/Sub, Cloud Tasks and Cloud Storage run on a real GCP project, with a budget alert set on day one.
- **Update 2026-10-27:** Thyago has no GCP account yet (A-002). Creating the account and project moves into week 1, before the first lab on 2026-11-09.
- **Rationale presented by the agent, accepted by Thyago:** Emulators would not exercise dead-letter topics, push subscriptions, Cloud Tasks queue rate limits or replay with seek.
- **Trade-off:** Small but real cost. Needs IAM and service account setup.
- **Status:** Confirmed by Thyago, 2026-10-27 ("Confirmo"). No rationale of his own stated beyond confirming.

### D-010: Scraping only public pages, respecting robots.txt and terms of use (was AD-005)

- **Choice:** Only public pages. Respect robots.txt and each site's terms of use. The rate cap itself was decided by Thyago in D-007.
- **Rationale presented by the agent, accepted by Thyago:** Legal and ethical safety.
- **Status:** Confirmed by Thyago, 2026-10-27 ("Confirmo"). No rationale of his own stated beyond confirming.

### D-011: Missed hourly runs are caught up with Airflow catchup (was AD-010)

- **Choice:** The hourly load DAG runs with catchup enabled. Each run loads only the GCS objects for its data interval and upserts by natural key, so re-running any interval produces the same rows.
- **Rationale presented by the agent, accepted by Thyago:** It follows from D-003 and D-006. The laptop will be off sometimes. Catchup turns that into a free, recurring test of idempotency and backfill.
- **Alternative:** Each run loads "everything new since the last successful run". Simpler, but not tied to a data interval, so replaying a specific hour is harder.
- **Trade-off:** After a long gap, many runs queue up at once. Needs max_active_runs set to avoid overloading local Postgres.
- **Status:** Confirmed by Thyago, 2026-10-27 ("Confirmo"). No rationale of his own stated beyond confirming.

### D-012: Project name is brazil-startup-intel (was AD-008)

- **Choice:** `brazil-startup-intel`.
- **Status:** Confirmed by Thyago, 2026-10-27 ("Pode ser brazil-startup-intel").

### Agent defaults still open

None. Every agent default from Stage 0 was confirmed or replaced by Thyago on 2026-10-27.

### Assumptions

- **A-001:** Resolved 2026-10-27. Study time is about 1 hour per weekday. Thyago raised the Saturday block to 3 hours. The plan uses 80% of each: 50 minutes on weekdays and 140 minutes on Saturdays.
- **A-002:** Resolved 2026-10-27. Thyago has no GCP account yet. He will create one in week 1. Credits are unknown until then, so the budget alert is the first thing configured. Because of D-004, Cloud Run, Pub/Sub, Cloud Tasks, GCS and Vertex are the only paid GCP pieces.

### Stage 0 consolidated summary

Closed 2026-10-27. Format: context → alternatives → choice → expected consequence → how I would know I was wrong.

**2. Domain and sources (D-002)**
- Context: The project has to model a company research product and cover files, provider data, PDFs, scraping and webhooks with real data.
- Alternatives: Sports and betting data.
- Choice: Brazilian companies and startup funding. Receita Federal CNPJ files, CVM crowdfunding registry, CVM annual report PDFs, scraped public offer pages, a simulated enrichment webhook.
- Expected consequence: Each intake type has a concrete source to prove it on. Monthly CNPJ files give a natural reason for backfills.
- How I would know I was wrong: The CNPJ download blocks the week 2 lab for more than two sessions.

**3. Where things run (D-003, D-004, D-009)**
- Context: No GCP account yet, unknown credits, a side-project budget. The part worth paying for is event-driven intake on GCP.
- Alternatives: Cloud Composer. Cloud SQL. Cloud SQL after a local start. Emulators for Pub/Sub and Cloud Tasks.
- Choice: Airflow and Postgres in Docker on the laptop. Cloud Run, Pub/Sub, Cloud Tasks, GCS and Vertex on a real GCP project, with a budget alert set first.
- Expected consequence: The paid surface is only the event-driven pieces.
- How I would know I was wrong: The monthly GCP bill passes the budget alert.

**4. Data flow and freshness (D-006, D-011)**
- Context: Cloud workers cannot reach a Postgres on a laptop without a tunnel. Source payloads must be preserved in GCS before anything transforms them.
- Alternatives: Daily freshness. Near real-time through a tunnel or Cloud SQL. Loads of "everything new since the last run" with no data interval.
- Choice: Workers land raw payloads in GCS. An hourly Airflow DAG with catchup loads each hour's objects into Postgres with idempotent upserts.
- Expected consequence: Curated data at most about one hour behind. A laptop that was off replays its missed hours, which tests idempotency and backfill for free.
- How I would know I was wrong: Re-running the same hour changes row counts in curated tables, or catchup after a long gap overloads local Postgres.

**5. Scraping policy (D-007, D-010)**
- Context: Small crowdfunding sites, a Cloud Tasks queue with per-queue rate limits.
- Alternatives: 10 requests per minute per domain.
- Choice: 30 requests per minute per domain, public pages only, robots.txt and terms of use respected.
- Expected consequence: Faster backfills with a real failure path: backoff with jitter, Retry-After, dead-letter queue, alerts.
- How I would know I was wrong: 429 or 403 above a few percent of requests on any domain in the first week, or a site's terms of use forbid scraping.

**6. LLM for extraction (D-005)**
- Context: CVM annual reports are PDFs. The platform needs LLM structured extraction from them.
- Alternatives: Claude API. Deciding in week 6.
- Choice: Gemini on Vertex AI, output validated against a Pydantic schema, model ID pinned.
- Expected consequence: One cloud and one IAM model. Cost per PDF measured in week 6.
- How I would know I was wrong: Schema validation failures above an agreed threshold on a hand-labeled sample, or cost per PDF out of line with the budget.

**7. Scope valve (D-008)**
- Context: Entity resolution is a nice to have. Event-driven intake and idempotent loading are core.
- Alternatives: Make entity resolution core.
- Choice: Entity resolution is wave 3 and is cut first.
- Expected consequence: A slip in the schedule removes a nice to have, never a requirement.
- How I would know I was wrong: Questions 1 and 3 undercount badly without fuzzy matching.

**8. Name (D-012)**
- Choice: `brazil-startup-intel`.

**Open items carried to Stage 1:** Thyago's own rationale for D-002, the Saturday block size (A-001), and an explicit confirmation of the GCS hand-off in D-006.

---

## Stage 1: Product spec (2026-10-27)

### D-013: Who consumes the curated data

- **Status:** Decided by Thyago, 2026-10-27.
- **Question asked by the agent:** Who consumes the curated data: a simple query API, a dashboard, or only SQL tables in Postgres?
- **Thyago's answer:** "a simple query API and a dashboard", with the dashboard tool left for the agent to suggest (see D-014).
- **Thyago's own rationale:** Not stated. The agent's framing when asking: company data platforms deliver data to products, so an API tells the full story, at the cost of more scope.
- **Option not chosen:** Tables in Postgres only, queried with SQL. Smallest scope, but no consumer contract to design against.
- **Trade-off:**
  - Cost: none for the API. The dashboard cost depends on D-014.
  - Maintenance: two consumers means two contracts to keep stable when curated models change.
  - Operational complexity: the API adds one more container next to Postgres.

### D-014: Dashboard on Looker Studio, fed by BigQuery

- **Status:** Decided by Thyago, 2026-10-27. He chose "Looker Studio + BigQuery".
- **Question asked by the agent:** Postgres runs on the laptop (D-004), so nobody outside the laptop can open a live dashboard pointing at it. Metabase locally, Looker Studio with BigQuery, or Power BI?
- **Choice:** Curated tables are copied to BigQuery every hour. A Looker Studio report reads from BigQuery and is shared with a public link.
- **Thyago's own rationale (added 2026-10-27):** He picked it to use more GCP services, since GCP is the platform he is specializing in. In his words: "para poder utilizar mais serviços do GCP, visto que é o que estou me especializando". This is why he chose it over the agent's recommendation (Metabase).
- **Options not chosen:**
  - Metabase in Docker next to Postgres. The agent's recommendation: free, SQL native, no new cloud piece. Public proof would only be screenshots or a GIF in the README.
  - Power BI. A tool Thyago already knows. Desktop is Windows only, and a public link needs Publish to web from a Power BI service account.
- **Trade-off:**
  - Cost: BigQuery storage and queries for small curated tables, likely within the free tier. Unconfirmed until the account exists (A-002).
  - Latency: the dashboard trails Postgres by one more hop. Up to about one hour after the Postgres load.
  - Maintenance: two copies of curated data (Postgres and BigQuery) that must stay consistent.
  - Operational complexity: one more Airflow task and one more set of IAM permissions.
- **Side effect worth noting:** A live public link is stronger proof than a screenshot.
- **How I would know I was wrong:** Row counts in BigQuery and Postgres curated tables drift apart, or BigQuery costs leave the free tier.

### D-015: The API is FastAPI, running locally

- **Status:** Decided by Thyago, 2026-10-27. He chose "FastAPI local", which was the agent's recommendation.
- **Choice:** FastAPI in Docker next to Postgres, read-only on the curated schema.
- **Rationale presented by the agent, accepted by Thyago:** He has built REST APIs with FastAPI before. Running next to Postgres keeps D-004 intact.
- **Thyago's own rationale:** Not stated beyond the choice.
- **Option not chosen:** FastAPI on Cloud Run. A public URL, but it needs a cloud database to reach, which reopens D-004.
- **Trade-off:**
  - Cost: zero.
  - Latency: local reads, fast.
  - Maintenance: the API is only reachable while the laptop is on. The public face of the project is the Looker Studio link (D-014).
  - Operational complexity: low.

### D-016: The three business questions the system must answer

- **Status:** Decided by Thyago, 2026-10-27.
- **Question asked by the agent:** Which business question does the system answer first?
- **Thyago's answer:** All three examples the agent listed:
  1. Which startups are raising money right now, and who are their partners?
  2. How much did each platform raise per year?
  3. Which companies raised money more than once?
- **Thyago's own rationale:** Not stated.
- **Order of priority:** Not stated by Thyago. The agent keeps the order above (AD-018).
- **Consequence:** Each question needs a different source join. Question 1 needs scraped offer pages joined to CNPJ partners. Question 2 needs CVM annual reports (LLM extraction) by platform and year. Question 3 needs issuer CNPJs matched across offers.

### D-017: What is out of scope

- **Status:** Decided by Thyago, 2026-10-27.
- **Choice:**
  - Personal data beyond the partner name in the CNPJ files.
  - History before 2022-07-01. Thyago chose this date from three options. It is when CVM Resolution 88 took effect, so it is a clean regulatory boundary.
  - Crowdfunding platforms that are not in the CVM registry.
- **Options not chosen for the cutoff:** 2024-01-01 (smaller backfill, faster labs). A rolling 12-month window (smallest volume).
- **Trade-off of the cutoff:**
  - Cost and latency: the backfill covers about 4.5 years of monthly CNPJ data and CVM reports, the largest of the three options.
  - Benefit: question 3 (companies that raised more than once) has the full Resolution 88 period to look back on.
- **How I would know I was wrong:** The first backfill does not finish in a Saturday lab block, or the 2022 CNPJ files are no longer published.

### D-018: Masked CPF and age bracket stay in raw and are dropped in standardized

- **Status:** Decided by Thyago, 2026-10-27. He chose "Keep in raw, drop in standardized", which was listed first by the agent.
- **Question asked by the agent:** The CNPJ partner files include a masked CPF and an age bracket. Out of scope says no personal data beyond the partner name. Where do those columns stop?
- **Choice:** GCS raw keeps the public file exactly as published. The standardized dbt layer drops the masked CPF and age bracket columns. They never reach curated tables, BigQuery, the API or the dashboard.
- **Thyago's own rationale:** Not stated beyond the choice. The option description he picked: raw stays replay-safe.
- **Option not chosen:** Strip the columns before writing to GCS. Nothing personal is ever stored, but raw is no longer the exact source file, so a replay cannot reproduce the original.
- **Trade-off:**
  - Maintenance: a test must fail the build if either column appears in any standardized or curated model.
  - Risk: the raw bucket holds personal data published by the government. Bucket access stays private.
- **Assumption A-003:** The current CNPJ partner file layout still has a masked CPF column and an age bracket column. To verify against the layout PDF in week 2.

### Stage 1 decisions confirmed from agent defaults

### D-019: Curated tables reach BigQuery through GCS Parquet with a full replace (was AD-013)

- **Choice:** After each hourly dbt build in Postgres, an Airflow task exports the curated tables to GCS as Parquet and loads them into BigQuery, replacing each table in full.
- **Rationale presented by the agent, accepted by Thyago:** Curated tables are small. A full replace is idempotent by construction and needs no merge logic. GCS is already the hand-off point (D-006).
- **Alternatives:**
  - Run dbt a second time against BigQuery. Two warehouses to keep in sync at the model level, double the dbt runtime.
  - Datastream or another CDC tool from Postgres. Cannot reach a laptop database, and overkill at this size.
  - Incremental merge into BigQuery. Cheaper at large volume, more code, and more to get wrong.
- **Trade-off:** Full replace costs more BigQuery load operations as tables grow. Fine at this size.
- **Status:** Confirmed by Thyago, 2026-10-27 ("Confirmo"). No rationale of his own stated beyond confirming.

### D-020: Four API endpoints, one per business question plus company detail (was AD-014)

- **Choice:**
  - `GET /startups/raising`: open offers with company data and partner names.
  - `GET /platforms/{cnpj}/raised?year=`: total raised per platform per year.
  - `GET /companies/repeat-raisers`: companies with two or more offers since 2022-07-01.
  - `GET /companies/{cnpj}`: company detail with its offers and partners.
- **Rationale presented by the agent, accepted by Thyago:** One endpoint per question keeps the API contract tied to D-016. The company detail endpoint is what a product page would call.
- **Status:** Confirmed by Thyago, 2026-10-27 ("Confirmo"). No rationale of his own stated beyond confirming.

### D-021: "Raising now" means open at the last scrape, and the scrape is under 2 hours old (was AD-015)

- **Choice:** An offer is "raising now" if its platform page showed it as open at the most recent successful scrape, and that scrape is less than 2 hours old.
- **Rationale presented by the agent, accepted by Thyago:** Ties the business answer to the freshness target (D-006). A stale scrape should not report an offer as open.
- **Status:** Confirmed by Thyago, 2026-10-27 ("Confirmo"). No rationale of his own stated beyond confirming.

### D-022: "Raised more than once" means the same CNPJ in two or more offers since 2022-07-01 (was AD-016)

- **Choice:** An issuer CNPJ that appears in two or more distinct offers since 2022-07-01, across CVM reports and scraped pages. Matching is by exact CNPJ until wave 3 adds fuzzy matching by company name.
- **Consequence:** Offers where no CNPJ can be extracted are not counted until wave 3. The share of those offers is measured and reported.
- **Status:** Confirmed by Thyago, 2026-10-27 ("Confirmo"). No rationale of his own stated beyond confirming.

### D-023: Partner names stay out of the public dashboard (was AD-017)

- **Choice:** The public Looker Studio report shows companies, offers and totals. Partner names appear only in the local API.
- **Rationale presented by the agent, accepted by Thyago:** CNPJ partner names are public by law, but republishing them on an open link next to fundraising data is a privacy call that Thyago should make, not the agent.
- **Alternative:** Show partner names in the dashboard, as question 1 asks.
- **Status:** Decided by Thyago, 2026-10-27.
- **Question asked by the agent:** "Question 1 asks for the partners, so this is your call: show them in the dashboard or not?"
- **Thyago's answer:** "Não" (no). Clarified on 2026-10-27: "Sim, não mostrar os sócios no dashboard público" (yes, do not show partners on the public dashboard).
- **Thyago's own rationale:** Not stated.

### D-024: Build order follows the order of the business questions (was AD-018)

- **Choice:** Build in the order Thyago listed them: raising now, platform totals per year, repeat raisers.
- **Status:** Confirmed by Thyago, 2026-10-27 ("Confirmo"). No rationale of his own stated beyond confirming.

### D-025: Five delivery attempts before the dead-letter queue, on Pub/Sub and Cloud Tasks

- **Status:** Decided by Thyago, 2026-10-27, in two steps.
  1. First answer: "3". The agent applied it to Pub/Sub and, as an agent default, to Cloud Tasks.
  2. The agent then checked the Pub/Sub documentation: max delivery attempts has a minimum of 5, a default of 5 and a maximum of 100. A value of 3 is not valid. Cloud Tasks sets its retry ceiling separately and could take 3. Source: https://docs.cloud.google.com/pubsub/docs/dead-letter-topics
  3. Second answer, after three options: "Escolho 2", meaning 5 attempts on both Pub/Sub and Cloud Tasks.
- **Choice:** Max 5 delivery attempts before the dead-letter path, on Pub/Sub subscriptions and on Cloud Tasks queues.
- **Thyago's own rationale (added 2026-10-27):** He first chose 3 because he had no reference for a standard or reasonable number. In his words: "não tinha noção de uma quantidade padrão e razoável". He then picked 5 on both paths from the options offered after the Pub/Sub minimum came up. The option description he picked: same rule everywhere, simpler to explain. He did not add a separate reason for 5 over the 5-and-3 split.
- **Options not chosen:**
  - 5 on Pub/Sub and 3 on Cloud Tasks. Each path as close as possible to the original intent of 3. Two different rules to document and explain.
  - Another single value between 5 and 100. More tolerance for long provider outages, slower dead-lettering.
- **Trade-off:**
  - Latency: a poison message takes up to 5 attempts, plus backoff, before it reaches the DLQ. Slower alerting than 3 would have given.
  - Operational complexity: one rule across both queues. The replay runbook has a single threshold.
  - Cost: two more attempts per failing message. Negligible at this volume.
- **How I would know I was wrong:** Scraping failures that are clearly permanent (404, page removed) burn 5 attempts each and delay the alert. If so, the worker should classify those as non-retryable and acknowledge them straight into a quarantine table, without spending attempts.

### Agent defaults still open (Stage 1)

#### AD-019: Reliability thresholds in spec section 7 (agent default)

- **Choice:** The numbers in the reliability table of `spec.md` are the agent's, not Thyago's:
  - Freshness warning when scraping or webhooks are more than 2 hours late, and when CNPJ files are more than 35 days late (monthly source plus a few days of slack).
  - Alert within 10 minutes of a message reaching the dead-letter queue.
- **Why the agent picked them:** 2 hours is twice the hourly cadence (D-006). 35 days covers a monthly release that slips a few days. 10 minutes is short enough to act within the same hour.
- **Update 2026-10-27:** Max delivery attempts is now decided in D-025 (5). He did not comment on the other three numbers when asked to confirm or change them. They stay agent defaults until he confirms explicitly.

### Stage 1 consolidated summary

Closed 2026-10-27, with AD-019 (three thresholds) still open. Format: context → alternatives → choice → expected consequence → how I would know I was wrong.

**1. Consumers and serving (D-013, D-014, D-015, D-019, D-020)**
- Context: Company data platforms deliver data to products. Postgres and Airflow run on the laptop (D-003, D-004), so anything public has to live in the cloud.
- Alternatives: Postgres tables only. Metabase locally (the agent's recommendation). Power BI. FastAPI on Cloud Run. dbt run twice, CDC or incremental merge into BigQuery.
- Choice: A local read-only FastAPI with four endpoints, and a public Looker Studio report on BigQuery. Curated tables are exported to GCS as Parquet and fully replaced in BigQuery every hour.
- Expected consequence: Anyone can open a live link. The API proves the consumer contract.
- How I would know I was wrong: Postgres and BigQuery row counts drift, BigQuery leaves the free tier, or nobody opens the dashboard link.

**2. What the product answers (D-016, D-021, D-022, D-024)**
- Context: Three questions need three different joins: scraped offers with CNPJ partners, LLM-extracted totals by platform and year, issuer CNPJs across offers.
- Alternatives: Picking one question first and dropping the others.
- Choice: All three, built in the listed order. "Raising now" is tied to a scrape under 2 hours old. "Raised more than once" uses exact CNPJ matching until wave 3.
- Expected consequence: Each wave ends with a question answered end to end.
- How I would know I was wrong: Most scraped offers have no extractable CNPJ, so question 3 undercounts before wave 3.

**3. Scope and privacy (D-017, D-018, D-023)**
- Context: CNPJ partner files carry personal data. The project publishes a public dashboard.
- Alternatives: Cutoffs of 2024-01-01 or a rolling 12 months. Stripping personal columns before GCS. Showing partner names publicly.
- Choice: History from 2022-07-01 (Resolution 88). Masked CPF and age bracket kept in raw, dropped in standardized, with a test that fails the build if they leak. Partner names only in the local API.
- Expected consequence: Raw stays replay-safe. Nothing personal beyond names leaves the laptop, and names never reach the public link.
- How I would know I was wrong: The backfill from 2022-07-01 does not fit in a Saturday block, or a personal column shows up in BigQuery.

**4. Failure handling (D-025)**
- Context: Retries alone leave failed work with nowhere to go.
- Alternatives: Higher delivery attempt counts.
- Choice: 5 attempts before the DLQ on both Pub/Sub and Cloud Tasks. Thyago first chose 3. Pub/Sub's documented minimum is 5, so he moved to 5 on both paths.
- Expected consequence: One retry rule across the platform. Transient errors mostly recover before the DLQ.
- How I would know I was wrong: Permanent errors (404, removed pages) burn all 5 attempts and delay alerts. Fix by classifying them as non-retryable in the worker.

**Open items carried to Stage 2:** AD-019 thresholds, Thyago's rationale for D-002, D-014 and D-025, A-001 (Saturday block), A-003 (CNPJ partner layout).

---

## Stage 2: Wave 1 plan (2026-10-27)

### D-026: CNPJ data is filtered by a watchlist before it reaches Postgres

- **Status:** Decided by Thyago, 2026-10-27. He chose "Watchlist filter", which was the agent's recommendation.
- **Question asked by the agent:** Each monthly CNPJ release is a full snapshot of all Brazilian companies, several GB zipped. With history from 2022-07-01 (D-017), that is 50+ snapshots. How much goes where?
- **Choice:** GCS raw keeps the monthly zip files as published. Postgres loads only rows whose `cnpj_basico` is on a watchlist: the CVM crowdfunding platforms first, then issuers found in offers and reports. When a new issuer joins the watchlist, older months are replayed from GCS for that CNPJ.
- **Rationale presented by the agent, accepted by Thyago:** Keeps the laptop database small. Raw stays complete, so replay works. Adding an issuer becomes a real, routine replay.
- **Thyago's own rationale:** Not stated beyond the choice.
- **Options not chosen:**
  - Latest month only, one state (Sergipe). Smallest. The backfill story would move to CVM data only.
  - Latest month, whole country. Tens of millions of rows on the laptop. A strong scale story, and a heavy laptop.
- **Trade-off:**
  - Cost: GCS storage grows by one monthly snapshot per month kept.
  - Latency: a new issuer's history appears only after its replay finishes.
  - Maintenance: the watchlist is a new table that drives loads, so it needs its own tests.
  - Operational complexity: two load modes, the normal hourly load and the per-CNPJ replay.
- **How I would know I was wrong:** Replays for new issuers take longer than one Saturday lab, or GCS storage cost passes the budget alert.

### D-027: The Receita download runs as an Airflow task on the laptop

- **Status:** Decided by Thyago, 2026-10-27. He chose "Airflow task on laptop".
- **Choice:** An Airflow task streams each Receita file from the source straight to GCS through Thyago's home connection.
- **Thyago's own rationale:** Not stated beyond the choice.
- **Option not chosen:** A Cloud Run job, triggered by Airflow, downloading cloud to cloud. Faster and independent of home bandwidth. More setup in week 2.
- **Trade-off:**
  - Cost: none in GCP compute. Home bandwidth is used for every monthly snapshot.
  - Latency: download time depends on the home connection. Several GB per month.
  - Maintenance: a dropped connection mid-file must not leave a half object in GCS. Resumable uploads and a checksum manifest handle that (AD-022).
  - Operational complexity: lower than a Cloud Run job.
- **How I would know I was wrong:** A single month takes more than one evening to download, or partial files reach GCS.

### D-028: Airflow runs with Docker Compose

- **Status:** Decided by Thyago, 2026-10-27. He chose "Docker Compose".
- **Choice:** The official Airflow Docker Compose file, extended with the data Postgres and, later, the FastAPI service. One `docker-compose.yml` for the whole local stack.
- **Thyago's own rationale:** Not stated beyond the choice. The option description he picked: full control.
- **Option not chosen:** Astro CLI. Faster setup, opinionated project layout.
- **Trade-off:**
  - Maintenance: upgrades of the Airflow image are manual.
  - Operational complexity: more YAML to own, and every service visible in one file.

### D-029: Wave 1 downloads only the latest 3 CNPJ months (was AD-021)

- **Status:** Decided by Thyago, 2026-10-27.
- **Question asked by the agent:** Are 3 months enough to prove the backfill, or do you want to show more volume from the start?
- **Thyago's answer and rationale:** "3 meses bastam sim" (3 months are enough).
- **Choice:** Wave 1 downloads the latest 3 monthly releases. Older months, back to 2022-07-01, come later, when a watchlisted issuer needs them or in a dedicated backfill session.
- **Option not chosen:** Downloading more months up front for a bigger volume story.
- **Trade-off:**
  - Cost: smallest GCS storage and home bandwidth (D-027).
  - Latency: the full history is not in GCS until later sessions.
  - Maintenance: the first per-issuer replay in wave 2 will also be the first download of old months, so two new things run at once there.
- **Open check A-004:** Whether Receita still publishes months back to 2022-07. Task T2, 2026-11-10.
- **How I would know I was wrong:** The 3-month backfill passes, but the first old-month replay in wave 2 fails for reasons the 3-month run never exercised.

### D-030: GCS ingest skips files that already exist with the same SHA-256 (was AD-022)

- **Status:** Decided by Thyago, 2026-10-27.
- **Question asked by the agent:** Do you accept paying the time to compute checksums in exchange for running the DAG as many times as you want without duplicates?
- **Thyago's answer and rationale:** "Aceito pagar o tempo de calcular o checksum" (I accept paying the time to compute the checksum).
- **Choice:** Resumable upload to `raw/cnpj/<yyyy-mm>/<file>`. A manifest records source URL, size, SHA-256 and fetch time. An object that already exists with the same checksum is skipped.
- **Option not chosen:** Upload without checksums and overwrite or skip by file name only. Faster, but a changed file with the same name would be missed, and a partial upload could be taken as complete.
- **Trade-off:**
  - Latency: one extra pass over every byte to hash it. Several GB per month on the laptop.
  - Maintenance: the manifest is one more artifact to keep consistent with the bucket.
  - Benefit: re-runs are safe, and a source file that changes under the same name is detected.
- **How I would know I was wrong:** Hashing takes a large share of the download time, or the manifest and the bucket disagree after a failed run.

### D-031: Raw natural keys include the release month, and the partner key is composite (was AD-023)

- **Status:** Decided by Thyago, 2026-10-27.
- **Question asked by the agent:** If two partners of the same company have the same name, does the composite partner key keep them apart?
- **Thyago's answer and rationale:** "Se tiverem o mesmo nome, terão CPFs diferentes, então deve separar" (if they have the same name, they will have different CPFs, so the key should separate them).
- **Choice:**
  - Every raw CNPJ row carries `competencia`. Raw keeps one version per month. Curated reads the latest.
  - Companies: `cnpj_basico` plus `competencia`.
  - Establishments: `cnpj_basico`, `cnpj_ordem`, `cnpj_dv` plus `competencia`.
  - Partners: `cnpj_basico`, partner identifier type, partner name, masked document, qualification, entry date, plus `competencia`.
- **Caveat the agent adds, not part of Thyago's rationale:** The CPF in the public file is masked. As far as the agent knows, only some middle digits are visible, so two different people with the same name could, in rare cases, share the same visible digits. Partners that are companies or foreigners use other document formats. Task T7 measures this: count partner rows that collide on the key in one month. Zero collisions confirms Thyago's reasoning on real data.
- **Option not chosen:** A surrogate key per row with no deduplication. Simpler, and every re-run would duplicate partners.
- **Trade-off:**
  - Maintenance: if the Receita layout changes a key column, loads fail loudly. That is the intended behavior.
  - Privacy: the masked document is part of the key in the Postgres raw schema only. Standardized drops it (D-018).
- **How I would know I was wrong:** The collision count in T7 is above zero, or the same partner shows up twice in curated after a re-run.

### D-032: Load with COPY into a staging table, then INSERT ON CONFLICT (was AD-024)

- **Status:** Decided by Thyago, 2026-10-27.
- **Question asked by the agent:** Do you prefer this pattern, or something simpler to start?
- **Thyago's answer and rationale:** He wants the pattern a production platform uses: idempotent upserts and incremental loading in PostgreSQL.
- **Choice:** Stream the zip from GCS, filter rows by watchlist, COPY into a temporary table, then `INSERT ... ON CONFLICT (natural key) DO UPDATE` into raw.
- **Option not chosen:** Row-by-row INSERT ON CONFLICT. Simpler code, much slower on monthly files.
- **Trade-off:**
  - Latency: COPY is the fastest bulk path in Postgres.
  - Maintenance: two steps per load, so a failure between them must leave raw untouched. The load runs in one transaction.
- **How I would know I was wrong:** A load interrupted midway leaves partial rows in raw, or the upsert step dominates load time.

### D-033: The watchlist starts with the CVM platform CNPJs (was AD-025)

- **Status:** Confirmed by Thyago, 2026-10-27 ("Aceito"). No rationale of his own stated beyond accepting.
- **Question asked by the agent:** Do you accept ending wave 1 with no startups in the database, only platforms?
- **Choice:** In wave 1 the watchlist holds only the CNPJs from the CVM crowdfunding platform registry. Issuers are added in wave 2, from scraped offers and extracted reports.
- **Consequence:** At the end of wave 1, Postgres holds platforms and their partners. Questions 1 and 3 need wave 2 data.
- **Option not chosen:** Seeding issuers by hand in wave 1 to have startups early. Faster to demo, and the watchlist would start with data that did not come through the pipeline.
- **How I would know I was wrong:** Wave 2 slips and the project has no startup data to show by 2026-12-19.

### D-034: GCP authentication from the laptop uses a service account key (was AD-026, agent default rejected)

- **Status:** Decided by Thyago, 2026-10-27. He rejected the agent default (Application Default Credentials).
- **Question asked by the agent:** Do you prefer logging in with your own account (ADC), or a service account with a key file, which is closer to how a server runs?
- **Thyago's answer:** "Prefiro service account com chave" (I prefer a service account with a key).
- **Thyago's own rationale (added 2026-10-27):** He does not want the pipeline to run on his personal credentials. In his words: "para não precisar utilizar credenciais pessoais".
- **Option not chosen:** Application Default Credentials with his own user account. The agent's default. No key file on disk.
- **Trade-off:**
  - Security: a key file can leak. Mitigations the agent will apply unless Thyago objects (agent default, AD-027): the key lives outside the repo, `*.json` keys are in `.gitignore`, the file is mounted read-only into the containers, the service account gets only the roles it needs (write to the raw bucket, later Pub/Sub and Cloud Tasks), and the key is rotated every 90 days.
  - Realism: the containers run as a service identity, as they would on a server. Permissions are tested with least privilege from day one, which a user login would hide.
  - Operational complexity: one service account and one key to manage.
- **Possible blocker:** Some Google Cloud organizations block service account key creation by policy. A personal account without an organization is usually not affected. Checked in task P2.
- **How I would know I was wrong:** The key ends up in a commit, or key creation is blocked by policy on the new account.

### D-035: Service account key hygiene (was AD-027)

- **Status:** Confirmed by Thyago, 2026-10-27 ("Confirmo"). No rationale of his own stated beyond confirming.
- **Choice:** The key file lives outside the repo. Key file patterns are in `.gitignore`. The key is mounted read-only into the containers. The service account gets only the roles it needs: write to the raw bucket in wave 1, then Pub/Sub, Cloud Tasks and BigQuery as each wave needs them. The key is rotated every 90 days.
- **Rationale presented by the agent, accepted by Thyago:** D-034 puts a long-lived credential on disk. These steps reduce the chance of a leak and limit the damage if one happens.
- **Option not offered in detail:** A shorter rotation period. Safer, and more manual work for a side project.
- **Trade-off:** One more routine task every 90 days. Roles must be added wave by wave, so missing permissions show up as errors during labs. That is the point of least privilege.
- **How I would know I was wrong:** A key shows up in `git log`, or a lab session is lost to permission errors more than once per wave.

### Stage 2 consolidated summary

Closed 2026-10-27. No agent defaults open in this stage. Format: context → alternatives → choice → expected consequence → how I would know I was wrong.

**1. How much CNPJ data, and where (D-026, D-029)**
- Context: Each monthly CNPJ release is a full national snapshot, several GB zipped. The cutoff is 2022-07-01 (D-017). Postgres runs on a laptop (D-004).
- Alternatives: Latest month for one state. Latest month for the whole country. More months downloaded up front.
- Choice: GCS keeps full monthly zips. Postgres loads only watchlisted CNPJs. Wave 1 downloads the latest 3 months.
- Expected consequence: A small database, a complete raw layer, and per-issuer replays as a routine operation.
- How I would know I was wrong: Replays for new issuers do not fit in a Saturday lab, or GCS storage passes the budget alert.

**2. Getting files into GCS safely (D-027, D-030)**
- Context: Downloads run on the home connection. Connections drop.
- Alternatives: A Cloud Run job for the download. Uploading without checksums.
- Choice: An Airflow task streams files to GCS with resumable uploads, a SHA-256 manifest, and skip-if-same-checksum.
- Expected consequence: Re-running ingestion never duplicates or half-writes a file.
- How I would know I was wrong: A month takes more than an evening to download, or the manifest and the bucket disagree.

**3. Idempotent loading into Postgres (D-031, D-032)**
- Context: The platform needs idempotent upserts and incremental loading. CNPJ partner rows have no official key.
- Alternatives: Row-by-row inserts. Surrogate keys with no deduplication.
- Choice: Natural keys with `competencia`. A composite partner key including the masked document. COPY into a temp table, then INSERT ON CONFLICT in one transaction.
- Expected consequence: Loading the same hour or month twice gives identical counts.
- How I would know I was wrong: Key collisions in T7, or duplicate partners in curated after a re-run.

**4. What wave 1 ends with (D-033)**
- Context: Issuers come from scraping and PDFs, which are wave 2.
- Alternatives: Seeding issuers by hand.
- Choice: The watchlist holds platform CNPJs only.
- Expected consequence: Wave 1 proves the pipeline. The business questions start getting answers in wave 2.
- How I would know I was wrong: Wave 2 slips and there is no startup data by 2026-12-19.

**5. Identity in GCP (D-028, D-034)**
- Context: Airflow runs in Docker Compose on the laptop and needs to write to GCS.
- Alternatives: Application Default Credentials. Astro CLI for Airflow.
- Choice: Docker Compose. A least-privilege service account with a key, stored outside the repo, mounted read-only and rotated every 90 days (D-035).
- Expected consequence: Permissions behave as they would on a server from day one.
- How I would know I was wrong: Key creation is blocked by policy, or the key leaks into a commit.

**Open items carried to wave 1 execution:** AD-019 thresholds, A-003 and A-004 (checked in T2). Update 2026-10-27: Thyago added his rationale for D-002, D-014, D-025 and D-034, and resolved A-001 (Saturday block raised to 3 hours).

---

## Stage 3: GCP account and cost guardrails (2026-11-03, task P1 moved up from 2026-11-05)

### Facts checked against Google Cloud documentation on 2026-11-03

- Free trial: US$ 300 credit for 90 days. A card is required. Google places a temporary hold of up to US$ 1. No billing during the trial. When the 90 days end or the credit runs out, the trial billing account closes and resources stop, with a 30-day grace period to upgrade. Source: https://docs.cloud.google.com/free/docs/free-cloud-features
- An alerts-only budget does not cap spending. It only sends alerts. By default it measures cost after credits, so during the trial it would read close to zero. Source: https://docs.cloud.google.com/billing/docs/how-to/budgets
- Spend cap budgets pause new usage of one service in one project when gross cost passes the target. Eligible services include Cloud Run and Vertex AI (Gemini). Enforcement is not instant. Source: https://docs.cloud.google.com/billing/docs/how-to/budgets-spend-caps
- Cloud Storage free tier covers 5 GB-months of regional storage in us-east1, us-west1 and us-central1 only. Relevant for the bucket region in task P2.

### D-036: Budget alert of US$ 25 per month on gross cost

- **Status:** Decided by Thyago, 2026-11-03. He chose "US$ 25/mês" from three options.
- **Question asked by the agent:** Which monthly amount should the budget alert watch? It measures gross cost, before the US$ 300 trial credit.
- **Choice:** One alerts-only budget, monthly, scoped to the `brazil-startup-intel` project, US$ 25 (or the equivalent in the billing account currency).
- **Thyago's own rationale:** Not stated beyond the choice. The option description he picked: room for the Vertex and backfill labs.
- **Options not chosen:**
  - US$ 10 per month. Earlier warning. The project at this scale should stay close to zero.
  - US$ 50 per month. Fewer and later warnings.
- **Trade-off:** A higher threshold means fewer false alarms during heavy lab weeks (Vertex extraction in week 6, backfills), and a later warning if something runs away.
- **How I would know I was wrong:** The 50% alert (US$ 12.50) fires in a normal week, or a runaway cost goes past US$ 25 before any alert arrives.

### D-037: Stay on the free trial until the plan ends

- **Status:** Decided by Thyago, 2026-11-03. He chose "Ficar no trial".
- **Choice:** No upgrade to a paid billing account before 2026-12-27. The trial runs to 2027-02-02, as shown in the billing console on 2026-11-03, which covers the whole 8-week plan.
- **Thyago's own rationale:** Not stated beyond the choice. The option description he picked: no charge is possible.
- **Option not chosen:** Upgrade now. Resources would not stop at the end of the trial, and spend above the credit would be charged to the card.
- **Trade-off:**
  - Cost: zero risk of a card charge during the plan. This is the real hard cap.
  - Operational complexity: when the trial ends, everything stops. The decision to upgrade or shut down comes back before 2027-02-01.
- **How I would know I was wrong:** The US$ 300 credit runs out before 2026-12-27 and the event-driven pieces stop mid-plan.

### Account facts recorded on 2026-11-03

From Thyago's message and his screenshot of Billing > Overview:

- Project ID: `brazil-startup-intel-513701`. The plain name was already taken. This ID is permanent.
- Billing account currency: BRL (R$).
- Free trial credit: R$ 1,831, shown as the equivalent of the US$ 300 credit. Implied rate in his console: about R$ 6.10 per US$.
- Trial end: 2027-02-02. 90 days remaining on 2026-11-03.
- Spend so far: R$ 0.00.

### D-036 update: the budget amount in BRL

- D-036 was decided in USD (US$ 25 per month). The billing account is in BRL, so the budget must be entered in reais.
- Agent conversion, using the rate implied by Thyago's own console (R$ 1,831 / US$ 300): US$ 25 is about R$ 153. The agent proposes **R$ 150**, rounded. Thresholds: 50% at R$ 75, 90% at R$ 135, 100% at R$ 150.
- This rounding was an agent default. Superseded: Thyago set R$ 1,000 (see the D-036 revision below).

### D-036 revision: Thyago set the budget at R$ 1,000 per month

- **Status:** Decided by Thyago, 2026-11-03, directly in the console. Shown in his screenshot of the Edit Budget page.
- **What he set:** Thresholds at 50% (R$ 500), 90% (R$ 900) and 100% (R$ 1,000), all on **Actual** spend. Email alerts to billing admins and users, and to project owners. No forecasted threshold. No Monitoring channel or Pub/Sub topic linked.
- **What this replaces:** The earlier choice of US$ 25 per month and the agent's BRL conversion of R$ 150. R$ 1,000 is about US$ 164 at the rate implied by his console.
- **Thyago's own rationale (added 2026-11-03):** "It's fine to me." No further reason given.
- **Trade-off the agent flagged:**
  - The whole trial credit is R$ 1,831. The first alert fires at R$ 500, after about 27% of the credit is spent in a single month.
  - Two months at the 100% mark would use more than the full credit, and the trial would end early, stopping every resource.
  - Without a forecasted threshold, every alert arrives after the money is spent.
- **Budget scope, from a second screenshot on 2026-11-03:** All services (1781). Savings: Promotional credits **unchecked**, Others unchecked. Free tier credits, sustained use discounts, spending-based discounts, subscription credits and savings programs checked. The free trial credit is a promotional credit as far as the agent knows, so the budget measures cost before the trial credit, as intended. Free tier usage stays netted out, which is correct: free tier usage costs nothing.
- **AD-028 outcome:** The credits part is done as proposed. The forecasted threshold was not added. Thyago set the thresholds himself.
- **How I would know I was wrong:** The R$ 500 alert fires and most of it was avoidable, or the trial credit runs out before 2026-12-27.

### D-038: The budget ignores promotional credits (was AD-028, partly adopted)

- **Choice:** In the budget scope, credits and promotions are unchecked, so the budget tracks gross cost. Thresholds at 50%, 90% and 100% of actual spend, plus 100% of forecasted spend. Emails go to billing admins and project owners.
- **Rationale presented by the agent, accepted by Thyago:** With credits included, a trial budget reads near zero and never fires. The forecasted threshold warns before the money is spent.
- **Status:** Partly adopted by Thyago, 2026-11-03. Promotional credits are unchecked as proposed. He set the thresholds himself at R$ 500, R$ 900 and R$ 1,000 on actual spend, with no forecasted threshold (see the D-036 revision).

### D-039: The account is Thyago's personal Google account (was AD-029)

- **Choice:** The GCP account and billing account sit on Thyago's personal Google account, separate from any employer account.
- **Rationale presented by the agent, accepted by Thyago:** The project is personal public work. It must not touch an employer's organization, policies or billing.
- **Status:** Confirmed by Thyago, 2026-11-03 ("I confirm"). No rationale of his own stated beyond confirming.

### D-040: Spend caps on Cloud Run and Vertex AI when each is first used (was AD-030)

- **Choice:** Add a spend cap budget for Cloud Run in week 4 and for Vertex AI in week 6, the first time each service is used.
- **Rationale presented by the agent, accepted by Thyago:** These are the two eligible services, and the two most likely to run away (a loop of requests, a batch of LLM calls). The trial already blocks card charges (D-037), so the caps mainly protect the US$ 300 credit.
- **Open question:** The spend cap documentation does not say whether caps work on free trial accounts. To check in week 4.
- **Status:** Confirmed by Thyago, 2026-11-03 ("I confirm"). No rationale of his own stated beyond confirming.

### D-041: New done criterion for task P1 (was AD-031)

- **Choice:** P1 is done when the budget is listed with the right scope, credits unchecked and recipients set, and the trial end date is written down. The original criterion, "budget alert email arrives on a test threshold", cannot be met with zero spend.
- **Status:** Confirmed by Thyago, 2026-11-03 ("I confirm"). No rationale of his own stated beyond confirming.

### D-042: The raw bucket lives in us-central1

- **Status:** Decided by Thyago, 2026-11-03. Answer: "us-central is okay". The agent reads this as the `us-central1` region, the one named in the question.
- **Question asked by the agent:** `us-central1`, inside the Cloud Storage free tier, or `southamerica-east1` (São Paulo), outside the free tier?
- **Thyago's own rationale:** Not stated beyond the choice. The option description: inside the free tier.
- **Option not chosen:** `southamerica-east1`. Closer to the Brazilian sources and to Thyago, outside the free tier.
- **Trade-off:**
  - Cost: the first 5 GB-months of regional storage are free. Monthly CNPJ zips will pass that over time (D-026, D-029).
  - Latency: downloads from Brazil and uploads from Brazil cross to the US. Fine for hourly batch.
  - Consistency: later regional resources (Cloud Run, Pub/Sub, Cloud Tasks, BigQuery) should sit in the same region to avoid cross-region egress. That is an agent default for later stages (AD-032).
- **How I would know I was wrong:** Storage passes the free tier in the first month, or cross-region egress shows up in the cost table.

#### AD-032: Every regional resource goes to us-central1 (agent default)

- **Choice:** Cloud Run, Pub/Sub, Cloud Tasks, Vertex AI and the BigQuery dataset use `us-central1` (BigQuery may use the `US` multi-region).
- **Why the agent picked it:** Same region as the bucket (D-042), so no cross-region data transfer.
- **Thyago must confirm in week 4.**

### Stage 3 consolidated summary

Closed 2026-11-03, with AD-032 left for week 4. Format: context → alternatives → choice → expected consequence → how I would know I was wrong.

**1. Hard cap on cost (D-037, D-039)**
- Context: No GCP account before this stage. A side project with no budget line.
- Alternatives: Upgrade to a paid billing account right away.
- Choice: Free trial on Thyago's personal Google account, no upgrade before 2026-12-27. Trial ends 2027-02-02 with R$ 1,831 of credit.
- Expected consequence: No card charge is possible during the plan.
- How I would know I was wrong: The credit runs out before 2026-12-27 and resources stop mid-plan.

**2. Early warning on spend (D-036, D-038)**
- Context: Budgets only alert. During a trial, a budget that nets out credits reads zero.
- Alternatives: US$ 10, 25 or 50 per month. The agent's R$ 150 conversion with a forecasted threshold.
- Choice: R$ 1,000 per month on gross cost (promotional credits excluded), alerts at R$ 500, R$ 900 and R$ 1,000 on actual spend.
- Expected consequence: Few alerts in normal weeks.
- How I would know I was wrong: The first alert arrives after a large part of the R$ 1,831 credit is gone.

**3. Per-service caps (D-040)**
- Context: Cloud Run and Vertex AI are the services most likely to run away, and both support spend caps.
- Choice: A spend cap on each, added in the week it is first used.
- How I would know I was wrong: Caps turn out unavailable on trial accounts (to check in week 4).

**4. Region (D-042)**
- Context: The Cloud Storage free tier only covers US regions.
- Alternatives: São Paulo.
- Choice: `us-central1`.
- How I would know I was wrong: Storage or egress costs appear before week 4.

**5. Done criterion (D-041)**
- P1 is done when the budget is listed with the right scope and recipients and the trial end date is recorded. Done on 2026-11-03, two days early.


---

## Stage 4: Task P2, bucket, service account and repository (2026-11-03, moved up from 2026-11-06)

### D-043: The ingest service account can create and read raw objects, never overwrite or delete

- **Status:** Decided by Thyago, 2026-11-03. He chose "Creator + Viewer", the agent's recommendation.
- **Question asked by the agent:** What can the service account do on the raw bucket? The spec says raw is write-once and never edited.
- **Choice:** Service account `bsi-ingest` gets two roles, granted on the raw bucket only, with no project-level roles:
  - Storage Object Creator: create objects.
  - Storage Object Viewer: read and list objects.
- **Rationale presented by the agent, accepted by Thyago:** Write-once is enforced by IAM, so a bug in the code cannot rewrite or delete raw.
- **Thyago's own rationale:** Not stated beyond the choice.
- **Option not chosen:** Storage Object Admin. Create, read, overwrite and delete. Simpler, and one bug can rewrite raw.
- **Consequence for the code:** Uploading to an object name that already exists fails with a permission error, because overwriting needs delete permission. D-030 already skips identical files. A source file that changed under the same name must land under a new object path, for example with the fetch date in the name. Logged as AD-033.
- **Trade-off:**
  - Maintenance: cleaning up a bad upload needs a human with higher permissions.
  - Safety: raw keeps every payload exactly as received, which is what replay depends on.
- **How I would know I was wrong:** Legitimate re-ingestion keeps failing on name collisions, or cleanup by hand becomes a weekly task.

### D-044: Personal planning files move out of the project folder

- **Status:** Decided by Thyago, 2026-11-03. He chose "Move them out", the agent's recommendation.
- **Question asked by the agent:** The project folder also holds the Notion CSVs and the `planejamento` folder (personal planning notes). The repo will be public. What do we do with them?
- **Choice:** Thyago moves the five Notion CSVs at the folder root and the `planejamento` folder to a separate folder outside the repo.
- **Option not chosen:** Keep them in the folder and list them in `.gitignore`. One `git add -f` or a broken ignore rule would publish them.
- **Thyago's own rationale:** Not stated beyond the choice.

### Bucket state recorded on 2026-11-03

From Thyago's screenshots of the bucket details page:

- Bucket `brazil-startup-intel-513701-raw` exists. Location `us-central1` (Iowa). Standard class. Not public, with public access prevention enforced against allUsers and allAuthenticatedUsers. Uniform access, no object ACLs. Soft delete on.
- Bucket permissions: `bsi-ingest@brazil-startup-intel-513701.iam.gserviceaccount.com` has Storage Object Creator and Storage Object Viewer, as D-043 requires.
- The bucket also carries the default legacy bindings that Google adds for project owners, editors and viewers. These cover human accounts on the project and are left as they are.
- Not yet confirmed: the JSON key and its location.

### D-045: The public decision log is technical only

- **Status:** Decided by Thyago, 2026-11-03. He chose "technical-only version".
- **Question asked by the agent:** The repo will be public. Publish the full decision log, or a technical-only version?
- **Choice:** The repo's `decisions.md` keeps only technical decisions. Personal and career context stays in a private file outside the repo.
- **Option not chosen:** Publishing the full log.
- **Trade-off:** Two files to keep in step. Every new decision is written to both, with personal context removed from the public one.

### D-046: A changed source file lands under a new object path (was AD-033)

- **Choice:** Object paths include the fetch date, for example `raw/cnpj/2026-10/fetched=2026-11-09/Empresas0.zip`. Same checksum: skip (D-030). Different checksum under the same source name: write a new object with the new fetch date, and keep both.
- **Rationale presented by the agent, accepted by Thyago:** It follows from D-043. Overwrite is not allowed, and keeping both versions is what replay needs.
- **Status:** Confirmed by Thyago, 2026-11-03 ("I confirm"). No rationale of his own stated beyond confirming.

### D-047: Bucket settings (was AD-034)

- **Choice:** Name `brazil-startup-intel-513701-raw`. Region `us-central1` (D-042). Standard storage class. Public access prevention on. Uniform bucket-level access. Object versioning off. Default soft delete kept.
- **Rationale presented by the agent, accepted by Thyago:** The project ID in the name makes it globally unique. Versioning is not needed, because the service account cannot overwrite.
- **Status:** Confirmed by Thyago, 2026-11-03 ("I confirm"). No rationale of his own stated beyond confirming.

### D-048: Key file location (was AD-035)

- **Choice:** `C:\Users\thyag\.gcp\bsi-ingest-key.json`. Outside the repo, outside Downloads, and outside any OneDrive-synced folder.
- **Rationale presented by the agent, accepted by Thyago:** A key in a synced or shared folder leaves the laptop. D-035 already requires the key outside the repo.
- **Status:** Confirmed by Thyago, 2026-11-03 ("I confirm"). No rationale of his own stated beyond confirming.

### Agent defaults still open (Stage 4)

None.

### Stage 4 consolidated summary

Closed 2026-11-03, three days before the planned date for task P2. Format: context → alternatives → choice → expected consequence → how I would know I was wrong.

**1. Write-once raw, enforced by IAM (D-043, D-046)**
- Context: The spec says raw is never edited. Code alone cannot guarantee that.
- Alternatives: Storage Object Admin on the bucket.
- Choice: `bsi-ingest` has Storage Object Creator and Storage Object Viewer on the raw bucket only, and no project roles. A changed source file lands under a new fetch-date path.
- Expected consequence: No bug can rewrite or delete a raw payload. Every version of a source file is kept for replay.
- How I would know I was wrong: Legitimate re-ingestion keeps failing on name collisions.

**2. Bucket and key (D-047, D-048)**
- Choice: `brazil-startup-intel-513701-raw` in `us-central1`, Standard, public access prevention on, uniform access, versioning off. JSON key stored outside the repo and outside synced folders.
- How I would know I was wrong: A key file appears in `git status`, or storage passes the free tier early.

**3. What is public (D-044, D-045)**
- Context: The repository is public.
- Alternatives: Keeping personal files in the folder behind `.gitignore`. Publishing the full decision log.
- Choice: Personal planning files live outside the repo. The public `decisions.md` is technical only. The first commit holds five files: `.gitignore`, `README.md`, `decisions.md`, `plan.md`, `spec.md`.
- Expected consequence: Nothing personal can be pushed by mistake.
- How I would know I was wrong: The public and private logs drift apart, or a technical decision is missing from the public one.

**Repository:** https://github.com/thyagomanhaes/brazil-startup-intel (public, first commit on 2026-11-03).

---

## Stage 5: Task T1, local stack (2026-11-03, moved up from 2026-11-09)

### Facts checked on 2026-11-03

- The current Airflow release is 3.3.2. Its official `docker-compose.yaml` uses CeleryExecutor with Redis and a worker, plus scheduler, DAG processor, API server, triggerer, init and a Postgres metadata database. The docs ask for at least 4 GB of RAM for Docker, 8 GB recommended. Default UI login is `airflow` / `airflow` on port 8080. Source: https://airflow.apache.org/docs/apache-airflow/stable/howto/docker-compose/index.html
- The agent's network could not download the file. Thyago downloads it on his machine, so the base file is the untouched official one, and the changes on top of it are visible in the first diff.

### D-049: LocalExecutor instead of CeleryExecutor

- **Status:** Decided by Thyago, 2026-11-03. He chose "LocalExecutor", the agent's recommendation.
- **Question asked by the agent:** The official 3.3.2 compose uses CeleryExecutor with Redis and worker containers. Which executor?
- **Choice:** LocalExecutor. Redis, the Celery worker and Flower are removed from the official file.
- **Rationale presented by the agent, accepted by Thyago:** Fewer containers and less RAM on a laptop. Hourly DAGs do not need distributed workers.
- **Thyago's own rationale:** Not stated beyond the choice.
- **Option not chosen:** CeleryExecutor, the official file as published. Closer to a multi-worker setup, heavier on RAM.
- **Trade-off:**
  - Latency and throughput: tasks run as processes next to the scheduler, so parallelism is bounded by the laptop.
  - Maintenance: the compose file diverges from the official one, so each Airflow upgrade means re-applying the same edits.
  - Operational complexity: three fewer containers to start, watch and debug.
- **How I would know I was wrong:** The backfill in T12 queues for a long time because tasks cannot run in parallel, or a task needs isolation that a separate worker would give.

### D-050: Tests run in a dedicated container

- **Status:** Decided by Thyago, 2026-11-03. He chose "Test container", the agent's recommendation.
- **Choice:** A `tests` service built from `docker/tests/Dockerfile` (python:3.12-slim, pytest, psycopg). It runs `pytest -q tests` against the compose network.
- **Rationale presented by the agent, accepted by Thyago:** Same result on any machine, and no dependency on the Windows Python install.
- **Option not chosen:** A virtualenv on Windows, hitting Postgres on localhost. Faster loop, tied to the local Python.
- **Trade-off:** Each test run starts a container, a few seconds slower than a local run. CI can reuse the same image later.

### D-051: The data database is Postgres 16

- **Status:** Decided by Thyago, 2026-11-03. He chose "Postgres 16".
- **Choice:** `postgres:16` for the data database, separate from the Airflow metadata database.
- **Rationale presented by the agent, accepted by Thyago:** The official Airflow compose uses the same major version for its metadata database, so one image covers both.
- **Option not chosen:** Postgres 17.

### Agent defaults to review (Stage 5)

#### AD-036: Data Postgres connection settings (agent default, confirmed by Thyago 2026-11-04)

- **Choice:** Service `data-postgres`. Database `bsi`, user `bsi`, password from `DATA_PG_PASSWORD` in `.env` (gitignored, with `.env.example` committed). Host port 5433, so it does not clash with the Airflow metadata Postgres or any Postgres already running on the laptop. Data in a named volume `data-pg`.
- **Status:** Confirmed by Thyago, 2026-11-04 ("I confirm"). No rationale of his own stated beyond confirming.

#### AD-037: The test reads its target from DATA_PG_DSN (agent default, confirmed by Thyago 2026-11-04)

- **Choice:** The smoke test takes its connection string from the `DATA_PG_DSN` environment variable, set by the `tests` service.
- **Why the agent picked it:** The same test runs against any database without code changes.
- **Status:** Confirmed by Thyago, 2026-11-04 ("I confirm"). No rationale of his own stated beyond confirming.

#### AD-038: Example DAGs off (agent default, confirmed by Thyago 2026-11-04)

- **Choice:** `AIRFLOW__CORE__LOAD_EXAMPLES` set to `'false'`. The official file ships it as `'true'`.
- **Why the agent picked it:** The UI then shows only the project's own DAGs.
- **Status:** Confirmed by Thyago, 2026-11-04 ("I confirm"). No rationale of his own stated beyond confirming.

### Changes applied to the official compose file (2026-11-03)

Base: the untouched official Airflow 3.3.2 `docker-compose.yaml`, downloaded by Thyago. Edits:

- Executor set to LocalExecutor. Celery broker and result backend variables removed (D-049).
- `redis` service, `airflow-worker` service and `flower` service removed. Redis removed from the shared `depends_on` (D-049).
- Example DAGs off (AD-038).
- `tests` service added, behind the `test` profile (D-050). At this point it has no `data-postgres` to reach, on purpose: the first run must fail (TDD red).

#### AD-039: Secrets stay out of test output and the data database stays on localhost (agent default, confirmed by Thyago 2026-11-04)

- **Context:** The first failing run printed the full connection parameters, password included, because pytest's default traceback shows function arguments.
- **Choice:** pytest runs with `--tb=short`, which drops function arguments from failure output. The data Postgres port is bound to `127.0.0.1:5433`, not to every network interface. Compose refuses to start the database if `DATA_PG_PASSWORD` is missing from `.env`.
- **Why the agent picked it:** A password in test output ends up in terminals, chat logs and CI logs. A database port open on every interface is reachable from any device on the same Wi-Fi.
- **Status:** Confirmed by Thyago, 2026-11-04 ("I confirm"). No rationale of his own stated beyond confirming.

#### AD-040: Fernet key set, Airflow UI on localhost, generated config ignored (agent default, confirmed by Thyago 2026-11-04)

- **Context:** After the first `docker compose up`, Compose warned that `FERNET_KEY` was blank, and the API server listened on `0.0.0.0:8080` with the default login `airflow` / `airflow`.
- **Choice:**
  - `FERNET_KEY` generated once and stored in `.env`, before any Airflow connection is created. With a blank key, connection passwords sit unencrypted in the metadata database, and setting a key later means re-encrypting what is already there.
  - The UI port bound to `127.0.0.1:8080`, the same rule as the data database (AD-039).
  - `config/airflow.cfg`, generated by `airflow-init`, added to `.gitignore`.
- **Status:** Confirmed by Thyago, 2026-11-04 ("I confirm"). No rationale of his own stated beyond confirming.

### Task T1 result (2026-11-04)

- `docker compose ps`: `airflow-apiserver`, `airflow-scheduler`, `airflow-dag-processor`, `airflow-triggerer`, `postgres` (Airflow metadata) and `data-postgres` all up and healthy. `data-postgres` on `127.0.0.1:5433`.
- TDD: the smoke test failed first with `failed to resolve host 'data-postgres'` (no database yet), then ran against the new `data-postgres` service.

### Stage 5 consolidated summary

Closed 2026-11-04, five days before the planned date for T1. Format: context → alternatives → choice → expected consequence → how I would know I was wrong.

**1. Local Airflow (D-049, AD-038, AD-040)**
- Context: The official Airflow 3.3.2 compose runs CeleryExecutor with Redis and a worker, and asks for 4 GB to 8 GB of RAM.
- Alternatives: The official file as published.
- Choice: LocalExecutor, with Redis, worker and Flower removed. Example DAGs off. UI on localhost only, Fernet key set.
- Expected consequence: Six containers instead of nine, all healthy on a laptop.
- How I would know I was wrong: The T12 backfill queues for a long time, or an Airflow upgrade breaks the edited file.

**2. A separate data database (D-051, AD-036, AD-039)**
- Context: Project data and Airflow's own metadata have different lifecycles.
- Alternatives: Postgres 17. Reusing the Airflow metadata database.
- Choice: `data-postgres`, Postgres 16, database `bsi`, on `127.0.0.1:5433`, in its own volume, with a required password.
- Expected consequence: Dropping or rebuilding project data never touches Airflow, and the reverse.
- How I would know I was wrong: Airflow tasks cannot reach `data-postgres` on the compose network in T7.

**3. Tests that run anywhere (D-050, AD-037)**
- Context: Every task in the plan starts with a failing test.
- Alternatives: A virtualenv on Windows.
- Choice: A `tests` container that waits for a healthy database and reads its target from `DATA_PG_DSN`. Short tracebacks, so secrets stay out of failure output.
- Expected consequence: `docker compose --profile test run --rm tests` gives the same answer on any machine, and later in CI.
- How I would know I was wrong: The test loop is slow enough that tasks skip the red step.

---

## Stage 6: Task T2, CNPJ source check (2026-11-04, moved up from 2026-11-10)

### Findings from secondary sources, pending Thyago's check in `docs/sources/cnpj.md`

- **A-004 likely fails.** A third-party loader reported monthly folders starting at 2023-05. If confirmed, CNPJ history starts at the oldest folder on the share, and the 2022-07-01 cutoff (D-017) applies to CVM data only. This is the fallback already written in `plan.md`.
- **A-003 partly confirmed.** The partner CPF is published masked, with the first three digits and the two check digits hidden (art. 129 § 2, Lei 13.473/2017). An age bracket column exists. Exact column names and codes still to confirm in the layout PDF.
- **Volume.** About 6.8 GB zipped per monthly release (2026-01), 37 files. Three months (D-029) is about 20 GB in GCS, above the 5 GB Cloud Storage free tier. At US$ 0.020 per GB-month in us-central1, the extra 15 GB costs about US$ 0.30 per month, far below the R$ 1,000 budget (D-036). The price per GB is the agent's recollection and is to be checked against the pricing page.
- **Download time.** Each month is about 6.8 GB through the home connection (D-027). The check "one month downloads in one evening" in `plan.md` now has a size to measure against.

### AD-041: Every CNPJ column is text (agent default, confirmed by Thyago 2026-11-04)

- **Context:** Receita Federal started issuing alphanumeric CNPJs for new registrations on 2026-07-31. Existing numeric CNPJs do not change.
- **Choice:** `cnpj_basico`, `cnpj_ordem` and `cnpj_dv` are `text` in every layer, in the watchlist and in API paths. Never integer.
- **Why the agent picked it:** Young companies, the ones raising money through crowdfunding, are the most likely to have new alphanumeric CNPJs. An integer column would reject them or silently drop leading zeros.
- **Consequence:** T7 DDL uses `text` with a check on length. Validation for the new format comes when the official validation rules are read.
- **Source:** https://agenciagov.ebc.com.br/noticias/202607/implantacao-do-cnpj-alfanumerico-ocorrera-a-partir-de-31-de-julho
- **Status:** Confirmed by Thyago, 2026-11-04 ("I confirm"). No rationale of his own stated beyond confirming.

### Checks closed on 2026-11-04

- **A-004: failed, as expected.** Thyago checked the share: oldest folder 2023-05, newest 2026-10. CNPJ history starts at 2023-05. The 2022-07-01 cutoff in D-017 now applies to CVM data only. Per-issuer replays (D-026) can go back to 2023-05 at most.
- **A-003: closed for the column list.** Thyago checked the partner layout: 11 columns, including the partner document (masked CPF), the legal representative's CPF and name, and the age bracket. The exact CPF mask and the age bracket codes are read from real rows in T8.
- **Release size:** 37 files, 7.3 GB zipped for 2026-10 (Thyago).
- **File format (agent, on `Cnaes.zip` from 2026-10):** semicolon separator, every field double-quoted, Latin-1 encoding, no header row, LF line endings, member file named without a `.csv` extension. 12 of 1,359 rows have a semicolon inside a quoted field, so the loader needs a real CSV parser (COPY with `FORMAT csv`), never a split on `;`.

### D-052: The legal representative's CPF and name are dropped in standardized

- **Status:** Decided by Thyago, 2026-11-04. He chose "Drop in standardized", the agent's recommendation.
- **Question asked by the agent:** The partner layout also has the legal representative's CPF and name. D-017 allows only the partner's name as personal data. Where do the representative columns stop?
- **Choice:** `legal_rep_document` and `legal_rep_name` follow the same rule as the partner's masked CPF and age bracket (D-018). Kept in raw for replay, dropped in standardized, never in curated, BigQuery, the API or the dashboard. The T10 leak test covers all four columns.
- **Thyago's own rationale:** Not stated beyond the choice.
- **Option not chosen:** Keep the representative's name in curated like the partner's name, and drop only the CPF.
- **Trade-off:** The API cannot say who legally represents a partner company. No business question in D-016 needs it.

### Agent defaults to review (Stage 6)

#### AD-042: Empty partner documents in the partner key (agent default, confirmed by Thyago 2026-11-04)

- **Context:** The layout says foreign partners have no document. D-031 puts the masked document in the partner key, and a primary key cannot hold NULL.
- **Choice:** In the raw partner table, an empty document is stored as an empty string, never NULL, so the composite key in D-031 still works.
- **Status:** Confirmed by Thyago, 2026-11-04 ("I confirm"). No rationale of his own stated beyond confirming.

#### AD-043: English column names from the first raw layer (agent default, confirmed by Thyago 2026-11-04)

- **Choice:** Raw tables use English snake_case names mapped one to one from the layout (`partner_name`, `partner_since`, `age_bracket`, and so on), as listed in `docs/sources/cnpj.md`. The original layout name stays in the column comment.
- **Why the agent picked it:** The repo, the API and the dashboard are in English. One naming convention from raw to curated.
- **Status:** Confirmed by Thyago, 2026-11-04 ("I confirm"). No rationale of his own stated beyond confirming.

### Stage 6 consolidated summary

Closed 2026-11-04, six days before the planned date for T2. AD-036 to AD-043 confirmed by Thyago the same day. Format: context → alternatives → choice → expected consequence → how I would know I was wrong.

**1. How far CNPJ history goes (A-004)**
- Context: D-017 set history from 2022-07-01. The Receita share starts at 2023-05.
- Alternatives: Third-party archives of older releases. Not explored, since they would add a source that is not official.
- Choice: CNPJ history starts at 2023-05. CVM data keeps the 2022-07-01 cutoff.
- Expected consequence: Offers and platform totals cover the full Resolution 88 period. Company and partner data for those offers comes from 2023-05 onward.
- How I would know I was wrong: A business question needs company data from before 2023-05 and gets an empty answer.

**2. Reading the files correctly (AD-041, AD-043)**
- Context: Latin-1, quoted fields, no header, semicolons inside text, member files without a `.csv` extension, and alphanumeric CNPJs since 2026-07-31.
- Alternatives: Splitting lines on `;`. Integer CNPJ columns.
- Choice: COPY with `FORMAT csv`, Latin-1, quote `"`. Every CNPJ column is text. English column names from raw onward.
- Expected consequence: The 12 Cnaes rows with a semicolon inside a description load as 2 fields, and new alphanumeric CNPJs load without errors.
- How I would know I was wrong: Row counts after load differ from line counts in the source file, or a CNPJ loses a leading zero.

**3. Personal data (D-018, D-052, AD-042)**
- Context: The partner file holds the masked partner CPF, the age bracket, and the legal representative's CPF and name. Foreign partners have no document.
- Alternatives: Keeping the representative's name in curated.
- Choice: All four columns stay in raw only. An empty document is an empty string, so the partner key works for foreign partners.
- Expected consequence: Nothing personal beyond the partner name leaves raw.
- How I would know I was wrong: The T10 leak test fails, or foreign partners collide on the key in T7.

---

## Stage 7: Task T3, object paths and streaming checksum (2026-11-04, moved up from 2026-11-11)

### D-053: Download to a temp file while hashing, then upload

- **Status:** Decided by Thyago, 2026-11-04. He chose "Temp file, then upload", the agent's recommendation.
- **Question asked by the agent:** How do bytes go from Receita to GCS? This decides what `sha256_stream()` hashes.
- **Choice:** Each source file is downloaded to a local temp file and hashed in the same pass. The checksum decides skip or upload (D-030). The upload then reads from the temp file.
- **Rationale presented by the agent, accepted by Thyago:** A failed upload retries from disk, without downloading the file again from Receita.
- **Thyago's own rationale:** Not stated beyond the choice.
- **Option not chosen:** Stream straight from Receita to GCS, hashing in one pass. No disk use. A broken connection means downloading that file again.
- **Trade-off:**
  - Disk: one part file at a time on the laptop, under 1 GB each (a 7.3 GB release split across 37 files).
  - Latency: download and upload run one after the other, not overlapped.
  - Reliability: the upload can be retried as often as needed, and the checksum is known before any byte reaches GCS.
- **How I would know I was wrong:** The laptop runs out of disk during a download, or temp files pile up after failed runs.

### D-054: The fetch part of the object path is a UTC timestamp

- **Status:** Decided by Thyago, 2026-11-04. He chose "UTC timestamp", the agent's recommendation.
- **Question asked by the agent:** What goes in the fetch part of the object path? Overwrite is blocked by IAM (D-043), so two different fetches must never get the same path.
- **Choice:** `fetched=<YYYY-MM-DDTHHMMSSZ>`, in UTC, to the second. Example: `raw/cnpj/2026-10/fetched=2026-11-09T140300Z/Empresas0.zip`. Times in other timezones are converted to UTC. A datetime without a timezone is rejected.
- **Thyago's own rationale:** Not stated beyond the choice.
- **Option not chosen:** Date only, `fetched=2026-11-09`. Easier to read. A changed file fetched twice in one day would fail on the second upload.
- **Trade-off:** Longer paths. Listing "everything fetched on a day" needs a prefix match on the date part, which the format still allows.

### Agent defaults to review (Stage 7)

#### AD-044: Path validation rules (agent default)

- **Choice:** `object_path()` raises `ValueError` for an unknown source (allowed: `cnpj`, `cvm_registry`), a period that is not `YYYY-MM` or `YYYY-MM-DD` with a real month and day, and a filename that is empty, `..`, or contains `/` or `\`.
- **Why the agent picked it:** Paths are the only key into write-once raw. A bad path written once stays forever (D-043).
- **Thyago must confirm.**

#### AD-045: Package in `src/bsi`, found by pytest through `pyproject.toml` (agent default)

- **Choice:** Code lives in `src/bsi/`. `pyproject.toml` sets pytest's `pythonpath` to `src`, so tests import `bsi` without installing it.
- **Thyago must confirm.**

#### AD-046: 8 MiB read chunks (agent default)

- **Choice:** `sha256_stream()` reads 8 MiB at a time by default.
- **Why the agent picked it:** Memory stays flat for any file size. 8 MiB is a multiple of 256 KiB, the chunk unit GCS resumable uploads require, so the same size can be reused in T4.
- **Thyago must confirm.**
