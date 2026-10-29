from datetime import date

import httpx
import pytest
import yaml

from atlas import compliance
from atlas.compliance import ComplianceGate, load_register, same_site
from atlas.models import Source

EMAIL = "team@example.com"


def make_source(**kw) -> Source:
    base = dict(
        source_id="acme_news", name="Acme Newsroom", url="https://acme.example/news", type="competitor",
        access_method="rss", feed_url="https://acme.example/news/rss", robots_status="allowed",
        terms_status="ok", vetting_status="working", status="proposed", review_date=date(2026, 10, 29),
    )
    base.update(kw)
    return Source(**base)


def make_gate(robots: tuple[int, str] | Exception = (200, "User-agent: *\nAllow: /\n"), sources=None,
              min_delay=3.0, seen=None):
    """Gate wired to a mock transport; `seen` collects the requests made."""
    seen = seen if seen is not None else []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if request.url.path == "/robots.txt":
            if isinstance(robots, Exception):
                raise robots
            return httpx.Response(robots[0], text=robots[1])
        return httpx.Response(200, text="ok")

    client = httpx.Client(transport=httpx.MockTransport(handler))
    gate = ComplianceGate(sources or [make_source()], client=client, min_delay=min_delay, contact_email=EMAIL)
    sleeps: list[float] = []
    clock = {"t": 1000.0}

    def fake_sleep(seconds: float) -> None:
        sleeps.append(seconds)
        clock["t"] += seconds

    gate._sleep = fake_sleep
    gate._now = lambda: clock["t"]
    return gate, sleeps, seen


# ---- register ----

def test_register_loads(tmp_path):
    p = tmp_path / "sources.yaml"
    p.write_text(yaml.safe_dump([make_source().model_dump(mode="json")]), encoding="utf-8")
    sources = load_register(str(p))
    assert [s.source_id for s in sources] == ["acme_news"]


def test_malformed_entry_names_its_source_id(tmp_path):
    p = tmp_path / "sources.yaml"
    p.write_text("- source_id: broken_one\n  name: Broken\n", encoding="utf-8")
    with pytest.raises(ValueError, match="broken_one"):
        load_register(str(p))


def test_default_register_in_repo_loads():
    assert all(isinstance(s, Source) for s in load_register())


# ---- construction ----

def test_empty_contact_email_raises():
    with pytest.raises(RuntimeError, match="CONTACT_EMAIL"):
        ComplianceGate([make_source()], contact_email="  ")


def test_email_from_settings(monkeypatch):
    class S:
        contact_email = "from-settings@example.com"

    monkeypatch.setattr(compliance, "get_settings", lambda: S())
    gate = ComplianceGate([make_source()], client=httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200))))
    assert gate.user_agent == "AtlasCopcoStudentPoC/0.1 (+contact: from-settings@example.com)"


# ---- check_source ----

def test_proposed_working_allowed():
    gate, _, _ = make_gate()
    d = gate.check_source(make_source())
    assert d.allowed and d.reasons == []
    assert gate.decisions == [d]


def test_approved_also_allowed():
    gate, _, _ = make_gate()
    assert gate.check_source(make_source(status="approved")).allowed


@pytest.mark.parametrize("kw,reason", [
    ({"status": "blocked"}, "status_blocked"),
    ({"status": "needs_permission"}, "status_blocked"),
    ({"vetting_status": "blocked"}, "vetting_blocked"),
    ({"vetting_status": "unreachable"}, "vetting_unreachable"),
    ({"vetting_status": "needs_permission"}, "vetting_needs_permission"),
    ({"terms_status": "forbids_automation"}, "terms_forbid_automation"),
])
def test_record_based_refusals(kw, reason):
    gate, _, seen = make_gate()
    d = gate.check_source(make_source(**kw))
    assert not d.allowed and reason in d.reasons
    assert [r.reason for r in gate.refusals if r.reason == reason]
    assert seen == []  # a refused source is not even contacted


def test_all_record_reasons_collected():
    gate, _, _ = make_gate()
    d = gate.check_source(make_source(status="blocked", vetting_status="blocked", terms_status="forbids_automation"))
    assert d.reasons == ["status_blocked", "vetting_blocked", "terms_forbid_automation"]


def test_robots_disallow_all_listing():
    gate, _, _ = make_gate(robots=(200, "User-agent: *\nDisallow: /\n"))
    d = gate.check_source(make_source())
    assert d.reasons == ["robots_disallow_listing"]


