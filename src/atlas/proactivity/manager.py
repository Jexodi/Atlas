from __future__ import annotations

import time
from typing import Any

from atlas.core.event_bus import EventBus

from .models import ProactiveSuggestion


class ProactivityManager:
    """Transforme des événements locaux en suggestions, sans exécuter d'action."""

    LEVELS = {"off", "low", "normal", "high", "jarvis"}

    def __init__(
        self,
        *,
        event_bus: EventBus,
        logger,
        level: str = "normal",
        cooldown_seconds: float = 120.0,
        clock=time.monotonic,
    ) -> None:
        normalized = str(level or "normal").strip().lower()
        self.level = normalized if normalized in self.LEVELS else "normal"
        self.events = event_bus
        self.logger = logger
        self.cooldown_seconds = max(0.0, float(cooldown_seconds))
        self._clock = clock
        self._last_emitted: dict[str, float] = {}

        self.events.subscribe("system.event", self._on_system_event)

    def close(self) -> None:
        self.events.unsubscribe("system.event", self._on_system_event)

    def _on_system_event(self, payload: Any) -> None:
        if self.level == "off" or not isinstance(payload, dict):
            return

        suggestion = self._build_suggestion(payload)
        if suggestion is None:
            return

        fingerprint = self._fingerprint(suggestion, payload)
        now = float(self._clock())
        last = self._last_emitted.get(fingerprint)
        if last is not None and (now - last) < self.cooldown_seconds:
            return

        self._last_emitted[fingerprint] = now
        data = suggestion.to_dict()
        self.logger.info(
            "Suggestion proactive : %s | source=%s | niveau=%s",
            suggestion.title,
            suggestion.source_event,
            self.level,
        )
        self.events.publish("proactivity.suggestion", data)

    def _build_suggestion(self, payload: dict[str, Any]) -> ProactiveSuggestion | None:
        event_type = str(payload.get("type") or "")

        if event_type == "system.disk_space_low":
            free_percent = payload.get("free_percent")
            suffix = f" ({float(free_percent):.1f} % libres)" if isinstance(free_percent, (int, float)) else ""
            return ProactiveSuggestion(
                title="Espace disque faible",
                message=(
                    "L'espace disponible dans la zone de stockage SIDERON devient faible"
                    f"{suffix}. Je peux vous aider à identifier ce qui consomme de l'espace."
                ),
                source_event=event_type,
                severity="warning",
            )

        if event_type == "system.audio_devices_changed" and self.level in {"normal", "high", "jarvis"}:
            added = list(payload.get("inputs_added") or []) + list(payload.get("outputs_added") or [])
            removed = list(payload.get("inputs_removed") or []) + list(payload.get("outputs_removed") or [])
            if not added and not removed:
                return None
            return ProactiveSuggestion(
                title="Périphériques audio modifiés",
                message=(
                    "La liste des périphériques audio a changé. Vérifiez le microphone et la sortie actifs "
                    "si le changement n'était pas volontaire."
                ),
                source_event=event_type,
                severity="info",
            )

        if event_type == "system.network_disconnected" and self.level in {"high", "jarvis"}:
            return ProactiveSuggestion(
                title="Connexion réseau perdue",
                message="SIDERON a détecté une perte de connectivité réseau. Je peux proposer un diagnostic si nécessaire.",
                source_event=event_type,
                severity="warning",
            )

        if event_type == "system.battery_changed" and self.level in {"normal", "high", "jarvis"}:
            percent = payload.get("percent")
            plugged = payload.get("plugged")
            if isinstance(percent, (int, float)) and float(percent) <= 20.0 and plugged is False:
                return ProactiveSuggestion(
                    title="Batterie faible",
                    message=f"La batterie est à {float(percent):.0f} % et le PC n'est pas branché.",
                    source_event=event_type,
                    severity="warning",
                )

        return None

    @staticmethod
    def _fingerprint(suggestion: ProactiveSuggestion, payload: dict[str, Any]) -> str:
        if suggestion.source_event == "system.audio_devices_changed":
            parts = (
                tuple(sorted(payload.get("inputs_added") or [])),
                tuple(sorted(payload.get("inputs_removed") or [])),
                tuple(sorted(payload.get("outputs_added") or [])),
                tuple(sorted(payload.get("outputs_removed") or [])),
            )
            return f"{suggestion.source_event}:{parts!r}"
        return suggestion.source_event
