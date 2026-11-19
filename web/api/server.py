"""Local API for the Market Scout website (React). Started by `npm run dev`; listens on 127.0.0.1 only.

The browser never sees the Databricks token: this process reads and writes the Volume through the team's own
code in personal_mlcp (atlas.storage, atlas.review, settings_store, classify_sources, write_brief) and starts
reruns as `python -m atlas.run` exactly like the team's Streamlit app. Nothing is written to the laptop.
Set ATLAS_REPO if the repo is not at ../personal_mlcp.
"""
from __future__ import annotations

import base64
import os
import re
import secrets
import sys
import threading
import time
import typing
from pathlib import Path

WEB = Path(__file__).resolve().parent.parent
_default_repo = WEB.parent if (WEB.parent / "atlas").is_dir() else WEB.parent / "personal_mlcp"
REPO = Path(os.environ.get("ATLAS_REPO", _default_repo)).resolve()
if not (REPO / "atlas").is_dir():
    sys.exit(f"Repo not found at {REPO}. Set ATLAS_REPO to the personal_mlcp folder.")
sys.path.insert(0, str(REPO))
os.chdir(REPO)  # config/ paths and the rerun subprocess expect the repo folder

from pydantic import ValidationError  # noqa: E402
from starlette.applications import Starlette  # noqa: E402
from starlette.middleware import Middleware  # noqa: E402
from starlette.middleware.base import BaseHTTPMiddleware  # noqa: E402
from starlette.middleware.trustedhost import TrustedHostMiddleware  # noqa: E402
from starlette.requests import Request  # noqa: E402
from starlette.responses import FileResponse, JSONResponse, Response  # noqa: E402
from starlette.routing import Route  # noqa: E402

from app.lib.settings_ui import load_technology_labels  # noqa: E402
from app.lib.simple import classify_sources, start_rerun  # noqa: E402
from atlas import review, storage  # noqa: E402
from atlas.compliance import load_register  # noqa: E402
from atlas.models import EventType, OutputEnvelope, ScoutSettings  # noqa: E402
from atlas.report.brief import brief_path, write_brief  # noqa: E402
from atlas.scout import settings_store  # noqa: E402
from atlas.models import CompanyIndex  # noqa: E402

RUN_FILE = re.compile(r"^poc_([0-9]{8}T[0-9]{6}Z)\.json$")
MIME = {"pdf": "application/pdf",
        "pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation"}

_lock = threading.Lock()
_state: dict[str, typing.Any] = {"watcher": None, "pending": False}
_envelopes: dict[str, OutputEnvelope] = {}  # a finished run's output never changes


def error(message: str, exc: Exception | None = None, status: int = 500) -> JSONResponse:
    detail = f"{type(exc).__name__}: {exc}" if exc else ""
    return JSONResponse({"error": message, "detail": detail}, status_code=status)


def prefix() -> str:
    try:
        return storage.get_settings().atlas_path_prefix.strip("/")
    except Exception:
        return ""


def run_ids() -> list[str]:
    try:
        names = storage.list_dir("output")
    except Exception as exc:
        if "NotFound" in type(exc).__name__ or "not exist" in str(exc).lower():
            return []
        raise
    return sorted((m.group(1) for n in names if (m := RUN_FILE.match(n.rstrip("/")))), reverse=True)


def envelope(run_id: str) -> OutputEnvelope:
    if run_id not in _envelopes:
        _envelopes[run_id] = OutputEnvelope.model_validate(storage.read_json(f"output/poc_{run_id}.json"))
    return _envelopes[run_id]


def rerun(reason: str) -> dict:
    """Start a rerun, or queue exactly one more if a run is going (same behaviour as the team's app)."""
    with _lock:
        watcher = _state["watcher"]
        if watcher is not None and watcher.running:
            _state["pending"] = True
            return {"started": False, "queued": True}
        _state["watcher"] = start_rerun(reason)
        return {"started": True, "queued": False}


# ---------- routes ----------

async def health(_: Request) -> JSONResponse:
    p = prefix()
    return JSONResponse({"prefix": p, "demo_folders": p == ""})


async def runs(_: Request) -> JSONResponse:
    try:
        ids = run_ids()
    except Exception as exc:
        return error("Could not reach the data store. Check DATABRICKS_HOST and DATABRICKS_TOKEN in .env.", exc)
    return JSONResponse({"runs": ids, "latest": ids[0] if ids else None})


