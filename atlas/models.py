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

# ---- phase 2 ----
Region = Literal["US", "CA", "MX"]
EventType = Literal[
    "product_launch", "acquisition", "investment_expansion", "partnership",
    "regulation_standard", "appointment", "award", "event", "other",
]
DiscoveryMethod = Literal["seed", "outbound_link", "feed_autodiscovery", "search_api", "manual"]
CandidateStatus = Literal["new", "auto_vetted", "needs_review", "rejected_by_rules"]
SourceOrigin = Literal["manual", "discovered"]
SummaryKind = Literal["registered", "discovered", "fallback"]

KeyFact = Annotated[str, StringConstraints(max_length=200)]

# ---- phase 3: company discovery, validation, company profiles ----
CompanyMethod = Literal[
    "competitor_source", "alias_list", "ticker", "about_section", "headline", "structured_data", "org_mentions",
]
Confidence = Literal["high", "medium", "low"]
ValidationStatus = Literal["confirmed", "not_confirmed"]
Heading = Annotated[str, StringConstraints(max_length=120)]


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
    origin: SourceOrigin = "manual"  # "discovered" = found by the scout engine, never auto-approved
    trust_score: Optional[int] = None  # 0-100, set for discovered sources


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

    # phase 2 (all optional, so phase 1 records stay valid)
    region: Optional[Region] = None  # where the item is about / from; None if unclear. Never guessed.
    event_type: Optional[EventType] = None
    story_id: Optional[str] = None  # set by the story clustering step
    via_fallback: bool = False  # True if collected because another source was refused
    fallback_for: Optional[str] = None  # source_id of the refused source this item substitutes for
    watch_matches: list[str] = Field(default_factory=list)  # watchlist names found in title/text

    # phase 3 (all optional, so phase 1 and 2 records stay valid)
    company_method: Optional[CompanyMethod] = None  # which rule found `company`
    company_confidence: Optional[Confidence] = None
    company_evidence: Optional[str] = Field(default=None, max_length=160)  # the short phrase that named it
    headings: list[Heading] = Field(default_factory=list)  # up to 5 page headings (h1-h3), scrubbed
    summary: Optional[str] = Field(default=None, max_length=300)  # the page's own meta description, scrubbed
    image_url: Optional[str] = None  # the page's og:image (a link only; the image is not copied)
    validation: Optional["Validation"] = None  # set by atlas.validate after the run


class Validation(BaseModel):
    """Confirmed / Not confirmed, with the rule that decided it and the links that back it."""

    status: ValidationStatus = "not_confirmed"
    criteria_met: list[str] = Field(default_factory=list)  # e.g. "corroborated by 2 independent sources"
    reasons: list[str] = Field(default_factory=list)  # why it is not (yet) confirmed
    evidence_urls: list[str] = Field(default_factory=list)


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
    kind: SummaryKind = "registered"
    fallback_for: Optional[str] = None  # for kind == "fallback": the refused source it stands in for


# ---------- phase 2: scout engine, settings, stories ----------

class WatchEntry(BaseModel):
    """A company, product or technology the scout keeps following, even if its own site is refused."""

    name: str
    kind: Literal["company", "product", "technology"] = "company"
    aliases: list[str] = Field(default_factory=list)
    follow_when_blocked: bool = True  # if its source is refused, look for coverage elsewhere


class ScoutSettings(BaseModel):
    """Everything the frontend can adjust. Defaults reproduce the phase 1 behaviour exactly.
    Stored as settings/scout_settings.json in the Volume; config/scout_settings.yaml holds the defaults."""

    # scope
    regions: list[Region] = Field(default_factory=lambda: ["US"])
    technologies: list[str] = Field(default_factory=list)  # labels from technologies.yaml; empty = all
    event_types: list[EventType] = Field(default_factory=list)  # empty = all
    # relevance filter
    recent_months: int = Field(12, ge=1, le=60)
    extra_compressor_keywords: list[str] = Field(default_factory=list)
    excluded_keywords: list[str] = Field(default_factory=list)
    require_industrial: bool = False
    # sources
    source_types: list[SourceType] = Field(default_factory=lambda: ["competitor", "trade_news", "government"])
    use_discovered_sources: bool = False
    min_trust_score: int = Field(70, ge=0, le=100)
    max_items_per_source: int = Field(20, ge=1, le=100)
    # scout engine
    discovery_enabled: bool = False
    search_api_enabled: bool = False  # phase 3: official search API (Firecrawl) for discovery; needs FIRECRAWL_API_KEY
    fallback_enabled: bool = True
    fallback_max_items_per_source: int = Field(40, ge=1, le=200)
    watchlist: list[WatchEntry] = Field(default_factory=list)


