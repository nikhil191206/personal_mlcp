# Atlas Copco Market & Technology Project: Friday PoC Spec

**Group 8, VIT Pune. Written Thu 29 Oct 2026. Demo to Atlas Copco: Fri 30 Oct 2026.**

This file is the brief for Claude Code. Read all of it before writing code. Where something is marked **DECISION** or **VERIFY**, do not guess: ask the team, or record the answer in `docs/decisions.md`.

---

## 0. Read this first (rules for Claude Code)

1. **Do the work in the order in section 12.** Do not skip ahead to the pipeline before storage is working (step 1) and sources are vetted (step 2).
2. **Nothing is stored locally.** No scraped data, JSON, logs of content, or caches may be written to the laptop's disk. Everything goes straight to Databricks (section 5). Code, config and docs live on disk and in git; data does not.
3. **Ask, don't assume.** If the spec does not answer something you need, ask the user. Write the question and answer in `docs/decisions.md`.
4. **Compliance first.** Public, logged-out pages only. Obey robots.txt on every run. If a site's terms of use forbid automated access, exclude it. Never try to get around a block.
5. **Facts, not copied text.** Store extracted fields and a source link. Do not store full articles or page text.
6. **No secrets in git.** The Databricks token lives in an environment variable or an ignored `.env` file. Never print it or commit it.
7. **Keep it simple.** Atlas Copco said the earlier design was over-engineered. This PoC is Input, Engine, Output. No graph databases, no embeddings, no multi-agent frameworks, no vector search.
8. **Plain progress notes.** After each step, say what works, what failed, and what is next. Do not claim something works until you have run it.

---

## 1. Background: why this project exists

