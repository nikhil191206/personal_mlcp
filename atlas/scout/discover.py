"""Source discovery: finds candidate sources. It never approves anything.

Owner: Ragini. Methods, in this order (each candidate records how it was found in `discovered_via`):
    1. seed        the curated list in config/discovery_seeds.yaml
    2. outbound    external links on a few pages of sources we already vetted (via the Collector)
    3. search_api  only with an official API key; no provider is implemented (open decision, parent2 s.17)
    4. feed        every new candidate's own homepage is fetched once for <link rel="alternate"> feeds

Every fetch goes through the Compliance Gate (robots.txt, polite delay, identified User-Agent). A candidate
whose robots.txt disallows its homepage is recorded as `rejected_by_rules` and never fetched again.
A search engine's result pages are never fetched and no search-engine address exists in this code.
Nothing is written to disk. Candidates are returned to the caller (the run saves them via settings_store).
"""
from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Optional, get_args
from urllib.parse import urljoin, urlsplit

import lxml.etree
import yaml
from lxml import html as lxml_html

import httpx

from atlas.collect import MAX_REDIRECTS, _decode, _http_get, collect_source
from atlas.compliance import RUNNABLE_STATUSES, ComplianceGate, same_site
from atlas.models import Candidate, Refusal, ScoutSettings, Source, SourceType

log = logging.getLogger("atlas.scout.discover")

ROOT = Path(__file__).resolve().parent.parent.parent
SEEDS_PATH = "config/discovery_seeds.yaml"
REGIONS = ("US", "CA", "MX")
OUTBOUND_PAGES_PER_SOURCE = 3

# Registered domains that sit under a two-label public suffix. A small list instead of a new dependency.
_TWO_LABEL_SUFFIXES = {
    "co.uk", "org.uk", "ac.uk", "gov.uk", "com.au", "co.in", "co.jp", "co.za", "com.br",
    "com.mx", "org.mx", "gc.ca", "gov.au",
}

# First label of a registered domain that is never a publisher, association or company worth vetting:
# social media, ad networks, search engines, link shorteners and page infrastructure. Labels, not URLs.
_SKIP_LABELS = {
    # social media and video
    "facebook", "fb", "twitter", "x", "linkedin", "instagram", "youtube", "youtu", "tiktok", "pinterest",
    "reddit", "tumblr", "flickr", "vimeo", "whatsapp", "snapchat", "threads", "telegram",
    # ad networks and trackers
    "doubleclick", "googlesyndication", "googleadservices", "googletagmanager", "adsrvr", "adnxs",
    "taboola", "outbrain", "criteo", "scorecardresearch", "quantserve", "hotjar", "hubspot",
    # search engines
    "google", "bing", "duckduckgo", "yahoo", "baidu", "yandex", "ecosia", "startpage",
    # link shorteners
    "bit", "bitly", "t", "tinyurl", "ow", "goo", "lnkd", "buff", "is", "shorturl", "cutt", "rebrand",
    # infrastructure, app stores, generic platforms
    "w3", "schema", "wordpress", "wp", "gravatar", "cloudflare", "apple", "adobe", "microsoft", "paypal",
    "mozilla", "github", "addthis", "sharethis", "mailchimp",
}


# ---------- small helpers shared with vet.py ----------

def registered_domain(url_or_host: str) -> str:
    """example.co.uk for https://www.news.example.co.uk/x; lowercased, no port."""
    host = urlsplit(url_or_host).hostname if "://" in url_or_host else url_or_host.split("/")[0].split(":")[0]
    labels = (host or "").lower().strip(".").split(".")
    if len(labels) <= 2:
        return ".".join(labels)
    if ".".join(labels[-2:]) in _TWO_LABEL_SUFFIXES:
        return ".".join(labels[-3:])
    return ".".join(labels[-2:])


def make_candidate_id(domain: str) -> str:
    """First 12 hex chars of sha256(domain)."""
    return hashlib.sha256(domain.encode("utf-8")).hexdigest()[:12]


def probe_source(url: str, domain: str, type_guess: str = "trade_news") -> Source:
    """A throwaway Source so the Compliance Gate can be used for a candidate. Never saved, never a register row."""
    return Source(
        source_id=f"cand_{make_candidate_id(domain)}", name=domain, url=url, type=type_guess,
        access_method="html", robots_status="unknown", terms_status="unknown", vetting_status="working",
        status="proposed", review_date=date.today(),
    )


