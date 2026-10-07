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


# LLM API module transfer and test button
LLM_API_MODULE_PATH = "llm_api.py"
LLM_API_MODULE_CONTENT = "\"\"\"YJ-64 LLM API connectivity module.\n\nProvider-level connectivity ported from kerosene-rose2 without its UI.\n\"\"\"\nfrom __future__ import annotations\n\nimport json\nimport os\nimport ssl\nfrom pathlib import Path\nfrom typing import Any\nfrom urllib.error import HTTPError, URLError\nfrom urllib.request import Request, urlopen\n\nCONFIG_RELATIVE_PATH = Path(\"yj64-llm-config.json\")\n\n\ndef _request(method: str, url: str, headers: dict[str, str], timeout: float = 30.0) -> dict[str, Any]:\n    try:\n        context = ssl.create_default_context()\n        try:\n            import certifi\n            context = ssl.create_default_context(cafile=certifi.where())\n        except Exception:\n            pass\n        with urlopen(Request(url, headers={\"Accept\": \"application/json\", **headers}, method=method), timeout=timeout, context=context) as response:\n            return json.loads(response.read().decode(\"utf-8\"))\n    except HTTPError as exc:\n        detail = exc.read().decode(\"utf-8\", errors=\"replace\")\n        raise RuntimeError(f\"HTTP {exc.code}: {detail[:800]}\") from exc\n    except URLError as exc:\n        raise RuntimeError(f\"Network error: {exc.reason}\") from exc\n    except json.JSONDecodeError as exc:\n        raise RuntimeError(\"API returned invalid JSON\") from exc\n\n\ndef load_config(user_data_dir: str | Path) -> dict[str, str]:\n    path = Path(user_data_dir) / CONFIG_RELATIVE_PATH\n    config: dict[str, str] = {}\n    if path.exists():\n        try:\n            raw = json.loads(path.read_text(encoding=\"utf-8\"))\n            if isinstance(raw, dict):\n                config = {str(k): str(v) for k, v in raw.items()}\n        except (OSError, ValueError):\n            pass\n    return {\n        \"provider\": config.get(\"provider\") or os.getenv(\"YJ64_LLM_PROVIDER\", \"openai\"),\n        \"model\": config.get(\"model\") or os.getenv(\"YJ64_LLM_MODEL\", \"\"),\n        \"api_key\": config.get(\"api_key\") or os.getenv(\"YJ64_LLM_API_KEY\", \"\"),\n        \"endpoint\": config.get(\"endpoint\") or os.getenv(\"YJ64_LLM_ENDPOINT\", \"\"),\n    }\n\n\ndef save_config(user_data_dir: str | Path, config: dict[str, str]) -> None:\n    path = Path(user_data_dir) / CONFIG_RELATIVE_PATH\n    path.parent.mkdir(parents=True, exist_ok=True)\n    path.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding=\"utf-8\")\n\n\ndef test_llm_api(user_data_dir: str | Path) -> dict[str, Any]:\n    config = load_config(user_data_dir)\n    provider = config[\"provider\"].strip().lower()\n    key = config[\"api_key\"].strip()\n    if not key:\n        raise RuntimeError(\"LLM API key is not configured\")\n\n    if provider in {\"openai\", \"openai-responses\"}:\n        endpoint = config[\"endpoint\"] or \"https://api.openai.com/v1/responses\"\n        base = endpoint.rstrip(\"/\")\n        if base.endswith(\"/responses\"):\n            base = base[:-len(\"/responses\")]\n        elif base.endswith(\"/chat/completions\"):\n            base = base[:-len(\"/chat/completions\")]\n        data = _request(\"GET\", base + \"/models\", {\"Authorization\": f\"Bearer {key}\"})\n        models = data.get(\"data\", []) if isinstance(data, dict) else []\n        ids = [str(x.get(\"id\")) for x in models if isinstance(x, dict) and x.get(\"id\")]\n    elif provider in {\"gemini\", \"google\", \"google-gemini\"}:\n        endpoint = (config[\"endpoint\"] or \"https://generativelanguage.googleapis.com/v1beta\").rstrip(\"/\")\n        data = _request(\"GET\", endpoint + \"/models\", {\"x-goog-api-key\": key})\n        models = data.get(\"models\", []) if isinstance(data, dict) else []\n        ids = []\n        for item in models:\n            if isinstance(item, dict) and item.get(\"name\"):\n                name = str(item[\"name\"])\n                ids.append(name[7:] if name.startswith(\"models/\") else name)\n    else:\n        raise RuntimeError(f\"Unsupported LLM provider: {config['provider']}\")\n\n    model = config[\"model\"]\n    if model and model not in ids:\n        result = f\"API reachable and key accepted; configured model not listed: {model}\"\n    else:\n        result = f\"API reachable and key accepted; models visible: {len(ids)}\"\n    return {\"provider\": config[\"provider\"], \"model\": model, \"result\": result}\n"
LLM_BUTTON_OLD = "        monitor_button.bind(on_release=self._open_monitor)\n        root.add_widget(monitor_button)\n"
LLM_BUTTON_NEW = "        monitor_button.bind(on_release=self._open_monitor)\n        root.add_widget(monitor_button)\n\n        llm_button = Button(\n            text=\"Test LLM API + Copy Report\",\n            size_hint_y=None,\n            height=72,\n        )\n        llm_button.bind(on_release=self._test_llm_api)\n        root.add_widget(llm_button)\n"
LLM_METHOD_MARKER = "    def _launched_by_internal_agent(self) -> bool:\n"
LLM_METHOD_BLOCK = "    def _test_llm_api(self, *_: Any) -> None:\n        self._append_report(\"llm_api_test_started\")\n        self.status.text = \"Testing LLM API connection...\"\n\n        def run_test() -> None:\n            try:\n                from llm_api import test_llm_api\n                result = test_llm_api(self.user_data_dir)\n                report = (\n                    \"YJ-64 LLM API TEST\\n\"\n                    f\"Provider: {result['provider']}\\n\"\n                    f\"Model: {result['model']}\\n\"\n                    f\"Result: {result['result']}\"\n                )\n                event = (\n                    \"llm_api_test_succeeded\",\n                    {\n                        \"provider\": result[\"provider\"],\n                        \"model\": result[\"model\"],\n                        \"result\": result[\"result\"],\n                    },\n                )\n            except Exception as exc:\n                report = (\n                    \"YJ-64 LLM API TEST\\n\"\n                    \"Result: FAILED\\n\"\n                    f\"Error: {type(exc).__name__}: {exc}\"\n                )\n                event = (\n                    \"llm_api_test_failed\",\n                    {\n                        \"error_type\": type(exc).__name__,\n                        \"error\": str(exc),\n                    },\n                )\n\n            def finish(*_args: Any) -> None:\n                self._append_report(event[0], **event[1])\n                self._copy_to_clipboard(report)\n                self.status.text = report\n\n            Clock.schedule_once(finish, 0)\n\n        from threading import Thread\n        Thread(target=run_test, name=\"yj64-llm-api-test\", daemon=True).start()\n\n    def _copy_to_clipboard(self, text: str) -> None:\n        try:\n            from jnius import autoclass\n            context = autoclass(\"org.kivy.android.PythonActivity\").mActivity\n            clipboard = context.getSystemService(\n                autoclass(\"android.content.Context\").CLIPBOARD_SERVICE\n            )\n            clip = autoclass(\"android.content.ClipData\").newPlainText(\n                \"YJ-64 LLM API report\", text\n            )\n            clipboard.setPrimaryClip(clip)\n        except Exception as exc:\n            self._append_report(\n                \"llm_api_clipboard_failed\",\n                error_type=type(exc).__name__,\n                error=str(exc),\n            )\n\n"

