# sachi.md — Engine: extraction and cleaning

**Person:** Sachi. **Read `parent.md` first**, fully. This file is your task spec and the prompt kit for your AI.

## How to use this file with your AI

Give your AI, in this order: (1) all of `parent.md`, (2) all of this file, (3) `atlas/models.py` and the three config files `config/keywords.yaml`, `config/aliases.yaml`, `config/technologies.yaml`, (4) the kickoff prompt below. Demand the output format from `parent.md` section 14 (complete files, exact paths, exact signatures, tests, commands, listed assumptions).

### Kickoff prompt (paste as-is)

> You are helping me build the extraction and cleaning engine of a scraping pipeline for an industrial-compressor market scout. I have pasted the master brief (`parent.md`), my task file, the shared models (`models.py`) and three config files. Implement `atlas/extract.py`, `atlas/clean.py`, `tests/test_extract.py` and `tests/test_clean.py` exactly as specified in my task file, using the exact function signatures from `parent.md` section 8 and the models in `atlas/models.py` (import them, never redefine). Return each file in full under a heading with its repo path. Page text must only ever exist in memory: never write it, log it, or return it in any field. Never write data files to local disk. Never guess a missing value: it stays `null`. Use Presidio with the small spaCy model `en_core_web_sm` (not the large one). No fallbacks: if Presidio fails to load, raise a clear error; do not silently switch to regex. Tests must run offline with `pytest` using synthetic HTML written in the tests. List every assumption at the end. If a requirement is ambiguous, ask me instead of choosing.

---

## Your files

| File | What |
|---|---|
| `atlas/extract.py` | page -> `Item` |
| `atlas/clean.py` | dedupe, ISO dates, company name matching |
| `config/aliases.yaml`, `config/technologies.yaml` | you maintain (seeds exist; only add entries) |
| `tests/test_extract.py`, `tests/test_clean.py` | tests |

## Task S0 — Setup (first)

Follow `parent.md` section 12 (including `python -m spacy download en_core_web_sm`). `python -m atlas.storage_check` must print PASS with `ATLAS_PATH_PREFIX=dev/sachi`.

Check Presidio loads with the small model:

```python
from presidio_analyzer import AnalyzerEngine
from presidio_analyzer.nlp_engine import NlpEngineProvider
conf = {"nlp_engine_name": "spacy", "models": [{"lang_code": "en", "model_name": "en_core_web_sm"}]}
analyzer = AnalyzerEngine(nlp_engine=NlpEngineProvider(nlp_configuration=conf).create_engine(), supported_languages=["en"])
print(analyzer.analyze(text="Call John Smith on 555-123-4567 or john@example.com", language="en"))
```
It must find a PERSON, a PHONE_NUMBER and an EMAIL_ADDRESS and must **not** start downloading `en_core_web_lg`. If it does, fix the configuration; do not accept the big download. If Presidio will not install or run, report the exact error to the team. Do not replace it with regex yourself (a substitute needs a team decision).

## Task S1 — `atlas/extract.py`

Signature (exact):

```python
def extract_item(page: FetchedPage, source: Source) -> Item:
```

`page.html` is the only place page text exists. Everything is computed in memory; the returned `Item` holds **no page text** (only short rule-extracted `key_facts`).

Pipeline inside `extract_item`:

1. **Main text.** `trafilatura.extract(page.html, include_comments=False, include_tables=False, favor_precision=True)` → `text` (may be `None` or empty). Metadata: `trafilatura.extract_metadata(page.html)` gives `title`, `date`, `sitename`, etc.
2. **Title.** `meta.title` → else `page.listing_title` → else `None`. Strip whitespace.
3. **Date.** `meta.date` → else `page.listing_published` → else `None`. Parse with `dateutil.parser.parse`, output ISO `YYYY-MM-DD`. If unparseable → `None`. Never use the fetch date as the published date. Default to day-first = False (US sources). If the parsed date is in the future, return `None`.
4. **Empty page.** If `text` is empty or shorter than 200 characters, still return an `Item` with whatever fields exist (`key_facts=[]`, `matched_keywords=[]`, `company=None` unless the source is a competitor, fingerprint of the empty string is **not** acceptable: use `make_fingerprint(page.final_url + "|" + (title or ""))` and keep `personal_data_removed=True`).
5. **Personal data removal (Presidio, small model).** Build the analyzer once per process (module-level lazy singleton). Entities to remove: `PERSON`, `EMAIL_ADDRESS`, `PHONE_NUMBER`, `CREDIT_CARD`, `IBAN_CODE`, `IP_ADDRESS`, `US_SSN`, `LOCATION` is **not** removed (needed for the US check), `ORGANIZATION` is **not** removed (company names are the point). Replace with `<PERSON>`, `<EMAIL>`, `<PHONE>` using `presidio-anonymizer` (or equivalent) → `clean_text`. Apply the same scrub to `title` and every key fact. Set `personal_data_removed=True` only when the scrub ran on the text, title and facts. If Presidio is not available, **raise**; do not skip.
6. **Signals** (computed on `clean_text + " " + title`, lower-cased matching, whole word/phrase, using `config/keywords.yaml`):
   - `matched_keywords`: the **compressor** keywords found (unique, in list order).
   - `industrial_hint`: any **industrial** keyword found.
   - `mentions_us_location`: any **us_locations** entry found (match whole words; do not treat the pronoun "us" as a location).