def parse_html(content: "bytes | str"):
    """Parse HTML into an lxml tree, or None if it is empty or unparseable."""
    try:
        if isinstance(content, str):
            data = content.encode("utf-8", errors="ignore")
            if not data.strip():
                return None
            return lxml_html.fromstring(data, parser=lxml_html.HTMLParser(encoding="utf-8"))
        if not content.strip():
            return None
        return lxml_html.fromstring(content)
    except (lxml.etree.ParserError, ValueError):
        return None


def find_feed_links(doc, base_url: str) -> list[str]:
    """Feeds a page advertises with <link rel="alternate" type="application/rss+xml|atom+xml">. RSS first."""
    rss: list[str] = []
    atom: list[str] = []
    for link in doc.iter("link"):
        rel = (link.get("rel") or "").lower().split()
        ctype = (link.get("type") or "").lower()
        href = (link.get("href") or "").strip()
        if "alternate" not in rel or not href:
            continue
        absolute = urljoin(base_url, href)
        if urlsplit(absolute).scheme not in ("http", "https"):
            continue
        if ctype == "application/rss+xml" and absolute not in rss:
            rss.append(absolute)
        elif ctype == "application/atom+xml" and absolute not in atom:
            atom.append(absolute)
    return rss + atom


# ---------- gated fetching ----------

class RateLimited(Exception):
    """HTTP 429 or 503: stop talking to this site."""


class BudgetExhausted(Exception):
    """The per-candidate request budget is used up."""


@dataclass
class Page:
    url: str  # final URL after redirects
    status: int
    content_type: str
    body: bytes

    @property
    def text(self) -> str:
        return _decode(self.body, self.content_type)


class GatedFetcher:
    """GET through the Compliance Gate with a request budget. Redirects are followed by hand, each hop
    re-checked, and never off the site asked for (the candidate's own, or a parent's terms page). `requests` counts every HTTP request made here
    (robots.txt is fetched by the gate itself, once per host, and is not counted)."""

    def __init__(self, gate: ComplianceGate, probe: Source, budget: Optional[int] = None) -> None:
        self.gate = gate
        self.probe = probe
        self.budget = budget
        self.requests = 0
        self.refusal: Optional[str] = None  # why the last get() returned None

    def allowed(self, url: str) -> tuple[bool, str]:
        """robots.txt verdict for a URL (no page request)."""
        return self.gate.can_fetch(self.probe, url)

    def get(self, url: str) -> Optional[Page]:
        """A Page for any HTTP answer (check .status), or None if nothing was fetched (see self.refusal)."""
        self.refusal = None
        current = url
        for _ in range(MAX_REDIRECTS + 1):
            ok, reason = self.gate.can_fetch(self.probe, current)
            if not ok:
                self.refusal = reason
                return None
            if self.budget is not None and self.requests >= self.budget:
                raise BudgetExhausted(f"request budget of {self.budget} used up")
            self.gate.wait(self.probe, current)
            self.requests += 1
            try:
                resp = _http_get(self.gate.client, current, self.gate.user_agent)
            except httpx.HTTPError as exc:
                self.refusal = f"fetch_error:{type(exc).__name__}"
                return None
            if resp.status in (429, 503):
                self.refusal = f"rate_limited_{resp.status}"
                raise RateLimited(self.refusal)
            if 300 <= resp.status < 400 and resp.location:
                nxt = urljoin(current, resp.location)
                if not same_site(nxt, self.probe.url) and not same_site(nxt, url):  # url: the host asked for
                    self.refusal = "redirect_off_host"
                    return None
                current = nxt
                continue
            if resp.too_large:
                self.refusal = "too_large"
                return None
            return Page(url=current, status=resp.status, content_type=resp.content_type, body=resp.body)
        self.refusal = "too_many_redirects"
        return None


# ---------- seeds ----------

