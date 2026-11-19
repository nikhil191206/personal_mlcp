"""The company profile sheet: the first page of every company report, in Atlas Copco's market-intelligence
format (reference: Market_Intelligence_Reference_format.png).

Owner: Sachi. Layout: the company name as the title, the logo top right, and six labelled boxes in two columns:

    Business description and ownership structure | Products, markets and finances
    Technology / product / service description   | Technology assessment by Atlas Copco
    Value for Atlas Copco                        | Links and attachments

Every line is filled from the run's data with fixed templates. Nothing is invented: a field the sources do
not state is written as "not stated in the collected sources", so the analyst can fill it in on the editable
slide. Facts that are not yet confirmed carry a "*". The two judgement boxes (assessment and value) hold the
evidence and the rule-based "why it matters" lines, marked for Atlas Copco to complete.
"""
from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Optional

from atlas.models import CompanyProfile, Item
from atlas.report.brief import WHY
from atlas.report.build import EVENT_LABELS, truncate

TEAL = "0B4F5C"        # label boxes and borders
TITLE_TEAL = "0E5A66"  # the company name
NOTE_GREY = "666666"
NOT_STATED = "not stated in the collected sources"
UNCONFIRMED_MARK = "*"
FOOTNOTE = ("* not yet confirmed (see the evidence pages). Lines marked 'to complete' are for Atlas Copco. "
            "Every fact comes from the linked sources; nothing is estimated.")

MONEY_OR_NUMBER = re.compile(r"\$\s?\d|\d[\d.,]*\s?(?:%|million|billion|bn|m\b|units|employees|cfm|psi|kw|hp|mw)", re.I)
OWNERSHIP_EVENTS = ("acquisition", "partnership", "investment_expansion", "appointment")
TECH_EVENTS = ("product_launch", "regulation_standard", "award", "event", "other")

# Space in each box on the slide, in text lines of the content font (checked by the tests).
CAPACITY = {"business": 10, "products": 10, "technology": 12, "assessment": 12, "value": 6, "links": 6}
CHARS_PER_LINE = 92


@dataclass
class Line:
    text: str
    level: int = 0          # 0 bullet, 1 sub-bullet
    url: Optional[str] = None
    note: bool = False      # grey italic: a gap or an instruction, not a fact
    whole_link: bool = False  # the whole line is the link (Links box); otherwise a small "source" link follows


@dataclass
class Sheet:
    title: str
    website: Optional[str]
    logo_bytes: Optional[bytes]
    sections: dict[str, list[Line]] = field(default_factory=dict)
    footnote: str = FOOTNOTE


SECTION_LABELS = {
    "business": "Business Description and Ownership structure",
    "products": "Products, markets and finances",
    "technology": "Technology/ Product/ Service Description",
    "assessment": "Technology assessment by Atlas Copco",
    "value": "Value for Atlas Copco",
    "links": "Links and attachments",
}
LEFT = ["business", "technology", "value"]
RIGHT = ["products", "assessment", "links"]


def _mark(item: Item) -> str:
    return "" if item.validation and item.validation.status == "confirmed" else UNCONFIRMED_MARK


def _fact_line(item: Item, fact: str, limit: int = 150, level: int = 0) -> Line:
    return Line(f"{truncate(fact, limit)}{_mark(item)}", level=level, url=item.source_url)


def _counts_text(counts: dict[str, int], labels: Optional[dict] = None, limit: int = 4) -> str:
    parts = [f"{(labels or {}).get(k, k)} ({v})" for k, v in list(counts.items())[:limit]]
    return ", ".join(parts)


def fit(lines: list[Line], capacity: int, chars: int = CHARS_PER_LINE) -> list[Line]:
    """Keep lines in order while they fit the box; never cut a line in half."""
    out: list[Line] = []
    used = 0
    for line in lines:
        need = max(1, math.ceil((len(line.text) + 4 * line.level) / chars))
        if used + need > capacity:
            break
        out.append(line)
        used += need
    return out


def lines_needed(lines: list[Line], chars: int = CHARS_PER_LINE) -> int:
    return sum(max(1, math.ceil((len(l.text) + 4 * l.level) / chars)) for l in lines)