WORKFLOW_BRANCHES_OLD = "    branches: [main]\n"
WORKFLOW_BRANCHES_NEW = "    branches: [main, 'work/**']\n"
LLM_WORKFLOW_PATHS_OLD = "      - 'main.py'\n      - 'services/**'\n"
LLM_WORKFLOW_PATHS_NEW = "      - 'main.py'\n      - 'services/**'\n      - 'llm_api.py'\n      - 'llm_settings.py'\n"
PY_COMPILE_OLD = "          python -m py_compile main.py services/internal_monitor.py\n"
PY_COMPILE_NEW = "          python -m py_compile main.py services/internal_monitor.py llm_api.py llm_settings.py\n"
LLM_MAIN_IMPORT_BROKEN = "from llm_api import test_llm_api\nfrom llm_settings import LLMSettingsPopup\n"
LLM_MAIN_IMPORT_FIXED = "from llm_api import test_llm_api\n"

LLM_SETTINGS_MODULE_PATH = "llm_settings.py"
LLM_SETTINGS_MODULE_CONTENT = "\"\"\"YJ-64 LLM connection settings UI.\n\nKeeps provider credentials in the app-private files directory and delegates\nnetwork access to llm_api.py.\n\"\"\"\nfrom __future__ import annotations\n\nfrom pathlib import Path\nfrom typing import Any, Callable\n\nfrom kivy.metrics import dp\nfrom kivy.uix.boxlayout import BoxLayout\nfrom kivy.uix.button import Button\nfrom kivy.uix.label import Label\nfrom kivy.uix.popup import Popup\nfrom kivy.uix.spinner import Spinner\nfrom kivy.uix.textinput import TextInput\n\nfrom llm_api import load_config, save_config, test_llm_api\n\n\nclass LLMSettingsPopup(Popup):\n    def __init__(\n        self,\n        user_data_dir: str | Path,\n        on_test: Callable[[], None] | None = None,\n        **kwargs: Any,\n    ) -> None:\n        self.user_data_dir = Path(user_data_dir)\n        self.on_test = on_test\n        config = load_config(self.user_data_dir)\n\n        content = BoxLayout(orientation=\"vertical\", padding=dp(10), spacing=dp(7))\n        content.add_widget(Label(\n            text=\"LLM MODEL / API CONNECTION\",\n            bold=True,\n            size_hint_y=None,\n            height=dp(36),\n        ))\n\n        content.add_widget(Label(text=\"Provider\", size_hint_y=None, height=dp(24)))\n        self.provider = Spinner(\n            text=config.get(\"provider\") or \"openai\",\n            values=(\"openai\", \"gemini\"),\n            size_hint_y=None,\n            height=dp(42),\n        )\n        self.provider.bind(text=self._provider_changed)\n        content.add_widget(self.provider)\n\n        content.add_widget(Label(text=\"Model\", size_hint_y=None, height=dp(24)))\n        self.model = TextInput(\n            text=config.get(\"model\", \"\"),\n            hint_text=\"Model ID, e.g. gpt-5.6\",\n            multiline=False,\n            size_hint_y=None,\n            height=dp(42),\n        )\n        content.add_widget(self.model)\n\n        content.add_widget(Label(text=\"API endpoint\", size_hint_y=None, height=dp(24)))\n        self.endpoint = TextInput(\n            text=config.get(\"endpoint\", \"\"),\n            hint_text=\"Leave empty for provider default\",\n            multiline=False,\n            size_hint_y=None,\n            height=dp(42),\n        )\n        content.add_widget(self.endpoint)\n\n        content.add_widget(Label(text=\"API key\", size_hint_y=None, height=dp(24)))\n        self.api_key = TextInput(\n            text=config.get(\"api_key\", \"\"),\n            hint_text=\"Enter your API key\",\n            password=True,\n            multiline=False,\n            size_hint_y=None,\n            height=dp(42),\n        )\n        content.add_widget(self.api_key)\n\n        self.status = Label(\n            text=\"Key is stored only in the app-private config file.\",\n            size_hint_y=None,\n            height=dp(42),\n        )\n        content.add_widget(self.status)\n\n        row = BoxLayout(spacing=dp(7), size_hint_y=None, height=dp(46))\n        save = Button(text=\"SAVE\")\n        save.bind(on_release=self._save)\n        row.add_widget(save)\n        test = Button(text=\"TEST + COPY\")\n        test.bind(on_release=self._test)\n        row.add_widget(test)\n        content.add_widget(row)\n\n        close = Button(text=\"CLOSE\", size_hint_y=None, height=dp(46))\n        close.bind(on_release=self.dismiss)\n        content.add_widget(close)\n\n        super().__init__(\n            title=\"MODEL CONNECTION\",\n            content=content,\n            size_hint=(0.94, 0.86),\n            auto_dismiss=True,\n            **kwargs,\n        )\n\n    def _provider_changed(self, *_: Any) -> None:\n        if self.provider.text == \"openai\":\n            self.endpoint.text = self.endpoint.text or \"https://api.openai.com/v1/responses\"\n        elif self.provider.text == \"gemini\":\n            self.endpoint.text = self.endpoint.text or \"https://generativelanguage.googleapis.com/v1beta\"\n\n    def _save(self, *_: Any) -> None:\n        save_config(\n            self.user_data_dir,\n            {\n                \"provider\": self.provider.text.strip(),\n                \"model\": self.model.text.strip(),\n                \"endpoint\": self.endpoint.text.strip(),\n                \"api_key\": self.api_key.text,\n            },\n        )\n        self.status.text = \"Settings saved.\"\n    \n    def _test(self, *_: Any) -> None:\n        self._save()\n        if self.on_test is not None:\n            self.on_test()\n        else:\n            try:\n                result = test_llm_api(self.user_data_dir)\n                self.status.text = result[\"result\"]\n            except Exception as exc:\n                self.status.text = f\"FAILED: {type(exc).__name__}: {exc}\"\n"
LLM_SETTINGS_IMPORT_OLD = "from llm_api import test_llm_api\n"
LLM_SETTINGS_IMPORT_NEW = "from llm_api import test_llm_api\nfrom llm_settings import LLMSettingsPopup\n"
LLM_SETTINGS_BUTTON_OLD = "        llm_button.bind(on_release=self._test_llm_api)\n        root.add_widget(llm_button)\n"
LLM_SETTINGS_BUTTON_NEW = "        llm_button.bind(on_release=self._test_llm_api)\n        root.add_widget(llm_button)\n\n        settings_button = Button(\n            text=\"Configure LLM API / Key\",\n            size_hint_y=None,\n            height=72,\n        )\n        settings_button.bind(on_release=self._open_llm_settings)\n        root.add_widget(settings_button)\n"
LLM_SETTINGS_METHOD_MARKER = "    def _test_llm_api(self, *_: Any) -> None:\n"
LLM_SETTINGS_METHOD = "    def _open_llm_settings(self, *_: Any) -> None:\n        popup = LLMSettingsPopup(self.user_data_dir, on_test=self._test_llm_api)\n        popup.open()\n\n"

