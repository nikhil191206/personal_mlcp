from datetime import date

import httpx

from atlas.collect import MAX_BYTES, collect_source
from atlas.compliance import ComplianceGate
from atlas.models import Source

BASE = "https://acme.example"
HTML_HEADERS = {"content-type": "text/html; charset=utf-8"}

FEED = """<?xml version="1.0"?><rss version="2.0"><channel><title>Acme</title>
<item><title>Acme launches oil-free unit</title><link>https://acme.example/news/one</link>
<pubDate>Mon, 05 Oct 2026 09:00:00 GMT</pubDate></item>
<item><title>Acme opens Texas plant</title><link>https://acme.example/news/two</link>
<pubDate>Tue, 06 Oct 2026 09:00:00 GMT</pubDate></item>
<item><title>Acme news three</title><link>https://www.acme.example/news/three</link></item>
<item><title>Off site</title><link>https://other.example/news/x</link></item>
</channel></rss>"""

LIST_PAGE = """<html><body>
<a href="/news/alpha">Alpha story</a>
<a href="https://acme.example/news/beta#top">Beta story</a>
<a href="/news/alpha">Alpha again</a>
<a href="/about">About</a>
<a href="https://other.example/news/gamma">Elsewhere</a>
</body></html>"""

ARTICLE = "<html><head><title>Story</title></head><body><p>Invented text about a compressor.</p></body></html>"


def make_source(**kw) -> Source:
    base = dict(
        source_id="acme_news", name="Acme Newsroom", url=f"{BASE}/news", type="competitor",
        access_method="rss", feed_url=f"{BASE}/news/rss", robots_status="allowed", terms_status="ok",
        vetting_status="working", status="proposed", review_date=date(2026, 10, 29),
    )
    base.update(kw)
    return Source(**base)


def build(routes: dict, robots="User-agent: *\nAllow: /\n", source=None):
    """routes: path -> httpx.Response (or callable). Returns (source, gate, requested_paths)."""
    requested: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested.append(request.url.path)
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text=robots)
        route = routes.get(request.url.path)
        if route is None:
            return httpx.Response(404, text="nope")
        return route(request) if callable(route) else route

    client = httpx.Client(transport=httpx.MockTransport(handler))
    src = source or make_source()
    gate = ComplianceGate([src], client=client, min_delay=0, contact_email="team@example.com")
    gate._sleep = lambda s: None
    return src, gate, requested


def feed_response() -> httpx.Response:
    return httpx.Response(200, text=FEED, headers={"content-type": "application/rss+xml"})


def article() -> httpx.Response:
    return httpx.Response(200, text=ARTICLE, headers=HTML_HEADERS)


def test_rss_collects_pages_with_listing_metadata():
    src, gate, _ = build({"/news/rss": feed_response(), "/news/one": article(), "/news/two": article(),
                          "/news/three": article()})
    result = collect_source(src, gate)
    assert [p.url for p in result.pages] == [f"{BASE}/news/one", f"{BASE}/news/two", "https://www.acme.example/news/three"]
    first = result.pages[0]
    assert first.listing_title == "Acme launches oil-free unit"
    assert "Oct 2026" in first.listing_published
    assert first.via == "rss" and first.status_code == 200
    assert "compressor" in first.html
    assert result.listing_count == 3  # the off-site link is not a candidate
    assert result.refusals == []


def test_html_list_page_filters_by_pattern_and_resolves_links():
    src = make_source(access_method="html", feed_url=None, item_url_pattern=r"/news/[a-z]+$")
    src, gate, requested = build({"/news": httpx.Response(200, text=LIST_PAGE, headers=HTML_HEADERS),
                                  "/news/alpha": article(), "/news/beta": article()}, source=src)
    result = collect_source(src, gate)
    assert [p.url for p in result.pages] == [f"{BASE}/news/alpha", f"{BASE}/news/beta"]
    assert result.pages[0].listing_title == "Alpha story"
    assert result.pages[0].via == "html"
    assert "/about" not in requested
    assert result.listing_count == 2


def test_max_items_limit_and_listing_count():
    src, gate, requested = build({"/news/rss": feed_response(), "/news/one": article(), "/news/two": article(),
                                  "/news/three": article()})
    result = collect_source(src, gate, max_items=1)
    assert len(result.pages) == 1
    assert result.listing_count == 3
    assert "/news/two" not in requested


def test_redirect_to_other_host_is_refused():
    redirect = httpx.Response(302, headers={"location": "https://evil.example/landing"})
    src, gate, _ = build({"/news/rss": feed_response(), "/news/one": redirect, "/news/two": article(),
                          "/news/three": article()})
    result = collect_source(src, gate)
    assert [r.reason for r in result.refusals] == ["redirect_off_host"]
    assert len(result.pages) == 2


def test_same_site_redirect_is_followed_and_final_url_recorded():
    redirect = httpx.Response(301, headers={"location": "/news/one-moved"})
    src, gate, _ = build({"/news/rss": feed_response(), "/news/one": redirect, "/news/one-moved": article(),
                          "/news/two": article(), "/news/three": article()})
    result = collect_source(src, gate)
    moved = result.pages[0]
    assert moved.url == f"{BASE}/news/one" and moved.final_url == f"{BASE}/news/one-moved"


