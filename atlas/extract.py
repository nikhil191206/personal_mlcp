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
# Reporting patterns that make a trade-news item a "fact". Deliberately narrow: trade sites mostly
# republish company press releases, which are claims. Generic words ("standard", "rule") and
# company-PR wording ("opens", "announces plans") are not in this list.
FACT_PATTERNS = [
    "acquires", "acquired", "files", "filed", "completes", "completed", "appoints", "fined",
    "recall", "regulation",
]

# Words that may appear in a page-title suffix ("... | Sullair") besides the source's own name.
SITE_WORDS = {"news", "newsroom", "press", "blog", "home", "official", "site", "website"}

# Sentence ends that are really abbreviations: "U.S.", "Inc.", "Co.", a single initial ("J.")...
ABBREVIATION_END = re.compile(
    r"(?:\b(?:[A-Za-z]\.){1,3}|\b(?:Inc|Co|Ltd|Corp|LLC|No|St|Mr|Mrs|Ms|Dr|vs|approx|Fig)\.)$"
)


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


@lru_cache
def _load_aliases(path: str = "config/aliases.yaml") -> dict[str, list[str]]:
    """canonical company name -> all names it is known by (canonical included)."""
    with open(_resolve(path), encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    return {str(canon): [str(canon), *(str(v) for v in (variants or []))] for canon, variants in data.items()}


_LEGAL_WORDS = {"inc", "incorporated", "llc", "ltd", "limited", "co", "company", "corp", "corporation",
                "ab", "gmbh", "plc", "sa", "ag", "holdings", "group"}


@lru_cache
def _allow_list() -> list[str]:
    """Strings Presidio must never replace: known company names and US place names. The small spaCy
    model often tags these as PERSON, which would wipe the company or place out of titles and facts.
    Includes canonical names, every variant, each variant without trailing legal words
    ("Atlas Copco Compressors LLC" -> "Atlas Copco Compressors"), and single words of 4+ letters."""
    names: set[str] = set()
    for canonical, variants in _load_aliases().items():
        for name in [canonical, *variants]:
            name = str(name).strip()
            if not name:
                continue
            names.add(name)
            names.update(re.findall(r"[A-Za-z][A-Za-z-]{3,}", name))
            words = name.replace(",", " ").split()
            while words and words[-1].strip(".").lower() in _LEGAL_WORDS:
                words.pop()
                if words:
                    names.add(" ".join(words))
    names.update(_load_keywords()["us_locations"])
    return sorted(names | {n.upper() for n in names} | {n.title() for n in names})


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
    results = analyzer.analyze(text=text, language="en", entities=PII_ENTITIES, allow_list=_allow_list())
    if not results:
        return text
    operators = {e: OperatorConfig("replace", {"new_value": v}) for e, v in PII_REPLACEMENTS.items()}
    return anonymizer.anonymize(text=text, analyzer_results=results, operators=operators).text


def person_name_tokens(*texts: Optional[str]) -> set[str]:
    """Name parts of every multi-word PERSON found in the given texts. A full name is caught by
    Presidio, but the same person is often mentioned again as a lone surname ("Foral will lead..."),
    which it misses. Tokens that also occur in lower case somewhere ("energy", "greater") are common
    words the small model mislabelled, so they are not treated as names."""
    analyzer, _, _ = _engines()
    joined = "\n".join(t for t in texts if t)
    tokens: set[str] = set()
    if not joined:
        return tokens
    for hit in analyzer.analyze(text=joined, language="en", entities=["PERSON"], allow_list=_allow_list()):
        parts = re.findall(r"[A-Za-z][A-Za-z'’-]+", joined[hit.start:hit.end])
        if len(parts) < 2:
            continue
        for part in parts:
            if len(part) >= 3 and not re.search(rf"(?<!\w){re.escape(part.lower())}(?!\w)", joined):
                tokens.add(part)
    return tokens


def redact_names(text: Optional[str], tokens: set[str]) -> Optional[str]:
    """Replace each name token (whole word, exact case) with <PERSON>."""
    if not text or not tokens:
        return text
    pattern = re.compile(r"(?<!\w)(?:" + "|".join(re.escape(t) for t in sorted(tokens, key=len, reverse=True)) + r")(?!\w)")
    return pattern.sub("<PERSON>", text)


# ---------- dates ----------

_DEFAULT_A = datetime(2000, 1, 1)
_DEFAULT_B = datetime(2001, 2, 2)


def trusted_metadata_date(strict: Optional[str], extensive: Optional[str]) -> Optional[str]:
    """Pick the page's own date. `strict` comes from trafilatura's normal metadata search, `extensive`
    from its extensive search, which also reads datelines in the text but turns a bare year such as
    '© 2026' into YYYY-01-01. A date that is exactly 1 January and only the extensive search found is
    that footer artefact, so it is treated as no date."""
    if strict:
        return strict
    if extensive and not extensive.endswith("-01-01"):
        return extensive
    return None


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


def _company_from_aliases(title: Optional[str], text: str) -> Optional[str]:
    """The known company (config/aliases.yaml) mentioned most in title + text, as its canonical name.
    None when nothing is known or two companies tie. Names of 3 characters or fewer are ignored
    (an alias such as 'IR' would match unrelated text)."""
    working = f"{title or ''}\n{text}"
    in_title = f"{title or ''}"
    counts: Counter = Counter()
    title_hits: set[str] = set()
    names = [(n, canon) for canon, variants in _load_aliases().items() for n in variants if len(n) > 3]
    for name, canon in sorted(names, key=lambda pair: -len(pair[0])):  # longest first: no double counting
        pattern = _term_regex(name)
        hits = len(pattern.findall(working))
        if hits:
            counts[canon] += hits
            working = pattern.sub(" ", working)
            if pattern.search(in_title):
                title_hits.add(canon)
    if not counts:
        return None
    ranked = counts.most_common()
    if len(ranked) > 1 and ranked[0][1] == ranked[1][1]:
        tied = [c for c, n in ranked if n == ranked[0][1] and c in title_hits]
        return tied[0] if len(tied) == 1 else None
    return ranked[0][0]


def _company_from_orgs(title: Optional[str], text: str, source_name: str) -> Optional[str]:
    """Fallback when no known company matches: the ORG name spaCy finds at least twice in the title
    plus the first 1,500 characters of text. The small model often mislabels phrases as ORG, so one
    mention is never enough; None when there is no single clear winner."""
    _, _, nlp = _engines()
    own = _norm(company_from_source_name(source_name) or source_name)
    own_full = _norm(source_name)
    # Pages repeat the headline as their <h1>; drop those lines so the title is not counted twice.
    title_key = _norm(title) if title else ""
    body = "\n".join(line for line in text.splitlines() if not title_key or _norm(line) != title_key)
    snippet = f"{title or ''}. {body[:ORG_TEXT_WINDOW]}".strip()
    names: list[str] = []
    for ent in nlp(snippet).ents:
        if ent.label_ != "ORG":
            continue
        value = re.sub(r"^the\s+", "", ent.text.strip(" .,:;\"'"), flags=re.IGNORECASE)
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
    if top_count < 2 or (len(counts) > 1 and counts[1][1] == top_count):
        return None
    return next(n for n in names if _norm(n) == top_key)


def strip_site_suffix(title: Optional[str], source_name: str) -> Optional[str]:
    """'Sullair OFE1550 Wins Award | Sullair' -> 'Sullair OFE1550 Wins Award'. Only a trailing part made
    entirely of the source's own name words is removed; anything else is left as published."""
    if not title:
        return title
    parts = re.split(r"\s+[|–—-]\s+", title)
    if len(parts) < 2:
        return title
    suffix = parts[-1]
    tokens = _norm(suffix).split()
    site_tokens = set(_norm(source_name).split()) | SITE_WORDS
    if tokens and all(t in site_tokens for t in tokens):
        stripped = title[: title.rfind(suffix)].rstrip(" |–—-")
        return stripped or title
    return title


def split_sentences(paragraph: str) -> list[str]:
    """Split after . ! ? but not after abbreviations such as 'U.S.', 'Inc.' or an initial."""
    sentences: list[str] = []
    for part in re.split(r"(?<=[.!?])\s+", paragraph.strip()):
        if sentences and ABBREVIATION_END.search(sentences[-1]):
            sentences[-1] = f"{sentences[-1]} {part}"
        else:
            sentences.append(part)
    return sentences


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
    title_key = _norm(title) if title else ""
    seen: set[str] = {title_key} if title_key else set()  # the headline is already in `title`
    for paragraph in clean_text.splitlines():
        for sentence in split_sentences(paragraph):
            sentence = sentence.strip()
            if len(sentence) < MIN_FACT_CHARS or BOILERPLATE.search(sentence):
                continue
            if sentence.isupper():  # navigation labels and shouted headings ("OUR DIGITAL PARTNERS")
                continue
            if title_key and _norm(sentence) in title_key:  # a piece of the headline, not a new fact
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
    raw_title = strip_site_suffix(raw_title, source.name)
    strict_meta = trafilatura.extract_metadata(trafilatura.load_html(page.html), extensive=False)
    meta_date = trusted_metadata_date(
        getattr(strict_meta, "date", None) if strict_meta else None,
        getattr(meta, "date", None) if meta else None,
    )
    published_at = parse_published_date(meta_date) or parse_published_date(page.listing_published)

    keywords = _load_keywords()
    names = person_name_tokens(raw_title, text)  # surnames that Presidio misses when they stand alone
    title = redact_names(scrub(raw_title), names)  # Presidio runs on the title in every case

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

    clean_text = redact_names(scrub(text), names) or ""
    haystack = f"{clean_text} {title or ''}"

    matched = [t for t in keywords["compressor"] if _found(t, haystack)]
    industrial_hint = any(_found(t, haystack) for t in keywords["industrial"])
    mentions_us = any(_found_location(t, haystack) for t in keywords["us_locations"])

    if source.type == "competitor":
        company = company_from_source_name(source.name)
    else:
        company = _company_from_aliases(title, clean_text) or _company_from_orgs(title, clean_text, source.name)

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