def build_sheet(profile: CompanyProfile, items: list[Item], logo_bytes: Optional[bytes] = None) -> Sheet:
    """The six boxes for one company. `items` = this company's validated items, newest first."""
    used_facts: set[str] = set()

    def facts_of(events: tuple[str, ...], n: int, need: Optional[re.Pattern] = None) -> list[tuple[Item, str]]:
        out: list[tuple[Item, str]] = []
        for item in items:
            if (item.event_type or "other") not in events:
                continue
            for fact in item.key_facts:
                if fact in used_facts or (need and not need.search(fact)):
                    continue
                used_facts.add(fact)
                out.append((item, fact))
                break
            if len(out) == n:
                break
        return out

    addresses = [c for c in profile.contacts if c.kind == "address"]
    confirmed = len(profile.confirmed_item_ids)

    # 1. Business description and ownership structure
    business: list[Line] = []
    if addresses:
        a = sorted(addresses, key=lambda c: c.validation.status != "confirmed")[0]
        business.append(Line(f"Office: {truncate(a.value, 120)}{'' if a.validation.status == 'confirmed' else UNCONFIRMED_MARK}",
                             url=a.found_on[0] if a.found_on else None))
    business.append(Line(f"Founded, ownership, employees, revenue: {NOT_STATED} (to complete)", note=True))
    ownership = facts_of(OWNERSHIP_EVENTS, 4)
    if ownership:
        business.append(Line("Ownership, partnerships and investment in the news:"))
        business += [_fact_line(i, f, level=1) for i, f in ownership]
    else:
        business.append(Line("No acquisition, partnership, investment or leadership news in this run.", note=True))

    # 2. Products, markets and finances
    products: list[Line] = []
    products.append(Line("Products named: " + (", ".join(profile.products[:5]) if profile.products else NOT_STATED),
                         note=not profile.products))
    if profile.technologies:
        products.append(Line("Technologies: " + _counts_text(profile.technologies)))
    products.append(Line("Markets (regions in the news): " + (_counts_text(profile.regions) if profile.regions else NOT_STATED),
                         note=not profile.regions))
    figures = facts_of(tuple(EVENT_LABELS), 2, MONEY_OR_NUMBER)
    if figures:
        products.append(Line("Figures stated in the news:"))
        products += [_fact_line(i, f, level=1) for i, f in figures]
    products.append(Line(f"Unit cost, production capacity, customers: {NOT_STATED} (to complete)", note=True))

    # 3. Technology / product / service description
    technology: list[Line] = []
    tech_facts = facts_of(TECH_EVENTS, 5)
    technology += [_fact_line(i, f) for i, f in tech_facts]
    for item in items:
        if item.summary and len(technology) < 6 and item.summary not in used_facts:
            used_facts.add(item.summary)
            technology.append(Line(f"{truncate(item.summary, 150)}{_mark(item)}", url=item.source_url))
    if not technology:
        technology.append(Line(f"Technology description: {NOT_STATED} (to complete)", note=True))

    # 4. Technology assessment by Atlas Copco: evidence for the assessor, not an assessment
    assessment: list[Line] = [Line("To complete by Atlas Copco. Evidence collected:", note=True)]
    assessment.append(Line(f"{len(items)} news item(s) from {len(profile.source_ids)} source(s); {confirmed} confirmed, "
                           f"{len(items) - confirmed} not yet confirmed."))
    criteria = Counter(c.split(" ")[0] for i in items if i.validation for c in i.validation.criteria_met)
    if criteria:
        assessment.append(Line("Confirmed by: " + ", ".join(
            f"{ {'C1': 'two or more websites', 'C2': 'authoritative source', 'C3': 'team review'}.get(k, k)} ({v})"
            for k, v in criteria.items())))
    if profile.event_types:
        assessment.append(Line("Types of news: " + _counts_text(profile.event_types, EVENT_LABELS, 5)))
    if profile.first_published:
        assessment.append(Line(f"News dated {profile.first_published} to {profile.last_published}."))
    if profile.story_ids:
        assessment.append(Line(f"{len(profile.story_ids)} story(ies) seen across sources."))

    # 5. Value for Atlas Copco: the fixed "why it matters" sentence per type of news
    value: list[Line] = [Line("To complete by Atlas Copco. What this type of news usually means:", note=True)]
    for event in profile.event_types:
        if event in WHY:
            value.append(Line(f"{EVENT_LABELS.get(event, event).capitalize()}: {WHY[event]}"))

    # 6. Links and attachments
    links: list[Line] = []
    if profile.website:
        links.append(Line(profile.website, url=profile.website, whole_link=True))
    ranked = sorted(items, key=lambda i: (i.validation is None or i.validation.status != "confirmed"))
    for item in ranked[:3]:
        links.append(Line(f"{truncate(item.title or item.source_name, 80)}{_mark(item)}", url=item.source_url, whole_link=True))
    contacts = [c for c in profile.contacts if c.kind in ("email", "phone")]
    if contacts:
        links.append(Line("Contact: " + ", ".join(
            f"{c.value}{'' if c.validation.status == 'confirmed' else UNCONFIRMED_MARK}" for c in contacts[:3])))
    else:
        links.append(Line(f"Contact: {NOT_STATED}", note=True))
    links.append(Line("Patents: not collected yet (to complete)", note=True))

    sections = {"business": business, "products": products, "technology": technology,
                "assessment": assessment, "value": value, "links": links}
    sections = {k: fit(v, CAPACITY[k]) for k, v in sections.items()}
    return Sheet(title=profile.name, website=profile.website, logo_bytes=logo_bytes, sections=sections)


