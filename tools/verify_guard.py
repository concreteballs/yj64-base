#!/usr/bin/env python3
"""Verify protected fragments and whole-file Git blob identities before Android build."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

GUARD = Path("PROTECTED-LINE-GUARD")
SECTION_RE = re.compile(
    r"^FILE: (?P<path>.+?) BEGIN ALLOWED\n(?P<content>.*?)\nEND ALLOWED$",
    re.MULTILINE | re.DOTALL,
)


def git_blob_sha(path: str) -> str:
    result = subprocess.run(
        ["git", "hash-object", path],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def main() -> int:
    guard = GUARD.read_text(encoding="utf-8")
    sections = list(SECTION_RE.finditer(guard))
    if not sections:
        raise SystemExit("GUARD CHECK FAILED: no allowed sections found")

    for match in sections:
        path = match.group("path")
        expected = match.group("content")
        if "ЗДЕСЬ " + "ДОЛЖЕН НАХОДИТЬСЯ" in expected:
            raise SystemExit(f"GUARD CHECK FAILED: placeholder remains for {path}")
        working_path = Path(path)
        if not working_path.is_file():
            raise SystemExit(f"GUARD CHECK FAILED: missing working file {path}")
        actual = working_path.read_text(encoding="utf-8")
        if actual.count(expected) != 1:
            raise SystemExit(
                f"GUARD CHECK FAILED: {path}: protected fragment count "
                f"is {actual.count(expected)}, expected 1"
            )

    marker = "EXPECTED-GIT-BLOB-SHA:"
    for line in guard.splitlines():
        if not line.startswith(marker):
            continue
        path, expected_sha = line[len(marker):].split("=", 1)
        actual_sha = git_blob_sha(path)
        if actual_sha != expected_sha:
            raise SystemExit(
                f"GUARD CHECK FAILED: {path}: git blob SHA {actual_sha} "
                f"!= Guard {expected_sha}"
            )

    print("GUARD CHECK PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
