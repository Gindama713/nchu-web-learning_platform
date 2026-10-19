"""Check required documents, teacher layout and local Markdown links."""

import re
import sys
from pathlib import Path
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parents[1]
DOCUMENTS = [ROOT / "README.md", *(ROOT / "docs" / name for name in (
    "PRD.md", "APIC.md", "ADR.md", "CHG-RB.md", "DBD.md"
))]
STEERING = [ROOT / "steering" / name for name in (
    "README.md", "product.md", "database.md", "architecture.md", "api-contract.md"
)]
SPEC_CODES = [*(f"{number:03d}" for number in range(1, 20)),
              "010A", "010B", "010C", "010D"]
SPEC_FILES = ("plan.md", "spec.md", "tasks.md", "wireframes.md")


def check() -> list[str]:
    errors = []
    spec_folders = {folder.name[:3].upper() + folder.name[3:4].upper().rstrip("-")
                    for folder in (ROOT / "specs").iterdir() if folder.is_dir()}
    if spec_folders != set(SPEC_CODES):
        errors.append(f"SPEC folders mismatch: missing={sorted(set(SPEC_CODES) - spec_folders)} "
                      f"extra={sorted(spec_folders - set(SPEC_CODES))}")
    specs = [ROOT / "specs" / "README.md"]
    for folder in (ROOT / "specs").iterdir():
        if folder.is_dir():
            specs.extend(folder / name for name in SPEC_FILES)
    for document in DOCUMENTS + STEERING + specs:
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
    print("\n".join(problems) if problems else "Required documents, teacher layout and local links: OK")
    sys.exit(bool(problems))
