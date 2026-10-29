# wd.md — Work distribution (one-page summary)

Read `parent.md` first (the full brief). Then read your own file: `nikhil.md`, `ragini.md`, `sachi.md` or `parth.md`.

**Demo to Atlas Copco: Fri 30 Oct 2026. Today: Thu 29 Oct.** Repo: https://github.com/nikhil191206/personal_mlcp (`main`).

Already done: repo skeleton, Databricks storage layer (`storage_check` PASS), shared data models (`atlas/models.py`), seed config files, environment setup instructions.

---

## Who does what

| Person | Area | Owns (files) | Main deliverable |
|---|---|---|---|
| **Nikhil** | Core, filter, orchestration, Databricks | `atlas/filter.py`, `atlas/run.py`, `config/keywords.yaml`, `tests/test_filter.py`, `tests/test_run.py`, `README.md`, `requirements.txt`, `atlas/models.py`, `atlas/settings.py`, `atlas/storage*.py` | One command `python -m atlas.run` that runs everything and writes the final JSON to Databricks; final demo run |
| **Ragini** | Input: sources, compliance, collection | `config/sources.yaml`, `docs/source_vetting.md`, `atlas/compliance.py`, `atlas/collect.py`, `tests/test_compliance.py`, `tests/test_collect.py` | 8+ sources vetted, best 5 selected; a Compliance Gate and a polite collector that return pages in memory |
| **Sachi** | Engine: extraction and cleaning | `atlas/extract.py`, `atlas/clean.py`, `config/aliases.yaml`, `config/technologies.yaml`, `tests/test_extract.py`, `tests/test_clean.py` | Turn a fetched page into a validated evidence record; PII removed; text dropped; duplicates and company names cleaned |
| **Parth** | Evidence, documentation, demo material | `docs/keyword_suggestions.md`, `docs/questions_for_atlas_copco.md`, `docs/glossary.md`, `docs/demo_note.md`, `docs/check_results.md` | Questions for Atlas Copco, keyword suggestions, glossary, the one-page demo note, the 10-item hand-check, the Volume screenshot |

---

## Pipeline and owners

```
sources.yaml (Ragini) -> compliance.py + collect.py (Ragini) -> extract.py + clean.py (Sachi)
   -> filter.py (Nikhil) -> run.py + Databricks output (Nikhil)
Documentation and checking around the pipeline: Parth
```

## Deadlines (proposed; shift together if the demo time changes)

| When | Nikhil | Ragini | Sachi | Parth |
|---|---|---|---|---|
| Thu, now | setup + `storage_check` PASS, add collaborators | setup + `storage_check` PASS | setup + `storage_check` PASS | setup + `storage_check` PASS |
| Thu 18:00 | `filter.py` + tests started | first `sources.yaml` pushed | `extract.py` started | `questions_for_atlas_copco.md` and `glossary.md` pushed |
| Thu 21:00 | `filter.py` + tests done, `run.py` skeleton | vetting table done, `compliance.py` + tests done | `extract.py` + tests done | `keyword_suggestions.md` pushed |
| Thu 23:30 | `run.py` end to end for one source | `collect.py` + tests done, 5 sources chosen | `clean.py` + tests done | demo-note template ready |
| Fri 07:30 | full run, fix list | fix collector issues | fix extraction issues | start the 10-item hand-check on the dev run |
| Fri 08:30 | final demo run, data check | on call | on call | hand-check done, Volume screenshot, demo note filled in |
| Before meeting | dry run on presenting laptop | present source vetting | present extraction and cleaning | present the checks and questions |

## Shared rules (short version)

- No data on laptops. Everything goes to Databricks via `atlas/storage.py`. Use your own prefix `ATLAS_PATH_PREFIX=dev/<yourname>`.
- Public pages only, obey robots.txt and terms, never work around a block.
- Never guess: unknown values stay `null`.
- Do not paste the Databricks token anywhere. Everyone generates their own.
- Commit to `main`, touch only your own files, `git pull --rebase origin main` before `git push origin main`.
- Report in the format in `parent.md` section 20. Do not say "works" until you ran it.
