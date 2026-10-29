"""Extractor: one fetched page -> one evidence record (Item).

Owner: Sachi. Spec: sachi.md task S1 and parent.md sections 6 and 8.

Page text only ever exists in memory inside `extract_item`. The returned Item holds no page text:
only short rule-extracted key facts (max 3, max 200 characters each) and signals computed while the
text is in memory. Personal data is removed with Presidio using the small spaCy model
`en_core_web_sm`. If Presidio or the model is missing, this module raises; it never falls back to
regex and never skips the scrub.
"""
from __future__ import annotations

import re
from collections import Counter
from datetime import date, datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Optional

import trafilatura
import yaml
from dateutil import parser as date_parser

from atlas.models import FetchedPage, Item, Label, Source, make_fingerprint, make_item_id

ROOT = Path(__file__).resolve().parent.parent

SPACY_MODEL = "en_core_web_sm"  # small model on purpose; never the 400 MB en_core_web_lg

# Entities removed by Presidio. LOCATION (needed for the US check) and ORGANIZATION (company
# names are the point of the project) are deliberately not removed.
PII_ENTITIES = ["PERSON", "EMAIL_ADDRESS", "PHONE_NUMBER", "CREDIT_CARD", "IBAN_CODE", "IP_ADDRESS", "US_SSN"]
PII_REPLACEMENTS = {
    "PERSON": "<PERSON>",
    "EMAIL_ADDRESS": "<EMAIL>",
    "PHONE_NUMBER": "<PHONE>",
    "CREDIT_CARD": "<CREDIT_CARD>",
    "IBAN_CODE": "<IBAN>",
    "IP_ADDRESS": "<IP>",
    "US_SSN": "<SSN>",
}

MIN_TEXT_CHARS = 200
MAX_KEY_FACTS = 3
MAX_FACT_CHARS = 200
MIN_FACT_CHARS = 20
ORG_TEXT_WINDOW = 1500

# Trailing words removed from a competitor source name to get the company name.
# "us" is not in sachi.md's list; it is added so "Sullair ... US news" becomes "Sullair".
COMPANY_NAME_SUFFIXES = ["press releases", "newsroom", "news", "press", "usa", "us"]

# ORG entities that are never a company.
GENERIC_ORG_WORDS = {
    "news", "newsroom", "press", "press release", "press releases", "company", "the company",
    "inc", "llc", "corp", "corporation", "group", "rss", "home", "blog",
}

NUMBER_WITH_UNIT = re.compile(
    r"\d+(?:[.,]\d+)?\s?(?:%|cfm|psi|bar|kw|hp|m3/min|million|billion|usd|\$)(?![a-z])",
    re.IGNORECASE,
)
DOLLAR_AMOUNT = re.compile(r"\$\s?\d")
EVENT_VERB = re.compile(
    r"\b(?:announce|launch|introduc|acquir|open|expand|partner|certif|award|invest)\w*",
    re.IGNORECASE,
)
BOILERPLATE = re.compile(
    r"cookie|subscribe|click here|read more|copyright|all rights reserved|©",
    re.IGNORECASE,
)
FACT_PATTERNS = [
    "acquires", "acquired", "files", "filed", "opens", "to open", "completes", "completed",
    "announces plans", "appoints", "fined", "recall", "regulation", "rule", "standard",
]


# ---------- config ----------

def _resolve(path: str) -> Path:
    p = Path(path)
    return p if p.is_absolute() else ROOT / p


