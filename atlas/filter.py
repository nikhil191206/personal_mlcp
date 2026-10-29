"""Relevance filter: four transparent yes/no checks per item (parent.md section 10)."""
import re
from datetime import date
from pathlib import Path

import yaml
from dateutil.relativedelta import relativedelta

from atlas.models import FilterResult, Item, Source

ROOT = Path(__file__).resolve().parent.parent
NORTH_AMERICA = {"US", "CA", "MX", "NA"}
CREDIBLE_STATUSES = {"proposed", "approved"}


def _load_keywords(path: str) -> dict[str, list[str]]:
    p = Path(path)
    if not p.is_absolute():
        p = ROOT / p
    with open(p, encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    return {key: list(data.get(key) or []) for key in ("compressor", "industrial", "us_locations")}


def _has_term(text: str, terms: list[str]) -> bool:
    """Case-insensitive whole-word / whole-phrase match."""
    return any(
        re.search(rf"(?<!\w){re.escape(term)}(?!\w)", text, flags=re.IGNORECASE) for term in terms
    )


def _parse_published(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _judge(item: Item, source: Source | None, today: date, recent_months: int,
           compressor_terms: list[str]) -> FilterResult:
    reasons: list[str] = []

    compressor_related = bool(item.matched_keywords) or _has_term(item.title or "", compressor_terms)
    if not compressor_related:
        reasons.append("no_compressor_keyword")

    if source is not None and source.region.upper() in NORTH_AMERICA:
        north_america = True
    else:
        north_america = item.mentions_us_location
    if not north_america:
        reasons.append("not_north_america")

    credible_source = (
        source is not None
        and bool(source.type)
        and source.vetting_status == "working"
        and source.status in CREDIBLE_STATUSES
    )
    if not credible_source:
        reasons.append("source_not_credible")

    published = _parse_published(item.published_at)
    date_missing = published is None
    recent = False
    if published is None:
        reasons.append("date_missing")
    elif published > today:
        date_missing = True
        reasons.extend(["date_missing", "date_in_future"])
    elif published >= today - relativedelta(months=recent_months):
        recent = True
    else:
        reasons.append("too_old")

    return FilterResult(
        compressor_related=compressor_related,
        north_america=north_america,
        credible_source=credible_source,
        recent=recent,
        passed=compressor_related and north_america and credible_source and recent,
        reasons=reasons,
        date_missing=date_missing,
    )


def apply_filter(items: list[Item], sources_by_id: dict[str, Source],
                 today: date | None = None, recent_months: int = 12,
                 keywords_path: str = "config/keywords.yaml") -> list[Item]:
    """Return the items with `.filter` set. Nothing is dropped here; run.py decides what goes where."""
    today = today or date.today()
    compressor_terms = _load_keywords(keywords_path)["compressor"]
    return [
        item.model_copy(update={
            "filter": _judge(item, sources_by_id.get(item.source_id), today, recent_months, compressor_terms)
        })
        for item in items
    ]
