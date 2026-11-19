"""One command runs the whole pipeline.

    python -m atlas.run [--only SOURCE_ID] [--max-items N] [--use-default-settings] [--no-discovery] [--no-fallback]

Per source: gate -> collect -> raw/ -> extract -> clean -> filter -> clean/ + facts/.
Then, if a source was refused (or gave nothing, or was rate limited) and a watch entry follows its company,
the scout switches to coverage from other allowed sources and labels it (via_fallback). Then stories are
built and output/poc_<run_id>.json and logs/<run_id>.json are written. Everything goes to Databricks via
atlas.storage; nothing is written to local disk.

Refusals and switching are findings, not errors: the exit code is 1 only for real errors.
"""
import argparse
import sys
from dataclasses import dataclass, field
from types import SimpleNamespace

from atlas import storage
from atlas.filter import apply_filter
from atlas.models import (
    Candidate, GateDecision, Item, OutputEnvelope, RawItem, RunLog, Scope, ScoutSettings, Source,
    SourceSummary, new_run_id, utc_now_iso,
)
from atlas.storage_check import _local_files

DISCOVERY_MAX_NEW = 60  # new candidates per run: all seeds first, then links found on our own sources
SWITCH_NO_PAGES = "no pages collected"
SWITCH_RATE_LIMITED = "rate limited (429/503)"


def _load_discovery() -> tuple:
    """Ragini's discovery and vetting functions, imported only when discovery is requested."""
    from atlas.scout.discover import discover_candidates
    from atlas.scout.vet import vet_candidate
    return discover_candidates, vet_candidate


def _stages() -> SimpleNamespace:
    """The modules the run uses, imported when a run starts (tests replace this)."""
    from atlas.clean import clean_items
    from atlas.collect import collect_source
    from atlas.compliance import ComplianceGate, load_register
    from atlas.extract import extract_item
    from atlas import review
    from atlas.scout import fallback, settings_store, stories

    return SimpleNamespace(
        ComplianceGate=ComplianceGate, load_register=load_register, collect_source=collect_source,
        extract_item=extract_item, clean_items=clean_items,
        load_settings=settings_store.load_settings, default_settings=settings_store.default_settings,
        load_candidates=settings_store.load_candidates, save_candidates=settings_store.save_candidates,
        load_decisions=settings_store.load_decisions, usable_sources=settings_store.usable_sources,
        load_discovery=_load_discovery, load_fact_decisions=review.load_fact_decisions,
        plan_switching=fallback.plan_switching, collect_fallback_items=fallback.collect_fallback_items,
        apply_fallback_labels=fallback.apply_fallback_labels, build_stories=stories.build_stories,
    )


def _dump(models: list) -> list[dict]:
    return [m.model_dump(mode="json") for m in models]


def _say(message: str) -> None:
    """Progress line, shown immediately. A run takes minutes (3 s between requests), so silence looks like a hang."""
    print(message, flush=True)


@dataclass
class _Outcome:
    summary: SourceSummary
    passed: list[Item] = field(default_factory=list)
    final: list[Item] = field(default_factory=list)  # every cleaned item, passed or not
    switch_reason: str | None = None  # set when this source should be switched away from
    allowed: bool = False


