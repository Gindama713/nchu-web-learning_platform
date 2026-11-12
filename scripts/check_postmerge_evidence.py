"""Check portable attachment hashes: UTF-8 text with LF, binary bytes unchanged."""

import hashlib
import json
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1] / "docs/evidence/postmerge-20261019"


def main():
    manifest = json.loads((ROOT / "sha256.json").read_text(encoding="utf-8"))
    entries = list(manifest.items())
    errors = []
    for start in range(0, len(entries), 3):
        for name, expected in entries[start:start + 3]:
            relative = PurePosixPath(name)
            if relative.is_absolute() or ".." in relative.parts or "\\" in name:
                errors.append(f"invalid relative path: {name}")
                continue
            path = ROOT / relative
            data = path.read_bytes()
            if path.suffix in (".json", ".txt", ".md"):
                data = data.replace(b"\r\n", b"\n")
            if hashlib.sha256(data).hexdigest() != expected:
                errors.append(f"hash mismatch: {name}")
    if errors:
        raise SystemExit("\n".join(errors))
    print(f"{len(entries)} evidence hashes: OK (text LF / binary bytes)")


if __name__ == "__main__":
    main()
