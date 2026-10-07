"""YJ-64 LLM API connectivity module.

Provider-level connectivity ported from kerosene-rose2 without its UI.
"""
from __future__ import annotations

import json
import os
import ssl
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

CONFIG_RELATIVE_PATH = Path("yj64-llm-config.json")


def _request(
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



def _participant_config_path(
    user_data_dir: str | Path,
    participant_name: str = "Owner",
) -> Path:
    if participant_name.strip().lower() == "owner":
        return Path(user_data_dir) / CONFIG_RELATIVE_PATH
    slug = participant_name.strip().lower().replace(" ", "-")
    return Path(user_data_dir) / f"yj64-llm-config-{slug}.json"


def load_config(
    user_data_dir: str | Path,
    participant_name: str = "Owner",
) -> dict[str, str]:
    path = _participant_config_path(user_data_dir, participant_name)
    config: dict[str, str] = {}
    if path.exists():
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                config = {str(k): str(v) for k, v in raw.items()}
        except (OSError, ValueError):
            pass

    return {
        "provider": config.get("provider") or os.getenv("YJ64_LLM_PROVIDER", "openai"),
        "model": config.get("model") or os.getenv("YJ64_LLM_MODEL", ""),
        "api_key": config.get("api_key") or os.getenv("YJ64_LLM_API_KEY", ""),
        "endpoint": config.get("endpoint") or os.getenv("YJ64_LLM_ENDPOINT", ""),
        "mode": config.get("mode") or "llm",
    }


def participant_config_exists(
    user_data_dir: str | Path,
    participant_name: str,
) -> bool:
    return _participant_config_path(
        user_data_dir,
        participant_name=participant_name,
    ).is_file()


def save_config(
    user_data_dir: str | Path,
    config: dict[str, str],
    participant_name: str = "Owner",
) -> None:
    path = _participant_config_path(user_data_dir, participant_name)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(config, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def generate_test_response(
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
    contents = []
    for item in history or [{"role": "user", "content": prompt}]:
        role = "model" if item.get("role") == "assistant" else "user"
        contents.append({
            "role": role,
            "parts": [{"text": str(item.get("content", ""))}],
        })
    data = _request(
        "POST",
        url,
        {"x-goog-api-key": key},
        payload={"contents": contents},
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


def generate_response(
    user_data_dir: str | Path,
    prompt: str,
    report: Any = None,
    participant_name: str = "Owner",
    history: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    _report(report, "generation_config_loaded")
    config = load_config(user_data_dir, participant_name=participant_name)
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
    if provider in {"openai", "openai-responses"}:
        endpoint = (
            config["endpoint"]
            or "https://api.openai.com/v1/responses"
        ).rstrip("/")
        if endpoint.endswith("/chat/completions"):
            url = endpoint
            payload = {
                "model": model,
                "messages": history or [{"role": "user", "content": prompt}],
            }
        else:
            url = endpoint if endpoint.endswith("/responses") else endpoint + "/responses"
            payload = {
                "model": model,
                "input": history or [{"role": "user", "content": prompt}],
            }
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
            {"Authorization": f"Bearer {key}"},
            payload=payload,
        )
        _report(report, "generation_response_received", provider=provider)
        response_text = str(data.get("output_text") or "").strip()
        if not response_text:
            output = data.get("output", [])
            texts: list[str] = []
            if isinstance(output, list):
                for item in output:
                    if not isinstance(item, dict):
                        continue
                    content = item.get("content", [])
                    if not isinstance(content, list):
                        continue
                    for part in content:
                        if isinstance(part, dict) and part.get("text") is not None:
                            texts.append(str(part["text"]))
            response_text = "".join(texts).strip()
        if not response_text:
            choices = data.get("choices", [])
            if isinstance(choices, list) and choices:
                message = choices[0].get("message", {})
                if isinstance(message, dict):
                    response_text = str(message.get("content") or "").strip()
        if not response_text:
            raise RuntimeError(
                f"OpenAI returned no text: {json.dumps(data, ensure_ascii=False)[:1200]}"
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

    if provider not in {"gemini", "google", "google-gemini"}:
        raise RuntimeError(f"Unsupported LLM provider: {config['provider']}")

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


def _report(report: Any, event: str, **data: Any) -> None:
    if report is not None:
        report(event, **data)


def test_llm_api(
    user_data_dir: str | Path,
    report: Any = None,
    participant_name: str = "Owner",
) -> dict[str, Any]:
    _report(report, "api_config_loaded")
    config = load_config(user_data_dir, participant_name=participant_name)
    provider = config["provider"].strip().lower()
    key = config["api_key"].strip()
    _report(report, "api_key_check", configured=bool(key))
    if not key:
        raise RuntimeError("LLM API key is not configured")

    if provider in {"openai", "openai-responses"}:
        endpoint = config["endpoint"] or "https://api.openai.com/v1/responses"
        base = endpoint.rstrip("/")
        if base.endswith("/responses"):
            base = base[:-len("/responses")]
        elif base.endswith("/chat/completions"):
            base = base[:-len("/chat/completions")]
        _report(report, "api_request_started", provider=provider, endpoint=base + "/models")
        data = _request("GET", base + "/models", {"Authorization": f"Bearer {key}"})
        _report(report, "api_request_succeeded", provider=provider)
        models = data.get("data", []) if isinstance(data, dict) else []
        ids = [str(x.get("id")) for x in models if isinstance(x, dict) and x.get("id")]
    elif provider in {"gemini", "google", "google-gemini"}:
        endpoint = (config["endpoint"] or "https://generativelanguage.googleapis.com/v1beta").rstrip("/")
        _report(report, "api_request_started", provider=provider, endpoint=endpoint + "/models")
        data = _request("GET", endpoint + "/models", {"x-goog-api-key": key})
        _report(report, "api_request_succeeded", provider=provider)
        models = data.get("models", []) if isinstance(data, dict) else []
        ids = []
        for item in models:
            if isinstance(item, dict) and item.get("name"):
                name = str(item["name"])
                ids.append(name[7:] if name.startswith("models/") else name)
    else:
        raise RuntimeError(f"Unsupported LLM provider: {config['provider']}")

    model = config["model"]
    if model and model not in ids:
        result = f"API reachable and key accepted; configured model not listed: {model}"
    else:
        result = f"API reachable and key accepted; models visible: {len(ids)}"
    _report(report, "api_test_completed", provider=config["provider"], model=model, result=result)
    return {"provider": config["provider"], "model": model, "result": result}
