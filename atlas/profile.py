"""Company website reader: contact details, logo and images from a company's OWN website.

Owner: Sachi (phase 3, task 8).

What is read: the homepage and up to 3 pages it links to whose address or link text says contact, about,
company or locations. Every request goes through the Compliance Gate (robots.txt, 3 s between requests,
identified User-Agent). A website that the source register refuses, or whose robots.txt disallows us, is
not read: the profile says why. Nothing works around a refusal.

What is kept:
    email     only role addresses on the company's own domain (info@, sales@, service@ ...). An address that
              looks like a person's (jane.doe@, jdoe@) is never kept: company contacts only.
    phone     numbers from tel: links, schema.org data, or text labelled phone / tel / call / toll-free (not fax)
    address   schema.org PostalAddress or an <address> element
    logo      schema.org logo, else an <img> marked as the logo, else the touch icon; the logo file is copied to
              the Volume for the company report (identification only)
    images    links only (og:image and product images): they are not copied
Pages stay in memory; only these short values leave this module.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional
from urllib.parse import urlsplit

import yaml

from atlas import htmlmeta
from atlas.compliance import RUNNABLE_STATUSES, ComplianceGate, same_site
from atlas.models import CompanyContact, CompanyImage, Source, utc_now_iso
from atlas.validate import validate_contact

ROOT = Path(__file__).resolve().parent.parent
COMPANIES_PATH = "config/companies.yaml"
MAX_PAGES = 4  # homepage + 3
MAX_LOGO_BYTES = 1_000_000
MAX_IMAGES = 6

ROLE_MAILBOXES = {
    "info", "sales", "service", "services", "support", "contact", "contactus", "contact-us", "hello", "marketing",
    "press", "media", "pr", "news", "communications", "inquiries", "inquiry", "enquiries", "enquiry", "orders",
    "order", "parts", "help", "customerservice", "customer.service", "customer-service", "customercare",
    "office", "general", "careers", "jobs", "hr", "investor", "investors", "ir", "webmaster", "quotes",
    "quote", "rfq", "techsupport", "aftermarket", "distribution", "export", "usa", "us", "na", "americas",
}
SUBPAGE_HINT = re.compile(r"contact|about|company|who-we-are|locations?|offices?|headquarters", re.IGNORECASE)
CONTACT_HINT = re.compile(r"contact", re.IGNORECASE)
PHONE = re.compile(r"(?<!\d)(?:\+?1[\s.-]?)?\(?\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4}(?!\d)")
PHONE_LABEL = re.compile(r"(?:phone|tel(?:ephone)?|call(?: us)?|toll[- ]?free|main|office)\s*[:.]?\s*$", re.IGNORECASE)
FAX_LABEL = re.compile(r"fax\s*[:.]?\s*$", re.IGNORECASE)
EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
IMAGE_TYPES = ("image/png", "image/jpeg", "image/jpg", "image/gif", "image/webp", "image/svg+xml")
PRODUCT_WORDS = re.compile(r"compressor|blower|vacuum|dryer|pump|air end|airend|booster", re.IGNORECASE)


@dataclass
class ProfileResult:
    website: str
    contacts: list[CompanyContact] = field(default_factory=list)
    logo: Optional[CompanyImage] = None
    logo_bytes: Optional[bytes] = None
    logo_type: Optional[str] = None
    images: list[CompanyImage] = field(default_factory=list)
    status: str = "not read yet"
    dropped_personal_emails: int = 0
    fetched_at: Optional[str] = None


# ---------- which website belongs to which company ----------

def load_company_sites(register: list[Source], path: str = COMPANIES_PATH) -> dict[str, str]:
    """Company name -> its own website. From config/companies.yaml, plus every competitor in the source
    register (its newsroom's site root). The config wins when both name a company."""
    from atlas.extract import company_from_source_name

    sites: dict[str, str] = {}
    for source in register:
        if source.type == "competitor":
            name = company_from_source_name(source.name)
            if name:
                parts = urlsplit(source.url)
                sites[name] = f"{parts.scheme}://{parts.netloc}/"
    p = Path(path) if Path(path).is_absolute() else ROOT / path
    if p.exists():
        for entry in yaml.safe_load(p.read_text(encoding="utf-8")) or []:
            if entry.get("name") and entry.get("website"):
                sites[str(entry["name"])] = str(entry["website"])
    return sites


def register_refusal(website: str, register: list[Source]) -> Optional[str]:
    """Why the source register refuses this website, or None. A refused site is never read here either."""
    for source in register:
        if not same_site(source.url, website):
            continue
        reasons = []
        if source.status not in RUNNABLE_STATUSES:
            reasons.append(f"status {source.status}")
        if source.terms_status == "forbids_automation":
            reasons.append("terms forbid automated access")
        if source.vetting_status != "working":
            reasons.append(f"vetting {source.vetting_status}")
        if reasons:
            return f"{source.source_id}: " + ", ".join(reasons)
    return None


# ---------- reading one page ----------

def _mailbox_ok(email: str, site_url: str) -> tuple[bool, bool]:
    """(keep, personal). Keep only role mailboxes on the company's own domain."""
    local, _, domain = email.lower().partition("@")
    own = urlsplit(site_url).hostname or ""
    own_root = ".".join(own.removeprefix("www.").split(".")[-2:])
    on_domain = domain == own_root or domain.endswith("." + own_root)
    role = local in ROLE_MAILBOXES or local.split("+")[0] in ROLE_MAILBOXES
    return (role and on_domain), (not role)


def _phone(value: str) -> Optional[str]:
    digits = re.sub(r"\D", "", value)
    if len(digits) == 11 and digits.startswith("1"):
        digits = digits[1:]
    if len(digits) != 10 or digits[0] in "01":
        return None
    return f"+1 {digits[:3]} {digits[3:6]} {digits[6:]}"


def _address(obj) -> Optional[str]:
    if isinstance(obj, str):
        return htmlmeta.clean_text(obj) or None
    if isinstance(obj, dict):
        parts = [obj.get(k) for k in ("streetAddress", "addressLocality", "addressRegion", "postalCode", "addressCountry")]
        parts = [p.get("name") if isinstance(p, dict) else p for p in parts]
        text = ", ".join(str(p).strip() for p in parts if p and str(p).strip())
        return text or None
    return None


def _img_url(value, base: str) -> Optional[str]:
    if isinstance(value, dict):
        value = value.get("url") or value.get("contentUrl")
    if isinstance(value, list):
        value = value[0] if value else None
    return htmlmeta.absolute_http(str(value), base) if value else None


def read_page(doc, page_url: str, site_url: str) -> tuple[list[CompanyContact], list[CompanyImage], int]:
    """Contacts and images on one page, and how many personal-looking emails were left out."""
    contacts: list[CompanyContact] = []
    images: list[CompanyImage] = []
    dropped: set[str] = set()

    def add(kind: str, value: Optional[str], method: str) -> None:
        if value:
            contacts.append(CompanyContact(kind=kind, value=value[:300], found_on=[page_url], method=method))

    def add_email(raw: str, method: str) -> None:
        email = raw.strip().strip(".").lower()
        keep, personal = _mailbox_ok(email, site_url)
        if keep:
            add("email", email, method)
        elif personal:
            dropped.add(email)  # counted, never kept

    # schema.org
    for obj in htmlmeta.jsonld_objects(doc):
        if not htmlmeta.types_of(obj) & htmlmeta.ORG_TYPES:
            continue
        for e in (obj.get("email") if isinstance(obj.get("email"), list) else [obj.get("email")]):
            if e:
                add_email(str(e).removeprefix("mailto:"), "structured_data")
        for t in (obj.get("telephone") if isinstance(obj.get("telephone"), list) else [obj.get("telephone")]):
            add("phone", _phone(str(t)) if t else None, "structured_data")
        add("address", _address(obj.get("address")), "structured_data")
        logo = _img_url(obj.get("logo"), page_url)
        if logo:
            images.append(CompanyImage(kind="logo", url=logo, source_url=page_url, alt="schema.org logo"))

    # links
    for a in doc.iter("a"):
        href = (a.get("href") or "").strip()
        if href.lower().startswith("mailto:"):
            add_email(href[7:].split("?")[0], "mailto_link")
        elif href.lower().startswith("tel:"):
            add("phone", _phone(href[4:]), "tel_link")

    # labelled text in short blocks: "Phone: (803) 555-0100", "<strong>Tel</strong> 803.555.0100"
    for el in doc.iter("p", "li", "td", "dd", "span", "div", "address", "footer"):
        text = htmlmeta.clean_text(el.text_content())
        if not text or len(text) > 300:
            continue
        for m in PHONE.finditer(text):
            label_zone = text[: m.start()][-24:]
            if FAX_LABEL.search(label_zone):
                continue
            if PHONE_LABEL.search(label_zone):
                add("phone", _phone(m.group(0)), "labelled_text")
        for m in EMAIL.finditer(text):
            add_email(m.group(0), "labelled_text")

    for el in doc.iter("address"):
        text = htmlmeta.clean_text(el.text_content())
        if re.search(r"\d", text) and len(text.split()) >= 3 and not re.search(r"\b(?:attn|c/o)\b", text, re.I):
            add("address", text, "address_tag")

    # logo candidates and images
    for img in doc.iter("img"):
        src = img.get("src") or img.get("data-src") or ""
        marker = " ".join([img.get("class") or "", img.get("id") or "", img.get("alt") or "", src]).lower()
        url = htmlmeta.absolute_http(src, page_url)
        if not url:
            continue
        if "logo" in marker:
            images.append(CompanyImage(kind="logo", url=url, source_url=page_url, alt=(img.get("alt") or None)))
        elif PRODUCT_WORDS.search(img.get("alt") or ""):
            images.append(CompanyImage(kind="image", url=url, source_url=page_url, alt=(img.get("alt") or "")[:160]))
    for link in doc.iter("link"):
        rel = (link.get("rel") or "").lower()
        if "apple-touch-icon" in rel:
            url = htmlmeta.absolute_http(link.get("href"), page_url)
            if url:
                images.append(CompanyImage(kind="logo", url=url, source_url=page_url, alt="touch icon"))
    og = htmlmeta.og_image(doc, page_url)
    if og:
        images.append(CompanyImage(kind="image", url=og, source_url=page_url, alt="page image (og:image)"))
    return merge_contacts(contacts), images, len(dropped)


def merge_contacts(contacts: list[CompanyContact]) -> list[CompanyContact]:
    order = {"structured_data": 0, "tel_link": 1, "mailto_link": 1, "address_tag": 2, "labelled_text": 3, "register": 4}
    merged: dict[tuple[str, str], CompanyContact] = {}
    for c in contacts:
        key = (c.kind, re.sub(r"\W", "", c.value.lower()))
        if key in merged:
            m = merged[key]
            m.found_on = list(dict.fromkeys(m.found_on + c.found_on))
            if order[c.method] < order[m.method]:
                m.method = c.method
        else:
            merged[key] = c.model_copy(deep=True)
    return list(merged.values())


def subpages(doc, page_url: str, limit: int) -> list[str]:
    """Same-site links whose address or text says contact / about / company / locations; contact first."""
    found: list[tuple[int, str]] = []
    seen: set[str] = set()
    for a in doc.iter("a"):
        href = (a.get("href") or "").strip()
        url = htmlmeta.absolute_http(href, page_url)
        if not url or url.split("#")[0] in seen or not same_site(url, page_url):
            continue
        label = f"{urlsplit(url).path} {htmlmeta.clean_text(a.text_content())}"
        if SUBPAGE_HINT.search(label):
            seen.add(url.split("#")[0])
            found.append((0 if CONTACT_HINT.search(label) else 1, url.split("#")[0]))
    return [u for _, u in sorted(found, key=lambda t: t[0])][:limit]


# ---------- the whole website ----------

def fetch_profile(name: str, website: str, gate: ComplianceGate, register: list[Source],
                  max_pages: int = MAX_PAGES) -> ProfileResult:
    """Read a company's own website politely and return its contacts, logo and images."""
    from atlas.scout.discover import BudgetExhausted, GatedFetcher, RateLimited, probe_source, registered_domain

    result = ProfileResult(website=website, fetched_at=utc_now_iso())
    refused = register_refusal(website, register)
    if refused:
        result.status = f"not read: the source register refuses this website ({refused})"
        return result
    probe = probe_source(website, registered_domain(website), "competitor")
    fetcher = GatedFetcher(gate, probe, budget=max_pages + 1)
    contacts: list[CompanyContact] = []
    images: list[CompanyImage] = []
    pages_read = 0
    try:
        queue = [website]
        while queue and pages_read < max_pages:
            url = queue.pop(0)
            page = fetcher.get(url)
            if page is None or page.status != 200 or "html" not in page.content_type:
                if pages_read == 0:
                    why = fetcher.refusal or (f"HTTP {page.status}" if page else "nothing fetched")
                    result.status = f"not read: {why}"
                    return result
                continue
            pages_read += 1
            doc = htmlmeta.parse(page.body)
            if doc is None:
                continue
            found, imgs, dropped = read_page(doc, page.url, website)
            contacts += found
            images += imgs
            result.dropped_personal_emails += dropped
            if pages_read == 1:
                queue += subpages(doc, page.url, max_pages - 1)
        logos = [i for i in images if i.kind == "logo"]
        result.logo = logos[0] if logos else None
        if result.logo is not None:
            try:
                img = fetcher.get(result.logo.url)
            except BudgetExhausted:
                img = None
            if img is not None and img.status == 200 and img.content_type.split(";")[0] in IMAGE_TYPES \
                    and len(img.body) <= MAX_LOGO_BYTES:
                result.logo_bytes, result.logo_type = img.body, img.content_type.split(";")[0]
        result.status = f"read {pages_read} page(s) of the company's own website"
    except RateLimited as exc:
        result.status = f"stopped: the website asked us to slow down ({exc})"
    except BudgetExhausted:
        result.status = f"read {pages_read} page(s) (request budget used up)"
    merged = merge_contacts(contacts)
    for c in merged:
        c.validation = validate_contact(c, website)
    result.contacts = merged
    seen: set[str] = set()
    result.images = []
    for i in images:
        if i.kind == "image" and i.url not in seen and len(result.images) < MAX_IMAGES:
            seen.add(i.url)
            result.images.append(i)
    return result
