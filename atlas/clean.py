"""Cleaner: removes duplicates, makes dates ISO and matches company-name variants.

Owner: Sachi. Spec: sachi.md task S2.

Works only on Item objects (no page text exists any more at this point). Nothing is written to disk.
Only `published_at`, `company` and whitespace around `title` are changed; every other field is left
exactly as extract.py produced it.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Optional
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import yaml
from rapidfuzz import fuzz, process

from atlas.extract import empty_page_fingerprint, parse_published_date
from atlas.models import CleanResult, Item

ROOT = Path(__file__).resolve().parent.parent

TRACKING_PARAMS = {"fbclid", "gclid", "ref"}
LEGAL_SUFFIXES = {
    "inc", "incorporated", "llc", "ltd", "limited", "co", "company", "corp", "corporation",
    "ab", "gmbh", "plc", "sa", "ag",
}
FUZZY_MIN_SCORE = 92


# ---------- URLs ----------

def normalise_url(url: str) -> str:
    """Comparison key for deduping. Lower-case host, no fragment, no tracking params, no trailing slash.
    The item's source_url itself is never changed."""
    parts = urlsplit(url.strip())
    query = [
        (k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True)
        if not k.lower().startswith("utm_") and k.lower() not in TRACKING_PARAMS
    ]
    path = parts.path.rstrip("/")
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), path, urlencode(query), ""))


# ---------- company names ----------

def normalise_name(name: str) -> str:
    """Casefold, drop punctuation, collapse spaces, drop trailing legal suffixes (Inc, LLC, Co, AB...)."""
    tokens = re.sub(r"[^\w\s]", " ", name.casefold()).split()
    while tokens and tokens[-1] in LEGAL_SUFFIXES:
        tokens.pop()
    return " ".join(tokens)


def _resolve(path: str) -> Path:
    p = Path(path)
    return p if p.is_absolute() else ROOT / p


def load_aliases(path: str = "config/aliases.yaml") -> dict[str, str]:
    """Map every normalised canonical name and variant to its canonical name."""
    with open(_resolve(path), encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    lookup: dict[str, str] = {}
    for canonical, variants in data.items():
        for name in [canonical, *(variants or [])]:
            key = normalise_name(str(name))
            if key:
                lookup.setdefault(key, str(canonical))
    return lookup


def match_company(name: Optional[str], lookup: dict[str, str]) -> Optional[str]:
    """Canonical name if the alias table knows it (exact, then fuzzy >= 92). Otherwise the original
    name, whitespace-stripped. None stays None."""
    if name is None:
        return None
    stripped = name.strip()
    key = normalise_name(stripped)
    if not key:
        return stripped or None
    if key in lookup:
        return lookup[key]
    best = process.extractOne(key, list(lookup), scorer=fuzz.token_sort_ratio, score_cutoff=FUZZY_MIN_SCORE)
    if best is not None:
        return lookup[best[0]]
    return stripped


# ---------- dedupe ----------

def _completeness(item: Item) -> int:
    """How many fields carry a value (not None, not empty)."""
    return sum(1 for v in item.model_dump().values() if v not in (None, "", [], {}))


def _better(a: tuple[int, Item], b: tuple[int, Item]) -> tuple[int, Item]:
    """More complete wins; tie -> earlier collected_at; tie -> earlier in the input."""
    (ia, xa), (ib, xb) = a, b
    ka = (-_completeness(xa), xa.collected_at, ia)
    kb = (-_completeness(xb), xb.collected_at, ib)
    return a if ka <= kb else b


def _dedupe(indexed: list[tuple[int, Item]], key_fn) -> list[tuple[int, Item]]:
    """Keep one item per key (None = never compared). Returns kept items in input order."""
    winners: dict[str, tuple[int, Item]] = {}
    keep: list[tuple[int, Item]] = []
    for entry in indexed:
        key = key_fn(entry[1])
        if key is None:
            keep.append(entry)
            continue
        winners[key] = _better(winners[key], entry) if key in winners else entry
    keep.extend(winners.values())
    return sorted(keep, key=lambda e: e[0])


def _fingerprint_key(item: Item) -> Optional[str]:
    # Items from empty pages only have a URL+title fingerprint: compare those by URL only.
    if item.page_fingerprint == empty_page_fingerprint(item.source_url, item.title):
        return None
    return item.page_fingerprint


# ---------- main entry point ----------

def clean_items(items: list[Item], aliases_path: str = "config/aliases.yaml") -> CleanResult:
    """Dedupe by URL then by fingerprint, make dates ISO, match company names. Order is preserved."""
    if not items:
        return CleanResult(items=[], duplicates_dropped=0)

    indexed = list(enumerate(items))
    kept = _dedupe(indexed, lambda i: normalise_url(i.source_url))
    kept = _dedupe(kept, _fingerprint_key)

    lookup = load_aliases(aliases_path)
    cleaned: list[Item] = []
    for _, item in kept:
        cleaned.append(item.model_copy(update={
            "published_at": parse_published_date(item.published_at),
            "company": match_company(item.company, lookup),
            "title": item.title.strip() if item.title is not None else None,
        }))
    return CleanResult(items=cleaned, duplicates_dropped=len(items) - len(cleaned))