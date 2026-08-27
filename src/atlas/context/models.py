from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class SystemContext:
    cpu_percent: float = 0.0
    memory_percent: float = 0.0
    memory_available_gb: float = 0.0

    uptime_seconds: float = 0.0

    network_bytes_sent: int = 0
    network_bytes_received: int = 0


@dataclass(slots=True)
class WindowContext:
    active_window_title: str | None = None
    active_process_name: str | None = None


@dataclass(slots=True)
class AtlasContext:
    system: SystemContext = field(
        default_factory=SystemContext
    )

    window: WindowContext = field(
        default_factory=WindowContext
    )

    extra: dict[str, Any] = field(
        default_factory=dict
    )