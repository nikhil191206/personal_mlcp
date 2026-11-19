# Individual work, for the presentation slides

Written for: the four team members (Nikhil, Ragini, Sachi, Parth), to build their own slides and to hand to an AI
assistant so its answers stay accurate.

## How to use this file

1. **Slides:** find your section. Each person has "Slide-ready text" (four slides: title, bullets and a suggested
   picture) and a 60-second speaker script. Paste, then add your own screenshots.
2. **With an AI:** paste this whole file, then your task, for example "write my 3-minute speaker notes" or "make 4
   slides from my section". Use the prompt below.
3. **Fill the gaps:** anything marked `[ADD: ...]` is something only you know (hours, hardest moment, what you
   learned). Fill it in first, or tell the AI that it is unknown.
4. **Check your section.** It was written from the code, the briefs and the commit history. You know your own work
   better; correct anything that is wrong before you present.

### Prompt to paste with this file (copy as is)

> You are helping one member of a four-person university team prepare a presentation for Atlas Copco and faculty.
> The attached file is the only source of truth. Rules: (1) Use only facts, numbers and names in the file. (2) If
> something is not in the file, say "not stated in the file" and do not guess. (3) Never invent numbers, dates,
> accuracy scores or features. (4) Say "proposed" for sources, never "approved": only Atlas Copco approves sources.
> (5) Do not call the system AI or machine learning. It is rule-based; the only pretrained model is spaCy
> `en_core_web_sm`, used for privacy scrubbing. (6) Keep the limits and the problems we fixed: honest limits are
> a strength. (7) Plain spoken English, short sentences, explain any jargon. (8) Write only about the person I name;
> do not take credit for other people's work. My name is: [YOUR NAME]. My task is: [YOUR TASK].

---

## Part A: The project in one page (everyone uses this)

**What it is.** A market scout for Atlas Copco's Compressor Technique business. It finds public news about
compressors and related technology in North America, reads it politely, checks it by rules, and produces a short
list of facts. Every fact keeps a link to the original article.

**One command runs everything:** `python -m atlas.run`.

```
settings --> register + discovered sources --> for each source:
  1 Compliance Gate  2 Collect  3 Extract  4 Clean  5 Filter  6 Save
--> switching for refused sources --> stories --> output + log
```

**The steps.**
0. **Settings:** the run loads the saved settings (or the defaults): regions, months back, words to include or
   exclude, source types, discovery on or off, switching on or off, the watchlist.
0b. **Discovery (if on):** the scout finds and vets new candidate sites.
1. **Compliance Gate:** before any page is touched: is the source allowed, is its robots.txt ok, do its terms allow
   automation? A refusal is recorded with a reason and the source is never contacted again in that run.
2. **Collect:** the article list comes from the RSS feed (preferred) or a list page. 3 seconds between requests, our
   identified User-Agent, and a 429 or 503 stops that source. Pages are held in memory only.
3. **Extract:** title, date (never guessed), company, product, technology, event type, region, up to 3 short key
   facts, fact or claim, and the signals the filter needs. Personal data is removed. The text is then thrown away.
4. **Clean:** duplicates removed, dates in ISO format, company-name variants merged.
5. **Filter:** four yes/no checks plus the settings rules. Nothing is deleted here; each item gets pass or fail and
   the reasons.
6. **Save:** to the Databricks Volume. Nothing on a laptop.
7. **Switching:** if a followed company's source is refused, look for the same company in other allowed sources and
   label the result.
8. **Stories:** the same news from different sources is grouped.
9. **Output:** the results file, the log, a printed summary and a check that no data file was created locally.

**Phase 2 added.** US plus Canada scope; new technologies (air treatment, blowers, vacuum pumps, gas and hydrogen
compression); event type, region and product on every item; a scout engine that finds and vets new sources; saved
settings that rerun the system; switching; a one-page brief and a full report as PowerPoint or PDF; and a web
interface.

**Shared numbers (final demo run, from GUIDE.md section 2).**

| What | Number |
|---|---|
| Items that passed the filter | 47 |
| Sources read | 7 |
| Sources refused or blocked, shown honestly | 7 |
| Stories | 46 (1 seen in two or more sources) |
| Candidate sites the scout looked at | 67 |
| Errors | 0 |
| Local data files created on a laptop | 0 |
| Automated tests | 461 in the repo now (442 at the final demo run), all passing offline |
| Items hand-checked against live pages | 9 (target was 10) |
| Switched (fallback) items in the demo run | 0 |
| Canadian sources working | 0 |

**Shared rules (say these in any section).**
- Only public pages. robots.txt and terms are respected. A refusal is final: no workaround, no mirror, no archive,
  no proxy.
- Every fact has its source link. Sources are only **proposed**; Atlas Copco approves them.
- Rule-based on purpose, so every result can be explained. The one pretrained model is spaCy `en_core_web_sm`, used
  to find personal names so they can be removed.
- **fact** means a neutral or official source states it; **claim** means the company says it about itself. Most
  items are company press releases, so most are claims.
- Facts, not text: only short facts and links are stored, never article text. Nothing on laptops.

**Shared limits (honest).**
- Only 7 sources are read; more need written permission or a verified terms page.
- No Canadian source works yet: every one we tried blocks robots or has no usable feed.
- Switching was proven live once but produced 0 items in the demo run.
- Tags are automatic. The hand-check found some wrong, which we fixed; others may remain.
- Sites that load their news with JavaScript cannot be read.

