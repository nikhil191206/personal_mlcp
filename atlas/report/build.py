"""Report computation shared by the PPTX and PDF builders (sachi2.md S6 to S8).

Owner: Sachi.

Everything shown in a report is computed here from one `OutputEnvelope`, so the two formats always
agree. Rules (parent2.md section 2, rule 8):
- only items in the envelope; every number is counted from it, nothing is typed in by hand;
- text comes from fixed templates filled with computed values (no AI-written text);
- key facts are shown as stored; no other article text exists or is used;
- a last-line check refuses (raises) if an item looks like it holds an email address or a phone number;
- nothing is written to local disk: builders return bytes, `write_report` uploads through atlas.storage.
"""
from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Literal, Optional

from atlas.models import OutputEnvelope, SourceSummary

Format = Literal["pptx", "pdf"]

PREPARED_FOR = "Prepared for Atlas Copco by Group 8, VIT Pune. Source list is proposed, pending approval."
DISCOVERED_NOTE = "discovered, not yet approved"
NOT_STATED = "(not stated)"
TOP_ITEMS = 8
TOP_COMPANIES = 10
HEADLINE_ITEMS = 3
APPENDIX_ROWS_PER_SLIDE = 12

SECTION_TITLES = {
    "title": "Market and Technology Scout",
    "summary": "Executive summary",
    "scope": "Scope and method",
    "found": "What we found",
    "company": "By company",
    "tech_event": "By technology and event type",
    "stories": "Seen in several sources",
    "sources": "Sources and compliance",
    "howto": "How to read this report",
    "appendix": "Appendix: all items",
}

EVENT_LABELS = {
    "product_launch": "product launch", "acquisition": "acquisition",
    "investment_expansion": "investment / expansion", "partnership": "partnership",
    "regulation_standard": "regulation / standard", "appointment": "appointment", "award": "award",
    "event": "event", "other": "other",
}
REFUSED_STATUSES = {"blocked", "needs_permission", "unreachable"}

HOW_TO_READ = [
    "Fact: reported by a government source, or trade news that reports an event such as an acquisition, "
    "a filing or a recall. Claim: what a company says about itself (press releases, company blogs) and "
    "anything we are not sure of. The system never decides what is true.",
    "Passed the filter: the item is about compressors or the related technologies in scope, is about or "
    "from the regions in scope, comes from a vetted source, and has a publication date inside the time "
    "window. Items without a date do not pass.",
    "Via switching: when a source was refused, the scout looked for articles about the same watched "
    "company or product in other allowed sources. Those items are marked and the refused site was not "
    "contacted again.",
    "Discovered sources were found by the scout, checked by automatic rules, and are not approved by "
    "Atlas Copco.",
    "Limits: all rules are fixed patterns, not judgement; region, event type and product stay empty "
    "when the page does not state them; this is a small sample from a short list of sources.",
]

METHOD_LINES = [
    "Filter: transparent yes/no rules on keywords, region, source and date; every item records why it "
    "passed.",
    "Compliance: public pages only; robots.txt and terms of use checked before any fetch; refused sites "
    "are never bypassed; no page text and no personal data are stored, only short facts and links.",
]

# Last line of defence against personal data (the extractor removes it before this point).
_EMAIL = re.compile(r"@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+")
_PHONE = re.compile(
    r"(?<![\w/])(?:\+?1[\s.-]?)?\(?\d{3}\)?[\s.-]\d{3}[\s.-]\d{4}(?![\w/])"
    r"|(?<![\w/])\+\d{1,3}(?:[\s.-]?\d{2,4}){3,}(?![\w/])"
)


class PersonalDataError(ValueError):
    """Raised when an item looks like it contains an email address or a phone number."""


# ---------- rows used by both builders ----------

@dataclass
class ItemRow:
    item_id: str
    title: str
    company: str
    event_type: str
    region: str
    technology: str
    product: str
    date: Optional[str]
    label: str
    url: str
    source_id: str
    source_name: str
    discovered: bool
    via_fallback: bool
    fallback_for: Optional[str]
    story_sources: int
    key_facts: list[str]

    @property
    def date_text(self) -> str:
        return self.date or "date not stated"

    @property
    def marker(self) -> str:
        """Short flags shown next to an item."""
        flags = []
        if self.via_fallback:
            flags.append(f"via switching (for {self.fallback_for})" if self.fallback_for else "via switching")
        if self.discovered:
            flags.append(f"source {DISCOVERED_NOTE}")
        return "; ".join(flags)


