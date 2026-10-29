# Source vetting

Checked on **2026-10-29** with the procedure in `parent.md` section 11. Agent used for every request: `AtlasCopcoStudentPoC/0.1 (+contact: industrymlcp@gmail.com)`, at least 3 s between requests, nothing saved to disk. Per source we fetched: `/robots.txt`, the homepage (to find news, feed and terms links), the terms page, and then one listing and one article through our own Compliance Gate and Collector.

**Result: 13 candidates vetted. 7 `working` (5 proposed, 2 held in reserve), 3 `blocked` by their terms, 3 `unreachable` (the site refuses our agent without a ban).** Nothing was worked around. All sources stay `proposed` until Atlas Copco approves them; Atlas Copco's Legal team should review the list before go-live.

## Summary table

| # | source_id | name | type | access | robots | terms | public | test fetch | vetting_status | in register |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 | airbestpractices_news | Compressed Air Best Practices | trade_news | rss | allowed | ok | yes | listing 25 entries, article 200 | **working** | proposed |
| 2 | atlas_copco_usa_news | Atlas Copco USA news | competitor (client) | html | allowed (crawl-delay 1) | ok | yes | listing 7 links, article 200 | **working** | proposed |
| 3 | sullair_america_news | Sullair US news | competitor | html | allowed | ok | yes | listing 10 links, article 200 | **working** | proposed |
| 4 | kaeser_usa_blog | Kaeser USA blog | competitor | html | allowed | unknown | yes | listing 11 links, article 200 | **working** | proposed |
| 5 | doe_newsroom | US DOE newsroom | government | html | allowed | ok | yes | listing 14 links, article 200 | **working** | proposed |
| 6 | cagi_news | CAGI | trade_news | html | allowed | **forbids automation** | yes | not fetched (terms ban) | **blocked** | blocked |
| 7 | prnewswire_releases | PR Newswire | trade_news | html | allowed | **forbids automation** | yes | not fetched (terms ban) | **blocked** | blocked |
| 8 | plant_services_news | Plant Services | trade_news | rss | allowed | **forbids automation** | yes | not fetched (terms ban) | **blocked** | blocked |
| 9 | plant_engineering_news | Plant Engineering | trade_news | html | allowed (crawl-delay 10) | unknown | n/a | homepage HTTP 403 | **unreachable** | needs_permission |
| 10 | ingersoll_rand_news | Ingersoll Rand | competitor | html | unknown (HTTP 429) | unknown | n/a | robots and homepage HTTP 429 | **unreachable** | needs_permission |
| 11 | businesswire_releases | Business Wire | trade_news | html | disallow-all (HTTP 403) | unknown | n/a | robots and homepage HTTP 403 | **unreachable** | needs_permission |
| 12 | atlas_copco_group_press | Atlas Copco Group press releases | competitor (client) | html | allowed (crawl-delay 1) | ok | yes | homepage lists 4 recent releases | working, **reserve** | not in register |
| 13 | elgi_usa | ELGi US | competitor | rss | allowed | unknown | yes | feed 10 entries (mostly product pages) | working, **reserve** | not in register |

Rows 1-11 are in `config/sources.yaml`. Rows 12-13 are vetted and can be added by copying a row if Atlas Copco wants them.

## Proposed five and why

Mix of 3 competitor newsrooms, 1 trade news and 1 government page, as the spec asks.

- **Compressed Air Best Practices:** the only trade source we could use; has an RSS feed, current industry news (the newest entry is dated 28 Oct 2026), and is entirely about compressed air.
- **Atlas Copco USA:** the client's own newsroom; shows how they describe their news and which items they already know.
- **Sullair US:** a major US compressor brand (Hitachi Global Air Power) with a news section.
- **Kaeser USA:** a major compressor brand; its press-release page lists no individual releases, so we use its blog (educational and product content, `claim` by default). Terms status is `unknown`, flagged for Legal.
- **DOE newsroom:** government source; mostly general energy news, so the relevance filter will drop most items, which demonstrates the filter on a real feed. Optional by the spec.

## Details per candidate