async def run_detail(request: Request) -> JSONResponse:
    run_id = request.path_params["run_id"]
    if not re.fullmatch(r"[0-9]{8}T[0-9]{6}Z", run_id):
        return error("Not a run id.", status=400)
    try:
        env = envelope(run_id)
    except ValidationError as exc:
        return error(f"The run {run_id} does not match the data contract.", exc)
    except Exception as exc:
        return error(f"The run {run_id} could not be read.", exc)
    return JSONResponse(env.model_dump(mode="json"))


async def settings_get(_: Request) -> JSONResponse:
    try:
        current = settings_store.load_settings()
    except Exception as exc:
        return error("The saved settings could not be read.", exc)
    return JSONResponse({"settings": current.model_dump(mode="json"),
                         "options": {"regions": ["US", "CA", "MX"],
                                     "technologies": load_technology_labels(),
                                     "event_types": list(typing.get_args(EventType))}})


async def settings_post(request: Request) -> JSONResponse:
    body = await request.json()
    allowed = ("regions", "recent_months", "technologies", "event_types",
               "extra_compressor_keywords", "excluded_keywords")
    try:
        current = settings_store.load_settings()
        new = ScoutSettings.model_validate({**current.model_dump(), **{k: body[k] for k in allowed if k in body}})
        settings_store.save_settings(new)
    except ValidationError as exc:
        return error("Not saved: some values are not valid.", exc, 400)
    except Exception as exc:
        return error("Not saved.", exc)
    return JSONResponse({"saved": True, **rerun("new filters")})


async def facts_get(_: Request) -> JSONResponse:
    try:
        return JSONResponse({"decisions": review.load_fact_decisions()})
    except Exception as exc:
        return error("The saved decisions could not be read.", exc)


async def facts_post(request: Request) -> JSONResponse:
    body = await request.json()
    try:
        decisions = review.load_fact_decisions()
        for item_id, value in (body.get("decisions") or {}).items():
            if value in ("approved", "denied"):
                decisions[item_id] = value
            else:
                decisions.pop(item_id, None)
        review.save_fact_decisions(decisions)
    except Exception as exc:
        return error("Not saved.", exc)
    return JSONResponse({"saved": True, **rerun("your fact decisions")})


async def sources_get(_: Request) -> JSONResponse:
    try:
        confirmations = review.load_source_confirmations()
        rejected = {d.candidate_id for d in settings_store.load_decisions() if d.decision == "rejected"}
        groups = classify_sources(load_register(), settings_store.load_candidates(), confirmations, rejected)
    except Exception as exc:
        return error("The sources could not be read.", exc)
    return JSONResponse(groups)


async def sources_post(request: Request) -> JSONResponse:
    body = await request.json()
    source_id, value = body.get("id"), body.get("value")
    if not source_id or value not in ("confirmed", "pending"):
        return error("Send an id and a value of confirmed or pending.", status=400)
    try:
        confirmations = review.load_source_confirmations()
        confirmations[source_id] = value
        review.save_source_confirmations(confirmations)
    except Exception as exc:
        return error("Not saved.", exc)
    return JSONResponse({"saved": True, **rerun("a source decision")})


async def rerun_status(_: Request) -> JSONResponse:
    with _lock:
        watcher = _state["watcher"]
        if watcher is None:
            return JSONResponse({"state": "idle"})
        if not watcher.running and _state["pending"]:
            _state["pending"] = False
            _state["watcher"] = watcher = start_rerun("your latest changes")
        if watcher.running:
            n, total = watcher.progress()
            return JSONResponse({"state": "running", "reason": watcher.reason, "n": n, "total": total,
                                 "last_line": watcher.last_line()[:160], "queued": _state["pending"]})
        if watcher.exit_code == 0:
            return JSONResponse({"state": "done", "reason": watcher.reason})
        return JSONResponse({"state": "failed", "exit_code": watcher.exit_code, "tail": watcher.lines[-8:]})


async def report(request: Request) -> Response:
    run_id, fmt = request.path_params["run_id"], request.path_params["fmt"]
    if fmt not in MIME or not re.fullmatch(r"[0-9]{8}T[0-9]{6}Z", run_id):
        return error("Unknown run or format.", status=400)
    try:
        write_brief(run_id, fmt)
        data = storage.read_bytes(brief_path(run_id, fmt))
    except Exception as exc:
        return error("The report could not be built.", exc)
    return Response(data, media_type=MIME[fmt],
                    headers={"Content-Disposition": f'attachment; filename="brief_{run_id}.{fmt}"'})


