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
        known_providers = ("openai", "gemini", "groq", "openrouter", "custom")
        current_provider = (config.get("provider") or "openai").strip().lower()
        self.provider = Spinner(
            text=current_provider if current_provider in known_providers else "custom",
            values=known_providers,
            size_hint_y=None,
            height=dp(42),
        )
        self.provider.bind(text=self._provider_changed)
        content.add_widget(self.provider)

        content.add_widget(Label(text="Custom provider name (for Custom only)", size_hint_y=None, height=dp(24)))
        self.custom_provider = TextInput(
            text=config.get("provider", "") if current_provider not in known_providers else "",
            hint_text="Provider ID, e.g. my-provider",
            multiline=False,
            size_hint_y=None,
            height=dp(42),
        )
        self.custom_provider.bind(text=self._custom_provider_changed)
        content.add_widget(self.custom_provider)

        content.add_widget(Label(text="Model", size_hint_y=None, height=dp(24)))
        self.model_picker = Spinner(
            text=config.get("model", "") or "Select or load models",
            values=(),
            size_hint_y=None,
            height=dp(42),
        )
        self.model_picker.bind(text=self._model_selected)
        content.add_widget(self.model_picker)
        self.model = TextInput(
            text=config.get("model", ""),
            hint_text="Or enter model ID manually",
            multiline=False,
            size_hint_y=None,
            height=dp(42),
        )
        self.model.bind(text=self._model_text_changed)
        content.add_widget(self.model)

        content.add_widget(Label(text="API endpoint", size_hint_y=None, height=dp(24)))
        self.endpoint = TextInput(
            text=config.get("endpoint", ""),
            hint_text="Leave empty for provider default",
            multiline=False,
            size_hint_y=None,
            height=dp(42),
        )
        self.endpoint.bind(text=self._endpoint_changed)
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
        self.api_key.bind(text=self._api_key_changed)
        content.add_widget(self.api_key)

        model_row = BoxLayout(spacing=dp(7), size_hint_y=None, height=dp(42))
        self.load_models_button = Button(text="LOAD MODELS")
        self.load_models_button.bind(on_release=self._load_models)
        model_row.add_widget(self.load_models_button)
        content.add_widget(model_row)

        self.status = Label(
            text="Enter an API key to load available models. Key stays in app-private storage after SAVE.",
            size_hint_y=None,
            height=dp(54),
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

    def _provider_id(self) -> str:
        if self.provider.text == "custom":
            return self.custom_provider.text.strip().lower()
        return self.provider.text.strip().lower()

    def _provider_changed(self, *_: Any) -> None:
        self._report("settings_provider_changed")
        defaults = {
            "openai": "https://api.openai.com/v1/responses",
            "gemini": "https://generativelanguage.googleapis.com/v1beta",
            "groq": "https://api.groq.com/openai/v1",
            "openrouter": "https://openrouter.ai/api/v1",
        }
        provider = self._provider_id()
        self.endpoint.text = defaults.get(provider, "")
        self.model_picker.values = ()
        self.model_picker.text = "Select or load models"
        self.model.text = ""
        if self.api_key.text.strip():
            self._schedule_model_load()

    def _custom_provider_changed(self, *_: Any) -> None:
        if self.provider.text == "custom" and self.api_key.text.strip():
            self._schedule_model_load()

    def _endpoint_changed(self, *_: Any) -> None:
        if self.api_key.text.strip():
            self._schedule_model_load()

    def _model_selected(self, _spinner: Spinner, value: str) -> None:
        if value and value != "Select or load models":
            self.model.text = value

    def _model_text_changed(self, _widget: TextInput, value: str) -> None:
        if value and value in self.model_picker.values and self.model_picker.text != value:
            self.model_picker.text = value

    def _api_key_changed(self, *_: Any) -> None:
        self._schedule_model_load()

    def _schedule_model_load(self) -> None:
        from kivy.clock import Clock
        if getattr(self, "_model_load_event", None) is not None:
            self._model_load_event.cancel()
        if not self.api_key.text.strip():
            return
        self.status.text = "API key changed; checking available models..."
        self._model_load_event = Clock.schedule_once(
            lambda _dt: self._load_models(), 1.2
        )

    def _load_models(self, *_: Any) -> None:
        from threading import Thread
        from kivy.clock import Clock
        provider = self._provider_id()
        key = self.api_key.text.strip()
        endpoint = self.endpoint.text.strip()
        if not provider or not key:
            self.status.text = "Select a provider and enter an API key first."
            return
        self.load_models_button.disabled = True
        self.status.text = "Loading models for this API key..."
        self._report("settings_model_list_request_started")

        def worker() -> None:
            try:
                from llm_api import fetch_models
                models = fetch_models(provider, key, endpoint)
                message = f"Loaded {len(models)} models."
            except Exception as exc:
                models = []
                message = f"Model list failed: {type(exc).__name__}: {exc}"

            def finish(_dt: float) -> None:
                self.load_models_button.disabled = False
                if models:
                    self.model_picker.values = tuple(models)
                    current = self.model.text.strip()
                    if current in models:
                        self.model_picker.text = current
                    else:
                        self.model_picker.text = models[0]
                        if not current:
                            self.model.text = models[0]
                    self.status.text = message
                    self._report("settings_model_list_loaded")
                else:
                    self.status.text = message
                    self._report("settings_model_list_failed")
            Clock.schedule_once(finish, 0)

        Thread(target=worker, name="yj64-model-list", daemon=True).start()

    def _save(self, *_: Any) -> None:
        self._report("settings_save_started")
        save_config(
            self.user_data_dir,
            {
                "provider": self._provider_id(),
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
