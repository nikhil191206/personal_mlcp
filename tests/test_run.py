from datetime import date, timedelta
from types import SimpleNamespace

import pytest

from atlas import run as run_mod
from atlas.models import (
    CleanResult, CollectResult, FetchedPage, GateDecision, Item, OutputEnvelope, Refusal, Source,
)


def make_source(source_id="src_a", **kw) -> Source:
    base = dict(
        source_id=source_id, name=f"{source_id} newsroom", url=f"https://{source_id}.example/news",
        type="competitor", access_method="rss", robots_status="allowed", terms_status="ok",
        vetting_status="working", status="proposed", review_date=date(2026, 10, 29), region="US",
    )
    base.update(kw)
    return Source(**base)


def make_page(source_id, n) -> FetchedPage:
    return FetchedPage(
        source_id=source_id, url=f"https://{source_id}.example/news/{n}",
        final_url=f"https://{source_id}.example/news/{n}", status_code=200, html="<p>secret page text</p>",
        listing_title=f"Title {n}", listing_published="2026-10-01", via="rss",
    )


def make_item(page: FetchedPage, source: Source, compressor=True) -> Item:
    recent = (date.today() - timedelta(days=10)).isoformat()
    return Item(
        id=page.final_url[-12:].rjust(12, "0"), source_id=source.source_id, source_name=source.name,
        source_type=source.type, source_url=page.final_url, licence_note=source.licence_note,
        collected_at=page.fetched_at, published_at=recent, title=page.listing_title,
        page_fingerprint=page.final_url, matched_keywords=["compressor"] if compressor else [],
        mentions_us_location=True,
    )


class FakeGate:
    def __init__(self, sources):
        self.refusals: list[Refusal] = []
        self.blocked = {s.source_id for s in sources if s.vetting_status != "working"}

    def check_source(self, source):
        if source.source_id in self.blocked:
            self.refusals.append(Refusal(source_id=source.source_id, reason="vetting_blocked"))
            return GateDecision(source_id=source.source_id, allowed=False, reasons=["vetting_blocked"])
        return GateDecision(source_id=source.source_id, allowed=True)


@pytest.fixture
def writes(monkeypatch):
    """Capture every storage write; nothing reaches Databricks or disk."""
    store: dict = {}
    monkeypatch.setattr(run_mod.storage, "ensure_folders", lambda: store.setdefault("_folders", True))
    monkeypatch.setattr(run_mod.storage, "write_json", lambda path, obj: store.__setitem__(path, obj))
    return store


def install_stages(monkeypatch, sources, pages_per_source=2, extract=None, collect=None, gate_cls=FakeGate):
    def default_collect(source, gate, max_items=20):
        pages = [make_page(source.source_id, n) for n in range(pages_per_source)]
        return CollectResult(source_id=source.source_id, pages=pages, listing_count=len(pages))

    def default_extract(page, source):
        return make_item(page, source, compressor=not page.final_url.endswith("1"))

    stages = SimpleNamespace(
        ComplianceGate=gate_cls,
        load_register=lambda: sources,
        collect_source=collect or default_collect,
        extract_item=extract or default_extract,
        clean_items=lambda items: CleanResult(items=items, duplicates_dropped=0),
    )
    monkeypatch.setattr(run_mod, "_stages", lambda: stages)


def paths_of(writes, prefix):
    return [p for p in writes if p.startswith(prefix)]


def test_happy_path_two_sources(monkeypatch, writes, capsys):
    sources = [make_source("src_a"), make_source("src_b")]
    install_stages(monkeypatch, sources)
    code = run_mod.main([])
    out = capsys.readouterr().out

    assert code == 0
    assert "source_register/sources.json" in writes
    for prefix in ("raw/src_a/", "raw/src_b/", "clean/src_a/", "clean/src_b/", "facts/src_a/", "facts/src_b/"):
        assert len(paths_of(writes, prefix)) == 1, prefix
    (output_path,) = paths_of(writes, "output/")
    (log_path,) = paths_of(writes, "logs/")
    envelope = OutputEnvelope.model_validate(writes[output_path])
    assert len(envelope.sources) == 2
    # each source: 2 pages, page "...1" has no compressor keyword -> 1 passed
    assert [s.items_collected for s in envelope.sources] == [2, 2]
    assert [s.items_passed for s in envelope.sources] == [1, 1]
    assert writes[log_path]["counts"]["src_a"]["passed"] == 1
    assert "output validated: PASS" in out and "local data check: PASS" in out


def test_output_has_only_passed_clean_has_all(monkeypatch, writes):
    install_stages(monkeypatch, [make_source("src_a")])
    run_mod.main([])
    (output_path,) = paths_of(writes, "output/")
    (clean_path,) = paths_of(writes, "clean/")
    (facts_path,) = paths_of(writes, "facts/")
    assert len(writes[clean_path]) == 2
    assert len(writes[facts_path]) == 1
    assert len(writes[output_path]["items"]) == 1
    failed = [i for i in writes[clean_path] if not i["filter"]["passed"]]
    assert failed and failed[0]["filter"]["reasons"] == ["no_compressor_keyword"]