@dataclass
class SourceRow:
    source_id: str
    name: str
    kind: str
    status: str
    collected: int
    passed: int
    note: str
    refused: bool
    discovered: bool
    fallback_for: Optional[str]


@dataclass
class StoryRow:
    story_id: str
    title: str
    company: str
    event_type: str
    source_names: list[str]
    item_count: int
    fallback_items: int


@dataclass
class ReportData:
    run_id: str
    run_date: str
    generated_at: str
    n_items: int
    n_sources: int
    n_sources_with_items: int
    n_refused: int
    n_discovered: int
    n_stories: int
    n_multi_source_stories: int
    n_fallback_items: int
    candidates_considered: int
    n_companies: int
    by_company: list[tuple[str, int]]
    company_events: dict[str, list[str]]
    by_technology: list[tuple[str, int]]
    by_event_type: list[tuple[str, int]]
    by_region: list[tuple[str, int]]
    by_label: list[tuple[str, int]]
    top_items: list[ItemRow]
    all_items: list[ItemRow]
    headline_items: list[ItemRow]
    stories: list[StoryRow]
    sources: list[SourceRow]
    refused: list[SourceRow]
    switching: list[tuple[str, list[str]]]
    switching_empty: list[str]
    scope_lines: list[str]
    summary_sentences: list[str]
    notes: dict[str, str] = field(default_factory=dict)

    @property
    def empty(self) -> bool:
        return self.n_items == 0


# ---------- checks ----------

def check_personal_data(envelope: OutputEnvelope) -> None:
    """Raise PersonalDataError if any item field holds '@domain' or a phone-number pattern."""
    for item in envelope.items:
        for name, value in item.model_dump(mode="json").items():
            values = value if isinstance(value, list) else [value]
            for v in values:
                if not isinstance(v, str):
                    continue
                if name.endswith("url") and v.startswith(("http://", "https://")) and "@" not in v.split("/")[2]:
                    continue  # a web address ("logo@2x.png" in a path is not an email); user@host is still caught
                if _EMAIL.search(v):
                    raise PersonalDataError(f"item {item.id}: field '{name}' looks like it holds an email address")
                if not name.endswith("url") and _PHONE.search(v):
                    raise PersonalDataError(f"item {item.id}: field '{name}' looks like it holds a phone number")


# ---------- helpers ----------

def _counts(values: list[Optional[str]]) -> list[tuple[str, int]]:
    """Count values, NOT_STATED for empty ones; largest first, then alphabetical."""
    c = Counter(v if v else NOT_STATED for v in values)
    return sorted(c.items(), key=lambda kv: (-kv[1], kv[0]))


def _is_refused(s: SourceSummary) -> bool:
    note = (s.note or "").lower()
    return note.startswith("refused") or (s.status in REFUSED_STATUSES and s.items_collected == 0)


def _event_text(value: Optional[str]) -> str:
    return EVENT_LABELS.get(value, value) if value else NOT_STATED


def _story_sources(envelope: OutputEnvelope) -> dict[str, set[str]]:
    """story_id -> distinct source ids, from the stories and from the items that carry the story id."""
    out: dict[str, set[str]] = {}
    for story in envelope.stories:
        out.setdefault(story.story_id, set()).update(story.source_ids)
    for item in envelope.items:
        if item.story_id:
            out.setdefault(item.story_id, set()).add(item.source_id)
    return out


def _rank(rows: list[ItemRow]) -> list[ItemRow]:
    """Transparent ranking: stories seen in more sources first, then most recent (no date last),
    then title. Implemented as stable sorts from the last key to the first."""
    ordered = sorted(rows, key=lambda r: r.title.casefold())
    ordered = sorted(ordered, key=lambda r: r.date or "", reverse=True)
    ordered = sorted(ordered, key=lambda r: r.date is None)
    return sorted(ordered, key=lambda r: -r.story_sources)