def company_index(run_id: str) -> tuple[CompanyIndex, list]:
    """The stored company index of a run (it has the website profiles if `atlas.companies --fetch-profiles`
    was run), else one built now from the run's output. Items always come back validated."""
    from atlas.companies import build_index
    try:
        decisions = review.load_fact_decisions()
    except Exception:
        decisions = {}
    built, items = build_index(envelope(run_id), decisions)
    path = f"companies/{run_id}/index.json"
    try:
        if storage.exists(path):
            stored = CompanyIndex.model_validate(storage.read_json(path))
            by_id = {p.company_id: p for p in stored.companies}
            # keep the website parts (contacts, logo, images) from the stored copy, the counts from now
            built.companies = [p.model_copy(update={k: getattr(by_id[p.company_id], k) for k in
                                                    ("website", "contacts", "logo", "images", "profile_status", "profile_fetched_at")})
                               if p.company_id in by_id else p for p in built.companies]
    except Exception:
        pass
    return built, items


async def companies(request: Request) -> JSONResponse:
    run_id = request.path_params["run_id"]
    if not re.fullmatch(r"[0-9]{8}T[0-9]{6}Z", run_id):
        return error("Not a run id.", status=400)
    try:
        index, items = company_index(run_id)
    except Exception as exc:
        return error(f"The companies of run {run_id} could not be built.", exc)
    return JSONResponse({"index": index.model_dump(mode="json"),
                         "items": {i.id: i.model_dump(mode="json") for i in items}})


async def company_report(request: Request) -> Response:
    run_id, cid, fmt = request.path_params["run_id"], request.path_params["company_id"], request.path_params["fmt"]
    if fmt not in MIME or not re.fullmatch(r"[0-9]{8}T[0-9]{6}Z", run_id) or not re.fullmatch(r"[a-z0-9-]{1,80}", cid):
        return error("Unknown run, company or format.", status=400)
    try:
        from atlas.report.company_report import company_report_path, write_company_report
        index, items = company_index(run_id)
        write_company_report(run_id, cid, fmt, index=index, items=items)
        data = storage.read_bytes(company_report_path(run_id, cid, fmt))
    except KeyError as exc:
        return error("No such company in this run.", exc, 404)
    except Exception as exc:
        return error("The company report could not be built.", exc)
    return Response(data, media_type=MIME[fmt],
                    headers={"Content-Disposition": f'attachment; filename="{cid}_{run_id}.{fmt}"'})


# ---------- one-process mode: this server also serves the built website (`npm start`) ----------

SERVE = os.environ.get("SCOUT_SERVE") == "1"
DIST = WEB / "dist"
HOST = os.environ.get("SCOUT_HOST", "127.0.0.1")
PUBLIC = HOST not in ("127.0.0.1", "localhost")  # listening beyond this laptop (a cloud host)
if SERVE and PUBLIC and not os.environ.get("SCOUT_PASSWORD"):
    sys.exit("Refusing to start on a public address without SCOUT_PASSWORD. Set a strong password first.")
PASSWORD = (os.environ.get("SCOUT_PASSWORD") or secrets.token_urlsafe(9)) if SERVE else None
ALLOWED_HOSTS = ["127.0.0.1", "localhost"] + [h.strip() for h in os.environ.get("SCOUT_ALLOWED_HOSTS", "").split(",") if h.strip()]
if os.environ.get("RENDER_EXTERNAL_HOSTNAME"):  # Render sets this to the service's public name
    ALLOWED_HOSTS.append(os.environ["RENDER_EXTERNAL_HOSTNAME"])

# Failed logins per client address in the last 10 minutes; 10 failures blocks that address for the rest of the window.
_failures: dict[str, list[float]] = {}
WINDOW_S, MAX_FAILURES = 600, 10


def client_ip(request: Request) -> str:
    # Behind the host's proxy the LAST address in X-Forwarded-For is the one the proxy itself saw; earlier ones can be
    # forged by the client, so they are not used.
    forwarded = request.headers.get("x-forwarded-for", "")
    return (forwarded.split(",")[-1].strip() if forwarded else (request.client.host if request.client else "?")) or "?"


async def healthz(_: Request) -> JSONResponse:
    return JSONResponse({"ok": True})


