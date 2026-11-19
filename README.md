# Atlas Copco Market & Technology PoC

Scout pipeline for industrial compressor technology (USA sources). Input, Engine, Output. Results are written to a Databricks Volume; no data is stored locally.

- `parent.md` is the full team brief; `wd.md` is the work split; `Friday_PoC_Spec.md` is the original spec.

## Setup

```
python -m venv .venv
.venv\Scripts\activate            # macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
python -m spacy download en_core_web_sm
copy .env.example .env            # macOS/Linux: cp .env.example .env
```

Fill `.env` with the workspace host, your own Databricks token, and a development prefix
(`ATLAS_PATH_PREFIX=dev/<yourname>`). Leave the prefix empty only for the final demo run.

## Run

```
python -m atlas.storage_check                      # must print PASS first
python -m atlas.run                                # full pipeline, all sources in config/sources.yaml
python -m atlas.run --only <source_id>             # one source
python -m atlas.run --max-items 5                  # limit items per source
python -m atlas.run --use-default-settings         # ignore the saved settings (config/scout_settings.yaml)
python -m atlas.run --no-discovery                 # skip source discovery this run
python -m atlas.run --no-fallback                  # do not switch to other sources when one is refused
pytest -q                                          # unit tests (offline)
```

Phase 2 (see `parent2.md`): saved settings (`settings/scout_settings.json`) control scope, filter rules and the
scout engine; candidates and decisions live in `scout/`; a run groups items into stories and, when a source is
refused, switches to coverage of the same companies from other allowed sources (labelled `via_fallback`).
The frontend is started with `.venv\Scripts\python.exe -m streamlit run app/main.py` (use the project's Python,
not Anaconda's). Reports: `atlas.report.onepager.write_onepager(run_id, fmt)` builds the one-page summary (one slide or
page), `atlas.report.build.write_report(run_id, fmt)` the full report.

A run writes `source_register/`, `raw/`, `clean/`, `facts/`, `output/poc_<run_id>.json` and `logs/<run_id>.json`
to the Volume `/Volumes/atlas_poc/default/data/<prefix>`, prints a per-source summary, and ends with a
local-data check. Exit code 0 means the output validated and nothing went wrong; blocked sources are reported
as findings and do not cause a non-zero exit.

## Phase 2 demo run

Final run `20261115T192521Z` (empty prefix, so the real demo folders): 10 sources read (5 registered, 5 found and
vetted by the scout engine), 63 items passed the filter, 6 sources refused and shown, Ingersoll Rand switching
tried (no coverage found in the pages read), 0 errors. Reports: `reports/report_20261115T192521Z.pptx` and `.pdf`.

## Phase 3 (company view)

- `python -m atlas.companies --fetch-profiles --reports both` builds one profile and one report per company
  (contacts, logo, images, Confirmed / Not confirmed items). A normal run already writes `companies/<run>/index.json`.
- The website has a new Companies page.
- Docs: `docs/architecture.md` (diagrams and workflow), `docs/company_profiles.md` (rules and commands),
  `docs/scraping_tools_evaluation.md`, `docs/research_blocked_sites_and_agents.md` (proposals, not built).
- Optional discovery through the official Firecrawl search API: `FIRECRAWL_API_KEY` in `.env` and
  `search_api_enabled: true` in the settings.
