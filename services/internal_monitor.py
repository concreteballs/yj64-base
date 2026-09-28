"""Embedded internal diagnostic agent for the YJ-64 base application."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import socket
import sys
import threading
import time
from datetime import datetime, timezone
import uuid
from pathlib import Path
from typing import Any
from urllib import request

from jnius import autoclass


SCHEMA = "yj64.diagnostic.v1"
SERVICE_LAUNCH_FLAG = "yj64.internal_agent_launch"
BASE_COMMAND_HOST = "127.0.0.1"
BASE_COMMAND_PORT = int(os.environ.get("YJ64_BASE_COMMAND_PORT", "9334"))
CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "bridge.json"


def load_config() -> dict[str, Any]:
    return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))


def write_status(service: Any, payload: dict[str, Any]) -> None:
    """Persist current status and append an immutable status-history record."""
    files_dir = Path(str(service.getFilesDir()))
    path = files_dir / "diagnostic-agent-status.json"
    history_path = files_dir / "diagnostic-agent-status.jsonl"
    record = {
        "recorded_at_wall_time": datetime.now(timezone.utc).isoformat(timespec="microseconds"),
        "recorded_monotonic_ns": time.monotonic_ns(),
        **payload,
    }
    try:
        with history_path.open("a", encoding="utf-8") as handle:
            handle.write(
                json.dumps(record, sort_keys=True, ensure_ascii=False) + "\n"
            )
    except OSError:
        pass
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False),
        encoding="utf-8",
    )


def spool_path(service: Any, filename: str) -> Path:
    return Path(str(service.getFilesDir())) / filename


_report_sequence = 0


def _new_message_metadata(prefix: str) -> dict[str, Any]:
    global _report_sequence
    _report_sequence += 1
    return {
        "message_id": f"{prefix}-{uuid.uuid4().hex}",
        "sequence": _report_sequence,
        "wall_time": datetime.now(timezone.utc).isoformat(timespec="microseconds"),
        "monotonic_ns": time.monotonic_ns(),
    }


def _sign_report(report: dict[str, Any], token: str) -> str:
    unsigned = {key: value for key, value in report.items() if key not in {"signature", "signature_algorithm"}}
    canonical = json.dumps(unsigned, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return hmac.new(token.encode("utf-8"), canonical, hashlib.sha256).hexdigest()


def make_report(agent_id: str, event: str, token: str, **data: Any) -> dict[str, Any]:
    metadata = _new_message_metadata("INT")
    report = {
        "schema": SCHEMA,
        "agent": agent_id,
        "event": event,
        "timestamp_ms": int(time.time() * 1000),
        **metadata,
        "report_id": metadata["message_id"],
        "data": data,
    }
    report["signature_algorithm"] = "HMAC-SHA256"
    report["signature"] = _sign_report(report, token)
    return report


def append_spool(service: Any, path: Path, report: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(report, sort_keys=True) + "\n")


def send_bridge(
    host: str,
    port: int,
    token: str,
    timeout: float,
    report: dict[str, Any],
) -> dict[str, Any] | None:
    envelope = {
        "token": token,
        "report": report,
        "sent_at_wall_time": datetime.now(timezone.utc).isoformat(timespec="microseconds"),
        "sent_monotonic_ns": time.monotonic_ns(),
    }
    payload = (json.dumps(envelope, sort_keys=True) + "\n").encode("utf-8")
    try:
        with socket.create_connection((host, port), timeout=timeout) as connection:
            connection.sendall(payload)
            connection.settimeout(timeout)
            response = connection.recv(8192).decode("utf-8", errors="replace").strip()
            response_received_wall_time = datetime.now(timezone.utc).isoformat(timespec="microseconds")
            response_received_monotonic_ns = time.monotonic_ns()
            if not response:
                return None
            ack = json.loads(response)
            if not isinstance(ack, dict):
                return None
            ack["client_received_wall_time"] = response_received_wall_time
            ack["client_received_monotonic_ns"] = response_received_monotonic_ns
            if ack.get("ok") is not True:
                return ack
            if ack.get("report_id") != report["report_id"]:
                return None
            return ack
    except (OSError, ValueError, TypeError):
        return None

def send_with_retry(
    config: dict[str, Any], report: dict[str, Any]
) -> dict[str, Any] | None:
    bridge = config["bridge"]
    attempts = int(bridge["retry_count"])
    delay = float(bridge["retry_delay_seconds"])
    for attempt in range(max(1, attempts)):
        ack = send_bridge(
            str(bridge["host"]),
            int(bridge["port"]),
            str(bridge["token"]),
            float(bridge["connect_timeout_seconds"]),
            report,
        )
        if ack is not None and ack.get("ok") is True:
            return ack
        if attempt + 1 < attempts:
            time.sleep(delay)
    return None

def upload_https(
    endpoint: str,
    report: dict[str, Any],
    timeout: float = 5.0,
) -> bool:
    """Upload a report when a real HTTPS endpoint is configured."""

    if not endpoint:
        return False

    try:
        body = json.dumps(report).encode("utf-8")
        req = request.Request(
            endpoint,
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with request.urlopen(req, timeout=timeout) as response:
            return 200 <= int(response.status) < 300
    except (OSError, ValueError, TypeError):
        return False


def self_diagnostic(config: dict[str, Any], service: Any) -> dict[str, Any]:
    """Run deterministic startup checks before handing control to the base app."""

    checks: dict[str, Any] = {}

    try:
        config["agent_id"]
        config["target_package"]
        config["bridge"]["host"]
        config["bridge"]["port"]
        checks["configuration"] = "ok"
    except (KeyError, TypeError):
        checks["configuration"] = "invalid"

    try:
        probe = Path(str(service.getFilesDir())) / ".diagnostic_write_test"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink(missing_ok=True)
        checks["storage"] = "ok"
    except OSError:
        checks["storage"] = "unavailable"

    try:
        package_manager = service.getPackageManager()
        visible = (
            package_manager.getLaunchIntentForPackage(
                str(config["target_package"])
            )
            is not None
        )
        checks["target_visibility"] = (
            "visible" if visible else "not_visible"
        )
    except Exception as exc:
        checks["target_visibility"] = f"probe_error:{type(exc).__name__}"

    checks["process"] = "ok"
    return checks


def launch_target(package_name: str) -> tuple[bool, str]:
    """Hand control to the base application's main activity."""

    try:
        context = autoclass("org.kivy.android.PythonService").mService
        package_manager = context.getPackageManager()
        intent = package_manager.getLaunchIntentForPackage(package_name)

        if intent is None:
            return False, "target_package_not_installed"

        Intent = autoclass("android.content.Intent")
        intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
        intent.putExtra(SERVICE_LAUNCH_FLAG, True)
        context.startActivity(intent)
        return True, "launched"
    except Exception as exc:
        return False, f"launch_error:{type(exc).__name__}"