def _scope_lines(envelope: OutputEnvelope, n_sources_with_items: int, n_sources: int) -> list[str]:
    s = envelope.settings_used
    if s is not None:
        regions = ", ".join(s.regions) if s.regions else "all regions in the register"
        techs = ", ".join(s.technologies) if s.technologies else "all technologies in config/technologies.yaml"
        events = ", ".join(_event_text(e) for e in s.event_types) if s.event_types else "all event types"
        window = f"published in the last {s.recent_months} months"
        origin = "settings saved for this run"
    else:
        regions = envelope.scope.region
        techs = envelope.scope.technology
        events = "all event types"
        window = "the default time window of the filter"
        origin = "default settings (no saved settings in this run)"
    return [
        f"Regions: {regions}",
        f"Technologies: {techs}",
        f"Event types: {events}",
        f"Time window: {window}",
        f"Sources used: {n_sources_with_items} of {n_sources} sources in this run returned items",
        f"Settings: {origin}",
    ]


def _n(count: int, singular: str, plural: Optional[str] = None) -> str:
    """'1 source', '2 sources'."""
    return f"{count} {singular if count == 1 else (plural or singular + 's')}"


def _summary(d: dict) -> list[str]:
    """Templated sentences, filled only with computed numbers."""
    if d["n_items"] == 0:
        return [
            f"No items passed the filter in run {d['run_id']}.",
            f"{_n(d['n_sources'], 'source')} in the run; {d['n_refused']} refused by the compliance gate.",
        ]
    out = [
        f"Run {d['run_id']} found {_n(d['n_items'], 'item')} that passed the filter, from "
        f"{d['n_sources_with_items']} of {_n(d['n_sources'], 'source')}.",
    ]
    named = [(c, n) for c, n in d["by_company"] if c != NOT_STATED]
    if named:
        out.append(f"{_n(len(named), 'company', 'companies')} named; the most frequent is {named[0][0]} "
                   f"({_n(named[0][1], 'item')}).")
    events = [(e, n) for e, n in d["by_event_type"] if e not in (NOT_STATED, "other")]
    general = dict(d["by_event_type"]).get("other", 0)
    if events:
        lead = f"Apart from {_n(general, 'general article')}, the" if general else "The"
        out.append(f"{lead} most common type of news is {events[0][0]} ({_n(events[0][1], 'item')}).")
    elif general:
        out.append(f"All dated news items are general articles ({_n(general, 'item')}); none reports a specific event.")
    out.append(f"{_n(d['n_multi_source_stories'], 'story', 'stories')} seen in two or more independent sources.")
    out.append(
        f"{_n(d['n_refused'], 'source')} refused by the compliance gate; "
        f"{_n(d['n_fallback_items'], 'item')} from switching to other allowed sources."
    )
    # (sources counted above exclude the rows that only record a switching attempt)
    return out


# ---------- main computation ----------

