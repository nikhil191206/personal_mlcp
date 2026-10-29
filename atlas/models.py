"""Shared data contracts for the whole pipeline.

Owner: Nikhil. Everyone imports from here. Do not redefine these classes elsewhere and do not change
a field without telling the owner: other people's code depends on exact names and types.

Persist with `obj.model_dump(mode="json")`. FetchedPage.html is excluded from dumps on purpose:
page text must never be stored.
"""
from __future__ import annotations

import hashlib
from datetime import date, datetime, timezone
from typing import Annotated, Literal, Optional

from pydantic import BaseModel, Field, StringConstraints

SourceType = Literal["competitor", "trade_news", "government"]
AccessMethod = Literal["rss", "api", "html"]
RobotsStatus = Literal["allowed", "disallowed", "unknown"]
TermsStatus = Literal["ok", "forbids_automation", "unknown"]
VettingStatus = Literal["working", "blocked", "needs_permission", "unreachable"]
ApprovalStatus = Literal["proposed", "approved", "blocked", "needs_permission"]
Label = Literal["fact", "claim"]

KeyFact = Annotated[str, StringConstraints(max_length=200)]


# ---------- helpers ----------

def new_run_id() -> str:
    """Run id format YYYYMMDDTHHMMSSZ (UTC)."""
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def make_item_id(source_url: str) -> str:
    """First 12 hex chars of sha256(source_url)."""
    return hashlib.sha256(source_url.encode("utf-8")).hexdigest()[:12]


def make_fingerprint(main_text: str) -> str:
    """sha256 hex of the cleaned main text. Lets a later run skip unchanged pages."""
    return hashlib.sha256(main_text.encode("utf-8")).hexdigest()


# ---------- source register ----------

class Source(BaseModel):
    """One row of config/sources.yaml (copied to source_register/sources.json each run)."""

    source_id: str
    name: str
    url: str
    type: SourceType
    access_method: AccessMethod
    feed_url: Optional[str] = None
    item_url_pattern: Optional[str] = None  # regex for article links on an HTML list page
    robots_status: RobotsStatus
    terms_status: TermsStatus
    vetting_status: VettingStatus
    status: ApprovalStatus = "proposed"
    review_date: date
    region: str = "US"
    licence_note: str = "Public web page; facts and links only"
    crawl_delay: Optional[float] = None  # seconds, from robots.txt if present
    notes: str = ""


# ---------- input side (Ragini -> Sachi) ----------

class GateDecision(BaseModel):
    source_id: str
    allowed: bool
    reasons: list[str] = Field(default_factory=list)


class Refusal(BaseModel):
    """Anything we did not fetch, and why. Goes into the run log."""

    source_id: str
    url: Optional[str] = None
    reason: str
    at: str = Field(default_factory=utc_now_iso)


class FetchedPage(BaseModel):
    """A page held in memory only. html is excluded from every dump."""

    source_id: str
    url: str
    final_url: str
    status_code: int
    html: str = Field(exclude=True, repr=False)
    fetched_at: str = Field(default_factory=utc_now_iso)
    listing_title: Optional[str] = None  # title from the RSS entry / list page, if any
    listing_published: Optional[str] = None  # raw date string from the RSS entry / list page, if any
    via: AccessMethod = "html"


class CollectResult(BaseModel):
    source_id: str
    pages: list[FetchedPage] = Field(default_factory=list)
    refusals: list[Refusal] = Field(default_factory=list)
    listing_count: int = 0  # how many candidate item URLs the listing offered


class RawItem(BaseModel):
    """What is stored in raw/: metadata of what was collected. No page text."""

    source_id: str
    source_url: str
    title: Optional[str] = None
    published_at_raw: Optional[str] = None
    collected_at: str
    http_status: int
    via: AccessMethod


# ---------- engine side ----------

class FilterResult(BaseModel):
    compressor_related: bool
    north_america: bool
    credible_source: bool
    recent: bool
    passed: bool
    reasons: list[str] = Field(default_factory=list)
    date_missing: bool = False


class Item(BaseModel):
    """One evidence record. Built by extract (filter=None), tidied by clean, judged by filter."""

    id: str
    source_id: str
    source_name: str
    source_type: SourceType
    source_url: str
    licence_note: str
    collected_at: str
    published_at: Optional[str] = None  # ISO date YYYY-MM-DD, or None. Never guessed.
    title: Optional[str] = None
    company: Optional[str] = None
    product: Optional[str] = None
    technology: Optional[str] = None
    key_facts: list[KeyFact] = Field(default_factory=list)
    label: Label = "claim"
    filter: Optional[FilterResult] = None
    page_fingerprint: str
    personal_data_removed: bool = False

    # Signals computed by extract while the text is still in memory (the text is then dropped).
    matched_keywords: list[str] = Field(default_factory=list)
    mentions_us_location: bool = False
    industrial_hint: bool = False  # a flag only, never a gate


class CleanResult(BaseModel):
    items: list[Item]
    duplicates_dropped: int = 0


# ---------- output ----------

class Scope(BaseModel):
    technology: str = "industrial compressors"
    region: str = "US"


class SourceSummary(BaseModel):
    source_id: str
    name: str
    status: VettingStatus
    items_collected: int = 0
    items_passed: int = 0
    note: Optional[str] = None  # e.g. why a source was blocked or errored


class OutputEnvelope(BaseModel):
    """output/poc_<run_id>.json. items = only the items that passed the filter."""

    run_id: str
    generated_at: str
    scope: Scope = Field(default_factory=Scope)
    sources: list[SourceSummary]
    items: list[Item]


class RunLog(BaseModel):
    """logs/<run_id>.json. What ran, what was blocked and why. Never page content."""

    run_id: str
    started_at: str
    finished_at: Optional[str] = None
    gate_decisions: list[GateDecision] = Field(default_factory=list)
    refusals: list[Refusal] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    counts: dict[str, dict[str, int]] = Field(default_factory=dict)  # source_id -> {collected, clean, passed}
