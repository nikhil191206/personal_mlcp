# Atlas Copco Market & Technology PoC

Scout pipeline for industrial compressor technology (USA sources). Input, Engine, Output. Results are written to a Databricks Volume; no data is stored locally.

See `Friday_PoC_Spec.md` for the full brief.

## Setup

```
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python -m spacy download en_core_web_sm
copy .env.example .env   # then fill in the Databricks values
```

## Run

```
python -m atlas.storage_check   # must print PASS first
python -m atlas.run             # full pipeline (later steps)
```
