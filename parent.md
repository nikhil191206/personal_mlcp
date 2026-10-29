# parent.md — Master brief: Atlas Copco Market & Technology PoC

**Group 8, VIT Pune. Demo to Atlas Copco: Fri 30 Oct 2026. Written Thu 29 Oct 2026.**
**Repo:** https://github.com/nikhil191206/personal_mlcp (branch `main`)

This is the single source of truth for the whole team. Everyone reads it fully. Each person then reads their own file (`nikhil.md`, `ragini.md`, `sachi.md`, `parth.md`). `wd.md` is the one-page summary of who does what. `Friday_PoC_Spec.md` is the original brief this file builds on; where they differ, **this file wins**.

> **Everyone uses a different AI assistant.** That is why this file is long and exact. Interfaces, file names, field names and output formats are fixed here so that four separately generated pieces of code fit together on the first try. Section 14 tells you how to brief your AI and what format you require back.

---

## Table of contents

1. What we are building and why
2. Non-negotiable rules
3. What Atlas Copco will see on Friday
4. Architecture and data flow
5. Repo layout and file ownership
6. Data contracts (`atlas/models.py`)
7. Databricks storage layout
8. Module interfaces (exact function signatures)
9. Config file formats
10. The relevance filter (exact rules)
11. Sources: candidates and vetting procedure
12. Tech stack and environment setup (everyone)
13. Git workflow
14. How to work with your AI (read this before prompting)
15. Timeline and hand-offs
16. Testing standards
17. Definition of done (Friday checklist)
18. Open items and decisions made
19. Glossary
20. Reporting format

---

## 1. What we are building and why

**Client.** Atlas Copco is a Swedish industrial group with four business areas: Compressor Technique (largest, about 46% of 2025 revenue), Vacuum Technique, Power Technique and Industrial Technique. It grows by acquiring companies (29 acquisitions announced in 2025), from small local sales-and-service firms to technology companies that fill gaps in its range.

**Project.** A *Market & Technology* study: help Atlas Copco see who is building what in the market so their team can spot relevant technology and companies sooner.

**Where we are.** At the first meeting (Fri 16 Oct) Atlas Copco said our first design was **over-engineered**. They want a **simple proof of concept (PoC)**, then upgrades. They care about **results, not technical cleverness**. They want us to understand their business, ask them for data sources, define what a "scout" is, and use a specific filter.

**Definitions.**
- **Scout:** a program that visits approved websites on a schedule and brings back new items that match a filter.
- **Niche:** the domain. Ours is **industrial compressor technology**.
- **PoC:** proves we can scrape real data and run a basic pipeline, with the output stored **in the cloud, not on a laptop**.

**The PoC in one sentence.** Read about 5 vetted USA sources about industrial compressors, collect items politely and legally, clean them, apply a transparent relevance filter, and write the result as JSON into a Databricks Volume. Shape: **Input → Engine → Output**. Nothing more.

---

## 2. Non-negotiable rules

These apply to every person and every AI. If your AI proposes something that breaks one, reject it.

1. **Serious project: no workarounds, no fallback modes.** If something fails (token, install, a site blocks us, a library will not work), diagnose the real cause and report it to the team. Do not silently swap in a substitute (local storage, regex instead of Presidio, another cloud). A substitute needs an explicit team decision, written in `docs/decisions.md`.
2. **Nothing is stored locally.** No scraped data, JSON, content logs or caches on any laptop disk. Everything goes straight from memory to Databricks. Code, config and docs live on disk and in git; data does not. Test fixtures must be **synthetic** (hand-written, invented text), never copied pages.
3. **Compliance first.** Public, logged-out pages only. Obey `robots.txt` on every run and before every fetch. If a site's terms forbid automated access, exclude it. **Never try to get around a block** (no header spoofing, no proxies, no retries to dodge a rate limit). Blocked sources stay in the register with their status; that is a finding, not a failure.
4. **Facts, not copied text.** Store extracted fields and a source link. Do not store full articles or page text. No text snippets per item.
5. **Never guess.** A missing value stays `null`. Never fill a gap by inventing it. When unsure of `label`, use `claim`.
6. **No secrets in git.** The Databricks token lives in `.env` (gitignored). Never print it, paste it in chat, or commit it. Everyone generates their own token (section 12).
7. **Keep it simple.** No graph databases, embeddings, multi-agent frameworks, vector search, Playwright, PostgreSQL, GPU serving. Rules and plain Python.
8. **Honest progress notes.** Do not claim something works until you have run it. Report what works, what failed, what is next (section 20).
9. **A person checks before anything is shared with Atlas Copco.** Every fact has a source link and a date.