@lru_cache
def _load_keywords(path: str = "config/keywords.yaml") -> dict[str, list[str]]:
    with open(_resolve(path), encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    return {key: [str(t) for t in (data.get(key) or [])] for key in ("compressor", "industrial", "us_locations")}


@lru_cache
def _load_technologies(path: str = "config/technologies.yaml") -> list[tuple[str, list[str]]]:
    with open(_resolve(path), encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or []
    return [(str(entry["label"]), [str(p) for p in entry.get("patterns") or []]) for entry in data]


# ---------- Presidio (built once per process) ----------

@lru_cache(maxsize=1)
def _engines():
    """Return (analyzer, anonymizer, spacy_nlp). Raises RuntimeError if anything is missing."""
    try:
        import spacy
        from presidio_analyzer import AnalyzerEngine
        from presidio_analyzer.nlp_engine import NlpEngineProvider
        from presidio_anonymizer import AnonymizerEngine
    except ImportError as exc:
        raise RuntimeError(
            "Presidio is not installed. Run: pip install -r requirements.txt"
        ) from exc

    # Check first, so Presidio cannot start a model download on its own.
    if not spacy.util.is_package(SPACY_MODEL):
        raise RuntimeError(
            f"spaCy model '{SPACY_MODEL}' is not installed. Run: python -m spacy download {SPACY_MODEL}"
        )

    conf = {"nlp_engine_name": "spacy", "models": [{"lang_code": "en", "model_name": SPACY_MODEL}]}
    nlp_engine = NlpEngineProvider(nlp_configuration=conf).create_engine()
    analyzer = AnalyzerEngine(nlp_engine=nlp_engine, supported_languages=["en"])
    anonymizer = AnonymizerEngine()
    nlp = spacy.load(SPACY_MODEL)  # used only to find ORG names for the company field
    return analyzer, anonymizer, nlp


def scrub(text: Optional[str]) -> Optional[str]:
    """Replace personal data in `text` with placeholders such as <PERSON>, <EMAIL>, <PHONE>."""
    if not text:
        return text
    from presidio_anonymizer.entities import OperatorConfig

    analyzer, anonymizer, _ = _engines()
    results = analyzer.analyze(text=text, language="en", entities=PII_ENTITIES)
    if not results:
        return text
    operators = {e: OperatorConfig("replace", {"new_value": v}) for e, v in PII_REPLACEMENTS.items()}
    return anonymizer.anonymize(text=text, analyzer_results=results, operators=operators).text


# ---------- dates ----------

_DEFAULT_A = datetime(2000, 1, 1)
_DEFAULT_B = datetime(2001, 2, 2)


def parse_published_date(value: Optional[str], today: Optional[date] = None) -> Optional[str]:
    """Parse a date string to ISO YYYY-MM-DD. Returns None if it is unparseable, incomplete
    (no day, month or year given) or in the future. Month first for ambiguous US dates."""
    if not value or not str(value).strip():
        return None
    text = str(value).strip()
    try:
        # Parse twice with different defaults: if the results differ, part of the date was missing
        # and dateutil filled it in. That would be a guess, so return None.
        a = date_parser.parse(text, dayfirst=False, default=_DEFAULT_A)
        b = date_parser.parse(text, dayfirst=False, default=_DEFAULT_B)
    except (ValueError, OverflowError, TypeError):
        return None
    if a.date() != b.date():
        return None
    if a.tzinfo is not None:
        a = a.astimezone(timezone.utc)
    parsed = a.date()
    if parsed > (today or datetime.now(timezone.utc).date()):
        return None
    return parsed.isoformat()


# ---------- matching helpers ----------

def _term_regex(term: str, case_sensitive: bool = False) -> re.Pattern:
    flags = 0 if case_sensitive else re.IGNORECASE
    return re.compile(rf"(?<!\w){re.escape(term)}(?!\w)", flags)


def _found(term: str, text: str) -> bool:
    return bool(_term_regex(term).search(text))


def _is_abbreviation(term: str) -> bool:
    """Short all-caps place terms such as 'USA' or 'U.S.' are matched case-sensitively,
    so the pronoun 'us' is never read as a location."""
    letters = term.replace(".", "")
    return letters.isupper() and len(letters) <= 4


def _found_location(term: str, text: str) -> bool:
    return bool(_term_regex(term, case_sensitive=_is_abbreviation(term)).search(text))


def empty_page_fingerprint(url: str, title: Optional[str]) -> str:
    """Fingerprint used when a page has no usable main text (also used by clean.py)."""
    return make_fingerprint(url + "|" + (title or ""))


def company_from_source_name(name: str) -> Optional[str]:
    """'Kaeser Compressors USA Newsroom' -> 'Kaeser Compressors'. Parenthetical notes are removed."""
    cleaned = re.sub(r"\([^)]*\)", " ", name)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" -–—,:")
    changed = True
    while changed:
        changed = False
        for suffix in COMPANY_NAME_SUFFIXES:
            pattern = re.compile(rf"\s+{re.escape(suffix)}$", re.IGNORECASE)
            if pattern.search(cleaned):
                cleaned = pattern.sub("", cleaned).strip(" -–—,:")
                changed = True
    return cleaned or None


def _norm(name: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", " ", name.casefold())).strip()


def _company_from_orgs(title: Optional[str], text: str, source_name: str) -> Optional[str]:
    """Most frequent ORG name in the title, else in the first 1,500 characters of the text.
    Returns None when there is no single clear winner."""
    _, _, nlp = _engines()
    own = _norm(company_from_source_name(source_name) or source_name)
    own_full = _norm(source_name)

    def pick(snippet: str, min_count: int) -> Optional[str]:
        if not snippet:
            return None
        names: list[str] = []
        for ent in nlp(snippet).ents:
            if ent.label_ != "ORG":
                continue
            value = ent.text.strip(" .,:;\"'")
            key = _norm(value)
            if not key or "<" in value or key in GENERIC_ORG_WORDS:
                continue
            if own and (key == own or key in own_full or own in key):
                continue
            names.append(value)
        if not names:
            return None
        counts = Counter(_norm(n) for n in names).most_common()
        top_key, top_count = counts[0]
        if top_count < min_count or (len(counts) > 1 and counts[1][1] == top_count):
            return None
        return next(n for n in names if _norm(n) == top_key)

    return pick(title or "", 1) or pick(text[:ORG_TEXT_WINDOW], 2)


def _technology(haystack: str) -> Optional[str]:
    for label, patterns in _load_technologies():
        if any(_found(p, haystack) for p in patterns):
            return label
    return None


def _shorten(sentence: str) -> str:
    sentence = re.sub(r"\s+", " ", sentence).strip()
    if len(sentence) <= MAX_FACT_CHARS:
        return sentence
    cut = sentence[: MAX_FACT_CHARS - 1]
    if " " in cut:
        cut = cut[: cut.rfind(" ")]
    return cut.rstrip(" ,;:-") + "…"


def _key_facts(clean_text: str, compressor_terms: list[str], title: Optional[str] = None) -> list[str]:
    facts: list[str] = []
    seen: set[str] = {_norm(title)} if title else set()  # the headline is already in `title`
    for paragraph in clean_text.splitlines():
        for sentence in re.split(r"(?<=[.!?])\s+", paragraph.strip()):
            sentence = sentence.strip()
            if len(sentence) < MIN_FACT_CHARS or BOILERPLATE.search(sentence):
                continue
            qualifies = (
                any(_found(t, sentence) for t in compressor_terms)
                or NUMBER_WITH_UNIT.search(sentence)
                or DOLLAR_AMOUNT.search(sentence)
                or EVENT_VERB.search(sentence)
            )
            if not qualifies:
                continue
            short = _shorten(sentence)
            key = _norm(short)
            if key in seen:
                continue
            seen.add(key)
            facts.append(short)
            if len(facts) == MAX_KEY_FACTS:
                return facts
    return facts


def _label(source: Source, haystack: str) -> Label:
    if source.type == "government":
        return "fact"
    if source.type == "trade_news" and any(_found(p, haystack) for p in FACT_PATTERNS):
        return "fact"
    return "claim"  # competitor newsrooms, and anything unsure


# ---------- main entry point ----------

def extract_item(page: FetchedPage, source: Source) -> Item:
    """Turn one in-memory page into an Item. Item.filter is None; the page text is not kept."""
    tree = trafilatura.load_html(page.html) if page.html and page.html.strip() else None
    if tree is None:
        raise ValueError(f"unparseable page: {page.final_url}")

    text = trafilatura.extract(
        tree, include_comments=False, include_tables=False, favor_precision=True,
    ) or ""
    meta = trafilatura.extract_metadata(tree)

    raw_title = (getattr(meta, "title", None) if meta else None) or page.listing_title
    raw_title = raw_title.strip() if raw_title and raw_title.strip() else None
    published_at = (
        parse_published_date(getattr(meta, "date", None) if meta else None)
        or parse_published_date(page.listing_published)
    )

    keywords = _load_keywords()
    title = scrub(raw_title)  # Presidio runs on the title in every case

    if len(text.strip()) < MIN_TEXT_CHARS:
        # Empty or very short page: keep what exists, never invent the rest.
        item = Item(
            id=make_item_id(page.final_url), source_id=source.source_id, source_name=source.name,
            source_type=source.type, source_url=page.final_url, licence_note=source.licence_note,
            collected_at=page.fetched_at, published_at=published_at, title=title,
            company=company_from_source_name(source.name) if source.type == "competitor" else None,
            product=None, technology=None, key_facts=[], label=_label(source, title or ""),
            filter=None, page_fingerprint=empty_page_fingerprint(page.final_url, title),
            personal_data_removed=True, matched_keywords=[], mentions_us_location=False,
            industrial_hint=False,
        )
        text = ""
        return item

    clean_text = scrub(text) or ""
    haystack = f"{clean_text} {title or ''}"

    matched = [t for t in keywords["compressor"] if _found(t, haystack)]
    industrial_hint = any(_found(t, haystack) for t in keywords["industrial"])
    mentions_us = any(_found_location(t, haystack) for t in keywords["us_locations"])

    if source.type == "competitor":
        company = company_from_source_name(source.name)
    else:
        company = _company_from_orgs(title, clean_text, source.name)

    facts = [f for f in (scrub(f) for f in _key_facts(clean_text, keywords["compressor"], title)) if f]
    facts = [_shorten(f) for f in facts][:MAX_KEY_FACTS]

    item = Item(
        id=make_item_id(page.final_url), source_id=source.source_id, source_name=source.name,
        source_type=source.type, source_url=page.final_url, licence_note=source.licence_note,
        collected_at=page.fetched_at, published_at=published_at, title=title, company=company,
        product=None, technology=_technology(haystack), key_facts=facts,
        label=_label(source, haystack), filter=None, page_fingerprint=make_fingerprint(clean_text),
        personal_data_removed=True, matched_keywords=matched, mentions_us_location=mentions_us,
        industrial_hint=industrial_hint,
    )
    # Drop the text: nothing below this point may keep it.
    text = clean_text = haystack = ""
    return item