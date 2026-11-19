"""Small readers for the structured parts of a page: JSON-LD, <meta> tags, headings, dates and images.

Used by the extractor (atlas.extract) and the company website reader (atlas.profile). Everything works on
an lxml tree held in memory; nothing here stores page content.
"""
from __future__ import annotations

import json
import re
from typing import Iterator, Optional
from urllib.parse import urljoin, urlsplit

import lxml.etree
from lxml import html as lxml_html

SKIP_ANCESTORS = ("nav", "header", "footer", "aside", "form")


def parse(content: "bytes | str | None"):
    """An lxml tree, or None if the content is empty or not HTML."""
    if not content:
        return None
    data = content.encode("utf-8", errors="ignore") if isinstance(content, str) else content
    if not data.strip():
        return None
    try:
        return lxml_html.fromstring(data, parser=lxml_html.HTMLParser(encoding="utf-8"))
    except (lxml.etree.ParserError, ValueError):
        return None


def clean_text(value: Optional[str]) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


# ---------- JSON-LD ----------

def _walk(obj) -> Iterator[dict]:
    if isinstance(obj, dict):
        yield obj
        for key in ("@graph", "mainEntity", "publisher", "author", "about", "mentions", "itemListElement"):
            if key in obj:
                yield from _walk(obj[key])
    elif isinstance(obj, list):
        for entry in obj:
            yield from _walk(entry)


def jsonld_objects(doc) -> list[dict]:
    """Every JSON-LD object on the page, nested @graph / publisher / author objects included."""
    if doc is None:
        return []
    out: list[dict] = []
    for script in doc.xpath('//script[@type="application/ld+json"]'):
        raw = (script.text or "").strip()
        if not raw:
            continue
        try:
            data = json.loads(raw)
        except ValueError:
            continue
        out.extend(_walk(data))
    return out


def types_of(obj: dict) -> set[str]:
    value = obj.get("@type")
    values = value if isinstance(value, list) else [value]
    return {str(v) for v in values if v}


ORG_TYPES = {"Organization", "Corporation", "LocalBusiness", "Company", "NGO", "GovernmentOrganization"}
ARTICLE_TYPES = {"NewsArticle", "Article", "BlogPosting", "Report", "PressRelease", "WebPage"}


def jsonld_date(doc) -> Optional[str]:
    """datePublished of the page's own article object, as written (parsed later)."""
    for obj in jsonld_objects(doc):
        if types_of(obj) & ARTICLE_TYPES and obj.get("datePublished"):
            return str(obj["datePublished"])
    return None


# ---------- <meta> ----------

def meta_content(doc, *names: str) -> Optional[str]:
    """First non-empty <meta name|property|itemprop=...> content among `names`, in order."""
    if doc is None:
        return None
    for name in names:
        for attr in ("property", "name", "itemprop"):
            for el in doc.xpath(f'//meta[@{attr}="{name}"]'):
                value = clean_text(el.get("content"))
                if value:
                    return value
    return None


def absolute_http(url: Optional[str], base: str) -> Optional[str]:
    if not url:
        return None
    absolute = urljoin(base, url.strip())
    return absolute if urlsplit(absolute).scheme in ("http", "https") else None


def og_image(doc, base: str) -> Optional[str]:
    return absolute_http(meta_content(doc, "og:image", "og:image:url", "twitter:image"), base)


def description(doc) -> Optional[str]:
    return meta_content(doc, "description", "og:description", "twitter:description")


# ---------- headings ----------

def _inside_skipped(el) -> bool:
    for anc in el.iterancestors():
        tag = anc.tag if isinstance(anc.tag, str) else ""
        if tag in SKIP_ANCESTORS:
            return True
        role = (anc.get("role") or "").lower()
        if role in ("navigation", "banner", "contentinfo"):
            return True
    return False


def headings(doc, limit: int = 12) -> list[str]:
    """h1-h3 texts in page order, from <article>/<main> when the page has one, skipping navigation,
    headers and footers. Raw (not yet scrubbed): the caller scrubs them."""
    if doc is None:
        return []
    roots = doc.xpath("//article") or doc.xpath("//main") or [doc]
    out: list[str] = []
    for root in roots:
        for el in root.iter("h1", "h2", "h3"):
            if _inside_skipped(el):
                continue
            text = clean_text(el.text_content())
            if text and text not in out:
                out.append(text)
            if len(out) >= limit:
                return out
    return out


def first_h1(doc) -> Optional[str]:
    hs = [h for h in (clean_text(el.text_content()) for el in (doc.iter("h1") if doc is not None else [])) if h]
    return hs[0] if hs else None