---

## 3. What Atlas Copco will see on Friday

1. A live run of `python -m atlas.run` on a laptop.
2. The result opened in Databricks: `output/poc_<run_id>.json` in the Volume, plus the six folders filled.
3. A list of proposed sources with robots/terms status, including sources we found **blocked** and excluded.
4. A one-page note and a list of questions for them (section 18 and `docs/`).

Out of scope for Friday: PPT/PDF report, review UI, AI summaries, regions outside the USA, scheduling, opportunity scoring, patents/papers, embeddings, version history, Atlas Copco internal data.

---

## 4. Architecture and data flow

```
config/sources.yaml ──► [Compliance Gate] ──► [Collector] ──► in-memory FetchedPage
 (the register)          compliance.py         collect.py            │
                         "can we use it?"      RSS first, HTML 2nd   │  raw/ <- RawItem list (metadata only)
                                                                     ▼
                                                              [Extractor] extract.py
                                                    text in memory -> fields + signals, PII removed,
                                                    text dropped, fingerprint kept  -> Item (filter=None)
                                                                     ▼
                                                              [Cleaner] clean.py
                                                    dedupe, ISO dates, company name matching
                                                                     ▼
                                                              [Filter] filter.py
                                                    4 yes/no checks per item  -> clean/ (all) , facts/ (passed)
                                                                     ▼
                                                              [Output] run.py
                                                    output/poc_<run_id>.json  +  logs/<run_id>.json
                                        everything above is written to Databricks via atlas/storage.py
```

Per source, `run.py` executes (in this order):

1. `gate.check_source(source)` → `GateDecision`. Not allowed → log the reasons, skip the source, go on.
2. `collect_source(source, gate)` → `CollectResult` (pages in memory, refusals).
3. Write `raw/<source_id>/<run_id>.json` = list of `RawItem` built from the pages.
4. For each page: `extract_item(page, source)` → `Item` (text already dropped).
5. `clean_items(items)` → `CleanResult`.
6. `apply_filter(items, sources_by_id)` → items with `filter` filled.
7. Write `clean/<source_id>/<run_id>.json` (all items) and `facts/<source_id>/<run_id>.json` (passed only).

After all sources: build `OutputEnvelope` (passed items only), validate, write `output/poc_<run_id>.json`, write `logs/<run_id>.json`, print the summary.

Team diagram tags: **AI** (model step), **RULES** (transparent rules), **AUTO** (automated, no AI), **HUMAN**. For Friday: Compliance Gate = RULES, Collector & Extractor = AUTO, Entity matching = RULES, Evidence record = AUTO, Filter = RULES. No AI step on Friday. Versioned facts: removed. Opportunity scoring and report drafting: later phases.

---

## 5. Repo layout and file ownership

Each file has **exactly one owner**. Only the owner edits it (exceptions: the two append-only shared files below).

```
README.md                      Nikhil
parent.md, wd.md               (this planning set; do not edit without telling the team)
nikhil.md ragini.md sachi.md parth.md   one per person (do not edit others')
Friday_PoC_Spec.md             original brief, read-only
requirements.txt               Nikhil (others append-only, see section 13)
.env.example  .gitignore       Nikhil
config/
  sources.yaml                 Ragini
  keywords.yaml                Nikhil   (seed exists; others suggest additions, see section 9)
  aliases.yaml                 Sachi    (seed exists)
  technologies.yaml            Sachi    (seed exists)
atlas/
  __init__.py
  settings.py                  Nikhil   (done)
  storage.py                   Nikhil   (done)
  storage_check.py             Nikhil   (done)
  models.py                    Nikhil   (done; the shared contract, section 6)
  compliance.py                Ragini
  collect.py                   Ragini
  extract.py                   Sachi
  clean.py                     Sachi
  filter.py                    Nikhil
  run.py                       Nikhil
tests/
  test_compliance.py           Ragini
  test_collect.py              Ragini
  test_extract.py              Sachi
  test_clean.py                Sachi
  test_filter.py               Nikhil
  test_run.py                  Nikhil
  fixtures/                    synthetic files only, owned by whoever writes the test using them
docs/
  decisions.md                 shared, append-only table
  source_vetting.md            Ragini
  keyword_suggestions.md       Parth
  questions_for_atlas_copco.md Parth
  glossary.md                  Parth
  demo_note.md                 Parth
  check_results.md             Parth
```

