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

    def select_participant(
        self,
        user_data_dir: str | Path,
        preferred: str | None = None,
        report: Callable[..., None] | None = None,
    ) -> str:
        """Select a configured route once; never retry another participant after API failure."""
        from llm_api import route_config_exists

        participant_order = ("Participant 1", "Participant 2", "Participant 3")
        connected = [
            name for name in participant_order
            if route_config_exists(user_data_dir, self.route_for_participant(name))
        ]
        owner_connected = route_config_exists(
            user_data_dir, self.route_for_participant("Owner")
        )

        if preferred is not None:
            if preferred not in PARTICIPANT_ROUTES:
                raise ValueError(f"Unknown preferred participant: {preferred}")
            if route_config_exists(
                user_data_dir, self.route_for_participant(preferred)
            ):
                selected = preferred
                reason = "preferred_participant_connected"
            else:
                selected = next(iter(connected), "Owner" if owner_connected else "")
                reason = "preferred_participant_not_connected_fallback"
        else:
            selected = next(iter(connected), "Owner" if owner_connected else "")
            reason = "first_connected_participant"

        if not selected:
            if report is not None:
                report(
                    "participant_selection_failed",
                    preferred=preferred,
                    connected_participants=connected,
                    owner_connected=owner_connected,
                )
            raise RuntimeError(
                "No connected LLM routes are configured for Owner or Participants 1–3"
            )

        route_id = self.route_for_participant(selected)
        if report is not None:
            report(
                "participant_selected",
                participant=selected,
                route_id=route_id,
                preferred=preferred,
                connected_participants=connected,
                owner_connected=owner_connected,
                reason=reason,
            )
        return selected

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
        selected_mode = self.mode
        if report is not None:
            report(
                "distributor_request_marked",
                operation_id=operation_id,
                participant=participant_name,
                route_id=route_id,
                mode=selected_mode,
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
            mode=selected_mode,
            history=history,
            operation_id=operation_id,
        )
        if report is not None:
            report(
                "distributor_response_returned",
                operation_id=operation_id,
                participant=participant_name,
                route_id=route_id,
                mode=selected_mode,
                response_length=len(result.get("response", "")),
            )
        return result