def load_seeds(path: str = SEEDS_PATH) -> list[dict]:
    """Read and validate the seed file. A malformed entry raises ValueError that names it."""
    p = Path(path)
    if not p.is_absolute():
        p = ROOT / p
    with open(p, encoding="utf-8") as fh:
        entries = yaml.safe_load(fh) or []
    if not isinstance(entries, list):
        raise ValueError(f"{path}: expected a list of seeds")
    seeds: list[dict] = []
    for i, entry in enumerate(entries):
        label = entry.get("name", f"entry {i}") if isinstance(entry, dict) else f"entry {i}"
        if not isinstance(entry, dict) or not entry.get("name") or not entry.get("url"):
            raise ValueError(f"{path}: seed '{label}' needs a name and a url")
        if urlsplit(str(entry["url"])).scheme not in ("http", "https"):
            raise ValueError(f"{path}: seed '{label}' url must start with http:// or https://")
        if entry.get("type_guess") not in get_args(SourceType):
            raise ValueError(f"{path}: seed '{label}' type_guess must be one of {get_args(SourceType)}")
        if entry.get("region", "US") not in REGIONS:
            raise ValueError(f"{path}: seed '{label}' region must be one of {REGIONS}")
        seeds.append(entry)
    return seeds


def _candidate_from_seed(seed: dict, seeds_path: str) -> Candidate:
    url = str(seed["url"]).strip()
    domain = registered_domain(url)
    tags = ["[seed:verified]" if seed.get("verified") is True else "[seed:unverified]"]
    if seed.get("association") is True:
        tags.append("[association]")
    why = str(seed.get("why", "")).strip()
    return Candidate(
        candidate_id=make_candidate_id(domain), name=str(seed["name"]), url=url, domain=domain,
        type_guess=seed["type_guess"], region=seed.get("region", "US"), discovered_via="seed",
        discovered_from=seeds_path, access_method="html", notes=" ".join(tags) + (f" {why}" if why else ""),
    )


# ---------- outbound links ----------

def _runnable(source: Source) -> bool:
    return (source.status in RUNNABLE_STATUSES and source.vetting_status == "working"
            and source.terms_status != "forbids_automation")


def _skipped_domain(domain: str) -> bool:
    return not domain or "." not in domain or domain.split(".")[0] in _SKIP_LABELS


def _type_for_link(domain: str) -> SourceType:
    if domain.endswith((".gov", ".mil")) or domain.endswith(".gc.ca") or ".gov." in domain:
        return "government"
    return "trade_news"  # unknown type from a link found by chance; a note says so


def _region_for_domain(domain: str) -> str:
    if domain.endswith(".ca"):
        return "CA"
    if domain.endswith(".mx"):
        return "MX"
    return "US"


def _outbound_from_page(doc, page_url: str, own_domain: str) -> list[tuple[str, str]]:
    """(domain, homepage url) for each external link that could be a publisher, association or company."""
    out: list[tuple[str, str]] = []
    seen: set[str] = set()
    for anchor in doc.iter("a"):
        href = (anchor.get("href") or "").strip()
        if not href:
            continue
        absolute = urljoin(page_url, href)
        parts = urlsplit(absolute)
        if parts.scheme not in ("http", "https") or not parts.hostname:
            continue
        domain = registered_domain(parts.hostname)
        if domain == own_domain or domain in seen or _skipped_domain(domain):
            continue
        seen.add(domain)
        out.append((domain, f"{parts.scheme}://{parts.netloc}/"))
    return out


# ---------- search api (official API only; none implemented) ----------

def _search_api_candidates(settings: ScoutSettings) -> list[Candidate]:
    """Optional. Off by default. Phase 3: the official Firecrawl search API, results only (see
    atlas/scout/search_provider.py and docs/scraping_tools_evaluation.md). Never a search engine's result
    pages. One log line when it is skipped."""
    if not getattr(settings, "search_api_enabled", False):
        log.info("search_api skipped: not enabled in the settings")
        return []
    from atlas.scout.search_provider import api_key, search_candidates
    if not api_key():
        log.info("search_api skipped: FIRECRAWL_API_KEY is not set")
        return []
    candidates, notes = search_candidates(settings)
    for note in notes:
        log.info(note)
    return candidates


# ---------- the discovery run ----------

def _note(candidate: Candidate, text: str) -> None:
    candidate.notes = f"{candidate.notes} | {text}" if candidate.notes else text


