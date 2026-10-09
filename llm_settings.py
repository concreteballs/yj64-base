"""Central LLM router settings UI for YJ-64."""
from __future__ import annotations

from pathlib import Path
from threading import Thread
from typing import Any, Callable

from kivy.clock import Clock
from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.popup import Popup
from kivy.uix.scrollview import ScrollView
from kivy.uix.spinner import Spinner
from kivy.uix.textinput import TextInput

from llm_api import (
    fetch_models,
    generate_test_response,
    list_routes,
    load_config,
    save_config,
    test_all_routes,
    test_llm_api,
)

ROUTE_LABELS = {
    "route_owner": "Owner / route_owner",
    "route_1": "Participant 1 / route_1",
    "route_2": "Participant 2 / route_2",
    "route_3": "Participant 3 / route_3",
}
LABEL_ROUTES = {label: route for route, label in ROUTE_LABELS.items()}
PROVIDERS = ("openai", "gemini", "groq", "openrouter", "custom")


class LLMSettingsPopup(Popup):
    """A single central router editor; participant screens only select a route cell."""

    def __init__(
        self,
        user_data_dir: str | Path,
        on_test: Callable[[], None] | None = None,
        participant_name: str = "Owner",
        route_id: str | None = None,
        on_report: Callable[..., None] | None = None,
        on_copy: Callable[[str], None] | None = None,
        **kwargs: Any,
    ) -> None:
        self.user_data_dir = Path(user_data_dir)
        self.on_test = on_test
        self.on_report = on_report
        self.on_copy = on_copy
        self.route_id = route_id or self._route_from_participant(participant_name)
        self._loading = False
        self._model_load_event = None
        self._report("router_settings_opened", route_id=self.route_id)

        self.content_box = BoxLayout(
            orientation="vertical", padding=dp(10), spacing=dp(7),
            size_hint_y=None,
        )
        self.content_box.bind(minimum_height=self.content_box.setter("height"))
        self.content_box.add_widget(Label(
            text="CENTRAL LLM ROUTER",
            bold=True, size_hint_y=None, height=dp(34),
        ))
        self.content_box.add_widget(Label(
            text="API keys and model settings are saved in the router, not in participants.",
            size_hint_y=None, height=dp(42),
        ))

        self.route_picker = Spinner(
            text=ROUTE_LABELS.get(self.route_id, self.route_id),
            values=tuple(ROUTE_LABELS.values()),
            size_hint_y=None, height=dp(44),
        )
        self.route_picker.bind(text=self._route_selected)
        self.content_box.add_widget(Label(
            text="Router cell / participant route",
            size_hint_y=None, height=dp(22),
        ))
        self.content_box.add_widget(self.route_picker)

        self.saved_routes = Label(
            text="", size_hint_y=None, height=dp(62),
            halign="left", valign="middle",
        )
        self.saved_routes.bind(size=lambda widget, value: setattr(widget, "text_size", value))
        self.content_box.add_widget(self.saved_routes)

        self.provider = Spinner(
            text="openai", values=PROVIDERS,
            size_hint_y=None, height=dp(42),
        )
        self.provider.bind(text=self._provider_changed)
        self.content_box.add_widget(Label(text="Provider", size_hint_y=None, height=dp(22)))
        self.content_box.add_widget(self.provider)

        self.custom_provider = TextInput(
            hint_text="Custom provider ID (only for custom)",
            multiline=False, size_hint_y=None, height=dp(42),
        )
        self.content_box.add_widget(self.custom_provider)

        self.model_picker = Spinner(
            text="Load or select model", values=(),
            size_hint_y=None, height=dp(42),
        )
        self.model_picker.bind(text=self._model_selected)
        self.content_box.add_widget(Label(text="Model", size_hint_y=None, height=dp(22)))
        self.content_box.add_widget(self.model_picker)
        self.model = TextInput(
            hint_text="Model ID", multiline=False,
            size_hint_y=None, height=dp(42),
        )
        self.content_box.add_widget(self.model)

        self.endpoint = TextInput(
            hint_text="API endpoint (leave blank for provider default)",
            multiline=False, size_hint_y=None, height=dp(42),
        )
        self.content_box.add_widget(Label(text="API endpoint", size_hint_y=None, height=dp(22)))
        self.content_box.add_widget(self.endpoint)

        self.api_key = TextInput(
            hint_text="API key for this router cell", password=True,
            multiline=False, size_hint_y=None, height=dp(42),
        )
        self.content_box.add_widget(Label(text="API key (stored by the central router)", size_hint_y=None, height=dp(22)))
        self.content_box.add_widget(self.api_key)

        self.status = Label(
            text="Choose a router cell, enter its connection details, then SAVE.",
            size_hint_y=None, height=dp(56), halign="left", valign="middle",
        )
        self.status.bind(size=lambda widget, value: setattr(widget, "text_size", value))
        self.content_box.add_widget(self.status)

        model_row = BoxLayout(spacing=dp(7), size_hint_y=None, height=dp(44))
        load_models_button = Button(text="LOAD MODELS")
        load_models_button.bind(on_release=self._load_models)
        model_row.add_widget(load_models_button)
        save_button = Button(text="SAVE CELL")
        save_button.bind(on_release=self._save)
        model_row.add_widget(save_button)
        self.content_box.add_widget(model_row)

        test_row = BoxLayout(spacing=dp(7), size_hint_y=None, height=dp(48))
        test_one_button = Button(text="TEST THIS CELL")
        test_one_button.bind(on_release=self._test_one)
        test_row.add_widget(test_one_button)
        test_all_button = Button(text="TEST ALL + COPY REPORT")
        test_all_button.bind(on_release=self._test_all)
        test_row.add_widget(test_all_button)
        self.content_box.add_widget(test_row)

        close_button = Button(text="CLOSE", size_hint_y=None, height=dp(44))
        close_button.bind(on_release=self.dismiss)
        self.content_box.add_widget(close_button)

        scroll = ScrollView(do_scroll_x=False)
        scroll.add_widget(self.content_box)
        super().__init__(
            title="CENTRAL ROUTER",
            content=scroll,
            size_hint=(0.96, 0.92),
            auto_dismiss=False,
            **kwargs,
        )
        self._load_route_fields()
        self._refresh_saved_routes()

    @staticmethod
    def _route_from_participant(participant_name: str) -> str:
        mapping = {
            "Owner": "route_owner",
            "Participant 1": "route_1",
            "Participant 2": "route_2",
            "Participant 3": "route_3",
        }
        return mapping.get(participant_name, "route_owner")

    def _report(self, event: str, **data: Any) -> None:
        if self.on_report is not None:
            try:
                self.on_report(event, **data)
            except TypeError:
                self.on_report(event)

    def _provider_id(self) -> str:
        if self.provider.text == "custom":
            return self.custom_provider.text.strip().lower()
        return self.provider.text.strip().lower()

    def _route_selected(self, _spinner: Spinner, label: str) -> None:
        selected = LABEL_ROUTES.get(label)
        if selected and selected != self.route_id:
            self.route_id = selected
            self._load_route_fields()

    def _load_route_fields(self) -> None:
        self._loading = True
        config = load_config(self.user_data_dir, route_id=self.route_id)
        provider = config.get("provider", "") or "openai"
        self.provider.text = provider if provider in PROVIDERS else "custom"
        self.custom_provider.text = provider if provider not in PROVIDERS else ""
        self.model.text = config.get("model", "")
        self.model_picker.text = config.get("model", "") or "Load or select model"
        self.endpoint.text = config.get("endpoint", "")
        self.api_key.text = config.get("api_key", "")
        self._loading = False
        self._report("router_cell_loaded", route_id=self.route_id,
                     provider=config.get("provider", ""), model=config.get("model", ""),
                     configured=bool(config.get("api_key") and config.get("model")))

    def _refresh_saved_routes(self) -> None:
        routes = list_routes(self.user_data_dir)
        if not routes:
            self.saved_routes.text = "Saved connections: none yet"
            return
        self.saved_routes.text = "Saved connections:\n" + "\n".join(
            f"{item['route_id']} — {item['provider']} / {item['model']}"
            for item in routes
        )

    def _provider_changed(self, *_: Any) -> None:
        if self._loading:
            return
        defaults = {
            "openai": "https://api.openai.com/v1",
            "gemini": "https://generativelanguage.googleapis.com/v1beta",
            "groq": "https://api.groq.com/openai/v1",
            "openrouter": "https://openrouter.ai/api/v1",
        }
        self.endpoint.text = defaults.get(self._provider_id(), "")
        self.model_picker.values = ()
        self.model_picker.text = "Load or select model"
        self.model.text = ""

    def _model_selected(self, _spinner: Spinner, value: str) -> None:
        if value and value != "Load or select model":
            self.model.text = value

    def _load_models(self, *_: Any) -> None:
        provider, key, endpoint = self._provider_id(), self.api_key.text.strip(), self.endpoint.text.strip()
        if not provider or not key:
            self.status.text = "Select a provider and enter an API key first."
            return
        self.status.text = "Loading model list from provider..."
        self._report("router_model_list_started", route_id=self.route_id, provider=provider)

        def worker() -> None:
            try:
                models = fetch_models(provider, key, endpoint)
                error = ""
            except Exception as exc:
                models = []
                error = f"{type(exc).__name__}: {exc}"

            def finish(_dt: float) -> None:
                if models:
                    self.model_picker.values = tuple(models)
                    if self.model.text.strip() in models:
                        self.model_picker.text = self.model.text.strip()
                    else:
                        self.model_picker.text = models[0]
                        if not self.model.text.strip():
                            self.model.text = models[0]
                    self.status.text = f"Loaded {len(models)} models for {self.route_id}."
                    self._report("router_model_list_loaded", route_id=self.route_id,
                                 provider=provider, count=len(models), models=models)
                else:
                    self.status.text = f"Model list failed: {error or 'no models returned'}"
                    self._report("router_model_list_failed", route_id=self.route_id,
                                 provider=provider, error=error)
            Clock.schedule_once(finish, 0)

        Thread(target=worker, name="yj64-router-model-list", daemon=True).start()

    def _save(self, *_: Any) -> None:
        provider = self._provider_id()
        if not provider or not self.api_key.text.strip() or not self.model.text.strip():
            self.status.text = "Provider, API key, and model are required."
            return
        self._report("router_cell_save_started", route_id=self.route_id, provider=provider, model=self.model.text.strip())
        save_config(
            self.user_data_dir,
            {
                "provider": provider,
                "model": self.model.text.strip(),
                "endpoint": self.endpoint.text.strip(),
                "api_key": self.api_key.text.strip(),
            },
            route_id=self.route_id,
        )
        self.status.text = f"Saved central router cell: {self.route_id}"
        self._report("router_cell_saved", route_id=self.route_id, provider=provider, model=self.model.text.strip())
        self._refresh_saved_routes()

    def _test_one(self, *_: Any) -> None:
        self._save()
        self.status.text = f"Testing text generation through {self.route_id}..."

        def worker() -> None:
            lines = [f"YJ-64 ROUTER TEST — {self.route_id}"]
            try:
                result = generate_test_response(
                    self.user_data_dir, route_id=self.route_id,
                    report=lambda event, **data: self._report(event, **data),
                )
                lines.extend([
                    "Result: SUCCESS", f"Provider: {result['provider']}",
                    f"Model: {result['model']}", f"Response: {result['response']}",
                ])
            except Exception as exc:
                lines.extend(["Result: FAILED", f"Error: {type(exc).__name__}: {exc}"])
            report_text = "\n".join(lines)

            def finish(_dt: float) -> None:
                self.status.text = report_text
                if self.on_copy is not None:
                    self.on_copy(report_text)
            Clock.schedule_once(finish, 0)

        Thread(target=worker, name="yj64-router-test-one", daemon=True).start()

    def _test_all(self, *_: Any) -> None:
        self._save()
        self.status.text = "Testing all saved router cells. This may take a while..."

        def worker() -> None:
            try:
                result = test_all_routes(
                    self.user_data_dir,
                    report=lambda event, **data: self._report(event, **data),
                )
                report_text = result["report"]
            except Exception as exc:
                report_text = f"YJ-64 CENTRAL ROUTER TEST\nFAILED: {type(exc).__name__}: {exc}"
                self._report("router_all_test_failed", error_type=type(exc).__name__, error=str(exc))

            def finish(_dt: float) -> None:
                self.status.text = report_text
                if self.on_copy is not None:
                    self.on_copy(report_text)
            Clock.schedule_once(finish, 0)

        Thread(target=worker, name="yj64-router-test-all", daemon=True).start()