LLM_MAIN_SETTINGS_IMPORT_OLD = "from llm_api import test_llm_api\\n"
LLM_MAIN_SETTINGS_IMPORT_NEW = "from llm_api import test_llm_api\\nfrom llm_settings import LLMSettingsPopup\\n"
LLM_OPEN_SETTINGS_OLD = "    def _open_llm_settings(self, *_: Any) -> None:\\n        popup = LLMSettingsPopup(self.user_data_dir, on_test=self._test_llm_api)\\n        popup.open()\\n\\n"
LLM_OPEN_SETTINGS_NEW = """    def _open_llm_settings(self, *_: Any) -> None:
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

"""

LLM_SETTINGS_REPORT_OLD = "        on_test: Callable[[], None] | None = None,\n        **kwargs: Any,\n"
LLM_SETTINGS_REPORT_NEW = "        on_test: Callable[[], None] | None = None,\n        on_report: Callable[[str], None] | None = None,\n        **kwargs: Any,\n"
LLM_SETTINGS_REPORT_INIT_OLD = "        self.on_test = on_test\n        config = load_config(self.user_data_dir)\n"
LLM_SETTINGS_REPORT_INIT_NEW = "        self.on_test = on_test\n        self.on_report = on_report\n        self._report(\"settings_init_started\")\n        config = load_config(self.user_data_dir)\n        self._report(\"settings_config_loaded\")\n"
LLM_SETTINGS_REPORT_METHOD = """    def _report(self, event: str) -> None:
        if self.on_report is not None:
            self.on_report(event)

"""
LLM_SETTINGS_SAVE_OLD = "    def _save(self, *_: Any) -> None:\n        save_config(\n"
LLM_SETTINGS_SAVE_NEW = "    def _save(self, *_: Any) -> None:\n        self._report(\"settings_save_started\")\n        try:\n            save_config(\n"

