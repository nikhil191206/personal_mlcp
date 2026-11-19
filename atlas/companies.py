"""Company-wise view of a run: one profile per company, with validation, contacts, logo and a report.

Owner: Sachi (phase 3, tasks 6, 7, 8 and 10).

    python -m atlas.companies [--run-id RUN_ID] [--fetch-profiles] [--reports pdf|pptx|both] [--only NAME]

1. Reads output/poc_<run_id>.json (the latest run if no id is given) and the team's fact decisions.
2. Validates every item (atlas.validate) and groups the items by company (atlas.clean has already merged
   spellings of the same company). Items with no company go to "unattributed".
3. With --fetch-profiles: reads each company's own website politely (atlas.profile) for contacts, logo and
   images. Websites refused in the source register, or by robots.txt, are not read.
4. Writes companies/<run_id>/index.json, companies/<run_id>/<company_id>.json and the logos to the Volume.
5. With --reports: builds one report per company (atlas.report.company_report) into reports/companies/<run_id>/.
Nothing is written to the laptop.
"""
from __future__ import annotations

import argparse
import re
import sys
from collections import Counter
from typing import Optional

from atlas.models import CompanyIndex, CompanyProfile, Item, OutputEnvelope, utc_now_iso
from atlas.validate import CONTACT_CRITERIA, ITEM_CRITERIA, validate_items

UNATTRIBUTED = "unattributed"
LOGO_EXT = {"image/png": "png", "image/jpeg": "jpg", "image/jpg": "jpg", "image/gif": "gif",
            "image/webp": "webp", "image/svg+xml": "svg"}


def company_id(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.casefold()).strip("-")
    return slug or "company"


def _counts(values: list[Optional[str]]) -> dict[str, int]:
    return dict(Counter(v for v in values if v).most_common())


def group_by_company(items: list[Item], stories) -> tuple[list[CompanyProfile], list[str]]:
    """One profile per company (largest first), and the ids of items without a company."""
    groups: dict[str, list[Item]] = {}
    names: dict[str, str] = {}
    unattributed: list[str] = []
    for item in items:
        if not item.company:
            unattributed.append(item.id)
            continue
        cid = company_id(item.company)
        groups.setdefault(cid, []).append(item)
        names.setdefault(cid, item.company)
    story_by_item = {i: s.story_id for s in stories for i in s.item_ids}
    profiles: list[CompanyProfile] = []
    for cid, members in groups.items():
        dates = sorted(i.published_at for i in members if i.published_at)
        profiles.append(CompanyProfile(
            company_id=cid, name=names[cid],
            item_ids=[i.id for i in members],
            confirmed_item_ids=[i.id for i in members if i.validation and i.validation.status == "confirmed"],
            source_ids=list(dict.fromkeys(i.source_id for i in members)),
            story_ids=list(dict.fromkeys(story_by_item[i.id] for i in members if i.id in story_by_item)),
            event_types=_counts([i.event_type for i in members]),
            technologies=_counts([i.technology for i in members]),
            regions=_counts([i.region for i in members]),
            products=list(dict.fromkeys(i.product for i in members if i.product)),
            first_published=dates[0] if dates else None, last_published=dates[-1] if dates else None,
        ))
    profiles.sort(key=lambda p: (-len(p.item_ids), p.name.casefold()))
    return profiles, unattributed


def build_index(envelope: OutputEnvelope, decisions: Optional[dict[str, str]] = None) -> tuple[CompanyIndex, list[Item]]:
    """The company index and the validated items (validation set on each)."""
    items = validate_items(envelope, decisions)
    profiles, unattributed = group_by_company(items, envelope.stories)
    index = CompanyIndex(run_id=envelope.run_id, generated_at=utc_now_iso(), companies=profiles,
                         unattributed_item_ids=unattributed, criteria=ITEM_CRITERIA + CONTACT_CRITERIA)
    return index, items


def attach_profile(profile: CompanyProfile, result, logo_path: Optional[str]) -> CompanyProfile:
    """Copy what atlas.profile found onto the company profile."""
    update = {"website": result.website, "contacts": result.contacts, "images": result.images,
              "profile_status": result.status, "profile_fetched_at": result.fetched_at}
    if result.logo is not None:
        update["logo"] = result.logo.model_copy(update={"stored_path": logo_path})
    if result.dropped_personal_emails:
        update["profile_status"] = (f"{result.status}; {result.dropped_personal_emails} personal email "
                                    f"address(es) seen and not kept")
    return profile.model_copy(update=update)


