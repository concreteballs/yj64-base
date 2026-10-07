"""YJ-64 LLM connection settings UI.

Keeps provider credentials in the app-private files directory and delegates
network access to llm_api.py.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.popup import Popup
from kivy.uix.spinner import Spinner
from kivy.uix.textinput import TextInput

from llm_api import load_config, save_config, test_llm_api


class LLMSettingsPopup(Popup):
    def __init__(
        self,
        user_data_dir: str | Path,
        on_test: Callable[[], None] | None = None,
        participant_name: str = "Owner",
        on_report: Callable[[str], None] | None = None,
        **kwargs: Any,
    ) -> None:
        self.user_data_dir = Path(user_data_dir)
        self.participant_name = participant_name
        self.on_test = on_test
        self.on_report = on_report
        self._report("settings_init_started")
        config = load_config(
            self.user_data_dir,
            participant_name=self.participant_name,
        )
        self._report("settings_config_loaded")

        content = BoxLayout(orientation="vertical", padding=dp(10), spacing=dp(7))
        content.add_widget(Label(
            text=f"{self.participant_name} / LLM MODEL / API CONNECTION",
            bold=True,
            size_hint_y=None,
            height=dp(36),
        ))

        content.add_widget(Label(text="Provider", size_hint_y=None, height=dp(24)))
        self.provider = Spinner(
            text=config.get("provider") or "openai",
            values=("openai", "gemini"),
            size_hint_y=None,
            height=dp(42),
        )
        self.provider.bind(text=self._provider_changed)
        content.add_widget(self.provider)

        content.add_widget(Label(text="Model", size_hint_y=None, height=dp(24)))
        self.model = TextInput(
            text=config.get("model", ""),
            hint_text="Model ID, e.g. gpt-5.6",
            multiline=False,
            size_hint_y=None,
            height=dp(42),
        )
        content.add_widget(self.model)

        content.add_widget(Label(text="API endpoint", size_hint_y=None, height=dp(24)))
        self.endpoint = TextInput(
            text=config.get("endpoint", ""),
            hint_text="Leave empty for provider default",
            multiline=False,
            size_hint_y=None,
            height=dp(42),
        )
        content.add_widget(self.endpoint)

        content.add_widget(Label(text="API key", size_hint_y=None, height=dp(24)))
        self.api_key = TextInput(
            text=config.get("api_key", ""),
            hint_text="Enter your API key",
            password=True,
            multiline=False,
            size_hint_y=None,
            height=dp(42),
        )
        content.add_widget(self.api_key)

        self.status = Label(
            text="Key is stored only in the app-private config file.",
            size_hint_y=None,
            height=dp(42),
        )
        content.add_widget(self.status)

        row = BoxLayout(spacing=dp(7), size_hint_y=None, height=dp(46))
        save = Button(text="SAVE")
        save.bind(on_release=self._save)
        row.add_widget(save)
        test = Button(text="TEST + COPY")
        test.bind(on_release=self._test)
        row.add_widget(test)
        content.add_widget(row)

        close = Button(text="CLOSE", size_hint_y=None, height=dp(46))
        close.bind(on_release=self.dismiss)
        content.add_widget(close)

        super().__init__(
            title="MODEL CONNECTION",
            content=content,
            size_hint=(0.94, 0.86),
            auto_dismiss=True,
            **kwargs,
        )

    def _report(self, event: str) -> None:
        if self.on_report is not None:
            self.on_report(event)

    def _provider_changed(self, *_: Any) -> None:
        self._report("settings_provider_changed")
        if self.provider.text == "openai":
            self.endpoint.text = self.endpoint.text or "https://api.openai.com/v1/responses"
        elif self.provider.text == "gemini":
            self.endpoint.text = self.endpoint.text or "https://generativelanguage.googleapis.com/v1beta"

    def _save(self, *_: Any) -> None:
        self._report("settings_save_started")
        save_config(
            self.user_data_dir,
            {
                "provider": self.provider.text.strip(),
                "model": self.model.text.strip(),
                "endpoint": self.endpoint.text.strip(),
                "api_key": self.api_key.text,
            },
            participant_name=self.participant_name,
        )
        self.status.text = "Settings saved."
    
    def _test(self, *_: Any) -> None:
        self._report("settings_test_started")
        self._save()
        if self.on_test is not None:
            self.on_test()
        else:
            try:
                result = test_llm_api(
                    self.user_data_dir,
                    participant_name=self.participant_name,
                )
                self.status.text = result["result"]
            except Exception as exc:
                self.status.text = f"FAILED: {type(exc).__name__}: {exc}"