def _process_source(source: Source, st: SimpleNamespace, gate, sources_by_id: dict[str, Source],
                    run_id: str, max_items: int, log: RunLog,
                    settings: ScoutSettings | None = None) -> _Outcome:
    kind = "discovered" if source.origin == "discovered" else "registered"
    decision: GateDecision = gate.check_source(source)
    log.gate_decisions.append(decision)
    if not decision.allowed:
        _say(f"  refused by the compliance gate: {', '.join(decision.reasons)}")
        return _Outcome(SourceSummary(
            source_id=source.source_id, name=source.name, status=source.vetting_status, kind=kind,
            note="refused by compliance gate: " + ", ".join(decision.reasons),
        ), switch_reason="refused by the compliance gate: " + ", ".join(decision.reasons))

    _say(f"  allowed; fetching up to {max_items} pages (3 s between requests)...")
    result = st.collect_source(source, gate, max_items=max_items)
    log.refusals.extend(result.refusals)
    _say(f"  collected {len(result.pages)} page(s) of {result.listing_count} listed; "
         f"extracting (the first page loads the language model, about 15 s)...")

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
    final = apply_filter(cleaned.items, sources_by_id, settings=settings)
    passed = [i for i in final if i.filter and i.filter.passed]

    storage.write_json(f"clean/{source.source_id}/{run_id}.json", _dump(final))
    storage.write_json(f"facts/{source.source_id}/{run_id}.json", _dump(passed))

    log.counts[source.source_id] = {
        "collected": len(result.pages), "clean": len(final), "passed": len(passed),
        "duplicates_dropped": cleaned.duplicates_dropped,
    }
    _say(f"  done: {len(passed)} of {len(final)} item(s) passed the filter")
    note = f"{len(result.refusals)} URL(s) refused during collection" if result.refusals else None
    switch = None
    if any(r.reason == "rate_limited_stop" for r in result.refusals):
        switch = SWITCH_RATE_LIMITED
    elif not result.pages:
        switch = SWITCH_NO_PAGES
    return _Outcome(SourceSummary(
        source_id=source.source_id, name=source.name, status=source.vetting_status, kind=kind,
        items_collected=len(result.pages), items_passed=len(passed), note=note,
    ), passed=passed, final=final, switch_reason=switch, allowed=True)


# ---------- discovery ----------

def _run_discovery(st: SimpleNamespace, sources: list[Source], gate, settings: ScoutSettings,
                   log: RunLog) -> list[Candidate]:
    """Find and vet new candidate sources, save them, return all stored candidates.
    A failure is logged and the run goes on with the candidates already stored."""
    existing = st.load_candidates()
    try:
        discover, vet = st.load_discovery()
        known = {c.domain for c in existing} | {s.url.split("/")[2].removeprefix("www.") for s in sources}
        _say("\nDiscovery: looking for new candidate sources (public pages and robots.txt rules apply)...")
        found = discover(sources, gate, settings, known_domains=known, max_new=DISCOVERY_MAX_NEW)
        vetted: list[Candidate] = []
        for cand in found:
            try:
                vetted.append(vet(cand, gate, settings))
            except Exception as exc:
                log.errors.append(f"discovery: vetting {cand.domain} failed: {type(exc).__name__}: {exc}")
                vetted.append(cand.model_copy(update={"notes": f"vetting failed: {type(exc).__name__}: {exc}"}))
        by_id = {c.candidate_id: c for c in existing}
        by_id.update({c.candidate_id: c for c in vetted})
        merged = list(by_id.values())
        st.save_candidates(merged)
        usable = sum(1 for c in vetted if c.usable)
        line = f"discovery: {len(found)} candidate(s) found, {len(vetted)} vetted, {usable} usable"
        log.notes.append(line)
        _say("  " + line)
        return merged
    except Exception as exc:
        log.errors.append(f"discovery: {type(exc).__name__}: {exc}")
        _say(f"  discovery ERROR: {type(exc).__name__}: {exc}")
        return existing


# ---------- switching ----------

@dataclass
class _Switching:
    rows: list[SourceSummary] = field(default_factory=list)
    items: list[Item] = field(default_factory=list)  # every filtered fallback item (second pass)
    relabelled: dict[str, list[Item]] = field(default_factory=dict)  # source_id -> labelled items


