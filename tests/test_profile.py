"""Phase 3 task 8: company contacts, logo and images from a company's own website. Offline (MockTransport)."""
from datetime import date

import httpx

from atlas.compliance import ComplianceGate
from atlas.htmlmeta import parse
from atlas.models import Source
from atlas.profile import fetch_profile, merge_contacts, read_page, register_refusal, subpages

SITE = "https://www.acme.example/"
HOME = """<html><head>
<script type="application/ld+json">{"@context": "https://schema.org", "@type": "Organization", "name": "Acme",
 "logo": "https://www.acme.example/img/acme-logo.png", "telephone": "+1 (803) 555-0100", "email": "info@acme.example",
 "address": {"@type": "PostalAddress", "streetAddress": "1 Air Way", "addressLocality": "Rock Hill",
 "addressRegion": "SC", "postalCode": "29730", "addressCountry": "US"}}</script>
<meta property="og:image" content="/img/hero.jpg"></head><body>
<header><img class="site-logo" src="/img/acme-logo.png" alt="Acme"></header>
<a href="/contact-us">Contact us</a> <a href="/about">About Acme</a> <a href="/products">Products</a>
<a href="https://other.example/contact">Partner</a>
<img src="/img/rs-compressor.jpg" alt="Rotary screw compressor RS-50">
<footer><p>Phone: 803.555.0100</p><p>Fax: 803-555-0199</p></footer>
</body></html>"""
CONTACT = """<html><body><h1>Contact</h1>
<p>Sales: <a href="mailto:sales@acme.example">sales@acme.example</a></p>
<p>Jane: <a href="mailto:jane.doe@acme.example">jane.doe@acme.example</a></p>
<p>Agency: <a href="mailto:info@agency.example">info@agency.example</a></p>
<p><a href="tel:+18035550100">Call us</a></p>
<address>1 Air Way, Rock Hill, SC 29730</address></body></html>"""


def contact_values(contacts, kind):
    return sorted(c.value for c in contacts if c.kind == kind)


def test_read_page_structured_data_and_labelled_phone_but_not_fax():
    contacts, images, dropped = read_page(parse(HOME), SITE, SITE)
    assert contact_values(contacts, "email") == ["info@acme.example"]
    assert set(contact_values(contacts, "phone")) == {"+1 803 555 0100"}
    assert "1 Air Way, Rock Hill, SC, 29730, US" in contact_values(contacts, "address")
    assert any(i.kind == "logo" and i.url.endswith("acme-logo.png") for i in images)
    assert any(i.kind == "image" and "rs-compressor" in i.url for i in images)
    assert dropped == 0


def test_personal_and_off_domain_emails_are_never_kept():
    contacts, _, dropped = read_page(parse(CONTACT), SITE + "contact-us", SITE)
    assert contact_values(contacts, "email") == ["sales@acme.example"]
    assert dropped == 1  # jane.doe@ counted, not kept; info@agency.example is not ours and not personal


def test_merge_keeps_every_page_and_the_strongest_method():
    a, _, _ = read_page(parse(HOME), SITE, SITE)
    b, _, _ = read_page(parse(CONTACT), SITE + "contact-us", SITE)
    phone = [c for c in merge_contacts(a + b) if c.kind == "phone"]
    assert len(phone) == 1 and phone[0].method == "structured_data" and len(phone[0].found_on) == 2


def test_subpages_contact_first_same_site_only():
    assert subpages(parse(HOME), SITE, 3) == ["https://www.acme.example/contact-us", "https://www.acme.example/about"]


def gate_for(routes: dict, robots: str = "User-agent: *\nAllow: /\n"):
    requested: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested.append(request.url.path)
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text=robots)
        spec = routes.get(request.url.path)
        if spec is None:
            return httpx.Response(404, text="nf")
        ctype, body = spec
        return httpx.Response(200, headers={"content-type": ctype}, content=body if isinstance(body, bytes) else body.encode())

    gate = ComplianceGate([], client=httpx.Client(transport=httpx.MockTransport(handler)), min_delay=0.0,
                          contact_email="test@example.org")
    gate._sleep = lambda s: None
    return gate, requested


PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 64


def test_fetch_profile_reads_home_and_contact_pages_and_stores_the_logo():
    gate, requested = gate_for({"/": ("text/html", HOME), "/contact-us": ("text/html", CONTACT),
                                "/about": ("text/html", "<html><body>About</body></html>"),
                                "/img/acme-logo.png": ("image/png", PNG)})
    result = fetch_profile("Acme", SITE, gate, [])
    assert result.status.startswith("read 3 page")
    by_kind = {c.kind: c for c in result.contacts}
    assert by_kind["phone"].validation.status == "confirmed"  # schema.org on its own site
    sales = next(c for c in result.contacts if c.value == "sales@acme.example")
    assert sales.validation.status == "not_confirmed"  # one page, from a link
    assert result.logo_bytes == PNG and result.logo_type == "image/png"
    assert result.dropped_personal_emails == 1
    assert "/products" not in requested


def test_robots_disallow_means_not_read():
    gate, requested = gate_for({"/": ("text/html", HOME)}, robots="User-agent: *\nDisallow: /\n")
    result = fetch_profile("Acme", SITE, gate, [])
    assert result.status.startswith("not read")
    assert requested == ["/robots.txt"]


def test_register_refusal_is_respected_without_any_request():
    refused = Source(source_id="acme_news", name="Acme News", url="https://www.acme.example/news", type="competitor",
                     access_method="html", robots_status="unknown", terms_status="forbids_automation",
                     vetting_status="blocked", status="blocked", review_date=date(2026, 11, 1))
    assert register_refusal(SITE, [refused])
    gate, requested = gate_for({"/": ("text/html", HOME)})
    result = fetch_profile("Acme", SITE, gate, [refused])
    assert "source register refuses" in result.status
    assert requested == []
