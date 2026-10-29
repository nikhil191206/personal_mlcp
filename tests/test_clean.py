"""Tests for atlas/clean.py. Offline, synthetic Item objects only."""
from atlas.clean import clean_items, match_company, normalise_name, normalise_url
from atlas.extract import empty_page_fingerprint
from atlas.models import CleanResult, FilterResult, Item


def make_item(**kw) -> Item:
    base = dict(
        id="abc123def456", source_id="acme_news", source_name="Acme Newsroom", source_type="competitor",
        source_url="https://acme.example/news/a", licence_note="Public web page; facts and links only",
        collected_at="2026-10-29T10:00:00Z", published_at="2026-09-18",
        title="Acme launches oil-free rotary screw compressor", page_fingerprint="a" * 64,
        matched_keywords=["compressor"], key_facts=["Acme launched a new compressor."],
    )
    base.update(kw)
    return Item(**base)


# 1. same URL with tracking params and a trailing slash
def test_same_url_with_tracking_params_is_one_item():
    a = make_item(source_url="https://Acme.example/news/a", page_fingerprint="a" * 64)
    b = make_item(source_url="https://acme.example/news/a/?utm_source=x#top", page_fingerprint="b" * 64)
    result = clean_items([a, b])
    assert isinstance(result, CleanResult)
    assert len(result.items) == 1
    assert result.duplicates_dropped == 1


def test_normalise_url():
    assert normalise_url("https://ACME.example/x/?utm_medium=y&id=3&fbclid=z#frag") == "https://acme.example/x?id=3"
    assert normalise_url("https://acme.example/x?ref=home&gclid=1") == "https://acme.example/x"


# 2. different URLs, same content
def test_same_fingerprint_different_url_is_one_item():
    a = make_item(source_url="https://acme.example/news/a", page_fingerprint="c" * 64)
    b = make_item(source_url="https://acme.example/news/a-copy", page_fingerprint="c" * 64)
    result = clean_items([a, b])
    assert len(result.items) == 1
    assert result.duplicates_dropped == 1


def test_empty_page_fingerprints_compared_by_url_only():
    url_a, url_b = "https://acme.example/news/a", "https://acme.example/news/b"
    a = make_item(source_url=url_a, title=None, page_fingerprint=empty_page_fingerprint(url_a, None))
    b = make_item(source_url=url_b, title=None, page_fingerprint=empty_page_fingerprint(url_b, None))
    assert len(clean_items([a, b]).items) == 2


# 3. the more complete duplicate is kept
def test_more_complete_duplicate_wins():
    sparse = make_item(company=None, technology=None, key_facts=[], collected_at="2026-10-29T09:00:00Z")
    full = make_item(company="Acme", technology="rotary screw compressor", collected_at="2026-10-29T11:00:00Z",
                     source_url="https://acme.example/news/a/")
    result = clean_items([sparse, full])
    assert len(result.items) == 1
    assert result.items[0].technology == "rotary screw compressor"


def test_tie_keeps_earlier_collected():
    late = make_item(collected_at="2026-10-29T12:00:00Z", key_facts=["late"])
    early = make_item(collected_at="2026-10-29T08:00:00Z", key_facts=["early"])
    assert clean_items([late, early]).items[0].key_facts == ["early"]


# 4 and 5. company names
def test_ingersoll_rand_variants():
    items = [
        make_item(source_url=f"https://x.example/{n}", page_fingerprint=str(n) * 64, company=c)
        for n, c in enumerate(["Ingersoll-Rand", "Ingersoll Rand Inc.", "IR", "Ingersol Rand"])
    ]
    assert [i.company for i in clean_items(items).items] == ["Ingersoll Rand"] * 4


def test_kaeser_alias_and_legal_suffix():
    aliases = {"kaeser compressors": "Kaeser Compressors", "kaeser kompressoren": "Kaeser Compressors"}
    assert match_company("Kaeser Kompressoren", aliases) == "Kaeser Compressors"
    assert match_company("Kaeser Compressors, Inc.", aliases) == "Kaeser Compressors"
    assert normalise_name("Sullair, LLC") == "sullair"


# 6. unknown and None
def test_unknown_company_kept_as_written_and_none_stays_none():
    items = [
        make_item(source_url="https://x.example/1", page_fingerprint="1" * 64, company="  Zeta Pneumatics  "),
        make_item(source_url="https://x.example/2", page_fingerprint="2" * 64, company=None),
    ]
    out = clean_items(items).items
    assert out[0].company == "Zeta Pneumatics"
    assert out[1].company is None


# 7. dates
def test_dates_made_iso_month_first_and_garbage_none():
    items = [
        make_item(source_url="https://x.example/1", page_fingerprint="1" * 64, published_at="03/10/2026"),
        make_item(source_url="https://x.example/2", page_fingerprint="2" * 64, published_at="not a date"),
        make_item(source_url="https://x.example/3", page_fingerprint="3" * 64, published_at="2026-09-18"),
        make_item(source_url="https://x.example/4", page_fingerprint="4" * 64, published_at=None),
    ]
    out = clean_items(items).items
    assert [i.published_at for i in out] == ["2026-03-10", None, "2026-09-18", None]


# 8. other fields unchanged, order preserved
def test_other_fields_unchanged_and_order_preserved():
    fr = FilterResult(compressor_related=True, north_america=True, credible_source=True, recent=True, passed=True)
    items = [
        make_item(source_url=f"https://x.example/{n}", page_fingerprint=str(n) * 64, title=f"  Title {n}  ",
                  label="fact" if n == 1 else "claim", filter=fr, matched_keywords=["compressor", "cfm"])
        for n in range(3)
    ]
    out = clean_items(items).items
    assert [i.source_url for i in out] == [f"https://x.example/{n}" for n in range(3)]
    assert [i.title for i in out] == ["Title 0", "Title 1", "Title 2"]
    for before, after in zip(items, out):
        b = before.model_dump(exclude={"title"})
        a = after.model_dump(exclude={"title"})
        assert a == b


# 9. empty list
def test_empty_list():
    result = clean_items([])
    assert result.items == [] and result.duplicates_dropped == 0