def _check_homepage_robots(candidate: Candidate, gate: ComplianceGate) -> None:
    """A homepage that robots.txt disallows ends this candidate: it is recorded and never fetched further."""
    probe = probe_source(candidate.url, candidate.domain, candidate.type_guess)
    allowed, reason = gate.can_fetch(probe, candidate.url)
    if allowed:
        return  # robots_status stays 'unknown' until vetting checks the feed or listing URL
    if reason == "robots_disallow":
        candidate.robots_status = "disallowed"
        candidate.status = "rejected_by_rules"
        _note(candidate, "robots.txt disallows the homepage; not fetched further")
    else:
        _note(candidate, f"robots.txt could not be read ({reason}); needs review")


def _autodiscover_feed(candidate: Candidate, gate: ComplianceGate) -> None:
    """Fetch the candidate's own homepage once and read its advertised feeds."""
    if candidate.status == "rejected_by_rules":
        return
    probe = probe_source(candidate.url, candidate.domain, candidate.type_guess)
    fetcher = GatedFetcher(gate, probe, budget=1)
    page = fetcher.get(candidate.url)
    if page is None:
        _note(candidate, f"homepage not fetched ({fetcher.refusal})")
        return
    if page.status != 200:
        _note(candidate, f"homepage answered HTTP {page.status}")
        return
    doc = parse_html(page.body)
    feeds = find_feed_links(doc, page.url) if doc is not None else []
    if feeds:
        candidate.feed_url = feeds[0]
        candidate.access_method = "rss"
        _note(candidate, "feed found by autodiscovery on the homepage")
    else:
        _note(candidate, "no feed advertised on the homepage")


def discover_candidates(sources: list[Source], gate: ComplianceGate, settings: ScoutSettings,
                        seeds_path: str = SEEDS_PATH, known_domains: set[str] | None = None,
                        max_new: int = 25) -> list[Candidate]:
    """Find up to `max_new` new candidate sources. De-duplicated by registered domain; the register and
    `known_domains` are skipped. One failing candidate is noted on that candidate and the loop continues."""
    known = {registered_domain(s.url) for s in sources}
    known |= {registered_domain(d) for d in (known_domains or set())}
    found: dict[str, Candidate] = {}

    def add(candidate: Candidate) -> None:
        if candidate.domain in known or candidate.domain in found or len(found) >= max_new:
            return
        found[candidate.domain] = candidate
        try:
            _check_homepage_robots(candidate, gate)
        except Exception as exc:  # recorded on the candidate, never silent
            _note(candidate, f"discovery error: {type(exc).__name__}: {exc}")

    # 1. seeds
    for seed in load_seeds(seeds_path):
        if len(found) >= max_new:
            break
        add(_candidate_from_seed(seed, seeds_path))

    # 2. outbound links from pages of sources we already vetted
    for source in sources:
        if len(found) >= max_new:
            break
        if not _runnable(source):
            continue
        try:
            result = collect_source(source, gate, max_items=OUTBOUND_PAGES_PER_SOURCE)
        except Exception as exc:  # one broken source must not stop discovery; the gate log keeps the reason
            gate.refusals.append(Refusal(source_id=source.source_id, url=source.url,
                                         reason=f"discovery_error:{type(exc).__name__}"))
            log.warning("outbound discovery skipped %s: %s", source.source_id, exc)
            continue
        own = registered_domain(source.url)
        for page in result.pages:
            doc = parse_html(page.html)
            if doc is None:
                continue
            for domain, home in _outbound_from_page(doc, page.final_url, own):
                if len(found) >= max_new:
                    break
                if domain in known or domain in found:
                    continue
                add(Candidate(
                    candidate_id=make_candidate_id(domain), name=domain, url=home, domain=domain,
                    type_guess=_type_for_link(domain), region=_region_for_domain(domain),
                    discovered_via="outbound_link", discovered_from=page.final_url, access_method="html",
                    notes=f"type unknown, guessed {_type_for_link(domain)}; found by a link on {source.source_id}",
                ))

    # 3. optional official search API (none implemented)
    for candidate in _search_api_candidates(settings):
        add(candidate)

    # 4. feed autodiscovery on every new candidate's own homepage
    for candidate in found.values():
        try:
            _autodiscover_feed(candidate, gate)
        except RateLimited:
            _note(candidate, "rate limited (HTTP 429/503) on the homepage; stopped for this site")
        except Exception as exc:
            _note(candidate, f"discovery error: {type(exc).__name__}: {exc}")

    return list(found.values())