Already done and committed: `settings.py`, `storage.py`, `storage_check.py`, `models.py`, the three seed config files, `.env.example`, `README.md`, `docs/decisions.md`. `python -m atlas.storage_check` printed PASS against the real workspace.

---

## 6. Data contracts (`atlas/models.py`)

`atlas/models.py` is **already written**. Import from it; never redefine. Summary of the classes (read the file for exact types):

| Class | Purpose | Produced by → consumed by |
|---|---|---|
| `Source` | One row of the source register | Ragini (`sources.yaml`) → everyone |
| `GateDecision` | Allowed or not, with reasons | `compliance.py` → `run.py` |
| `Refusal` | Something we did not fetch, and why | `compliance.py`, `collect.py` → `run.py` log |
| `FetchedPage` | Page held **in memory only**; `html` is excluded from dumps | `collect.py` → `extract.py`, `run.py` |
| `CollectResult` | pages + refusals + listing_count for one source | `collect.py` → `run.py` |
| `RawItem` | What goes in `raw/` (metadata, no text) | `run.py` |
| `FilterResult` | 4 checks + `passed` + `reasons` + `date_missing` | `filter.py` |
| `Item` | One evidence record | `extract.py` → `clean.py` → `filter.py` → output |
| `CleanResult` | items + duplicates_dropped | `clean.py` → `run.py` |
| `SourceSummary`, `OutputEnvelope`, `Scope` | The output file | `run.py` |
| `RunLog` | The run log | `run.py` |

Helpers in the same file: `new_run_id()`, `utc_now_iso()`, `make_item_id(url)`, `make_fingerprint(text)`.

### `Item` fields (this is the JSON Atlas Copco sees)

| Field | Type | Rule |
|---|---|---|
| `id` | str | first 12 chars of `sha256(source_url)` → use `make_item_id` |
| `source_id`, `source_name`, `source_type` | str | copied from the `Source` |
| `source_url` | str | the item page URL (final URL after redirects, same host) |
| `licence_note` | str | copied from the `Source` |
| `collected_at` | str | UTC ISO `YYYY-MM-DDTHH:MM:SSZ`, from `FetchedPage.fetched_at` |
| `published_at` | str or null | ISO date `YYYY-MM-DD`. null if unknown. Never guessed |
| `title` | str or null | headline as published |
| `company` | str or null | company the item is about. null if unclear |
| `product` | str or null | **always null on Friday** |
| `technology` | str or null | label from `config/technologies.yaml`, else null |
| `key_facts` | list of str | max 3, each max 200 chars, PII removed, rule-extracted. May be empty |
| `label` | `"fact"` or `"claim"` | rules in `sachi.md`; default `claim` |
| `filter` | `FilterResult` | filled by `filter.py` |
| `page_fingerprint` | str | `make_fingerprint(cleaned main text)` |
| `personal_data_removed` | bool | true once Presidio has run on the text and key facts |
| `matched_keywords` | list of str | compressor keywords found in title+text (extract computes it) |
| `mentions_us_location` | bool | a US location from `keywords.yaml` appears in title+text |
| `industrial_hint` | bool | an industrial keyword appears; **flag only, never a gate** |

### Output example (`output/poc_<run_id>.json`)

