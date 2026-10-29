# nikhil.md — Core, filter, orchestration, Databricks

**Person:** Nikhil. **Read `parent.md` first**, fully. This file is your task spec and the prompt kit for your AI.

## How to use this file with your AI

Give your AI, in this order: (1) all of `parent.md`, (2) all of this file, (3) `atlas/models.py`, `atlas/storage.py`, `atlas/settings.py`, (4) the kickoff prompt below. Demand the output format from `parent.md` section 14 (complete files, exact paths, exact signatures, tests, commands, listed assumptions).

### Kickoff prompt (paste as-is)

> You are helping me build the filter and the orchestrator of a scraping pipeline for an industrial-compressor market scout. I have pasted the master brief (`parent.md`), my task file, and the shared code (`models.py`, `storage.py`, `settings.py`). Implement `atlas/filter.py`, `atlas/run.py`, `tests/test_filter.py`, `tests/test_run.py` exactly as specified in my task file, using the exact function signatures from `parent.md` section 8 and the models in `atlas/models.py` (import them, never redefine). Return each file in full under a heading with its repo path. Never write data files to local disk; all persistence goes through `atlas/storage.py`. Do not add fallbacks: if something fails, record it and surface it. Tests must run offline with `pytest`, mocking `atlas.storage`, the gate, the collector, extract and clean. List every assumption at the end. If a requirement is ambiguous, ask me instead of choosing.

---

## Your files

| File | Status |
|---|---|
| `atlas/models.py`, `atlas/settings.py`, `atlas/storage.py`, `atlas/storage_check.py` | done; you own them and handle change requests |
| `atlas/filter.py` | you write |
| `atlas/run.py` | you write |
| `config/keywords.yaml` | seed exists; you maintain it |
| `tests/test_filter.py`, `tests/test_run.py` | you write |
| `README.md`, `requirements.txt`, `.env.example`, `.gitignore` | you maintain |

## Task N0 — Team setup (do first, before anything else)

1. Add Ragini, Sachi and Parth as collaborators on the GitHub repo (Settings → Collaborators).
2. Check each teammate is in the Databricks workspace (Settings → Identity and access → Users) and can see the `atlas_poc` catalog and the `data` volume (they need read/write on it: Catalog → atlas_poc → default → data → Permissions). Fix permissions if they cannot.
3. `python-dateutil` and `lxml` are already in `requirements.txt` (used by filter, extract and collect).
4. Post the open items from `parent.md` section 18 in the team chat: **contact email**, **demo time**.
5. Remind everyone: own token, own `ATLAS_PATH_PREFIX=dev/<name>`, never share a token in chat.

## Task N1 — `atlas/filter.py`

Signature (exact):

```python
def apply_filter(items: list[Item], sources_by_id: dict[str, Source],
                 today: date | None = None, recent_months: int = 12,
                 keywords_path: str = "config/keywords.yaml") -> list[Item]:
```

Behaviour: return the **same items** (new objects are fine) each with `item.filter` set to a `FilterResult`. `today` defaults to `date.today()`; injectable for tests. Load `keywords.yaml` once per call (`compressor`, `industrial`, `us_locations`). Rules exactly as `parent.md` section 10:

- `compressor_related = bool(item.matched_keywords) or title_has_compressor_keyword` where the title check is a case-insensitive whole-word/phrase match against the `compressor` list.
- `north_america = source.region.upper() in {"US","CA","MX","NA"} or item.mentions_us_location`. If the item's `source_id` is not in `sources_by_id`, treat the source as unknown: `north_america` falls back to `item.mentions_us_location` only.
- `credible_source = source exists and source.type set and source.vetting_status == "working" and source.status in {"proposed","approved"}`.
- `recent`: parse `item.published_at` (`YYYY-MM-DD`). Missing or unparseable → `recent=False`, `date_missing=True`, reason `date_missing`. Otherwise `recent = (today - published) <= recent_months months` (use `dateutil.relativedelta`: `published >= today - relativedelta(months=recent_months)`). A **future** date is invalid: treat as `date_missing` with reason `date_in_future` added to `reasons`.
- `passed = all four`.
- `reasons`: one string per failed check, from this closed set: `no_compressor_keyword`, `not_north_america`, `source_not_credible`, `too_old`, `date_missing`, `date_in_future`. Every failed check appears; order = the check order above.
- `industrial_hint` stays as set by extract. Do not touch it. It never affects `passed`.
- Do not mutate items other than setting `filter`. Do not drop items: dropping is `run.py`'s job.