LLM_API_REPORT_SIGNATURE_OLD = "def test_llm_api(user_data_dir: str | Path) -> dict[str, Any]:\n"
LLM_API_REPORT_SIGNATURE_NEW = "def test_llm_api(user_data_dir: str | Path, report: Any = None) -> dict[str, Any]:\n"
LLM_API_SAVE_CONFIG_OLD = "def _report(report: Any, event: str, **data: Any) -> None:\n"
LLM_API_SAVE_CONFIG_NEW = """def save_config(user_data_dir: str | Path, config: dict[str, str]) -> None:
    path = Path(user_data_dir) / CONFIG_RELATIVE_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")


def _report(report: Any, event: str, **data: Any) -> None:
"""
LLM_API_REPORT_HELPER = """def _report(report: Any, event: str, **data: Any) -> None:
    if report is not None:
        report(event, **data)

"""
LLM_API_REPORT_STAGES = (
    ("    config = load_config(user_data_dir)\n", "    _report(report, \"api_config_loaded\")\n    config = load_config(user_data_dir)\n"),
    ("    if not key:\n", "    _report(report, \"api_key_check\", configured=bool(key))\n    if not key:\n"),
    ("        data = _request(\"GET\", base + \"/models\", {\"Authorization\": f\"Bearer {key}\"})\n", "        _report(report, \"api_request_started\", provider=provider, endpoint=base + \"/models\")\n        data = _request(\"GET\", base + \"/models\", {\"Authorization\": f\"Bearer {key}\"})\n        _report(report, \"api_request_succeeded\", provider=provider)\n"),
    ("        data = _request(\"GET\", endpoint + \"/models\", {\"x-goog-api-key\": key})\n", "        _report(report, \"api_request_started\", provider=provider, endpoint=endpoint + \"/models\")\n        data = _request(\"GET\", endpoint + \"/models\", {\"x-goog-api-key\": key})\n        _report(report, \"api_request_succeeded\", provider=provider)\n"),
    ("    return {\"provider\": config[\"provider\"], \"model\": model, \"result\": result}\n", "    _report(report, \"api_test_completed\", provider=config[\"provider\"], model=model, result=result)\n    return {\"provider\": config[\"provider\"], \"model\": model, \"result\": result}\n"),
)
LLM_MAIN_API_CALL_OLD = "                result = test_llm_api(self.user_data_dir)\n"
LLM_MAIN_API_CALL_NEW = "                result = test_llm_api(\n                    self.user_data_dir,\n                    report=lambda event, **data: self._append_report(\n                        \"llm_api_\" + event, **data\n                    ),\n                )\n"

