"""YJ-64 minimal base application with an embedded diagnostic agent."""

from __future__ import annotations

import json
import os
import time
import uuid
from pathlib import Path
from typing import Any

from kivy.app import App
from kivy.clock import Clock
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.core.window import Window
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput

Window.softinput_mode = "below_target"

SERVICE_CLASS = "org.blackmirror.blackmirror.ServiceInternal"
MONITOR_ACTIVITY_CLASS = "org.blackmirror.blackmirror.MonitorActivity"
SERVICE_LAUNCH_FLAG = "yj64.internal_agent_launch"
REPORT_RELATIVE_PATH = Path("yj64-reports") / "yj64-report.jsonl"


class YJ64BaseApp(App):
    def build(self):
        self.report_path = Path(self.user_data_dir) / REPORT_RELATIVE_PATH
        self.pid_path = Path(self.user_data_dir) / "yj64-main-process.pid"
        self.status = Label(
            text="Starting embedded diagnostic agent...",
            halign="left",
            valign="top",
        )
        self.status.bind(
            size=lambda instance, value: setattr(instance, "text_size", value)
        )

        root = BoxLayout(orientation="vertical", padding=24, spacing=16)
        root.add_widget(Label(
            text="YJ-64 Base Application",
            size_hint_y=None,
            height=80,
        ))
        root.add_widget(self.status)

        monitor_button = Button(
            text="Open Internal Monitor",
            size_hint_y=None,
            height=72,
        )
        monitor_button.bind(on_release=self._open_monitor)
        root.add_widget(monitor_button)

        llm_button = Button(
            text="Test LLM API + Copy Report",
            size_hint_y=None,
            height=72,
        )
        llm_button.bind(on_release=self._test_llm_api)
        root.add_widget(llm_button)

        settings_button = Button(
            text="Configure LLM API / Key",
            size_hint_y=None,
            height=72,
        )
        settings_button.bind(on_release=self._open_llm_settings)
        root.add_widget(settings_button)

        generation_button = Button(
            text="Test LLM Generation + Copy",
            size_hint_y=None,
            height=72,
        )
        generation_button.bind(on_release=self._test_llm_generation)
        root.add_widget(generation_button)

        root.add_widget(Label(
            text="LLM CHAT",
            size_hint_y=None,
            height=42,
        ))
        self.chat_output = TextInput(
            text="The successful generation test will appear here.",
            readonly=True,
            multiline=True,
            size_hint_y=None,
            height=180,
        )
        root.add_widget(self.chat_output)

        chat_row = BoxLayout(
            spacing=12,
            size_hint_y=None,
            height=64,
        )
        self.chat_input = TextInput(
            hint_text="Write a message...",
            multiline=True,
            write_tab=False,
            input_type="text",
            keyboard_suggestions=True,
        )
        self.chat_input.bind(focus=self._chat_input_focus_changed)
        chat_row.add_widget(self.chat_input)
        chat_send = Button(
            text="SEND",
            size_hint_x=None,
            width=120,
        )
        chat_send.bind(on_release=self._send_llm_chat)
        chat_row.add_widget(chat_send)
        root.add_widget(chat_row)

        self._write_main_pid()
        self._append_report(
            "base_ui_ready",
            pid=os.getpid(),
            process_name=self._process_name(),
        )

        Clock.schedule_once(self._ensure_service_started, 0.5)
        Clock.schedule_interval(self._refresh_status, 1.0)
        return root

    def _process_name(self) -> str:
        try:
            from jnius import autoclass
            return str(autoclass("android.os.Process").myProcessName())
        except Exception:
            return "unknown"

    def _write_main_pid(self) -> None:
        try:
            self.pid_path.parent.mkdir(parents=True, exist_ok=True)
            self.pid_path.write_text(str(os.getpid()), encoding="utf-8")
        except OSError:
            pass

    def _append_report(self, event: str, **data: Any) -> None:
        try:
            self.report_path.parent.mkdir(parents=True, exist_ok=True)
            record = {
                "schema": "yj64.diagnostic.v1",
                "agent": "yj64-base-application",
                "event": event,
                "timestamp_ms": int(time.time() * 1000),
                "monotonic_ns": time.monotonic_ns(),
                "message_id": f"APP-{uuid.uuid4().hex}",
                "data": data,
            }
            with self.report_path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(record, sort_keys=True) + "\n")
                handle.flush()
                os.fsync(handle.fileno())
        except OSError:
            pass

    def _open_monitor(self, *_: Any) -> None:
        self._append_report(
            "internal_monitor_window_requested",
            main_pid=os.getpid(),
            main_process_name=self._process_name(),
        )
        try:
            from jnius import autoclass
            activity = autoclass("org.kivy.android.PythonActivity").mActivity
            monitor_activity = autoclass(MONITOR_ACTIVITY_CLASS)
            intent = autoclass("android.content.Intent")(activity, monitor_activity)
            # Keep the monitor in its own Android task.  The base app task
            # remains alive in the background and can be returned to from Recents.
            intent.addFlags(
                0x10000000  # FLAG_ACTIVITY_NEW_TASK
                | 0x00020000  # FLAG_ACTIVITY_REORDER_TO_FRONT
            )
            activity.startActivity(intent)
            self.status.text = "Internal Monitor window requested."
        except Exception as exc:
            self.status.text = (
                "Internal Monitor window failed: "
                f"{type(exc).__name__}: {exc}"
            )

    def _open_llm_settings(self, *_: Any) -> None:
        self._append_report("llm_settings_open_requested")
        try:
            self._append_report("llm_settings_import_started")
            from llm_settings import LLMSettingsPopup
            self._append_report("llm_settings_import_succeeded")
            popup = LLMSettingsPopup(
                self.user_data_dir,
                on_test=self._test_llm_api,
                on_report=lambda event: self._append_report(
                    "llm_settings_" + event
                ),
            )
            self._append_report("llm_settings_popup_created")
            popup.open()
            self._append_report("llm_settings_popup_opened")
        except Exception as exc:
            import traceback
            self._append_report(
                "llm_settings_open_failed",
                error_type=type(exc).__name__,
                error=str(exc),
                traceback=traceback.format_exc(),
            )
            self.status.text = (
                "LLM settings failed: "
                f"{type(exc).__name__}: {exc}"
            )

    def _test_llm_api(self, *_: Any) -> None:
        self._append_report("llm_api_test_started")
        self.status.text = "Testing LLM API connection..."

        def run_test() -> None:
            try:
                from llm_api import test_llm_api
                result = test_llm_api(
                    self.user_data_dir,
                    report=lambda event, **data: self._append_report(
                        "llm_api_" + event, **data
                    ),
                )
                report = (
                    "YJ-64 LLM API TEST\n"
                    f"Provider: {result['provider']}\n"
                    f"Model: {result['model']}\n"
                    f"Result: {result['result']}"
                )
                event = (
                    "llm_api_test_succeeded",
                    {
                        "provider": result["provider"],
                        "model": result["model"],
                        "result": result["result"],
                    },
                )
            except Exception as exc:
                report = (
                    "YJ-64 LLM API TEST\n"
                    "Result: FAILED\n"
                    f"Error: {type(exc).__name__}: {exc}"
                )
                event = (
                    "llm_api_test_failed",
                    {
                        "error_type": type(exc).__name__,
                        "error": str(exc),
                    },
                )

            def finish(*_args: Any) -> None:
                self._append_report(event[0], **event[1])
                self._copy_to_clipboard(report)
                self.status.text = report

            Clock.schedule_once(finish, 0)

        from threading import Thread
        Thread(target=run_test, name="yj64-llm-api-test", daemon=True).start()

    def _test_llm_generation(self, *_: Any) -> None:
        self._append_report("llm_generation_test_started")
        self.status.text = "Testing LLM generation..."

        def run_test() -> None:
            chat_text = ""
            try:
                from llm_api import generate_test_response
                result = generate_test_response(
                    self.user_data_dir,
                    report=lambda event, **data: self._append_report(
                        "llm_generation_" + event, **data
                    ),
                )
                chat_text = result["response"]
                report = (
                    "YJ-64 LLM GENERATION TEST\n"
                    f"Provider: {result['provider']}\n"
                    f"Model: {result['model']}\n"
                    f"Prompt: {result['prompt']}\n"
                    "Result: SUCCESS\n"
                    f"Response: {result['response']}"
                )
                event = (
                    "llm_generation_test_succeeded",
                    {
                        "provider": result["provider"],
                        "model": result["model"],
                        "prompt": result["prompt"],
                        "response": result["response"],
                    }
    def _chat_input_focus_changed(self, _instance: Any, focused: bool) -> None:
        self._append_report("llm_chat_input_focus_changed", focused=focused)

    def _send_llm_chat(self, *_: Any) -> None:
        prompt = self.chat_input.text.strip()
        if not prompt:
            return
        self._append_report("llm_chat_send_started", prompt=prompt)
        self.status.text = "Sending chat message to LLM..."
        self.chat_input.text = ""

        def run_chat() -> None:
            try:
                from llm_api import generate_response
                result = generate_response(
                    self.user_data_dir,
                    prompt,
                    report=lambda event, **data: self._append_report(
                        "llm_chat_" + event, **data
                    ),
                )
                report = (
                    f"User: {prompt}\n"
                    f"Model: {result['response']}"
                )
                event = (
                    "llm_chat_send_succeeded",
                    {
                        "provider": result["provider"],
                        "model": result["model"],
                        "prompt": prompt,
                        "response": result["response"],
                    },
                )
            except Exception as exc:
                report = (
                    f"User: {prompt}\n"
                    "Result: FAILED\n"
                    f"Error: {type(exc).__name__}: {exc}"
                )
                event = (
                    "llm_chat_send_failed",
                    {
                        "prompt": prompt,
                        "error_type": type(exc).__name__,
                        "error": str(exc),
                    },
                )

            def finish(*_args: Any) -> None:
                self._append_report(event[0], **event[1])
                self.chat_output.text = report
                self.status.text = report

            Clock.schedule_once(finish, 0)

        from threading import Thread
        Thread(
            target=run_chat,
            name="yj64-llm-chat",
            daemon=True,
        ).start()

    def _send_llm_chat(self, *_: Any) -> None:
        prompt = self.chat_input.text.strip()
        if not prompt:
            return
        self._append_report("llm_chat_send_started", prompt=prompt)
        self.status.text = "Sending chat message to LLM..."
        self.chat_input.text = ""

        def run_chat() -> None:
            try:
                from llm_api import generate_response
                result = generate_response(
                    self.user_data_dir,
                    prompt,
                    report=lambda event, **data: self._append_report(
                        "llm_chat_" + event, **data
                    ),
                )
                report = (
                    f"User: {prompt}
"
                    f"Model: {result['response']}"
                )
                event = (
                    "llm_chat_send_succeeded",
                    {
                        "provider": result["provider"],
                        "model": result["model"],
                        "prompt": prompt,
                        "response": result["response"],
                    },
                )
            except Exception as exc:
                report = (
                    f"User: {prompt}
"
                    "Result: FAILED
"
                    f"Error: {type(exc).__name__}: {exc}"
                )
                event = (
                    "llm_chat_send_failed",
                    {
                        "prompt": prompt,
                        "error_type": type(exc).__name__,
                        "error": str(exc),
                    },
                )

            def finish(*_args: Any) -> None:
                self._append_report(event[0], **event[1])
                self.chat_output.text = report
                self.status.text = report

            Clock.schedule_once(finish, 0)

        from threading import Thread
        Thread(
            target=run_chat,
            name="yj64-llm-chat",
            daemon=True,
        ).start()

    def _copy_to_clipboard(self, text: str) -> None:
        try:
            from jnius import autoclass
            context = autoclass("org.kivy.android.PythonActivity").mActivity
            clipboard = context.getSystemService(
                autoclass("android.content.Context").CLIPBOARD_SERVICE
            )
            clip = autoclass("android.content.ClipData").newPlainText(
                "YJ-64 LLM API report", text
            )
            clipboard.setPrimaryClip(clip)
        except Exception as exc:
            self._append_report(
                "llm_api_clipboard_failed",
                error_type=type(exc).__name__,
                error=str(exc),
            )

    def _launched_by_internal_agent(self) -> bool:
        try:
            from jnius import autoclass
            activity = autoclass("org.kivy.android.PythonActivity").mActivity
            return bool(activity.getIntent().getBooleanExtra(
                SERVICE_LAUNCH_FLAG, False
            ))
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
        path = Path(self.user_data_dir) / "diagnostic-agent-status.json"
        if not path.exists():
            return
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return
        self.status.text = (
            "Embedded diagnostic agent\n"
            f"Bridge: {data.get('bridge_status', 'unknown')}\n"
            f"Self-diagnostic: {data.get('self_diagnostic', 'unknown')}\n"
            f"Base app: {data.get('target_launch', 'unknown')}\n"
            f"Last event: {data.get('event', 'unknown')}"
        )

    def on_start(self) -> None:
        self._append_report(
            "base_activity_started",
            pid=os.getpid(),
            process_name=self._process_name(),
        )

    def on_resume(self) -> None:
        self._append_report("base_activity_resumed")

    def on_pause(self) -> bool:
        self._append_report("base_activity_paused")
        return True

    def on_stop(self) -> None:
        self._append_report("base_activity_stopped")


YJ64BaseApp().run()
