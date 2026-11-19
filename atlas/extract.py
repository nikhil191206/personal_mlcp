"""Extractor: one fetched page -> one evidence record (Item).

Owner: Sachi. Spec: sachi.md task S1, parent.md sections 6 and 8; Phase 2: sachi2.md tasks S1 to S5.

Page text only ever exists in memory inside `extract_item`. The returned Item holds no page text:
only short rule-extracted key facts (max 3, max 200 characters each) and signals computed while the
text is in memory. Personal data is removed with Presidio using the small spaCy model
`en_core_web_sm`. If Presidio or the model is missing, this module raises; it never falls back to
regex and never skips the scrub.

Phase 2 adds three rule-based signals, computed inside `extract_item` while the text is in memory:
`detect_region` (US / CA / MX or None), `classify_event` (EventType or None) and `detect_product`
(a stated product or model name, or None). None of them guesses: unknown stays None.
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

from atlas import htmlmeta
from atlas.company import CompanyGuess, discover_company
from atlas.models import (
    EventType, FetchedPage, Item, Label, Region, Source, make_fingerprint, make_item_id,
)

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
    keys = ("compressor", "industrial", "us_locations", "ca_locations", "mx_locations", "other_locations")
    return {key: [str(t) for t in (data.get(key) or [])] for key in keys}


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


@lru_cache
def _load_products(path: str = "config/products.yaml") -> dict[str, list[str]]:
    """canonical company name -> product or series names (config/products.yaml)."""
    with open(_resolve(path), encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    return {
        str(company): [str(entry["name"]) for entry in (entries or []) if entry.get("name")]
        for company, entries in data.items()
    }


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
    keywords = _load_keywords()
    names.update(keywords["us_locations"] + keywords["ca_locations"] + keywords["mx_locations"])
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


@lru_cache(maxsize=1)
def _product_words() -> frozenset[str]:
    """Words from our own compressor keywords and technology patterns ("centrifugal", "vacuum", "blower").
    A span containing one is a product or machine name, never a person."""
    phrases = _load_keywords()["compressor"] + [p for _, patterns in _load_technologies() for p in patterns]
    return frozenset(w.lower() for phrase in phrases for w in re.findall(r"[A-Za-z]{4,}", phrase))


def _looks_like_full_name(span: str) -> bool:
    """True for a PERSON detection that reads like a person's full name: two or more words, letters only.
    The small spaCy model tags brand and product names ("Fluke", "Polaris P300", "Regulus R2000") as
    PERSON; a single word or a word with digits is far more often a product or company than a person.
    A lone surname of a person found elsewhere in the text is still caught by person_name_tokens."""
    words = re.findall(r"[^\s]+", span.strip())
    letters = [w for w in words if re.fullmatch(r"[A-Za-z][A-Za-z'’.-]*", w)]
    if len(words) < 2 or len(letters) != len(words):
        return False
    parts = [part for w in words for part in re.split(r"[-'’.]", w.lower()) if part]
    return not any(part in _product_words() for part in parts)  # "Regulus Centrifugal", "Delivering Oil-Free"


def scrub(text: Optional[str]) -> Optional[str]:
    """Replace personal data in `text` with placeholders such as <PERSON>, <EMAIL>, <PHONE>."""
    if not text:
        return text
    from presidio_anonymizer.entities import OperatorConfig

    analyzer, anonymizer, _ = _engines()
    results = analyzer.analyze(text=text, language="en", entities=PII_ENTITIES, allow_list=_allow_list())
    results = [r for r in results if r.entity_type != "PERSON" or _looks_like_full_name(text[r.start:r.end])]
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
        if len(parts) < 2 or not _looks_like_full_name(joined[hit.start:hit.end]):
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


# ---------- Phase 2: region (sachi2.md S2) ----------

REGIONS: tuple[str, ...] = ("US", "CA", "MX")

# Phrases resolved before counting, so their words are not counted again: "North America" is not the
# US, "New Mexico" is not Mexico, "Baja California" is not California.
REGION_PHRASES: list[tuple[str, Optional[str]]] = [
    ("North American", None), ("North America", None), ("Latin American", None), ("Latin America", None),
    ("South American", None), ("South America", None), ("Central American", None),
    ("Central America", None), ("Gulf of Mexico", None), ("New Mexico", "US"), ("Baja California", "MX"),
]

US_STATE_ABBR = {
    "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "FL", "GA", "HI", "ID", "IL", "IN", "IA", "KS", "KY",
    "LA", "ME", "MD", "MA", "MI", "MN", "MS", "MO", "MT", "NE", "NV", "NH", "NJ", "NM", "NY", "NC", "ND",
    "OH", "OK", "OR", "PA", "RI", "SC", "SD", "TN", "TX", "UT", "VT", "VA", "WA", "WV", "WI", "WY", "DC",
    # AP style, as used in press-release datelines ("DAVIDSON, N.C.")
    "Ala.", "Ariz.", "Ark.", "Calif.", "Colo.", "Conn.", "Del.", "Fla.", "Ga.", "Ill.", "Ind.", "Kan.",
    "Ky.", "La.", "Md.", "Mass.", "Mich.", "Minn.", "Miss.", "Mo.", "Mont.", "Neb.", "Nev.", "N.H.",
    "N.J.", "N.M.", "N.Y.", "N.C.", "N.D.", "Okla.", "Ore.", "Pa.", "R.I.", "S.C.", "S.D.", "Tenn.",
    "Vt.", "Va.", "Wash.", "W.Va.", "Wis.", "Wyo.",
}
CA_PROVINCE_ABBR = {
    "ON", "QC", "BC", "AB", "MB", "SK", "NS", "NB", "NL", "PE", "YT", "NT", "NU",
    "Ont.", "Que.", "B.C.", "Alta.", "Man.", "Sask.", "N.S.", "N.B.",
}
# A province or state abbreviation counts only directly after a capitalised place name and a comma
# ("Burlington, ON", "Rock Hill, SC"). Case-sensitive, so "on" or "ca" in running text never counts.
_CITY_COMMA_ABBR = re.compile(
    r"(?<![\w<])[A-Z][A-Za-z.'’-]+(?:\s[A-Z][A-Za-z.'’-]+){0,2},\s("
    + "|".join(re.escape(a) for a in sorted(US_STATE_ABBR | CA_PROVINCE_ABBR, key=len, reverse=True))
    + r")(?!\w)"
)


def _count_location(term: str, text: str) -> int:
    return len(_term_regex(term, case_sensitive=_is_abbreviation(term)).findall(text))


def _region_counts(text: str) -> Counter:
    """Hits per region in one piece of text."""
    counts: Counter = Counter()
    if not text:
        return counts
    for phrase, region in REGION_PHRASES:
        pattern = _term_regex(phrase)
        hits = len(pattern.findall(text))
        if hits:
            if region:
                counts[region] += hits
            text = pattern.sub(" ", text)
    keywords = _load_keywords()
    for region, key in (("US", "us_locations"), ("CA", "ca_locations"), ("MX", "mx_locations")):
        for term in sorted(keywords[key], key=len, reverse=True):  # longest first: "Mexico City" before "Mexico"
            pattern = _term_regex(term, case_sensitive=_is_abbreviation(term))
            hits = len(pattern.findall(text))
            if hits:
                counts[region] += hits
                text = pattern.sub(" ", text)
    for match in _CITY_COMMA_ABBR.finditer(text):
        counts["CA" if match.group(1) in CA_PROVINCE_ABBR else "US"] += 1
    return counts


def _other_count(text: str) -> int:
    """Hits for places outside North America (config/keywords.yaml other_locations)."""
    if not text:
        return 0
    for phrase, _ in REGION_PHRASES:  # "Latin America" etc. are not a foreign-country hit either
        text = _term_regex(phrase).sub(" ", text)
    return sum(_count_location(t, text) for t in _load_keywords()["other_locations"])


def detect_region(source: Source, title: str | None, text: str) -> Region | None:
    """US, CA or MX when the item itself is clearly about that region: the region with the most place
    hits in title + text (title hits count double). A tie means conflicting locations: None. Places
    outside North America named at least as often as the top region: the item is about somewhere
    else, None. No hit at all: the source's own region, if the source is based in one of the three;
    otherwise None. Never defaults to US."""
    counts = Counter()
    for region, n in _region_counts(title or "").items():
        counts[region] += 2 * n
    counts.update(_region_counts(text or ""))
    other = 2 * _other_count(title or "") + _other_count(text or "")
    ranked = [(r, n) for r, n in counts.most_common() if n > 0]
    if other and (not ranked or other >= ranked[0][1]):
        return None
    if ranked:
        if len(ranked) > 1 and ranked[0][1] == ranked[1][1]:
            return None
        return ranked[0][0]  # type: ignore[return-value]
    source_region = (source.region or "").upper()
    return source_region if source_region in REGIONS else None  # type: ignore[return-value]


# ---------- Phase 2: event type (sachi2.md S3) ----------
# Rule table (decision: kept here, not in a YAML file, so the patterns sit next to the code that
# applies them). Checked in this priority order; the first category with a hit wins.
# "any": checked in the title and, if the title has no hit at all, in the first sentences.
# "title": too common in body text ("contact your local distributor", "return on investment"), so
# they are checked in the title only. Patterns are regular expressions, case-insensitive unless
# wrapped in (?-i:...).

EVENT_PRIORITY: list[str] = [
    "acquisition", "regulation_standard", "partnership", "investment_expansion", "product_launch",
    "appointment", "award", "event",
]
_ROLE = (r"(?:president|chief|ceo|cfo|coo|cto|vice president|vp|director|head of|general manager|"
         r"managing director|chair\w*|leader|manager)")
EVENT_RULES: dict[str, dict[str, list[str]]] = {
    "acquisition": {
        "any": [r"acquires?", r"acquired", r"acquisition of", r"to acquire", r"completes (?:the )?acquisition",
                r"merger", r"merges? with", r"buys", r"bought"],
        "title": [r"acquisition"],
    },
    "regulation_standard": {
        "any": [r"regulations?", r"regulatory", r"directive", r"(?:efficiency|energy conservation|energy|emissions?|safety) standards?",
                r"new standards?", r"final rule", r"proposed rule", r"(?-i:ISO) ?\d{3,5}", r"(?-i:ASME)", r"(?-i:EPA)",
                r"(?-i:DOE) (?:efficiency|energy|standard|rule|test procedure)\w*"],
        "title": [r"rules?", r"standards?", r"compliance"],
    },
    "partnership": {
        "any": [r"partners with", r"partnering with", r"partnership", r"strategic alliance", r"collaborat\w+ with",
                r"collaboration", r"joint venture", r"(?:distribution|distributor|supply|service) agreement",
                r"agreement with", r"signs? (?:an? )?agreement"],
        "title": [r"(?:new|exclusive|authori[sz]ed|appoints?|names?|adds?) (?:\w+ )?distributors?", r"agreement",
                  r"teams up"],
    },
    "investment_expansion": {
        "any": [r"invests?", r"invested", r"to invest", r"investment of", r"\$\s?[\d.,]+\s?(?:million|billion|m|bn) investment",
                r"expands", r"expanded", r"expansion", r"opens (?:a |an |its |the |new )", r"opening of", r"new facility",
                r"new plant", r"new factory", r"new headquarters", r"breaks ground", r"broke ground", r"groundbreaking"],
        "title": [r"investment", r"expand\w*", r"opens(?! registration)", r"plant", r"hiring", r"hires", r"jobs"],
    },
    "product_launch": {
        "any": [r"launch(?:es|ed)?", r"introduc(?:es|ed|ing)", r"unveil(?:s|ed)?", r"debuts?", r"new series",
                r"now available", r"released", r"rolls out", r"new (?:line|range|generation|family) of"],
        "title": [r"new\b.{0,40}\b(?:compressors?|dryers?|blowers?|pumps?|series|range)"],
    },
    "appointment": {
        "any": [r"appoints?", r"appointed", r"appointment of", r"joins as", r"promoted to", r"promotes",
                rf"named (?:as )?(?:the )?(?:new )?{_ROLE}"],
        # "<PERSON> COO of ...": the scrub can swallow "Appointed" together with the name
        "title": [rf"names\b.{{0,60}}\b{_ROLE}", r"welcomes", r"new (?:ceo|president|cfo)",
                  rf"<PERSON>,? (?:as |the )?(?:new )?{_ROLE}"],
    },
    "award": {
        # "wins an order" is a sale, not an award: wins/won count only next to an award word
        "any": [r"wins (?:an? |the )?(?:[\w-]+ ){0,3}?(?:award|prize|trophy|recognition|honou?rs?)",
                r"won (?:an? |the )?(?:[\w-]+ ){0,3}?(?:award|prize|trophy)", r"awarded", r"awards?", r"named (?:a |the )?winner", r"recogni[sz]ed",
                r"honou?red", r"top workplaces?"],
        "title": [],
    },
    "event": {
        "any": [r"webinar", r"conference", r"trade ?show", r"expo", r"exposition", r"summit", r"exhibition",
                r"booth", r"symposium"],
        "title": [r"meeting", r"show", r"workshop"],
    },
}
_EVENT_REGEX: dict[str, tuple[Optional[re.Pattern], Optional[re.Pattern]]] = {}
for _cat, _rules in EVENT_RULES.items():
    _any = re.compile(r"(?<!\w)(?:" + "|".join(_rules["any"]) + r")(?!\w)", re.IGNORECASE) if _rules["any"] else None
    _ttl = re.compile(r"(?<!\w)(?:" + "|".join(_rules["title"]) + r")(?!\w)", re.IGNORECASE) if _rules["title"] else None
    _EVENT_REGEX[_cat] = (_any, _ttl)

# Titles of explainers and guides. Their body text talks about standards, regulations or agreements without
# reporting any such event.
EDUCATIONAL_TITLE = re.compile(
    r"(?<!\w)(?:how to|episode \d+|how do|how does|what is|what are|why \w+|guide to|guide|tips|checklist|\d+ ways|best practices for|explained|basics of|beginner)(?!\w)", re.IGNORECASE)

EVENT_SIGNAL_SENTENCES = 3  # how many opening sentences extract_item passes as `text_signals`


def _usable_title(title: Optional[str]) -> bool:
    """A title is usable if something besides placeholders such as <PERSON> remains."""
    if not title:
        return False
    return len(re.findall(r"[A-Za-z]{2,}", re.sub(r"<[A-Z_]+>", " ", title))) >= 2


def _event_in(text: str, include_title_rules: bool) -> Optional[str]:
    for category in EVENT_PRIORITY:
        any_rx, title_rx = _EVENT_REGEX[category]
        if any_rx is not None and any_rx.search(text):
            return category
        if include_title_rules and title_rx is not None and title_rx.search(text):
            return category
    return None


def classify_event(title: str | None, text_signals: str) -> EventType | None:
    """Rule-based event type. The title is checked first (all rules), then the opening sentences (only
    the rules safe in body text). First category in EVENT_PRIORITY with a hit wins. No hit: 'other' if
    there is a usable title, None if there is not."""
    usable = _usable_title(title)
    if usable:
        found = _event_in(title or "", include_title_rules=True)
        if found:
            return found  # type: ignore[return-value]
    if usable and EDUCATIONAL_TITLE.search(title or ""):
        return "other"  # a how-to or guide is not news; body words such as "standards" must not make it one
    if text_signals and text_signals.strip():
        found = _event_in(text_signals, include_title_rules=False)
        if found:
            return found  # type: ignore[return-value]
    return "other" if usable else None


def opening_sentences(clean_text: str, title: Optional[str], n: int = EVENT_SIGNAL_SENTENCES) -> str:
    """The first `n` real sentences of the text (headline repeats and boilerplate skipped)."""
    title_key = _norm(title) if title else ""
    out: list[str] = []
    for paragraph in clean_text.splitlines():
        for sentence in split_sentences(paragraph):
            sentence = sentence.strip()
            if len(sentence) < MIN_FACT_CHARS or BOILERPLATE.search(sentence) or sentence.isupper():
                continue
            if title_key and _norm(sentence) in title_key:
                continue
            out.append(sentence)
            if len(out) == n:
                return " ".join(out)
    return " ".join(out)


# ---------- Phase 2: product (sachi2.md S4) ----------

# Prefixes that look like model codes but are standards, units, periods or pollutants.
MODEL_CODE_STOP = {
    "ISO", "IEC", "ASME", "ANSI", "EPA", "DOE", "UL", "CSA", "API", "EN", "DIN", "NFPA", "OSHA", "NEMA",
    "IP", "IE", "CO", "NOX", "SO", "NO", "PM", "Q", "H", "FY", "COVID", "AD", "BC", "US", "USA", "UK", "EU",
    "HP", "KW", "MW", "CFM", "SCFM", "ACFM", "PSI", "PSIG", "BAR", "DB", "DBA", "PH", "AC", "DC", "TEFC",
    "SKU", "NO", "PO", "ID", "NEW", "TOP", "CEO", "CFO", "LLC", "INC", "AB", "AG", "SA", "GMBH",
}
_MODEL_CODE = re.compile(r"(?<![\w/-])([A-Z]{1,4})([ -]?)(\d{2,5})([A-Z]{0,3})(?![\w])")
PRODUCT_CONTEXT_WORDS = {
    "compressor", "compressors", "dryer", "dryers", "blower", "blowers", "pump", "pumps", "vacuum",
    "airend", "series", "model", "models", "unit", "units", "range", "vsd", "booster",
}


def _canonical_company(company: Optional[str]) -> Optional[str]:
    """The canonical name from config/aliases.yaml for `company`, or None if it is not known."""
    if not company:
        return None

    def key(name: str) -> str:
        words = _norm(name).split()
        while words and words[-1] in _LEGAL_WORDS:
            words.pop()
        return " ".join(words)

    wanted = key(company)
    for canon, variants in _load_aliases().items():
        if any(key(v) == wanted for v in variants):
            return canon
    return None


def _product_regex(name: str) -> re.Pattern:
    letters = re.sub(r"[^A-Za-z]", "", name)
    case_sensitive = len(letters) <= 4 or letters.isupper()
    return _term_regex(name, case_sensitive=case_sensitive)


def _known_product(title: str, text: str, company: Optional[str]) -> Optional[str]:
    products = _load_products()
    canon = _canonical_company(company)
    if company and canon is None:
        return None  # unknown company: never attach another company's product to it
    if canon is not None:
        pool = [(canon, n) for n in products.get(canon, [])]
    else:
        pool = [(c, n) for c, names in products.items() for n in names]
    in_title = {(c, n) for c, n in pool if _product_regex(n).search(title)}
    found = in_title or {(c, n) for c, n in pool if _product_regex(n).search(text)}
    names = {n for _, n in found}
    owners = {c for c, _ in found}
    if len(names) == 1 and len(owners) == 1:
        return next(iter(names))
    return None  # nothing, or several different products: do not pick one


def _company_words(company: Optional[str]) -> set[str]:
    words: set[str] = set()
    if not company:
        return words
    canon = _canonical_company(company)
    names = _load_aliases().get(canon, []) if canon else [company]
    for name in names:
        words.update(w for w in _norm(name).split() if len(w) >= 3 and w not in _LEGAL_WORDS)
    return words


def _model_code(title: str, text: str, company: Optional[str]) -> Optional[str]:
    company_words = _company_words(company)
    context = PRODUCT_CONTEXT_WORDS | {t.lower() for t in _load_keywords()["compressor"] if " " not in t}
    title_key = _norm(title)
    body = "\n".join(line for line in text.splitlines() if _norm(line) != title_key)
    found: dict[str, str] = {}
    for m in _MODEL_CODE.finditer(title):
        prefix, sep, digits, tail = m.groups()
        code = m.group(0)
        if not 2 <= len(code) <= 12 or prefix in MODEL_CODE_STOP:
            continue
        if prefix == "R" and sep == "-":  # refrigerants such as R-410A
            continue
        if len(digits) == 4 and digits[:2] in ("19", "20") and not tail:  # a year: "EXPO 2026"
            continue
        before = _norm(title[: m.start()]).split()[-3:]
        after = _norm(title[m.end():]).split()[:3]
        nearby = set(before + after)
        if not (nearby & context or nearby & company_words):
            continue
        same = re.compile(rf"(?<![\w/-]){re.escape(prefix)}[ -]?{re.escape(digits)}{re.escape(tail)}(?!\w)")
        if same.search(body):  # stated at least once more in the text
            found[f"{prefix}{digits}{tail}"] = code
    if len(found) == 1:
        return next(iter(found.values()))
    return None  # none, or several different codes: do not pick one


def detect_product(title: str | None, text: str, company: str | None) -> str | None:
    """A product or series name that the page states, or None. Order: (1) a name from
    config/products.yaml in title or text; (2) a model code in the title next to the company or a
    compressor word, and repeated in the text. Never guesses."""
    title = title or ""
    text = text or ""
    return _known_product(title, text, company) or _model_code(title, text, company)


# ---------- Phase 3: headings, summary, image, text fallback (task 3) ----------

MAX_HEADINGS = 5
MAX_HEADING_CHARS = 120
MAX_SUMMARY_CHARS = 300


def _main_text(html: str) -> str:
    """Main text by trafilatura. Precision first (fewest menus and footers); when that leaves less than
    MIN_TEXT_CHARS, a second pass that favours recall and keeps tables, so short or table-heavy articles
    (spec sheets, award lists) are not lost. Each pass gets its own tree: trafilatura edits the tree it reads."""
    text = trafilatura.extract(
        trafilatura.load_html(html), include_comments=False, include_tables=False, favor_precision=True,
    ) or ""
    if len(text.strip()) >= MIN_TEXT_CHARS:
        return text
    recall = trafilatura.extract(
        trafilatura.load_html(html), include_comments=False, include_tables=True, favor_recall=True,
    ) or ""
    return recall if len(recall.strip()) > len(text.strip()) else text


def _limit(text: str, limit: int) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) <= limit:
        return text
    cut = text[: limit - 1]
    if " " in cut[limit // 2:]:
        cut = cut[: cut.rfind(" ")]
    return cut.rstrip(" ,;:-") + "…"


def page_headings(doc, title: Optional[str], names: set[str]) -> list[str]:
    """Up to 5 real headings (h1-h3) of the article, scrubbed. The headline itself, navigation labels,
    shouted headings and boilerplate are skipped."""
    title_key = _norm(title) if title else ""
    out: list[str] = []
    seen: set[str] = set()
    for raw in htmlmeta.headings(doc):
        if len(raw) < 4 or raw.isupper() or BOILERPLATE.search(raw):
            continue
        cleaned = redact_names(scrub(raw), names) or ""
        key = _norm(cleaned)
        if not key or key == title_key or key in seen:
            continue
        seen.add(key)
        out.append(_limit(cleaned, MAX_HEADING_CHARS))
        if len(out) == MAX_HEADINGS:
            break
    return out


def page_summary(doc, names: set[str]) -> Optional[str]:
    """The page's own meta description (written by the publisher), scrubbed and capped at 300 characters."""
    raw = htmlmeta.description(doc)
    if not raw or BOILERPLATE.search(raw) and len(raw) < 80:
        return None
    cleaned = redact_names(scrub(raw), names)
    return _limit(cleaned, MAX_SUMMARY_CHARS) if cleaned else None


