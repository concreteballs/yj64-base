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
from kivy.uix.popup import Popup

Window.softinput_mode = "below_target"

SERVICE_CLASS = "org.blackmirror.blackmirror.ServiceInternal"
MONITOR_ACTIVITY_CLASS = "org.blackmirror.blackmirror.MonitorActivity"
SERVICE_LAUNCH_FLAG = "yj64.internal_agent_launch"
REPORT_RELATIVE_PATH = Path("yj64-reports") / "yj64-report.jsonl"
TEST_COMMAND_RELATIVE_PATH = Path("yj64-test-command.json")
TEST_RESULT_RELATIVE_PATH = Path("yj64-test-result.json")


class YJ64BaseApp(App):
    def build(self):
        from message_distributor import MessageDistributor
        self.message_distributor = MessageDistributor()
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

        import_keys_button = Button(
            text="Import API Keys File",
            size_hint_y=None,
            height=72,
        )
        import_keys_button.bind(on_release=self._open_monitor)
        root.add_widget(import_keys_button)

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

        participant_column = BoxLayout(
            orientation="vertical",
            spacing=8,
            size_hint_y=None,
            height=340,
        )
        participant_column.add_widget(Label(
            text="PARTICIPANTS",
            size_hint_y=None,
            height=36,
        ))
        self.participant_buttons = {}
        for participant_name in ("Participant 1", "Participant 2", "Participant 3"):
            button = Button(
                text=participant_name,
                size_hint_y=None,
                height=54,
            )
            button.bind(
                on_release=lambda _button, name=participant_name:
                self._open_participant_menu(name)
            )
            self.participant_buttons[participant_name] = button
            participant_column.add_widget(button)
        dialogue_button = Button(
            text="START GROUP DIALOGUE",
            size_hint_y=None,
            height=58,
        )
        dialogue_button.bind(on_release=self._open_group_dialogue)
        participant_column.add_widget(dialogue_button)
        self.mode_button = Button(
            text="REQUEST MODE: TEXT",
            size_hint_y=None,
            height=54,
        )
        self.mode_button.bind(on_release=self._toggle_request_mode)
        participant_column.add_widget(self.mode_button)
        root.add_widget(participant_column)
        self._refresh_participant_buttons()

        self._write_main_pid()
        self._append_report(
            "base_ui_ready",
            pid=os.getpid(),
            process_name=self._process_name(),
        )

        Clock.schedule_once(self._ensure_service_started, 0.5)
        Clock.schedule_interval(self._refresh_status, 1.0)
        Clock.schedule_interval(self._refresh_participant_buttons, 1.0)
        Clock.schedule_interval(self._poll_test_command, 0.5)
        return root

    def _toggle_request_mode(self, *_: Any) -> None:
        mode = self.message_distributor.toggle_mode()
        self.mode_button.text = f"REQUEST MODE: {mode.upper()}"
        self._append_report(
            "message_mode_changed",
            mode=mode,
            note=(
                "Agent mode is a route marker only; the agent API adapter is not implemented yet."
                if mode == "agent" else "Text mode selected."
            ),
        )
        self.status.text = (
            "Text mode selected."
            if mode == "text"
            else "Practical/agent mode marker selected; its API adapter is not implemented yet."
        )

    def _participant_config_status(self, participant_name: str) -> dict[str, str | bool]:
        from llm_api import load_config, route_config_exists

        route_id = self.message_distributor.route_for_participant(participant_name)
        configured = route_config_exists(self.user_data_dir, route_id)
        config = load_config(self.user_data_dir, route_id=route_id) if configured else {}
        return {
            "configured": configured,
            "mode": self.message_distributor.mode,
            "route_id": route_id,
            "provider": str(config.get("provider") or ""),
            "model": str(config.get("model") or ""),
        }

    def _refresh_participant_buttons(self, *_: Any) -> None:
        for participant_name, button in self.participant_buttons.items():
            status = self._participant_config_status(participant_name)
            if status["configured"]:
                button.background_color = (0.2, 0.8, 0.2, 1)
                button.text = f"{participant_name}  [CONNECTED]"
            else:
                button.background_color = (1, 1, 1, 1)
                button.text = participant_name

    def _open_participant_menu(self, participant_name: str) -> None:
        status = self._participant_config_status(participant_name)
        self._append_report(
            "participant_menu_opened",
            participant=participant_name,
            configured=status["configured"],
            mode=status["mode"],
            provider=status["provider"],
            model=status["model"],
        )

        content = BoxLayout(
            orientation="vertical",
            spacing=8,
            padding=12,
        )
        title = Label(
            text=f"{participant_name}\n"
                 f"{status['provider'] or 'not configured'} / "
                 f"{status['model'] or 'no model'}",
            size_hint_y=None,
            height=70,
        )
        content.add_widget(title)

        write_button = Button(text="WRITE / GET ANSWER", size_hint_y=None, height=56)
        write_button.bind(
            on_release=lambda *_: (
                popup.dismiss(),
                self._open_participant_chat(participant_name),
            )
        )
        content.add_widget(write_button)

        settings_button = Button(text="SETTINGS", size_hint_y=None, height=56)
        settings_button.bind(
            on_release=lambda *_: (
                popup.dismiss(),
                self._open_participant_settings(participant_name),
            )
        )
        content.add_widget(settings_button)

        close_button = Button(text="CLOSE", size_hint_y=None, height=56)
        close_button.bind(on_release=lambda *_: popup.dismiss())
        content.add_widget(close_button)

        popup = Popup(
            title=participant_name,
            content=content,
            size_hint=(0.9, 0.55),
        )
        popup.open()

    def _open_participant_settings(self, participant_name: str) -> None:
        self._append_report(
            "participant_settings_opened",
            participant=participant_name,
        )
        from llm_settings import LLMSettingsPopup
        route_id = self.message_distributor.route_for_participant(participant_name)
        LLMSettingsPopup(
            self.user_data_dir,
            route_id=route_id,
            on_report=lambda event, **data: self._append_report(
                "router_" + event,
                participant=participant_name,
                **data,
            ),
            on_copy=self._copy_to_clipboard,
        ).open()

    def _open_participant_chat(self, participant_name: str) -> None:
        status = self._participant_config_status(participant_name)
        self._append_report(
            "participant_chat_opened",
            participant=participant_name,
            configured=status["configured"],
            mode=status["mode"],
            provider=status["provider"],
            model=status["model"],
        )

        content = BoxLayout(orientation="vertical", spacing=8, padding=12)
        output = TextInput(
            text=f"{participant_name} response will appear here.",
            readonly=True,
            multiline=True,
        )
        prompt = TextInput(
            hint_text=f"Message to {participant_name}...",
            multiline=True,
            size_hint_y=None,
            height=110,
            write_tab=False,
        )
        send = Button(text="SEND", size_hint_y=None, height=54)
        close = Button(text="CLOSE", size_hint_y=None, height=54)

        content.add_widget(output)
        content.add_widget(prompt)
        content.add_widget(send)
        content.add_widget(close)

        popup = Popup(
            title=f"{participant_name} CHAT",
            content=content,
            size_hint=(0.94, 0.72),
        )
        self.message_distributor.set_private_participant(participant_name)
        popup.bind(
            on_dismiss=lambda *_: self.message_distributor.set_private_participant(None)
        )

        def send_message(*_args: Any) -> None:
            message = prompt.text.strip()
            if not message:
                return
            prompt.text = ""
            send.disabled = True
            output.text = "Sending..."
            self._append_report(
                "participant_request_started",
                participant=participant_name,
                route_id=status["route_id"],
                mode=self.message_distributor.mode,
                prompt=message,
                provider=status["provider"],
                model=status["model"],
            )
            self.chat_output.text += f"\n\nOwner: {message}"

            def run_chat() -> None:
                try:
                    self._append_report(
                        "participant_api_request_sent",
                        participant=participant_name,
                        route_id=status["route_id"],
                        mode=self.message_distributor.mode,
                        provider=status["provider"],
                        model=status["model"],
                    )
                    result = self.message_distributor.dispatch_message(
                        self.user_data_dir,
                        participant_name,
                        message,
                        report=lambda event, **data: self._append_report(
                            "participant_" + event,
                            participant=participant_name,
                            **data,
                        ),
                    )
                    response = result["response"]
                    event = (
                        "participant_api_response_received",
                        {
                            "participant": participant_name,
                            "provider": result["provider"],
                            "model": result["model"],
                            "response": response,
                        },
                    )
                    text_value = response
                except Exception as exc:
                    event = (
                        "participant_request_failed",
                        {
                            "participant": participant_name,
                            "error_type": type(exc).__name__,
                            "error": str(exc),
                        },
                    )
                    text_value = (
                        f"FAILED: {type(exc).__name__}: {exc}"
                    )

                def finish(*_finish_args: Any) -> None:
                    self._append_report(event[0], **event[1])
                    output.text = text_value
                    if event[0] == "participant_api_response_received":
                        self.chat_output.text += f"\n\n{participant_name}:\n{text_value}"
                    send.disabled = False

                Clock.schedule_once(finish, 0)

            from threading import Thread
            Thread(
                target=run_chat,
                name=f"yj64-{participant_name.lower().replace(' ', '-')}-chat",
                daemon=True,
            ).start()

        send.bind(on_release=send_message)
        close.bind(on_release=lambda *_: popup.dismiss())
        popup.open()

    def _open_group_dialogue(self, *_: Any) -> None:
        self.message_distributor.set_private_participant(None)
        participants = [
            name
            for name in ("Participant 1", "Participant 2", "Participant 3")
            if self._participant_config_status(name)["configured"]
        ]
        if len(participants) < 2:
            self._append_report(
                "group_dialogue_start_rejected",
                reason="at_least_two_participants_required",
                participants=participants,
            )
            self.status.text = "Configure at least two participants first."
            return

        self.message_distributor.reset_queue()
        self._append_report(
            "group_dialogue_opened",
            participants=participants,
            mode=self.message_distributor.mode,
            route_ids={
                name: self.message_distributor.route_for_participant(name)
                for name in participants
            },
        )
        content = BoxLayout(orientation="vertical", spacing=8, padding=12)
        output = TextInput(
            text="Group dialogue is ready.\n",
            readonly=True,
            multiline=True,
        )
        prompt = TextInput(
            hint_text="Your question to the participants...",
            multiline=True,
            size_hint_y=None,
            height=110,
            write_tab=False,
        )
        controls = BoxLayout(
            spacing=8,
            size_hint_y=None,
            height=54,
        )
        send = Button(text="START", size_hint_x=0.5)
        stop = Button(text="STOP DIALOGUE", size_hint_x=0.5, disabled=True)
        controls.add_widget(send)
        controls.add_widget(stop)
        close = Button(text="CLOSE", size_hint_y=None, height=54)
        content.add_widget(output)
        content.add_widget(prompt)
        content.add_widget(controls)
        content.add_widget(close)

        popup = Popup(
            title="GROUP DIALOGUE",
            content=content,
            size_hint=(0.95, 0.86),
            auto_dismiss=False,
        )

        state = {
            "running": False,
            "stop_requested": False,
        }

        def append_chat(text_value: str) -> None:
            output.text = output.text.rstrip() + "\n" + text_value + "\n"

        def request_stop(*_args: Any) -> None:
            state["stop_requested"] = True
            stop.disabled = True
            self._append_report("group_dialogue_stop_requested")
            append_chat("[STOP REQUESTED] Waiting for the current request to finish.")

        def run_dialogue(question: str) -> None:
            messages: list[dict[str, str]] = [
                {"speaker": "Owner", "text": question}
            ]
            seen_by = {name: 0 for name in participants}
            turn = 0
            state["running"] = True
            state["stop_requested"] = False
            self._append_report(
                "group_dialogue_started",
                participants=participants,
                question=question,
            )

            while not state["stop_requested"]:
                participant = self.message_distributor.next_participant(participants)
                status = self._participant_config_status(participant)
                history: list[dict[str, str]] = []
                for item in messages:
                    role = "assistant" if item["speaker"] == participant else "user"
                    history.append({
                        "role": role,
                        "content": f"{item['speaker']}: {item['text']}",
                    })
                new_count = len(messages) - seen_by[participant]
                self._append_report(
                    "group_dialogue_turn_started",
                    participant=participant,
                    turn=turn + 1,
                    new_messages=new_count,
                )
                Clock.schedule_once(
                    lambda _dt, p=participant: append_chat(f"\n[{p} is thinking...]"),
                    0,
                )
                try:
                    result = self.message_distributor.dispatch_message(
                        self.user_data_dir,
                        participant,
                        messages[-1]["text"],
                        history=history,
                        report=lambda event, **data: self._append_report(
                            "group_dialogue_" + event,
                            participant=participant,
                            **data,
                        ),
                    )
                    response = result["response"]
                    messages.append({"speaker": participant, "text": response})
                    seen_by[participant] = len(messages)
                    self._append_report(
                        "group_dialogue_turn_completed",
                        participant=participant,
                        turn=turn + 1,
                        response=response,
                        unseen_messages=new_count,
                    )
                    Clock.schedule_once(
                        lambda _dt, p=participant, r=response:
                        append_chat(f"{p}:\n{r}"),
                        0,
                    )
                except Exception as exc:
                    self._append_report(
                        "group_dialogue_turn_failed",
                        participant=participant,
                        turn=turn + 1,
                        error_type=type(exc).__name__,
                        error=str(exc),
                    )
                    Clock.schedule_once(
                        lambda _dt, p=participant, e=exc:
                        append_chat(f"{p} FAILED: {type(e).__name__}: {e}"),
                        0,
                    )
                    break
                turn += 1
            state["running"] = False
            Clock.schedule_once(
                lambda _dt: (
                    setattr(send, "disabled", False),
                    setattr(stop, "disabled", True),
                ),
                0,
            )
            self._append_report(
                "group_dialogue_stopped",
                participants=participants,
                turns=turn,
                stop_requested=state["stop_requested"],
            )

        def start_dialogue(*_args: Any) -> None:
            question = prompt.text.strip()
            if not question or state["running"]:
                return
            prompt.text = ""
            send.disabled = True
            stop.disabled = False
            output.text = "Group dialogue started.\n"
            from threading import Thread
            Thread(
                target=run_dialogue,
                args=(question,),
                name="yj64-group-dialogue",
                daemon=True,
            ).start()

        send.bind(on_release=start_dialogue)
        stop.bind(on_release=request_stop)
        close.bind(on_release=lambda *_: popup.dismiss())
        popup.open()

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
                route_id="route_owner",
                on_report=lambda event, **data: self._append_report(
                    "router_settings_" + event, **data
                ),
                on_copy=self._copy_to_clipboard,
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
                    route_id="route_owner",
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
                    },
                )
            except Exception as exc:
                report = (
                    "YJ-64 LLM GENERATION TEST\n"
                    "Result: FAILED\n"
                    f"Error: {type(exc).__name__}: {exc}"
                )
                chat_text = report
                event = (
                    "llm_generation_test_failed",
                    {
                        "error_type": type(exc).__name__,
                        "error": str(exc),
                    },
                )

            def finish(*_args: Any) -> None:
                self._append_report(event[0], **event[1])
                self._copy_to_clipboard(report)
                self.chat_output.text = chat_text
                self.status.text = report

            Clock.schedule_once(finish, 0)

        from threading import Thread
        Thread(
            target=run_test,
            name="yj64-llm-generation-test",
            daemon=True,
        ).start()

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
                configured_participants = [
                    name for name in ("Participant 1", "Participant 2", "Participant 3")
                    if self._participant_config_status(name)["configured"]
                ]
                participant = (
                    self.message_distributor.active_participant
                    or (configured_participants[0] if configured_participants else "Owner")
                )
                result = self.message_distributor.dispatch_message(
                    self.user_data_dir,
                    participant,
                    prompt,
                    report=lambda event, **data: self._append_report(
                        "llm_chat_" + event, **data
                    ),
                )
                report = (
                    f"Owner: {prompt}\n"
                    f"{participant}: {result['response']}"
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
                self.chat_output.text += f"\n\n{report}"
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

    def _poll_test_command(self, *_: Any) -> None:
        command_path = Path(self.user_data_dir) / TEST_COMMAND_RELATIVE_PATH
        if not command_path.is_file():
            return
        try:
            command = json.loads(command_path.read_text(encoding="utf-8"))
            command_path.unlink()
        except (OSError, ValueError):
            return
        if command.get("action") != "full_test":
            return
        test_id = str(command.get("test_id") or uuid.uuid4().hex)
        self._run_full_function_test(test_id)

    def _run_full_function_test(self, test_id: str) -> None:
        from threading import Thread

        def step(name: str, action: Any) -> tuple[bool, str]:
            self._append_report("full_test_step_started", test_id=test_id, step=name)
            try:
                result = action()
                self._append_report(
                    "full_test_step_completed",
                    test_id=test_id,
                    step=name,
                    result=result,
                )
                return True, str(result)
            except Exception as exc:
                self._append_report(
                    "full_test_step_failed",
                    test_id=test_id,
                    step=name,
                    error_type=type(exc).__name__,
                    error=str(exc),
                )
                return False, f"{type(exc).__name__}: {exc}"

        def worker() -> None:
            self._append_report("full_test_started", test_id=test_id)
            results: list[str] = []

            ok, value = step("report_storage", lambda: f"report_exists={self.report_path.is_file()}")
            results.append(f"report_storage: {'PASS' if ok else 'FAIL'} ({value})")

            ok, value = step(
                "process_identity",
                lambda: f"pid={os.getpid()},process={self._process_name()}",
            )
            results.append(f"process_identity: {'PASS' if ok else 'FAIL'} ({value})")

            def config_check() -> str:
                from llm_api import load_config
                config = load_config(self.user_data_dir)
                if not config.get("api_key"):
                    raise RuntimeError("LLM API key is not configured")
                if not config.get("model"):
                    raise RuntimeError("LLM model is not configured")
                return f"provider={config.get('provider')},model={config.get('model')}"

            ok, value = step("llm_config", config_check)
            results.append(f"llm_config: {'PASS' if ok else 'FAIL'} ({value})")

            def api_check() -> str:
                from llm_api import test_llm_api
                return str(test_llm_api(
                    self.user_data_dir,
                    report=lambda event, **data: self._append_report(
                        "full_test_llm_api_" + event,
                        test_id=test_id,
                        **data,
                    ),
                )["result"])

            ok, value = step("llm_api", api_check)
            results.append(f"llm_api: {'PASS' if ok else 'FAIL'} ({value})")

            def generation_check() -> str:
                from llm_api import generate_test_response
                result = generate_test_response(
                    self.user_data_dir,
                    report=lambda event, **data: self._append_report(
                        "full_test_llm_generation_" + event,
                        test_id=test_id,
                        **data,
                    ),
                )
                return str(result["response"])

            ok, value = step("llm_generation", generation_check)
            results.append(f"llm_generation: {'PASS' if ok else 'FAIL'} ({value})")

            ok, value = step(
                "diagnostic_agent_status",
                lambda: (
                    "status_file_present"
                    if (Path(self.user_data_dir) / "diagnostic-agent-status.json").is_file()
                    else "status_file_missing"
                ),
            )
            results.append(f"diagnostic_agent_status: {'PASS' if ok else 'FAIL'} ({value})")

            summary = "YJ-64 FULL FUNCTION TEST\n" + "\n".join(results)
            self._append_report("full_test_completed", test_id=test_id, summary=summary)
            result_path = Path(self.user_data_dir) / TEST_RESULT_RELATIVE_PATH
            try:
                result_path.write_text(
                    json.dumps(
                        {
                            "test_id": test_id,
                            "completed": True,
                            "summary": summary,
                            "timestamp_ms": int(time.time() * 1000),
                        },
                        ensure_ascii=False,
                    ),
                    encoding="utf-8",
                )
            except OSError as exc:
                self._append_report(
                    "full_test_result_write_failed",
                    test_id=test_id,
                    error_type=type(exc).__name__,
                    error=str(exc),
                )

            def finish(_dt: float) -> None:
                self._copy_to_clipboard(self._read_report_text())
                self.status.text = summary
            Clock.schedule_once(finish, 0)

        Thread(target=worker, name="yj64-full-function-test", daemon=True).start()

    def _read_report_text(self) -> str:
        try:
            return self.report_path.read_text(encoding="utf-8")
        except OSError as exc:
            return f"YJ-64 REPORT READ FAILED: {type(exc).__name__}: {exc}"

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
