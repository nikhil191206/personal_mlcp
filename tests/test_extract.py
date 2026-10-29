"""Tests for atlas/extract.py. Offline: synthetic HTML only (invented text, no real pages).

Needs Presidio and the spaCy model: python -m spacy download en_core_web_sm
"""
import json
from datetime import date

import pytest

from atlas.extract import (
    SPACY_MODEL, _engines, company_from_source_name, empty_page_fingerprint, extract_item,
    parse_published_date,
)
from atlas.models import FetchedPage, Item, Source, make_item_id

URL = "https://acme.example/news/acme-launches-oil-free-unit"

# A distinctive phrase from the body that must never reach the stored Item (60+ characters).
SECRET_PHRASE = "the quarterly lavender committee reviewed seventeen ceramic teapots slowly"

BODY = f"""
<p>Acme Compressors announced a new oil-free rotary screw compressor for factories in Houston, Texas.</p>
<p>The new unit delivers 500 cfm at 125 psi and uses a variable speed drive to cut energy use by 20%.</p>
<p>The company plans to expand production at its plant in Ohio next year to meet demand from food makers.</p>
<p>Unrelated paragraph: {SECRET_PHRASE} while the office kept working on routine filing tasks.</p>
<p>Subscribe to our newsletter and click here to read more stories from our newsroom team.</p>
"""


def make_source(**kw) -> Source:
    base = dict(
        source_id="acme_news", name="Acme Compressors USA Newsroom", url="https://acme.example/news",
        type="competitor", access_method="html", robots_status="allowed", terms_status="ok",
        vetting_status="working", status="proposed", review_date=date(2026, 10, 29), region="US",
    )
    base.update(kw)
    return Source(**base)


def make_html(title: str = "Acme launches oil-free rotary screw compressor in Texas",
              body: str = BODY, published: str | None = "2026-10-03") -> str:
    meta = f'<meta property="article:published_time" content="{published}">' if published else ""
    return (
        f"<html><head><title>{title}</title>{meta}</head>"
        f"<body><article><h1>{title}</h1>{body}</article></body></html>"
    )


def make_page(html: str, **kw) -> FetchedPage:
    base = dict(source_id="acme_news", url=URL, final_url=URL, status_code=200, html=html,
                fetched_at="2026-10-29T10:00:00Z")
    base.update(kw)
    return FetchedPage(**base)


# 1. good article
def test_good_article():
    item = extract_item(make_page(make_html()), make_source())
    assert isinstance(item, Item)
    assert item.id == make_item_id(URL)
    assert item.title == "Acme launches oil-free rotary screw compressor in Texas"
    assert item.published_at == "2026-10-03"
    assert "compressor" in item.matched_keywords and "oil-free" in item.matched_keywords
    assert item.mentions_us_location is True
    assert item.industrial_hint is True
    assert item.technology == "oil-free rotary screw compressor"
    assert 1 <= len(item.key_facts) <= 3
    assert all(len(f) <= 200 for f in item.key_facts)
    assert not any("subscribe" in f.lower() or "click here" in f.lower() for f in item.key_facts)
    assert item.label == "claim"
    assert item.filter is None
    assert item.collected_at == "2026-10-29T10:00:00Z"
    assert item.personal_data_removed is True


# 2. dates
def test_date_parsing_rules():
    today = date(2026, 10, 29)
    assert parse_published_date("October 3, 2026", today=today) == "2026-10-03"
    assert parse_published_date("Fri, 02 Oct 2026 09:00:00 GMT", today=today) == "2026-10-02"
    assert parse_published_date("10/03/2026", today=today) == "2026-10-03"  # month first (US)
    assert parse_published_date("not a date at all", today=today) is None
    assert parse_published_date("October 2026", today=today) is None  # no day given: not guessed
    assert parse_published_date("2027-01-15", today=today) is None  # future
    assert parse_published_date(None) is None
    assert parse_published_date("") is None


def test_missing_date_uses_listing_date():
    page = make_page(make_html(published=None), listing_published="October 1, 2026")
    assert extract_item(page, make_source()).published_at == "2026-10-01"


def test_garbage_and_missing_dates_stay_none():
    page = make_page(make_html(published=None), listing_published="sometime soon")
    assert extract_item(page, make_source()).published_at is None


def test_fetch_date_is_never_used_as_published_date():
    item = extract_item(make_page(make_html(published=None)), make_source())
    assert item.published_at is None