```json
{
  "run_id": "20261030T043000Z",
  "generated_at": "2026-10-30T04:30:00Z",
  "scope": {"technology": "industrial compressors", "region": "US"},
  "sources": [
    {"source_id": "example_source", "name": "Example Newsroom", "status": "working",
     "items_collected": 12, "items_passed": 5, "note": null}
  ],
  "items": [
    {
      "id": "a3f9c1d2e4b5",
      "source_id": "example_source",
      "source_name": "Example Newsroom",
      "source_type": "competitor",
      "source_url": "https://example.com/news/some-article",
      "licence_note": "Public web page; facts and links only",
      "collected_at": "2026-10-30T04:31:12Z",
      "published_at": "2026-09-18",
      "title": "Headline as published",
      "company": "Example Corp",
      "product": null,
      "technology": "oil-free rotary screw compressor",
      "key_facts": ["short fact", "another fact"],
      "label": "claim",
      "filter": {"compressor_related": true, "north_america": true, "credible_source": true,
                 "recent": true, "passed": true, "reasons": [], "date_missing": false},
      "page_fingerprint": "sha256 hex",
      "personal_data_removed": true,
      "matched_keywords": ["compressor", "oil-free"],
      "mentions_us_location": true,
      "industrial_hint": true
    }
  ]
}
```

Validate every record with these Pydantic models before writing. Never hand-build dicts for output.

---

## 7. Databricks storage layout

Workspace: `https://dbc-57cf1ee1-bdf1.cloud.databricks.com/`. Unity Catalog Volume: `/Volumes/atlas_poc/default/data/`.

```
<prefix>/source_register/sources.json              list[Source], copied from config/sources.yaml each run
<prefix>/raw/<source_id>/<run_id>.json             list[RawItem]
<prefix>/clean/<source_id>/<run_id>.json           list[Item]  (ALL items, with filter results and reasons)
<prefix>/facts/<source_id>/<run_id>.json           list[Item]  (only filter.passed == true)
<prefix>/output/poc_<run_id>.json                  OutputEnvelope
<prefix>/logs/<run_id>.json                        RunLog
```

- **Never write to Databricks except through `atlas/storage.py`** (`write_json`, `read_json`, `list_dir`, `ensure_folders`). It uploads from memory.
- **`ATLAS_PATH_PREFIX`** (in `.env`) is the `<prefix>`. Developers set `dev/<yourname>` so test runs never pollute the demo folders. **Only Nikhil's final demo run uses an empty prefix.** `ensure_folders()` creates the six folders under the prefix.
- `run_id` format `YYYYMMDDTHHMMSSZ` (UTC), from `new_run_id()`. One run id per `python -m atlas.run`.
- JSON files are written with `indent=2`, UTF-8, via `write_json`.

---

## 8. Module interfaces (exact function signatures)

Your AI must implement **exactly these names and signatures** so the pieces plug together. Extra helper functions are fine; changing these is not.

### `atlas/compliance.py` (Ragini)

```python
USER_AGENT_TEMPLATE = "AtlasCopcoStudentPoC/0.1 (+contact: {email})"

def load_register(path: str = "config/sources.yaml") -> list[Source]: ...

class ComplianceGate:
    def __init__(self, sources: list[Source], client: "httpx.Client | None" = None,
                 min_delay: float = 3.0) -> None: ...
    user_agent: str                      # built from get_settings().contact_email; raise if empty
    refusals: list[Refusal]              # everything refused during this run
    decisions: list[GateDecision]        # one per source checked
    def check_source(self, source: Source) -> GateDecision: ...
    def can_fetch(self, source: Source, url: str) -> tuple[bool, str]: ...   # (allowed, reason)
    def wait(self, source: Source) -> None: ...                              # per-host polite delay
```

### `atlas/collect.py` (Ragini)

```python
def collect_source(source: Source, gate: ComplianceGate, max_items: int = 20,
                   client: "httpx.Client | None" = None) -> CollectResult: ...
```

### `atlas/extract.py` (Sachi)

```python
def extract_item(page: FetchedPage, source: Source) -> Item: ...   # Item.filter is None
```

### `atlas/clean.py` (Sachi)

```python
def clean_items(items: list[Item], aliases_path: str = "config/aliases.yaml") -> CleanResult: ...
```

### `atlas/filter.py` (Nikhil)

```python
def apply_filter(items: list[Item], sources_by_id: dict[str, Source],
                 today: "date | None" = None, recent_months: int = 12,
                 keywords_path: str = "config/keywords.yaml") -> list[Item]: ...   # returns items with .filter set
```

### `atlas/run.py` (Nikhil)