# ---------- PPTX: one 16:9 slide ----------

def add_sheet_slide(prs, sheet: Sheet) -> None:
    from io import BytesIO

    from pptx.dml.color import RGBColor
    from pptx.enum.dml import MSO_LINE_DASH_STYLE
    from pptx.enum.shapes import MSO_SHAPE
    from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
    from pptx.util import Inches, Pt

    teal, title_teal, grey = (RGBColor.from_string(c) for c in (TEAL, TITLE_TEAL, NOTE_GREY))
    s = prs.slides.add_slide(prs.slide_layouts[6])

    title = s.shapes.add_textbox(Inches(0.35), Inches(0.12), Inches(10.5), Inches(0.75)).text_frame
    title.word_wrap = True
    title.text = sheet.title
    title.paragraphs[0].alignment = PP_ALIGN.LEFT
    run = title.paragraphs[0].runs[0]
    run.font.size, run.font.bold, run.font.color.rgb = Pt(32), True, title_teal

    # logo top right, or a dashed "LOGO" box to fill in
    if sheet.logo_bytes:
        try:
            s.shapes.add_picture(BytesIO(sheet.logo_bytes), Inches(11.35), Inches(0.15), height=Inches(0.6))
        except Exception:
            sheet.logo_bytes = None
    if not sheet.logo_bytes:
        box = s.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(11.35), Inches(0.22), Inches(1.4), Inches(0.42))
        box.fill.background()
        box.line.color.rgb, box.line.dash_style = teal, MSO_LINE_DASH_STYLE.DASH
        box.text_frame.text = "LOGO"
        r = box.text_frame.paragraphs[0].runs[0]
        r.font.size, r.font.color.rgb = Pt(11), teal

    top, heights = 0.95, [2.2, 2.4, 1.4]
    label_w, content_w, gap = 1.3, 4.95, 0.1
    col_x = [0.35, 0.35 + label_w + content_w + gap]
    outer = s.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(0.3), Inches(top - 0.05),
                               Inches(2 * (label_w + content_w) + gap + 0.1), Inches(sum(heights) + 0.1))
    outer.fill.background()
    outer.line.color.rgb, outer.line.width = teal, Pt(1)

    for col, keys in enumerate((LEFT, RIGHT)):
        y = top
        for key, h in zip(keys, heights):
            x = col_x[col]
            label = s.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(x), Inches(y), Inches(label_w), Inches(h - 0.06))
            label.fill.solid()
            label.fill.fore_color.rgb = teal
            label.line.fill.background()
            tf = label.text_frame
            tf.word_wrap, tf.vertical_anchor = True, MSO_ANCHOR.MIDDLE
            tf.text = SECTION_LABELS[key]
            for p in tf.paragraphs:
                for r in p.runs:
                    r.font.size, r.font.bold, r.font.color.rgb = Pt(12), True, RGBColor(0xFF, 0xFF, 0xFF)

            body = s.shapes.add_textbox(Inches(x + label_w + 0.05), Inches(y), Inches(content_w - 0.05), Inches(h - 0.06))
            tf = body.text_frame
            tf.word_wrap = True
            for n, line in enumerate(sheet.sections[key]):
                p = tf.paragraphs[0] if n == 0 else tf.add_paragraph()
                p.level = line.level
                size = Pt(10 if line.level == 0 else 9)
                r = p.add_run()
                r.text = ("▪ " if line.level == 0 else "– ") + line.text
                r.font.size = size
                if line.note:
                    r.font.italic, r.font.color.rgb = True, grey
                if line.url and line.whole_link:
                    r.hyperlink.address = line.url
                elif line.url:
                    src = p.add_run()
                    src.text = "  source"
                    src.font.size = Pt(8)
                    src.hyperlink.address = line.url
            divider = s.shapes.add_connector(1, Inches(x), Inches(y + h - 0.03), Inches(x + label_w + content_w), Inches(y + h - 0.03))
            divider.line.color.rgb = teal
            y += h

    foot = s.shapes.add_textbox(Inches(0.35), Inches(7.08), Inches(12.6), Inches(0.3)).text_frame
    foot.text = sheet.footnote
    r = foot.paragraphs[0].runs[0]
    r.font.size, r.font.italic, r.font.color.rgb = Pt(8), True, grey


