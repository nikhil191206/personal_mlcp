"""One report per company (phase 3, task 10): a single page, the company profile sheet in Atlas Copco's
market-intelligence format (atlas/report/company_sheet.py), with the report date and the company's contacts
under the title. PDF (reportlab, one landscape A4 page) or PPTX (python-pptx, one 16:9 slide). The full
evidence (every item with its validation, contacts, images, sources) stays in companies/<run_id>/<company_id>.json
and on the Companies page.

Owner: Sachi. Built in memory from a CompanyProfile and its validated items; `write_company_report` uploads
it to reports/companies/<run_id>/<company_id>.<fmt> through atlas.storage. Text comes from fixed templates.
A last check refuses (raises) if a contact email is not a role mailbox or an item holds personal data.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from io import BytesIO
from typing import Literal, Optional

from atlas.models import CompanyIndex, CompanyProfile, Item, OutputEnvelope
from atlas.report.build import EVENT_LABELS, PersonalDataError, check_personal_data
from atlas.report.company_sheet import Sheet, add_sheet_slide, build_sheet, sheet_flowables

Format = Literal["pdf", "pptx"]


@dataclass
class CompanyReportData:
    run_id: str
    profile: CompanyProfile
    items: list[Item]
    criteria: list[str]
    logo_bytes: Optional[bytes] = None
    glance: list[str] = field(default_factory=list)
    sheet: Optional[Sheet] = None


def _n(count: int, one: str, many: Optional[str] = None) -> str:
    return f"{count} {one if count == 1 else (many or one + 's')}"


def check_contacts(profile: CompanyProfile) -> None:
    """Company contacts only: every email must be a role mailbox (info@, sales@ ...)."""
    from atlas.profile import ROLE_MAILBOXES
    for c in profile.contacts:
        if c.kind == "email" and c.value.split("@")[0].lower() not in ROLE_MAILBOXES:
            raise PersonalDataError(f"{profile.name}: contact {c.value!r} is not a role mailbox")


def usable_logo(data: Optional[bytes]) -> Optional[bytes]:
    """The logo bytes if they are a raster image both builders can draw (PNG, JPEG, GIF), else None.
    An SVG or a broken file is left out; the logo link is still listed."""
    if not data:
        return None
    try:
        from PIL import Image as PILImage
        with PILImage.open(BytesIO(data)) as img:
            img.load()
            if img.format not in ("PNG", "JPEG", "GIF"):
                return None
    except Exception:
        return None
    return data


def compute(run_id: str, profile: CompanyProfile, items: list[Item], criteria: list[str],
            logo_bytes: Optional[bytes] = None) -> CompanyReportData:
    check_contacts(profile)
    logo_bytes = usable_logo(logo_bytes)
    mine = [i for i in items if i.id in set(profile.item_ids)]
    check_personal_data(OutputEnvelope(run_id=run_id, generated_at="", sources=[], items=mine))
    mine.sort(key=lambda i: (i.published_at or "", i.title or ""), reverse=True)
    confirmed = sum(1 for i in mine if i.validation and i.validation.status == "confirmed")
    glance = [
        f"{_n(len(mine), 'news item')} in this run, {confirmed} confirmed and {len(mine) - confirmed} not confirmed.",
        f"From {_n(len(profile.source_ids), 'source')}; {_n(len(profile.story_ids), 'story', 'stories')}.",
    ]
    if profile.first_published:
        glance.append(f"Published between {profile.first_published} and {profile.last_published}.")
    if profile.event_types:
        glance.append("Types of news: " + ", ".join(f"{EVENT_LABELS.get(k, k)} ({v})" for k, v in profile.event_types.items()) + ".")
    if profile.technologies:
        glance.append("Technologies: " + ", ".join(f"{k} ({v})" for k, v in profile.technologies.items()) + ".")
    if profile.products:
        glance.append("Products named: " + ", ".join(profile.products) + ".")
    if profile.regions:
        glance.append("Regions: " + ", ".join(f"{k} ({v})" for k, v in profile.regions.items()) + ".")
    glance.append(f"Company website: {profile.profile_status}.")
    sheet = build_sheet(profile, mine, logo_bytes, report_date(run_id))
    return CompanyReportData(run_id, profile, mine, criteria, logo_bytes, glance, sheet)


def report_date(run_id: str) -> str:
    """The run's date as '19 November 2026' (run ids look like 20261119T155035Z); today's date if it is not one."""
    from datetime import datetime, timezone
    try:
        day = datetime.strptime(run_id, "%Y%m%dT%H%M%SZ")
    except ValueError:
        day = datetime.now(timezone.utc)
    return f"{day.day} {day:%B %Y}"


# ---------- PDF: one landscape A4 page ----------

def _pdf(d: CompanyReportData) -> bytes:
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.units import cm
    from reportlab.platypus import SimpleDocTemplate

    margin = 1.2 * cm
    frame_w = landscape(A4)[0] - 2 * margin
    pages: list[int] = []
    buf = BytesIO()
    SimpleDocTemplate(buf, pagesize=landscape(A4), leftMargin=margin, rightMargin=margin, topMargin=margin, bottomMargin=margin,
                      title=f"{d.profile.name} - company profile - {d.sheet.report_date}", author="Group 8, VIT Pune",
                      invariant=1, pageCompression=0).build(sheet_flowables(d.sheet, frame_w),
                                                            onFirstPage=lambda c, doc: pages.append(doc.page),
                                                            onLaterPages=lambda c, doc: pages.append(doc.page))
    if len(pages) != 1:
        raise RuntimeError(f"{d.profile.name}: the profile sheet ran onto {len(pages)} pages; it must fit one")
    return buf.getvalue()


# ---------- PPTX: one 16:9 slide ----------

def _pptx(d: CompanyReportData) -> bytes:
    from pptx import Presentation
    from pptx.util import Inches

    prs = Presentation()
    prs.slide_width, prs.slide_height = Inches(13.333), Inches(7.5)
    add_sheet_slide(prs, d.sheet)
    # the source links behind each news line, for whoever presents the slide
    prs.slides[0].notes_slide.notes_text_frame.text = "\n".join(
        f"{i.title or i.source_name}: {i.source_url}" for i in d.items)
    buf = BytesIO()
    prs.save(buf)
    return buf.getvalue()


# ---------- entry points ----------

def build_company_report(d: CompanyReportData, fmt: Format) -> bytes:
    if fmt == "pdf":
        return _pdf(d)
    if fmt == "pptx":
        return _pptx(d)
    raise ValueError(f"unknown report format: {fmt!r} (use 'pdf' or 'pptx')")


def company_report_path(run_id: str, company_id: str, fmt: str) -> str:
    return f"reports/companies/{run_id}/{company_id}.{fmt}"


def write_company_report(run_id: str, company_id: str, fmt: Format, index: Optional[CompanyIndex] = None,
                         items: Optional[list[Item]] = None) -> str:
    """Build one company's report and upload it to the Volume. Reads companies/<run_id>/ when the index and
    items are not passed in. Returns the Volume path. Nothing touches local disk."""
    from atlas import storage
    from atlas.settings import get_settings

    if index is None:
        index = CompanyIndex.model_validate(storage.read_json(f"companies/{run_id}/index.json"))
    profile = next((p for p in index.companies if p.company_id == company_id), None)
    if profile is None:
        raise KeyError(f"no company {company_id!r} in run {run_id}")
    if items is None:
        raw = storage.read_json(f"companies/{run_id}/{company_id}.json")
        items = [Item.model_validate(i) for i in raw.get("items", [])]
    logo = None
    if profile.logo and profile.logo.stored_path:
        try:
            logo = storage.read_bytes(profile.logo.stored_path)
        except Exception:
            logo = None
    data = build_company_report(compute(run_id, profile, items, index.criteria, logo), fmt)
    relative = company_report_path(run_id, company_id, fmt)
    storage.write_bytes(relative, data)
    return f"{get_settings().volume_root}/{relative}"
