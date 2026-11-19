"""One report per company (phase 3, task 10): logo, contact details, news and facts with their validation
status, images, sources and the rules used. PDF (reportlab, A4) or PPTX (python-pptx, 16:9).

Owner: Sachi. Built in memory from a CompanyProfile and its validated items; `write_company_report` uploads
it to reports/companies/<run_id>/<company_id>.<fmt> through atlas.storage. Text comes from fixed templates.
A last check refuses (raises) if a contact email is not a role mailbox or an item holds personal data.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from io import BytesIO
from typing import Literal, Optional
from xml.sax.saxutils import escape, quoteattr

from atlas.models import CompanyIndex, CompanyProfile, Item, OutputEnvelope
from atlas.report.build import EVENT_LABELS, PREPARED_FOR, PersonalDataError, check_personal_data, truncate

Format = Literal["pdf", "pptx"]
STATUS_TEXT = {"confirmed": "Confirmed", "not_confirmed": "Not confirmed"}
ROWS_PER_SLIDE = 7


@dataclass
class CompanyReportData:
    run_id: str
    profile: CompanyProfile
    items: list[Item]
    criteria: list[str]
    logo_bytes: Optional[bytes] = None
    glance: list[str] = field(default_factory=list)


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
    return CompanyReportData(run_id, profile, mine, criteria, logo_bytes, glance)


def _status_line(item: Item) -> str:
    v = item.validation
    if v is None:
        return "Not checked"
    detail = "; ".join(v.criteria_met if v.status == "confirmed" else v.reasons)
    return f"{STATUS_TEXT[v.status]}: {detail}" if detail else STATUS_TEXT[v.status]


# ---------- PDF ----------

def _pdf(d: CompanyReportData) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import cm
    from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    page_w, page_h = A4
    margin = 1.8 * cm
    frame_w = page_w - 2 * margin
    base = getSampleStyleSheet()
    h1 = ParagraphStyle("H1", parent=base["Heading1"], fontSize=22, leading=27, spaceAfter=4)
    h2 = ParagraphStyle("H2", parent=base["Heading2"], fontSize=13, leading=16, spaceBefore=10, spaceAfter=6)
    body = ParagraphStyle("Body", parent=base["BodyText"], fontSize=9.5, leading=13)
    small = ParagraphStyle("Small", parent=body, fontSize=8, leading=10, textColor=colors.HexColor("#555555"))
    cell = ParagraphStyle("Cell", parent=body, fontSize=7.5, leading=9.2)
    head = ParagraphStyle("Head", parent=cell, fontName="Helvetica-Bold")

    def p(text: str, style=body) -> Paragraph:
        return Paragraph(escape(text), style)

    def link(text: str, url: Optional[str], style=cell) -> Paragraph:
        if not url:
            return p(text, style)
        return Paragraph(f'<a href={quoteattr(url)} color="#0072B2">{escape(text)}</a>', style)

    def table(header, rows, widths):
        data = [[p(h, head) for h in header]] + [[c if isinstance(c, Paragraph) else p(str(c), cell) for c in r] for r in rows]
        t = Table(data, colWidths=[frame_w * w / sum(widths) for w in widths], repeatRows=1, splitByRow=1)
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#E8E8E8")),
            ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#BBBBBB")),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ]))
        return t

    prof = d.profile
    story: list = []
    if d.logo_bytes:
        try:
            img = Image(BytesIO(d.logo_bytes))
            ratio = img.imageHeight / float(img.imageWidth or 1)
            img.drawWidth = min(5 * cm, 2.2 * cm / ratio if ratio else 5 * cm)
            img.drawHeight = img.drawWidth * ratio
            img.hAlign = "LEFT"
            story += [img, Spacer(1, 6)]
        except Exception:  # an SVG or broken image: the link is still listed below
            pass
    story.append(p(prof.name, h1))
    story.append(link(prof.website or "website not on file", prof.website, body))
    story.append(p(f"Company report, run {d.run_id}", small))
    story.append(p("At a glance", h2))
    story += [Paragraph(escape(line), body, bulletText="•") for line in d.glance]

    story.append(p("Contact details", h2))
    if prof.contacts:
        rows = [[c.kind, c.value, STATUS_TEXT[c.validation.status] + (f": {'; '.join(c.validation.criteria_met or c.validation.reasons)}"),
                 link(truncate(c.found_on[0], 60) if c.found_on else "-", c.found_on[0] if c.found_on else None)]
                for c in prof.contacts]
        story.append(table(["Type", "Detail", "Status", "Where found"], rows, [2, 6, 5, 5]))
    else:
        story.append(p(f"No contact details yet. Company website: {prof.profile_status}."))
    story.append(p("Company contact details only (role mailboxes, main numbers, offices); personal contacts are never kept.", small))

    story.append(p("News and facts", h2))
    if d.items:
        rows = [[i.published_at or "(no date)", EVENT_LABELS.get(i.event_type or "", i.event_type or "-"),
                 link(truncate(i.title or "(no title)", 90), i.source_url),
                 truncate(i.key_facts[0], 160) if i.key_facts else "-", i.label, _status_line(i)] for i in d.items]
        story.append(table(["Date", "Type", "Headline (link)", "Key fact", "Label", "Validation"], rows, [2.5, 2.3, 5, 5.6, 1.3, 4.3]))
    else:
        story.append(p("No items for this company in this run."))

    if prof.logo or prof.images:
        story.append(p("Logo and images (links)", h2))
        rows = [[img.kind, link(truncate(img.url, 70), img.url), link(truncate(img.source_url, 50), img.source_url), img.alt or ""]
                for img in ([prof.logo] if prof.logo else []) + prof.images]
        story.append(table(["Kind", "Image", "Found on", "Description"], rows, [1.5, 6, 5, 4]))
        story.append(p("Only the logo is copied (for identification in this report); other images are links.", small))

    story.append(p("Sources", h2))
    by_source: dict[str, list[Item]] = {}
    for i in d.items:
        by_source.setdefault(i.source_name, []).append(i)
    story.append(table(["Source", "Items", "Confirmed"],
                       [[name, len(its), sum(1 for i in its if i.validation and i.validation.status == "confirmed")]
                        for name, its in sorted(by_source.items())], [8, 2, 2]))
    story.append(p("How items and contacts are validated", h2))
    story += [Paragraph(escape(line), body, bulletText="•") for line in d.criteria]

    def decorate(canvas, doc) -> None:
        canvas.saveState()
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(colors.HexColor("#666666"))
        canvas.drawString(margin, page_h - 1.1 * cm, f"{prof.name}  |  company report  |  run {d.run_id}")
        canvas.drawString(margin, 1.0 * cm, PREPARED_FOR)
        canvas.drawRightString(page_w - margin, 1.0 * cm, f"Page {doc.page}")
        canvas.restoreState()

    buf = BytesIO()
    SimpleDocTemplate(buf, pagesize=A4, leftMargin=margin, rightMargin=margin, topMargin=margin, bottomMargin=margin,
                      title=f"{prof.name} - company report - run {d.run_id}", author="Group 8, VIT Pune",
                      invariant=1).build(story, onFirstPage=decorate, onLaterPages=decorate)
    return buf.getvalue()


# ---------- PPTX ----------

def _pptx(d: CompanyReportData) -> bytes:
    from pptx import Presentation
    from pptx.dml.color import RGBColor
    from pptx.util import Inches, Pt

    prs = Presentation()
    prs.slide_width, prs.slide_height = Inches(13.333), Inches(7.5)
    blank = prs.slide_layouts[6]
    prof = d.profile

    def slide(title: str):
        s = prs.slides.add_slide(blank)
        box = s.shapes.add_textbox(Inches(0.5), Inches(0.3), Inches(12.3), Inches(0.8)).text_frame
        box.text = title
        box.paragraphs[0].runs[0].font.size = Pt(28)
        box.paragraphs[0].runs[0].font.bold = True
        foot = s.shapes.add_textbox(Inches(0.5), Inches(7.0), Inches(12.3), Inches(0.3)).text_frame
        foot.text = PREPARED_FOR
        foot.paragraphs[0].runs[0].font.size = Pt(9)
        foot.paragraphs[0].runs[0].font.color.rgb = RGBColor(0x66, 0x66, 0x66)
        return s

    def lines(s, top, text_lines, size=16, height=5.5):
        tf = s.shapes.add_textbox(Inches(0.5), Inches(top), Inches(12.3), Inches(height)).text_frame
        tf.word_wrap = True
        for n, line in enumerate(text_lines):
            para = tf.paragraphs[0] if n == 0 else tf.add_paragraph()
            para.text = line
            for run in para.runs:
                run.font.size = Pt(size)

    def grid(s, header, rows, widths, top=1.3):
        shape = s.shapes.add_table(len(rows) + 1, len(header), Inches(0.5), Inches(top), Inches(12.3), Inches(0.4 * (len(rows) + 1)))
        t = shape.table
        for c, w in enumerate(widths):
            t.columns[c].width = Inches(12.3 * w / sum(widths))
        for r, row in enumerate([header] + rows):
            for c, value in enumerate(row):
                t.cell(r, c).text = str(value)
                for para in t.cell(r, c).text_frame.paragraphs:
                    for run in para.runs:
                        run.font.size = Pt(11 if r == 0 else 10)

    s = slide(prof.name)
    if d.logo_bytes:
        try:
            s.shapes.add_picture(BytesIO(d.logo_bytes), Inches(10.8), Inches(0.3), height=Inches(0.9))
        except Exception:
            pass
    lines(s, 1.3, [prof.website or "website not on file", f"Company report, run {d.run_id}", ""] + d.glance, size=16)

    s = slide("Contact details")
    if prof.contacts:
        grid(s, ["Type", "Detail", "Status", "Where found"],
             [[c.kind, c.value, STATUS_TEXT[c.validation.status], c.found_on[0] if c.found_on else "-"] for c in prof.contacts[:10]],
             [1.5, 5, 2, 4])
    else:
        lines(s, 1.3, [f"No contact details yet. Company website: {prof.profile_status}."])

    chunks = [d.items[i:i + ROWS_PER_SLIDE] for i in range(0, len(d.items), ROWS_PER_SLIDE)] or [[]]
    for n, chunk in enumerate(chunks, 1):
        s = slide("News and facts" + (f" ({n}/{len(chunks)})" if len(chunks) > 1 else ""))
        if chunk:
            grid(s, ["Date", "Type", "Headline", "Validation"],
                 [[i.published_at or "(no date)", EVENT_LABELS.get(i.event_type or "", "-"), truncate(i.title or "", 80),
                   STATUS_TEXT[i.validation.status] if i.validation else "-"] for i in chunk], [1.4, 1.8, 6.5, 2.6])
            s.notes_slide.notes_text_frame.text = "\n".join(f"{i.title}: {i.source_url}" for i in chunk)
        else:
            lines(s, 1.3, ["No items for this company in this run."])

    s = slide("How items and contacts are validated")
    lines(s, 1.3, d.criteria, size=14)
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
