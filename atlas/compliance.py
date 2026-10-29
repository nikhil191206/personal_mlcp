"""Compliance Gate: decides whether a source / URL may be fetched (status, terms, robots.txt, delay).

Never works around a block. Every refusal is recorded as a Refusal with a short reason code.
"""
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional
from urllib.parse import urlsplit
from urllib.robotparser import RobotFileParser

import httpx
import yaml
from pydantic import ValidationError

from atlas.models import GateDecision, Refusal, Source
from atlas.settings import get_settings

USER_AGENT_TEMPLATE = "AtlasCopcoStudentPoC/0.1 (+contact: {email})"
ROBOTS_AGENT = "AtlasCopcoStudentPoC"
ROOT = Path(__file__).resolve().parent.parent
RUNNABLE_STATUSES = {"proposed", "approved"}


def load_register(path: str = "config/sources.yaml") -> list[Source]:
    p = Path(path)
    if not p.is_absolute():
        p = ROOT / p
    with open(p, encoding="utf-8") as fh:
        entries = yaml.safe_load(fh) or []
    sources: list[Source] = []
    for entry in entries:
        try:
            sources.append(Source.model_validate(entry))
        except ValidationError as exc:
            raise ValueError(f"invalid source entry '{entry.get('source_id', '?')}': {exc}") from exc
    return sources


def _host(url: str) -> str:
    return (urlsplit(url).hostname or "").lower()


def same_site(url_a: str, url_b: str) -> bool:
    """Same host, ignoring a leading www., or one a subdomain of the other."""
    a, b = _host(url_a).removeprefix("www."), _host(url_b).removeprefix("www.")
    return bool(a) and bool(b) and (a == b or a.endswith("." + b) or b.endswith("." + a))


@dataclass
class _Robots:
    mode: str  # parsed | allow_all | disallow_all | unreachable
    parser: Optional[RobotFileParser] = None
    crawl_delay: float = 0.0


class ComplianceGate:
    def __init__(self, sources: list[Source], client: "httpx.Client | None" = None,
                 min_delay: float = 3.0, contact_email: Optional[str] = None) -> None:
        email = contact_email if contact_email is not None else get_settings().contact_email
        if not email.strip():
            raise RuntimeError("CONTACT_EMAIL is not set in .env")
        self.user_agent = USER_AGENT_TEMPLATE.format(email=email.strip())
        self.sources = {s.source_id: s for s in sources}
        self.client = client or httpx.Client(headers={"User-Agent": self.user_agent}, timeout=20,
                                             follow_redirects=False)
        self.min_delay = min_delay
        self.refusals: list[Refusal] = []
        self.decisions: list[GateDecision] = []
        self._robots: dict[str, _Robots] = {}  # per run, in memory only
        self._last_request: dict[str, float] = {}
        self._sleep: Callable[[float], None] = time.sleep
        self._now: Callable[[], float] = time.monotonic

    # ---- robots.txt ----

    def _robots_for(self, url: str) -> _Robots:
        parts = urlsplit(url)
        key = f"{parts.scheme}://{parts.netloc}"
        if key in self._robots:
            return self._robots[key]
        try:
            resp = self.client.get(f"{key}/robots.txt", headers={"User-Agent": self.user_agent},
                                   follow_redirects=True)
        except httpx.HTTPError:
            info = _Robots("unreachable")
        else:
            if resp.status_code == 200:
                parser = RobotFileParser()
                parser.parse(resp.text.splitlines())
                info = _Robots("parsed", parser, float(parser.crawl_delay(ROBOTS_AGENT) or 0))
            elif resp.status_code in (404, 410):
                info = _Robots("allow_all")
            elif resp.status_code in (401, 403):
                info = _Robots("disallow_all")
            else:
                info = _Robots("unreachable")
        self._last_request[parts.netloc] = self._now()
        self._robots[key] = info
        return info

    def _verdict(self, url: str) -> str:
        """'ok', 'robots_disallow' or 'robots_unreachable'."""
        info = self._robots_for(url)
        if info.mode == "unreachable":
            return "robots_unreachable"
        if info.mode == "disallow_all":
            return "robots_disallow"
        if info.mode == "parsed" and not info.parser.can_fetch(ROBOTS_AGENT, url):
            return "robots_disallow"
        return "ok"

    def _refuse(self, source_id: str, url: Optional[str], reason: str) -> None:
        self.refusals.append(Refusal(source_id=source_id, url=url, reason=reason))

    # ---- public API ----

    def check_source(self, source: Source) -> GateDecision:
        """Run at the start of every run. Allowed only if every rule passes."""
        reasons: list[str] = []
        if source.status not in RUNNABLE_STATUSES:
            reasons.append("status_blocked")
        if source.vetting_status != "working":
            reasons.append(f"vetting_{source.vetting_status}")
        if source.terms_status == "forbids_automation":
            reasons.append("terms_forbid_automation")
        if not reasons:  # do not even contact a source that is already refused on its record
            listing = source.feed_url if source.access_method == "rss" and source.feed_url else source.url
            verdict = self._verdict(listing)
            if verdict == "robots_unreachable":
                reasons.append("robots_unreachable")
            elif verdict != "ok":
                reasons.append("robots_disallow_listing")
        decision = GateDecision(source_id=source.source_id, allowed=not reasons, reasons=reasons)
        for reason in reasons:
            self._refuse(source.source_id, source.url, reason)
        self.decisions.append(decision)
        return decision

    def can_fetch(self, source: Source, url: str) -> tuple[bool, str]:
        verdict = self._verdict(url)
        if verdict != "ok":
            self._refuse(source.source_id, url, verdict)
            return False, verdict
        return True, "ok"

    def wait(self, source: Source, url: Optional[str] = None) -> None:
        """Polite per-host delay: never below min_delay, and at least any Crawl-delay we know of."""
        target = url or source.url
        parts = urlsplit(target)
        robots = self._robots.get(f"{parts.scheme}://{parts.netloc}")
        delay = max(self.min_delay, robots.crawl_delay if robots else 0.0, source.crawl_delay or 0.0)
        last = self._last_request.get(parts.netloc)
        if last is not None:
            remaining = delay - (self._now() - last)
            if remaining > 0:
                self._sleep(remaining)
        self._last_request[parts.netloc] = self._now()