def _run_switching(st: SimpleNamespace, settings: ScoutSettings, gate, outcomes: dict[str, _Outcome],
                   run_sources: list[Source], sources_by_id: dict[str, Source], run_id: str,
                   log: RunLog, paths: list[str]) -> _Switching:
    switching = _Switching()
    triggers = {sid: o.switch_reason for sid, o in outcomes.items() if o.switch_reason}
    if not triggers:
        return switching
    refused_sources = [sources_by_id[sid] for sid in triggers]
    _say(f"\nSwitching: {len(triggers)} source(s) gave no usable coverage "
         f"({', '.join(triggers)}). Looking for the same companies in other sources...")
    entries, refused_by, notes = st.plan_switching(refused_sources, settings.watchlist)
    for note in notes:
        log.notes.append("switching: " + note)
        _say("  " + note)
    if not entries:
        return switching

    allowed = [s for s in run_sources if outcomes[s.source_id].allowed and s.source_id not in triggers]
    already = [i for o in outcomes.values() for i in o.final]
    result, fb_items = st.collect_fallback_items(
        entries, refused_by, allowed, gate, settings, already, refused=refused_sources,
        collect=st.collect_source, extract=st.extract_item)
    log.refusals.extend(result.refusals)

    cleaned = st.clean_items(fb_items)
    fb_final = apply_filter(cleaned.items, sources_by_id, settings=settings)
    fb_final = st.apply_fallback_labels(fb_final, entries, refused_by)
    switching.items = fb_final

    # First pass: items other sources already gave us this run that mention a followed entry.
    for sid, outcome in outcomes.items():
        if outcome.final:
            labelled = st.apply_fallback_labels(outcome.final, entries, refused_by)
            if any(a.via_fallback for a in labelled):
                switching.relabelled[sid] = labelled

    all_labelled = [i for items in switching.relabelled.values() for i in items if i.via_fallback] + \
                   [i for i in fb_final if i.via_fallback]
    for refused_id, reason in triggers.items():
        mine = [i for i in all_labelled if i.fallback_for == refused_id]
        from_sources = list(dict.fromkeys(i.source_name for i in mine))
        names = ", ".join(e.name for e in entries if refused_by.get(e.name) == refused_id)
        if not names:
            continue
        passed = sum(1 for i in mine if i.filter and i.filter.passed)
        note = (f"switched because {reason}; followed {names}; {len(mine)} item(s) from "
                f"{len(from_sources)} other source(s)" + (f": {', '.join(from_sources)}" if from_sources else ""))
        summary = SourceSummary(
            source_id=f"fallback_{refused_id}", name=f"Coverage of {sources_by_id[refused_id].name} (switched)",
            status="working", items_collected=len(mine), items_passed=passed, note=note,
            kind="fallback", fallback_for=refused_id,
        )
        switching.rows.append(summary)
        line = f"Switched: {refused_id} -> {len(mine)} item(s) from {len(from_sources)} other source(s)"
        log.notes.append(line + f" (followed {names}; reason: {reason})")
        _say("  " + line)

        own = [i for i in fb_final if i.fallback_for == refused_id]
        folder = f"fallback_{refused_id}"
        raw = [RawItem(source_id=i.source_id, source_url=i.source_url, title=i.title, published_at_raw=i.published_at,
                       collected_at=i.collected_at, http_status=200, via="html") for i in own]
        storage.write_json(f"raw/{folder}/{run_id}.json", _dump(raw))
        storage.write_json(f"clean/{folder}/{run_id}.json", _dump(own))
        storage.write_json(f"facts/{folder}/{run_id}.json", _dump([i for i in own if i.filter and i.filter.passed]))
        paths += [f"raw/{folder}/{run_id}.json", f"clean/{folder}/{run_id}.json", f"facts/{folder}/{run_id}.json"]
    return switching


# ---------- summary ----------

def _print_summary(run_id: str, summaries: list[SourceSummary], log: RunLog, paths: list[str],
                   new_local: list[str], valid: bool, stories: list, candidates_considered: int) -> None:
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
    switched = [s for s in summaries if s.kind == "fallback"]
    print(f"\nSwitched: {len(switched)}")
    for s in switched:
        print(f"  - {s.fallback_for} -> {s.items_collected} item(s) ({s.items_passed} passed). {s.note}")
    for note in log.notes:
        if note.startswith("discovery") or note.startswith("switching"):
            print(f"  {note}")
    multi = sum(1 for s in stories if len(s.source_ids) >= 2)
    print(f"\nStories: {len(stories)} ({multi} seen in 2 or more sources)")
    print(f"Candidates considered: {candidates_considered}")
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


