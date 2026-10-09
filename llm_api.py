"""Central YJ-64 LLM router.

Provider credentials and model settings live in one app-private router file.
Participants send a route marker and mode; provider-specific HTTP details stay here.
"""
from __future__ import annotations

import json
import ssl
import uuid
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

ROUTER_CONFIG_RELATIVE_PATH = Path("yj64-router-config.json")
LEGACY_CONFIG_RELATIVE_PATH = Path("yj64-llm-config.json")
LEGACY_BUNDLE_RELATIVE_PATH = Path("yj64-llm-keys.json")
LEGACY_PARTICIPANTS = (
    ("Owner", "route_owner"),
    ("Participant 1", "route_1"),
    ("Participant 2", "route_2"),
    ("Participant 3", "route_3"),
)
PROVIDER_DEFAULTS = {
    "openai": "https://api.openai.com/v1",
    "openai-responses": "https://api.openai.com/v1",
    "gemini": "https://generativelanguage.googleapis.com/v1beta",
    "google": "https://generativelanguage.googleapis.com/v1beta",
    "google-gemini": "https://generativelanguage.googleapis.com/v1beta",
    "groq": "https://api.groq.com/openai/v1",
    "openrouter": "https://openrouter.ai/api/v1",
}


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
            Request(url, headers=request_headers, method=method, data=body),
            timeout=timeout,
            context=context,
        ) as response:
            raw = response.read().decode("utf-8")
            parsed = json.loads(raw)
            if not isinstance(parsed, dict):
                raise RuntimeError("API returned JSON that is not an object")
            return parsed
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code}: {detail[:800]}") from exc
    except URLError as exc:
        raise RuntimeError(f"Network error: {exc.reason}") from exc
    except json.JSONDecodeError as exc:
        raise RuntimeError("API returned invalid JSON") from exc


def _route_id(route_id: str | None = None, participant_name: str = "Owner") -> str:
    if route_id:
        value = route_id.strip().lower()
        if value.startswith("route_"):
            return value
        raise ValueError(f"Invalid route marker: {route_id}")
    # Compatibility for existing callers while all chat dispatch moves to
    # message_distributor.py. Provider/API details are not inferred here.
    name = participant_name.strip().lower()
    legacy_map = {
        "owner": "route_owner",
        "participant 1": "route_1",
        "participant 2": "route_2",
        "participant 3": "route_3",
    }
    if name not in legacy_map:
        raise ValueError(f"No router route is registered for {participant_name}")
    return legacy_map[name]


