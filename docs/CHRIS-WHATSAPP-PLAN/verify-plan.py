"""Read-only plan integrity and source-drift check; no provider calls or writes."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import sys


def matches(path: Path, entry: dict) -> bool:
    if not path.is_file():
        return False
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() == entry["sha256"]:
        return True
    # Git may check the same source out with CRLF on Windows.
    normalized = raw.replace(b"\r\n", b"\n")
    return hashlib.sha256(normalized).hexdigest() == entry.get("lf_sha256")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, help="WACRM worktree to compare at build start")
    args = parser.parse_args()
    root = Path(__file__).resolve().parent
    manifest = json.loads((root / "source-manifest.json").read_text(encoding="utf-8"))
    errors: list[str] = []
    drift: list[str] = []
    for entry in manifest["files"]:
        if entry["kind"] == "fleet_behaviour_reference":
            snapshot = root / entry["snapshot"]
            if not matches(snapshot, entry):
                errors.append(f"Snapshot missing or changed: {entry['snapshot']}")
        source = (args.source_root / entry["relative_path"]
                  if args.source_root and entry["kind"] == "wacrm_source"
                  else Path(entry["original_path"]))
        if not source.is_file():
            drift.append(f"Unavailable source: {source}")
        elif not matches(source, entry):
            drift.append(f"Changed source: {source}")
    documents = sorted(root.glob("*.md"))
    for document in documents:
        for target in re.findall(r"\]\(([^)]+)\)", document.read_text(encoding="utf-8")):
            if "://" in target or target.startswith("#"):
                continue
            relative = target.split("#", 1)[0].strip("<>")
            if not (document.parent / relative).is_file():
                errors.append(f"Broken link in {document.name}: {target}")
    matrix = (root / "08-ACCEPTANCE-MATRIX.md").read_text(encoding="utf-8")
    case_ids = re.findall(r"^\| ([A-Z]\d{2}) \|", matrix, re.MULTILINE)
    if len(case_ids) != len(set(case_ids)):
        errors.append("Duplicate acceptance scenario ID")
    tasks = (root / "07-IMPLEMENTATION-TASKS.md").read_text(encoding="utf-8")
    task_ids = re.findall(r"^## (T\d{2}):", tasks, re.MULTILINE)
    if task_ids != [f"T{i:02}" for i in range(20)]:
        errors.append("Implementation tasks must cover T00 through T19 exactly once")
    result = {
        "integrity": "failed" if errors else "passed",
        "documents": len(documents),
        "word_count": sum(len(p.read_text(encoding="utf-8").split()) for p in documents),
        "source_files": len(manifest["files"]),
        "implementation_tasks": len(task_ids),
        "acceptance_scenarios": len(case_ids),
        "errors": errors,
        "source_drift": drift,
    }
    print(json.dumps(result, indent=2))
    return 1 if errors else 2 if drift else 0


if __name__ == "__main__":
    sys.exit(main())
