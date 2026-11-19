"""Phase 3 tasks 6 and 10: company-wise grouping, and one report per company (PDF and PPTX, in memory)."""
import io

import pytest
from pptx import Presentation

from atlas.companies import attach_profile, build_index, company_id
from atlas.models import CompanyContact, CompanyImage, Item, OutputEnvelope, StoryCluster, Validation
from atlas.profile import ProfileResult
from atlas.report.build import PersonalDataError
from atlas.report.company_report import build_company_report, compute

def _png() -> bytes:
    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGB", (40, 20), (0, 114, 178)).save(buf, format="PNG")
    return buf.getvalue()


PNG_1PX = _png()


def item(i: str, company: str | None, url: str, **kw) -> Item:
    base = dict(id=i, source_id=url.split("/")[2], source_name=url.split("/")[2], source_type="trade_news",
                source_url=url, licence_note="l", collected_at="2026-11-01T00:00:00Z", page_fingerprint=i,
                published_at="2026-10-01", company=company, title=f"Headline {i}", key_facts=[f"Fact for {i}"],
                event_type="product_launch", technology="vacuum pump", region="US")
    base.update(kw)
    return Item(**base)


def envelope() -> OutputEnvelope:
    items = [item("a", "Borealis Vacuum", "https://one.example/a"), item("b", "Borealis Vacuum", "https://two.example/b"),
             item("c", "Cobalt Blowers", "https://one.example/c", event_type="award"), item("d", None, "https://one.example/d")]
    return OutputEnvelope(run_id="20261119T000000Z", generated_at="t", sources=[], items=items,
                          stories=[StoryCluster(story_id="s1", headline="h", item_ids=["a", "b"], source_ids=["x", "y"])])


def test_company_id_slug():
    assert company_id("Kaeser Compressors, Inc.") == "kaeser-compressors-inc"


def test_grouping_and_validation():
    index, items = build_index(envelope())
    assert [p.name for p in index.companies] == ["Borealis Vacuum", "Cobalt Blowers"]
    borealis = index.companies[0]
    assert borealis.item_ids == ["a", "b"] and borealis.confirmed_item_ids == ["a", "b"]
    assert borealis.story_ids == ["s1"] and borealis.event_types == {"product_launch": 2}
    assert index.unattributed_item_ids == ["d"]
    assert index.criteria and all(i.validation for i in items)


def profile_with_contacts(email: str = "info@borealis.example"):
    index, items = build_index(envelope())
    result = ProfileResult(website="https://borealis.example/", status="read 2 page(s) of the company's own website",
                           contacts=[CompanyContact(kind="email", value=email, found_on=["https://borealis.example/"],
                                                    method="mailto_link", validation=Validation())],
                           logo=CompanyImage(kind="logo", url="https://borealis.example/logo.png", source_url="https://borealis.example/"),
                           images=[CompanyImage(kind="image", url="https://borealis.example/pump.jpg", source_url="https://borealis.example/")],
                           dropped_personal_emails=2)
    profile = attach_profile(index.companies[0], result, "companies/r/borealis-vacuum/logo.png")
    return profile, items, index


def test_attach_profile_notes_dropped_personal_emails():
    profile, _, _ = profile_with_contacts()
    assert profile.logo.stored_path == "companies/r/borealis-vacuum/logo.png"
    assert "2 personal email address(es) seen and not kept" in profile.profile_status


@pytest.mark.parametrize("logo", [None, PNG_1PX, b"<svg>not a raster</svg>"])
def test_pdf_and_pptx_reports(logo):
    profile, items, index = profile_with_contacts()
    data = compute("20261119T000000Z", profile, items, index.criteria, logo)
    pdf = build_company_report(data, "pdf")
    assert pdf.startswith(b"%PDF") and b"Borealis Vacuum" in pdf
    pptx = build_company_report(data, "pptx")
    prs = Presentation(io.BytesIO(pptx))
    assert len(prs.slides) == 4  # title, contacts, news, validation rules
    assert len(data.items) == 2 and "2 news items in this run, 2 confirmed" in data.glance[0]


def test_a_personal_email_stops_the_report():
    profile, items, index = profile_with_contacts("jane.doe@borealis.example")
    with pytest.raises(PersonalDataError):
        compute("r", profile, items, index.criteria)


def test_unknown_format():
    profile, items, index = profile_with_contacts()
    with pytest.raises(ValueError):
        build_company_report(compute("r", profile, items, index.criteria), "docx")