def compute(envelope: OutputEnvelope) -> ReportData:
    """Everything both builders need, computed from the envelope only."""
    check_personal_data(envelope)

    summaries = {s.source_id: s for s in envelope.sources}
    names = {s.source_id: s.name for s in envelope.sources}
    story_sources = _story_sources(envelope)

    def name_of(source_id: Optional[str]) -> str:
        return names.get(source_id, source_id) if source_id else ""

    rows: list[ItemRow] = []
    for item in envelope.items:
        summary = summaries.get(item.source_id)
        rows.append(ItemRow(
            item_id=item.id, title=item.title or "(no title)", company=item.company or NOT_STATED,
            event_type=_event_text(item.event_type), region=item.region or NOT_STATED,
            technology=item.technology or NOT_STATED, product=item.product or NOT_STATED,
            date=item.published_at, label=item.label, url=item.source_url, source_id=item.source_id,
            source_name=item.source_name,
            discovered=bool(summary and summary.kind == "discovered"),
            via_fallback=item.via_fallback, fallback_for=name_of(item.fallback_for) or None,
            story_sources=len(story_sources.get(item.story_id, set())) if item.story_id else 1,
            key_facts=list(item.key_facts),
        ))

    source_rows = [
        SourceRow(
            source_id=s.source_id, name=s.name, kind=s.kind, status=s.status, collected=s.items_collected,
            passed=s.items_passed, note=s.note or "", refused=_is_refused(s), discovered=s.kind == "discovered",
            fallback_for=name_of(s.fallback_for) or None,
        )
        for s in envelope.sources
    ]
    refused = [r for r in source_rows if r.refused]

    # switching: refused source -> the sources that supplied items in its place
    switching: dict[str, set[str]] = {}
    for item in envelope.items:
        if item.via_fallback:
            switching.setdefault(name_of(item.fallback_for) or "(not recorded)", set()).add(item.source_name)
    tried_empty: list[str] = []
    for s in source_rows:
        if s.kind == "fallback" and s.fallback_for:
            if s.passed > 0:
                switching.setdefault(s.fallback_for, set()).add(s.name)
            elif s.fallback_for not in switching:
                tried_empty.append(s.fallback_for)

    items_by_id = {i.id: i for i in envelope.items}
    story_rows: list[StoryRow] = []
    for story in envelope.stories:
        ids = set(story_sources.get(story.story_id, set()))
        if len(ids) < 2:
            continue
        members = [items_by_id[i] for i in story.item_ids if i in items_by_id] or \
                  [i for i in envelope.items if i.story_id == story.story_id]
        story_rows.append(StoryRow(
            story_id=story.story_id, title=story.headline or (members[0].title if members and members[0].title else "(no title)"),
            company=story.company or NOT_STATED, event_type=_event_text(story.event_type),
            source_names=sorted(name_of(i) for i in ids), item_count=len(members),
            fallback_items=sum(1 for m in members if m.via_fallback),
        ))
    story_rows.sort(key=lambda r: (-len(r.source_names), r.title.casefold()))

    by_company = _counts([i.company for i in envelope.items])
    company_events: dict[str, list[str]] = {}
    for item in envelope.items:
        key = item.company or NOT_STATED
        event = _event_text(item.event_type)
        if event not in company_events.setdefault(key, []):
            company_events[key].append(event)

    ranked = _rank(rows)
    candidates = envelope.candidates_considered
    n_candidates = len(candidates) if isinstance(candidates, list) else int(candidates or 0)
    d = dict(
        run_id=envelope.run_id, run_date=envelope.generated_at[:10], generated_at=envelope.generated_at,
        n_items=len(envelope.items), n_sources=sum(1 for s in envelope.sources if s.kind != "fallback"),
        n_sources_with_items=sum(1 for s in envelope.sources if s.items_passed > 0 and s.kind != "fallback"),
        n_refused=len(refused), n_discovered=sum(1 for s in source_rows if s.discovered),
        n_stories=len(envelope.stories), n_multi_source_stories=len(story_rows),
        n_fallback_items=sum(1 for i in envelope.items if i.via_fallback),
        candidates_considered=n_candidates,
        n_companies=len([c for c, _ in by_company if c != NOT_STATED]),
        by_company=by_company,
        by_technology=_counts([i.technology for i in envelope.items]),
        by_event_type=_counts([_event_text(i.event_type) if i.event_type else None for i in envelope.items]),
        by_region=_counts([i.region for i in envelope.items]),
        by_label=_counts([i.label for i in envelope.items]),
    )
    data = ReportData(
        **d,
        company_events=company_events,
        top_items=ranked[:TOP_ITEMS], all_items=ranked, headline_items=ranked[:HEADLINE_ITEMS],
        stories=story_rows, sources=source_rows, refused=refused,
        switching=sorted((k, sorted(v)) for k, v in switching.items()),
        switching_empty=sorted(set(tried_empty) - set(switching)),
        scope_lines=_scope_lines(envelope, d["n_sources_with_items"], d["n_sources"]),
        summary_sentences=_summary(d),
    )
    data.notes = _notes(data)
    return data


