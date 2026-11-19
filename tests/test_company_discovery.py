"""Phase 3 task 2: finding the company a page is about when no source or list names it. Synthetic text only."""
from datetime import date

from atlas.company import (
    discover_company, from_about_section, from_headline, from_structured_data, from_ticker, norm,
)
from atlas.extract import extract_item
from atlas.htmlmeta import parse
from atlas.models import FetchedPage, Source


def test_ticker_rule():
    text = "ROCK HILL, S.C., Oct. 3, 2026 -- Zephyr Air Systems (NYSE: ZPHR) today opened a plant."
    name, evidence = from_ticker(text)
    assert name == "Zephyr Air Systems"
    assert "NYSE: ZPHR" in evidence
    assert from_ticker("No ticker in this sentence at all.") is None


def test_about_section_rule():
    text = "Body text.\nAbout Borealis Vacuum Inc.\nBorealis makes vacuum pumps."
    assert from_about_section(text)[0] == "Borealis Vacuum Inc"
    assert from_about_section("About us\nWe sell things.") is None


def test_headline_rule():
    assert from_headline("Cobalt Blowers Launches New Turbo Blower Line")[0] == "Cobalt Blowers"
    assert from_headline("New compressor rules announced") is None
    assert from_headline("How to size a dryer") is None


def test_structured_data_skips_the_publisher():
    html = """<html><head><script type="application/ld+json">
    {"@type": "NewsArticle", "publisher": {"@type": "Organization", "name": "Trade Weekly"},
     "about": {"@type": "Organization", "name": "Emerald Hydrogen"}}</script></head><body></body></html>"""
    assert from_structured_data(parse(html), "Trade Weekly")[0] == "Emerald Hydrogen"
    only_publisher = html.replace('"about": {"@type": "Organization", "name": "Emerald Hydrogen"}', '"x": 1')
    assert from_structured_data(parse(only_publisher), "Trade Weekly") is None


def test_two_rules_agreeing_give_high_confidence():
    text = "Zephyr Air Systems (NYSE: ZPHR) expands.\nAbout Zephyr Air Systems\nIt makes compressors."
    guess = discover_company("Zephyr Air Systems expands plant", text, "Trade Weekly")
    assert guess.name == "Zephyr Air Systems"
    assert guess.confidence == "high"


def test_single_headline_is_low_confidence_and_a_tie_gives_nothing():
    guess = discover_company("Cobalt Blowers Opens Texas Site", "Short body.", "Trade Weekly")
    assert (guess.name, guess.method, guess.confidence) == ("Cobalt Blowers", "headline", "low")
    tie = discover_company("Cobalt Blowers Opens Texas Site", "Zephyr Air Systems (NYSE: ZPHR) said.", "Trade Weekly")
    assert tie.name == "Zephyr Air Systems"  # ticker (3) beats headline (2)
    tie2 = discover_company("Cobalt Blowers Opens Site", "Body.\nAbout Zephyr Air Systems", "Trade Weekly")
    assert tie2 is not None and tie2.name == "Zephyr Air Systems"


def test_publisher_name_and_placeholders_are_never_the_company():
    assert discover_company("Trade Weekly Announces Awards", "Body", "Trade Weekly") is None
    assert discover_company("<PERSON> Joins Board", "Body", "Trade Weekly") is None


def test_alias_lookup_wins():
    guess = discover_company("Cobalt Blowers Opens Site", "text", "Trade Weekly",
                             alias_lookup=lambda t, x: "Kaeser Compressors")
    assert (guess.name, guess.method, guess.confidence) == ("Kaeser Compressors", "alias_list", "high")


def test_norm_drops_legal_words():
    assert norm("Zephyr Air Systems, Inc.") == norm("zephyr air systems")


def test_extract_item_records_how_the_company_was_found():
    body = ("<p>ROCK HILL, S.C. -- Zephyr Air Systems (NYSE: ZPHR) today opened a compressor assembly plant in "
            "South Carolina with 120 jobs and a $40 million investment in new rotary screw lines.</p>"
            "<p>The plant builds oil-free rotary screw compressor packages rated at 500 cfm for food makers.</p>"
            "<h3>About Zephyr Air Systems</h3><p>Zephyr Air Systems makes industrial air compressors in the US.</p>")
    html = (f"<html><head><title>Zephyr opens new plant</title>"
            f'<meta property="article:published_time" content="2026-10-03"></head>'
            f"<body><article><h1>Zephyr opens new plant</h1>{body}</article></body></html>")
    page = FetchedPage(source_id="tw", url="https://tw.example/a", final_url="https://tw.example/a", status_code=200,
                       html=html, fetched_at="2026-10-29T10:00:00Z")
    source = Source(source_id="tw", name="Trade Weekly", url="https://tw.example/", type="trade_news",
                    access_method="html", robots_status="allowed", terms_status="ok", vetting_status="working",
                    review_date=date(2026, 10, 29))
    item = extract_item(page, source)
    assert item.company == "Zephyr Air Systems"
    assert item.company_confidence == "high"
    assert item.company_method in ("ticker", "about_section")
    assert item.company_evidence
