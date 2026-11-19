# Scraping tools: DuckDuckGo, Agentic Scraper (ScrapeGraphAI) and Firecrawl

Task 4 of phase 3. The question: which tool should Market Scout use to discover websites and to read them?
Checked against the rules we already work under (parent2.md): public pages only, robots.txt and terms read
before any fetch, refused sites never worked around, no page text stored, and nothing the team cannot explain.

## Summary

| | DuckDuckGo (ddgs library) | Agentic Scraper (ScrapeGraphAI) | Firecrawl |
|---|---|---|---|
| What it is | A Python library that loads DuckDuckGo's search pages and parses them | An LLM-driven scraper: you describe what you want and a graph of fetch, parse and LLM steps extracts it | A hosted web-data API (search, scrape, crawl, map), also open source (AGPL-3.0) to self-host |
| Official API with a contract | No. DuckDuckGo's only official API is the Instant Answer API, which returns no web results | Yes for their cloud API; the library is open source | Yes, keyed REST API (`/v2/search`, `/v2/scrape` ...) |
| Discovery (finding new sites) | Works, but by scraping a search engine's result pages | Has a search graph, built on a search provider | `/v2/search` returns url, title, description; scraping the results is optional |
| Reading pages | Not a reader | Yes, with an LLM on every page | Yes (markdown), with optional anti-bot proxies |
| Fits our compliance rules | No: result-page scraping is what parent2 s.17 rules out, and the library itself says it is not for commercial use | Only if it runs behind our gate; LLM output must be validated | Yes for search results only; its stealth proxy mode must stay off |
| Reliability | Frequent "202 Ratelimit" soft blocks, and the package was renamed in 2025, breaking old pins | Output can change between runs; slower and costlier per page | Managed service; pay per credit; free tier to start |
| Cost | Free | LLM tokens per page, plus their API credits | Credits per request; free tier, then monthly plans |
| Explainability | Fine | Low: an LLM decides what to extract | Fine for search; scraping hides which proxy was used |

## Recommendation (implemented)

1. **Discovery: Firecrawl search, results only.** `atlas/scout/search_provider.py` calls `POST /v2/search`
   with just a query and a limit. No `scrapeOptions` and no proxy settings, so Firecrawl only returns links.
   Every link becomes a candidate that our own Compliance Gate and vetter check (robots.txt, terms page,
   3 s delay) before a single page is read. It is off by default: set `search_api_enabled: true` in the
   settings and `FIRECRAWL_API_KEY` in `.env`.
2. **Reading pages: keep our own collector.** It already respects robots.txt, follows redirects by hand,
   stops on 429/503 and keeps pages in memory only. Firecrawl's scrape endpoint adds nothing we need for
   allowed pages, and its `auto` proxy mode escalates to stealth proxies when a site blocks, which is the
   opposite of our rule. We do not use it for reading.
3. **DuckDuckGo: not used.** There is no official web-search API, the library scrapes result pages, and it is
   marked "educational purposes only, not for commercial use". It would also break the existing test that
   checks no search-engine address appears in the discovery code.
4. **Agentic Scraper: not in the pipeline yet.** Worth testing offline on pages we are already allowed to read
   (for example to compare its company and event tags with our rules on the hand-check set), but its output
   must pass `atlas/validate.py` like anything else. See `docs/research_blocked_sites_and_agents.md`, part 2.

## How to try the Firecrawl search

```bash
# .env
FIRECRAWL_API_KEY=fc-...

# settings: Filters page cannot set this yet, so use the saved settings or config/scout_settings.yaml
discovery_enabled: true
search_api_enabled: true

python -m atlas.run --max-items 3
```

The run log shows one line per query (`search_api: '...' gave N result(s)`). New sites appear on the Sources
page as "found by the scout" and still need a team decision.

## Sources

- [DuckDuckGo API: what it returns and what to use instead (cloro.dev)](https://cloro.dev/blog/duckduckgo-api/)
- [duckduckgo-search on PyPI (disclaimer and rate-limit exception)](https://pypi.org/project/duckduckgo-search/6.1.6)
- [Rate-limit reports with the library (Agno community)](https://community.agno.com/t/duckduckgo-search-rate-limit-issue/1021)
- [Firecrawl search endpoint (v2)](https://docs.firecrawl.dev/features/search.md)
- [Firecrawl stealth / proxy modes](https://docs.firecrawl.dev/features/stealth-mode)
- [Firecrawl guide: self-hosting, pricing and limits (webscraping.ai)](https://webscraping.ai/blog/firecrawl-guide)
- [What is agentic scraping (ScrapeGraphAI)](https://scrapegraphai.com/glossary/ai-scraping/agentic-scraping)
- [ScrapeGraphAI library overview](https://blog.brightcoding.dev/2025/07/31/scrapegraphai-the-you-only-scrape-once-python-library-powered-by-llms)
