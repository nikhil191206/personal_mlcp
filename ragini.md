# ragini.md — Input: sources, compliance, collection

**Person:** Ragini. **Read `parent.md` first**, fully. This file is your task spec and the prompt kit for your AI.

## How to use this file with your AI

Give your AI, in this order: (1) all of `parent.md`, (2) all of this file, (3) `atlas/models.py` and `atlas/settings.py`, (4) the kickoff prompt below. Demand the output format from `parent.md` section 14 (complete files, exact paths, exact signatures, tests, commands, listed assumptions).

### Kickoff prompt (paste as-is)

> You are helping me build the input side of a scraping pipeline for an industrial-compressor market scout: a source register, a Compliance Gate and a polite collector. I have pasted the master brief (`parent.md`), my task file, and the shared code (`models.py`, `settings.py`). Implement `atlas/compliance.py`, `atlas/collect.py`, `tests/test_compliance.py` and `tests/test_collect.py` exactly as specified in my task file, using the exact class and function signatures from `parent.md` section 8 and the models in `atlas/models.py` (import them, never redefine). Return each file in full under a heading with its repo path. Never write data files to local disk. Never add any way around a block (no header spoofing, no proxies, no retries to dodge limits). If anything fails, record it as a `Refusal`; do not fall back. Tests must run offline with `pytest` using `httpx.MockTransport`. List every assumption at the end. If a requirement is ambiguous, ask me instead of choosing.

For the **vetting work** (Task R1) the AI cannot browse for you unless it has a browser. You open the sites yourself, read the pages, and give the AI the facts; the AI helps structure the table and the YAML. Do not let the AI invent robots.txt or terms content from memory: every entry must come from what you or your code actually saw today.

---

## Your files

| File | What |
|---|---|
| `config/sources.yaml` | the source register (format in `parent.md` section 9) |
| `docs/source_vetting.md` | the vetting table and notes (format below) |
| `atlas/compliance.py` | Compliance Gate |
| `atlas/collect.py` | Collector |
| `tests/test_compliance.py`, `tests/test_collect.py` | tests |

## Task R0 — Setup (first)

Follow `parent.md` section 12. `python -m atlas.storage_check` must print PASS with `ATLAS_PATH_PREFIX=dev/ragini`. Ask the team for `CONTACT_EMAIL` and put it in your `.env`. You need it for live fetches.

## Task R1 — Vet the sources (Thu, first)