def _scope(settings: ScoutSettings) -> Scope:
    return Scope(
        technology=", ".join(settings.technologies) if settings.technologies else "industrial compressors",
        region="+".join(settings.regions) if settings.regions else "none",
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m atlas.run")
    parser.add_argument("--only", help="run a single source_id")
    parser.add_argument("--max-items", type=int, default=None,
                        help="pages per source (default: the saved setting, 20 unless changed)")
    parser.add_argument("--use-default-settings", action="store_true",
                        help="ignore the saved settings and use config/scout_settings.yaml")
    parser.add_argument("--no-discovery", action="store_true", help="skip source discovery this run")
    parser.add_argument("--no-fallback", action="store_true", help="do not switch to other sources")
    args = parser.parse_args(argv)

    before = _local_files()
    st = _stages()
    run_id = new_run_id()
    log = RunLog(run_id=run_id, started_at=utc_now_iso())
    paths: list[str] = []

    def put(path: str, obj) -> None:
        storage.write_json(path, obj)
        paths.append(path)

    _say(f"Run {run_id} starting. Connecting to Databricks...")
    storage.ensure_folders()
    try:
        settings = st.default_settings() if args.use_default_settings else st.load_settings()
    except Exception as exc:  # an invalid saved file is stopped on, never replaced by defaults
        print(f"Cannot start: settings could not be loaded: {exc}", file=sys.stderr)
        return 1
    if args.no_fallback:
        settings = settings.model_copy(update={"fallback_enabled": False})
    max_items = args.max_items if args.max_items is not None else settings.max_items_per_source
    _say("Settings: " + ("defaults" if args.use_default_settings else "saved (or defaults if none saved)") +
         f"; regions {'+'.join(settings.regions)}, last {settings.recent_months} months, "
         f"discovery {'on' if settings.discovery_enabled and not args.no_discovery else 'off'}, "
         f"switching {'on' if settings.fallback_enabled else 'off'}.")

    register = st.load_register()
    try:
        gate = st.ComplianceGate(register)
    except RuntimeError as exc:
        print(f"Cannot start: {exc}", file=sys.stderr)
        return 1

    candidates: list[Candidate] = []
    if settings.discovery_enabled and not args.no_discovery:
        candidates = _run_discovery(st, register, gate, settings, log)
    else:
        try:
            candidates = st.load_candidates()
        except Exception as exc:
            log.errors.append(f"candidates could not be loaded: {type(exc).__name__}: {exc}")
    discovered = st.usable_sources(settings, candidates, st.load_decisions() if candidates else [], register)
    sources = register + discovered
    put("source_register/sources.json", _dump(sources))
    if discovered:
        _say(f"{len(discovered)} discovered source(s) are usable under the current settings (not approved by Atlas Copco).")

    selected = [s for s in sources if not args.only or s.source_id == args.only]
    if not selected:
        print(f"No source with source_id '{args.only}' in the register.", file=sys.stderr)
        return 2
    _say(f"{len(selected)} source(s) to check, up to {max_items} items each. "
         f"We wait 3 s between requests, so expect a few minutes.")

    sources_by_id = {s.source_id: s for s in sources}
    summaries: list[SourceSummary] = []
    outcomes: dict[str, _Outcome] = {}

    for number, source in enumerate(selected, 1):
        _say(f"\n[{number}/{len(selected)}] {source.source_id}")
        try:
            outcome = _process_source(source, st, gate, sources_by_id, run_id, max_items, log, settings)
            outcomes[source.source_id] = outcome
            summaries.append(outcome.summary)
            if source.source_id in log.counts:
                paths += [f"raw/{source.source_id}/{run_id}.json", f"clean/{source.source_id}/{run_id}.json",
                          f"facts/{source.source_id}/{run_id}.json"]
        except Exception as exc:  # one failing source must not stop the others
            log.errors.append(f"{source.source_id}: {type(exc).__name__}: {exc}")
            _say(f"  ERROR: {type(exc).__name__}: {exc}")
            summaries.append(SourceSummary(
                source_id=source.source_id, name=source.name, status=source.vetting_status,
                note=f"error: {type(exc).__name__}: {exc}",
                kind="discovered" if source.origin == "discovered" else "registered",
            ))

    switching = _Switching()
    if settings.fallback_enabled:
        try:
            switching = _run_switching(st, settings, gate, outcomes, selected, sources_by_id, run_id, log, paths)
        except Exception as exc:
            log.errors.append(f"switching: {type(exc).__name__}: {exc}")
            _say(f"  switching ERROR: {type(exc).__name__}: {exc}")
    else:
        refused_n = sum(1 for o in outcomes.values() if o.switch_reason)
        if refused_n:
            log.notes.append(f"switching: disabled; {refused_n} source(s) gave no usable coverage")
            _say(f"\nSwitching is off: {refused_n} source(s) gave no usable coverage and nothing replaces them.")

    # Labelled first-pass items replace the unlabelled ones; their clean/ and facts/ files are rewritten.
    for sid, labelled in switching.relabelled.items():
        outcomes[sid].final = labelled
        outcomes[sid].passed = [i for i in labelled if i.filter and i.filter.passed]
        storage.write_json(f"clean/{sid}/{run_id}.json", _dump(labelled))
        storage.write_json(f"facts/{sid}/{run_id}.json", _dump(outcomes[sid].passed))
    summaries.extend(switching.rows)

    all_passed = [i for o in outcomes.values() for i in o.passed]
    all_passed += [i for i in switching.items if i.filter and i.filter.passed]
    # Facts the team denied on the Facts screen stay out of the output (they remain in clean/ with their reasons).
    try:
        decisions = getattr(st, "load_fact_decisions", dict)()
    except Exception as exc:
        decisions = {}
        log.errors.append(f"fact decisions could not be loaded: {type(exc).__name__}: {exc}")
    denied = [i for i in all_passed if decisions.get(i.id) == "denied"]
    if denied:
        log.notes.append(f"{len(denied)} fact(s) left out because the team denied them")
        _say(f"{len(denied)} fact(s) left out because the team denied them.")
    all_passed = [i for i in all_passed if decisions.get(i.id) != "denied"]
    all_passed, story_clusters = st.build_stories(all_passed)

    log.refusals.extend(r for r in gate.refusals if r not in log.refusals)

    envelope = OutputEnvelope(
        run_id=run_id, generated_at=utc_now_iso(), scope=_scope(settings), sources=summaries,
        items=all_passed, stories=story_clusters, settings_used=settings,
        candidates_considered=len(candidates),
    )
    valid = True
    try:
        OutputEnvelope.model_validate(envelope.model_dump(mode="json"))
    except Exception as exc:
        valid = False
        log.errors.append(f"output validation failed: {exc}")
    if valid:
        # Phase 3: every item gets Confirmed / Not confirmed (atlas.validate), and the company-wise index is
        # written (atlas.companies). Websites are not read here: python -m atlas.companies --fetch-profiles.
        try:
            from atlas.companies import build_index
            index, validated = build_index(envelope, decisions)
            envelope = envelope.model_copy(update={"items": validated})
            confirmed = sum(1 for i in validated if i.validation and i.validation.status == "confirmed")
            log.notes.append(f"validation: {confirmed} of {len(validated)} item(s) confirmed; "
                             f"{len(index.companies)} company(ies)")
        except Exception as exc:
            index = None
            log.errors.append(f"validation / company index: {type(exc).__name__}: {exc}")
        put(f"output/poc_{run_id}.json", envelope.model_dump(mode="json"))
        if index is not None:
            put(f"companies/{run_id}/index.json", index.model_dump(mode="json"))

    log.finished_at = utc_now_iso()
    put(f"logs/{run_id}.json", log.model_dump(mode="json"))

    new_local = sorted(_local_files() - before)
    _print_summary(run_id, summaries, log, paths, new_local, valid, story_clusters, len(candidates))
    return 0 if valid and not log.errors and not new_local else 1


if __name__ == "__main__":
    sys.exit(main())
