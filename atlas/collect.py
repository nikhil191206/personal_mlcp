"""Collector: gets the item list (RSS first, HTML list page second) and fetches each item page politely.

Pages stay in memory (FetchedPage.html). Every URL goes through the Compliance Gate; redirects are
followed by hand so each hop is checked. No retries to dodge limits: a 429/503 stops the source.
"""
import re
from dataclasses import dataclass
from typing import Optional
from urllib.parse import urldefrag, urljoin

import feedparser
import httpx
from lxml import html as lxml_html

from atlas.compliance import ComplianceGate, same_site
from atlas.models import CollectResult, FetchedPage, Refusal, Source, utc_now_iso

MAX_BYTES = 3_000_000
MAX_REDIRECTS = 4


class _RateLimited(Exception):
    pass


@dataclass
class _Response:
    status: int
    url: str
    content_type: str
    location: Optional[str]
    body: bytes
    too_large: bool = False


def _http_get(client: httpx.Client, url: str, user_agent: str) -> _Response:
    """One GET without following redirects; the body is read only for 200s and capped at MAX_BYTES."""
    with client.stream("GET", url, headers={"User-Agent": user_agent}, follow_redirects=False) as resp:
        ctype = resp.headers.get("content-type", "").lower()
        location = resp.headers.get("location")
        if resp.status_code != 200:
            return _Response(resp.status_code, url, ctype, location, b"")
        chunks, size = [], 0
        for chunk in resp.iter_bytes():
            size += len(chunk)
            if size > MAX_BYTES:
                return _Response(200, url, ctype, location, b"", too_large=True)
            chunks.append(chunk)
        return _Response(200, url, ctype, location, b"".join(chunks))


def _decode(body: bytes, content_type: str) -> str:
    match = re.search(r"charset=([\w-]+)", content_type)
    for enc in ([match.group(1)] if match else []) + ["utf-8"]:
        try:
            return body.decode(enc, errors="replace")
        except LookupError:
            continue
    return body.decode("utf-8", errors="replace")


def _fetch(source: Source, url: str, gate: ComplianceGate, client: httpx.Client,
           local: list[Refusal]) -> Optional[_Response]:
    """Gate check + polite wait + GET, following redirects by hand (each hop re-checked)."""
    current = url
    for _ in range(MAX_REDIRECTS + 1):
        allowed, _reason = gate.can_fetch(source, current)  # the gate records its own refusals
        if not allowed:
            return None
        gate.wait(source, current)
        try:
            resp = _http_get(client, current, gate.user_agent)
        except httpx.HTTPError as exc:
            local.append(Refusal(source_id=source.source_id, url=current,
                                 reason=f"fetch_error:{type(exc).__name__}"))
            return None
        if resp.status in (429, 503):
            local.append(Refusal(source_id=source.source_id, url=current, reason="rate_limited_stop"))
            raise _RateLimited
        if 300 <= resp.status < 400 and resp.location:
            nxt = urljoin(current, resp.location)
            if not same_site(nxt, source.url):
                local.append(Refusal(source_id=source.source_id, url=url, reason="redirect_off_host"))
                return None
            current = nxt
            continue
        if resp.status != 200:
            local.append(Refusal(source_id=source.source_id, url=current, reason=f"http_{resp.status}"))
            return None
        if resp.too_large:
            local.append(Refusal(source_id=source.source_id, url=current, reason="too_large"))
            return None
        resp.url = current
        return resp
    local.append(Refusal(source_id=source.source_id, url=url, reason="too_many_redirects"))
    return None


def _candidates_from_feed(source: Source, resp: _Response) -> list[tuple[str, Optional[str], Optional[str]]]:
    feed = feedparser.parse(resp.body)
    out: list[tuple[str, Optional[str], Optional[str]]] = []
    seen: set[str] = set()
    for entry in feed.entries:
        link = (entry.get("link") or "").strip()
        if not link or link in seen or not same_site(link, source.url):
            continue
        seen.add(link)
        out.append((link, entry.get("title"), entry.get("published") or entry.get("updated")))
    return out


def _candidates_from_html(source: Source, resp: _Response) -> list[tuple[str, Optional[str], Optional[str]]]:
    pattern = re.compile(source.item_url_pattern)
    doc = lxml_html.fromstring(_decode(resp.body, resp.content_type))
    out: list[tuple[str, Optional[str], Optional[str]]] = []
    seen: set[str] = set()
    for anchor in doc.iter("a"):
        href = anchor.get("href")
        if not href:
            continue
        link = urldefrag(urljoin(resp.url, href.strip()))[0]
        if link in seen or not same_site(link, source.url) or not pattern.search(link):
            continue
        seen.add(link)
        out.append((link, (anchor.text_content() or "").strip() or None, None))
    return out


def collect_source(source: Source, gate: ComplianceGate, max_items: int = 20,
                   client: "httpx.Client | None" = None) -> CollectResult:
    client = client or gate.client
    local: list[Refusal] = []
    gate_start = len(gate.refusals)
    result = CollectResult(source_id=source.source_id)

    try:
        if source.access_method == "api":
            raise NotImplementedError("api access not used in the Friday PoC")

        if source.access_method == "rss":
            listing_url = source.feed_url or source.url
        else:
            listing_url = source.url
            if not source.item_url_pattern:
                local.append(Refusal(source_id=source.source_id, url=source.url, reason="no_item_url_pattern"))
                listing_url = None

        if listing_url:
            listing = _fetch(source, listing_url, gate, client, local)
            if listing is not None:
                if source.access_method == "rss":
                    candidates = _candidates_from_feed(source, listing)
                else:
                    candidates = _candidates_from_html(source, listing)
                result.listing_count = len(candidates)
                if not candidates:
                    local.append(Refusal(source_id=source.source_id, url=listing_url, reason="no_items_found"))
                for link, title, published in candidates[:max_items]:
                    resp = _fetch(source, link, gate, client, local)
                    if resp is None:
                        continue
                    if "html" not in resp.content_type:
                        local.append(Refusal(source_id=source.source_id, url=resp.url, reason="not_html"))
                        continue
                    result.pages.append(FetchedPage(
                        source_id=source.source_id, url=link, final_url=resp.url, status_code=resp.status,
                        html=_decode(resp.body, resp.content_type), fetched_at=utc_now_iso(),
                        listing_title=title, listing_published=published, via=source.access_method,
                    ))
    except _RateLimited:
        pass  # already recorded as rate_limited_stop; stop collecting from this source

    result.refusals = gate.refusals[gate_start:] + local
    return result