def _notes(d: ReportData) -> dict[str, str]:
    """Where each number comes from (speaker notes on slides 2 to 8)."""
    src = f"output/poc_{d.run_id}.json"
    return {
        "summary": f"All numbers are counted from {src}: items = entries in 'items'; sources = entries in "
                   f"'sources'; refused = sources whose note starts with 'refused' or whose status is "
                   f"blocked / needs_permission / unreachable with nothing collected; stories in several "
                   f"sources = stories whose items come from 2 or more distinct source_id values; switching "
                   f"items = items with via_fallback = true. The sentences are fixed templates.",
        "scope": f"Scope lines come from 'settings_used' in {src} (or from 'scope' when no settings were "
                 f"saved). 'Sources used' counts sources with items_passed > 0.",
        "found": f"The 8 items shown are from 'items' in {src}. Ranking rule: items in stories seen in more distinct sources first, then the most recent "
                 "publication date (items without a date last), then title A to Z.",
        "company": f"Counts of the 'company' field of each item in {src}; '{NOT_STATED}' = company not stated "
                   f"on the page. Event types listed are those seen for that company.",
        "tech_event": f"Counts of the 'technology' and 'event_type' fields of each item in {src}. Event types "
                      f"come from fixed patterns in atlas/extract.py; '{NOT_STATED}' = no usable title.",
        "stories": f"Stories from 'stories' in {src}, kept when their items come from 2 or more distinct "
                   f"sources. Items marked 'via switching' have via_fallback = true.",
        "sources": f"One row per entry in 'sources' in {src}. Refused sources keep the reason recorded by the "
                   f"compliance gate. 'Coverage for X came from Y' is built from items with via_fallback = "
                   f"true and their fallback_for field.",
    }


def note_text(row: SourceRow) -> str:
    """Note column of the sources table. A refused source starts with REFUSED and keeps the gate's reason."""
    note = row.note or ""
    if row.refused:
        reason = re.sub(r"^refused\b\s*", "", note, flags=re.IGNORECASE)
        return ("REFUSED " + reason).strip() if reason else f"REFUSED (status: {row.status})"
    return note or "-"


def compliance_lines(d: ReportData) -> list[str]:
    """Lines under the sources table: refused count and switching."""
    if d.refused:
        lines = [f"Refused sources: {len(d.refused)}, marked REFUSED in the table with the reason the "
                 f"compliance gate recorded. They were not contacted and not bypassed."]
    else:
        lines = ["Refused sources: 0."]
    lines += [f"Coverage for {k} came from {', '.join(v)}." for k, v in d.switching]
    lines += [f"Switching was tried for {k}: no items about it were found in other allowed sources."
              for k in d.switching_empty]
    if not d.switching and not d.switching_empty:
        lines.append("No switching was needed in this run.")
    return lines


def item_line(row: ItemRow) -> str:
    """One-line description of an item used by both builders (no link text)."""
    parts = [row.company, row.event_type, row.date_text, row.label]
    if row.marker:
        parts.append(row.marker)
    return " | ".join(parts)


def truncate(text: str, limit: int) -> str:
    """Cut at a word boundary and add an ellipsis if the text is longer than `limit`."""
    text = re.sub(r"\s+", " ", text or "").strip()
    if len(text) <= limit:
        return text
    cut = text[: limit - 1]
    if " " in cut[limit // 2:]:
        cut = cut[: cut.rfind(" ")]
    return cut.rstrip(" ,;:-|") + "…"


# ---------- entry points (parent2.md section 10) ----------

def build_report(envelope: OutputEnvelope, fmt: Literal["pptx", "pdf"]) -> bytes:
    """Build the report for one run as PPTX or PDF bytes. Raises PersonalDataError if an item looks
    like it holds personal data, ValueError for an unknown format."""
    if fmt not in ("pptx", "pdf"):
        raise ValueError(f"unknown report format: {fmt!r} (use 'pptx' or 'pdf')")
    data = compute(envelope)
    if fmt == "pptx":
        from atlas.report.pptx_builder import build_pptx
        return build_pptx(data)
    from atlas.report.pdf_builder import build_pdf
    return build_pdf(data)


def report_path(run_id: str, fmt: str) -> str:
    """Path inside the Volume prefix: reports/report_<run_id>.<fmt>."""
    return f"reports/report_{run_id}.{fmt}"


def _volume_path(relative: str) -> str:
    from atlas.settings import get_settings
    return f"{get_settings().volume_root}/{relative}"


def write_report(run_id: str, fmt: Literal["pptx", "pdf"]) -> str:
    """Read output/poc_<run_id>.json, build the report, upload it to reports/report_<run_id>.<fmt>
    through atlas.storage, and return its full Volume path. Nothing touches local disk."""
    from atlas import storage

    raw = storage.read_json(f"output/poc_{run_id}.json")
    envelope = OutputEnvelope.model_validate(raw)
    data = build_report(envelope, fmt)
    relative = report_path(run_id, fmt)
    storage.write_bytes(relative, data)
    return _volume_path(relative)