7. **Technology.** Walk `config/technologies.yaml` in order; first entry with a pattern found in title + text gives `technology`. None found → `None`.
8. **Company.**
   - `source.type == "competitor"` → the company is the source's own company: use `source.name` with a trailing "Newsroom", "News", "Press", "Press Releases", "USA" removed (e.g. "Kaeser Compressors USA Newsroom" → "Kaeser Compressors"). 
   - Otherwise: the most frequent organization name that spaCy tags `ORG` in the title (preferred) or the first 1,500 characters of text, ignoring the source's own name and generic words. If nothing clear, `None`. **Do not guess.**
9. **Product:** always `None` on Friday.
10. **Key facts** (rules, no AI): split `clean_text` into sentences (simple regex split is fine). Keep sentences that contain at least one matched compressor keyword **or** one of: a number with a unit/currency (`\d+(\.\d+)?\s?(%|cfm|psi|bar|kw|hp|m3/min|million|billion|usd|\$)`), or an event verb (`announce`, `launch`, `introduc`, `acquir`, `open`, `expand`, `partner`, `certif`, `award`, `invest`). Shorten each to at most 200 characters (cut at a word boundary, add "…"), strip whitespace and boilerplate (cookie, subscribe, "click here", "read more", copyright lines). Take the first 3 distinct sentences. They are **short extracted statements**, not the article. None qualify → `[]`.
11. **Label.** Default `claim`. Return `fact` only when: `source.type == "government"`, **or** (`source.type == "trade_news"` and the title/text contains a reporting pattern: `acquires`, `acquired`, `files`, `filed`, `opens`, `to open`, `completes`, `completed`, `announces plans`, `appoints`, `fined`, `recall`, `regulation`, `rule`, `standard`). Competitor newsrooms are always `claim`. When unsure: `claim`.
12. **Fingerprint.** `make_fingerprint(clean_text)` when text exists (see step 4 for the empty case).
13. **Build the Item:** `id=make_item_id(page.final_url)`, `source_url=page.final_url`, `source_id`, `source_name=source.name`, `source_type=source.type`, `licence_note=source.licence_note`, `collected_at=page.fetched_at`, plus the fields above, `filter=None`.
14. Drop the text: do not keep `text`, `clean_text`, or the HTML in any returned field, log line, exception message or cache. Overwrite the local variables before returning (not required to wipe memory, but do not return or store them).

Failure behaviour: if the HTML cannot be parsed at all, raise `ValueError(f"unparseable page: {page.final_url}")` so `run.py` records it in the log. Do not return a half-made item.

### `tests/test_extract.py` (at minimum, synthetic HTML in the tests)

1. Good article (invented): title, date, compressor + US keywords → `matched_keywords` non-empty, `mentions_us_location=True`, `technology` set, 1-3 key facts, each ≤ 200 chars, `label="claim"` for a competitor source.
2. Date handling: "October 3, 2026" → `2026-10-03`; garbage date → `None`; missing date but `listing_published` given → used; future date → `None`.
3. PII: text with a name, email and phone → none appear in `key_facts` or `title`; `personal_data_removed=True`.
4. **No text stored:** assert no field of `item.model_dump()` contains a long run of the source text (for example assert no value is longer than 200 chars, and a distinctive 60-char phrase from the page body does not appear in the JSON dump).
5. Empty/very short page: returns an Item with `key_facts=[]`, fingerprint set, no exception.
6. Government source → `label="fact"`. Competitor → `claim`. Unknown → `claim`.
7. `product` is always `None`. `company` for a competitor source is the cleaned source name.
8. The word "us" in lower case alone does not set `mentions_us_location`.
9. Presidio small model is used (assert the configured model name, or that `en_core_web_lg` is not loaded).
10. Unparseable input → `ValueError`.