# ---------- PDF: one landscape A4 page ----------

def sheet_flowables(sheet: Sheet, frame_w: float) -> list:
    from io import BytesIO
    from xml.sax.saxutils import escape, quoteattr

    from reportlab.lib import colors
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import cm
    from reportlab.platypus import Image, Paragraph, Spacer, Table, TableStyle

    teal = colors.HexColor("#" + TEAL)
    base = getSampleStyleSheet()["BodyText"]
    title = ParagraphStyle("SheetTitle", parent=base, fontName="Helvetica-Bold", fontSize=24, leading=28,
                           textColor=colors.HexColor("#" + TITLE_TEAL))
    label = ParagraphStyle("SheetLabel", parent=base, fontName="Helvetica-Bold", fontSize=9.5, leading=11.5,
                           textColor=colors.white)
    body = ParagraphStyle("SheetBody", parent=base, fontSize=7.8, leading=9.6, spaceAfter=1)
    sub = ParagraphStyle("SheetSub", parent=body, leftIndent=10, fontSize=7.3, leading=9)
    foot = ParagraphStyle("SheetFoot", parent=base, fontSize=6.8, leading=8, textColor=colors.HexColor("#" + NOTE_GREY))

    def para(line: Line) -> Paragraph:
        text = escape(line.text)
        if line.note:
            text = f'<font color="#{NOTE_GREY}"><i>{text}</i></font>'
        if line.url and line.whole_link:
            text = f'<a href={quoteattr(line.url)} color="#0072B2">{text}</a>'
        elif line.url:
            text += f' <a href={quoteattr(line.url)} color="#0072B2"><font size="6.5">source</font></a>'
        return Paragraph(text, sub if line.level else body, bulletText="\u2022" if line.level == 0 else "\u2013")

    head_cells: list = [Paragraph(escape(sheet.title), title)]
    logo = None
    if sheet.logo_bytes:
        try:
            logo = Image(BytesIO(sheet.logo_bytes))
            ratio = logo.imageHeight / float(logo.imageWidth or 1)
            logo.drawHeight = 1.2 * cm
            logo.drawWidth = min(4.5 * cm, logo.drawHeight / ratio if ratio else 4.5 * cm)
        except Exception:
            logo = None
    head = Table([[head_cells[0], logo or Paragraph("LOGO", ParagraphStyle("L", parent=base, textColor=teal, alignment=1))]],
                 colWidths=[frame_w - 5 * cm, 5 * cm])
    head.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("ALIGN", (1, 0), (1, 0), "RIGHT")]
                             + ([] if logo else [("BOX", (1, 0), (1, 0), 0.8, teal)])))

    label_w = 3.1 * cm
    content_w = (frame_w - 2 * label_w) / 2
    rows = []
    for left, right in zip(LEFT, RIGHT):
        rows.append([Paragraph(escape(SECTION_LABELS[left]), label), [para(l) for l in sheet.sections[left]],
                     Paragraph(escape(SECTION_LABELS[right]), label), [para(l) for l in sheet.sections[right]]])
    grid = Table(rows, colWidths=[label_w, content_w, label_w, content_w], rowHeights=[5.5 * cm, 5.7 * cm, 4.1 * cm])
    grid.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, -1), teal), ("BACKGROUND", (2, 0), (2, -1), teal),
        ("VALIGN", (0, 0), (0, -1), "MIDDLE"), ("VALIGN", (2, 0), (2, -1), "MIDDLE"),
        ("VALIGN", (1, 0), (1, -1), "TOP"), ("VALIGN", (3, 0), (3, -1), "TOP"),
        ("BOX", (0, 0), (-1, -1), 1, teal), ("LINEBELOW", (0, 0), (-1, -2), 0.8, teal),
        ("LINEAFTER", (1, 0), (1, -1), 0.8, teal),
        ("LEFTPADDING", (0, 0), (-1, -1), 5), ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
    ]))
    return [head, Spacer(1, 6), grid, Spacer(1, 4), Paragraph(escape(sheet.footnote), foot)]
