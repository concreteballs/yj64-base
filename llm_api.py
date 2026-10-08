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
    """Run the fixed Gemini generation smoke test through the current provider path."""
    prompt = "Reply with exactly: YJ64_OK"
    _report(report, "generation_config_loaded")
    result = generate_response(
        user_data_dir,
        prompt,
        report=report,
        participant_name="Owner",
    )
    return result


def _extract_interaction_text(data: dict[str, Any]) -> str:
    """Extract model text from a Gemini Interactions API response."""
    output_text = data.get("output_text")
    if isinstance(output_text, str) and output_text.strip():
        return output_text.strip()

    steps = data.get("steps", [])
    texts: list[str] = []
    if isinstance(steps, list):
        for step in steps:
            if not isinstance(step, dict):
                continue
            step_content = step.get("content", [])
            if not isinstance(step_content, list):
                continue
            for part in step_content:
                if isinstance(part, dict) and part.get("type") == "text":
                    text = part.get("text")
                    if text is not None:
                        texts.append(str(text))
    return "".join(texts).strip()


def _generate_gemini_interaction(
    config: dict[str, str],
    prompt: str,
    model: str,
    key: str,
    report: Any = None,
    history: list[dict[str, str]] | None = None,
) -> str:
    endpoint = (
        config["endpoint"]
        or "https://generativelanguage.googleapis.com/v1beta"
    ).rstrip("/")
    url = endpoint + "/interactions"

    input_text = prompt
    if history:
        transcript = []
        for item in history:
            role = str(item.get("role") or "user")
            transcript.append(f"{role}: {str(item.get('content') or '')}")
        transcript.append(f"user: {prompt}")
        input_text = "\n".join(transcript)

    _report(
        report,
        "generation_request_started",
        provider=config["provider"],
        model=model,
        endpoint=url,
        prompt=prompt,
        api="interactions",
    )
    data = _request(
        "POST",
        url,
        {"x-goog-api-key": key},
        payload={
            "model": model,
            "input": input_text,
        },
    )
    _report(
        report,
        "generation_response_received",
        provider=config["provider"],
        api="interactions",
    )
    response_text = _extract_interaction_text(data)
    if not response_text:
        raise RuntimeError(
            "Gemini Interactions API returned no text: "
            f"{json.dumps(data, ensure_ascii=False)[:1200]}"
        )
    return response_text


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

    if provider in {"groq", "openrouter"} or provider not in {
        "gemini", "google", "google-gemini", "openai", "openai-responses"
    }:
        defaults = {
            "groq": "https://api.groq.com/openai/v1",
            "openrouter": "https://openrouter.ai/api/v1",
        }
        base = (config["endpoint"] or defaults.get(provider, "")).rstrip("/")
        if not base:
            raise RuntimeError(
                "Custom provider requires an API endpoint compatible with Chat Completions"
            )
        url = base if base.endswith("/chat/completions") else base + "/chat/completions"
        payload = {
            "model": model,
            "messages": history or [{"role": "user", "content": prompt}],
        }
        _report(
            report,
            "generation_request_started",
            provider=provider,
            model=model,
            endpoint=url,
            prompt=prompt,
        )
        headers = {"Authorization": f"Bearer {key}"}
        if provider == "openrouter":
            headers.update({
                "HTTP-Referer": "https://github.com/concreteballs/yj64-base",
                "X-Title": "YJ-64",
            })
        data = _request("POST", url, headers, payload=payload)
        _report(report, "generation_response_received", provider=provider)
        choices = data.get("choices", [])
        response_text = ""
        if isinstance(choices, list) and choices:
            message = choices[0].get("message", {})
            if isinstance(message, dict):
                response_text = str(message.get("content") or "").strip()
        if not response_text:
            raise RuntimeError(
                f"{provider} returned no text: {json.dumps(data, ensure_ascii=False)[:1200]}"
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

    response_text = _generate_gemini_interaction(
        config,
        prompt,
        model,
        key,
        report=report,
        history=history,
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


def fetch_models(
    provider: str,
    api_key: str,
    endpoint: str = "",
) -> list[str]:
    """Return model IDs visible to this API key without saving the key."""
    provider_id = provider.strip().lower()
    key = api_key.strip()
    if not key:
        raise RuntimeError("LLM API key is not configured")

    if provider_id in {"gemini", "google", "google-gemini"}:
        base = (endpoint or "https://generativelanguage.googleapis.com/v1beta").rstrip("/")
        data = _request("GET", base + "/models", {"x-goog-api-key": key})
        models = data.get("models", []) if isinstance(data, dict) else []
        result = []
        for item in models:
            if not isinstance(item, dict) or not item.get("name"):
                continue
            name = str(item["name"])
            result.append(name[7:] if name.startswith("models/") else name)
        return sorted(set(result), key=str.casefold)

    defaults = {
        "openai": "https://api.openai.com/v1",
        "openai-responses": "https://api.openai.com/v1",
        "groq": "https://api.groq.com/openai/v1",
        "openrouter": "https://openrouter.ai/api/v1",
    }
    base = (endpoint or defaults.get(provider_id, "")).rstrip("/")
    if not base:
        raise RuntimeError("Custom provider requires an API endpoint")
    for suffix in ("/chat/completions", "/responses"):
        if base.endswith(suffix):
            base = base[:-len(suffix)]
            break
    models_url = base + "/models"
    headers = {"Authorization": f"Bearer {key}"}
    if provider_id == "openrouter":
        headers.update({
            "HTTP-Referer": "https://github.com/concreteballs/yj64-base",
            "X-Title": "YJ-64",
        })
    data = _request("GET", models_url, headers)
    models = data.get("data", []) if isinstance(data, dict) else []
    ids = [
        str(item["id"])
        for item in models
        if isinstance(item, dict) and item.get("id")
    ]
    return sorted(set(ids), key=str.casefold)


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

    if provider in {"openai", "openai-responses", "gemini", "google", "google-gemini", "groq", "openrouter"}:
        defaults = {
            "openai": "https://api.openai.com/v1",
            "openai-responses": "https://api.openai.com/v1",
            "gemini": "https://generativelanguage.googleapis.com/v1beta",
            "google": "https://generativelanguage.googleapis.com/v1beta",
            "google-gemini": "https://generativelanguage.googleapis.com/v1beta",
            "groq": "https://api.groq.com/openai/v1",
            "openrouter": "https://openrouter.ai/api/v1",
        }
        endpoint = config["endpoint"] or defaults.get(provider, "")
        _report(report, "api_request_started", provider=provider, endpoint=endpoint)
        ids = fetch_models(provider, key, endpoint)
        _report(report, "api_request_succeeded", provider=provider)
    else:
        _report(report, "api_request_started", provider=provider, endpoint=config["endpoint"])
        ids = fetch_models(provider, key, config["endpoint"])
        _report(report, "api_request_succeeded", provider=provider)

    model = config["model"]
    if model and model not in ids:
        result = f"API reachable and key accepted; configured model not listed: {model}"
    else:
        result = f"API reachable and key accepted; models visible: {len(ids)}"
    _report(report, "api_test_completed", provider=config["provider"], model=model, result=result)
    return {"provider": config["provider"], "model": model, "result": result}