LLM_MAIN_TEST_IMPORT_BROKEN = "                from llm_api import test_llm_api\nfrom llm_settings import LLMSettingsPopup\n"
LLM_MAIN_TEST_IMPORT_FIXED = "                from llm_api import test_llm_api\n"

LLM_API_REQUEST_OLD = "def _request(method: str, url: str, headers: dict[str, str], timeout: float = 30.0) -> dict[str, Any]:\n"
LLM_API_REQUEST_NEW = """def _request(
    method: str,
    url: str,
    headers: dict[str, str],
    timeout: float = 30.0,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    try:
        context = ssl.create_default_context()
        try:
            import certifi
            context = ssl.create_default_context(cafile=certifi.where())
        except Exception:
            pass
        body = None
        request_headers = {"Accept": "application/json", **headers}
        if payload is not None:
            body = json.dumps(payload).encode("utf-8")
            request_headers["Content-Type"] = "application/json"
        with urlopen(
            Request(
                url,
                headers=request_headers,
                method=method,
                data=body,
            ),
            timeout=timeout,
            context=context,
        ) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code}: {detail[:800]}") from exc
    except URLError as exc:
        raise RuntimeError(f"Network error: {exc.reason}") from exc
    except json.JSONDecodeError as exc:
        raise RuntimeError("API returned invalid JSON") from exc


"""
LLM_API_GENERATION_METHOD_OLD = "def _report(report: Any, event: str, **data: Any) -> None:\n"
LLM_API_GENERATION_METHOD_NEW = """def generate_test_response(
    user_data_dir: str | Path,
    report: Any = None,
) -> dict[str, Any]:
    _report(report, "generation_config_loaded")
    config = load_config(user_data_dir)
    provider = config["provider"].strip().lower()
    model = config["model"].strip()
    key = config["api_key"].strip()
    _report(
        report,
        "generation_config_checked",
        provider=provider,
        model=model,
        configured=bool(key and model),
    )
    if not key:
        raise RuntimeError("LLM API key is not configured")
    if not model:
        raise RuntimeError("LLM model is not configured")
    if provider not in {"gemini", "google", "google-gemini"}:
        raise RuntimeError(
            "Generation test currently supports Gemini only"
        )

    endpoint = (
        config["endpoint"]
        or "https://generativelanguage.googleapis.com/v1beta"
    ).rstrip("/")
    prompt = "Reply with exactly: YJ64_OK"
    url = f"{endpoint}/models/{model}:generateContent"
    _report(
        report,
        "generation_request_started",
        provider=provider,
        model=model,
        endpoint=url,
        prompt=prompt,
    )
    data = _request(
        "POST",
        url,
        {"x-goog-api-key": key},
        payload={
            "contents": [
                {
                    "parts": [
                        {"text": prompt},
                    ],
                },
            ],
        },
    )
    _report(report, "generation_response_received", provider=provider)

    candidates = data.get("candidates", [])
    if not isinstance(candidates, list) or not candidates:
        raise RuntimeError(
            f"Gemini returned no candidates: {json.dumps(data, ensure_ascii=False)[:1200]}"
        )
    content = candidates[0].get("content", {})
    parts = content.get("parts", []) if isinstance(content, dict) else []
    texts = [
        str(part["text"])
        for part in parts
        if isinstance(part, dict) and part.get("text") is not None
    ]
    response_text = "".join(texts).strip()
    if not response_text:
        raise RuntimeError(
            f"Gemini returned no text: {json.dumps(data, ensure_ascii=False)[:1200]}"
        )

    _report(
        report,
        "generation_test_completed",
        provider=provider,
        model=model,
        response=response_text,
    )
    return {
        "provider": config["provider"],
        "model": model,
        "prompt": prompt,
        "response": response_text,
    }

"""
LLM_MAIN_GENERATION_BUTTON_OLD = """        settings_button.bind(on_release=self._open_llm_settings)
        root.add_widget(settings_button)
"""
LLM_MAIN_GENERATION_BUTTON_NEW = """        settings_button.bind(on_release=self._open_llm_settings)
        root.add_widget(settings_button)

        generation_button = Button(
            text="Test LLM Generation + Copy",
            size_hint_y=None,
            height=72,
        )
        generation_button.bind(on_release=self._test_llm_generation)
        root.add_widget(generation_button)
"""
LLM_MAIN_GENERATION_METHOD_MARKER = "    def _copy_to_clipboard(self, text: str) -> None:\n"
LLM_API_DUPLICATE_REPORT_OLD = "def _report(report: Any, event: str, **data: Any) -> None:\n\ndef _report(report: Any, event: str, **data: Any) -> None:\n"
LLM_API_DUPLICATE_REPORT_NEW = "def _report(report: Any, event: str, **data: Any) -> None:\n"
LLM_MAIN_GENERATION_METHOD_NEW = """    def _test_llm_generation(self, *_: Any) -> None:
        self._append_report("llm_generation_test_started")
        self.status.text = "Testing LLM generation..."

        def run_test() -> None:
            try:
                from llm_api import generate_test_response
                result = generate_test_response(
                    self.user_data_dir,
                    report=lambda event, **data: self._append_report(
                        "llm_generation_" + event, **data
                    ),
                )
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
                self.status.text = report

            Clock.schedule_once(finish, 0)

        from threading import Thread
        Thread(
            target=run_test,
            name="yj64-llm-generation-test",
            daemon=True,
        ).start()

"""


