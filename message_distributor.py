"""Message distribution layer for YJ-64.

This module knows participant order and route markers only. It does not know
provider names, API endpoints, credentials, or provider-specific request formats.
"""
from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any, Callable

PARTICIPANT_ROUTES = {
    "Owner": "route_owner",
    "Participant 1": "route_1",
    "Participant 2": "route_2",
    "Participant 3": "route_3",
}


class MessageDistributor:
    """Tracks dialogue order, current mode marker, and optional private target."""

    def __init__(self) -> None:
        self.mode = "text"
        self._next_index = 0
        self._private_participant: str | None = None

    def route_for_participant(self, participant_name: str) -> str:
        try:
            return PARTICIPANT_ROUTES[participant_name]
        except KeyError as exc:
            raise ValueError(
                f"No route marker is assigned to participant {participant_name!r}"
            ) from exc

    def set_mode(self, mode: str) -> str:
        selected = str(mode or "text").strip().lower()
        if selected not in {"text", "agent"}:
            raise ValueError(f"Unknown message mode marker: {mode}")
        self.mode = selected
        return self.mode

    def toggle_mode(self) -> str:
        self.mode = "agent" if self.mode == "text" else "text"
        return self.mode

    def set_private_participant(self, participant_name: str | None) -> None:
        self._private_participant = participant_name

    @property
    def active_participant(self) -> str | None:
        return self._private_participant

    def next_participant(self, participants: list[str]) -> str:
        if not participants:
            raise ValueError("Cannot select the next participant from an empty queue")
        participant = participants[self._next_index % len(participants)]
        self._next_index = (self._next_index + 1) % len(participants)
        return participant

    def reset_queue(self) -> None:
        self._next_index = 0

    def dispatch_message(
        self,
        user_data_dir: str | Path,
        participant_name: str,
        message: str,
        report: Callable[..., None] | None = None,
        history: list[dict[str, str]] | None = None,
    ) -> dict[str, Any]:
        route_id = self.route_for_participant(participant_name)
        operation_id = uuid.uuid4().hex
        if report is not None:
            report(
                "distributor_request_marked",
                operation_id=operation_id,
                participant=participant_name,
                route_id=route_id,
                mode=self.mode,
                history_count=len(history or []),
            )
        # Provider-specific routing, credentials, HTTP, and response text
        # extraction all remain inside the central llm_api router.
        from llm_api import generate_response

        result = generate_response(
            user_data_dir,
            message,
            report=report,
            route_id=route_id,
            mode=self.mode,
            history=history,
            operation_id=operation_id,
        )
        if report is not None:
            report(
                "distributor_response_returned",
                operation_id=operation_id,
                participant=participant_name,
                route_id=route_id,
                mode=self.mode,
                response_length=len(result.get("response", "")),
            )
        return result
