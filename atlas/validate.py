"""Information validation: every item and every company contact is Confirmed or Not confirmed.

Owner: Sachi (phase 3, task 7). Pure functions; no network, no storage.

An ITEM is Confirmed when at least one of these holds and nothing blocks it:
    C1  corroborated: the same story was reported by 2 or more independent sources (different websites)
    C2  authoritative: the source reports it as a fact (a government source, or a trade-news report of an
        acquisition, filing, appointment, fine or recall) and the article states its own date
    C3  reviewed: a team member marked the fact Important on the Facts screen
Blocking (any one makes it Not confirmed, whatever else holds):
    B1  the company was found only by a weak rule (low confidence), so we cannot say whose news it is
    B2  the team marked the fact Not important
Every item keeps evidence_urls: its own link plus the links of the other items in its story.

A CONTACT (email, phone, address) is Confirmed when it was read from the company's own website in
structured data (schema.org JSON-LD) or on 2 or more of its pages; otherwise Not confirmed.
"""
from __future__ import annotations

from typing import Optional
from urllib.parse import urlsplit

from atlas.models import CompanyContact, Item, OutputEnvelope, Validation

ITEM_CRITERIA = [
    "C1 corroborated: the same story was reported by 2 or more independent websites",
    "C2 authoritative: a government source, or a trade-news report of a hard event (acquisition, filing, "
    "appointment, fine, recall), with the article's own date",
    "C3 reviewed: a team member marked the fact Important",
    "Blocked if the company was found only by a weak rule (low confidence) or the team marked it Not important",
]
CONTACT_CRITERIA = [
    "A contact is confirmed when it comes from the company's own website, in schema.org data or on 2 or more pages",
]


def site(url: Optional[str]) -> str:
    host = (urlsplit(url or "").hostname or "").lower().removeprefix("www.")
    parts = host.split(".")
    return ".".join(parts[-2:]) if len(parts) >= 2 else host


def validate_item(item: Item, story_items: list[Item], decision: Optional[str] = None) -> Validation:
    """Validation for one item. `story_items` = every item in its story (itself included)."""
    met: list[str] = []
    reasons: list[str] = []
    sites = {site(i.source_url) for i in story_items} | {site(item.source_url)}
    sites.discard("")
    if len(sites) >= 2:
        met.append(f"C1 corroborated by {len(sites)} independent websites")
    else:
        reasons.append("reported by one website only")
    if item.label == "fact" and item.published_at:
        met.append("C2 authoritative source with its own date" if item.source_type == "government"
                   else "C2 trade-news report of a hard event, with its own date")
    elif item.label == "fact":
        reasons.append("a fact-type report, but the article states no date")
    elif item.source_type == "competitor":
        reasons.append("the company's own newsroom (a claim)")
    else:
        reasons.append("reported as a claim, not a hard event")
    if decision == "approved":
        met.append("C3 marked Important by the team")
    blocked = False
    if item.company_confidence == "low":
        reasons.append("company found only by a weak rule; check whose news this is")
        blocked = True
    if decision == "denied":
        reasons.append("marked Not important by the team")
        blocked = True
    evidence = list(dict.fromkeys([item.source_url] + [i.source_url for i in story_items if i.source_url]))
    status = "confirmed" if met and not blocked else "not_confirmed"
    return Validation(status=status, criteria_met=met, reasons=[] if status == "confirmed" else reasons,
                      evidence_urls=evidence)


def validate_items(envelope: OutputEnvelope, decisions: Optional[dict[str, str]] = None) -> list[Item]:
    """A copy of every item in the envelope with `validation` set."""
    decisions = decisions or {}
    by_id = {i.id: i for i in envelope.items}
    story_of: dict[str, list[Item]] = {}
    for story in envelope.stories:
        members = [by_id[i] for i in story.item_ids if i in by_id]
        for member in members:
            story_of[member.id] = members
    return [i.model_copy(update={"validation": validate_item(i, story_of.get(i.id, [i]), decisions.get(i.id))})
            for i in envelope.items]


def validate_contact(contact: CompanyContact, company_site: Optional[str]) -> Validation:
    pages = list(dict.fromkeys(contact.found_on))
    own = [p for p in pages if company_site and site(p) == site(company_site)]
    met: list[str] = []
    reasons: list[str] = []
    if not own:
        reasons.append("not found on the company's own website")
    elif contact.method == "structured_data":
        met.append("in the company's own schema.org data")
    elif len(own) >= 2:
        met.append(f"on {len(own)} pages of the company's own website")
    else:
        reasons.append("seen on one page only")
    status = "confirmed" if met else "not_confirmed"
    return Validation(status=status, criteria_met=met, reasons=[] if met else reasons, evidence_urls=pages)
