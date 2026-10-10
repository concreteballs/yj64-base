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

MONITOR_ACTIVITY_OLD = '''<activity android:name="org.blackmirror.blackmirror.MonitorActivity"
    android:process=":service_internal"
    android:exported="false"
    android:label="YJ-64 Internal Monitor" />'''
MONITOR_ACTIVITY_NEW = '''<activity android:name="org.blackmirror.blackmirror.MonitorActivity"
    android:process=":monitor_ui"
    android:exported="false"
    android:label="YJ-64 Internal Monitor"
    android:taskAffinity="org.blackmirror.blackmirror.monitor"
    android:launchMode="singleTask" />'''

MONITOR_LAUNCH_OLD = '''            intent.addFlags(0x10000000)
            activity.startActivity(intent)'''
MONITOR_LAUNCH_NEW = '''            # Keep the monitor in its own Android task.  The base app task
            # remains alive in the background and can be returned to from Recents.
            intent.addFlags(
                0x10000000  # FLAG_ACTIVITY_NEW_TASK
                | 0x00020000  # FLAG_ACTIVITY_REORDER_TO_FRONT
            )
            activity.startActivity(intent)'''

def verify_one_match(text: str, old: str) -> None:
    count = text.count(old)
    if count != 1:
        raise ValueError(f"guard: expected exactly one match, got {count}")

def replace_one(text: str, old: str, new: str) -> str:
    verify_one_match(text, old)
    return text.replace(old, new, 1)
