"""Phase 3 task 3: headings, summary, image link, title and date fallbacks, and the recall pass for short
or table-heavy articles. Synthetic HTML only."""
from datetime import date

from atlas.extract import extract_item
from atlas.models import FetchedPage, Source

URL = "https://tw.example/news/a"
BODY = ("<p>Acme Compressors announced a new oil-free rotary screw compressor for factories in Houston, Texas.</p>"
        "<p>The new unit delivers 500 cfm at 125 psi and uses a variable speed drive to cut energy use by 20%.</p>"
        "<p>The company plans to expand production at its plant in Ohio next year to meet demand.</p>")


def source() -> Source:
    return Source(source_id="tw", name="Trade Weekly", url="https://tw.example/", type="trade_news",
                  access_method="html", robots_status="allowed", terms_status="ok", vetting_status="working",
                  review_date=date(2026, 10, 29))


def page(html: str, **kw) -> FetchedPage:
    return FetchedPage(source_id="tw", url=URL, final_url=URL, status_code=200, html=html,
                       fetched_at="2026-10-29T10:00:00Z", **kw)


def html(head: str = "", body: str = BODY, title: str = "<title>Acme launches oil-free compressor</title>") -> str:
    return f"<html><head>{title}{head}</head><body>{body}</body></html>"


def test_headings_skip_navigation_footer_and_the_headline():
    body = ("<nav><h2>Products</h2></nav><article><h1>Acme launches oil-free compressor</h1>"
            f"<h2>Lower energy use</h2>{BODY}<h2>Availability in Texas</h2><h3>SUBSCRIBE NOW</h3></article>"
            "<footer><h2>Contact us</h2></footer>")
    item = extract_item(page(html(body=body)), source())
    assert item.headings == ["Lower energy use", "Availability in Texas"]


def test_headings_are_scrubbed_and_capped():
    many = "".join(f"<h2>Section number {n} of the release</h2>" for n in range(9))
    body = f"<article><h2>Comments by Jane Marlowe Smith</h2>{many}{BODY}</article>"
    item = extract_item(page(html(body=body)), source())
    assert len(item.headings) == 5
    assert all("Marlowe" not in h for h in item.headings)


def test_summary_and_image_come_from_meta_tags():
    head = ('<meta name="description" content="Acme adds an oil-free unit; call Jane Marlowe Smith at 803-555-0100.">'
            '<meta property="og:image" content="/img/unit.jpg">')
    item = extract_item(page(html(head=head)), source())
    assert item.summary and "803-555-0100" not in item.summary and "Marlowe" not in item.summary
    assert item.image_url == "https://tw.example/img/unit.jpg"


def test_title_falls_back_to_og_title_then_h1():
    item = extract_item(page(html(head='<meta property="og:title" content="Acme unveils dryer">', title="")), source())
    assert item.title == "Acme unveils dryer"
    item = extract_item(page(html(title="", body=f"<article><h1>Acme opens Ohio plant</h1>{BODY}</article>")), source())
    assert item.title == "Acme opens Ohio plant"


def test_date_from_json_ld_when_no_meta_date():
    head = '<script type="application/ld+json">{"@type": "NewsArticle", "datePublished": "2026-09-14T08:00:00Z"}</script>'
    item = extract_item(page(html(head=head)), source())
    assert item.published_at == "2026-09-14"


def test_recall_pass_keeps_a_table_heavy_article():
    rows = "".join(f"<tr><td>Model AC-{n}00 rotary screw compressor</td><td>{n}00 cfm at 125 psi</td></tr>" for n in range(1, 8))
    body = f"<article><h1>Acme compressor range 2026</h1><p>Acme lists its range.</p><table>{rows}</table></article>"
    item = extract_item(page(html(body=body, title="<title>Acme compressor range 2026</title>")), source())
    assert item.key_facts, "facts from the table should be found by the recall pass"


def test_no_page_text_is_stored():
    secret = "the quarterly lavender committee reviewed seventeen ceramic teapots slowly"
    item = extract_item(page(html(body=BODY + f"<p>{secret} while the office kept working.</p>")), source())
    assert secret not in item.model_dump_json()