### `tests/test_filter.py` (at minimum)

1. Happy path: all four true, `passed=True`, `reasons=[]`.
2. No compressor keyword in `matched_keywords` nor title → `no_compressor_keyword`.
3. Title has "compressor" but `matched_keywords` empty → `compressor_related=True`.
4. Non-US source and `mentions_us_location=False` → `not_north_america`; with `mentions_us_location=True` → passes.
5. Source with `vetting_status="blocked"` → `source_not_credible`. Unknown `source_id` → `source_not_credible`.
6. Date 13 months old → `too_old`. Date exactly 12 months ago → passes. Missing date → `recent=False`, `date_missing=True`. Future date → fails.
7. Multiple failures list every reason.
8. `industrial_hint=True` or `False` never changes `passed`.
9. Real-looking examples written by hand (invented text), not scraped.

## Task N2 — `atlas/run.py`

CLI: `python -m atlas.run [--only SOURCE_ID] [--max-items N]`. Default `--max-items 20`. `--only` limits to one source (used for dev and integration).

Implementation steps (exact order, matches `parent.md` section 4):

1. `run_id = new_run_id()`; `started_at = utc_now_iso()`. Create a `RunLog`.
2. `storage.ensure_folders()`.
3. `sources = load_register()` (from `atlas.compliance`). Validate (pydantic does it). Copy to Databricks: `write_json("source_register/sources.json", [s.model_dump(mode="json") for s in sources])`.
4. `gate = ComplianceGate(sources)`. Raises if `CONTACT_EMAIL` is empty: **let that error stop the run with a clear message**; do not default an email.
5. For each source (apply `--only`):
   1. `decision = gate.check_source(source)`; append to `log.gate_decisions`. If `not decision.allowed`: record, add a `SourceSummary(... status=source.vetting_status, note=<reasons joined>)`, continue to the next source.
   2. `result = collect_source(source, gate, max_items=...)`. Append `result.refusals` to the log.
   3. Build `RawItem`s from `result.pages` (title = `page.listing_title`, `published_at_raw = page.listing_published`, `collected_at = page.fetched_at`, `http_status = page.status_code`, `via = page.via`, `source_url = page.final_url`) and write `raw/<source_id>/<run_id>.json`.
   4. For each page: `extract_item(page, source)`. **Catch exceptions per page**: append `f"{source_id} {url}: {type(e).__name__}: {e}"` to `log.errors` and continue. Do not hide it: it must show in the printed summary too.
   5. `clean = clean_items(items)`.
   6. `final = apply_filter(clean.items, {s.source_id: s for s in sources})`.
   7. Write `clean/<source_id>/<run_id>.json` (all `final`) and `facts/<source_id>/<run_id>.json` (those with `item.filter.passed`).
   8. `log.counts[source_id] = {"collected": len(result.pages), "clean": len(final), "passed": n_passed, "duplicates_dropped": clean.duplicates_dropped}`.
   9. Wrap the whole per-source block in `try/except Exception`: on error, record in `log.errors`, mark a `SourceSummary` note, continue. Never abort other sources because one failed.