```python
def main(argv: list[str] | None = None) -> int: ...   # python -m atlas.run [--only SOURCE_ID] [--max-items N]
```

Exit code 0 only if the run completed and the output validated; non-zero otherwise.

**Error policy (all modules):** do not swallow exceptions silently. Record refusals/failures in the structures above (`Refusal`, `RunLog.errors`) and keep the run going for other sources. Never return fake or partial data to hide a failure.

---

## 9. Config file formats

### `config/sources.yaml` (Ragini) — list of `Source`

```yaml
- source_id: example_source          # snake_case, unique, stable
  name: Example Newsroom
  url: https://example.com/news
  type: competitor                   # competitor | trade_news | government
  access_method: rss                 # rss | api | html
  feed_url: https://example.com/news/rss      # required if rss
  item_url_pattern: null             # regex for article links, required if html
  robots_status: allowed             # allowed | disallowed | unknown
  terms_status: ok                   # ok | forbids_automation | unknown
  vetting_status: working            # working | blocked | needs_permission | unreachable
  status: proposed                   # proposed | approved | blocked | needs_permission
  review_date: 2026-10-29
  region: US
  licence_note: "Public web page; facts and links only"
  crawl_delay: null                  # seconds, if robots.txt gives one
  notes: ""
```

**All sources stay `proposed`** until Atlas Copco signs off. The Compliance Gate lets `proposed` and `approved` sources run (only if `vetting_status == "working"`) and refuses `blocked`, `needs_permission` and `unreachable`. This fixes a gap in the original spec; it is logged in `docs/decisions.md`.

### `config/keywords.yaml` (Nikhil) — three lists

Keys: `compressor`, `industrial`, `us_locations`. Matching is case-insensitive, whole word/phrase. Others who want to add terms write them in `docs/keyword_suggestions.md` (Parth collects; Nikhil merges).

### `config/aliases.yaml` (Sachi) — canonical company name → list of variants

### `config/technologies.yaml` (Sachi) — ordered list of `{label, patterns}`; first match wins

Seeds for the last three already exist in the repo.

---

## 10. The relevance filter (exact rules)

Every item gets four yes/no checks. `passed = all four true`. Stored on the item so a person can see why. Failed items are dropped from `facts/` but stay in `clean/` with their `reasons`.

| Check | Rule | Reason string when false |
|---|---|---|
| `compressor_related` | `item.matched_keywords` is non-empty, **or** any `compressor` keyword appears in `item.title` | `no_compressor_keyword` |
| `north_america` | source `region` in {`US`, `CA`, `MX`, `NA`}, **or** `item.mentions_us_location` | `not_north_america` |
| `credible_source` | `item.source_id` is in the register **and** its `type` is set **and** `vetting_status == "working"` **and** `status` in {`proposed`, `approved`}. Unknown sites fail | `source_not_credible` |
| `recent` | `published_at` parses as a date and is within the last `recent_months` (default 12) of `today` | `too_old` or `date_missing` |

- Missing date → `recent=false`, `date_missing=true`, reason `date_missing`.
- `industrial_hint` is **not** a gate (decided: "industrial" is a flag only).
- `reasons` lists every failed check (not just the first).

---

## 11. Sources: candidates and vetting procedure

Goal: **at least 8 candidates vetted, at least 5 `working`**, then the team picks the best 5 (mix of competitor newsrooms and trade news; government optional).

### Candidate pool (all unverified until Ragini checks them)

| Type | Candidate | Why |
|---|---|---|
| competitor | Ingersoll Rand (irco.com news / press) | large US compressor maker |
| competitor | Kaeser Compressors USA (news/press) | major compressor brand |
| competitor | Sullair (press releases) | industrial compressors |
| competitor | Atlas Copco USA / Group press releases | the client; shows how they describe their own news |
| trade_news | Compressed Air Best Practices (airbestpractices.com) | magazine focused on compressed air |
| trade_news | Plant Engineering / Plant Services / similar | industrial trade news |
| trade_news | PR Newswire / Business Wire releases of the companies above | check terms carefully |
| trade_news | CAGI (Compressed Air and Gas Institute) | industry body news |
| government | US DOE compressed-air and efficiency pages | optional |

### Vetting procedure (per candidate)

