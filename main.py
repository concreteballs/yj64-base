"""YJ-64 minimal base application with an embedded diagnostic agent."""

from __future__ import annotations

import json
import os
import signal
import time
import uuid
from pathlib import Path
from typing import Any

from kivy.app import App
from kivy.clock import Clock
from kivy.core.clipboard import Clipboard
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput


SERVICE_CLASS = "org.blackmirror.blackmirror.ServiceInternal"
SERVICE_LAUNCH_FLAG = "yj64.internal_agent_launch"


class YJ64BaseApp(App):
    """Minimal target application used to validate the embedded agent."""

    def build(self):
        self.fault_report_path = (
            Path(self.user_data_dir) / "fault-injection-report.json"
        )
        self.status = TextInput(
            text="Starting embedded diagnostic agent...",
            readonly=True,
            multiline=True,
            halign="left",
            size_hint_y=1,
        )

        root = BoxLayout(orientation="vertical", padding=24, spacing=16)
        root.add_widget(
            Label(
                text="YJ-64 Base Application",
                size_hint_y=None,
                height=80,
            )
        )
        root.add_widget(self.status)

        test_button = Button(
            text="TEST: planned crash",
            size_hint_y=None,
            height=72,
        )
        test_button.bind(on_release=self._run_planned_crash)
        root.add_widget(test_button)

        copy_button = Button(
            text="Copy diagnostic report",
            size_hint_y=None,
            height=64,
        )
        copy_button.bind(on_release=self._copy_diagnostic_report)
        root.add_widget(copy_button)

        self._load_previous_fault_report()
        Clock.schedule_once(self._ensure_service_started, 0.5)
        Clock.schedule_interval(self._refresh_status, 1.0)
        return root


    def _load_previous_fault_report(self) -> None:
        """Show the last planned-crash report after a test restart."""
        if not self.fault_report_path.exists():
            return

        try:
            report = json.loads(
                self.fault_report_path.read_text(encoding="utf-8")
            )
        except (OSError, ValueError):
            return

        self.status.text = json.dumps(
            {
                "previous_fault_injection_report": report,
                "message": (
                    "Previous planned-crash report is preserved. "
                    "Press Copy diagnostic report to copy it."
                ),
            },
            indent=2,
            sort_keys=True,
            ensure_ascii=False,
        )

    def _copy_diagnostic_report(self, *_: Any) -> None:
        """Copy the persisted diagnostic report to the clipboard."""
        try:
            if self.fault_report_path.exists():
                report = self.fault_report_path.read_text(encoding="utf-8")
            else:
                report = self.status.text
            Clipboard.copy(report)
        except Exception:
            pass

    def _run_planned_crash(self, *_: Any) -> None:
        """Persist a deterministic crash marker, then abort this app process."""
        report = {
            "event": "planned_crash_requested",
            "test": "YJ64 planned crash detection",
            "test_id": f"FAULT-{uuid.uuid4().hex}",
            "timestamp_ms": int(time.time() * 1000),
            "monotonic_ns": time.monotonic_ns(),
            "pid": os.getpid(),
            "signal": "SIGABRT",
            "message": "The test button requested an intentional process abort.",
            "next_step": (
                "Restart the base application to inspect and copy this report."
            ),
        }

        try:
            self.fault_report_path.write_text(
                json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False),
                encoding="utf-8",
            )
            with self.fault_report_path.open("r+b") as handle:
                handle.flush()
                os.fsync(handle.fileno())
        except OSError as exc:
            self.status.text = json.dumps(
                {
                    "event": "planned_crash_persistence_failed",
                    "error": f"{type(exc).__name__}: {exc}",
                },
                indent=2,
                ensure_ascii=False,
            )
            return

        self.status.text = json.dumps(
            report,
            indent=2,
            sort_keys=True,
            ensure_ascii=False,
        )
        Clock.schedule_once(
            lambda *_args: os.kill(os.getpid(), signal.SIGABRT),
            0.1,
        )

    def _write_runtime_event(self, event: str) -> None:
        """Persist an explicit Activity lifecycle event for diagnostics."""
        try:
            path = Path(self.user_data_dir) / "base-runtime-events.jsonl"
            record = {
                "event": event,
                "timestamp_ms": int(time.time() * 1000),
            }
            with path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(record, sort_keys=True) + "\n")
        except OSError:
            pass

    def on_start(self) -> None:
        self._write_runtime_event("base_activity_started")

    def on_resume(self) -> None:
        self._write_runtime_event("base_activity_resumed")

    def on_pause(self) -> bool:
        self._write_runtime_event("base_activity_paused")
        return True

    def on_stop(self) -> None:
        self._write_runtime_event("base_activity_stopped")

    def _launched_by_internal_agent(self) -> bool:
        try:
            from jnius import autoclass

            activity = autoclass("org.kivy.android.PythonActivity").mActivity
            intent = activity.getIntent()
            return bool(intent.getBooleanExtra(SERVICE_LAUNCH_FLAG, False))
        except Exception:
            return False

    def _ensure_service_started(self, *_: Any) -> None:
        if self._launched_by_internal_agent():
            self.status.text = (
                "Base application started by the internal diagnostic agent."
            )
            return

        try:
            from jnius import autoclass

            service_class = autoclass(SERVICE_CLASS)
            activity = autoclass("org.kivy.android.PythonActivity").mActivity
            service_class.start(activity, "")
            self.status.text = (
                "Diagnostic agent starting first; waiting for self-diagnostic "
                "and bridge handshake..."
            )
        except Exception as exc:
            self.status.text = (
                "Diagnostic agent start failed: "
                f"{type(exc).__name__}: {exc}"
            )

    def _refresh_status(self, *_: Any) -> None:
        report_path = Path(self.user_data_dir) / "diagnostic-agent-status.json"
        if not report_path.exists():
            return

        try:
            data = json.loads(report_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return

        previous_fault_report = None
        if self.fault_report_path.exists():
            try:
                previous_fault_report = json.loads(
                    self.fault_report_path.read_text(encoding="utf-8")
                )
            except (OSError, ValueError):
                previous_fault_report = None

        self.status.text = json.dumps(
            {
                "event": data.get("event", "unknown"),
                "bridge_status": data.get("bridge_status", "unknown"),
                "target_launch": data.get("target_launch", "unknown"),
                "last_command": data.get("last_command"),
                "diagnostic_test": data.get("diagnostic_test"),
                "last_report": data.get("last_report"),
                "previous_fault_injection_report": previous_fault_report,
            },
            indent=2,
            sort_keys=True,
            ensure_ascii=False,
        )


YJ64BaseApp().run()