**Shared glossary.**
- **Candidate:** a website the scout found that nobody has approved.
- **Usable:** a candidate that passed every safety check and the pass mark.
- **Trust score:** 0 to 100 points for a candidate, with a reason for every point.
- **Envelope:** the final output file of a run.
- **Switching (fallback):** looking for the same company in other allowed sources when its own source is blocked.
- **Evidence record (Item):** one article reduced to its facts, tags and link.
- **Register:** the list of known sources and their status (`config/sources.yaml`).

---

## Part B: Nikhil

**Role in one line.** The backbone and the integrator: storage, the compliance gate, the collector, the filter, the
run command, the shared data models, settings, switching, stories, the one-page summary, the simple app, and the
final run and hand-checks.

### What Nikhil owns, file by file

| Area | File | What it does | Tests |
|---|---|---|---|
| Storage | `atlas/storage.py`, `atlas/storage_check.py` | Reads and writes the Databricks Volume through the Databricks SDK; the check proves a write, a read-back and that no local file was created | in test_run |
| Compliance Gate | `atlas/compliance.py` | robots.txt, terms status, 3 s delay, identified User-Agent, per-source decision with reasons | 31 |
| Collector | `atlas/collect.py` | RSS first, else an HTML list page; page budget; stops on 429 or 503 | 18 |
| Filter | `atlas/filter.py` | The four checks, plus the settings rules, with a closed set of reason codes | 35 |
| Run command | `atlas/run.py` | Orchestrates everything; live progress; summary; exit code; local-data check | 29 |
| Shared models | `atlas/models.py` | The data contract: Item, Source, Candidate, ScoutSettings, WatchEntry, StoryCluster, OutputEnvelope | in all |
| Settings | `atlas/scout/settings_store.py` | Saved settings, candidates and decisions on the Volume; `usable_sources` | 20 |
| Switching | `atlas/scout/fallback.py` | Looks for a blocked company in other allowed sources and labels the result | 29 |
| Stories | `atlas/scout/stories.py` | Groups the same news from different sources | 14 |
| One-page summary | `atlas/report/onepager.py` | Four-box summary as PPTX or PDF | 12 |
| Brief | `atlas/report/brief.py` | Facts, sources and why it matters for Atlas Copco | 8 |
| Review | `atlas/review.py` | Saves Important or Not important facts and source confirmations | 5 |
| Simple app | `app/main.py`, `app/pages/1_Sources.py`, `2_Facts.py`, `3_Report.py`, `app/lib/simple.py`, `simple_ui.py` | The four-page Streamlit app with a rerun after every save | 5 |
| Docs | `GUIDE.md`, `README.md`, `docs/decisions.md`, `docs/check_results_phase2.md` | The complete guide, decisions, hand-check results | n/a |

### Phase 1 in detail

**Storage and the "nothing on laptops" rule.** All data lives in the Volume
`/Volumes/atlas_poc/default/data/<prefix>/`, in these folders: `source_register/`, `raw/`, `clean/`, `facts/`,
`output/`, `logs/`, plus `settings/`, `scout/` and `reports/` in Phase 2. The prefix (`ATLAS_PATH_PREFIX`) decides the
folder: empty means the real demo folders, `dev/<name>` is a personal sandbox. The token lives only in `.env`, which is
git-ignored.

**The Compliance Gate.** Before a source is touched it must pass: not blocked, vetted as working, terms do not forbid
automation, robots.txt allows the listing. Every decision is written to the log with its reasons. The gate sends our
identified User-Agent (`AtlasCopcoStudentPoC/0.1`, with the team contact email; the run stops with a clear error if the
contact email is missing) and waits 3 seconds between requests.

**The collector.** Reads the RSS feed when there is one, otherwise a list page. Each page is fetched through the gate
and held in memory. A 429 or 503 stops that source and nothing retries around it.

**The filter, check by check.** An item passes only if all four are true.

| Check | Passes when | Reason code if it fails |
|---|---|---|
| Compressor-related | a compressor keyword is in the title or text | `no_compressor_keyword` |
| North America | the source is in US, CA or MX, or the text names a place there | `not_north_america` |
| Credible source | the source is vetted "working" and its status is proposed or approved | `source_not_credible` |
| Recent | the date is within the last N months (default 12) | `too_old`, `date_missing`, `date_in_future` |

Every failed check is listed, not only the first. A future date is treated as invalid. "Industrial" is only a flag
unless the setting "require industrial" is on. The filter never deletes an item; dropping is the run command's job.

**The run command.** For each source: gate, collect, write `raw/`, extract each page (an error on one page is logged
and the run continues), clean, filter, write `clean/` (everything) and `facts/` (passed only). The final output holds
only passed items; failed items stay in `clean/` so anyone can see why. At the end it validates the output against the
data contract, writes the log, prints a summary table, and runs a local-data check (`PASS` means no file was created on
the laptop). **Exit code 0** means the output validated and there were no errors. Blocked sources are findings, not
errors. It also prints live progress lines per source.

**Shared models.** `atlas/models.py` fixed the exact field names so four people, using four different AI tools, produced
code that fits together. Changes to it were announced to everyone.

### Phase 2 in detail

