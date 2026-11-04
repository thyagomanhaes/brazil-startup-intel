# brazil-startup-intel

A multi-source data platform about Brazilian startups that raise money through regulated crowdfunding. It turns public government files, PDFs, scraped offer pages and provider webhooks into company and funding records, served to an API and a public dashboard.

Status: design done, implementation starts with wave 1 (files and batch).

| File | What it holds |
|---|---|
| [`spec.md`](spec.md) | What the system does, for whom, and its reliability requirements |
| [`plan.md`](plan.md) | The build plan, task by task, each with its test |
| [`decisions.md`](decisions.md) | Every architectural decision: the question, the options, the choice and the trade-off |

Stack: Python, Airflow, dbt, PostgreSQL, Google Cloud Storage, Pub/Sub, Cloud Tasks, Cloud Run, Vertex AI (Gemini), BigQuery, Looker Studio.

Data sources: Receita Federal open CNPJ data, CVM open data and annual reports of crowdfunding platforms, public offer pages of CVM-registered platforms.