1. Fetch `/robots.txt`. Is the target path allowed for our user agent? Note any `Crawl-delay`.
2. Read the terms of use. Do they forbid automated access or scraping? Quote the relevant sentence (short quote, in the vetting note only).
3. Look for an RSS feed or official API. Prefer these over HTML scraping.
4. Is the content public and logged-out? Paywalled pages are excluded.
5. Test **one** fetch (one page, polite).
6. Assign `vetting_status`: `working`, `blocked` (robots or terms say no), `needs_permission`, or `unreachable`.
7. **Never work around a block.** Blocked sources stay in the register with their status.

All five chosen sources stay `proposed`. On Friday say: "These 5 are our proposed list; the approved list needs your sign-off, and your Legal team should review it before go-live."

---

## 12. Tech stack and environment setup (everyone)

| Part | Tool |
|---|---|
| Language | Python 3.11+ (tested on 3.12) |
| Fetching | `httpx` (+ `feedparser` for RSS). No Scrapy, no Playwright |
| robots.txt | `urllib.robotparser` (parse text we fetch ourselves with our own User-Agent) |
| Text extraction | `trafilatura` (in memory only) |
| Personal data removal | `presidio-analyzer` + `presidio-anonymizer` with spaCy `en_core_web_sm` |
| Cleaning / matching | `pandas` (optional), `rapidfuzz`, `python-dateutil`, `pyyaml` |
| Storage | `databricks-sdk` via `atlas/storage.py` |
| Settings / validation | `python-dotenv`, `pydantic`, `pydantic-settings` |
| Tests | `pytest` |

### One-time setup

**Windows (PowerShell):**
```powershell
git clone https://github.com/nikhil191206/personal_mlcp.git
cd personal_mlcp
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m spacy download en_core_web_sm
copy .env.example .env
```
**macOS / Linux:**
```bash
git clone https://github.com/nikhil191206/personal_mlcp.git
cd personal_mlcp
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python -m spacy download en_core_web_sm
cp .env.example .env
```

### Fill `.env` (never commit it, never paste the token anywhere)

```
DATABRICKS_HOST=https://dbc-57cf1ee1-bdf1.cloud.databricks.com
DATABRICKS_TOKEN=<your own token>
DATABRICKS_CATALOG=atlas_poc
DATABRICKS_SCHEMA=default
DATABRICKS_VOLUME=data
CONTACT_EMAIL=industrymlcp@gmail.com
ATLAS_PATH_PREFIX=dev/<yourname>
```

**Your own token:** log in at the workspace (you were added as a user) → profile icon (top right) → **Settings → Developer → Access tokens → Generate new token**, lifetime 7 days. Copy it once into `.env`.

**Verify your setup:** `python -m atlas.storage_check` must print **PASS**. It writes a small test file under `dev/<yourname>/logs/`. If it fails, send the exact error to Nikhil; do not edit `storage.py` yourself.

**Presidio note:** by default Presidio downloads the 400 MB `en_core_web_lg` model on first use. Sachi pins it to `en_core_web_sm` in `extract.py` so nobody downloads the big model.

---

## 13. Git workflow

- Everyone commits to **`main`**. Because every file has one owner, conflicts should not happen.
- Before every push: `git pull --rebase origin main`, then `git push origin main`. Never `--force`.
- Touch **only your own files** (section 5). Exceptions, append-only:
  - `docs/decisions.md`: add rows at the bottom of the table; never edit others' rows.
  - `requirements.txt`: if you need a package, add one line at the bottom and tell Nikhil.
- Commit small and often (at least every time a function works). Message format: `[name] what changed`, e.g. `[ragini] add robots.txt check to ComplianceGate`.
- Never commit: `.env`, tokens, any scraped content, any data file. If `git status` shows a data file, stop and tell the team.
- Commit message trailer for AI-assisted commits is optional; do not add secrets or personal data to messages.

---

## 14. How to work with your AI (read this before prompting)

Each of you uses a different AI. Your AI does **not** know this project. You must give it the context, and you must require a result in a format that fits the scaffold.

### What to give your AI (in this order)

1. Paste the full text of `parent.md`.
2. Paste the full text of your own file (`<yourname>.md`).
3. If your task consumes someone else's module, paste the relevant part of `atlas/models.py` (or the whole file).
4. Then send the **kickoff prompt** that is at the top of your own file.