def _company_fields(guess: Optional[CompanyGuess]) -> dict:
    if guess is None:
        return {"company": None}
    return {"company": guess.name, "company_method": guess.method, "company_confidence": guess.confidence,
            "company_evidence": guess.evidence}


def _competitor_guess(source: Source) -> Optional[CompanyGuess]:
    name = company_from_source_name(source.name)
    return CompanyGuess(name, "competitor_source", "high", f"page on {source.name}") if name else None


# ---------- main entry point ----------

def extract_item(page: FetchedPage, source: Source) -> Item:
    """Turn one in-memory page into an Item. Item.filter is None; the page text is not kept."""
    tree = trafilatura.load_html(page.html) if page.html and page.html.strip() else None
    if tree is None:
        raise ValueError(f"unparseable page: {page.final_url}")
    doc = htmlmeta.parse(page.html)  # our own copy for headings, JSON-LD and meta tags

    text = _main_text(page.html)
    meta = trafilatura.extract_metadata(tree)

    raw_title = ((getattr(meta, "title", None) if meta else None)
                 or htmlmeta.meta_content(doc, "og:title", "twitter:title")
                 or htmlmeta.first_h1(doc) or page.listing_title)
    raw_title = raw_title.strip() if raw_title and raw_title.strip() else None
    raw_title = strip_site_suffix(raw_title, source.name)
    strict_meta = trafilatura.extract_metadata(trafilatura.load_html(page.html), extensive=False)
    meta_date = trusted_metadata_date(
        (getattr(strict_meta, "date", None) if strict_meta else None) or htmlmeta.jsonld_date(doc),
        getattr(meta, "date", None) if meta else None,
    )
    published_at = parse_published_date(meta_date) or parse_published_date(page.listing_published)

    keywords = _load_keywords()
    names = person_name_tokens(raw_title, text)  # surnames that Presidio misses when they stand alone
    title = redact_names(scrub(raw_title), names)  # Presidio runs on the title in every case
    extras = dict(headings=page_headings(doc, title, names), summary=page_summary(doc, names),
                  image_url=htmlmeta.og_image(doc, page.final_url))

    if len(text.strip()) < MIN_TEXT_CHARS:
        # Empty or very short page: keep what exists, never invent the rest. Region, event type and
        # product may still be stated in the title or the few words there are.
        short_text = redact_names(scrub(text), names) or "" if text.strip() else ""
        guess = _competitor_guess(source) if source.type == "competitor" else None
        company = guess.name if guess else None
        item = Item(
            id=make_item_id(page.final_url), source_id=source.source_id, source_name=source.name,
            source_type=source.type, source_url=page.final_url, licence_note=source.licence_note,
            collected_at=page.fetched_at, published_at=published_at, title=title,
            company=company, product=detect_product(title, short_text, company),
            technology=None, key_facts=[], label=_label(source, title or ""),
            filter=None, page_fingerprint=empty_page_fingerprint(page.final_url, title),
            personal_data_removed=True, matched_keywords=[], mentions_us_location=False,
            industrial_hint=False, region=detect_region(source, title, short_text),
            event_type=classify_event(title, opening_sentences(short_text, title)),
            **{k: v for k, v in _company_fields(guess).items() if k != "company"}, **extras,
        )
        text = short_text = ""
        return item

    clean_text = redact_names(scrub(text), names) or ""
    haystack = f"{clean_text} {title or ''}"

    matched = [t for t in keywords["compressor"] if _found(t, haystack)]
    industrial_hint = any(_found(t, haystack) for t in keywords["industrial"])
    mentions_us = any(_found_location(t, haystack) for t in keywords["us_locations"])

    if source.type == "competitor":
        guess = _competitor_guess(source)
    else:
        guess = discover_company(title, clean_text, source.name, doc=doc,
                                 alias_lookup=_company_from_aliases, org_lookup=_company_from_orgs)
    company_fields = _company_fields(guess)
    company = company_fields.pop("company")

    facts = [f for f in (scrub(f) for f in _key_facts(clean_text, keywords["compressor"], title)) if f]
    facts = [_shorten(f) for f in facts][:MAX_KEY_FACTS]

    item = Item(
        id=make_item_id(page.final_url), source_id=source.source_id, source_name=source.name,
        source_type=source.type, source_url=page.final_url, licence_note=source.licence_note,
        collected_at=page.fetched_at, published_at=published_at, title=title, company=company,
        product=detect_product(title, clean_text, company), technology=_technology(haystack), key_facts=facts,
        label=_label(source, haystack), filter=None, page_fingerprint=make_fingerprint(clean_text),
        personal_data_removed=True, matched_keywords=matched, mentions_us_location=mentions_us,
        industrial_hint=industrial_hint, region=detect_region(source, title, clean_text),
        event_type=classify_event(title, opening_sentences(clean_text, title)),
        **company_fields, **extras,
    )
    # Drop the text: nothing below this point may keep it.
    text = clean_text = haystack = ""
    return item