### 1. Compressed Air Best Practices (airbestpractices_news)
- Checked on: 2026-10-29
- robots.txt: https://www.airbestpractices.com/robots.txt -> allowed for `*` (blocks only `/media/oembed`; separate rules exist for AI-training bots, not for our agent); crawl-delay: none
- Terms: https://www.airbestpractices.com/terms-conditions -> read in full (about 12,000 characters); no sentence on scraping, robots or automated access -> ok
- Feed/API: https://www.airbestpractices.com/rss.xml (25 entries, valid)
- Public, logged-out: yes
- Test fetch: RSS 200; one article (Atlas Copco Group expands U.S. operations, 28 Oct 2026) 200, about 51,000 characters of HTML, held in memory only
- Status: **working** — reason: RSS available, no restriction found

### 2. Atlas Copco USA (atlas_copco_usa_news)
- Checked on: 2026-10-29
- robots.txt: https://www.atlascopco.com/robots.txt -> allowed for `*` (restricts only some parts pages); crawl-delay: 1 s (we use at least 3 s)
- Terms: https://www.atlascopco.com/en-us/privacy-policy ("Legal & Privacy Notices") -> no sentence on automated access found -> ok
- Feed/API: none found (listing is an HTML page with paging)
- Public, logged-out: yes
- Test fetch: listing https://www.atlascopco.com/en-us/news/latest-news 200 (7 article links on page 1); one article 200
- Status: **working** — reason: HTML listing, no restriction found. Note: the client's own site, so its content is `claim`.

### 3. Sullair US (sullair_america_news)
- Checked on: 2026-10-29
- robots.txt: https://america.sullair.com/robots.txt -> allowed for `*` (blocks only `/media/oembed`); crawl-delay: none
- Terms: https://america.sullair.com/en/terms-and-conditions-use (same text as the global site) -> read in full (about 17,000 characters); no sentence on scraping, robots or automated access -> ok
- Feed/API: none found. The global site www.sullair.com has no news section; the US site does
- Public, logged-out: yes
- Test fetch: https://america.sullair.com/en/news 200 (10 article links); one article 200
- Status: **working**

