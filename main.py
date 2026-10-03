"""YJ-64 minimal base application with an embedded diagnostic agent."""

from __future__ import annotations

import hashlib
import hmac
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
BRIDGE_CONFIG_PATH = Path(__file__).resolve().parent / "config" / "bridge.json"


class YJ64BaseApp(App):
    """Minimal target application used to validate the embedded agent."""

    def build(self):
        self.report_dir = Path(self.user_data_dir) / "yj64-reports"
        self.report_dir.mkdir(parents=True, exist_ok=True)
        self.report_path = self.report_dir / "yj64-report.jsonl"
        self.archive_path = self.report_dir / "yj64-diagnostics.zip"
        self.fault_report_path = self.report_dir / "fault-injection-report.json"
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

        path_button = Button(
            text="Copy report path",
            size_hint_y=None,
            height=64,
        )
        path_button.bind(on_release=self._copy_report_path)
        root.add_widget(path_button)

        archive_button = Button(
            text="Create diagnostic archive",
            size_hint_y=None,
            height=64,
        )
        archive_button.bind(on_release=self._create_diagnostic_archive)
        root.add_widget(archive_button)

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


    def _copy_report_path(self, *_: Any) -> None:
        Clipboard.copy(str(self.report_path))
        self.status.text = (
            "Report path copied:\n"
            f"{self.report_path}\n\n"
            "Archive path:\n"
            f"{self.archive_path}"
        )

    def _create_diagnostic_archive(self, *_: Any) -> None:
        import zipfile

        try:
            self.report_dir.mkdir(parents=True, exist_ok=True)
            files = [
                path for path in self.report_dir.iterdir()
                if path.is_file() and path.name != self.archive_path.name
            ]
            with zipfile.ZipFile(
                self.archive_path, "w", zipfile.ZIP_DEFLATED
            ) as archive:
                for path in files:
                    archive.write(path, arcname=path.name)
            Clipboard.copy(str(self.archive_path))
            self.status.text = (
                "Archive created. Its absolute path was copied:\n"
                f"{self.archive_path}"
            )
        except OSError as exc:
            self.status.text = (
                f"Archive creation failed: {type(exc).__name__}: {exc}\n\n"
                f"Report path:\n{self.report_path}\n\n"
                f"Archive path:\n{self.archive_path}"
            )

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
                    "The complete report journal is available for copying."
                ),
                "report_path": str(self.report_path),
                "archive_path": str(self.archive_path),
            },
            indent=2,
            sort_keys=True,
            ensure_ascii=False,
        )

    def _copy_diagnostic_report(self, *_: Any) -> None:
        """Copy the persisted diagnostic report to the clipboard."""
        try:
            report = (
                self.report_path.read_text(encoding="utf-8")
                if self.report_path.exists()
                else self.status.text
            )
            Clipboard.copy(report)
        except OSError:
            pass

    def _load_bridge_token(self) -> str:
        """Load the shared bridge token used to sign persisted fault reports."""
        config = json.loads(BRIDGE_CONFIG_PATH.read_text(encoding="utf-8"))
        token = config["bridge"]["token"]
        if not isinstance(token, str) or not token:
            raise ValueError("bridge token is missing or invalid")
        return token

    @staticmethod
    def _sign_report(report: dict[str, Any], token: str) -> str:
        """Return an HMAC-SHA256 signature for the report without signature fields."""
        unsigned = {
            key: value
            for key, value in report.items()
            if key not in {"signature", "signature_algorithm"}
        }
        canonical = json.dumps(
            unsigned,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
        return hmac.new(
            token.encode("utf-8"), canonical, hashlib.sha256
        ).hexdigest()

    def _run_planned_crash(self, *_: Any) -> None:
        """Sign and persist the original crash report, then abort this process."""
        report = {
            "schema": "yj64.diagnostic.v1",
            "agent": "yj64-base-application",
            "event": "planned_crash_requested",
            "message_id": f"INT-{uuid.uuid4().hex}",
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
        report["report_id"] = report["message_id"]

        try:
            token = self._load_bridge_token()
            report["signature_algorithm"] = "HMAC-SHA256"
            report["signature"] = self._sign_report(report, token)
        except (OSError, KeyError, TypeError, ValueError) as exc:
            self.status.text = json.dumps(
                {
                    "event": "planned_crash_signing_failed",
                    "error": f"{type(exc).__name__}: {exc}",
                },
                indent=2,
                ensure_ascii=False,
            )
            return

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
            {
                **report,
                "report_path": str(self.report_path),
                "archive_path": str(self.archive_path),
            },
            indent=2,
            sort_keys=True,
            ensure_ascii=False,
        )
        Clock.schedule_once(
            lambda *_args: os.kill(os.getpid(), signal.SIGABRT),
            0.1,
        )

    def _append_report_event(self, event: str, **data: Any) -> None:
        record = {
            "schema": "yj64.diagnostic.v1",
            "agent": "yj64-base-application",
            "event": event,
            "message_id": f"APP-{uuid.uuid4().hex}",
            "timestamp_ms": int(time.time() * 1000),
            "monotonic_ns": time.monotonic_ns(),
            "data": data,
        }
        try:
            self.report_dir.mkdir(parents=True, exist_ok=True)
            with self.report_path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(record, sort_keys=True, ensure_ascii=False) + "\n")
                handle.flush()
                os.fsync(handle.fileno())
        except OSError:
            pass

    def _write_runtime_event(self, event: str) -> None:
        self._append_report_event(event)

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

        status_history = []
        history_path = Path(self.user_data_dir) / "diagnostic-agent-status.jsonl"
        if history_path.exists():
            try:
                lines = [
                    line
                    for line in history_path.read_text(encoding="utf-8").splitlines()
                    if line.strip()
                ]
                for line in lines[-20:]:
                    try:
                        status_history.append(json.loads(line))
                    except ValueError:
                        continue
            except OSError:
                status_history = []

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
                "status_history": status_history,
                "report_path": str(self.report_path),
                "archive_path": str(self.archive_path),
            },
            indent=2,
            sort_keys=True,
            ensure_ascii=False,
        )


YJ64BaseApp().run()
