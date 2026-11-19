"""Databricks Volume storage. Everything is written from memory; nothing touches local disk."""
import json
from functools import lru_cache
from io import BytesIO
from typing import Any

from databricks.sdk import WorkspaceClient
from databricks.sdk.errors import NotFound

from atlas.settings import get_settings

# The first six are phase 1. settings/ = saved ScoutSettings and Candidate decisions, scout/ = discovered
# candidates, reports/ = generated PDF and PPTX files.
FOLDERS = ["source_register", "raw", "clean", "facts", "output", "logs", "settings", "scout", "reports", "companies"]


@lru_cache
def _client() -> WorkspaceClient:
    s = get_settings()
    return WorkspaceClient(host=s.databricks_host, token=s.databricks_token.get_secret_value())


def _full(path: str) -> str:
    return f"{get_settings().volume_root}/{path.strip('/')}"


def ensure_folders() -> None:
    """Create the top-level folders (idempotent)."""
    for folder in FOLDERS:
        _client().files.create_directory(_full(folder))


def write_json(path: str, obj: Any) -> None:
    data = json.dumps(obj, indent=2, ensure_ascii=False).encode("utf-8")
    _client().files.upload(_full(path), BytesIO(data), overwrite=True)


def read_json(path: str) -> Any:
    resp = _client().files.download(_full(path))
    return json.loads(resp.contents.read().decode("utf-8"))


def write_bytes(path: str, data: bytes) -> None:
    """Binary files (PDF, PPTX, PNG). Uploaded from memory, never via a local file."""
    _client().files.upload(_full(path), BytesIO(data), overwrite=True)


def read_bytes(path: str) -> bytes:
    return _client().files.download(_full(path)).contents.read()


def exists(path: str) -> bool:
    try:
        _client().files.get_metadata(_full(path))
        return True
    except NotFound:
        return False


def read_json_or_none(path: str) -> Any:
    """Like read_json, but None when the file does not exist (first run, no saved settings yet)."""
    return read_json(path) if exists(path) else None


def list_dir(path: str = "") -> list[str]:
    """Names of entries in a Volume folder (directories end with '/')."""
    return [
        e.name + ("/" if e.is_directory else "")
        for e in _client().files.list_directory_contents(_full(path))
    ]
