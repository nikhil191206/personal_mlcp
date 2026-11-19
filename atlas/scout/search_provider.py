"""Official search API for source discovery (phase 3, task 4): Firecrawl /v2/search, results only.

Owner: Ragini (discovery) / Sachi (phase 3). Chosen after docs/scraping_tools_evaluation.md:
- an official, keyed API with a contract (DuckDuckGo has no official web-search API; scraping its result
  pages is what the team ruled out in parent2 section 17);
- we ask for search RESULTS ONLY (url, title, description). We never ask Firecrawl to scrape the pages and
  never use its stealth proxies: every result is a candidate that our own Compliance Gate and vetter
  (robots.txt, terms, 3 s delay) check before a single page is read.

Off by default. Needs ScoutSettings.search_api_enabled = true and FIRECRAWL_API_KEY in .env.
"""
from __future__ import annotations

import os
from typing import Optional
from urllib.parse import urlsplit

import httpx

from atlas.models import Candidate, ScoutSettings

FIRECRAWL_SEARCH_URL = "https://api.firecrawl.dev/v2/search"
RESULTS_PER_QUERY = 10
MAX_QUERIES = 6
BASE_QUERIES = [
    "industrial air compressor news United States",
    "compressed air industry news",
]


def api_key() -> Optional[str]:
    """FIRECRAWL_API_KEY from the environment or .env (never printed or logged)."""
    if os.environ.get("FIRECRAWL_API_KEY"):
        return os.environ["FIRECRAWL_API_KEY"]
    try:
        from atlas.settings import get_settings
        secret = get_settings().firecrawl_api_key
    except Exception:  # no .env in tests
        return None
    return secret.get_secret_value() if secret else None


def queries(settings: ScoutSettings) -> list[str]:
    """Plain queries built from the settings: the watched companies, then the selected technologies."""
    out: list[str] = []
    for entry in settings.watchlist:
        if entry.kind == "company":
            out.append(f'"{entry.name}" compressor news')
    for tech in settings.technologies:
        out.append(f"{tech} news")
    out += BASE_QUERIES
    return list(dict.fromkeys(out))[:MAX_QUERIES]


def firecrawl_search(query: str, key: str, limit: int = RESULTS_PER_QUERY,
                     client: Optional[httpx.Client] = None) -> list[dict]:
    """[{url, title, description}] for one query. Results only: no scrapeOptions, no proxy settings."""
    own = client is None
    client = client or httpx.Client(timeout=30)
    try:
        resp = client.post(FIRECRAWL_SEARCH_URL, json={"query": query, "limit": limit},
                           headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
        resp.raise_for_status()
        data = resp.json().get("data") or {}
        web = data.get("web") if isinstance(data, dict) else data  # v2: data.web; v1: data
        return [{"url": r.get("url"), "title": r.get("title"), "description": r.get("description")}
                for r in (web or []) if isinstance(r, dict) and r.get("url")]
    finally:
        if own:
            client.close()


def search_candidates(settings: ScoutSettings, client: Optional[httpx.Client] = None) -> tuple[list[Candidate], list[str]]:
    """(candidates, notes). One candidate per new registered domain; each is vetted later like any other."""
    from atlas.scout.discover import _region_for_domain, _skipped_domain, _type_for_link, make_candidate_id, registered_domain

    key = api_key()
    if not key:
        return [], ["search_api: FIRECRAWL_API_KEY is not set"]
    found: dict[str, Candidate] = {}
    notes: list[str] = []
    for q in queries(settings):
        try:
            results = firecrawl_search(q, key, client=client)
        except (httpx.HTTPError, ValueError) as exc:
            notes.append(f"search_api: query {q!r} failed: {type(exc).__name__}")
            continue
        for r in results:
            parts = urlsplit(r["url"])
            if parts.scheme not in ("http", "https") or not parts.hostname:
                continue
            domain = registered_domain(parts.hostname)
            if domain in found or _skipped_domain(domain):
                continue
            found[domain] = Candidate(
                candidate_id=make_candidate_id(domain), name=(r.get("title") or domain)[:120],
                url=f"{parts.scheme}://{parts.netloc}/", domain=domain, type_guess=_type_for_link(domain),
                region=_region_for_domain(domain), discovered_via="search_api", discovered_from=f"firecrawl: {q}",
                access_method="html", notes=f"found by the search API for {q!r}; not yet vetted",
            )
        notes.append(f"search_api: {q!r} gave {len(results)} result(s)")
    return list(found.values()), notes