def test_raw_has_metadata_but_no_page_text(monkeypatch, writes):
    install_stages(monkeypatch, [make_source("src_a")])
    run_mod.main([])
    (raw_path,) = paths_of(writes, "raw/")
    assert writes[raw_path][0]["title"] == "Title 0"
    assert "secret page text" not in str(writes)


def test_refused_source_is_skipped_and_reported(monkeypatch, writes, capsys):
    sources = [make_source("src_a"), make_source("src_blocked", vetting_status="blocked")]
    install_stages(monkeypatch, sources)
    code = run_mod.main([])
    out = capsys.readouterr().out

    assert code == 0  # a blocked source is a finding, not an error
    assert paths_of(writes, "raw/src_blocked/") == []
    (output_path,) = paths_of(writes, "output/")
    blocked = next(s for s in writes[output_path]["sources"] if s["source_id"] == "src_blocked")
    assert "vetting_blocked" in blocked["note"]
    assert "src_blocked: vetting_blocked" in out
    (log_path,) = paths_of(writes, "logs/")
    assert any(r["reason"] == "vetting_blocked" for r in writes[log_path]["refusals"])


def test_extract_error_is_logged_and_run_continues(monkeypatch, writes, capsys):
    def flaky_extract(page, source):
        if page.final_url.endswith("0"):
            raise ValueError("unparseable page")
        return make_item(page, source)

    install_stages(monkeypatch, [make_source("src_a")], extract=flaky_extract)
    code = run_mod.main([])
    out = capsys.readouterr().out

    assert code == 1
    (log_path,) = paths_of(writes, "logs/")
    assert any("ValueError: unparseable page" in e for e in writes[log_path]["errors"])
    (output_path,) = paths_of(writes, "output/")
    assert len(writes[output_path]["items"]) == 1  # the other page still made it
    assert "unparseable page" in out


def test_collector_crash_does_not_stop_other_sources(monkeypatch, writes):
    def collect(source, gate, max_items=20):
        if source.source_id == "src_a":
            raise RuntimeError("boom")
        return CollectResult(source_id=source.source_id, pages=[make_page(source.source_id, 0)], listing_count=1)

    install_stages(monkeypatch, [make_source("src_a"), make_source("src_b")], collect=collect)
    code = run_mod.main([])

    assert code == 1
    assert paths_of(writes, "facts/src_b/")
    (output_path,) = paths_of(writes, "output/")
    summaries = {s["source_id"]: s for s in writes[output_path]["sources"]}
    assert "RuntimeError: boom" in summaries["src_a"]["note"]
    assert summaries["src_b"]["items_passed"] == 1


def test_only_flag_limits_to_one_source(monkeypatch, writes):
    install_stages(monkeypatch, [make_source("src_a"), make_source("src_b")])
    assert run_mod.main(["--only", "src_b"]) == 0
    assert paths_of(writes, "raw/src_a/") == []
    assert paths_of(writes, "raw/src_b/")


def test_unknown_only_returns_2(monkeypatch, writes):
    install_stages(monkeypatch, [make_source("src_a")])
    assert run_mod.main(["--only", "nope"]) == 2
    assert paths_of(writes, "output/") == []


def test_max_items_is_passed_to_collector(monkeypatch, writes):
    seen = {}

    def collect(source, gate, max_items=20):
        seen["max_items"] = max_items
        return CollectResult(source_id=source.source_id)

    install_stages(monkeypatch, [make_source("src_a")], collect=collect)
    run_mod.main(["--max-items", "5"])
    assert seen["max_items"] == 5


def test_missing_contact_email_stops_the_run(monkeypatch, writes, capsys):
    class NoEmailGate:
        def __init__(self, sources):
            raise RuntimeError("CONTACT_EMAIL is not set in .env")

    install_stages(monkeypatch, [make_source("src_a")], gate_cls=NoEmailGate)
    assert run_mod.main([]) == 1
    assert "CONTACT_EMAIL" in capsys.readouterr().err
    assert paths_of(writes, "output/") == []


def test_collection_refusals_reach_the_log(monkeypatch, writes):
    def collect(source, gate, max_items=20):
        return CollectResult(
            source_id=source.source_id, pages=[make_page(source.source_id, 0)], listing_count=2,
            refusals=[Refusal(source_id=source.source_id, url="https://x.example/p", reason="http_404")],
        )

    install_stages(monkeypatch, [make_source("src_a")], collect=collect)
    assert run_mod.main([]) == 0
    (log_path,) = paths_of(writes, "logs/")
    assert [r["reason"] for r in writes[log_path]["refusals"]] == ["http_404"]


def test_no_local_files_written(monkeypatch, writes, tmp_path):
    monkeypatch.chdir(tmp_path)
    install_stages(monkeypatch, [make_source("src_a")])
    run_mod.main([])
    assert list(tmp_path.iterdir()) == []