def _latest_run_id() -> Optional[str]:
    from atlas import storage
    runs = sorted((n.rstrip("/") for n in storage.list_dir("output") if n.startswith("poc_")), reverse=True)
    return runs[0][4:-5] if runs else None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m atlas.companies")
    parser.add_argument("--run-id", help="the run to use (default: the latest run)")
    parser.add_argument("--fetch-profiles", action="store_true",
                        help="read each company's own website for contacts, logo and images")
    parser.add_argument("--reports", choices=["pdf", "pptx", "both"], help="build one report per company")
    parser.add_argument("--only", help="only this company (name or company id)")
    args = parser.parse_args(argv)

    from atlas import review, storage
    from atlas.storage_check import _local_files

    before = _local_files()
    run_id = args.run_id or _latest_run_id()
    if not run_id:
        print("No run found in output/. Run python -m atlas.run first.", file=sys.stderr)
        return 1
    envelope = OutputEnvelope.model_validate(storage.read_json(f"output/poc_{run_id}.json"))
    try:
        decisions = review.load_fact_decisions()
    except Exception as exc:  # the index is still useful without them
        print(f"note: fact decisions could not be loaded ({type(exc).__name__}); C3 not applied")
        decisions = {}
    index, items = build_index(envelope, decisions)
    if args.only:
        wanted = company_id(args.only)
        index.companies = [p for p in index.companies if p.company_id == wanted]
        if not index.companies:
            print(f"No company '{args.only}' in run {run_id}.", file=sys.stderr)
            return 2
    print(f"Run {run_id}: {len(items)} item(s), {len(index.companies)} company(ies), "
          f"{len(index.unattributed_item_ids)} item(s) without a company.")

    if args.fetch_profiles:
        from atlas.compliance import ComplianceGate, load_register
        from atlas.profile import fetch_profile, load_company_sites

        register = load_register()
        gate = ComplianceGate(register)
        sites = load_company_sites(register)
        site_by_id = {company_id(name): url for name, url in sites.items()}
        updated: list[CompanyProfile] = []
        for profile in index.companies:
            website = site_by_id.get(profile.company_id)
            if not website:
                updated.append(profile.model_copy(update={"profile_status": "not read: no website on file "
                                                          "(add it to config/companies.yaml)"}))
                continue
            print(f"  {profile.name}: reading {website} (robots.txt and a 3 s delay apply)...", flush=True)
            result = fetch_profile(profile.name, website, gate, register)
            logo_path = None
            if result.logo_bytes:
                ext = LOGO_EXT.get(result.logo_type or "", "img")
                logo_path = f"companies/{run_id}/{profile.company_id}/logo.{ext}"
                storage.write_bytes(logo_path, result.logo_bytes)
            updated.append(attach_profile(profile, result, logo_path))
            print(f"    {updated[-1].profile_status}; {len(result.contacts)} contact(s), "
                  f"logo {'stored' if logo_path else 'not stored'}, {len(result.images)} image link(s)")
        index.companies = updated

    storage.write_json(f"companies/{run_id}/index.json", index.model_dump(mode="json"))
    by_id = {i.id: i for i in items}
    for profile in index.companies:
        storage.write_json(f"companies/{run_id}/{profile.company_id}.json", {
            "profile": profile.model_dump(mode="json"),
            "items": [by_id[i].model_dump(mode="json") for i in profile.item_ids if i in by_id],
        })
    print(f"Written to Databricks: companies/{run_id}/index.json and {len(index.companies)} company file(s)")

    if args.reports:
        from atlas.report.company_report import write_company_report
        formats = ["pdf", "pptx"] if args.reports == "both" else [args.reports]
        for profile in index.companies:
            for fmt in formats:
                path = write_company_report(run_id, profile.company_id, fmt, index=index, items=items)
                print(f"  report: {path}")

    new_local = sorted(_local_files() - before)
    print(f"local data check: {'PASS' if not new_local else 'FAIL ' + str(new_local)}")
    return 0 if not new_local else 1


if __name__ == "__main__":
    sys.exit(main())