**Saved settings.** `settings/scout_settings.json` holds the settings the run uses. A saved file that fails validation
raises a clear error naming the file, instead of silently using defaults. The defaults live in
`config/scout_settings.yaml`, and the default regions are now **US and Canada**.

**`usable_sources`: which discovered sources a run may use.** All of these must hold: "use discovered sources" is on;
the candidate is usable; its trust score is at or above the minimum (default 70); its source type is allowed; no person
rejected it; it is not already in the register; its newest item is inside the recency window; and its relevance sample
is not zero. Accepting a candidate never overrides an unsafe one. Nothing is ever approved automatically.

**Filter obeys settings.** Six extra rules, checked after the four, each with its own reason code:
`region_not_selected`, `technology_not_selected`, `event_type_not_selected`, `excluded_keyword`, `not_industrial`,
`source_type_not_selected`. With no settings the filter behaves exactly like Phase 1.

**Switching.** If a source is refused, returns nothing, or hits a rate limit, and a watch entry follows its company
(the watchlist: Ingersoll Rand, Kaeser, Sullair, Quincy, Gardner Denver, Hertz), the run:
1. labels items other sources already gave that mention the company;
2. collects more from the other allowed sources and keeps only items that mention the company in the title, key facts
   or extracted company;
3. labels them `via_fallback`, adds a "switched" row to the sources table, and prints and logs it.
A guard refuses the refused site, its subdomains and any web archive, cache, translation or proxy route to it
(`fallback_forbidden_route`). So switching is a visible, labelled feature, never a hidden workaround.

**Stories.** Items join one story when the company is the same and either the product is the same, or the event type
is the same (and not the catch-all "other") with similar titles of at least 4 words, within 10 days. Groups are
transitive (union-find) and the story id is stable between runs. Single-item stories are still produced.

**Run integration.** New flags `--use-default-settings`, `--no-discovery`, `--no-fallback`. The source list is the
register plus the usable discovered sources. A discovery error is logged and never stops the run. The discovery cap is
60 new candidates per run (it was 25, which left half the seeds untried).

**Sample data.** `tests/fixtures/sample_output.json` is a synthetic, validated output (invented companies) with
stories, a switched item, a refused source and a discovered source, so Sachi and Parth could build their parts before
real runs existed.

**One-page summary and brief.** The one-page summary has four boxes, every line computed from the run's data with no
invented text: "look at first" (top 3 events at other companies, ranked acquisition, partnership,
investment or expansion, regulation, product launch, one per company), "other facts", "difference from Atlas Copco",
and "sources". A line counts as a fact only if it has a number or an event verb and is not a blog teaser, and a text
containing a removed-name placeholder is never shown. The brief is facts, sources and why it matters, and leaves out
facts a person marked Not important.

**Review and the simple app.** Facts can be marked Important or Not important; sources can be confirmed. Saving writes
the decision and starts a rerun, queueing one more run if one is already going. The simple app has four pages:
Dashboard (filters with a Done button, run progress, results), Sources, Facts and Report. Confirming a source records
the team's decision only; it is not an Atlas Copco approval.

**Final run and hand-check.** The final demo run `20261115T204628Z` (empty prefix) gave 47 items. Nikhil re-fetched 9
items through the gate and compared title, date, company and the key-fact wording against the live pages: no wrong
title, date, company or fact was found, and fact overlap ranged from 0.9 to 1.0. The demo commit was tagged
(`phase2-demo`, `phase2-demo-v2`).

### Problems Nikhil found and fixed (use as stories)
- **Stories merged two unrelated "other" articles** (found in Sachi's live check): "other" never joins items, and short
  titles cannot join on a subset match.
- **Switching missed a Kaeser article whose title never names Kaeser:** it now also uses the extracted company field.
- **The scout marked Sundyne's terms fine** (it read purchase conditions, but the real website terms are Honeywell's
  and forbid robots): the vetter reads website terms first and follows a parent's terms link; Sundyne is blocked and its
  three fetched pages were removed from the Volume.
- **Default regions US only dropped US-source articles about Canada:** default is now US and Canada.
- **The discovery cap of 25 left half the seeds untried:** raised to 60.
- **A terminal that looked frozen:** live progress lines were added.

### Numbers Nikhil can quote
47 items, 7 sources read, 7 refused openly, 46 stories (1 in two or more sources), 67 candidates, 0 errors, 0 local
files, 461 tests in the repo (442 at the final run), 9 items hand-checked.

### Demo moments
1. Run summary: per source collected, passed, dropped, and the refused list with reasons.
2. Dashboard: sources table (7 read, 7 refused with reasons); open one item and show why it passed.
3. Settings: change "how recent" and press Done; show that a rerun starts by itself.
4. Switching: explain the Ingersoll Rand case (refused, tried correctly, found nothing); mechanism proven live.

### Limits
Switching gave 0 items in the demo run; only 7 sources; most facts are claims; 9 items hand-checked instead of 10;
stories are rule-based and can still miss a same-story pair when the company is missing.

### Slide-ready text

**Slide 1: Backbone: storage, compliance and the run**
- All data on a Databricks Volume; 0 files on laptops (a check at the end of every run).
- One Compliance Gate for every request: robots.txt, terms, 3 s delay, identified User-Agent.
- One command, `python -m atlas.run`, with live progress and a validated output.
- Visual: the pipeline diagram (gate, collect, extract, clean, filter, save).