Goal: vet **at least 8 candidates**, with **at least 5 `working`**. Candidates are listed in `parent.md` section 11 (Ingersoll Rand, Kaeser USA, Sullair, Atlas Copco USA, Compressed Air Best Practices, Plant Engineering/Services, PR Newswire/Business Wire company releases, CAGI, US DOE). You may add others if they are strong (for example another US compressor maker's newsroom).

For **each** candidate:

1. **robots.txt.** Open `<site>/robots.txt` in the browser (or fetch it in memory with the snippet below). Is the target path (news/press section) allowed for our agent `AtlasCopcoStudentPoC`? Note any `Crawl-delay`. Record `robots_status`.
2. **Terms of use.** Open the site's Terms / Legal page. Find any sentence about automated access, scraping, robots, crawling, data mining. Copy a **short quote** (under 25 words) into the vetting note, with the URL of the terms page. If nothing mentions it, say "no automation clause found". Record `terms_status`: `ok` (no ban), `forbids_automation` (ban stated), `unknown` (could not find/read terms).
3. **RSS / API.** Look for an RSS feed (`/feed`, `/rss`, a feed icon, `<link rel="alternate" type="application/rss+xml">`) or an official API. Prefer these over HTML scraping. Record `access_method` and `feed_url`.
4. **Public and logged-out?** Open the page in a private window. Paywalled or login pages are excluded.
5. **One test fetch.** Fetch **one** listing page (RSS or news list) and **one** article page, politely, with the real User-Agent (use the snippet). Do not crawl anything else.
6. **Assign `vetting_status`:** `working` (allowed and usable), `blocked` (robots or terms say no), `needs_permission` (terms ask for written permission or require an agreement), `unreachable` (site down, blocks us with 403/429 **without** a robots/terms ban, or times out). **Never work around a block**: a 403 is recorded, not bypassed.
7. Fill `status: proposed` for every candidate that is `working`, `needs_permission` for those needing it, `blocked` for blocked ones. (Nothing is `approved`; only Atlas Copco can approve.)

In-memory snippet for robots.txt and a single test fetch (run it in a Python shell; it prints, it does not save):

```python
import httpx
from urllib.robotparser import RobotFileParser
UA = "AtlasCopcoStudentPoC/0.1 (+contact: <team email>)"
base = "https://example.com"
txt = httpx.get(base + "/robots.txt", headers={"User-Agent": UA}, timeout=20, follow_redirects=True)
print(txt.status_code); print(txt.text[:2000])
rp = RobotFileParser(); rp.parse(txt.text.splitlines())
print("can fetch news:", rp.can_fetch("AtlasCopcoStudentPoC", base + "/news"))
print("crawl delay:", rp.crawl_delay("AtlasCopcoStudentPoC"))
```

### `docs/source_vetting.md` format

A summary table, then one block per candidate.

```markdown
| # | source_id | name | type | access | robots | terms | public | test fetch | vetting_status |
|---|---|---|---|---|---|---|---|---|---|

### 1. <name> (<source_id>)
- Checked on: 2026-10-29
- robots.txt: <URL> -> <allowed/disallowed/unknown>, crawl-delay: <n or none>
- Terms: <URL> -> "<short quote, under 25 words>" -> <ok / forbids_automation / unknown>
- Feed/API: <URL or none>
- Public, logged-out: <yes/no>
- Test fetch: <what you fetched, HTTP status, worked yes/no>
- Status: <working | blocked | needs_permission | unreachable> — reason: <one line>
```

### `config/sources.yaml`

One entry per vetted candidate (blocked ones too). Format exactly as `parent.md` section 9. `source_id` snake_case and stable (e.g. `ingersoll_rand_news`). For `html` sources, give `item_url_pattern` (a regex matching article URLs on the list page, e.g. `^https://www\.example\.com/news/[a-z0-9-]+/?$`). `review_date: 2026-10-29`. `region: US`. Validate it: every entry must load as `Source` (`Source.model_validate(entry)`). Push a **first version by Thu 18:00** even if some statuses are provisional; update as you finish. After vetting, show the table to the team and ask which 5 to keep; mark the 5 chosen in the table (the others stay in the register with their status).

## Task R2 — `atlas/compliance.py`

Signatures exactly as in `parent.md` section 8.

```python
USER_AGENT_TEMPLATE = "AtlasCopcoStudentPoC/0.1 (+contact: {email})"
def load_register(path: str = "config/sources.yaml") -> list[Source]: ...
class ComplianceGate: ...
```

Requirements:

- `load_register`: read the YAML (`yaml.safe_load`), validate each entry as `Source`. A malformed entry raises with the entry's `source_id` in the message (do not skip silently).
- `ComplianceGate.__init__(sources, client=None, min_delay=3.0)`: builds `user_agent` from `get_settings().contact_email`. **If the email is empty, raise `RuntimeError("CONTACT_EMAIL is not set in .env")`**: no default email. Creates an `httpx.Client` with headers `{"User-Agent": user_agent}`, `timeout=20`, `follow_redirects=False` unless injected. Keeps `refusals` and `decisions` lists.
- `check_source(source) -> GateDecision`: run at the **start of every run**. Reasons it refuses (all collected, not just the first): `status_blocked` (status is `blocked` or `needs_permission`), `vetting_<status>` (vetting_status != `working`), `terms_forbid_automation`, `robots_disallow_listing` (listing URL or feed URL not allowed by robots.txt), `robots_unreachable` (robots.txt fetch failed with 5xx or network error). On refusal, also append a `Refusal` to `self.refusals`. Allowed only if status in {`proposed`, `approved`} **and** `vetting_status == "working"` **and** `terms_status != "forbids_automation"` **and** robots allow the listing URL. Append the decision to `self.decisions`.
- **robots.txt handling:** fetch `scheme://host/robots.txt` yourself with our User-Agent (not `RobotFileParser.read()`, which uses its own UA), then `rp.parse(text.splitlines())`. Rules: HTTP 200 → parse; 404/410 → no restrictions (allow); 401/403 → treat as **disallow all**; 5xx/network error → treat as **disallow** and reason `robots_unreachable`. Cache the parser per host **for this run only, in memory**. Read `Crawl-delay` via `rp.crawl_delay(agent)`; use `agent = "AtlasCopcoStudentPoC"`.
- `can_fetch(source, url) -> tuple[bool, str]`: re-checks the cached robots for the URL's host (fetch robots for a new host first). Returns `(False, "robots_disallow")` or `(True, "ok")`. Appends a `Refusal` on refusal.
- `wait(source)`: per-host politeness. Delay = `max(self.min_delay, crawl_delay_from_robots or 0, source.crawl_delay or 0)` seconds since the last request to that host (use `time.monotonic()` and `time.sleep`). Never fewer than `min_delay`. Make sleeping injectable or patchable so tests run fast.
- Never log page content. Refusal `reason` strings are short codes.

### `tests/test_compliance.py` (at minimum, offline with `httpx.MockTransport`)

1. Register loads; a malformed entry raises with its `source_id`.
2. Empty `CONTACT_EMAIL` → `RuntimeError`.
3. `proposed` + `working` + robots allow → allowed.
4. Each refusal reason: blocked status, vetting_status `blocked`/`unreachable`, `forbids_automation`, robots `Disallow: /`, robots 403 (disallow all), robots 500 (`robots_unreachable`).
5. robots 404 → allowed.
6. `Crawl-delay: 10` → `wait` enforces at least 10 s (patch sleep/monotonic and assert the requested sleep).
7. `min_delay` of 3 s is the floor.
8. User-Agent header is sent on the robots request.
9. Refusals are recorded in `gate.refusals`.

## Task R3 — `atlas/collect.py`

```python
def collect_source(source: Source, gate: ComplianceGate, max_items: int = 20,
                   client: httpx.Client | None = None) -> CollectResult: ...
```

Requirements:

- Use `client` if given, else `gate.client` (the gate's client with the correct User-Agent). Every request is preceded by `gate.can_fetch(source, url)` and `gate.wait(source)`.
- **RSS first** (`access_method == "rss"`): fetch `feed_url` as bytes via httpx, then `feedparser.parse(content)` (so our User-Agent is used). For each entry take: link, title → `listing_title`, `published` (raw string) → `listing_published`. **Do not use the feed's summary/content for the main text**; always fetch the article page. Candidates = entry links, same host as the source URL (or `www.` variant), de-duplicated, first `max_items`.
- **HTML list page** (`access_method == "html"`): fetch `source.url`, parse with `lxml.html`, collect `<a href>`s (resolve relative to the page URL), keep those matching `source.item_url_pattern` (regex), same host, de-duplicated, first `max_items`. If `item_url_pattern` is missing, return a `Refusal(reason="no_item_url_pattern")` and an empty result (do not guess links).
- **API** (`access_method == "api"`): implement only if one chosen source uses it; otherwise raise `NotImplementedError("api access not used in the Friday PoC")` and make sure no chosen source uses it.
- `listing_count` = number of candidate URLs found before the `max_items` cut.
- For each candidate: gate check → wait → `GET` with `follow_redirects=True` but **verify the final host** is the same host (or same registered domain) as the source; if it redirected elsewhere, drop it with `Refusal(reason="redirect_off_host")`. Re-check robots for the final URL if the host changed.
- Accept only status 200 and content type containing `html` (or `xml` for feeds). Anything else → `Refusal(reason=f"http_{status}")` or `Refusal(reason="not_html")`. Cap response size (e.g. 3 MB): larger → `Refusal(reason="too_large")`.
- Timeouts and network errors → `Refusal(reason="fetch_error:<ExceptionClass>")`. **No retries to dodge limits.** On HTTP 429 or 503: stop collecting from this source immediately and add `Refusal(reason="rate_limited_stop")`; do not continue.
- Build `FetchedPage(source_id, url=candidate, final_url=response.url, status_code, html=response.text, fetched_at=utc_now_iso(), listing_title, listing_published, via=source.access_method)`. `html` stays in memory.
- Return `CollectResult(source_id, pages, refusals = gate refusals added during this call + local ones, listing_count)`.
- Never write anything to disk. Never log page text.

### `tests/test_collect.py` (at minimum, offline)

Use synthetic RSS XML and synthetic HTML written in the test (invented headlines).
1. RSS source: feed with 3 entries → 3 `FetchedPage`s with `listing_title`/`listing_published` set, `via == "rss"`.
2. HTML source: list page with matching and non-matching links → only matching ones fetched; relative links resolved.
3. `max_items` limit respected; `listing_count` reports the pre-cut number.
4. A link to another host is skipped. A redirect to another host → `redirect_off_host`.
5. robots disallow on one article → that URL refused, others collected.
6. 404/500 on an article → `http_404`/`http_500` refusal, others continue.
7. 429 → collection stops with `rate_limited_stop`.
8. HTML source with no `item_url_pattern` → refusal, no guessing.
9. `FetchedPage.model_dump()` has no `html` key.
10. No file is written (assert nothing new in the working dir or use `tmp_path` cwd).

## Task R4 — Live check (Thu night; under `dev/ragini`)

With your real `.env` and email:
```python
from atlas.compliance import load_register, ComplianceGate
from atlas.collect import collect_source
srcs = load_register(); gate = ComplianceGate(srcs)
for s in srcs:
    d = gate.check_source(s); print(s.source_id, d.allowed, d.reasons)
allowed = {d.source_id for d in gate.decisions if d.allowed}
s = next(x for x in srcs if x.source_id in allowed)   # first source the gate let through
r = collect_source(s, gate, max_items=3)
print(len(r.pages), r.listing_count, [x.model_dump() for x in r.refusals])
print([ (p.final_url, p.status_code, len(p.html)) for p in r.pages])   # prints only metadata and lengths
```
Report the printed result to the team (format: `parent.md` section 20). Then tell Nikhil the `source_id`s he can run with `python -m atlas.run --only <id>`.

## Task R5 — Friday morning

- Be available on the full run at 07:30: if a source starts blocking or changes its structure, record it (never bypass), update `sources.yaml` and `docs/source_vetting.md`, and tell Nikhil.
- Prepare to present: which candidates were vetted, which 5 are proposed and why, and **which were blocked and why** (that is a finding for Atlas Copco).

## Acceptance criteria (yours)

- [ ] `docs/source_vetting.md` and `config/sources.yaml` list at least 8 candidates, with at least 5 `working`; every entry has robots, terms (with quote), feed/API, public and test-fetch notes.
- [ ] `config/sources.yaml` loads cleanly via `load_register()`.
- [ ] `pytest tests/test_compliance.py tests/test_collect.py -q` passes offline.
- [ ] Live check printed results for at least one real source.
- [ ] robots.txt is checked on every run and before every fetch; delay is at least 3 s (or the site's Crawl-delay if larger).
- [ ] No page content or data is saved locally.

## Do not

- Do not bypass any block (headers, proxies, user-agent tricks, retry loops).
- Do not take robots/terms information from the AI's memory; use what you saw today.
- Do not fetch more than one listing page and one article per source during vetting.
- Do not mark anything `approved`.
- Do not edit `models.py`; ask Nikhil.
