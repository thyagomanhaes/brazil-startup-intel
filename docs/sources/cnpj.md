# Source: Receita Federal open CNPJ data

Status: checked in task T2, 2026-11-04. Share listing and partner layout checked by Thyago. File format checked by the agent on `Cnaes.zip` from the 2026-10 release. Two items stay open until the first partner file is loaded in T8, marked **[T8]**.

## What it is

The national company registry (Cadastro Nacional da Pessoa Jurídica), published by Receita Federal as open data. Each monthly release is a **full snapshot** of every company, establishment and partner, active or not. It is not a change log.

In this project it gives company data and partner names for the CNPJs on the watchlist (D-026, D-033).

## Where to get it

| Item | Value |
|---|---|
| Catalog entry | https://dados.gov.br/dados/conjuntos-dados/cadastro-nacional-da-pessoa-juridica---cnpj |
| Download share (Nextcloud) | `https://arquivos.receitafederal.gov.br/index.php/s/gn672Ad4CF8N6TK?dir=/Dados/Cadastros/CNPJ` |
| Folder per release | `AAAA-MM`, for example `2026-10` |
| Layout PDF | https://www.gov.br/receitafederal/dados/cnpj-metadados.pdf |
| Release cadence | Monthly |

## How far back it goes (A-004, closed)

Checked by Thyago on 2026-11-04: the oldest folder on the share is **2023-05** and the newest is **2026-10**.

A-004 fails. The share does not go back to 2022-07-01, the cutoff in D-017. CNPJ history starts at 2023-05. The 2022-07-01 cutoff still applies to CVM data.


## Files in each release

Checked by Thyago in the 2026-10 folder: **37 files, 7.3 GB zipped**.

| File | Parts | Grain |
|---|---|---|
| `Empresas` | 0 to 9 | One row per company (`cnpj_basico`) |
| `Estabelecimentos` | 0 to 9 | One row per establishment (head office and branches) |
| `Socios` | 0 to 9 | One row per partner per company |
| `Simples` | 1 | Simples Nacional and MEI status |
| `Cnaes`, `Motivos`, `Municipios`, `Naturezas`, `Paises`, `Qualificacoes` | 1 each | Lookup tables |

Rows in the 2026-09 release, from a public Parquet mirror: about 73.4M establishments, 70.1M companies, 28.3M partners, 50.4M Simples records.


## File format

Checked by the agent on `Cnaes.zip`, 2026-10 release:

- One CSV per ZIP. The member file has **no `.csv` extension**: in `Cnaes.zip` it is `F.K03200$Z.D61010.CNAECSV`. The loader must take the single member, whatever its name.
- Separator: semicolon (`;`).
- **Every field is wrapped in double quotes**, including numeric codes such as `"0111301"`.
- Encoding: **ISO-8859-1 (Latin-1)**. The bytes are not valid UTF-8, and they decode cleanly as Latin-1 (`não`, `algodão`).
- **No header row.** Column order comes from the layout PDF.
- Line ending: LF.
- **Separators inside quoted text.** 12 of the 1,359 rows in `Cnaes` have a semicolon inside a description, for example `"3520401";"Produção de gás; processamento de gás natural"`. Splitting lines on `;` breaks those rows. A CSV parser with quote handling reads all 1,359 rows with exactly 2 fields. The T8 loader uses COPY with `FORMAT csv, DELIMITER ';', QUOTE '"', ENCODING 'LATIN1'`, never a plain split.


## Partner file (`Socios`) and personal data (A-003, D-018, D-052)

Columns, in order, checked by Thyago against the layout PDF on 2026-11-04:

| # | Layout field | Column name in this project | Personal data rule |
|---|---|---|---|
| 1 | CNPJ BÁSICO | `cnpj_basico` | Kept |
| 2 | IDENTIFICADOR DE SÓCIO (1 company, 2 person, 3 foreigner) | `partner_type` | Kept |
| 3 | NOME DO SÓCIO (PF) OU RAZÃO SOCIAL (PJ) | `partner_name` | Kept (D-017). Not shown on the public dashboard (D-023) |
| 4 | CNPJ/CPF DO SÓCIO | `partner_document` | Masked CPF for people. **Dropped in standardized** (D-018) |
| 5 | QUALIFICAÇÃO DO SÓCIO | `partner_qualification` | Kept |
| 6 | DATA DE ENTRADA SOCIEDADE | `partner_since` | Kept |
| 7 | PAIS | `country_code` | Kept |
| 8 | REPRESENTANTE LEGAL (CPF) | `legal_rep_document` | **Dropped in standardized** (D-052) |
| 9 | NOME DO REPRESENTANTE | `legal_rep_name` | **Dropped in standardized** (D-052) |
| 10 | QUALIFICAÇÃO DO REPRESENTANTE LEGAL | `legal_rep_qualification` | Kept |
| 11 | FAIXA ETÁRIA | `age_bracket` | **Dropped in standardized** (D-018) |

- The partner CPF is published masked: under art. 129 § 2 of Lei 13.473/2017, the first three digits and the two check digits are hidden. The exact mask format **[T8]**, read from the first loaded partner rows.
- The age bracket codes are not in the part of the layout checked so far **[T8]**. They are dropped in standardized anyway, so the codes only matter for documentation.
- Foreign partners have no document (layout note on column 4). `partner_document` can be empty, which matters for the partner key in D-031.

The T10 leak test fails the build if `partner_document`, `legal_rep_document`, `legal_rep_name` or `age_bracket` appear in any standardized or curated model.


## Alphanumeric CNPJ from 2026-07-31

Receita Federal started issuing **alphanumeric CNPJs** for new registrations from 2026-07-31. Existing numeric CNPJs do not change.

Consequence for this project: every CNPJ column (`cnpj_basico`, `cnpj_ordem`, `cnpj_dv`) is stored as **text**, never as an integer. Startups that raise money through crowdfunding are often young companies, so new alphanumeric CNPJs will show up in this data. Leading zeros in numeric CNPJs are kept the same way.

## Checklist for T2

- [x] Oldest and newest folders: 2023-05 and 2026-10.
- [x] Files and size in the newest folder: 37 files, 7.3 GB.
- [x] Partner columns from the layout PDF.
- [x] Separator, encoding, quoting and header, from `Cnaes.zip`.
- [ ] CPF mask format and age bracket codes, from the first partner rows **[T8]**.


## Sources

- Catalog: https://dados.gov.br/dados/conjuntos-dados/cadastro-nacional-da-pessoa-juridica---cnpj
- Folder pattern and history: https://pypi.org/project/cnpj-processor/4.2.2/
- Row counts: https://huggingface.co/datasets/cnpjaberto/cnpj-dados-receita-brasil-2026-09
- CPF masking rule: https://docs.cnpj.ws/modelos-de-dados/socios
- Alphanumeric CNPJ: https://agenciagov.ebc.com.br/noticias/202607/implantacao-do-cnpj-alfanumerico-ocorrera-a-partir-de-31-de-julho