class Candidate(BaseModel):
    """A source found by the scout engine. Stored in scout/candidates.json. Never `approved` automatically."""

    candidate_id: str  # first 12 hex chars of sha256(domain)
    name: str
    url: str
    domain: str
    type_guess: SourceType
    region: str = "US"
    discovered_via: DiscoveryMethod
    discovered_from: Optional[str] = None  # the page, seed file or query that led here
    discovered_at: str = Field(default_factory=utc_now_iso)
    access_method: AccessMethod = "rss"
    feed_url: Optional[str] = None
    item_url_pattern: Optional[str] = None
    robots_status: RobotsStatus = "unknown"
    terms_status: TermsStatus = "unknown"
    terms_url: Optional[str] = None
    terms_evidence: Optional[str] = Field(default=None, max_length=200)  # a short quote only
    public_ok: Optional[bool] = None  # public and logged-out
    newest_item_date: Optional[str] = None  # ISO date of the newest dated item seen
    relevance_sample: Optional[float] = Field(default=None, ge=0, le=1)  # share of sampled items that match a compressor keyword
    trust_score: int = Field(0, ge=0, le=100)
    trust_reasons: list[str] = Field(default_factory=list)  # one line per point awarded or withheld
    status: CandidateStatus = "new"
    usable: bool = False  # True only when every automatic rule passed; still needs a human decision
    notes: str = ""


class CandidateDecision(BaseModel):
    """A team member's decision on a candidate. Stored in scout/decisions.json. Not an Atlas Copco approval."""

    candidate_id: str
    decision: Literal["accepted", "rejected"]
    decided_by: str
    decided_at: str = Field(default_factory=utc_now_iso)
    note: str = ""


class StoryCluster(BaseModel):
    """Items from different sources about the same company / product / event."""

    story_id: str
    headline: str  # title of the earliest item
    company: Optional[str] = None
    product: Optional[str] = None
    event_type: Optional[EventType] = None
    item_ids: list[str]
    source_ids: list[str]
    first_published: Optional[str] = None
    last_published: Optional[str] = None
    via_fallback_count: int = 0


class OutputEnvelope(BaseModel):
    """output/poc_<run_id>.json. items = only the items that passed the filter."""

    run_id: str
    generated_at: str
    scope: Scope = Field(default_factory=Scope)
    sources: list[SourceSummary]
    items: list[Item]
    # phase 2 (optional, so phase 1 outputs stay valid)
    stories: list[StoryCluster] = Field(default_factory=list)
    settings_used: Optional[ScoutSettings] = None
    candidates_considered: int = 0


class CompanyContact(BaseModel):
    """A contact detail of a company (never of a person), read from the company's own website."""

    kind: Literal["email", "phone", "address", "website"]
    value: str = Field(max_length=300)
    found_on: list[str] = Field(default_factory=list)  # page URLs where it appeared
    method: Literal["structured_data", "mailto_link", "tel_link", "labelled_text", "address_tag", "register"] = "labelled_text"
    validation: Validation = Field(default_factory=Validation)


class CompanyImage(BaseModel):
    """A link to a logo or image. Only the logo is copied (to the Volume, for the company report)."""

    kind: Literal["logo", "image"]
    url: str
    source_url: str  # the page that pointed to it
    alt: Optional[str] = Field(default=None, max_length=160)
    stored_path: Optional[str] = None  # Volume path of the stored copy (logo only)


class CompanyProfile(BaseModel):
    """Everything known about one company in one run: its items, contacts, images and validation."""

    company_id: str  # slug, e.g. "kaeser-compressors"
    name: str
    website: Optional[str] = None
    item_ids: list[str] = Field(default_factory=list)
    confirmed_item_ids: list[str] = Field(default_factory=list)
    source_ids: list[str] = Field(default_factory=list)
    story_ids: list[str] = Field(default_factory=list)
    event_types: dict[str, int] = Field(default_factory=dict)
    technologies: dict[str, int] = Field(default_factory=dict)
    regions: dict[str, int] = Field(default_factory=dict)
    products: list[str] = Field(default_factory=list)
    first_published: Optional[str] = None
    last_published: Optional[str] = None
    contacts: list[CompanyContact] = Field(default_factory=list)
    logo: Optional[CompanyImage] = None
    images: list[CompanyImage] = Field(default_factory=list)
    profile_status: str = "not read yet"  # what happened when the website was read (or why it was not)
    profile_fetched_at: Optional[str] = None


class CompanyIndex(BaseModel):
    """companies/<run_id>/index.json: the company-wise view of one run."""

    run_id: str
    generated_at: str
    companies: list[CompanyProfile]
    unattributed_item_ids: list[str] = Field(default_factory=list)  # items with no company found
    criteria: list[str] = Field(default_factory=list)  # the validation rules used, in plain words


class RunLog(BaseModel):
    """logs/<run_id>.json. What ran, what was blocked and why. Never page content."""

    run_id: str
    started_at: str
    finished_at: Optional[str] = None
    gate_decisions: list[GateDecision] = Field(default_factory=list)
    refusals: list[Refusal] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)  # phase 2: discovery and switching findings (not errors)
    counts: dict[str, dict[str, int]] = Field(default_factory=dict)  # source_id -> {collected, clean, passed}


# Item refers to Validation, which is defined after it.
Item.model_rebuild()
CleanResult.model_rebuild()
OutputEnvelope.model_rebuild()
