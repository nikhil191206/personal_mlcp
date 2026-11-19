"""The company profile sheet (Atlas Copco market-intelligence format): six boxes, nothing invented, fits the slide."""
import io

from pptx import Presentation

from atlas.companies import build_index
from atlas.models import Item, OutputEnvelope, StoryCluster
from atlas.report.company_report import build_company_report, compute
from atlas.report.company_sheet import CAPACITY, LEFT, NOT_STATED, RIGHT, SECTION_LABELS, build_sheet, fit, lines_needed, Line


def item(i: str, url: str, **kw) -> Item:
    base = dict(id=i, source_id=url.split("/")[2], source_name=url.split("/")[2], source_type="trade_news",
                source_url=url, licence_note="l", collected_at="2026-11-01T00:00:00Z", page_fingerprint=i,
                published_at="2026-10-0" + i[-1], company="Borealis Vacuum", title=f"Borealis headline {i}",
                event_type="product_launch", technology="vacuum pump", region="US",
                key_facts=[f"Borealis fact {i} says the new pump delivers 500 cfm."])
    base.update(kw)
    return Item(**base)


def setup():
    items = [item("a1", "https://one.example/a"), item("b2", "https://two.example/b"),
             item("c3", "https://one.example/c", event_type="acquisition",
                  key_facts=["Borealis acquires a pump maker for $40 million."])]
    env = OutputEnvelope(run_id="20261119T000000Z", generated_at="t", sources=[], items=items,
                         stories=[StoryCluster(story_id="s", headline="h", item_ids=["a1", "b2"], source_ids=["x", "y"])])
    index, validated = build_index(env)
    return index, validated


def test_six_boxes_in_the_reference_order():
    assert LEFT == ["business", "technology", "value"] and RIGHT == ["products", "assessment", "links"]
    assert SECTION_LABELS["assessment"] == "Technology assessment by Atlas Copco"
    index, items = setup()
    sheet = build_sheet(index.companies[0], items)
    assert set(sheet.sections) == set(LEFT + RIGHT) and all(sheet.sections.values())


def test_gaps_are_stated_not_invented_and_unconfirmed_facts_are_marked():
    index, items = setup()
    sheet = build_sheet(index.companies[0], items)
    business = " ".join(l.text for l in sheet.sections["business"])
    assert NOT_STATED in business and "acquires a pump maker for $40 million.*" in business
    every = [l.text for lines in sheet.sections.values() for l in lines]
    assert any(t.endswith("500 cfm.") for t in every)  # corroborated by two websites: no star
    assert any("Patents" in l.text and l.note for l in sheet.sections["links"])
    assert all(l.note for l in sheet.sections["assessment"][:1])  # "to complete by Atlas Copco"


def test_every_box_fits_its_space():
    index, items = setup()
    many = items * 8
    sheet = build_sheet(index.companies[0], many)
    for key, lines in sheet.sections.items():
        assert lines_needed(lines) <= CAPACITY[key]
    assert fit([Line("x" * 500)], 3) == []


def test_report_is_one_page_with_date_and_contact():
    index, items = setup()
    d = compute("20261119T155035Z", index.companies[0], items, index.criteria)
    assert d.sheet.report_date == "19 November 2026"
    assert d.sheet.info_line.startswith("Report date: 19 November 2026") and "Contact: " in d.sheet.info_line
    assert NOT_STATED in d.sheet.contact  # no contacts read for this company yet: said, not invented
    prs = Presentation(io.BytesIO(build_company_report(d, "pptx")))
    assert len(prs.slides) == 1
    texts = [sh.text_frame.text for sh in prs.slides[0].shapes if sh.has_text_frame]
    assert d.sheet.info_line in texts
    pdf = build_company_report(d, "pdf")
    assert b"Report date: 19 November 2026" in pdf and b"/Count 1" in pdf


def test_sheet_is_the_only_page_in_both_formats():
    index, items = setup()
    d = compute("20261119T000000Z", index.companies[0], items, index.criteria)
    prs = Presentation(io.BytesIO(build_company_report(d, "pptx")))
    texts = [sh.text_frame.text for sh in prs.slides[0].shapes if sh.has_text_frame]
    assert "Borealis Vacuum" in texts and "LOGO" in texts
    assert all(label in texts for label in SECTION_LABELS.values())
    pdf = build_company_report(d, "pdf")
    assert pdf.startswith(b"%PDF") and b"(Technology)" in pdf and b"(Links and)" in pdf
