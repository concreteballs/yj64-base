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
LLM_API_MODULE_CONTENT = "\"\"\"YJ-64 LLM API connectivity module.\n\nProvider-level connectivity ported from kerosene-rose2 without its UI.\n\"\"\"\nfrom __future__ import annotations\n\nimport json\nimport os\nimport ssl\nfrom pathlib import Path\nfrom typing import Any\nfrom urllib.error import HTTPError, URLError\nfrom urllib.request import Request, urlopen\n\nCONFIG_RELATIVE_PATH = Path(\"yj64-llm-config.json\")\n\n\ndef _request(method: str, url: str, headers: dict[str, str], timeout: float = 30.0) -> dict[str, Any]:\n    try:\n        context = ssl.create_default_context()\n        try:\n            import certifi\n            context = ssl.create_default_context(cafile=certifi.where())\n        except Exception:\n            pass\n        with urlopen(Request(url, headers={\"Accept\": \"application/json\", **headers}, method=method), timeout=timeout, context=context) as response:\n            return json.loads(response.read().decode(\"utf-8\"))\n    except HTTPError as exc:\n        detail = exc.read().decode(\"utf-8\", errors=\"replace\")\n        raise RuntimeError(f\"HTTP {exc.code}: {detail[:800]}\") from exc\n    except URLError as exc:\n        raise RuntimeError(f\"Network error: {exc.reason}\") from exc\n    except json.JSONDecodeError as exc:\n        raise RuntimeError(\"API returned invalid JSON\") from exc\n\n\ndef load_config(user_data_dir: str | Path) -> dict[str, str]:\n    path = Path(user_data_dir) / CONFIG_RELATIVE_PATH\n    config: dict[str, str] = {}\n    if path.exists():\n        try:\n            raw = json.loads(path.read_text(encoding=\"utf-8\"))\n            if isinstance(raw, dict):\n                config = {str(k): str(v) for k, v in raw.items()}\n        except (OSError, ValueError):\n            pass\n    return {\n        \"provider\": config.get(\"provider\") or os.getenv(\"YJ64_LLM_PROVIDER\", \"openai\"),\n        \"model\": config.get(\"model\") or os.getenv(\"YJ64_LLM_MODEL\", \"\"),\n        \"api_key\": config.get(\"api_key\") or os.getenv(\"YJ64_LLM_API_KEY\", \"\"),\n        \"endpoint\": config.get(\"endpoint\") or os.getenv(\"YJ64_LLM_ENDPOINT\", \"\"),\n    }\n\n\ndef test_llm_api(user_data_dir: str | Path) -> dict[str, Any]:\n    config = load_config(user_data_dir)\n    provider = config[\"provider\"].strip().lower()\n    key = config[\"api_key\"].strip()\n    if not key:\n        raise RuntimeError(\"LLM API key is not configured\")\n\n    if provider in {\"openai\", \"openai-responses\"}:\n        endpoint = config[\"endpoint\"] or \"https://api.openai.com/v1/responses\"\n        base = endpoint.rstrip(\"/\")\n        if base.endswith(\"/responses\"):\n            base = base[:-len(\"/responses\")]\n        elif base.endswith(\"/chat/completions\"):\n            base = base[:-len(\"/chat/completions\")]\n        data = _request(\"GET\", base + \"/models\", {\"Authorization\": f\"Bearer {key}\"})\n        models = data.get(\"data\", []) if isinstance(data, dict) else []\n        ids = [str(x.get(\"id\")) for x in models if isinstance(x, dict) and x.get(\"id\")]\n    elif provider in {\"gemini\", \"google\", \"google-gemini\"}:\n        endpoint = (config[\"endpoint\"] or \"https://generativelanguage.googleapis.com/v1beta\").rstrip(\"/\")\n        data = _request(\"GET\", endpoint + \"/models\", {\"x-goog-api-key\": key})\n        models = data.get(\"models\", []) if isinstance(data, dict) else []\n        ids = []\n        for item in models:\n            if isinstance(item, dict) and item.get(\"name\"):\n                name = str(item[\"name\"])\n                ids.append(name[7:] if name.startswith(\"models/\") else name)\n    else:\n        raise RuntimeError(f\"Unsupported LLM provider: {config['provider']}\")\n\n    model = config[\"model\"]\n    if model and model not in ids:\n        result = f\"API reachable and key accepted; configured model not listed: {model}\"\n    else:\n        result = f\"API reachable and key accepted; models visible: {len(ids)}\"\n    return {\"provider\": config[\"provider\"], \"model\": model, \"result\": result}\n"
LLM_BUTTON_OLD = "        monitor_button.bind(on_release=self._open_monitor)\n        root.add_widget(monitor_button)\n"
LLM_BUTTON_NEW = "        monitor_button.bind(on_release=self._open_monitor)\n        root.add_widget(monitor_button)\n\n        llm_button = Button(\n            text=\"Test LLM API + Copy Report\",\n            size_hint_y=None,\n            height=72,\n        )\n        llm_button.bind(on_release=self._test_llm_api)\n        root.add_widget(llm_button)\n"
LLM_METHOD_MARKER = "    def _launched_by_internal_agent(self) -> bool:\n"
LLM_METHOD_BLOCK = "    def _test_llm_api(self, *_: Any) -> None:\n        self._append_report(\"llm_api_test_started\")\n        self.status.text = \"Testing LLM API connection...\"\n\n        def run_test(*_args: Any) -> None:\n            try:\n                from llm_api import test_llm_api\n                result = test_llm_api(self.user_data_dir)\n                report = (\n                    \"YJ-64 LLM API TEST\\n\"\n                    f\"Provider: {result['provider']}\\n\"\n                    f\"Model: {result['model']}\\n\"\n                    f\"Result: {result['result']}\"\n                )\n                self._append_report(\n                    \"llm_api_test_succeeded\",\n                    provider=result[\"provider\"],\n                    model=result[\"model\"],\n                    result=result[\"result\"],\n                )\n            except Exception as exc:\n                report = (\n                    \"YJ-64 LLM API TEST\\n\"\n                    \"Result: FAILED\\n\"\n                    f\"Error: {type(exc).__name__}: {exc}\"\n                )\n                self._append_report(\n                    \"llm_api_test_failed\",\n                    error_type=type(exc).__name__,\n                    error=str(exc),\n                )\n            self._copy_to_clipboard(report)\n            self.status.text = report\n\n        Clock.schedule_once(run_test, 0)\n\n    def _copy_to_clipboard(self, text: str) -> None:\n        try:\n            from jnius import autoclass\n            context = autoclass(\"org.kivy.android.PythonActivity\").mActivity\n            clipboard = context.getSystemService(\n                autoclass(\"android.content.Context\").CLIPBOARD_SERVICE\n            )\n            clip = autoclass(\"android.content.ClipData\").newPlainText(\n                \"YJ-64 LLM API report\", text\n            )\n            clipboard.setPrimaryClip(clip)\n        except Exception as exc:\n            self._append_report(\n                \"llm_api_clipboard_failed\",\n                error_type=type(exc).__name__,\n                error=str(exc),\n            )\n\n"
