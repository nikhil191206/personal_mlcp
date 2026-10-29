"""Databricks Volume storage. Everything is written from memory; nothing touches local disk."""
import json
from functools import lru_cache
from io import BytesIO
from typing import Any

from databricks.sdk import WorkspaceClient

from atlas.settings import get_settings

FOLDERS = ["source_register", "raw", "clean", "facts", "output", "logs"]


@lru_cache
def _client() -> WorkspaceClient:
    s = get_settings()
    return WorkspaceClient(host=s.databricks_host, token=s.databricks_token.get_secret_value())


def _full(path: str) -> str:
    return f"{get_settings().volume_root}/{path.strip('/')}"


def ensure_folders() -> None:
    """Create the six top-level folders (idempotent)."""
    for folder in FOLDERS:
        _client().files.create_directory(_full(folder))


def write_json(path: str, obj: Any) -> None:
    data = json.dumps(obj, indent=2, ensure_ascii=False).encode("utf-8")
    _client().files.upload(_full(path), BytesIO(data), overwrite=True)


def read_json(path: str) -> Any:
    resp = _client().files.download(_full(path))
    return json.loads(resp.contents.read().decode("utf-8"))


def list_dir(path: str = "") -> list[str]:
    """Names of entries in a Volume folder (directories end with '/')."""
    return [
        e.name + ("/" if e.is_directory else "")
        for e in _client().files.list_directory_contents(_full(path))
    ]
