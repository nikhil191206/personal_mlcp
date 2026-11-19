"""Phase 3 task 4: the official Firecrawl search API (results only) for discovery. Offline (MockTransport)."""
import json
import logging

import httpx

from atlas.models import ScoutSettings, WatchEntry
from atlas.scout import search_provider
from atlas.scout.discover import _search_api_candidates


def client_with(results: list[dict], seen: list[dict]):
    def handler(request: httpx.Request) -> httpx.Response:
        seen.append({"url": str(request.url), "body": json.loads(request.content), "auth": request.headers.get("authorization")})
        return httpx.Response(200, json={"success": True, "data": {"web": results}})
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_queries_come_from_the_watchlist_and_technologies():
    s = ScoutSettings(watchlist=[WatchEntry(name="Kaeser Compressors")], technologies=["vacuum pump"])
    q = search_provider.queries(s)
    assert q[0] == '"Kaeser Compressors" compressor news' and "vacuum pump news" in q
    assert len(q) <= search_provider.MAX_QUERIES


def test_results_only_request_and_parsing():
    seen: list[dict] = []
    client = client_with([{"url": "https://news.example/a", "title": "A", "description": "d"}], seen)
    out = search_provider.firecrawl_search("air compressor news", "fc-test", client=client)
    assert out == [{"url": "https://news.example/a", "title": "A", "description": "d"}]
    assert seen[0]["url"] == search_provider.FIRECRAWL_SEARCH_URL
    assert seen[0]["body"] == {"query": "air compressor news", "limit": 10}  # no scrapeOptions, no proxy
    assert seen[0]["auth"] == "Bearer fc-test"


def test_candidates_one_per_domain_and_social_sites_skipped(monkeypatch):
    monkeypatch.setenv("FIRECRAWL_API_KEY", "fc-test")
    seen: list[dict] = []
    client = client_with([{"url": "https://www.news.example/a", "title": "News"},
                          {"url": "https://news.example/b", "title": "News again"},
                          {"url": "https://www.linkedin.com/x", "title": "Social"}], seen)
    cands, notes = search_provider.search_candidates(ScoutSettings(), client=client)
    assert [c.domain for c in cands] == ["news.example"]
    assert cands[0].discovered_via == "search_api" and cands[0].url == "https://www.news.example/"
    assert notes


def test_discovery_uses_it_only_when_enabled_and_keyed(monkeypatch, caplog):
    monkeypatch.delenv("FIRECRAWL_API_KEY", raising=False)
    monkeypatch.setattr(search_provider, "api_key", lambda: None)
    with caplog.at_level(logging.INFO, logger="atlas.scout.discover"):
        assert _search_api_candidates(ScoutSettings(search_api_enabled=True)) == []
    assert any("FIRECRAWL_API_KEY is not set" in r.getMessage() for r in caplog.records)
