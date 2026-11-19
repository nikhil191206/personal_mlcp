"""Company discovery: which company is a page about, even when no source or list names it?

Owner: Sachi (phase 3, task 2). Called by atlas.extract while the page is in memory.

Rules, strongest first. Each rule gives a candidate name, the rule's name and a short evidence phrase:
    1. competitor_source  the page is on a competitor's own newsroom: that competitor (high)
    2. alias_list         a company from config/aliases.yaml is named most often (high)
    3. ticker             "Acme Corp (NYSE: ACME)": the name before a stock ticker (medium)
    4. about_section      the press-release boilerplate heading "About Acme Corp" (medium)
    5. structured_data    a JSON-LD Organization the page is about (not its publisher) (medium)
    6. headline           "Acme Corp launches ...": the subject of the headline (low)
    7. org_mentions       an organisation spaCy finds at least twice near the top (low)

Rules 3 to 7 vote. Two or more rules naming the same company make it high confidence. Two different
companies with the same best score means no company: the extractor never guesses.
"""
from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass
from typing import Callable, Optional

from atlas.htmlmeta import ORG_TYPES, jsonld_objects, types_of

EXCHANGES = r"(?:NYSE(?: American)?|NASDAQ|Nasdaq|TSX|TSXV|TSX-V|BMV|OTC(?:QX|QB|\s?Markets)?|LSE|SIX|XETRA|Euronext|NYSEAMERICAN)"
TICKER = re.compile(
    r"(?P<name>(?:[A-Z][\w&'’.-]*,?\s+){0,5}[A-Z][\w&'’.-]*)[,\s]*\(\s*" + EXCHANGES + r"\s*:\s*[A-Z][A-Z0-9.\-]{0,7}\s*\)"
)
ABOUT_LINE = re.compile(r"^\s*About\s+(?P<name>[A-Z][\w&'’.,()-]*(?:\s+[\w&'’.,()-]+){0,6}?)\s*[:.]?\s*$")
HEADLINE_VERBS = (
    r"announces?|launch(?:es)?|introduces?|unveils?|acquires?|completes|opens|expands|partners|names|appoints|"
    r"wins|celebrates|debuts|releases|signs|invests|receives|joins|selects|reports|achieves|adds|"
    r"to acquire|to open|to expand|to invest|teams up|showcases|presents|highlights|breaks ground"
)
HEADLINE = re.compile(
    r"^(?P<name>(?:[A-Z][\w&'’.-]*|[A-Z]{2,}|&)(?:\s+(?:[A-Z][\w&'’.-]*|[A-Z]{2,}|&|of|and|de)){0,5}?)\s+(?i:" + HEADLINE_VERBS + r")\b"
)
# First words that are never a company in a headline subject.
NOT_A_COMPANY = {
    "new", "the", "how", "why", "what", "when", "where", "who", "this", "these", "our", "your", "top", "best",
    "breaking", "update", "watch", "video", "podcast", "episode", "webinar", "report", "study", "survey", "doe",
    "energy", "department", "u.s.", "us", "usa", "today", "industry", "global", "local", "north", "america",
}
GENERIC = {"news", "newsroom", "press", "press release", "press releases", "company", "the company", "inc", "llc",
           "corp", "corporation", "group", "rss", "home", "blog", "media", "editor", "staff", "admin"}
LEGAL_TAIL = re.compile(r"[,\s]+(?:Inc|Incorporated|LLC|L\.L\.C|Ltd|Limited|Corp|Corporation|Co|Company|plc|AG|AB|SA|GmbH|N\.V|S\.A)\.?$",
                        re.IGNORECASE)

WEIGHTS = {"ticker": 3, "about_section": 3, "structured_data": 2, "headline": 2, "org_mentions": 1}


@dataclass
class CompanyGuess:
    name: str
    method: str
    confidence: str  # high | medium | low
    evidence: str


def norm(name: str) -> str:
    """Comparison key: lower case, punctuation and trailing legal words removed."""
    name = LEGAL_TAIL.sub("", name.strip())
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s&]", " ", name.casefold())).strip()


def tidy(name: str) -> str:
    name = re.sub(r"\s+", " ", name).strip(" ,.;:-–—\"'")
    return re.sub(r"^(?:the|today|and)\s+", "", name, flags=re.IGNORECASE).strip()


def _usable(name: Optional[str], source_name: str) -> bool:
    if not name or "<" in name or len(name) < 2 or len(name) > 80:
        return False
    key = norm(name)
    if not key or key in GENERIC or key.split()[0] in NOT_A_COMPANY:
        return False
    own = norm(source_name)
    if own and (key == own or key in own or own in key):  # the publisher, not the subject
        return False
    return bool(re.search(r"[A-Z]", name))


def _short(text: str, limit: int = 160) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


# ---------- single rules ----------

