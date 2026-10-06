"""YJ-64 guarded edit table.

The section below is the single operational source for this build fix.
Working-file changes must be copied from these exact fragments and verified
as one-match replacements before the build is started.
"""

PROTECTED_FILES = (
    "buildozer.spec",
    "p4a/hook.py",
    ".github/workflows/ci.yml",
    ".github/workflows/android-apk.yml",
)

# Операционный стол
HOOK_BEFORE = """def before_apk_build(toolchain: ToolchainCL) -> None:"""
HOOK_AFTER = """def after_apk_build(toolchain: ToolchainCL) -> None:"""
MONITOR_PROCESS_OLD = "PROCESS = ':service_internal'"
MONITOR_PROCESS_NEW = "PROCESS = ':monitor_ui'"
WORKFLOW_TRIGGER_OLD = "      - '.github/workflows/android-apk.yml'\n"
WORKFLOW_TRIGGER_NEW = "      - '.github/workflows/android-apk.yml'\n      - 'p4a/**'\n      - 'guard.py'\n"

def verify_one_match(text: str, old: str) -> None:
    count = text.count(old)
    if count != 1:
        raise ValueError(f"guard: expected exactly one match, got {count}")

def replace_one(text: str, old: str, new: str) -> str:
    verify_one_match(text, old)
    return text.replace(old, new, 1)