# 3. personal data
def test_personal_data_removed_from_title_and_facts():
    body = (
        "<p>Acme Compressors said John Smith will lead the new compressor plant in Texas from next month.</p>"
        "<p>Questions about the oil-free compressor can go to john.smith@acme-example.com or 555-123-4567 "
        "during office hours.</p>" + BODY
    )
    html = make_html(title="John Smith to lead Acme compressor plant", body=body)
    item = extract_item(make_page(html), make_source())
    dump = item.model_dump_json()
    assert "John Smith" not in dump
    assert "john.smith@acme-example.com" not in dump
    assert "555-123-4567" not in dump
    assert item.personal_data_removed is True


# 4. no page text stored
def test_no_page_text_in_item():
    item = extract_item(make_page(make_html()), make_source())
    data = item.model_dump(mode="json")
    dump = json.dumps(data)
    assert SECRET_PHRASE not in dump
    assert "lavender committee" not in dump
    assert "html" not in data
    for key, value in data.items():
        if isinstance(value, str) and key not in ("source_url",):
            assert len(value) <= 200, key
        if isinstance(value, list):
            assert all(len(str(v)) <= 200 for v in value), key


# 5. empty / very short page
def test_short_page_returns_item_without_facts():
    html = "<html><head><title>Short note</title></head><body><p>Tiny.</p></body></html>"
    item = extract_item(make_page(html), make_source())
    assert item.key_facts == []
    assert item.matched_keywords == []
    assert item.page_fingerprint == empty_page_fingerprint(URL, "Short note")
    assert item.personal_data_removed is True
    assert item.company == "Acme Compressors"


def test_short_page_non_competitor_has_no_company():
    html = "<html><head><title>Short note</title></head><body><p>Tiny.</p></body></html>"
    item = extract_item(make_page(html), make_source(type="trade_news", name="Trade Weekly"))
    assert item.company is None


# 6. labels
def test_labels_by_source_type():
    page = make_page(make_html())
    assert extract_item(page, make_source(type="government", name="Energy Office")).label == "fact"
    assert extract_item(page, make_source(type="competitor")).label == "claim"
    # trade news without a reporting pattern -> claim
    assert extract_item(page, make_source(type="trade_news", name="Trade Weekly")).label == "claim"


def test_trade_news_reporting_pattern_is_fact():
    html = make_html(title="Acme acquires Beta Compressors to grow its rotary screw range")
    item = extract_item(make_page(html), make_source(type="trade_news", name="Trade Weekly"))
    assert item.label == "fact"


# 7. product and company
def test_product_always_none_and_competitor_company():
    item = extract_item(make_page(make_html()), make_source(name="Kaeser Compressors USA Newsroom"))
    assert item.product is None
    assert item.company == "Kaeser Compressors"


def test_company_from_source_name_variants():
    assert company_from_source_name("Kaeser Compressors USA Newsroom") == "Kaeser Compressors"
    assert company_from_source_name("Atlas Copco USA (local news and updates)") == "Atlas Copco"
    assert company_from_source_name("Sullair (Hitachi Global Air Power) US news") == "Sullair"
    assert company_from_source_name("Acme Press Releases") == "Acme"


# 8. "us" is not a location
def test_lowercase_us_is_not_a_location():
    body = (
        "<p>Contact us to learn how a rotary screw compressor can lower running costs in your workshop.</p>"
        "<p>Our team will help us and you choose the right compressor size, dryer and piping layout.</p>"
        "<p>Many owners tell us they save energy after a simple leak survey of the compressed air system.</p>"
    )
    html = make_html(title="How to size a rotary screw compressor", body=body)
    item = extract_item(make_page(html), make_source())
    assert item.mentions_us_location is False


# 9. small spaCy model
def test_presidio_uses_small_model():
    assert SPACY_MODEL == "en_core_web_sm"
    analyzer, _, nlp = _engines()
    loaded = {lang: m.meta["name"] for lang, m in analyzer.nlp_engine.nlp.items()}
    assert loaded == {"en": "core_web_sm"}
    assert nlp.meta["name"] == "core_web_sm"


# 10. unparseable input
@pytest.mark.parametrize("bad", ["", "   "])
def test_unparseable_page_raises(bad):
    with pytest.raises(ValueError, match="unparseable page"):
        extract_item(make_page(bad), make_source())