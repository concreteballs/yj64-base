#!/usr/bin/env python3
"""Fail-closed guard for the YJ-64 base diagnostic workflow."""

from pathlib import Path
import ast

ROOT = Path(__file__).resolve().parents[1]

REQUIRED = [
    ROOT / "main.py",
    ROOT / "services" / "internal_monitor.py",
    ROOT / "buildozer.spec",
    ROOT / "config" / "bridge.json",
    ROOT / ".github" / "workflows" / "ci.yml",
]

REQUIRED_TEXT = {
    "main.py": [
        'self.report_dir = Path(self.user_data_dir) / "yj64-reports"',
        'self.report_path = self.report_dir / "yj64-report.jsonl"',
        'self.archive_path = self.report_dir / "yj64-diagnostics.zip"',
        "os.kill(os.getpid(), signal.SIGABRT)",
    ],
    "services/internal_monitor.py": [
        "def report_dir(service: Any) -> Path:",
        "def primary_report_path(service: Any) -> Path:",
        "append_primary_report(service, report)",
        '"event": "report_storage_ready"',
    ],
    ".github/workflows/ci.yml": [
        "python tools/verify_guard.py",
        "GUARD_OK",
    ],
}

def fail(message: str) -> None:
    print(f"GUARD_FAIL: {message}")
    raise SystemExit(1)

def main() -> None:
    for path in REQUIRED:
        if not path.is_file():
            fail(f"missing protected file: {path.relative_to(ROOT)}")

    for relative, needles in REQUIRED_TEXT.items():
        text = (ROOT / relative).read_text(encoding="utf-8")
        for needle in needles:
            if needle not in text:
                fail(f"missing required text in {relative}: {needle}")

    main_source = (ROOT / "main.py").read_text(encoding="utf-8")
    tree = ast.parse(main_source)

    crash_methods = [
        node for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name == "_run_planned_crash"
    ]
    if len(crash_methods) != 1:
        fail("expected exactly one _run_planned_crash method")

    event_keys = []
    for node in ast.walk(crash_methods[0]):
        if isinstance(node, ast.Dict):
            for key in node.keys:
                if isinstance(key, ast.Constant) and key.value == "event":
                    event_keys.append(key)
    if len(event_keys) != 1:
        fail('planned crash report must contain exactly one "event" key')

    for relative in ("main.py", "services/internal_monitor.py"):
        try:
            ast.parse((ROOT / relative).read_text(encoding="utf-8"))
        except SyntaxError as exc:
            fail(f"syntax error in {relative}: {exc}")

    print("GUARD_OK")

if __name__ == "__main__":
    main()