**Slide 2: The filter: four yes/no checks**
- Compressor-related, North America, credible source, recent. One no drops the item and the reason is saved.
- Settings add six more rules: region, technology, event type, excluded words, industrial, source type.
- Visual: a table of the four checks with their reason codes.

**Slide 3: Settings, switching and stories**
- Saved settings change the next run; saving reruns the system.
- If a followed company's source is blocked, look in other allowed sources, labelled `via_fallback`.
- Same news from several sources is grouped into one story.
- Visual: the switching flow with the "never contact the refused site" guard.

**Slide 4: Result and checks**
- 47 facts, 7 sources read, 7 refused openly, 0 errors, 461 tests.
- 9 items hand-checked against live pages: no wrong title, date, company or fact.
- Visual: the run summary screenshot.

### 60-second speaker script
"I built the backbone. Every request passes one compliance gate that checks robots.txt and the site's terms and waits
three seconds, so we stay polite and legal. Data goes straight to a Databricks Volume, nothing is saved on a laptop, and
every run ends with a check that proves it. The filter asks four yes or no questions, and for every dropped item we save
the reason. In Phase 2 I added saved settings, switching to other sources when one is blocked, and stories that group the
same news. The final run gave 47 facts from 7 sources, with 7 sources refused openly and zero errors. I also re-checked 9
items against the live pages and found no wrong title, date or company."

### Likely questions
- *Why wait 3 seconds?* To be polite and compliant. A full run takes 15 to 25 minutes in the background.
- *What if a site blocks us?* We stop and say so. Switching may find the same company in other allowed sources, and
  never goes around the block.
- *Why were most facts claims?* Most items are company press releases; "fact" needs a neutral or official source.
- *What would you improve?* More sources with permission, and better story grouping when the company is missing.

`[ADD: Nikhil's own hours, hardest moment, what you learned]`

---

## Part C: Ragini

**Role in one line.** The scout: finding new sources, vetting them against the rules, scoring them, and the search tool
and website for the demo.

### What Ragini owns

| File | What it does | Tests |
|---|---|---|
| `atlas/scout/discover.py` | Finds candidate sites from seeds, links and feed autodiscovery | 16 |
| `atlas/scout/vet.py` | Checks robots.txt and terms, finds a feed, samples relevance, computes the trust score | 45 (Nikhil added some with the vetter fix) |
| `config/discovery_seeds.yaml` | 40 starting websites, all marked unverified | n/a |
| `demo_search.py` | Terminal search over a finished run | n/a |
| `web/` | React website with a local API: Overview, Search, Facts, Sources, Filters, Report | n/a |
| `docs/source_vetting.md`, `docs/decisions.md`, `docs/questions_for_atlas_copco.md` | Live-check findings, decisions, question 11 | n/a |

### How it works
1. **Find:** the seed list, links found on sources we already read (skipping social media, search engines and known
   domains), and RSS feeds advertised on a homepage. At most 60 new candidates per run.
2. **Safety checks, in order:** robots.txt (if it says no, stop, nothing else is fetched), then the whole terms page is
   scanned for words such as robot, spider, scrape, crawl, bot, harvest, data mining, automated; the quote (up to 200
   characters) is kept as evidence. Purchase and sales conditions do not count as website terms. Terms not found means
   `unknown`, which is not usable.
3. **Useful?** A feed or a list page, a recent date, and a relevance sample of titles against compressor keywords.
4. **Limits:** at most 8 requests per candidate, 3 seconds between requests, stop on HTTP 429.
5. **Score and verdict.**

### The trust score (rule-based, no AI)

| Check | Points |
|---|---|
| Terms of use read and ok | 25 |
| robots.txt allows | 15 |
| Feed: RSS 15, HTML list 10 | 15 |
| Freshness: within 30 days 15, 90 days 10, a year 5 | 15 |
| Relevance: 50% or more of sampled titles 15, 25% or more 10, any 5 | 15 |
| Source type: government or association 10, listed in a seed 5 | 10 |
| HTTPS with the feed on the same domain | 5 |

If the terms forbid automation, the score is forced to 0. A candidate is usable only if robots allow, terms are
positively ok, it is public and it has a dated item; the pass mark for a run is 70 by default and changeable in
Settings. The weights are our own judgement, not learned from data.

### Numbers Ragini can quote
- 67 candidates looked at in one run: 14 rejected by the rules, 12 auto-vetted, 41 needing review, 8 usable (12%).
- 21% of candidates actively refuse robots (robots.txt 15%, terms 6%). 63% have no readable terms page and are treated
  as not usable. Half of our own 14 registered sources (7) are blocked or need permission.
- Burckhardt Compression scored 85 (terms ok, robots allowed, RSS feed, news from 3 Nov 2026).

### The Sundyne story (use it)
Sundyne looked fine at first: the check read its purchase conditions and said OK. A hand-check found that the website
terms belong to Honeywell and forbid robots. The vetter now ignores sales and purchase terms and follows a parent
company's terms. Sundyne is blocked and never read. The system was corrected after a human check.

### The Canada finding
We tried 16 English-language Canadian sites. Every one refused robots, forbade automation, or had no usable feed. Canada
is in scope but no Canadian source can be read without permission. Question 11 in
`docs/questions_for_atlas_copco.md` asks Atlas Copco for help.

### Demo moments
1. Sources page: a trust score with its reasons, and a blocked source with its reason (Sundyne).
2. Search: type "compressor" and open a source link.

