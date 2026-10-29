"""Storage test: python -m atlas.storage_check. Must print PASS before anything else is built."""
import os
import sys
from pathlib import Path

from atlas import storage

ROOT = Path(__file__).resolve().parent.parent
SKIP_DIRS = {".venv", ".git", "__pycache__", ".pytest_cache"}
TEST_PATH = "logs/storage_check.json"
PAYLOAD = {"hello": "atlas"}


def _local_files() -> set[str]:
    """All files under the project root, pruning .venv/.git/caches so the walk stays fast."""
    found: set[str] = set()
    for dirpath, dirnames, filenames in os.walk(ROOT):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        found.update(str((Path(dirpath) / f).relative_to(ROOT)) for f in filenames)
    return found


def main() -> int:
    before = _local_files()
    failures: list[str] = []
    try:
        storage.ensure_folders()
        print("1. folders ensured:", ", ".join(storage.FOLDERS))

        storage.write_json(TEST_PATH, PAYLOAD)
        print(f"2. wrote {TEST_PATH}")

        back = storage.read_json(TEST_PATH)
        print("3. read back:", back)
        if back != PAYLOAD:
            failures.append(f"read-back mismatch: {back!r} != {PAYLOAD!r}")

        listing = storage.list_dir("logs")
        print("4. logs/ contains:", listing)
        if "storage_check.json" not in listing:
            failures.append("storage_check.json missing from logs/ listing")
    except Exception as exc:  # report the real cause; do not fall back to anything
        failures.append(f"{type(exc).__name__}: {exc}")

    new_local = _local_files() - before
    print("5. new local files:", sorted(new_local) or "none")
    if new_local:
        failures.append(f"new files on local disk: {sorted(new_local)}")

    if failures:
        print("FAIL")
        for f in failures:
            print(" -", f)
        return 1
    print("PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