def test_robots_disallow_only_matters_for_listing_path():
    gate, _, _ = make_gate(robots=(200, "User-agent: *\nDisallow: /private/\n"))
    assert gate.check_source(make_source()).allowed


def test_robots_403_means_disallow_all():
    gate, _, _ = make_gate(robots=(403, "forbidden"))
    assert gate.check_source(make_source()).reasons == ["robots_disallow_listing"]


def test_robots_500_is_unreachable():
    gate, _, _ = make_gate(robots=(500, "oops"))
    assert gate.check_source(make_source()).reasons == ["robots_unreachable"]


def test_robots_network_error_is_unreachable():
    gate, _, _ = make_gate(robots=httpx.ConnectError("down"))
    assert gate.check_source(make_source()).reasons == ["robots_unreachable"]


def test_robots_404_allows_everything():
    gate, _, _ = make_gate(robots=(404, "not found"))
    assert gate.check_source(make_source()).allowed


def test_our_agent_specific_rule_is_honoured():
    gate, _, _ = make_gate(robots=(200, "User-agent: AtlasCopcoStudentPoC\nDisallow: /\n\nUser-agent: *\nAllow: /\n"))
    assert not gate.check_source(make_source()).allowed


def test_user_agent_header_sent_on_robots_request():
    gate, _, seen = make_gate()
    gate.check_source(make_source())
    robots_req = next(r for r in seen if r.url.path == "/robots.txt")
    assert robots_req.headers["user-agent"] == f"AtlasCopcoStudentPoC/0.1 (+contact: {EMAIL})"


def test_html_source_checks_its_page_url_not_a_feed():
    gate, _, seen = make_gate(robots=(200, "User-agent: *\nDisallow: /news\n"))
    d = gate.check_source(make_source(access_method="html", feed_url=None, item_url_pattern="x"))
    assert d.reasons == ["robots_disallow_listing"]


# ---- can_fetch ----

def test_can_fetch_per_url_and_records_refusal():
    gate, _, _ = make_gate(robots=(200, "User-agent: *\nDisallow: /secret/\n"))
    src = make_source()
    assert gate.can_fetch(src, "https://acme.example/news/a") == (True, "ok")
    ok, reason = gate.can_fetch(src, "https://acme.example/secret/b")
    assert (ok, reason) == (False, "robots_disallow")
    assert gate.refusals[-1].url == "https://acme.example/secret/b"


def test_robots_cached_per_host_for_the_run():
    gate, _, seen = make_gate()
    src = make_source()
    for path in ("a", "b", "c"):
        gate.can_fetch(src, f"https://acme.example/news/{path}")
    assert sum(r.url.path == "/robots.txt" for r in seen) == 1


def test_new_host_gets_its_own_robots_fetch():
    gate, _, seen = make_gate()
    src = make_source()
    gate.can_fetch(src, "https://acme.example/a")
    gate.can_fetch(src, "https://www.acme.example/a")
    assert sum(r.url.path == "/robots.txt" for r in seen) == 2


# ---- wait ----

def test_min_delay_is_the_floor():
    gate, sleeps, _ = make_gate(min_delay=3.0)
    src = make_source()
    gate.can_fetch(src, "https://acme.example/a")  # robots fetched "now"
    gate.wait(src)
    assert sleeps == [3.0]
    gate.wait(src)
    assert sleeps == [3.0, 3.0]


def test_crawl_delay_from_robots_is_honoured():
    gate, sleeps, _ = make_gate(robots=(200, "User-agent: *\nCrawl-delay: 10\n"))
    src = make_source()
    gate.check_source(src)
    gate.wait(src)
    assert sleeps == [10.0]


def test_source_crawl_delay_from_register_is_honoured():
    gate, sleeps, _ = make_gate()
    src = make_source(crawl_delay=7)
    gate.can_fetch(src, "https://acme.example/a")
    gate.wait(src)
    assert sleeps == [7.0]


def test_no_sleep_when_enough_time_has_passed():
    gate, sleeps, _ = make_gate()
    src = make_source()
    gate.can_fetch(src, "https://acme.example/a")
    gate._now = lambda: 5000.0
    gate.wait(src)
    assert sleeps == []


# ---- same_site ----

def test_same_site():
    assert same_site("https://www.acme.example/a", "https://acme.example/b")
    assert same_site("https://news.acme.example/a", "https://acme.example/b")
    assert not same_site("https://evil.example/a", "https://acme.example/b")
    assert not same_site("https://notacme.example/a", "https://acme.example/b")
