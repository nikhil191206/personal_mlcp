# Scout phase 3: what changed

All 10 tasks from the Scout task breakdown are covered. Tasks 5 and 9 are research only, with no code
changes. The test suite grew from 461 to 508 tests, all passing, and the website builds.

## Built

**1. Backend architecture.** `docs/architecture.md` has a component diagram, an end-to-end sequence diagram
of one run, a stage table (inputs, outputs, key rule) and a map of where each task lives. PNG copies for
slides: `docs/images/architecture_components.png` and `docs/images/architecture_workflow.png`.

**2. Company discovery.** New `atlas/company.py`. When a page is not on a competitor's newsroom and no known
company is named, it now finds the company from a stock ticker, the "About ..." press-release section,
schema.org data (never the publisher), the headline subject, or repeated organisation names. Each item
records how the company was found, a confidence (high, medium, low) and the phrase that named it. Two
companies with equal support give no company rather than a guess.

**3. Content extraction.** In `atlas/extract.py` and the new `atlas/htmlmeta.py`:
- a second Trafilatura pass (recall mode, tables kept) when the first pass gives too little text;
- title fallbacks (og:title, then h1) and a schema.org date fallback, still never the fetch date;
- new fields: up to 5 page headings, the page's meta description as a summary, and the og:image link,
  all scrubbed of personal data.

**4. Scraping tools.** `docs/scraping_tools_evaluation.md` compares DuckDuckGo, the ScrapeGraphAI agentic
scraper and Firecrawl. Decision: Firecrawl's official search API for discovery, results only, behind our own
gate (`atlas/scout/search_provider.py`, off by default); our own collector stays the page reader;
DuckDuckGo is not used because it has no official web-search API.

**6. Company-wise classification.** New `atlas/companies.py` groups each run's items by company, with
counts by type of news, technology and region, products, dates, sources and stories. Items with no company
are listed as unattributed. Every run now writes `companies/<run>/index.json`. The website has a new
Companies page.

**7. Validation.** New `atlas/validate.py`. Every item is Confirmed or Not confirmed:
- C1, the story was reported by 2 or more independent websites;
- C2, a government source or a trade-news report of a hard event, with its own date;
- C3, the team marked it Important.
A weak company match or a "Not important" mark always blocks confirmation. Each item keeps its evidence
links. Contacts are confirmed when they come from the company's own site, in schema.org data or on 2 pages.

**8. Contacts and images.** New `atlas/profile.py` reads each company's own homepage and up to 3
contact / about pages through the Compliance Gate. It keeps role emails only (info@, sales@ ...) on the
company's domain, phone numbers (not fax), addresses, the logo (copied to the Volume) and image links.
Personal emails are counted and dropped. Sites the register refuses are not read.

**10. Company reports.** New `atlas/report/company_report.py` builds one PDF and/or PowerPoint per company.
Page 1 follows Atlas Copco's market-intelligence format (`atlas/report/company_sheet.py`): company name,
logo top right, and six teal-labelled boxes (business and ownership, products/markets/finances,
technology description, technology assessment, value for Atlas Copco, links). Gaps are written as "not
stated in the collected sources (to complete)", unconfirmed facts carry a `*`, and every fact links to its
source. The pages after it are the evidence: contacts with status, news with each item's validation,
images, sources and the rules. Run `python -m atlas.companies --fetch-profiles --reports both`, or use the buttons on the
Companies page.

## Researched only (no code changes)

**5. Blocked websites** and **9. Agentic approach**: `docs/research_blocked_sites_and_agents.md`.
In short:
- Blocked sites: classify each refusal (owner refused, bot wall, rate limited, technical, gated), then use
  allowed routes only: official APIs (SEC EDGAR for listed companies, GDELT for news mentions), coverage
  from other sources, a permission request, a slower retry, and a monthly re-check. No stealth proxies,
  CAPTCHA solving or archives.
- Agents: keep the rule-based pipeline as the backbone and add small, optional LLM steps only where rules
  are weak (company or event type at low confidence, discovery query planning, the "why it matters" line).
  Everything stays behind the gate and validation, with the team's review on top. The team must first agree,
  because the project currently says "rule-based, no AI".

## Changed files

- New: `atlas/company.py`, `atlas/htmlmeta.py`, `atlas/validate.py`, `atlas/companies.py`,
  `atlas/profile.py`, `atlas/report/company_report.py`, `atlas/report/company_sheet.py`, `atlas/scout/search_provider.py`,
  `config/companies.yaml`, `web/src/pages/Companies.jsx`, 7 test files, 5 docs and 2 diagram images.
- Edited: `atlas/models.py` (new optional fields and models, so old outputs still load), `atlas/extract.py`,
  `atlas/run.py` (validation and company index at the end of a run), `atlas/scout/discover.py`,
  `atlas/settings.py`, `atlas/storage.py`, `atlas/report/build.py` (image links are not mistaken for emails),
  `web/api/server.py` (two new routes), the website menu, `README.md` and `.env.example`.

## Things to tell the team

- `atlas/models.py` is Nikhil's contract file. Only optional fields were added, but he should review them.
- Contact extraction is new personal-data territory. It keeps only role mailboxes and main numbers, but the
  team should agree that this is acceptable before a demo run.
- Run the company profiles with `ATLAS_PATH_PREFIX=dev/<name>` first, not on the demo folders.