# Android chat / IME port from kerosene-rose2
CHAT_IMPORT_OLD = "from kivy.uix.label import Label\n"
CHAT_IMPORT_NEW = "from kivy.core.window import Window\nfrom kivy.uix.label import Label\nfrom kivy.uix.textinput import TextInput\n"
CHAT_SOFTINPUT_MARKER = "SERVICE_CLASS = \"org.blackmirror.blackmirror.ServiceInternal\"\n"
CHAT_SOFTINPUT_INSERT = "Window.softinput_mode = \"below_target\"\n\n"
CHAT_UI_OLD = """        generation_button.bind(on_release=self._test_llm_generation)
        root.add_widget(generation_button)
"""
CHAT_UI_NEW = """        generation_button.bind(on_release=self._test_llm_generation)
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
"""
CHAT_GENERATION_METHOD_OLD = """    def _test_llm_generation(self, *_: Any) -> None:
        self._append_report("llm_generation_test_started")
        self.status.text = "Testing LLM generation..."

        def run_test() -> None:
            try:
                from llm_api import generate_test_response
                result = generate_test_response(
                    self.user_data_dir,
                    report=lambda event, **data: self._append_report(
                        "llm_generation_" + event, **data
                    ),
                )
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
                self.status.text = report

            Clock.schedule_once(finish, 0)

        from threading import Thread
        Thread(
            target=run_test,
            name="yj64-llm-generation-test",
            daemon=True,
        ).start()

"""
CHAT_GENERATION_METHOD_NEW = """    def _test_llm_generation(self, *_: Any) -> None:
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

"""
CHAT_METHOD = """    def _chat_input_focus_changed(self, _instance: Any, focused: bool) -> None:
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

"""
CHAT_API_MARKER = "def _report(report: Any, event: str, **data: Any) -> None:\n"
CHAT_API_METHOD = """def generate_response(
    user_data_dir: str | Path,
    prompt: str,
    report: Any = None,
) -> dict[str, Any]:
    _report(report, "generation_config_loaded")
    config = load_config(user_data_dir)
    provider = config["provider"].strip().lower()
    model = config["model"].strip()
    key = config["api_key"].strip()
    _report(
        report,
        "generation_config_checked",
        provider=provider,
        model=model,
        configured=bool(key and model),
    )
    if not key:
        raise RuntimeError("LLM API key is not configured")
    if not model:
        raise RuntimeError("LLM model is not configured")
    if provider not in {"gemini", "google", "google-gemini"}:
        raise RuntimeError("Chat currently supports Gemini only")

    endpoint = (
        config["endpoint"]
        or "https://generativelanguage.googleapis.com/v1beta"
    ).rstrip("/")
    url = f"{endpoint}/models/{model}:generateContent"
    _report(
        report,
        "generation_request_started",
        provider=provider,
        model=model,
        endpoint=url,
        prompt=prompt,
    )
    data = _request(
        "POST",
        url,
        {"x-goog-api-key": key},
        payload={
            "contents": [
                {
                    "parts": [
                        {"text": prompt},
                    ],
                },
            ],
        },
    )
    _report(report, "generation_response_received", provider=provider)
    candidates = data.get("candidates", [])
    if not isinstance(candidates, list) or not candidates:
        raise RuntimeError(
            f"Gemini returned no candidates: {json.dumps(data, ensure_ascii=False)[:1200]}"
        )
    content = candidates[0].get("content", {})
    parts = content.get("parts", []) if isinstance(content, dict) else []
    response_text = "".join(
        str(part["text"])
        for part in parts
        if isinstance(part, dict) and part.get("text") is not None
    ).strip()
    if not response_text:
        raise RuntimeError(
            f"Gemini returned no text: {json.dumps(data, ensure_ascii=False)[:1200]}"
        )
    _report(
        report,
        "generation_completed",
        provider=provider,
        model=model,
        response=response_text,
    )
    return {
        "provider": config["provider"],
        "model": model,
        "prompt": prompt,
        "response": response_text,
    }


"""
CHAT_RECORD_AUDIO_OLD = "android.permissions = INTERNET,FOREGROUND_SERVICE,FOREGROUND_SERVICE_SPECIAL_USE"
CHAT_RECORD_AUDIO_NEW = "android.permissions = INTERNET,FOREGROUND_SERVICE,FOREGROUND_SERVICE_SPECIAL_USE,RECORD_AUDIO"