### Limits
The weights are judgement, not learned. The scout cannot read sites that need JavaScript. Unknown terms count as not
usable, which is strict and rejects some harmless sites. The pass mark of 70 is a default, not a proven optimum.

### Slide-ready text

**Slide 1: The scout: finding sources**
- Three ways to find candidates: 40 seeds, links on known sources, feed autodiscovery.
- Never a search engine, never a bypass. At most 60 new candidates per run.
- Visual: a flow from seeds and links to a candidates list.

**Slide 2: Vetting: safety before reading**
- robots.txt first; then the whole terms page is scanned for bans on robots; the quote is kept as evidence.
- No terms page means not usable. 8 requests per site, 3 s apart, stop on 429.
- Visual: the ordered checks with a stop sign on each refusal.

**Slide 3: The trust score**
- Out of 100: terms 25, robots 15, feed 15, freshness 15, relevance 15, type 10, https 5.
- Forbidden terms force 0. Pass mark 70, changeable in Settings.
- Visual: the points table, with Burckhardt (85) and Sundyne (0) as examples.

**Slide 4: Result and the honest findings**
- 67 candidates: 21% refuse robots, 12% usable. Sundyne caught and blocked.
- Canada: 16 sites tried, none readable; we need Atlas Copco's help.
- Visual: a bar of the 67 split into rejected, needs review, auto-vetted.

### 60-second speaker script
"My part is the scout: how the system decides which websites it may read. It finds candidates from a seed list, from
links on sources we already use, and from feeds. For each one it checks robots.txt, then reads the whole terms page for
any ban on robots, and keeps the quote as evidence. Then it gives a trust score out of 100, with a reason for every
point. Of 67 candidates, 21 percent refuse robots and only 12 percent pass every check. A real example: Sundyne looked
fine until a hand-check showed its parent company's terms forbid robots, so we fixed the vetter and blocked it. We also
tried 16 Canadian sites and none could be read, so we are asking Atlas Copco for help."

### Likely questions
- *Is the trust score machine learning?* No. It is a weighted checklist with a hard-fail gate, so it is explainable.
- *Why is only 12% usable?* The safety rules are strict on purpose; most sites have no terms page or block robots.
- *Why not use a search engine to find sites?* Scraping search results breaks their terms; we never do it.

`[ADD: Ragini's own hours, hardest moment, what you learned]`

---

## Part D: Sachi

**Role in one line.** The extractor and the reports: turning a web page into a clean evidence record, adding the Phase
2 tags (region, event type, product), and building the PDF and PowerPoint report.

### What Sachi owns

| File | What it does | Tests |
|---|---|---|
| `atlas/extract.py` | One page to one evidence record: text, title, date, company, technology, key facts, label, privacy scrub, region, event type, product | 82 |
| `atlas/clean.py` | Dedupe, ISO dates, company-name merging | 14 |
| `config/keywords.yaml`, `technologies.yaml`, `aliases.yaml`, `products.yaml` | Keyword lists, technology labels, company aliases, product families | n/a |
| `atlas/report/build.py` | Shared report computation used by both formats | 24 (with the builders) |
| `atlas/report/charts.py` | Charts drawn with matplotlib into memory | in the 24 |
| `atlas/report/pptx_builder.py`, `pdf_builder.py` | The PowerPoint and PDF reports | in the 24 |
| `docs/report_design.md` | What was checked in the reports | n/a |

### Phase 1: the extractor in detail (`extract_item`)
Page text exists only inside this function. The returned record holds no page text.
1. **Main text.** `trafilatura` removes menus, ads and footers and returns the article text and metadata.
2. **Title.** From metadata, else the list-page title, else none.
3. **Date.** From metadata or the list page, parsed with `dateutil` to ISO `YYYY-MM-DD`. Month first for ambiguous US
   dates. **Never the fetch date.** An unparseable date, an incomplete one, or one in the future becomes none. A date
   that only comes from a page footer artefact (for example a faked 1 January) is treated as no date.
4. **Very short page.** Below the minimum text length, it still returns a record with what exists (`key_facts=[]`),
   a fingerprint built from the URL and title, and never invents the rest.
5. **Privacy scrub.** Microsoft Presidio with the small spaCy model `en_core_web_sm` removes personal names, emails,
   phone numbers and similar data (replaced by `<PERSON>`, `<EMAIL>`, `<PHONE>`). Places and organisations are **not**
   removed, because they are needed for the North America check and the company. The same scrub runs on the title and on
   every key fact. If Presidio or the model is missing, the function **raises an error**. It never skips the scrub and
   never falls back to regex.
6. **Signals.** On the cleaned text plus the title: the compressor keywords found, an industrial hint, and whether a US
   place is named (whole words only; the pronoun "us" is never read as a location).
7. **Technology.** The first match walking `config/technologies.yaml` in order (specific before general).
8. **Company.** A competitor source gives its own cleaned company name (for example "Kaeser Compressors USA Newsroom"
   becomes "Kaeser Compressors"); otherwise the company comes from the alias list, then from organisation names found by
   spaCy, else none. Never a guess.
9. **Key facts.** By rules, no AI: sentences with a compressor keyword, a number with a unit or currency, or an event verb
   (announce, launch, acquire, open, expand, partner, certify, award, invest); each at most 200 characters, boilerplate
   (cookie, subscribe, "read more", copyright) removed, the first 3 distinct ones kept.
