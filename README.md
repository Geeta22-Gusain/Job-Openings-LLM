# Job Openings LLM

Python CLI to discover **QA and Program Manager jobs in India** targeting **8–12 years of experience**, extract available job details, and rank skills. Searches Naukri, LinkedIn job pages, and company/ATS career pages using Google results through SerpApi. An optional OpenAI step extracts structured details from job descriptions or fetched public pages.

## Run

Requires Python 3.10 or newer. Uses the standard library; no packages to install.

```bash
cd /workspace/Job-Openings-LLM
python3 job_search.py --input example_jobs.json --output results/demo
python3 -m unittest discover -s tests -v
```

The example contains **fictional listings**, solely to test exports without credentials.

For live discovery, set `SERPAPI_API_KEY` securely in your shell or environment settings. Obtain a key from https://serpapi.com/. For LLM extraction, also set `OPENAI_API_KEY` from your OpenAI account. Do not put keys in source files or commit them. The script reads process environment variables; it does not load `.env` files. API use may incur charges. Search needs access to `serpapi.com`; LLM extraction needs `api.openai.com`; page fetching needs access to the listing domains.

```bash
# Search all three source categories; extract from indexed snippets using an LLM.
python3 job_search.py --location India --llm

# Also attempt public HTML detail extraction before LLM extraction.
python3 job_search.py --location India --fetch --llm --pages 2

# Narrow a search; --help shows all options.
python3 job_search.py --roles qa --sources naukri linkedin --location Bengaluru --fetch --llm
python3 job_search.py --roles program-manager --sources company --location India --llm
```

Default discovery makes six API requests: two roles × three source categories × one page. `--pages 2` doubles that. The default search freshness is the last month (`--freshness m`); this describes the search index and does not verify a job's posting date. Each listing passed to `--llm` makes a separate model request (default `gpt-4o-mini`, configurable with `--model`). Source text, capped at 24,000 characters, is sent to OpenAI only when `--llm` is enabled.

## Job API plugins

Choose discovery providers with `--providers`. No additional Python packages are needed.

| Plugin | Coverage | Credentials |
| --- | --- | --- |
| `search` (default) | Indexed Naukri, LinkedIn, and company career pages via SerpApi | `SERPAPI_API_KEY` |
| `adzuna` | Adzuna's India jobs endpoint; supports city searches | `ADZUNA_APP_ID`, `ADZUNA_APP_KEY` |
| `remotive` | Remote QA and Program Manager roles explicitly tagged India or worldwide | None |

```bash
# Public API: no search or OpenAI key needed.
python3 job_search.py --providers remotive --location India

# India job API, using credentials set securely in the process environment.
python3 job_search.py --providers adzuna --location India

# Combine APIs with the existing search/LLM workflow.
python3 job_search.py --providers search adzuna remotive --location India --llm
```

Register Adzuna API credentials at https://developer.adzuna.com/ and check its [search API documentation](https://developer.adzuna.com/docs/search). Never commit keys. Required API hosts are `api.adzuna.com` and `remotive.com`; restricted environments may need these added to their network settings. OpenAI is optional for every provider. These plugins do not grant direct LinkedIn or Naukri API access; those sources still use the search provider and permitted public pages.

`--sources` and `--freshness` apply only to `search`. `--pages` applies to search and Adzuna (up to 50 results per role per Adzuna page); Remotive uses one unpaginated API request. Remotive currently supports `--location India` only and retains India/worldwide eligibility text for manual confirmation. Adzuna always uses the India country endpoint; a different location is interpreted as a city/region within India. Adzuna descriptions may be truncated and salary estimates are preserved as such; verify the full listing.

Respect the [Remotive public API conditions](https://github.com/remotive-com/remote-jobs-api), including attribution and querying no more than four times daily. This CLI does not schedule or cache calls; avoid repeated polling. Remotive attribution and links are retained in exports. Do not republish listings beyond the provider's permitted use.

Exports include `provider` and `provider_job_id`. `providers.json` reports success/failure and raw listing counts before URL deduplication for each requested provider. One failed provider does not discard other providers' results. Exit codes: **0** all selected providers succeeded (possibly zero listings), **2** partial provider failure with remaining results exported, **1** all providers failed or a fatal input/output error. `--input` bypasses all providers and writes an empty provider report. URL deduplication retains the first copy when providers share an identical normalized URL.

To add a plugin, define a class in [job_providers.py](job_providers.py) with `search(args, request_json)` returning listing dictionaries (`url`, `title`, `description`, plus available detail fields and `provider`/`provider_job_id`). Register it in `PROVIDERS`; it then appears in `--providers`. Use `ProviderConfigurationError` for safe credential/configuration instructions; other exceptions are reported without their raw text to avoid exposing key-bearing URLs.

## Matching and details

Skills: Java, Selenium, Scrum methodologies, functional testing, API testing (including REST Assured), Cursor, Claude, resource planning/allocation/management, sprint planning, sprint deliverables/delivery. The score is the percentage of these ten skills explicitly found in extracted text. Skills are preferences, not mandatory filters; management jobs can match without QA tools. Cursor/Claude keyword matches should be manually checked for context.

An explicit experience requirement must overlap 8–12 years to be a potential match; this is **not** an exact 8–12 range requirement. For example, 10+ and 7–10 overlap, while 15+ and 3–5 do not. Missing experience stays unknown. Role detection uses the job title. Unknown titles, ambiguous pages, snippet-only results, and unstructured pages require review. All candidates are retained in the output, including excluded entries, so you can audit filtering.

`results/jobs.json` and `results/jobs.csv` include available title, company, location, salary, employment type, work mode, experience bounds, posting/closing dates, description, responsibilities, qualifications, skills, application/source URLs, source category, retrieval time, match score, missing skills, extraction method, and warnings. Unavailable facts remain null/empty; salary currencies and periods are preserved as source text or structured JSON. CSV cells are escaped against spreadsheet formula execution. `potential_match` is a recommendation for review, not confirmation that the listing is still open. The source URL is the fallback application link.

## Coverage limits

This is search-based discovery, **not exhaustive access to every source**. Search results may be stale, duplicated across sites, or point to indexes and unrelated job boards. Company queries include common career paths and ATS hosts; results labelled `company-or-other` are not verified company-owned sites. Deduplication removes repeated normalized URLs, not all cross-postings. Search country is part of the query, not a verified geographic filter, so check the extracted location.

Public fetching reads HTML and Schema.org `JobPosting` data; it does not execute JavaScript, log in, bypass CAPTCHAs, or circumvent access controls. LinkedIn and Naukri commonly restrict automated access. A failed fetch retains search metadata and warnings, and should be reviewed manually. Only use automated fetching where permitted by the source's terms. `--llm` can extract snippet-only details but those records still require review. LLM output can be wrong; confirm experience, salary, deadline, location, and application link on the original listing. No applications or messages are sent.

## Use your own saved listings

`--input path/to/listings.json` skips paid search. Supply a JSON array with `url`, `title`, `description`, and optionally any of the exported detail fields. Alternatively use `search_title` and `snippet` for search metadata. Add `--fetch` to attempt public detail retrieval or `--llm` for extraction. Use files you trust; fetching follows their URLs. Outputs are local and may contain source text; handle them according to the source's permissions.

## Development

```bash
python3 -m unittest discover -s tests -v
python3 job_search.py --help
```

Tests cover experience/skill matching, manager roles, missing data, public JSON-LD extraction, blocked pages, multi-job pages, mocked LLM/search calls, URL deduplication, and an end-to-end offline CSV/JSON export. Live API behavior requires your own configured credentials.
