"""Local API for the Market Scout website (React). Started by `npm run dev`; listens on 127.0.0.1 only.

The browser never sees the Databricks token: this process reads and writes the Volume through the team's own
code in personal_mlcp (atlas.storage, atlas.review, settings_store, classify_sources, write_brief) and starts
reruns as `python -m atlas.run` exactly like the team's Streamlit app. Nothing is written to the laptop.
Set ATLAS_REPO if the repo is not at ../personal_mlcp.
"""
from __future__ import annotations

import os
import re
import sys
import threading
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
from starlette.requests import Request  # noqa: E402
from starlette.responses import JSONResponse, Response  # noqa: E402
from starlette.routing import Route  # noqa: E402

from app.lib.settings_ui import load_technology_labels  # noqa: E402
from app.lib.simple import classify_sources, start_rerun  # noqa: E402
from atlas import review, storage  # noqa: E402
from atlas.compliance import load_register  # noqa: E402
from atlas.models import EventType, OutputEnvelope, ScoutSettings  # noqa: E402
from atlas.report.brief import brief_path, write_brief  # noqa: E402
from atlas.scout import settings_store  # noqa: E402

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


app = Starlette(routes=[
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
])

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("SCOUT_API_PORT", "8765"))
    print(f"Market Scout API on http://127.0.0.1:{port} (repo: {REPO}, prefix: {prefix() or 'DEMO FOLDERS'})", flush=True)
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")