10. **Label.** Default `claim`. `fact` only for a government source, or a trade-news source with a reporting pattern
    (acquires, files, opens, completes, appoints, fined, recall). A competitor's newsroom is always a claim; when unsure,
    a claim.
11. **Fingerprint** of the cleaned text, for duplicate detection. Then the text is dropped.

### Phase 1: the cleaner in detail (`clean_items`)
1. URLs are normalised only to compare: host in lower case, no fragment, no tracking parameters (`utm_*`, `fbclid`,
   `gclid`, `ref`), no trailing slash.
2. Duplicates dropped by normalised URL, then by fingerprint (same content at a different URL). The more complete item
   is kept, and the count is reported.
3. Dates are made ISO, month first when ambiguous, and unparseable ones become none.
4. Company names are merged using `config/aliases.yaml`: the name is normalised (case, punctuation, legal suffixes such
   as Inc, LLC, GmbH removed), matched exactly, and otherwise matched fuzzily with `rapidfuzz` (token sort ratio of 92 or
   more). No match keeps the original name; the cleaner never invents a canonical form.
5. No other field is changed.

### Phase 2: wider scope (Part A of Sachi's task)
- **New technology labels and keywords:** air treatment (dryers, filters), blowers, vacuum pumps, gas compressors,
  hydrogen compression; new company aliases; `config/products.yaml`; separate Canadian and Mexican place lists.
- **Region (`detect_region`):** US, CA, MX or none. It takes the most frequent hit among the three location lists in the
  title and text (the title counts double); a tie or no hit falls back to the source's region only if the source is a
  company or publisher based there and the text has no conflicting location; otherwise none. **Never defaults to US.**
  Abbreviations are case-sensitive. Places outside North America give a null region.
- **Event type (`classify_event`):** rule-based, no model. It looks at the title, then the opening sentences, with this
  priority: acquisition, regulation or standard, partnership, investment or expansion, product launch, appointment,
  award, event; no match gives "other". Later fixes: a how-to article is not news, a video episode is not a launch, and
  "wins an order" is not an award.
- **Product (`detect_product`):** a known series from `products.yaml`, or a model code (letters then digits, for example
  `OFE1550`) that appears more than once; otherwise none. **No product beats a wrong product.**

### Phase 2: the report (Part B of Sachi's task)
- **Structure (about 10 slides or pages, same content in both formats):** title; executive summary (templated text filled
  only with computed counts, no AI); scope and method; what we found (top items ranked by a transparent rule); by company;
  by technology and event type; stories seen in several sources; sources and compliance (refused sources are never hidden);
  how to read fact versus claim; appendix with every item and link.
- **Builders:** `charts.py` draws matplotlib charts into memory with a colour-blind-safe palette; `pptx_builder.py`
  (python-pptx, 16:9, speaker notes saying where each number comes from); `pdf_builder.py` (reportlab, A4, page numbers,
  clickable links); `build.py` holds the shared counts so both formats always agree.
- **Safety:** nothing is written to the laptop; the builder refuses (raises) if an item contains an email or phone
  pattern; an empty run produces a valid report with an honest "no items passed" message.
- **Wording rules:** "Prepared for Atlas Copco by Group 8, VIT Pune. Source list is proposed, pending approval."

### Live check and fixes (15 Nov 2026)
Run `20261115T045141Z` (prefix `dev/sachi`): 13 items from 3 of 11 sources, 6 refused; Ingersoll Rand switching tried with
0 items. Both reports were opened in the Volume and read: numbers matched the run, links opened the right articles, no
text overflowed. 7 items were hand-checked: event types right, product OFE1550 right, the Fluke item correctly has no
product (the article names two models). Fixes that followed: places outside North America give a null region (2 items
were still tagged US although about Portugal and the Netherlands), a switching row is no longer counted as a source,
"other" is not reported as the most common type of news, and a switch that found nothing is now stated.

### Problems Sachi found and fixed (use as stories)
- **Known company names were scrubbed as people.** An allow-list keeps canonical names, names without the legal suffix
  and single brand words out of the scrub (two commits).
- **Product names were scrubbed too** ("Polaris P300", "Fluke"): the name removal now needs a full name of two or more
  letter-only words with no machine word.
- **Dates faked as 1 January** from page footers: such dates are treated as no date.
- **A 400 MB model was downloaded:** the small model is pinned.
- **Wrong region:** places outside North America no longer default to US.

### Numbers Sachi can quote
- 82 extractor tests, 14 cleaner tests, 24 report tests (the repo now has 461 tests in total).
- Live check: 13 items, 3 of 11 sources, 7 items hand-checked, report built in both formats.
- 9 event types, 3 regions, 5 technology groups added.

### Demo moments
1. Open one item and show its tags (company, event type, region, key facts) next to the source link.
2. Show a `<PERSON>` replacement and explain why names are removed.
3. Build the report and open it: executive summary, sources and compliance page (refused sources visible).

### Limits
Tags are rule-based and some are still wrong; a vague title gives a vague tag. Names can be over-scrubbed. Some items
have no region. The report layout is our own neutral design because no Atlas Copco template was received (open question).
Stored items from older runs keep old tags until rerun.

### Slide-ready text