def send_report_or_spool(
    config: dict[str, Any],
    service: Any,
    spool: Path,
    report: dict[str, Any],
) -> dict[str, Any] | None:
    """Prefer the external bridge and persist the report when it is unavailable."""

    bridge_ack = send_with_retry(config, report)
    if bridge_ack is None:
        append_spool(service, spool, report)

    endpoint = str(config["report"].get("https_endpoint", ""))
    if endpoint:
        upload_https(endpoint, report)

    return bridge_ack


def inspect_activity_process(service: Any, package_name: str) -> dict[str, Any]:
    """Observe the target app's own processes from its embedded service."""
    activity_manager = service.getSystemService("activity")
    package_manager = service.getPackageManager()
    application_info = package_manager.getApplicationInfo(package_name, 0)
    target_uid = int(application_info.uid)

    matching: list[dict[str, Any]] = []
    for process in activity_manager.getRunningAppProcesses() or []:
        if int(process.uid) != target_uid:
            continue
        matching.append(
            {
                "pid": int(process.pid),
                "process_name": str(process.processName),
                "importance": int(process.importance),
            }
        )

    activity_process = [
        item for item in matching
        if item["process_name"] == package_name
    ]
    return {
        "target_uid": target_uid,
        "processes": matching,
        "activity_process_visible": bool(activity_process),
    }




def verify_fault_report_signature(
    report: dict[str, Any], token: str
) -> bool:
    """Verify the persisted crash report before forwarding it unchanged."""
    signature = report.get("signature")
    algorithm = report.get("signature_algorithm")
    if not isinstance(signature, str) or algorithm != "HMAC-SHA256":
        return False
    expected = _sign_report(report, token)
    return hmac.compare_digest(signature, expected)


