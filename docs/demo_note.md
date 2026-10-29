# Demo note: Atlas Copco Market & Technology PoC

Group 8, VIT Pune. Demo: Friday 30 October 2026.

> Items marked `TODO(owner)` must be filled with real values from the final run before the meeting. Nothing here is estimated.

## 1. What we built

We built a small pipeline that visits five approved, public USA websites about industrial compressor technology, collects their newest items, cleans them, and keeps only the relevant ones. The result is stored as JSON in a cloud Databricks Volume, never on a laptop. Every item carries its source link, collection date and a fact or claim label so a person can check it.

## 2. How it works

Input, then Engine, then Output. A compliance step first checks each site's status, terms and robots.txt and waits politely between requests. The collector reads each site's feed or news page in memory. The engine extracts a few fields from each page (title, date, company, technology, short key facts), removes personal data, and throws the page text away, keeping only a fingerprint. A filter then checks four things per item: is it about compressors, in North America, from a credible source, and recent (last 12 months). The reasons are stored, so we can show why something passed or failed. Nothing is stored locally and no AI model is used on Friday.

## 3. The 5 sources we propose, and why

| Source | Type | How we read it | robots.txt | Terms of use |
|---|---|---|---|---|
| Compressed Air Best Practices (industry news) | Trade news | RSS feed | allowed | no clause on automated access |
| Quincy Compressor (blog) | Competitor | RSS feed | allowed | no clause on automated access |
| Sullair US news | Competitor | web page list | allowed | no clause on automated access |
| Pumps & Systems (industry news) | Trade news | RSS feed | allowed | no clause on automated access |
| US Department of Energy newsroom | Government | web page list | allowed | no clause on automated access |

These 5 are our proposed list; the approved list needs your sign-off, and your Legal team should review it before go-live.

Why these: two US compressor makers (Sullair and Quincy), two trade publications with current dated feeds, and one government source. The useful compressor items come mainly from Compressed Air Best Practices, Quincy and Sullair; Pumps & Systems and the DOE newsroom cover wider topics, so most of their items are dropped by the filter, which shows the filter at work.

We also checked Atlas Copco's own newsroom and Kaeser's blog and decided not to use them: your own site adds nothing to a study of the market, and Kaeser's blog posts show no publication date, so none can pass our "recent" check.

## 4. Sources we found blocked or excluded, and why

| Source | Finding | Why |
|---|---|---|
| CAGI | Blocked | Its terms forbid "data mining, robots, or similar automated data gathering and extraction tools" |
| PR Newswire | Blocked | Its terms forbid scraping and any "robot, spider" access |
| Plant Services (Endeavor Business Media) | Blocked | Its terms forbid robots, spiders and scraping, even though a feed exists |
| Plant Engineering | Unreachable | The site answered HTTP 403 to our identified agent. We did not retry or bypass |
| Ingersoll Rand | Unreachable | The site answered HTTP 429 (too many requests) on our first request. We did not retry or bypass |
| Business Wire | Unreachable | The site answered HTTP 403, including for robots.txt. We did not bypass |

Two more sites were checked and are usable but held in reserve: Atlas Copco Group press releases (the list page builds itself with scripts) and ELGi US (its feed carries product pages, not news).

## 5. What the filter kept and dropped

Run `TODO(Nikhil: run_id)` on `TODO(Nikhil: date and time)`:

| Source | Collected | Duplicates dropped | Passed | Dropped by the filter |
|---|---|---|---|---|
| Compressed Air Best Practices | TODO(Nikhil) | TODO(Nikhil) | TODO(Nikhil) | TODO(Nikhil) |
| Atlas Copco USA | TODO(Nikhil) | TODO(Nikhil) | TODO(Nikhil) | TODO(Nikhil) |
| Sullair US | TODO(Nikhil) | TODO(Nikhil) | TODO(Nikhil) | TODO(Nikhil) |
| Kaeser USA blog | TODO(Nikhil) | TODO(Nikhil) | TODO(Nikhil) | TODO(Nikhil) |
| US DOE newsroom | TODO(Nikhil) | TODO(Nikhil) | TODO(Nikhil) | TODO(Nikhil) |

Examples of why items were dropped (take two or three real ones from the `clean/` folder in Databricks):
- TODO(Parth: item title, source, reason such as `no_compressor_keyword`, `too_old` or `date_missing`)
- TODO(Parth: item title, source, reason)

## 6. What we checked by hand

TODO(Parth: after `docs/check_results.md` is complete, write: "We opened 10 items from N sources and checked title, date, label, company, technology, key facts and personal data against the live page. X of 10 were fully correct. The errors we found were: ...")

## 7. Open questions for you

See `docs/questions_for_atlas_copco.md`. The most important: approval of the source list, a workspace on your side, who reviews the list in Legal, and a route to the sites that refused us (Ingersoll Rand in particular).

## 8. What comes next

Report template (PowerPoint or PDF), a review page where a person approves items, an AI-written summary, a weekly schedule, Canada and Mexico, patents and papers, and scoring of opportunities. These are not in Friday's PoC.