**Slide 1: From a web page to an evidence record**
- Page text is read in memory only; we keep the link, a few short facts and tags.
- Title, date (never guessed), company, technology, up to 3 key facts, fact or claim.
- Visual: a page turning into a small record card.

**Slide 2: Privacy by design**
- Personal names, emails and phones removed with Presidio and a pretrained spaCy model.
- If the model is missing, the system stops; it never skips the scrub.
- Visual: before and after of a name replaced by `<PERSON>`.

**Slide 3: Phase 2 tags: region, event type, product**
- Region US, CA or MX, never defaulting to US; event type from 8 rule categories; product only if clearly stated.
- Visual: the event priority list.

**Slide 4: The report**
- About 10 slides or pages, as PowerPoint and PDF, with charts, built in memory.
- Refused sources are shown, never hidden; every number is computed from the run.
- Visual: two report pages side by side.

### 60-second speaker script
"I built the extractor, the cleaner and the report. The extractor reads a web page in memory and turns it into a small
evidence record: the title, the date, which company, the technology, up to three short key facts and whether it is a fact
or just a company claim. Then it removes personal names using a pretrained model and throws the text away, so we keep only
the link and a few facts. In Phase 2 I added region, event type and product detection, all by rules, and when something is
unclear it stays empty instead of guessing. I also built the report as PowerPoint and PDF, with charts, where every number is
computed from the run and refused sources are shown openly."

### Likely questions
- *Why not store the full text?* Copyright and privacy; the link and a few facts are enough.
- *How accurate are the tags?* They are rule-based. A hand-check found some wrong, which we fixed. We do not claim a
  percentage. `[ADD: Sachi's own check numbers if available]`
- *Is it AI?* No. The only pretrained model is spaCy's small English model, used for names. The report text is templated.

`[ADD: Sachi's own hours, hardest moment, what you learned]`

---

## Part E: Parth

**Role in one line.** Quality assurance, documentation and the first full frontend.

### What Parth owns

| Area | File | What it is |
|---|---|---|
| Client questions | `docs/questions_for_atlas_copco.md` | Questions for Atlas Copco, each with "why we ask" and "what we do with the answer" |
| Glossary | `docs/glossary.md` | Plain-English definitions of compressor terms (rotary screw, centrifugal, oil-free, air end, VSD, CFM, PSI) and pipeline terms (robots.txt, RSS, fingerprint, evidence record) |
| Keyword suggestions | `docs/keyword_suggestions.md` | Terms to add to the keyword lists, plus words that could cause false matches |
| Demo note | `docs/demo_note.md` | One page: what we built, how it works, proposed sources, blocked sources, what the filter kept and dropped |
| QA rubric | `docs/check_results.md` | The hand-check method: title, date, label, company, technology, key facts, no personal data, filter result |
| Frontend | `app/main.py`, `app/pages/1_Dashboard.py` to `5_Report.py` | The five-screen Streamlit app |
| Frontend logic | `app/lib/data.py`, `filters.py`, `settings_ui.py`, `sources.py`, `runner.py`, `report.py`, `dashboard.py` | The logic, kept out of the browser code so it can be tested |
| Tests | `tests/test_app_logic.py` | 72 offline tests now (69 when delivered) |
| User guide | `docs/frontend.md` | How to start the app and what each screen does |
| Status record | `docs/parth_contribution_and_team_status.md` | Parth's contribution record |

The work was delivered through two pull requests (#1 documentation, #2 frontend) from Parth's own fork and merged into
`main` by Nikhil.

### Phase 1 in detail (documentation and quality assurance)
- **Questions for Atlas Copco:** approval of the proposed sources, a workspace so data stays in their environment, the
  report template, a narrower compressor topic, the run frequency, who in Legal reviews the source list, and whether a
  hosted model is allowed for the AI step, plus questions on fact versus claim, whether "industrial" must be required and
  whether the 12-month window is right.
- **Glossary and keyword suggestions:** so a non-engineer can follow the project, and so Nikhil can merge sensible
  keywords into the filter.
- **Demo note and QA rubric:** the one-page brief for the demo and the method that every hand-check follows. Rule: any
  number in the demo note must match the real run, and errors go to the owner (extraction to Sachi, filter to Nikhil,
  sources to Ragini).

### Phase 2 in detail (the five screens)
**Entry point.** `app/main.py` uses a wide layout and a sidebar showing the active storage prefix, with an amber warning
when the prefix is empty ("you are looking at the real demo folders").

**Data layer (`app/lib/data.py`).** Reads Databricks only through the team's storage code: newest run, run list,
the output file validated with the data contract, the run log, and all cleaned items so failed items can be browsed with
their reasons. Reads are cached for 60 seconds with a Refresh button. If Databricks cannot be reached, the real error is
shown and the page stops; it never shows stale or fake data.

**1. Dashboard.** Header counts; a sources table with refused sources highlighted and discovered sources badged
"discovered, not approved"; an item browser with combinable filters (source, type, fact or claim, passed or failed,
company, technology, event type, region, date range, story, via fallback, text search); item detail with the four filter
checks and a plain-English "why was this dropped?" for every reason code; a stories view; charts (items per source,
company, event type, month); and JSON or CSV downloads built in memory.

**2. Settings.** An editor for every scout setting, grouped (scope, relevance filter, sources, scout engine, watchlist),
validated by building the settings object (errors shown, invalid values not saved), Save, Reset to defaults with a
confirmation, a diff panel listing every field that differs from the defaults, and a plain-English line under each
control. A note: "Changes apply to the next run."

**3. Sources.** The register (read only) and the scout's candidates with trust score, evidence, terms quote and link,
robots status and whether usable. Accept and Reject buttons record the decision with a name; **Accept is disabled with an
explanation when the candidate is not usable**, so a person cannot override the safety rules. A banner says discovered
sources are not approved by Atlas Copco.

**4. Run.** Controls for source, max items, default settings, no discovery and no fallback; starts `python -m atlas.run`
as a subprocess with the same Python; live progress parsed from the console lines into a progress bar and per-source
status; a Stop button; the run id and summary at the end; only one run at a time.

**5. Report.** Pick a run, pick PDF or PPTX, generate through Sachi's report function, and download from memory; list
existing reports.

**Frontend safety rules (they are tested).**
- The token is never shown, logged or put on a command line; a guard in the runner blocks any argument that contains
  "token", "dapi", "secret" or "password".
- No data or report file is written to the laptop.
- The app never contacts a website; it only starts the pipeline.
- Settings change only through the saved-settings code; the app never edits files in `config/`.

### Tests
`tests/test_app_logic.py` covers the pure logic only, no browser and synthetic data: every filter and their
combinations, the settings diff, building settings from form values (valid and invalid), the progress-line parser, the
newest-run lookup with mocked storage, the run command with the token never in the arguments, reason-code labels, and that a
decision cannot be saved for an unusable candidate. 69 passed when delivered, 72 now.

### Problems and honest notes
- Nikhil later replaced the five screens with a simpler four-page app; the original five screens are kept in
  `app/advanced_pages/`.
- The Phase 2 integration check in Parth's task (hand-check 10 items and 3 switched items, then
  `docs/check_results_phase2.md`) was written by Nikhil from the final run; 9 items were checked and no switched item
  existed. `[ADD: if Parth did any of this check, say what]`