def recover_previous_fault_report(
    config: dict[str, Any],
    service: Any,
    spool: Path,
    agent_id: str,
) -> dict[str, Any] | None:
    """Forward the original signed crash object unchanged on next launch."""
    fault_path = Path(str(service.getFilesDir())) / "fault-injection-report.json"
    if not fault_path.exists():
        return None
    try:
        fault_report = json.loads(fault_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(fault_report, dict) or not fault_report.get("test_id"):
        return None

    token = str(config["bridge"]["token"])
    if not verify_fault_report_signature(fault_report, token):
        write_status(
            service,
            {
                "agent": agent_id,
                "event": "fault_report_signature_invalid",
                "bridge_status": "not_sent",
                "report_id": fault_report.get("report_id"),
                "test_id": fault_report.get("test_id"),
            },
        )
        return None

    marker_path = Path(str(service.getFilesDir())) / "fault-report-forwarded.json"
    try:
        marker = json.loads(marker_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        marker = {}
    if marker.get("test_id") == fault_report["test_id"]:
        return None

    write_status(
        service,
        {
            "agent": agent_id,
            "event": "fault_report_recovery_pending",
            "bridge_status": "pending",
            "report_id": fault_report.get("report_id"),
            "test_id": fault_report.get("test_id"),
        },
    )
    return fault_report


def forward_recovered_fault_report(
    config: dict[str, Any],
    service: Any,
    spool: Path,
    agent_id: str,
    fault_report: dict[str, Any],
) -> bool:
    """Retry the exact persisted signed crash object until the bridge ACKs it."""
    marker_path = Path(str(service.getFilesDir())) / "fault-report-forwarded.json"
    test_id = fault_report.get("test_id")
    if not isinstance(test_id, str) or not test_id:
        return False

    try:
        marker = json.loads(marker_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        marker = {}
    if marker.get("test_id") == test_id:
        return True

    ack = send_with_retry(config, fault_report)
    if ack is None:
        write_status(
            service,
            {
                "agent": agent_id,
                "event": "fault_report_recovery_pending",
                "bridge_status": "unavailable",
                "report_id": fault_report.get("report_id"),
                "test_id": test_id,
            },
        )
        return False

    try:
        marker_path.write_text(
            json.dumps(
                {
                    "test_id": test_id,
                    "report_id": fault_report.get("report_id"),
                    "signature": fault_report.get("signature"),
                    "forwarded_at": datetime.now(
                        timezone.utc
                    ).isoformat(timespec="microseconds"),
                },
                sort_keys=True,
            ),
            encoding="utf-8",
        )
    except OSError:
        return False

    write_status(
        service,
        {
            "agent": agent_id,
            "event": "fault_report_recovered_and_forwarded",
            "bridge_status": "connected",
            "report_id": fault_report.get("report_id"),
            "test_id": test_id,
            "ack_message_id": ack.get("ack_message_id"),
            "ack_wall_time": ack.get("ack_wall_time"),
            "client_received_wall_time": ack.get("client_received_wall_time"),
        },
    )
    return True


def execute_bridge_command(
    config: dict[str, Any],
    service: Any,
    spool: Path,
    command: dict[str, Any],
) -> None:
    """Execute a one-shot command delivered by the external monitor."""
    command_id = str(command.get("message_id", ""))
    command_type = str(command.get("command", ""))
    received_at = datetime.now(timezone.utc).isoformat(timespec="microseconds")
    received_monotonic = time.monotonic_ns()

    if command_type != "RUN_DIAGNOSTIC_TEST":
        report = make_report(
            str(config["agent_id"]),
            "bridge_command_rejected",
            str(config["bridge"]["token"]),
            command=command_type,
            command_id=command_id,
            reason="unsupported_command",
            received_at_wall_time=received_at,
            received_monotonic_ns=received_monotonic,
        )
        send_report_or_spool(config, service, spool, report)
        return

    result = {
        "command": command_type,
        "command_id": command_id,
        "accepted": True,
        "received_at_wall_time": received_at,
        "received_monotonic_ns": received_monotonic,
        "bridge_ack_wall_time": command.get("ack_wall_time"),
        "bridge_ack_monotonic_ns": command.get("ack_monotonic_ns"),
        "client_received_wall_time": command.get("client_received_wall_time"),
        "client_received_monotonic_ns": command.get("client_received_monotonic_ns"),
        "test": "external_to_internal_bridge",
        "message": "External monitor command received by internal diagnostic monitor.",
    }
    report = make_report(
        str(config["agent_id"]),
        "diagnostic_test_result",
        str(config["bridge"]["token"]),
        **result,
    )
    write_status(
        service,
        {
            "agent": str(config["agent_id"]),
            "event": "diagnostic_test_result",
            "bridge_status": "connected",
            "target_launch": "launched",
            "target_success": True,
            "last_command": command,
            "last_report": report,
            "diagnostic_test": result,
        },
    )
    send_report_or_spool(config, service, spool, report)


def run() -> None:
    PythonService = autoclass("org.kivy.android.PythonService")
    service = PythonService.mService
    service.setAutoRestartService(True)

    config = load_config()
    agent_id = str(config["agent_id"])
    spool = spool_path(service, str(config["report"]["spool_filename"]))

    recovered_fault_report = recover_previous_fault_report(
        config, service, spool, agent_id
    )

    if recovered_fault_report is not None:
        restart_report = make_report(
            agent_id,
            "target_planned_crash_recovered",
            str(config["bridge"]["token"]),
            recovered_fault_report_id=recovered_fault_report.get("report_id"),
            recovered_test_id=recovered_fault_report.get("test_id"),
            recovered_fault_timestamp_ms=recovered_fault_report.get("timestamp_ms"),
            restart_pid=os.getpid(),
            message=(
                "Base application restarted after a planned crash; "
                "the persisted signed crash report was recovered."
            ),
        )
        restart_ack = send_report_or_spool(
            config,
            service,
            spool,
            restart_report,
        )
        write_status(
            service,
            {
                "agent": agent_id,
                "event": "fault_report_restart_recovery",
                "bridge_status": (
                    "connected" if restart_ack is not None else "spooled"
                ),
                "restart_report_id": restart_report.get("report_id"),
                "recovered_fault_report_id": recovered_fault_report.get("report_id"),
                "recovered_test_id": recovered_fault_report.get("test_id"),
            },
        )

    checks = self_diagnostic(config, service)
    self_report = make_report(
        agent_id,
        "self_diagnostic",
        str(config["bridge"]["token"]),
        checks=checks,
        target_package=config["target_package"],
    )
    self_bridge_ok = send_report_or_spool(
        config,
        service,
        spool,
        self_report,
    )

    startup = make_report(
        agent_id,
        "internal_startup",
        str(config["bridge"]["token"]),
        pid=os.getpid(),
        python_version=sys.version.split()[0],
        target_package=config["target_package"],
        cwd=os.getcwd(),
    )
    startup_bridge_ok = send_report_or_spool(
        config,
        service,
        spool,
        startup,
    )

    launch_ok, launch_reason = launch_target(str(config["target_package"]))
    launch_report = make_report(
        agent_id,
        "target_launch_result",
        str(config["bridge"]["token"]),
        target_package=config["target_package"],
        success=launch_ok,
        reason=launch_reason,
        bridge_received_self_diagnostic=bool(self_bridge_ok),
        bridge_received_startup=bool(startup_bridge_ok),
    )
    launch_ack = send_report_or_spool(
        config,
        service,
        spool,
        launch_report,
    )

    write_status(
        service,
        {
            "agent": agent_id,
            "event": "target_launch_result",
            "bridge_status": (
                "connected"
                if self_bridge_ok or startup_bridge_ok or launch_ack
                else "spooled"
            ),
            "self_diagnostic": (
                "ok"
                if all(value in {"ok", "visible"} for value in checks.values())
                else json.dumps(checks, sort_keys=True)
            ),
            "target_launch": launch_reason,
            "target_success": launch_ok,
            "launch_report_sent": bool(launch_ack),
        },
    )

    if launch_ack and isinstance(launch_ack.get("command"), dict):
        execute_bridge_command(config, service, spool, launch_ack["command"])

    last_activity_process_visible: bool | None = None
    recovery_attempts = 0

    while True:
        try:
            if recovered_fault_report is not None:
                recovery_attempts += 1
                if forward_recovered_fault_report(
                    config,
                    service,
                    spool,
                    agent_id,
                    recovered_fault_report,
                ):
                    recovered_fault_report = None
                    recovery_attempts = 0
                elif recovery_attempts >= 20:
                    write_status(
                        service,
                        {
                            "agent": agent_id,
                            "event": "fault_report_recovery_still_pending",
                            "bridge_status": "unavailable",
                            "report_id": recovered_fault_report.get("report_id"),
                            "test_id": recovered_fault_report.get("test_id"),
                            "attempts": recovery_attempts,
                        },
                    )
                    recovery_attempts = 0

            process_state = inspect_activity_process(
                service,
                str(config["target_package"]),
            )
            visible = bool(process_state["activity_process_visible"])
            if visible != last_activity_process_visible:
                process_report = make_report(
                    agent_id,
                    "target_activity_process_state",
                    str(config["bridge"]["token"]),
                    target_package=config["target_package"],
                    **process_state,
                )
                send_report_or_spool(
                    config,
                    service,
                    spool,
                    process_report,
                )
                last_activity_process_visible = visible
        except Exception as exc:
            error_report = make_report(
                agent_id,
                "target_activity_process_observation_error",
                str(config["bridge"]["token"]),
                target_package=config["target_package"],
                error_type=type(exc).__name__,
                error=str(exc),
            )
            send_report_or_spool(
                config,
                service,
                spool,
                error_report,
            )

        time.sleep(1)


run()