def test_robots_disallow_on_one_article():
    src, gate, requested = build(
        {"/news/rss": feed_response(), "/news/one": article(), "/news/two": article(), "/news/three": article()},
        robots="User-agent: *\nDisallow: /news/two\n",
    )
    result = collect_source(src, gate)
    assert [p.url for p in result.pages] == [f"{BASE}/news/one", "https://www.acme.example/news/three"]
    assert "/news/two" not in requested  # never even requested
    assert [(r.reason, r.url) for r in result.refusals] == [("robots_disallow", f"{BASE}/news/two")]


def test_http_errors_are_refusals_and_collection_continues():
    src, gate, _ = build({"/news/rss": feed_response(), "/news/one": httpx.Response(404),
                          "/news/two": httpx.Response(500), "/news/three": article()})
    result = collect_source(src, gate)
    assert sorted(r.reason for r in result.refusals) == ["http_404", "http_500"]
    assert len(result.pages) == 1


def test_429_stops_collection():
    src, gate, requested = build({"/news/rss": feed_response(), "/news/one": article(),
                                  "/news/two": httpx.Response(429), "/news/three": article()})
    result = collect_source(src, gate)
    assert [p.url for p in result.pages] == [f"{BASE}/news/one"]
    assert [r.reason for r in result.refusals] == ["rate_limited_stop"]
    assert "/news/three" not in requested


def test_503_stops_collection():
    src, gate, _ = build({"/news/rss": httpx.Response(503)})
    result = collect_source(src, gate)
    assert result.pages == [] and [r.reason for r in result.refusals] == ["rate_limited_stop"]


def test_html_source_without_pattern_does_not_guess():
    src = make_source(access_method="html", feed_url=None, item_url_pattern=None)
    src, gate, requested = build({"/news": httpx.Response(200, text=LIST_PAGE, headers=HTML_HEADERS)}, source=src)
    result = collect_source(src, gate)
    assert result.pages == []
    assert [r.reason for r in result.refusals] == ["no_item_url_pattern"]
    assert requested == []


def test_non_html_article_refused():
    pdf = httpx.Response(200, content=b"%PDF", headers={"content-type": "application/pdf"})
    src, gate, _ = build({"/news/rss": feed_response(), "/news/one": pdf, "/news/two": article(),
                          "/news/three": article()})
    result = collect_source(src, gate)
    assert [r.reason for r in result.refusals] == ["not_html"]


def test_oversized_page_refused():
    big = httpx.Response(200, content=b"x" * (MAX_BYTES + 1), headers=HTML_HEADERS)
    src, gate, _ = build({"/news/rss": feed_response(), "/news/one": big, "/news/two": article(),
                          "/news/three": article()})
    result = collect_source(src, gate)
    assert [r.reason for r in result.refusals] == ["too_large"]


def test_network_error_is_a_refusal():
    def boom(request):
        raise httpx.ConnectTimeout("slow")

    src, gate, _ = build({"/news/rss": feed_response(), "/news/one": boom, "/news/two": article(),
                          "/news/three": article()})
    result = collect_source(src, gate)
    assert [r.reason for r in result.refusals] == ["fetch_error:ConnectTimeout"]
    assert len(result.pages) == 2


def test_empty_feed_is_reported():
    empty = httpx.Response(200, text='<?xml version="1.0"?><rss version="2.0"><channel></channel></rss>')
    src, gate, _ = build({"/news/rss": empty})
    result = collect_source(src, gate)
    assert result.listing_count == 0
    assert [r.reason for r in result.refusals] == ["no_items_found"]


def test_api_access_not_implemented():
    src = make_source(access_method="api")
    src, gate, _ = build({}, source=src)
    try:
        collect_source(src, gate)
    except NotImplementedError as exc:
        assert "api access" in str(exc)
    else:
        raise AssertionError("expected NotImplementedError")


def test_every_request_carries_the_user_agent():
    agents = []

    def spy(request):
        agents.append(request.headers["user-agent"])
        return article()

    src, gate, _ = build({"/news/rss": feed_response(), "/news/one": spy, "/news/two": spy, "/news/three": spy})
    collect_source(src, gate)
    assert agents and all("AtlasCopcoStudentPoC/0.1 (+contact: team@example.com)" == a for a in agents)


def test_dump_never_contains_html():
    src, gate, _ = build({"/news/rss": feed_response(), "/news/one": article(), "/news/two": article(),
                          "/news/three": article()})
    result = collect_source(src, gate)
    assert "html" not in result.pages[0].model_dump()
    assert "Invented text" not in result.model_dump_json()


def test_no_files_written(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    src, gate, _ = build({"/news/rss": feed_response(), "/news/one": article(), "/news/two": article(),
                          "/news/three": article()})
    collect_source(src, gate)
    assert list(tmp_path.iterdir()) == []