6. Build `OutputEnvelope(run_id, generated_at=utc_now_iso(), scope=Scope(), sources=[...SourceSummary...], items=[all passed items across sources])`. Re-validate with `OutputEnvelope.model_validate(envelope.model_dump(mode="json"))`. Write `output/poc_<run_id>.json`.
7. `log.finished_at = utc_now_iso()`; write `logs/<run_id>.json`. Include gate decisions, refusals and errors only; **never page content**.
8. Print the summary (plain text table): per source `collected / duplicates dropped / passed / dropped by filter`, then blocked sources with reasons, then errors, then the Databricks paths written, then the `run_id`.
9. Exit code: `0` if the output validated and there were no `log.errors`; `1` otherwise. (Blocked/refused sources are **not** errors; they are findings. Extraction/cleaning exceptions are errors.)

Also print, at the end of every run, a **local-data check**: list files under the project root excluding `.venv`, `.git`, `__pycache__`, `.pytest_cache`, and compare with the list taken at start; print `local data check: PASS` or the new files (reuse the approach in `atlas/storage_check.py`).

### `tests/test_run.py` (at minimum)

Mock `atlas.storage` (record `write_json` calls in a dict), `load_register`, `ComplianceGate`, `collect_source`, `extract_item`, `clean_items`.
1. Happy path with two sources: writes `source_register`, `raw`, `clean`, `facts`, `output`, `logs` paths; output validates; counts correct.
2. A source the gate refuses is skipped, appears in the summary with its reason, and exit code stays 0.
3. `extract_item` raises for one page: the error is in the log, other pages still processed, exit code 1.
4. A source whose collector raises does not stop the other source.
5. Output contains **only passed** items; `clean/` contains all.
6. No test writes outside `tmp_path`.

## Task N3 — Keep shared things healthy

- `config/keywords.yaml`: when Parth posts suggestions in `docs/keyword_suggestions.md`, review and merge sensible ones (keep the three top-level keys). Tell the team when merged.
- `requirements.txt`: merge anything teammates append; keep it installable on a fresh venv.
- `docs/decisions.md`: make sure each decision from `parent.md` section 18 is present; add new ones as they come.
- Answer change requests for `models.py`. If you change a field, tell **everyone** in chat and update `parent.md` section 6 in the same commit.
- Update `README.md` with the final run instructions at the end.

## Task N4 — Integration (Thu night to Fri)

1. As soon as Ragini's `compliance.py`/`collect.py` and Sachi's `extract.py`/`clean.py` are on `main`: `git pull --rebase origin main`, `pip install -r requirements.txt`, then run
   `python -m atlas.run --only <source_id>` under your own prefix `dev/nikhil`.
2. Open the files in Databricks (Catalog → atlas_poc → default → data → dev → nikhil) and check each folder is filled.
3. Fix interface mismatches: if a teammate's function does not match `parent.md` section 8, ask the **owner** to fix it; do not patch their file.
4. Full run over all chosen sources (Fri 07:30). Collect a fix list and send it to the owners.
5. **Final demo run (Fri 08:30):** set `ATLAS_PATH_PREFIX=` (empty) in `.env`, run `python -m atlas.run`. Confirm: six folders filled, `output/poc_<run_id>.json` opens in Databricks, local-data check PASS, `git status` clean of data.
6. Tag the commit that did the demo run: `git tag friday-demo && git push origin friday-demo`.
7. Give Parth the run summary text for the demo note.

## Acceptance criteria (yours)

- [ ] `pytest tests/test_filter.py tests/test_run.py -q` passes offline.
- [ ] `python -m atlas.run --only <source_id>` works end to end under `dev/nikhil`.
- [ ] Full run produces `output/poc_<run_id>.json` that validates as `OutputEnvelope`.
- [ ] Items that failed the filter are in `clean/` with `reasons`, not in `facts/` or `output/`.
- [ ] A refused/blocked source is visible in the summary and the log with its reason.
- [ ] Demo run done with an empty prefix; local-data check PASS.
- [ ] Every teammate can run `storage_check` PASS.

## Do not

- Do not add a fallback to local storage, a second cloud, or silent retries that hide failures.
- Do not change another person's file; ask the owner.
- Do not print or commit the token.
- Do not store page text anywhere.