- Atlas Copco is a Swedish industrial group with four business areas: Compressor Technique, Vacuum Technique, Power Technique and Industrial Technique. Compressor Technique is the largest (about 46% of 2025 revenue, per Atlas Copco's reports).
- Atlas Copco **grows by acquiring companies**. It announced 29 acquisitions in 2025. Many are small local sales-and-service firms, and some are technology companies that fill gaps in its range.
- Our project is a **Market & Technology** study: it should help Atlas Copco see who is building what in the market, so their team can spot relevant technology and companies sooner.
- After our first meeting (Fri 16 Oct) Atlas Copco said our first design was **over-engineered**. They want a **simple proof of concept (PoC)**, then upgrades. They care about **results, not technical cleverness**. They want us to understand their business, ask them for data sources, define what a "scout" is, and use a specific filter.
- **Scout** (our definition): a program that visits approved websites on a schedule and brings back new items that match a filter.
- **Niche** means domain. Our niche for now is **industrial compressor technology**.

## 2. What Atlas Copco asked for by Friday

Atlas Copco wants to see that **we can actually scrape data and make a basic pipeline work**, and show the output **at least as JSON**. They did not specify what exactly the JSON must contain. They are checking our **capability**. They also require that **data is not stored locally**: use something like Azure or Databricks.

**Friday deliverable:** a working pipeline that

1. reads about **5 trusted, approved USA sources** about **industrial compressor technology**,
2. collects items, cleans them, applies the relevance filter,
3. writes the results as **JSON into Databricks**, and
4. can be shown live (run it, then open the JSON in Databricks).

Out of scope for Friday: the PPT/PDF report, the review UI, the AI summary, regions outside the USA, scheduling, and anything in section 11.

## 3. Scope of the PoC

| Item | Value |
|---|---|
| Technology | Industrial compressor technology |
| Region | USA only for Friday (the Phase 1 plan covers all of North America later) |
| Sources | About 5: competitors' newsrooms, trade news, possibly government pages |
| Output | JSON in a Databricks Volume |
| Storage | Databricks Free Edition (cloud). Backup option: Cloudflare R2 |
| Run frequency | Manual run for Friday (weekly schedule later) |

## 4. Architecture (Phase 1 PoC)

This is the team's Phase 1 diagram with **Versioned facts removed**. Data flows left to right.

```
 DATA SOURCES            1 INGEST                2 FACT STORE              3 MOVE ENGINE        FINAL
 (USA, approved)         "Can we use it?"        "What do we know?"        "What matters?"      OUTPUT

 Competitor  ----+      +-----------------+     +-------------------+     +----------------+   +--------+
 newsrooms       |      | Compliance Gate |     | Evidence record   |     | Opportunity    |   | JSON   |
                 +----->| [RULES]         |---->| [AUTO]            |---->| scoring [RULES]|-->| in     |
 Trade news      |      | region, robots, |     | source, date,     |     | (later phase)  |   | Data-  |
                 |      | terms, licence  |     | label fact/claim  |     +----------------+   | bricks |
 Government      |      +-----------------+     +-------------------+     | Report drafting|   +--------+
 pages (opt.)    |      | Collector &     |     | Entity matching   |     | [AI] (later)   |
                 +----->| Extractor       |     | [RULES]           |     +----------------+
                        | [AUTO]          |     | same company once |
                        | pulls facts,    |     +-------------------+
                        | removes personal|
                        | data            |
                        +-----------------+
```

Tag legend from the team diagram: **AI** (model step), **RULES** (transparent rules), **AUTO** (automated, no AI), **HUMAN** (a person decides).

**For Friday we build only these boxes:**

| Box | Friday status | What it does |
|---|---|---|
| Compliance Gate | Build | Reads the source register, checks robots.txt on every run, only runs approved sources |
| Collector & Extractor | Build | Fetches pages, extracts main text, pulls fields, removes personal data, drops full text |
| Entity matching | Build (simple) | Name rules so "Co." vs "Company" is one company |
| Evidence record | Build | Every item stores source URL, collection date, licence note, label fact or claim |
| Relevance filter | Build | Compressor-related, North American, credible source, recent |
| Opportunity scoring | Later | Not needed for Friday |
| Report drafting (AI) | Later | Not needed for Friday |
| Versioned facts | **Removed** | Team decision: no version history in the PoC |

Pipeline steps (matches the team's 7-step workflow, first four plus a JSON write):
**Collect, Clean, Filter, Structure, then write JSON.** (Summarize, Review and Download come later.)

## 5. Data storage: Databricks (set up first)

Atlas Copco's rule: data must not be stored locally. We use **Databricks Free Edition** (no credit card). The scraper runs on a laptop (it needs open internet) but sends every result **straight to Databricks from memory**.

Why not run the scraper inside Databricks: Free Edition limits outbound internet to a small list of trusted domains, so scraping from there would likely fail ([limitations](https://docs.databricks.com/aws/en/getting-started/free-edition-limitations)). Free Edition is also for non-commercial use; fine for a student PoC, but a real deployment needs an Atlas Copco workspace.

### 5.1 Layout

One Unity Catalog **Volume** (a cloud folder) with these subfolders:

```
/Volumes/<catalog>/atlas_poc/data/
    source_register/    sources.json          (approved sources, one row each)
    raw/                <source_id>/<run_id>.json   (items straight after collection, no full text)
    clean/              <source_id>/<run_id>.json   (after cleaning and personal-data removal)
    facts/              <source_id>/<run_id>.json   (items that passed the relevance filter)
    output/             poc_<run_id>.json           (the combined JSON we show Atlas Copco)
    logs/               <run_id>.json               (what ran, what was blocked and why; no page content)
```

`<catalog>` is probably `workspace` on Free Edition. **VERIFY** on screen under Catalog.
`<run_id>` format: `YYYYMMDDTHHMMSSZ`.

### 5.2 Setup steps (done by a person, in the browser)

1. Log in at the Databricks Free Edition workspace.
2. **Catalog** (left menu) → open the catalog (likely `workspace`) → **Create → Schema** → name `atlas_poc`.
3. Open `atlas_poc` → **Create → Volume** → name `data`, type **Managed**.
4. Open the volume → create the six folders from 5.1 (use the folder/upload option, or let the code create them on first write).
5. **Create an access token:** profile icon (top right) → **Settings → Developer → Access tokens → Generate new token**. Lifetime: 7 days. Copy it once.
6. Copy the **workspace host** from the browser address bar (for example `https://dbc-xxxx.cloud.databricks.com`). Only the `https://host` part.
7. On the laptop, create `.env` (listed in `.gitignore`):

```
DATABRICKS_HOST=https://<your-workspace-host>
DATABRICKS_TOKEN=<token>
DATABRICKS_CATALOG=workspace
DATABRICKS_SCHEMA=atlas_poc
DATABRICKS_VOLUME=data
```

### 5.3 Storage test (must pass before anything else)

`python -m atlas.storage_check` must:
1. write `{"hello": "atlas"}` to `logs/storage_check.json` in the Volume **from memory**,
2. read it back and compare,
3. list the folder,
4. confirm no new data file appeared on the local disk,
5. print PASS or FAIL.

Implementation options (use the first that works):
- `databricks-sdk` for Python: `WorkspaceClient().files.upload(file_path, BytesIO(data), overwrite=True)` and `files.download(...)`.
- Files REST API: `PUT {host}/api/2.0/fs/files/Volumes/<catalog>/<schema>/<volume>/<path>?overwrite=true` with header `Authorization: Bearer <token>`.

**VERIFY:** that Free Edition allows personal access tokens and the Files API. If either fails, tell the user. Fallback: Cloudflare R2 (S3-compatible, `boto3`, needs a card from one team member). Do not silently fall back to local storage.

### 5.4 Team access

The workspace belongs to one person's account (`nikhil.shah242@vit.edu` in the screenshot). **VERIFY** whether teammates can be added under Settings → Identity and access → Users. If not, the options are one shared login (share in person, not in chat) or each person running the code with the same token. Atlas Copco's access: send them the output JSON and a screenshot of the Volume for Friday, and ask them for their own workspace for the real build.

## 6. Tech stack for the PoC

| Part | Tool | Notes |
|---|---|---|
| Language | Python 3.11+ | One language for everything |
| Source register | `config/sources.yaml` in git, copied to `source_register/sources.json` in Databricks on each run | Replaces the PostgreSQL table in the old plan |
| Fetching | `httpx` or Scrapy | Start with `httpx` + `feedparser` for RSS; use Scrapy only if needed. Plain Scrapy settings: `ROBOTSTXT_OBEY=True`, `DOWNLOAD_DELAY>=3`, `AUTOTHROTTLE_ENABLED=True` |
| robots.txt check | Python `urllib.robotparser` | Check before every fetch and at the start of every run. Also read the Crawl-delay if present and honour it with our own delay (Scrapy does not do this by itself) |
| Text extraction | `trafilatura` | Main text only, in memory |
| Personal data removal | `presidio-analyzer` + `presidio-anonymizer` (needs a spaCy English model) | VERIFY it installs cleanly. If too heavy for Friday, use a simple regex for emails and phone numbers and record this in `docs/decisions.md` |
| Cleaning | `pandas` and simple Python | Dedupe, dates to ISO, strip clutter |
| Units (later) | `pint` | cfm, m3/min, psi, bar, hp, kW. Only if specs appear in items |
| Name matching | `rapidfuzz` + a small alias table | No embeddings |
| Storage | `databricks-sdk` | Section 5 |
| Settings | `python-dotenv`, `pydantic` | Config and record validation |
| AI model | **DECISION**, see section 10 | Not needed for Friday |
| Tests | `pytest` | A few tests for the filter and compliance gate |

**Removed from the older plan (do not add):** pgvector, multilingual-e5-small embeddings, scrapy-playwright, USPTO, Lens.org, IBM Granite fallback, PostgreSQL, GPU serving. These were either rejected by Atlas Copco (embeddings) or are not needed for Friday.

## 7. Sources: find and vet 5 USA sources

Goal: **5 approved sources** by the end of step 2. Mix of competitor newsrooms and trusted trade news. Government pages are optional.

### 7.1 Candidate pool (all UNVERIFIED; Claude Code must check each)

| Type | Candidate | Why |
|---|---|---|
| Competitor | Ingersoll Rand (irco.com news / press releases) | Large US compressor maker |
| Competitor | Kaeser Compressors USA (news/press section) | Major compressor brand |
| Competitor | Sullair (press releases) | Industrial compressors |
| Competitor | Atlas Copco USA / Group press releases | The client; shows how they describe their own news |
| Trade news | Compressed Air Best Practices (airbestpractices.com) | Industry magazine focused on compressed air |
| Trade news | Plant Engineering, Plant Services, or similar | Industrial trade news |
| Wire service | PR Newswire / Business Wire releases from the companies above | Press releases (check terms) |
| Industry body | CAGI (Compressed Air and Gas Institute) | Industry news |
| Government | US DOE compressed-air and efficiency pages | Rules and efficiency news (optional) |

The candidates come from general knowledge, not checked pages. Some may block scraping, have no RSS, or forbid automated access.

### 7.2 Vetting procedure (do this for every candidate)

For each candidate, record in `config/sources.yaml` and in `docs/source_vetting.md`:

1. **Fetch `/robots.txt`.** Is the target path allowed for our user agent? Note any Crawl-delay.
2. **Read the terms of use.** Do they forbid automated access or scraping? Quote the relevant sentence in the vetting note (a short quote in a note is fine; the pipeline itself stores no copied text).
3. **Look for an RSS feed or official API.** Prefer these over page scraping.
4. **Is the content public and logged-out?** Paywalled pages are excluded.
5. **Test one fetch** (one page, polite).
6. **Assign a status:** `working`, `blocked` (robots or terms say no), `needs_permission`, or `unreachable`.
7. **Never work around a block.** Blocked sources stay in the register with their status. They are a useful finding for the meeting ("we found which competitors do not allow scraping").

Pick the 5 best `working` sources. **All sources stay `proposed` until Atlas Copco approves them**, so on Friday say clearly: "These 5 are our proposed list; the approved list needs your sign-off, and your Legal team should review it before go-live."

### 7.3 `config/sources.yaml` format

```yaml
- source_id: example_source
  name: Example Newsroom
  url: https://example.com/news
  type: competitor            # competitor | trade_news | government
  access_method: rss          # rss | api | html
  feed_url: https://example.com/news/rss   # if any
  robots_status: allowed      # allowed | disallowed | unknown
  terms_status: ok            # ok | forbids_automation | unknown
  status: proposed            # proposed | approved | blocked | needs_permission
  review_date: 2026-10-29
  region: US
  licence_note: "Public web page; facts and links only"
  notes: ""
```

## 8. The relevance filter

Atlas Copco's "endorsement criteria". Every item gets four yes/no checks, stored in the JSON so a person can see why it passed or failed.

| Check | Rule for Friday (simple, transparent, no AI) |
|---|---|
| `compressor_related` | Title or main text contains compressor-related keywords (compressor, compressed air, rotary screw, centrifugal, oil-free, air end, CFM...). Keep the list in `config/keywords.yaml` so the team can edit it |
| `north_america` | Source region is US, or the text mentions US locations. For Friday all sources are US, so this mostly confirms the source |
| `credible_source` | Source is in the approved/proposed register with a type. Unknown sites fail |
| `recent` | Published within the last 12 months (configurable). If the date is missing, flag `date_missing` and treat as not passed |

`passed = all four true`. Items that fail are dropped from `facts/` but stay in `clean/` with their `reasons`, so we can show what the filter removed.

**DECISION (ask the team):** is "industrial" also a required keyword, or are all compressor items fine? Default: all compressor items pass; add an `industrial_hint` flag (not a gate).

## 9. Output JSON

One record per item, in `output/poc_<run_id>.json` as a list inside an envelope.

```json
{
  "run_id": "20261030T043000Z",
  "generated_at": "2026-10-30T04:30:00Z",
  "scope": {"technology": "industrial compressors", "region": "US"},
  "sources": [{"source_id": "...", "name": "...", "status": "working", "items_collected": 12, "items_passed": 5}],
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
      "key_facts": ["short fact in our own words", "another fact"],
      "label": "claim",
      "filter": {"compressor_related": true, "north_america": true, "credible_source": true, "recent": true, "passed": true, "reasons": []},
      "page_fingerprint": "sha256 of the main text",
      "personal_data_removed": true
    }
  ]
}
```

Notes:
- `id` = first 12 characters of `sha256(source_url)`.
- `label` is `fact` (stated by a neutral or official source, for example a regulator or a reporter reporting an event) or `claim` (a company says it about itself, such as marketing statements). When unsure, use `claim`.
- `key_facts` are short statements written in our own words. For Friday they may be produced by simple rules (the sentence-level facts around the matched keywords, stripped and shortened) or left empty with `null` fields. **Never fill a gap by guessing.** A missing value stays `null`.
- The page text is never stored. `page_fingerprint` lets the next run skip unchanged pages.
- Validate every record with a Pydantic model before writing.

## 10. Open decisions (ask the user; defaults given)

| # | Question | Default if no answer |
|---|---|---|
| 1 | Does Databricks Free Edition allow tokens and let teammates be added? | Test it in step 1 and report |
| 2 | AI model for extraction: needed on Friday? Options: none (rules only), Databricks-hosted models if Free Edition offers them, or a hosted API with a team key. gpt-oss-20b self-hosted is not realistic by Friday (no GPU) | Rules only on Friday. Add an optional AI step behind a flag later |
| 3 | Keep a short text snippet per item? Policy says facts and links only | No snippets |
| 4 | Is "industrial" a required keyword? | No, a flag only |
| 5 | Is Cloudflare R2 allowed if Databricks fails? | Ask the user before using it |
| 6 | Date window for "recent" | 12 months |
| 7 | Who owns the Databricks account and token? | Ask the team |

## 11. Not in Friday's PoC

Report template and PPT/PDF, Streamlit review page, AI summaries, opportunity scoring, scheduling, Canada and Mexico, USPTO/EPO/OpenAlex patents and papers, embeddings, startup funding data, version history, Atlas Copco internal data. These come in later phases.

## 12. Work plan: what to do, in order

### Step 1: Storage (Thu morning). Done when `storage_check` prints PASS.
- Repo skeleton, `.gitignore` (includes `.env`), `requirements.txt`, `README.md`.
- Section 5.2 setup done by the person; code in `atlas/storage.py` (functions `write_json(path, obj)`, `read_json(path)`, `list_dir(path)`) and `atlas/storage_check.py`.
- Report: does the token work, can teammates be added.

### Step 2: Vet sources (Thu midday). Done when `docs/source_vetting.md` and `config/sources.yaml` list at least 8 candidates with status and at least 5 `working`.
- Follow section 7.2 for every candidate. Do not scrape anything beyond one test page per source.
- Show the user the table and **ask which 5 to keep**.

### Step 3: Compliance Gate and fetcher (Thu afternoon). Done when one source runs end to end into `raw/`.
- `atlas/compliance.py`: load register, skip non-approved/`blocked` sources, check robots.txt every run, enforce delay and user agent: `AtlasCopcoStudentPoC/0.1 (+contact: <team email>)`. **Ask the user for the contact email.**
- `atlas/collect.py`: for a source, get the item list (RSS first, HTML list page second) and fetch each item page politely.
- Write the run log with every refusal and reason to `logs/`.

### Step 4: Extract, clean, filter (Thu evening to Fri morning). Done when `clean/` and `facts/` are filled for all 5 sources.
- `atlas/extract.py`: Trafilatura in memory, fields (title, date, company, technology, key facts), personal-data removal, then drop the text.
- `atlas/clean.py`: dedupe by URL and fingerprint, dates to ISO, company-name matching with `rapidfuzz` and an alias table.
- `atlas/filter.py`: section 8. Unit tests for each check with real examples.

### Step 5: Output and demo (Fri morning). Done when `output/poc_<run_id>.json` opens in Databricks and a person can read it.
- `atlas/run.py`: one command runs everything: `python -m atlas.run`.
- Validate against Pydantic. Print a summary: items collected, passed, dropped per source, and blocked sources with reasons.
- Hand-check **10 items**: open each source URL and confirm title, date and label are right. Record the result in `docs/check_results.md`.

### Step 6: Demo prep (Fri, before the meeting)
- A one-page note: what we built, the 5 sources and why, what the filter dropped, blocked sources, open questions.
- Dry run: run it live on the laptop, then open the JSON in Databricks.

### Definition of done for Friday
- [ ] No data files on the laptop (check with `git status` and a folder listing).
- [ ] Databricks Volume has `source_register`, `raw`, `clean`, `facts`, `output`, `logs` filled.
- [ ] 5 sources, each with robots.txt and terms status recorded.
- [ ] Every output item has a source URL, collection date, licence note, label and filter result.
- [ ] `python -m atlas.run` works from a clean checkout with the `.env` file.
- [ ] 10 items hand-checked.
- [ ] A list of blocked or excluded sources with reasons.
- [ ] Questions for Atlas Copco listed (section 13).

## 13. Questions to ask Atlas Copco on Friday

1. Please approve or change the 5 proposed sources. Which sources do you trust, and which should we avoid?
2. Can you give us a Databricks or Azure workspace so the data stays in your environment?
3. What should the summary report look like? Do you have a template?
4. Is there a narrower compressor topic you want first?
5. Is the weekly frequency right?
6. Who in your Legal team reviews the source list?
7. Is it fine for the AI step to use a hosted model, or must it be self-hosted?

## 14. Proposed repo layout

```
atlas-poc/
  README.md
  requirements.txt
  .env.example          (names only, no values)
  .gitignore            (.env, __pycache__, any data/ dirs)
  config/
    sources.yaml
    keywords.yaml
    aliases.yaml        (company name aliases)
  atlas/
    __init__.py
    settings.py
    storage.py
    storage_check.py
    compliance.py
    collect.py
    extract.py
    clean.py
    filter.py
    models.py           (Pydantic)
    run.py
  tests/
    test_filter.py
    test_compliance.py
  docs/
    decisions.md
    source_vetting.md
    check_results.md
```

## 15. Team rules

- Every fact has a source link and a date.
- The program never guesses a missing fact; it stays `null`.
- A person checks results before anything is shared with Atlas Copco.
- Commit daily. Log what failed and why.
- Do not paste tokens or passwords in chat or commits.

## 16. First message to give Claude Code

> Read `Friday_PoC_Spec.md` fully. Start with Step 1 only (storage). Set up the repo skeleton, then write and run `atlas/storage_check.py` against my Databricks workspace using the `.env` file. Do not scrape anything yet. Tell me what you need from me, list any VERIFY items you could not confirm, and ask before making any assumption.
