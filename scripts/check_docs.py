"""Check the six required documents and their local Markdown links."""

import re
import sys
from pathlib import Path
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parents[1]
DOCUMENTS = [ROOT / "README.md", *(ROOT / "docs" / name for name in (
    "PRD.md", "APIC.md", "ADR.md", "CHG-RB.md", "DBD.md"
))]


def check() -> list[str]:
    errors = []
    for document in DOCUMENTS:
        if not document.is_file():
            errors.append(f"missing: {document.relative_to(ROOT)}")
            continue
        for target in re.findall(r"\]\(([^)]+)\)", document.read_text(encoding="utf-8")):
            if target.startswith(("http://", "https://", "mailto:", "#")):
                continue
            local = unquote(target.split("#", 1)[0])
            if local and not (document.parent / local).exists():
                errors.append(f"{document.relative_to(ROOT)}: broken link {target}")
    return errors


if __name__ == "__main__":
    problems = check()
    print("\n".join(problems) if problems else "Six documents and local links: OK")
    sys.exit(bool(problems))