## Task S2 — `atlas/clean.py`

Signature (exact):

```python
def clean_items(items: list[Item], aliases_path: str = "config/aliases.yaml") -> CleanResult:
```

1. **Normalise URLs for deduping** (do not change `source_url`, only the comparison key): lower-case host, drop the fragment, drop tracking params (`utm_*`, `fbclid`, `gclid`, `ref`), strip a trailing slash.
2. **Dedupe:** drop items with the same normalised URL; then drop items with the same `page_fingerprint` (different URL, same content). Keep the one with more non-null fields, tie → earlier `collected_at`. Count drops in `duplicates_dropped`. Items with empty-text fingerprints (step 4 of S1) are only compared by URL.
3. **Dates:** make sure `published_at` is ISO `YYYY-MM-DD` or `None`; reformat if it is another parseable format; unparseable → `None` (never guess).
4. **Company name matching (simple, no embeddings):**
   - Load `config/aliases.yaml` (canonical → variants).
   - Normalise a name: casefold, remove punctuation, collapse spaces, remove legal suffixes (`inc`, `incorporated`, `llc`, `ltd`, `limited`, `co`, `company`, `corp`, `corporation`, `ab`, `gmbh`, `plc`, `sa`, `ag`).
   - Exact match on normalised canonical or alias → set `company` to the canonical name.
   - Otherwise fuzzy match with `rapidfuzz.process.extractOne(name, choices, scorer=fuzz.token_sort_ratio)`; accept at score ≥ 92 → canonical name.
   - No match → keep the original string, only whitespace-stripped. Do **not** invent a canonical form.
   - `company=None` stays `None`.
5. **Do not alter** `key_facts`, `label`, `matched_keywords`, `filter`, `title` (beyond whitespace strip), or any other field.
6. Return `CleanResult(items=..., duplicates_dropped=n)`. Input list order preserved for kept items.
7. Add new aliases to `config/aliases.yaml` as you meet them (append only).

### `tests/test_clean.py` (at minimum)

1. Same URL twice (one with `?utm_source=x` and a trailing slash) → one kept, `duplicates_dropped=1`.
2. Different URLs, same fingerprint → one kept.
3. Duplicate resolution keeps the more complete item.
4. "Ingersoll-Rand", "Ingersoll Rand Inc." and "IR" → "Ingersoll Rand".
5. "Kaeser Kompressoren" → "Kaeser Compressors"; a near-typo ("Ingersol Rand") matches by fuzzy score.
6. An unknown company stays as written (stripped). `None` stays `None`.
7. Date `"03/10/2026"` (ambiguous) → handled consistently (month first) and ISO; garbage → `None`.
8. Other fields are unchanged; order preserved.
9. Empty list → empty `CleanResult`.

## Task S3 — Integration (Thu night to Fri)

1. When Ragini's `collect_source` is on `main`, test your extractor on **real** pages **in memory only**: run `collect_source(source, gate, max_items=3)` in a Python shell and call `extract_item` on each page. Print only the resulting items (`item.model_dump_json(indent=2)`); never print or save `page.html`.
2. Check by eye: is the title right, the date right, is `matched_keywords` sensible, are key facts short and PII-free, is the company right? Fix extraction rules where real pages disagree with your assumptions (typical: dates in unusual formats, boilerplate in facts).
3. Send Nikhil any model field you think is missing (he owns `models.py`).
4. Be on call for the full run at Fri 07:30.

## Acceptance criteria (yours)

- [ ] `pytest tests/test_extract.py tests/test_clean.py -q` passes offline.
- [ ] Presidio runs with `en_core_web_sm`; no large-model download.
- [ ] On real pages (in memory), items validate as `Item` and contain no page text.
- [ ] Missing values are `null`, never guessed; `product` is `null`.
- [ ] Duplicates and company name variants are merged as specified.
- [ ] `run.py` (Nikhil) runs your functions without changes to your signatures.

## Do not

- Do not store, log or print page text or HTML.
- Do not fall back to regex when Presidio fails; report the exact error.
- Do not guess dates, companies, products or technologies.
- Do not use embeddings, LLMs or extra frameworks.
- Do not edit `models.py` or `keywords.yaml`; ask Nikhil.
