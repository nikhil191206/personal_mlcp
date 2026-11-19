"""Phase 3 task 7: Confirmed / Not confirmed rules for items and company contacts."""
from atlas.models import CompanyContact, Item, OutputEnvelope, StoryCluster
from atlas.validate import validate_contact, validate_item, validate_items


def item(i: str, url: str, **kw) -> Item:
    base = dict(id=i, source_id="s", source_name="S", source_type="trade_news", source_url=url, licence_note="l",
                collected_at="2026-11-01T00:00:00Z", page_fingerprint=i, published_at="2026-10-01",
                company="Acme", label="claim")
    base.update(kw)
    return Item(**base)


def test_two_websites_corroborate():
    a, b = item("a", "https://one.example/x"), item("b", "https://www.two.example/y")
    v = validate_item(a, [a, b])
    assert v.status == "confirmed"
    assert any(c.startswith("C1") for c in v.criteria_met)
    assert v.evidence_urls == ["https://one.example/x", "https://www.two.example/y"]


def test_same_website_twice_is_not_corroboration():
    a, b = item("a", "https://one.example/x"), item("b", "https://news.one.example/y")
    assert validate_item(a, [a, b]).status == "not_confirmed"


def test_authoritative_fact_needs_its_own_date():
    gov = item("g", "https://energy.example/x", source_type="government", label="fact")
    assert validate_item(gov, [gov]).status == "confirmed"
    undated = gov.model_copy(update={"published_at": None})
    v = validate_item(undated, [undated])
    assert v.status == "not_confirmed" and "no date" in " ".join(v.reasons)


def test_company_claim_alone_is_not_confirmed_until_reviewed():
    own = item("c", "https://acme.example/news", source_type="competitor")
    v = validate_item(own, [own])
    assert v.status == "not_confirmed" and "own newsroom" in " ".join(v.reasons)
    assert validate_item(own, [own], decision="approved").status == "confirmed"


def test_blocks_win_over_criteria():
    weak = item("w", "https://gov.example/x", source_type="government", label="fact", company_confidence="low")
    v = validate_item(weak, [weak], decision="approved")
    assert v.status == "not_confirmed" and "weak rule" in " ".join(v.reasons)
    gov = item("g", "https://gov.example/x", source_type="government", label="fact")
    assert validate_item(gov, [gov], decision="denied").status == "not_confirmed"


def test_validate_items_uses_stories():
    a, b, c = item("a", "https://one.example/x"), item("b", "https://two.example/y"), item("c", "https://one.example/z")
    env = OutputEnvelope(run_id="r", generated_at="t", sources=[], items=[a, b, c],
                         stories=[StoryCluster(story_id="s1", headline="h", item_ids=["a", "b"], source_ids=["x", "y"])])
    out = {i.id: i.validation.status for i in validate_items(env)}
    assert out == {"a": "confirmed", "b": "confirmed", "c": "not_confirmed"}


def test_contacts():
    site = "https://www.acme.example/"
    ld = CompanyContact(kind="phone", value="+1 803 555 0100", found_on=["https://acme.example/contact"], method="structured_data")
    assert validate_contact(ld, site).status == "confirmed"
    twice = CompanyContact(kind="email", value="info@acme.example", method="mailto_link",
                           found_on=["https://acme.example/", "https://acme.example/contact"])
    assert validate_contact(twice, site).status == "confirmed"
    once = twice.model_copy(update={"found_on": ["https://acme.example/"]})
    assert validate_contact(once, site).status == "not_confirmed"
    elsewhere = twice.model_copy(update={"found_on": ["https://directory.example/acme"]})
    assert validate_contact(elsewhere, site).status == "not_confirmed"