# Dialog participants / stop semantics
MAIN_DIALOG_STATE_OLD = "        self.report_path = Path(self.user_data_dir) / REPORT_RELATIVE_PATH\n        self.pid_path = Path(self.user_data_dir) / \"yj64-main-process.pid\"\n"
MAIN_DIALOG_STATE_NEW = "        self.report_path = Path(self.user_data_dir) / REPORT_RELATIVE_PATH\n        self.pid_path = Path(self.user_data_dir) / \"yj64-main-process.pid\"\n        self.dialog_stop_requested = False\n        self.chat_generation_active = False\n"
MAIN_DIALOG_UI_OLD = "        root.add_widget(self.chat_output)\n\n        chat_row = BoxLayout(\n            spacing=12,\n            size_hint_y=None,\n            height=64,\n        )\n"
MAIN_DIALOG_UI_NEW = "        root.add_widget(self.chat_output)\n\n        root.add_widget(Label(\n            text=\"PARTICIPANTS: Owner | Participant 1 | Participant 2 | Participant 3\",\n            size_hint_y=None,\n            height=42,\n        ))\n        self.dialog_status = Label(\n            text=\"Dialog ready. Automated participants may continue until stopped.\",\n            size_hint_y=None,\n            height=42,\n        )\n        root.add_widget(self.dialog_status)\n\n        chat_row = BoxLayout(\n            spacing=12,\n            size_hint_y=None,\n            height=64,\n        )\n"
MAIN_DIALOG_STOP_OLD = "        chat_send.bind(on_release=self._send_llm_chat)\n        chat_row.add_widget(chat_send)\n        root.add_widget(chat_row)\n\n        self._write_main_pid()\n"
MAIN_DIALOG_STOP_NEW = "        chat_send.bind(on_release=self._send_llm_chat)\n        chat_row.add_widget(chat_send)\n        root.add_widget(chat_row)\n\n        self.stop_dialog_button = Button(\n            text=\"STOP DIALOG\",\n            size_hint_y=None,\n            height=58,\n        )\n        self.stop_dialog_button.bind(on_release=self._stop_dialog)\n        root.add_widget(self.stop_dialog_button)\n\n        self._write_main_pid()\n"
MAIN_DIALOG_METHOD_MARKER = "    def _chat_input_focus_changed(self, _instance: Any, focused: bool) -> None:\n"
MAIN_DIALOG_METHOD_BLOCK = "    def _stop_dialog(self, *_: Any) -> None:\n        self.dialog_stop_requested = True\n        self._append_report(\n            \"llm_dialog_stop_requested\",\n            generation_active=self.chat_generation_active,\n            policy=\"finish_current_response_then_block_next_automated_turn\",\n        )\n        if self.chat_generation_active:\n            message = \"Dialog stopped: the current response will finish; no next automated participant turn will start.\"\n        else:\n            message = \"Dialog stopped: no automated participant can start another turn. You can still send messages as Owner.\"\n        self.dialog_status.text = message\n        self.status.text = message\n\n    def _automated_turn_allowed(self) -> bool:\n        return not self.dialog_stop_requested\n\n"

