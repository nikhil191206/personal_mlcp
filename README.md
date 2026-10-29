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
pytest -q                                          # unit tests (offline)
```

A run writes `source_register/`, `raw/`, `clean/`, `facts/`, `output/poc_<run_id>.json` and `logs/<run_id>.json`
to the Volume `/Volumes/atlas_poc/default/data/<prefix>`, prints a per-source summary, and ends with a
local-data check. Exit code 0 means the output validated and nothing went wrong; blocked sources are reported
as findings and do not cause a non-zero exit.