- Several screens used emojis for status; they were removed in the simple app.

### Numbers Parth can quote
- 5 documents in Phase 1; 5 screens and 7 logic modules in Phase 2.
- 72 offline tests for the app logic in the repo now (69 on delivery).
- In his own record at the time: 408 of 408 repo tests passing.

### Demo moments
1. Dashboard: open one item and show "why was this kept or dropped".
2. Settings: change a value and show the diff panel (but do not save, because saving starts a run).
3. Sources: a candidate with its trust score and the Accept button greyed out for an unusable one.

### Limits
The five-screen app is now secondary to the simple four-page app. Some screens depend on a finished run existing in the
Volume. The app is local only and must never be hosted publicly.

### Slide-ready text

**Slide 1: Documentation and quality assurance**
- Questions for Atlas Copco, glossary, keyword suggestions, demo note.
- A hand-check method with 8 checks per item; every error goes to its owner.
- Visual: the QA table.

**Slide 2: The frontend: five screens**
- Dashboard, Settings, Sources, Run, Report, in Streamlit.
- Every screen explains itself in one line; errors are shown in plain English with the technical message beneath.
- Visual: one screenshot per screen.

**Slide 3: Safe by design**
- No token on screen or in any command; no files on the laptop; the app never visits a website.
- Accept is disabled for an unusable source: a person cannot override the safety rules.
- Visual: the disabled Accept button with its explanation.

**Slide 4: Tested**
- The logic is kept out of the browser code and tested offline: 72 tests.
- Visual: the test summary.

### 60-second speaker script
"I looked after quality, documentation and the frontend. In Phase 1 I wrote the questions for Atlas Copco, the glossary,
the keyword suggestions, the demo note and the method for hand-checking items against live pages. In Phase 2 I built a
five-screen Streamlit app: a dashboard to browse and filter the facts and see why an item was dropped, a settings editor,
a sources screen, a run launcher with live progress, and a report screen. It is safe by design: the token is never shown,
nothing is saved on the laptop, and a source that failed the safety rules cannot be accepted. The logic has 72 offline
tests."

### Likely questions
- *Where do the settings go?* Saved to the Volume; they apply to the next run.
- *Can the app approve a source?* No. Confirming only records the team's decision; Atlas Copco approves.
- *Why two apps?* The five-screen app is the full version; Nikhil added a simpler four-page one for the demo.

`[ADD: Parth's own hours, hardest moment, what you learned]`

---

## Part F: Questions anyone may get (answers all four can use)

- **Is the data correct?** Every fact links to its source, the rules are tested, and we hand-checked 9 items against the
  live pages and found no wrong title, date, company or fact. The tags are automatic and roughly right; we found and fixed
  mistakes. We do not claim a percentage.
- **Why no Atlas Copco news?** Their own newsroom is left out on purpose: it adds nothing to a market study.
- **Is any of this AI?** No. The decisions are rules. The only pretrained model is spaCy `en_core_web_sm`, used to remove
  personal names.
- **Why does a full run take 15 to 25 minutes?** We wait 3 seconds between requests to be polite. It is a background job.
- **What do you need from Atlas Copco?** Approval of the source list; permission emails for sites without a terms page and
  for a Canadian trade magazine; a slide template; whether Mexico is in scope; whether a search API may be used for
  discovery.
- **What would you do next?** Get permission for more sources, add a Canadian source, hand-label a set of articles and
  test a trained event-type classifier against the rules, and add a summary step if a model is approved.
