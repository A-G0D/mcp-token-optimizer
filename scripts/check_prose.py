#!/usr/bin/env python3
"""Writing-hygiene check for tracked markdown and source files.

Scans for things that tend to leak in from AI-assisted editing and shouldn't
end up in this repo's committed text: em-dashes, leftover tool-call XML
fragments accidentally pasted into a file, and employer or internal-tool
references that don't belong in a public repo.

Stdlib only, no dependencies. Not wired into a git hook, run it by hand:

    python scripts/check_prose.py

Exits 1 and prints `path:line: reason` for every hit, 0 if clean. This file is
excluded from its own scan since the pattern list below necessarily contains
the strings it looks for.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

EXTENSIONS = {".md", ".py", ".txt", ".json", ".js", ".ts"}
SKIP_DIRS = {".git", "__pycache__", "node_modules", ".venv", "venv"}

EM_DASH = "—"

TOOL_ARTIFACT_PATTERNS = [
    re.compile(p, re.IGNORECASE)
    for p in [
        r"</invoke>",
        r"<function>",
        r"<parameter\b",
        r"\btool_use\b",
        r"^\s*Human:\s",
        r"^\s*Assistant:\s",
        r"</content>",
    ]
]

# Employer / internal-tool references that shouldn't appear in a public repo.
BLOCKED_KEYWORDS = [
    re.compile(p, re.IGNORECASE)
    for p in [
        r"\bgss\b",
        r"global shop",
        r"gssmail",
        r"fact.graph",
        r"brain.vault",
        r"livefire",
    ]
]


SELF_PATH = Path(__file__).resolve()


def iter_files():
    for path in ROOT.rglob("*"):
        if not path.is_file():
            continue
        if path.resolve() == SELF_PATH:
            continue
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        if path.suffix.lower() not in EXTENSIONS:
            continue
        yield path


def check_file(path: Path) -> list[str]:
    problems: list[str] = []
    try:
        text = path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return problems

    for lineno, line in enumerate(text.splitlines(), start=1):
        if EM_DASH in line:
            problems.append(f"{path}:{lineno}: em-dash found")
        for pat in TOOL_ARTIFACT_PATTERNS:
            if pat.search(line):
                problems.append(f"{path}:{lineno}: possible leaked tool-call artifact ({pat.pattern})")
        for pat in BLOCKED_KEYWORDS:
            if pat.search(line):
                problems.append(f"{path}:{lineno}: blocked keyword ({pat.pattern})")
    return problems


def main() -> int:
    all_problems: list[str] = []
    for path in iter_files():
        all_problems.extend(check_file(path))

    if all_problems:
        for p in all_problems:
            print(p)
        print(f"\n{len(all_problems)} issue(s) found.")
        return 1

    print("check_prose: clean.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