### 4. Kaeser USA blog (kaeser_usa_blog)
- Checked on: 2026-10-29
- robots.txt: https://us.kaeser.com/robots.txt -> allowed for `*`; crawl-delay: none
- Terms: no terms-of-use page found; the footer has only "Legal notice" (https://us.kaeser.com/company-information.aspx, an imprint) and privacy pages. No sentence on automated access in the legal notice -> **unknown** (flag for Atlas Copco Legal)
- Feed/API: none found. https://us.kaeser.com/about-us/press/press-releases/ lists no individual release links in its HTML, so the "Kaeser Talks Shop" blog is used instead
- Public, logged-out: yes
- Test fetch: blog index 200 (11 post links after excluding category and year pages); one post 200
- Status: **working** — caveat: terms unknown; blog posts are mostly evergreen articles, so many may fail the 12-month "recent" check

### 5. US DOE newsroom (doe_newsroom)
- Checked on: 2026-10-29
- robots.txt: https://www.energy.gov/robots.txt -> allowed for `*` (blocks only `/media/oembed`); crawl-delay: none
- Terms: https://www.energy.gov/about-us/web-policies -> read in full; no sentence on automated access -> ok (US government site)
- Feed/API: none found for the newsroom
- Public, logged-out: yes
- Test fetch: https://www.energy.gov/newsroom 200 (14 article links); one article 200
- Status: **working** — caveat: general energy news, few items mention compressors

### 6. CAGI (cagi_news)
- Checked on: 2026-10-29
- robots.txt: https://www.cagi.org/robots.txt -> 200, no restrictions
- Terms: https://www.cagi.org/cagi-terms-of-use -> "use any data mining, robots, or similar automated data gathering and extraction tools to access the CAGI website" -> **forbids_automation**
- Feed/API: none found
- Public, logged-out: yes
- Test fetch: none beyond the homepage and terms page (the terms ban automated access)
- Status: **blocked** — reason: terms forbid automated access. Route: ask CAGI for written permission.

### 7. PR Newswire (prnewswire_releases)
- Checked on: 2026-10-29
- robots.txt: https://www.prnewswire.com/robots.txt -> 200, allowed for `*`
- Terms: https://www.prnewswire.com/terms-of-use/ -> "use any robot, spider, site search/retrieval application, or other manual or automatic device or process to access, search, download, retrieve" and a separate ban on scraping -> **forbids_automation**
- Feed/API: none for public use (paid distribution products exist)
- Public, logged-out: yes
- Test fetch: none beyond the homepage and terms page
- Status: **blocked** — reason: terms forbid scraping and robots. Route: a licensed feed, or take the same releases from each company's own newsroom.

### 8. Plant Services (plant_services_news)
- Checked on: 2026-10-29
- robots.txt: https://www.plantservices.com/robots.txt -> 200, allowed for `*`
- Terms: https://www.endeavorbusinessmedia.com/endeavor-terms (Endeavor Business Media, linked from the footer) -> "use robots, spiders, scripts, service, software or any manual or automatic device, tool, or process designed to data mine or scrape the Content" -> **forbids_automation**
- Feed/API: RSS exists (`__rss/website-scheduled-content.xml`), but the terms still apply to automated collection
- Public, logged-out: yes
- Test fetch: none beyond the homepage and terms page
- Status: **blocked** — reason: terms forbid automated collection even though a feed exists. Route: ask Endeavor for permission. (A first keyword pass over this page missed the clause because the page is very long; a second whole-page search found it.)

### 9. Plant Engineering (plant_engineering_news)
- Checked on: 2026-10-29
- robots.txt: https://www.plantengineering.com/robots.txt -> 200, `Crawl-delay: 10`, allowed for `*`
- Terms: not read (site blocked us first) -> unknown
- Feed/API: not checked
- Public, logged-out: could not confirm
- Test fetch: homepage returned **HTTP 403** to our identified agent. Not retried, no other agent tried
- Status: **unreachable** — reason: the site refuses our agent. Register status `needs_permission`: ask the publisher.

### 10. Ingersoll Rand (ingersoll_rand_news)
- Checked on: 2026-10-29
- robots.txt: https://www.irco.com/robots.txt -> **HTTP 429** (too many requests) on the first request
- Terms: not read -> unknown
- Feed/API: not checked
- Public, logged-out: could not confirm
- Test fetch: homepage also **HTTP 429** on the first request. Not retried
- Status: **unreachable** — reason: the site rate-limits or blocks our agent before any content. Register status `needs_permission`: ask Ingersoll Rand, or use a licensed feed.

### 11. Business Wire (businesswire_releases)
- Checked on: 2026-10-29
- robots.txt: https://www.businesswire.com/robots.txt -> **HTTP 403** (a 403 on robots.txt is treated as disallow-all)
- Terms: not read -> unknown
- Feed/API: not checked
- Public, logged-out: could not confirm
- Test fetch: homepage **HTTP 403**
- Status: **unreachable** — reason: refuses our agent. Register status `needs_permission`.

### 12. Atlas Copco Group press releases (atlas_copco_group_press) — reserve, not in register
- Checked on: 2026-10-29
- robots.txt: https://www.atlascopcogroup.com/robots.txt -> allowed for `*`; crawl-delay: 1 s
- Terms: https://www.atlascopcogroup.com/en/privacy ("Legal and Privacy Notices") -> no sentence on automated access -> ok
- Feed/API: none found. The press-release list page builds its list with scripts (no article links in the page HTML); only the 4 most recent releases are linked from the homepage
- Public, logged-out: yes
- Test fetch: pages 200
- Status: **working (limited)** — held in reserve: the group site is global, mostly financial releases, and only a few recent ones are reachable without scripts.

### 13. ELGi US (elgi_usa) — reserve, not in register
- Checked on: 2026-10-29
- robots.txt: https://www.elgi.com/robots.txt -> allowed for `*` (a 300 s crawl-delay applies to one other named bot only)
- Terms: no terms-of-use page found (privacy policy only) -> unknown
- Feed/API: https://www.elgi.com/us/feed/ (10 entries; mostly product pages, newest 28 Oct 2026, others 2024-2025)
- Public, logged-out: yes
- Test fetch: feed 200
- Status: **working (limited)** — held in reserve: the feed carries product pages, not news.

Also looked at and dropped before full vetting: Quincy Compressor (www.quincycompressor.com; robots allow, but no news listing on the homepage).

## Findings for the meeting

- **Blocked by their own terms:** CAGI, PR Newswire, Plant Services (Endeavor). These need written permission or a licensed feed.
- **Refuse our agent without stating a ban (HTTP 403 / 429):** Plant Engineering, Ingersoll Rand, Business Wire. We did not retry or change our agent. These need a conversation with the owners (or Atlas Copco's own access).
- **Ingersoll Rand is Atlas Copco's largest US competitor and is not reachable;** worth raising with Atlas Copco: do they have a data licence or a preferred route?
- **Open for Atlas Copco Legal:** Kaeser's terms (`unknown`), and the whole list before go-live.