# Free-tier model presets layered above the existing editable model field
LLM_FREE_MODELS_OLD = "CONFIG_RELATIVE_PATH = Path(\"yj64-llm-config.json\")\n"
LLM_FREE_MODELS_NEW = "CONFIG_RELATIVE_PATH = Path(\"yj64-llm-config.json\")\nFREE_GEMINI_MODELS = (\n    \"gemini-2.5-flash\",\n    \"gemini-2.5-flash-lite\",\n)\n"
LLM_MODEL_PRESET_UI_OLD = "        content.add_widget(Label(text=\"Model\", size_hint_y=None, height=dp(24)))\n        self.model = TextInput(\n"
LLM_MODEL_PRESET_UI_NEW = "        content.add_widget(Label(text=\"Free-tier model presets\", size_hint_y=None, height=dp(24)))\n        self.model_preset = Spinner(\n            text=(\n                config.get(\"model\", \"\")\n                if config.get(\"model\", \"\") in FREE_GEMINI_MODELS\n                else \"CUSTOM / KEEP CURRENT\"\n            ),\n            values=(\"CUSTOM / KEEP CURRENT\",) + FREE_GEMINI_MODELS,\n            size_hint_y=None,\n            height=dp(42),\n        )\n        self.model_preset.bind(text=self._model_preset_changed)\n        content.add_widget(self.model_preset)\n\n        content.add_widget(Label(text=\"Model\", size_hint_y=None, height=dp(24)))\n        self.model = TextInput(\n"
LLM_MODEL_PRESET_METHOD_MARKER = "    def _provider_changed(self, *_: Any) -> None:\n"
LLM_MODEL_PRESET_METHOD_BLOCK = "    def _model_preset_changed(self, _instance: Any, value: str) -> None:\n        self._report(\"settings_model_preset_changed\")\n        if value != \"CUSTOM / KEEP CURRENT\":\n            self.model.text = value\n\n"

# Free-tier model preset import insertion point
LLM_FREE_MODEL_IMPORT_OLD = """from llm_api import load_config, save_config, test_llm_api
"""
LLM_FREE_MODEL_IMPORT_NEW = """from llm_api import load_config, save_config, test_llm_api

FREE_GEMINI_MODELS = (
    "gemini-2.5-flash",
    "gemini-2.5-flash-lite",
)
"""

# Dialog generation lifecycle
MAIN_DIALOG_ACTIVE_OLD = """        self.chat_input.text = ""

        def run_chat() -> None:
"""
MAIN_DIALOG_ACTIVE_NEW = """        self.chat_input.text = ""
        self.chat_generation_active = True

        def run_chat() -> None:
"""
MAIN_DIALOG_FINISH_OLD = """            def finish(*_args: Any) -> None:
                self._append_report(event[0], **event[1])
                self.chat_output.text = report
                self.status.text = report
"""
MAIN_DIALOG_FINISH_NEW = """            def finish(*_args: Any) -> None:
                self.chat_generation_active = False
                self._append_report(event[0], **event[1])
                self.chat_output.text = report
                self.status.text = report
                if self.dialog_stop_requested:
                    self.dialog_status.text = "Dialog stopped. Current response finished; only Owner can send the next message."
"""


# Automatic APK build for the monitor-api branch
WORKFLOW_ANDROID_BRANCHES_OLD = "    branches: [main, 'work/**']\n"
WORKFLOW_ANDROID_BRANCHES_NEW = "    branches: [main, 'work/**', 'monitor-api']\n"