async def site(request: Request) -> Response:
    """Static files from dist/, and index.html for any page route (the site does its own routing)."""
    rel = request.path_params.get("path", "")
    target = (DIST / rel).resolve()
    if rel and DIST.resolve() in target.parents and target.is_file():
        return FileResponse(target)
    return FileResponse(DIST / "index.html")


class Guard(BaseHTTPMiddleware):
    """Blocks requests from other web pages, and asks for the password in one-process mode.

    - A POST must be JSON. A page on another site cannot send JSON to us without our permission, so this stops a
      malicious page from making our logged-in browser save settings or start a run.
    - If the browser sends an Origin header, it must be this server's own address.
    - With SCOUT_SERVE=1 every request needs the password (HTTP Basic; any user name).
    """

    async def dispatch(self, request: Request, call_next):
        if request.url.path == "/healthz":  # for the host's health check; reveals nothing
            return await call_next(request)
        if request.method == "POST":
            if not request.headers.get("content-type", "").startswith("application/json"):
                return JSONResponse({"error": "Requests must be JSON.", "detail": ""}, status_code=415)
        origin = request.headers.get("origin")
        if origin and origin.split("://", 1)[-1] != request.headers.get("host", ""):
            return JSONResponse({"error": "Request from another site refused.", "detail": ""}, status_code=403)
        if PASSWORD is not None:
            ip, now = client_ip(request), time.time()
            recent = [t for t in _failures.get(ip, []) if now - t < WINDOW_S]
            _failures[ip] = recent
            if len(recent) >= MAX_FAILURES:
                return Response("Too many wrong passwords. Try again in a few minutes.", status_code=429)
            sent = ""
            header = request.headers.get("authorization", "")
            if header.lower().startswith("basic "):
                try:
                    sent = base64.b64decode(header[6:]).decode("utf-8", "replace").partition(":")[2]
                except Exception:
                    sent = ""
            if not secrets.compare_digest(sent.encode(), PASSWORD.encode()):
                if header:  # a wrong password counts; the first prompt with no credentials does not
                    _failures[ip].append(now)
                return Response("Password required.", status_code=401,
                                headers={"WWW-Authenticate": 'Basic realm="Market Scout"'})
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        if request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        return response


routes = [
    Route("/healthz", healthz),
    Route("/api/health", health),
    Route("/api/runs", runs),
    Route("/api/runs/{run_id}", run_detail),
    Route("/api/settings", settings_get, methods=["GET"]),
    Route("/api/settings", settings_post, methods=["POST"]),
    Route("/api/facts", facts_get, methods=["GET"]),
    Route("/api/facts", facts_post, methods=["POST"]),
    Route("/api/sources", sources_get, methods=["GET"]),
    Route("/api/sources", sources_post, methods=["POST"]),
    Route("/api/rerun", rerun_status),
    Route("/api/reports/{run_id}/{fmt}", report, methods=["POST"]),
    Route("/api/companies/{run_id}", companies),
    Route("/api/companies/{run_id}/{company_id}/report/{fmt}", company_report, methods=["POST"]),
]
if SERVE:
    if not (DIST / "index.html").is_file():
        sys.exit("The website is not built. Run `npm run build` in web/ first (or use `npm start`).")
    routes += [Route("/", site), Route("/{path:path}", site)]

middleware = [Middleware(TrustedHostMiddleware, allowed_hosts=ALLOWED_HOSTS), Middleware(Guard)]
app = Starlette(routes=routes, middleware=middleware)

if __name__ == "__main__":
    import uvicorn
    for stream in (sys.stdout, sys.stderr):  # a folder name with non-Latin letters must not crash the start-up message
        try:
            stream.reconfigure(errors="replace")
        except Exception:
            pass
    port =int(os.environ.get("PORT") or os.environ.get("SCOUT_API_PORT", "8765"))
    print(f"Market Scout API on http://{HOST}:{port} (repo: {REPO}, prefix: {prefix() or 'DEMO FOLDERS'})", flush=True)
    if SERVE and not PUBLIC:
        print(f"\n  OPEN  http://127.0.0.1:{port}\n  LOGIN user: scout   password: {PASSWORD}\n"
              "  (local only; set SCOUT_PASSWORD to choose your own)\n", flush=True)
    elif SERVE:
        print("Serving the website with a password (the password is not printed). "
              f"Allowed host names: {', '.join(ALLOWED_HOSTS)}", flush=True)
    uvicorn.run(app, host=HOST, port=port, log_level="warning", proxy_headers=True, forwarded_allow_ips="*")
