from datetime import date

from atlas.filter import apply_filter
from atlas.models import Item, Source

TODAY = date(2026, 10, 29)


def make_source(**kw) -> Source:
    base = dict(
        source_id="acme_news", name="Acme Newsroom", url="https://acme.example/news",
        type="competitor", access_method="rss", robots_status="allowed", terms_status="ok",
        vetting_status="working", status="proposed", review_date=date(2026, 10, 29), region="US",
    )
    base.update(kw)
    return Source(**base)


def make_item(**kw) -> Item:
    base = dict(
        id="abc123def456", source_id="acme_news", source_name="Acme Newsroom", source_type="competitor",
        source_url="https://acme.example/news/a", licence_note="Public web page; facts and links only",
        collected_at="2026-10-29T10:00:00Z", published_at="2026-09-18",
        title="Acme launches oil-free rotary screw compressor in Texas",
        page_fingerprint="f" * 64, matched_keywords=["compressor", "oil-free"], mentions_us_location=True,
    )
    base.update(kw)
    return Item(**base)


def run(item: Item, source: Source | None = None, **kw) -> Item:
    sources = {"acme_news": source or make_source()}
    return apply_filter([item], sources, today=TODAY, **kw)[0]


def test_happy_path_passes():
    out = run(make_item())
    assert out.filter.passed is True
    assert out.filter.reasons == []
    assert out.filter.date_missing is False


def test_no_compressor_keyword():
    out = run(make_item(matched_keywords=[], title="Acme opens a new office"))
    assert out.filter.compressor_related is False
    assert out.filter.passed is False
    assert out.filter.reasons == ["no_compressor_keyword"]


def test_title_keyword_counts_when_matched_keywords_empty():
    out = run(make_item(matched_keywords=[], title="New Compressor range announced"))
    assert out.filter.compressor_related is True


def test_title_match_is_whole_word():
    out = run(make_item(matched_keywords=[], title="Decompressor-free office tour"))
    assert out.filter.compressor_related is False


def test_non_us_source_needs_us_mention():
    src = make_source(region="DE")
    assert run(make_item(mentions_us_location=False), src).filter.reasons == ["not_north_america"]
    assert run(make_item(mentions_us_location=True), src).filter.passed is True


def test_canada_source_counts_as_north_america():
    out = run(make_item(mentions_us_location=False), make_source(region="CA"))
    assert out.filter.north_america is True


def test_blocked_source_not_credible():
    out = run(make_item(), make_source(vetting_status="blocked"))
    assert out.filter.credible_source is False
    assert "source_not_credible" in out.filter.reasons
    assert out.filter.passed is False


def test_needs_permission_status_not_credible():
    out = run(make_item(), make_source(status="needs_permission"))
    assert out.filter.credible_source is False


def test_approved_source_credible():
    assert run(make_item(), make_source(status="approved")).filter.credible_source is True


def test_unknown_source_not_credible_and_falls_back_to_item_signal():
    out = apply_filter([make_item(source_id="mystery")], {"acme_news": make_source()}, today=TODAY)[0]
    assert out.filter.credible_source is False
    assert out.filter.north_america is True  # from mentions_us_location only
    assert out.filter.passed is False


def test_too_old():
    out = run(make_item(published_at="2025-09-29"))  # 13 months before TODAY
    assert out.filter.recent is False
    assert out.filter.reasons == ["too_old"]
    assert out.filter.date_missing is False


def test_exactly_twelve_months_passes():
    assert run(make_item(published_at="2025-10-29")).filter.recent is True


def test_today_is_recent():
    assert run(make_item(published_at="2026-10-29")).filter.recent is True


def test_missing_date():
    out = run(make_item(published_at=None))
    assert out.filter.recent is False
    assert out.filter.date_missing is True
    assert out.filter.reasons == ["date_missing"]
    assert out.filter.passed is False


def test_unparseable_date_is_missing():
    out = run(make_item(published_at="last Tuesday"))
    assert out.filter.date_missing is True


def test_future_date_fails():
    out = run(make_item(published_at="2026-12-01"))
    assert out.filter.recent is False
    assert out.filter.date_missing is True
    assert out.filter.reasons == ["date_missing", "date_in_future"]


def test_recent_months_is_configurable():
    out = run(make_item(published_at="2026-01-15"), recent_months=6)
    assert out.filter.recent is False
    assert out.filter.reasons == ["too_old"]


def test_all_failures_listed_in_check_order():
    item = make_item(matched_keywords=[], title="Quarterly results", mentions_us_location=False,
                     published_at="2020-01-01")
    out = run(item, make_source(region="DE", vetting_status="blocked"))
    assert out.filter.reasons == [
        "no_compressor_keyword", "not_north_america", "source_not_credible", "too_old",
    ]


def test_industrial_hint_never_changes_passed():
    assert run(make_item(industrial_hint=True)).filter.passed is True
    assert run(make_item(industrial_hint=False)).filter.passed is True
    assert run(make_item(industrial_hint=True, matched_keywords=[], title="Office party")).filter.passed is False


def test_other_fields_untouched_and_input_not_mutated():
    item = make_item()
    out = run(item)
    assert item.filter is None
    assert out.model_dump(exclude={"filter"}) == item.model_dump(exclude={"filter"})


def test_nothing_dropped():
    items = [make_item(id="1"), make_item(id="2", matched_keywords=[], title="Office party")]
    out = apply_filter(items, {"acme_news": make_source()}, today=TODAY)
    assert [i.id for i in out] == ["1", "2"]
    assert [i.filter.passed for i in out] == [True, False]
