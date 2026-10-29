"""Tests for atlas/extract.py. Offline: synthetic HTML only (invented text, no real pages).

Needs Presidio and the spaCy model: python -m spacy download en_core_web_sm
"""
import json
from datetime import date

import pytest

from atlas.extract import (
    SPACY_MODEL, _company_from_orgs, _engines, company_from_source_name, empty_page_fingerprint,
    extract_item, parse_published_date, scrub, split_sentences, strip_site_suffix, trusted_metadata_date,
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

# ---------- regression tests from the live-page review (2026-10-29) ----------

# 11. dates: a bare year in a footer must never become YYYY-01-01
def test_trusted_metadata_date_rules():
    assert trusted_metadata_date(None, "2026-01-01") is None          # footer artefact
    assert trusted_metadata_date(None, "2026-06-24") == "2026-06-24"  # a real dateline from the text
    assert trusted_metadata_date("2026-03-02", "2026-01-01") == "2026-03-02"  # strict result wins
    assert trusted_metadata_date(None, None) is None


def test_footer_year_is_not_a_published_date():
    body = BODY + "<footer><span>© 2026 ACME COMPRESSORS</span></footer>"
    item = extract_item(make_page(make_html(published=None, body=body)), make_source())
    assert item.published_at is None


def test_dateline_in_text_is_still_used():
    body = "<p>Mobile, AL, June 24, 2026 - Acme Compressors expanded its oil-free compressor assembly in Alabama.</p>" + BODY
    item = extract_item(make_page(make_html(published=None, body=body)), make_source())
    assert item.published_at == "2026-06-24"


# 12. title suffix
def test_site_suffix_is_stripped_only_when_it_is_the_site_name():
    assert strip_site_suffix("Sullair OFE1550 Wins Award | Sullair", "Sullair (Hitachi) US news") == "Sullair OFE1550 Wins Award"
    assert strip_site_suffix("Nitrogen Explained | KAESER TALKS SHOP BLOG",
                             "Kaeser Compressors USA (Kaeser Talks Shop blog)") == "Nitrogen Explained"
    assert strip_site_suffix("Atlas wins - Atlas Copco", "Atlas Copco USA (local news)") == "Atlas wins"
    assert strip_site_suffix("Acme wins award - Beta Corp", "Acme Newsroom") == "Acme wins award - Beta Corp"
    assert strip_site_suffix("Plain headline", "Acme Newsroom") == "Plain headline"
    assert strip_site_suffix(None, "Acme") is None


def test_title_suffix_stripped_in_item():
    html = make_html(title="Acme launches oil-free rotary screw compressor in Texas | Acme Compressors USA Newsroom")
    assert extract_item(make_page(html), make_source()).title == "Acme launches oil-free rotary screw compressor in Texas"


# 13. sentence splitting
def test_sentences_do_not_split_after_abbreviations():
    assert split_sentences("Atlas Copco expands U.S. operations in Ohio. It opened a plant.") == [
        "Atlas Copco expands U.S. operations in Ohio.", "It opened a plant."]
    assert split_sentences("Acme Inc. announced a deal. More news follows.") == [
        "Acme Inc. announced a deal.", "More news follows."]
    assert split_sentences("One thing. Two things! Three things?") == ["One thing.", "Two things!", "Three things?"]


def test_key_facts_do_not_repeat_the_headline_or_cut_at_us():
    title = "Acme Group Expands U.S. Operations and Opens Facility in South Carolina"
    body = f"<p>{title}</p><p>Acme Group announced a new oil-free air compressor assembly center in Rock Hill, SC.</p>" + BODY
    item = extract_item(make_page(make_html(title=title, body=body)), make_source())
    assert not any(f.rstrip(".") == "Acme Group Expands U.S" for f in item.key_facts)
    assert not any(f in title for f in item.key_facts)
    assert any("Rock Hill" in f for f in item.key_facts)


# 14. company: known names first, never a one-off spaCy guess
def test_company_from_alias_table_for_trade_news():
    html = make_html(title="ZEKS Launches Next-Generation Dryers for Greater Energy Savings",
                     body="<p>ZEKS Compressed Air Solutions introduced new refrigerated air dryers for compressed air systems in factories.</p>" + BODY)
    item = extract_item(make_page(html), make_source(type="trade_news", name="Trade Weekly"))
    assert item.company == "ZEKS Compressed Air Solutions"


def test_one_off_org_guess_is_not_used():
    text = "Acme Industries brought partners together for a distributor meeting this week."
    assert _company_from_orgs("Unleash Prosperity and Security For Everyone", text, "Trade Weekly") is None
    html = make_html(title="Greater Energy Savings Arrive", body="<p>New refrigerated compressed air dryers cut energy use in plants.</p>" + BODY)
    item = extract_item(make_page(html), make_source(type="trade_news", name="Trade Weekly"))
    assert item.company is None


# 15. personal-data scrub keeps known companies and places
def test_scrub_keeps_known_companies_and_places_but_removes_people():
    assert scrub("Hertz Kompressoren brought together distributors in Rock Hill, South Carolina.") == \
        "Hertz Kompressoren brought together distributors in Rock Hill, South Carolina."
    out = scrub("John Smith joined Hertz Kompressoren in Rock Hill.")
    assert "John Smith" not in out and "<PERSON>" in out
    assert "Hertz Kompressoren" in out and "Rock Hill" in out


# 16. labels: only narrow reporting patterns make trade news a "fact"
def test_generic_words_do_not_make_trade_news_a_fact():
    body = "<p>The new compressor meets the industry standard and follows the usual rule for safe installation in plants.</p>" + BODY
    html = make_html(title="Acme unveils a new rotary screw compressor", body=body)
    assert extract_item(make_page(html), make_source(type="trade_news", name="Trade Weekly")).label == "claim"


# 17. technology labels for screw compressors
def test_screw_air_compressor_labels():
    body = (
        "<p>Acme expanded assembly of its 90-250 HP oil-injected screw air compressors in Alabama this year.</p>"
        "<p>The company said the plant in Mobile will add shifts to meet demand from factories across the region.</p>"
        "<p>Local suppliers will provide housings and piping for the new production line over the coming months.</p>"
    )
    html = make_html(title="Acme expands assembly of screw air compressors", body=body)
    assert extract_item(make_page(html), make_source()).technology == "oil-injected rotary screw compressor"


# 18. a surname that stands alone after the full name must not leak
def test_lone_surname_is_redacted_after_full_name():
    body = (
        "<p>Acme Compressors welcomed Sarah Mitchell as director of marketing for its compressor business in Texas.</p>"
        "<p>Mitchell will lead product launches for the oil-free rotary screw compressor range across the region.</p>"
        "<p>The company said Mitchell brings fifteen years of experience in industrial sales to the new role.</p>"
    )
    html = make_html(title="Acme welcomes Sarah Mitchell as marketing director", body=body)
    item = extract_item(make_page(html), make_source())
    dump = item.model_dump_json()
    assert "Mitchell" not in dump and "Sarah" not in dump
    assert item.title is not None and "<PERSON>" in item.title
    assert "Acme" in item.title


def test_common_words_mislabelled_as_names_are_not_redacted_everywhere():
    # "energy" appears in lower case, so it is never turned into a name token
    from atlas.extract import person_name_tokens, redact_names
    tokens = person_name_tokens("John Smith saves energy with the new compressor. Smith likes energy.")
    assert "Smith" in tokens and "John" in tokens
    assert redact_names("Smith saves energy", tokens) == "<PERSON> saves energy"
    assert redact_names("nothing to hide", set()) == "nothing to hide"


# 19. shouted navigation labels are not facts
def test_all_caps_labels_are_not_key_facts():
    body = BODY + "<p>OUR DIGITAL PARTNERS</p><p>THE NEW OIL-FREE COMPRESSOR IS HERE TODAY FOR ALL FACTORIES</p>"
    item = extract_item(make_page(make_html(body=body)), make_source())
    assert not any(f.isupper() for f in item.key_facts)