### Output format you must demand from the AI (the contract)

Tell the AI that every answer must follow this:

1. **Complete files only.** For each file, a heading with the exact repo path (e.g. `### atlas/compliance.py`) followed by one code block containing the **entire** file. No "rest unchanged", no `...`, no pseudo-code, no TODO placeholders.
2. **Exact names.** Function names, signatures, class names and field names exactly as in sections 6 and 8. Import models with `from atlas.models import ...`. Never redefine a model.
3. **No local data.** Code never writes data files to disk. All persistence goes through `atlas/storage.py`. Tests use synthetic fixtures created in code or small hand-written files.
4. **Runnable.** After the code, give the exact commands to run the tests and a quick manual check, and what output should appear.
5. **Tests included** for everything it writes (section 16), runnable with `pytest tests/<file>.py` and **no network access** (mock HTTP with `httpx.MockTransport`).
6. **Python 3.11+, type hints, short docstrings,** no extra frameworks beyond section 12. If the AI wants a new package it must say so explicitly and why (then append it to `requirements.txt` and tell Nikhil).
7. **Assumptions listed.** At the end the AI lists anything it assumed or could not verify. Do not accept silent guesses (rule 5).
8. **Stop and ask** if a requirement is ambiguous or contradicts section 2, instead of choosing.

### After the AI answers

1. Save the files at the exact paths.
2. Run the commands. **Paste real output back to the AI** if something fails; ask it to fix the root cause, not to bypass the problem.
3. Run `pytest` for your files and `python -m atlas.storage_check` if you touched storage-related code.
4. Only then commit and push (section 13).
5. Send the team your report (section 20).

### Quick checks you can do without understanding the code

- Does the file path match section 5? Is the function signature exactly as in section 8?
- Does the code import from `atlas.models` rather than defining its own models?
- Does anything write to a local file path (`open(..., "w")`, `.to_csv`, `.write_text`, `json.dump` to a file)? If yes (other than editing code/config/docs), reject it.
- Does it contain a fallback ("if this fails, use X instead")? If yes, reject it unless the team agreed.

---

## 15. Timeline and hand-offs

Today is Thu 29 Oct; demo is Fri 30 Oct. The clock times below are proposals; if the meeting time is earlier or later, shift them together. **Confirm the demo time in the team chat.**

| When | Milestone |
|---|---|
| Thu, as soon as possible | Everyone: setup done, `storage_check` PASS under own prefix |
| Thu 18:00 | Ragini pushes a first `config/sources.yaml` (even if statuses are still "unknown") so others can build against it |
| Thu 21:00 | First working version of each module pushed with its tests passing |
| Thu 23:30 | Integration: `python -m atlas.run --only <source_id>` works end to end for at least one source |
| Fri 07:30 | Full run over all 5 sources under a dev prefix; fix list agreed |
| Fri 08:30 | Final demo run into the real (empty-prefix) folders, `git status` data check |
| Before the meeting | Hand-check of 10 items done, demo note ready, dry run on the presenting laptop |

### Hand-offs (who needs what from whom)

| From | To | What | Until it exists, build against |
|---|---|---|---|
| Nikhil (done) | all | `models.py`, `storage.py`, configs | n/a, already in repo |
| Ragini | Nikhil | first `sources.yaml`, then final 5 | a one-source sample the AI writes from the example in section 9 |
| Ragini | Sachi | working `collect_source` | synthetic `FetchedPage` objects in tests |
| Sachi | Nikhil | `extract_item`, `clean_items` | synthetic `Item` objects in tests |
| Nikhil | all | `python -m atlas.run` | each module is testable on its own first |
| each person | Parth | final facts for notes (run summary, source table) | templates in `parth.md` |

Nobody should wait idle: every module has a clear interface and can be built and tested with synthetic inputs.

---

## 16. Testing standards

