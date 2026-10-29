"""One command runs the whole pipeline: python -m atlas.run [--only SOURCE_ID] [--max-items N]

Per source: gate -> collect -> raw/ -> extract -> clean -> filter -> clean/ + facts/.
After all sources: output/poc_<run_id>.json and logs/<run_id>.json. Everything goes to Databricks via
atlas.storage; nothing is written to local disk.
"""
import argparse
import sys
from types import SimpleNamespace

from atlas import storage
from atlas.filter import apply_filter
from atlas.models import (
    GateDecision, Item, OutputEnvelope, RawItem, RunLog, Scope, Source, SourceSummary,
    new_run_id, utc_now_iso,
)
from atlas.storage_check import _local_files


def _stages() -> SimpleNamespace:
    """The teammates' modules, imported when a run starts (tests replace this)."""
    from atlas.clean import clean_items
    from atlas.collect import collect_source
    from atlas.compliance import ComplianceGate, load_register
    from atlas.extract import extract_item

    return SimpleNamespace(
        ComplianceGate=ComplianceGate, load_register=load_register, collect_source=collect_source,
        extract_item=extract_item, clean_items=clean_items,
    )


def _dump(models: list) -> list[dict]:
    return [m.model_dump(mode="json") for m in models]


def _process_source(source: Source, st: SimpleNamespace, gate, sources_by_id: dict[str, Source],
                    run_id: str, max_items: int, log: RunLog) -> tuple[SourceSummary, list[Item]]:
    decision: GateDecision = gate.check_source(source)
    log.gate_decisions.append(decision)
    if not decision.allowed:
        return SourceSummary(
            source_id=source.source_id, name=source.name, status=source.vetting_status,
            note="refused by compliance gate: " + ", ".join(decision.reasons),
        ), []

    result = st.collect_source(source, gate, max_items=max_items)
    log.refusals.extend(result.refusals)

    raw = [
        RawItem(
            source_id=source.source_id, source_url=p.final_url, title=p.listing_title,
            published_at_raw=p.listing_published, collected_at=p.fetched_at,
            http_status=p.status_code, via=p.via,
        )
        for p in result.pages
    ]
    storage.write_json(f"raw/{source.source_id}/{run_id}.json", _dump(raw))

    items: list[Item] = []
    for page in result.pages:
        try:
            items.append(st.extract_item(page, source))
        except Exception as exc:  # recorded, not hidden: it shows in the log and the printed summary
            log.errors.append(f"{source.source_id} {page.final_url}: {type(exc).__name__}: {exc}")

    cleaned = st.clean_items(items)
    final = apply_filter(cleaned.items, sources_by_id)
    passed = [i for i in final if i.filter and i.filter.passed]

    storage.write_json(f"clean/{source.source_id}/{run_id}.json", _dump(final))
    storage.write_json(f"facts/{source.source_id}/{run_id}.json", _dump(passed))

    log.counts[source.source_id] = {
        "collected": len(result.pages), "clean": len(final), "passed": len(passed),
        "duplicates_dropped": cleaned.duplicates_dropped,
    }
    note = f"{len(result.refusals)} URL(s) refused during collection" if result.refusals else None
    return SourceSummary(
        source_id=source.source_id, name=source.name, status=source.vetting_status,
        items_collected=len(result.pages), items_passed=len(passed), note=note,
    ), passed


def _print_summary(run_id: str, summaries: list[SourceSummary], log: RunLog, paths: list[str],
                   new_local: list[str], valid: bool) -> None:
    print(f"\n=== Run {run_id} ===")
    print(f"{'source':<28}{'collected':>10}{'dupes':>7}{'passed':>8}{'dropped':>9}")
    for s in summaries:
        c = log.counts.get(s.source_id)
        if c:
            dropped = c["clean"] - c["passed"]
            print(f"{s.source_id:<28}{c['collected']:>10}{c['duplicates_dropped']:>7}{c['passed']:>8}{dropped:>9}")
    refused = [d for d in log.gate_decisions if not d.allowed]
    print(f"\nBlocked / refused sources: {len(refused)}")
    for d in refused:
        print(f"  - {d.source_id}: {', '.join(d.reasons)}")
    print(f"\nURLs refused during collection: {len(log.refusals)}")
    for r in log.refusals:
        print(f"  - {r.source_id} {r.url or ''} {r.reason}")
    print(f"\nErrors: {len(log.errors)}")
    for e in log.errors:
        print(f"  - {e}")
    print("\nWritten to Databricks:")
    for p in paths:
        print(f"  {p}")
    print(f"\noutput validated: {'PASS' if valid else 'FAIL'}")
    print(f"local data check: {'PASS' if not new_local else 'FAIL ' + str(new_local)}")
    print(f"run_id: {run_id}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m atlas.run")
    parser.add_argument("--only", help="run a single source_id")
    parser.add_argument("--max-items", type=int, default=20)
    args = parser.parse_args(argv)

    before = _local_files()
    st = _stages()
    run_id = new_run_id()
    log = RunLog(run_id=run_id, started_at=utc_now_iso())
    paths: list[str] = []

    def put(path: str, obj) -> None:
        storage.write_json(path, obj)
        paths.append(path)

    storage.ensure_folders()
    sources = st.load_register()
    put("source_register/sources.json", _dump(sources))

    selected = [s for s in sources if not args.only or s.source_id == args.only]
    if not selected:
        print(f"No source with source_id '{args.only}' in the register.", file=sys.stderr)
        return 2

    try:
        gate = st.ComplianceGate(sources)
    except RuntimeError as exc:
        print(f"Cannot start: {exc}", file=sys.stderr)
        return 1

    sources_by_id = {s.source_id: s for s in sources}
    summaries: list[SourceSummary] = []
    all_passed: list[Item] = []

    for source in selected:
        try:
            summary, passed = _process_source(source, st, gate, sources_by_id, run_id, args.max_items, log)
            summaries.append(summary)
            all_passed.extend(passed)
            if source.source_id in log.counts:
                paths += [f"raw/{source.source_id}/{run_id}.json", f"clean/{source.source_id}/{run_id}.json",
                          f"facts/{source.source_id}/{run_id}.json"]
        except Exception as exc:  # one failing source must not stop the others
            log.errors.append(f"{source.source_id}: {type(exc).__name__}: {exc}")
            summaries.append(SourceSummary(
                source_id=source.source_id, name=source.name, status=source.vetting_status,
                note=f"error: {type(exc).__name__}: {exc}",
            ))

    log.refusals.extend(r for r in gate.refusals if r not in log.refusals)

    envelope = OutputEnvelope(run_id=run_id, generated_at=utc_now_iso(), scope=Scope(),
                              sources=summaries, items=all_passed)
    valid = True
    try:
        OutputEnvelope.model_validate(envelope.model_dump(mode="json"))
    except Exception as exc:
        valid = False
        log.errors.append(f"output validation failed: {exc}")
    if valid:
        put(f"output/poc_{run_id}.json", envelope.model_dump(mode="json"))

    log.finished_at = utc_now_iso()
    put(f"logs/{run_id}.json", log.model_dump(mode="json"))

    new_local = sorted(_local_files() - before)
    _print_summary(run_id, summaries, log, paths, new_local, valid)
    return 0 if valid and not log.errors and not new_local else 1


if __name__ == "__main__":
    sys.exit(main())