def _read_json_dict(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return raw if isinstance(raw, dict) else {}


def _write_router_data(user_data_dir: str | Path, data: dict[str, Any]) -> None:
    path = Path(user_data_dir) / ROUTER_CONFIG_RELATIVE_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _load_router_data(user_data_dir: str | Path) -> dict[str, Any]:
    root = Path(user_data_dir)
    path = root / ROUTER_CONFIG_RELATIVE_PATH
    if path.is_file():
        data = _read_json_dict(path)
        routes = data.get("routes", {})
        return {"routes": routes if isinstance(routes, dict) else {}}

    # One-time migration from the old per-participant files into router cells.
    routes: dict[str, dict[str, str]] = {}
    migrated_paths: list[Path] = []
    for participant, route_id in LEGACY_PARTICIPANTS:
        legacy_path = (
            root / LEGACY_CONFIG_RELATIVE_PATH
            if participant == "Owner"
            else root / f"yj64-llm-config-{participant.lower().replace(' ', '-')}.json"
        )
        legacy = _read_json_dict(legacy_path)
        if legacy.get("api_key") and legacy.get("model"):
            routes[route_id] = {
                "provider": str(legacy.get("provider") or "openai"),
                "model": str(legacy.get("model") or ""),
                "api_key": str(legacy.get("api_key") or ""),
                "endpoint": str(legacy.get("endpoint") or ""),
            }
            migrated_paths.append(legacy_path)

    bundle_path = root / LEGACY_BUNDLE_RELATIVE_PATH
    bundle = _read_json_dict(bundle_path)
    providers = bundle.get("providers", {})
    if isinstance(providers, dict):
        next_index = 1
        for provider_name, raw in providers.items():
            if not isinstance(raw, dict) or not raw.get("api_key") or not raw.get("model"):
                continue
            while f"route_{next_index}" in routes:
                next_index += 1
            routes[f"route_{next_index}"] = {
                "provider": str(provider_name),
                "model": str(raw.get("model") or ""),
                "api_key": str(raw.get("api_key") or ""),
                "endpoint": str(raw.get("endpoint") or ""),
            }
            next_index += 1
        if routes:
            migrated_paths.append(bundle_path)

    data = {"routes": routes}
    if routes:
        _write_router_data(root, data)
        # Remove migrated duplicate credential files only after the central
        # router file has been written successfully.
        for legacy_path in migrated_paths:
            try:
                legacy_path.unlink(missing_ok=True)
            except OSError:
                pass
    return data


def list_routes(user_data_dir: str | Path) -> list[dict[str, str]]:
    routes = _load_router_data(user_data_dir).get("routes", {})
    if not isinstance(routes, dict):
        return []
    result: list[dict[str, str]] = []
    for route_id, raw in routes.items():
        if not isinstance(raw, dict):
            continue
        config = {str(k): str(v) for k, v in raw.items()}
        if config.get("api_key") and config.get("model"):
            result.append({
                "route_id": str(route_id),
                "provider": config.get("provider", ""),
                "model": config.get("model", ""),
                "endpoint": config.get("endpoint", ""),
            })
    return sorted(result, key=lambda item: item["route_id"])


def load_config(
    user_data_dir: str | Path,
    participant_name: str = "Owner",
    route_id: str | None = None,
) -> dict[str, str]:
    selected_route = _route_id(route_id, participant_name)
    routes = _load_router_data(user_data_dir).get("routes", {})
    raw = routes.get(selected_route, {}) if isinstance(routes, dict) else {}
    if not isinstance(raw, dict):
        raw = {}
    return {
        "route_id": selected_route,
        "provider": str(raw.get("provider") or ""),
        "model": str(raw.get("model") or ""),
        "api_key": str(raw.get("api_key") or ""),
        "endpoint": str(raw.get("endpoint") or ""),
    }


def route_config_exists(
    user_data_dir: str | Path,
    route_id: str,
) -> bool:
    config = load_config(user_data_dir, route_id=route_id)
    return bool(config.get("api_key") and config.get("model") and config.get("provider"))


def participant_config_exists(
    user_data_dir: str | Path,
    participant_name: str,
) -> bool:
    return route_config_exists(user_data_dir, _route_id(participant_name=participant_name))


def save_config(
    user_data_dir: str | Path,
    config: dict[str, str],
    participant_name: str = "Owner",
    route_id: str | None = None,
) -> None:
    selected_route = _route_id(route_id, participant_name)
    data = _load_router_data(user_data_dir)
    routes = data.setdefault("routes", {})
    routes[selected_route] = {
        "provider": str(config.get("provider") or "").strip().lower(),
        "model": str(config.get("model") or "").strip(),
        "api_key": str(config.get("api_key") or "").strip(),
        "endpoint": str(config.get("endpoint") or "").strip(),
    }
    _write_router_data(user_data_dir, data)


def _report(report: Any, event: str, **data: Any) -> None:
    if report is not None:
        report(event, **data)


def fetch_models(
    provider: str,
    api_key: str,
    endpoint: str = "",
) -> list[str]:
    provider_id = provider.strip().lower()
    key = api_key.strip()
    if not key:
        raise RuntimeError("LLM API key is not configured")
    base = (endpoint or PROVIDER_DEFAULTS.get(provider_id, "")).rstrip("/")
    if not base:
        raise RuntimeError("Custom provider requires an API endpoint")
    if provider_id in {"gemini", "google", "google-gemini"}:
        data = _request("GET", base + "/models", {"x-goog-api-key": key})
        models = data.get("models", [])
        result = []
        for item in models if isinstance(models, list) else []:
            if isinstance(item, dict) and item.get("name"):
                name = str(item["name"])
                result.append(name[7:] if name.startswith("models/") else name)
        return sorted(set(result), key=str.casefold)

    for suffix in ("/chat/completions", "/responses", "/models"):
        if base.endswith(suffix):
            base = base[:-len(suffix)]
            break
    headers = {"Authorization": f"Bearer {key}"}
    if provider_id == "openrouter":
        headers.update({
            "HTTP-Referer": "https://github.com/concreteballs/yj64-base",
            "X-Title": "YJ-64",
        })
    data = _request("GET", base + "/models", headers)
    models = data.get("data", [])
    ids = [
        str(item["id"])
        for item in models if isinstance(models, list)
        if isinstance(item, dict) and item.get("id")
    ]
    return sorted(set(ids), key=str.casefold)


def _gemini_contents(
    prompt: str,
    history: list[dict[str, str]] | None,
) -> list[dict[str, Any]]:
    contents: list[dict[str, Any]] = []
    for item in history or []:
        role = str(item.get("role") or "user").strip().lower()
        content = str(item.get("content") or "")
        if not content:
            continue
        contents.append({
            "role": "model" if role in {"assistant", "model"} else "user",
            "parts": [{"text": content}],
        })
    if not contents or str((history or [{}])[-1].get("content") or "") != prompt:
        contents.append({"role": "user", "parts": [{"text": prompt}]})
    return contents


def _extract_gemini_text(data: dict[str, Any]) -> str:
    candidates = data.get("candidates", [])
    if not isinstance(candidates, list):
        return ""
    texts: list[str] = []
    for candidate in candidates[:1]:
        if not isinstance(candidate, dict):
            continue
        content = candidate.get("content", {})
        parts = content.get("parts", []) if isinstance(content, dict) else []
        if isinstance(parts, list):
            for part in parts:
                if isinstance(part, dict) and part.get("text") is not None:
                    texts.append(str(part["text"]))
    return "".join(texts).strip()


def _extract_openai_text(data: dict[str, Any]) -> str:
    output_text = data.get("output_text")
    if isinstance(output_text, str) and output_text.strip():
        return output_text.strip()
    output = data.get("output", [])
    texts: list[str] = []
    if isinstance(output, list):
        for item in output:
            if not isinstance(item, dict):
                continue
            content = item.get("content", [])
            if isinstance(content, list):
                for part in content:
                    if isinstance(part, dict) and part.get("text") is not None:
                        texts.append(str(part["text"]))
    if texts:
        return "".join(texts).strip()
    choices = data.get("choices", [])
    if isinstance(choices, list) and choices and isinstance(choices[0], dict):
        message = choices[0].get("message", {})
        if isinstance(message, dict):
            return str(message.get("content") or "").strip()
    return ""


def generate_response(
    user_data_dir: str | Path,
    prompt: str,
    report: Any = None,
    participant_name: str = "Owner",
    history: list[dict[str, str]] | None = None,
    route_id: str | None = None,
    mode: str = "text",
    operation_id: str | None = None,
) -> dict[str, Any]:
    """Single gateway entry point; mode and route are markers, not API details."""
    operation = operation_id or uuid.uuid4().hex
    selected_route = _route_id(route_id, participant_name)
    selected_mode = str(mode or "text").strip().lower()
    _report(
        report, "gateway_request_received",
        operation_id=operation, route_id=selected_route, mode=selected_mode,
        prompt=prompt,
    )
    if selected_mode != "text":
        _report(
            report, "gateway_mode_rejected",
            operation_id=operation, route_id=selected_route, mode=selected_mode,
            reason="Only text mode is implemented in this build",
        )
        raise RuntimeError(f"Request mode '{selected_mode}' is not implemented yet")

    config = load_config(user_data_dir, route_id=selected_route)
    provider = config["provider"].strip().lower()
    model = config["model"].strip()
    key = config["api_key"].strip()
    if not provider or not key or not model:
        _report(
            report, "gateway_config_missing",
            operation_id=operation, route_id=selected_route,
            provider=provider, model=model,
            configured=bool(provider and key and model),
        )
        raise RuntimeError(f"Router cell {selected_route} is not fully configured")
    _report(
        report, "gateway_config_loaded",
        operation_id=operation, route_id=selected_route,
        provider=provider, model=model, configured=True,
    )

    if provider in {"gemini", "google", "google-gemini"}:
        base = (config["endpoint"] or PROVIDER_DEFAULTS["gemini"]).rstrip("/")
        url = f"{base}/models/{model}:generateContent"
        payload = {"contents": _gemini_contents(prompt, history)}
        headers = {"x-goog-api-key": key}
        api_method = "generateContent"
    elif provider in {"openai", "openai-responses"}:
        endpoint = (config["endpoint"] or "https://api.openai.com/v1/responses").rstrip("/")
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
        headers = {"Authorization": f"Bearer {key}"}
        api_method = "responses" if url.endswith("/responses") else "chat_completions"
    else:
        base = (config["endpoint"] or PROVIDER_DEFAULTS.get(provider, "")).rstrip("/")
        if not base:
            raise RuntimeError(f"Router cell {selected_route} requires an API endpoint")
        url = base if base.endswith("/chat/completions") else base + "/chat/completions"
        payload = {
            "model": model,
            "messages": history or [{"role": "user", "content": prompt}],
        }
        headers = {"Authorization": f"Bearer {key}"}
        if provider == "openrouter":
            headers.update({
                "HTTP-Referer": "https://github.com/concreteballs/yj64-base",
                "X-Title": "YJ-64",
            })
        api_method = "chat_completions"

    _report(
        report, "gateway_request_prepared",
        operation_id=operation, route_id=selected_route,
        provider=provider, model=model, api_method=api_method,
        http_method="POST", endpoint=url, prompt=prompt,
        history_count=len(history or []),
    )
    _report(
        report, "gateway_request_sending",
        operation_id=operation, route_id=selected_route,
        provider=provider, model=model, api_method=api_method,
    )
    data = _request("POST", url, headers, payload=payload)
    _report(
        report, "gateway_http_response_received",
        operation_id=operation, route_id=selected_route,
        provider=provider, model=model, api_method=api_method,
    )

    response_text = (
        _extract_gemini_text(data)
        if provider in {"gemini", "google", "google-gemini"}
        else _extract_openai_text(data)
    )
    if not response_text:
        _report(
            report, "gateway_response_text_missing",
            operation_id=operation, route_id=selected_route,
            provider=provider, model=model,
            response_shape=list(data.keys()),
        )
        raise RuntimeError(
            f"{provider} returned an HTTP response without extractable text: "
            f"{json.dumps(data, ensure_ascii=False)[:1000]}"
        )
    _report(
        report, "gateway_response_ready",
        operation_id=operation, route_id=selected_route,
        provider=provider, model=model,
        response_length=len(response_text),
    )
    return {
        "route_id": selected_route,
        "provider": config["provider"],
        "model": model,
        "prompt": prompt,
        "response": response_text,
        "operation_id": operation,
    }


def generate_test_response(
    user_data_dir: str | Path,
    report: Any = None,
    route_id: str = "route_owner",
) -> dict[str, Any]:
    prompt = "Reply with exactly: YJ64_OK"
    return generate_response(
        user_data_dir, prompt, report=report, route_id=route_id, mode="text"
    )


def test_llm_api(
    user_data_dir: str | Path,
    report: Any = None,
    participant_name: str = "Owner",
    route_id: str | None = None,
) -> dict[str, Any]:
    selected_route = _route_id(route_id, participant_name)
    config = load_config(user_data_dir, route_id=selected_route)
    provider = config["provider"].strip().lower()
    key = config["api_key"].strip()
    model = config["model"].strip()
    _report(
        report, "router_connection_test_started",
        route_id=selected_route, provider=provider, model=model,
        key_configured=bool(key),
    )
    if not key or not model or not provider:
        raise RuntimeError(f"Router cell {selected_route} is not fully configured")
    endpoint = config["endpoint"] or PROVIDER_DEFAULTS.get(provider, "")
    models = fetch_models(provider, key, endpoint)
    listed = model in models
    _report(
        report, "router_connection_test_completed",
        route_id=selected_route, provider=provider, model=model,
        model_list_count=len(models), configured_model_listed=listed,
        available_models=models,
    )
    result = (
        "API reachable; configured model is listed"
        if listed else
        f"API reachable; configured model not listed among {len(models)} models"
    )
    return {
        "route_id": selected_route, "provider": config["provider"],
        "model": model, "result": result, "models": models,
    }


def test_all_routes(
    user_data_dir: str | Path,
    report: Any = None,
) -> dict[str, Any]:
    prompt = "Reply with exactly: YJ64_OK"
    routes = list_routes(user_data_dir)
    if not routes:
        raise RuntimeError("No saved router cells are configured")
    results: list[dict[str, str]] = []
    report_lines = ["YJ-64 CENTRAL ROUTER — TEST ALL SAVED CONNECTIONS"]
    for item in routes:
        route_id = item["route_id"]
        provider = item["provider"]
        model = item["model"]
        _report(
            report, "router_all_test_route_started",
            route_id=route_id, provider=provider, model=model,
            prompt=prompt,
        )
        try:
            result = generate_response(
                user_data_dir, prompt, report=report,
                route_id=route_id, mode="text",
            )
            status = "PASS"
            detail = result["response"]
        except Exception as exc:
            status = "FAIL"
            detail = f"{type(exc).__name__}: {exc}"
            _report(
                report, "router_all_test_route_failed",
                route_id=route_id, provider=provider, model=model,
                error_type=type(exc).__name__, error=str(exc),
            )
        else:
            _report(
                report, "router_all_test_route_completed",
                route_id=route_id, provider=provider, model=model,
                response=result["response"],
            )
        results.append({
            "route_id": route_id, "provider": provider, "model": model,
            "status": status, "detail": detail,
        })
        report_lines.extend([
            "", f"[{status}] {route_id} — {provider} / {model}",
            f"Result: {detail}",
        ])
    passed = sum(1 for item in results if item["status"] == "PASS")
    report_lines.extend(["", f"Summary: {passed}/{len(results)} connections passed"])
    return {"results": results, "report": "\n".join(report_lines)}