- `pytest` only. Tests live in `tests/`, named as in section 5.
- **No network in unit tests.** Mock with `httpx.MockTransport` or by passing synthetic objects.
- **No real scraped content in fixtures.** Write invented text such as "Acme Compressors announced a new oil-free rotary screw unit in Texas." Keep fixtures tiny.
- Every module has at least: one happy-path test, one "missing data stays null" test, one failure-path test (e.g. robots disallow, bad date, empty page).
- Tests must not write files outside pytest's `tmp_path`, and must not need `.env` or Databricks (mock `atlas.storage`).
- Before pushing: `pytest -q` passes for your files.
- Live checks (real sites, real Databricks) are done by hand with the commands in your file, under your own `ATLAS_PATH_PREFIX`.

---

## 17. Definition of done (Friday checklist)

- [ ] No data files on any laptop (`git status` clean of data; folder listing checked).
- [ ] Databricks Volume has `source_register`, `raw`, `clean`, `facts`, `output`, `logs` filled by the final run.
- [ ] 5 sources, each with robots.txt and terms status recorded in `config/sources.yaml` and `docs/source_vetting.md`.
- [ ] Every output item has a source URL, collection date, licence note, label and filter result.
- [ ] `python -m atlas.run` works from a clean checkout with a `.env` file.
- [ ] 10 items hand-checked; results in `docs/check_results.md`.
- [ ] List of blocked or excluded sources with reasons.
- [ ] Questions for Atlas Copco listed (`docs/questions_for_atlas_copco.md`).
- [ ] `pytest -q` passes for the whole repo.
- [ ] A screenshot of the Volume and the output JSON ready to send.

---

## 18. Open items and decisions made

### Decided

| Topic | Decision |
|---|---|
| Storage | Databricks Free Edition. Tokens and the Files API work (verified, `storage_check` PASS). Volume: `/Volumes/atlas_poc/default/data` |
| Team access | Teammates added to the workspace |
| "industrial" keyword | Flag only (`industrial_hint`), not a gate |
| Personal data removal | Presidio + spaCy `en_core_web_sm` |
| AI model on Friday | None. Rules only |
| Text snippets per item | None |
| Recency window | 12 months |
| Gate vs `proposed` | Gate admits `proposed`/`approved`, refuses the rest |
| Contact email in the User-Agent | `industrymlcp@gmail.com` (`CONTACT_EMAIL`, already in `.env.example`) |
| Two status lists | `vetting_status` (technical result) separate from `status` (approval) |

### Open (need an answer)

| Item | Who answers | Needed by |
|---|---|---|
| Demo time on Friday | team | now |
| Which 5 sources to keep (after vetting) | team, with Ragini's table | Thu night |
| Add Ragini, Sachi, Parth as GitHub collaborators on the repo | Nikhil | now |

Record every new decision as a row in `docs/decisions.md`.

---

## 19. Glossary

- **Scout:** program that visits approved sites on a schedule and returns new matching items.
- **Niche:** the domain, here industrial compressor technology.
- **PoC:** proof of concept.
- **Source register:** the list of sources with their compliance status (`config/sources.yaml`).
- **Compliance Gate:** the code that decides whether a source/URL may be fetched (robots, terms, status).
- **Evidence record:** an item with source URL, date, licence note and fact/claim label.
- **Fact / claim:** `fact` = stated by a neutral or official source or a reporter reporting an event; `claim` = a company saying it about itself.
- **Fingerprint:** sha256 of the cleaned main text; lets a later run skip unchanged pages.
- **Volume (Databricks):** a cloud folder in Unity Catalog.
- **robots.txt:** a site's rules for automated visitors. **Crawl-delay:** how long to wait between requests.
- **RSS:** a feed listing a site's recent items.
- **PII:** personal data (names, emails, phone numbers).
- **Compressor terms:** *rotary screw* (common industrial compressor type), *centrifugal* (large-scale, high-flow), *oil-free* (no oil in the compressed air), *air end* (the compression element), *CFM* (cubic feet per minute, flow), *VSD* (variable speed drive).

---

## 20. Reporting format

After each piece of work, post this in the team chat (and paste it to your AI as the next prompt's context):

```
WHO: <name>            WHEN: <date time>
DONE: <files pushed, with commit hash>
WORKS (I ran it): <command> -> <result>
FAILED / NOT WORKING: <exact error or "none">
ASSUMPTIONS / DECISIONS NEEDED: <list or "none">
NEXT: <what I do next>
NEED FROM OTHERS: <list or "none">
```

Do not write "works" unless you ran it and saw the result.