def from_ticker(text: str) -> Optional[tuple[str, str]]:
    for m in TICKER.finditer(text or ""):
        name = tidy(m.group("name"))
        # keep the last capitalised run: "DAVIDSON, N.C., Oct. 3 -- Acme Corp (NYSE: ACM)" -> "Acme Corp"
        name = re.split(r"\s(?:--|–|—|-)\s|\)\s", name)[-1].strip()
        words = name.split()
        while words and (words[0].lower() in NOT_A_COMPANY or re.fullmatch(r"[A-Z]\.|[A-Z]{1,2}\.[A-Z]\.,?", words[0])):
            words.pop(0)
        name = tidy(" ".join(words))
        if name:
            return name, m.group(0)
    return None


def from_about_section(text: str) -> Optional[tuple[str, str]]:
    for line in (text or "").splitlines():
        m = ABOUT_LINE.match(line)
        if m:
            name = tidy(m.group("name"))
            if name.lower() not in {"us", "the author", "this release", "the company", "our company"}:
                return name, line.strip()
    return None


def from_headline(title: Optional[str]) -> Optional[tuple[str, str]]:
    m = HEADLINE.match((title or "").strip())
    if not m:
        return None
    return tidy(m.group("name")), title.strip()


def from_structured_data(doc, source_name: str) -> Optional[tuple[str, str]]:
    """An Organization the page is about: JSON-LD `about` / `mentions`, or the article's author when it is
    an Organization different from the publisher. The publisher itself is never the answer."""
    publishers: set[str] = set()
    found: list[str] = []
    for obj in jsonld_objects(doc):
        pub = obj.get("publisher")
        if isinstance(pub, dict) and pub.get("name"):
            publishers.add(norm(str(pub["name"])))
    for obj in jsonld_objects(doc):
        for key in ("about", "mentions", "author"):
            value = obj.get(key)
            for entry in (value if isinstance(value, list) else [value]):
                if isinstance(entry, dict) and types_of(entry) & ORG_TYPES and entry.get("name"):
                    name = str(entry["name"]).strip()
                    if norm(name) not in publishers and _usable(name, source_name):
                        found.append(name)
    if not found:
        return None
    return found[0], f"JSON-LD organisation: {found[0]}"


# ---------- combined ----------

def discover_company(title: Optional[str], text: str, source_name: str, doc=None,
                     alias_lookup: Optional[Callable[[Optional[str], str], Optional[str]]] = None,
                     org_lookup: Optional[Callable[[Optional[str], str, str], Optional[str]]] = None,
                     ) -> Optional[CompanyGuess]:
    """The company a non-competitor page is about, or None. `title` and `text` are already scrubbed."""
    if alias_lookup is not None:
        known = alias_lookup(title, text)
        if known:
            return CompanyGuess(known, "alias_list", "high", _short(f"known company named in the page: {known}"))

    votes: dict[str, list[tuple[str, str, str]]] = defaultdict(list)  # key -> [(method, name, evidence)]

    def vote(method: str, hit: Optional[tuple[str, str]]) -> None:
        if hit and _usable(hit[0], source_name):
            votes[norm(hit[0])].append((method, hit[0], hit[1]))

    vote("ticker", from_ticker(text))
    vote("about_section", from_about_section(text))
    if doc is not None:
        vote("structured_data", from_structured_data(doc, source_name))
    vote("headline", from_headline(title))
    if org_lookup is not None:
        org = org_lookup(title, text, source_name)
        if org:
            vote("org_mentions", (org, f"named {org} at least twice near the top"))

    if not votes:
        return None
    # Merge keys where one name contains the other ("Acme" and "Acme Compressors").
    keys = sorted(votes, key=len, reverse=True)
    for long_key in keys:
        for short_key in keys:
            if short_key != long_key and short_key in votes and long_key in votes and \
                    re.search(rf"(?<!\w){re.escape(short_key)}(?!\w)", long_key):
                votes[long_key].extend(votes.pop(short_key))

    def score(key: str) -> int:
        return sum(WEIGHTS[m] for m in {m for m, _, _ in votes[key]})

    ranked = sorted(votes, key=score, reverse=True)
    if len(ranked) > 1 and score(ranked[0]) == score(ranked[1]):
        return None  # two different companies with equal support: no guess
    best = votes[ranked[0]]
    methods = {m for m, _, _ in best}
    # the name as written by the strongest rule
    strongest = max(best, key=lambda v: WEIGHTS[v[0]])
    if len(methods) >= 2:
        confidence = "high"
    elif strongest[0] in ("ticker", "about_section", "structured_data"):
        confidence = "medium"
    else:
        confidence = "low"
    name = LEGAL_TAIL.sub("", strongest[1]).strip(" ,") or strongest[1]
    return CompanyGuess(name, strongest[0], confidence, _short(strongest[2]))
