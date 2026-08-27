from __future__ import annotations

import json
import socket
import threading
import time
from pathlib import Path
from typing import Any

import psutil

from atlas.system.powershell import run_fixed_powershell


class AtlasTelemetryPublisher:
    """Publie une télémétrie système légère vers Atlas.UI.

    Ce composant est strictement en lecture seule.
    Il n'exécute aucun Skill et aucune commande libre.

    Les informations réseau Windows plus détaillées sont obtenues via
    un script PowerShell fixe défini dans Atlas, jamais depuis OpenAI.
    """

    INTERVAL_SECONDS = 2.0

    NETWORK_CONFIG_REFRESH_SECONDS = 30.0

    _NETWORK_CONFIG_SCRIPT = r"""
$ErrorActionPreference = 'SilentlyContinue'

$configs = @(
    Get-NetIPConfiguration |
        Where-Object {
            $_.NetAdapter.Status -eq 'Up' -and
            $_.IPv4Address
        }
)

$selected = $configs |
    Sort-Object {
        $_.NetAdapter.InterfaceMetric
    } |
    Select-Object -First 1

if ($null -eq $selected) {
    [pscustomobject]@{
        interface_alias = $null
        interface_description = $null
        link_speed_bps = $null
        ipv4 = $null
        gateway = $null
        dns = @()
    } | ConvertTo-Json -Compress -Depth 4
    exit 0
}

[pscustomobject]@{
    interface_alias = $selected.InterfaceAlias
    interface_description = $selected.InterfaceDescription
    # Numeric UInt64 in bits/s: never parse the localized LinkSpeed display.
    link_speed_bps = $selected.NetAdapter.ReceiveLinkSpeed
    ipv4 = @(
        $selected.IPv4Address |
            Select-Object -First 1
    )[0].IPv4Address
    gateway = @(
        $selected.IPv4DefaultGateway |
            Select-Object -First 1
    )[0].NextHop
    dns = @(
        $selected.DNSServer.ServerAddresses |
            Where-Object { $_ }
    )
} | ConvertTo-Json -Compress -Depth 4
"""

    def __init__(
        self,
        ui_bridge,
        logger,
        storage_root_provider,
    ) -> None:

        self._ui_bridge = ui_bridge
        self._logger = logger
        self._storage_root_provider = (
            storage_root_provider
        )

        self._stop_event = threading.Event()

        self._thread: (
            threading.Thread
            | None
        ) = None

        self._network_config: dict[
            str,
            Any,
        ] = {}

        self._network_config_timestamp = 0.0

        self._last_network_counters: (
            tuple[
                str,
                int,
                int,
                float,
            ]
            | None
        ) = None

    def start(
        self,
    ) -> None:

        if (
            self._thread is not None
            and self._thread.is_alive()
        ):
            return

        self._stop_event.clear()

        try:
            psutil.cpu_percent(
                interval=None
            )
        except Exception:
            pass

        self._thread = threading.Thread(
            target=self._run,
            name="AtlasTelemetry",
            daemon=True,
        )

        self._thread.start()

        self._logger.info(
            "Télémétrie Atlas.UI démarrée."
        )

    def stop(
        self,
        timeout: float = 2.0,
    ) -> None:

        self._stop_event.set()

        if (
            self._thread is not None
            and self._thread.is_alive()
        ):
            self._thread.join(
                timeout=timeout
            )

        self._thread = None

        self._logger.info(
            "Télémétrie Atlas.UI arrêtée."
        )

    def _run(
        self,
    ) -> None:

        self._stop_event.wait(
            0.5
        )

        while not self._stop_event.is_set():

            try:
                snapshot = (
                    self._collect_snapshot()
                )

                self._ui_bridge.send_event(
                    "system.telemetry",
                    snapshot,
                )

            except Exception as exc:
                self._logger.debug(
                    "Télémétrie Atlas.UI indisponible : %s",
                    exc,
                )

            self._stop_event.wait(
                self.INTERVAL_SECONDS
            )

    def _collect_snapshot(
        self,
    ) -> dict[str, Any]:

        cpu_percent = round(
            float(
                psutil.cpu_percent(
                    interval=None
                )
            ),
            1,
        )

        memory = psutil.virtual_memory()

        storage_root = (
            self._resolve_storage_root()
        )

        disk = psutil.disk_usage(
            storage_root
        )

        uptime_seconds = max(
            0,
            int(
                time.time()
                - psutil.boot_time()
            ),
        )

        network = (
            self._collect_network_snapshot()
        )

        return {
            "cpu_percent":
                cpu_percent,

            "memory_percent":
                round(
                    float(
                        memory.percent
                    ),
                    1,
                ),

            "memory_used_bytes":
                int(
                    memory.used
                ),

            "memory_total_bytes":
                int(
                    memory.total
                ),

            "disk_percent":
                round(
                    float(
                        disk.percent
                    ),
                    1,
                ),

            "disk_used_bytes":
                int(
                    disk.used
                ),

            "disk_total_bytes":
                int(
                    disk.total
                ),

            "storage_root":
                storage_root,

            "uptime_seconds":
                uptime_seconds,

            "network_up":
                bool(
                    network.get(
                        "up",
                        False,
                    )
                ),

            "network":
                network,

            "timestamp":
                time.time(),
        }

    def _collect_network_snapshot(
        self,
    ) -> dict[str, Any]:

        self._refresh_network_config_if_needed()

        config = dict(
            self._network_config
        )

        alias = str(
            config.get(
                "interface_alias"
            )
            or ""
        )

        description = str(
            config.get(
                "interface_description"
            )
            or ""
        )

        if not alias:
            alias = (
                self._find_fallback_interface()
                or ""
            )

        stats = (
            psutil.net_if_stats()
        )

        interface_stats = (
            stats.get(
                alias
            )
        )

        interface_up = bool(
            interface_stats
            and interface_stats.isup
        )

        link_speed_mbps = self._resolve_link_speed_mbps(
            alias, config, interface_stats
        )

        ipv4 = (
            config.get(
                "ipv4"
            )
            or self._get_interface_ipv4(
                alias
            )
        )

        rx_bps, tx_bps = (
            self._calculate_network_rates(
                alias
            )
        )

        return {
            "up":
                interface_up,

            "interface":
                alias or None,

            "description":
                description or None,

            "connection_type":
                self._classify_connection(
                    alias,
                    description,
                ),

            "ipv4":
                ipv4,

            "gateway":
                config.get(
                    "gateway"
                ),

            "dns":
                self._normalize_dns(
                    config.get(
                        "dns"
                    )
                ),

            "link_speed_mbps":
                link_speed_mbps,

            "download_bps":
                rx_bps,

            "upload_bps":
                tx_bps,
        }

    @staticmethod
    def _resolve_link_speed_mbps(
        alias: str,
        config: dict[str, Any],
        interface_stats,
    ) -> int | None:
        if interface_stats is None or not interface_stats.isup:
            return None

        # Use the UInt64 Windows measurement only for the matching adapter.
        if alias and alias == config.get("interface_alias"):
            raw = config.get("link_speed_bps")
            if isinstance(raw, int) and not isinstance(raw, bool) and raw > 0:
                return max(1, raw // 1_000_000)

        # Older Windows backends saturate at DWORD_MAX bits/s, truncated
        # to 4294 Mbit/s by psutil. Do not display that sentinel as a speed.
        speed = int(interface_stats.speed)
        if speed > 0 and speed != 4294:
            return speed
        return None

    def _refresh_network_config_if_needed(
        self,
    ) -> None:

        now = time.monotonic()

        if (
            self._network_config
            and now
            - self._network_config_timestamp
            < self.NETWORK_CONFIG_REFRESH_SECONDS
        ):
            return

        self._network_config_timestamp = (
            now
        )

        # An expired speed must not survive a failed refresh/renegotiation.
        self._network_config.pop("link_speed_bps", None)

        try:
            result = run_fixed_powershell(
                self._NETWORK_CONFIG_SCRIPT,
                timeout=4.0,
            )

            if result.returncode != 0:
                return

            output = result.stdout.strip()

            if not output:
                return

            parsed = json.loads(
                output
            )

            if isinstance(
                parsed,
                dict,
            ):
                self._network_config = (
                    parsed
                )

        except Exception as exc:
            self._logger.debug(
                "Configuration réseau détaillée indisponible : %s",
                exc,
            )

    def _find_fallback_interface(
        self,
    ) -> str | None:

        stats = psutil.net_if_stats()
        addresses = psutil.net_if_addrs()

        for (
            name,
            interface_stats,
        ) in stats.items():

            lowered = name.lower()

            if (
                not interface_stats.isup
                or "loopback" in lowered
                or "bluetooth" in lowered
            ):
                continue

            for address in addresses.get(
                name,
                [],
            ):
                if (
                    address.family
                    == socket.AF_INET
                    and not address.address.startswith(
                        "127."
                    )
                ):
                    return name

        return None

    @staticmethod
    def _get_interface_ipv4(
        alias: str,
    ) -> str | None:

        if not alias:
            return None

        for address in psutil.net_if_addrs().get(
            alias,
            [],
        ):
            if (
                address.family
                == socket.AF_INET
                and not address.address.startswith(
                    "127."
                )
            ):
                return address.address

        return None

    def _calculate_network_rates(
        self,
        alias: str,
    ) -> tuple[
        float,
        float,
    ]:

        if not alias:
            self._last_network_counters = (
                None
            )
            return 0.0, 0.0

        counters = psutil.net_io_counters(
            pernic=True
        ).get(
            alias
        )

        if counters is None:
            self._last_network_counters = (
                None
            )
            return 0.0, 0.0

        now = time.monotonic()

        previous = (
            self._last_network_counters
        )

        self._last_network_counters = (
            alias,
            int(
                counters.bytes_recv
            ),
            int(
                counters.bytes_sent
            ),
            now,
        )

        if (
            previous is None
            or previous[0] != alias
        ):
            return 0.0, 0.0

        elapsed = max(
            0.001,
            now - previous[3],
        )

        rx = max(
            0,
            int(
                counters.bytes_recv
            )
            - previous[1],
        )

        tx = max(
            0,
            int(
                counters.bytes_sent
            )
            - previous[2],
        )

        return (
            round(
                rx / elapsed,
                1,
            ),
            round(
                tx / elapsed,
                1,
            ),
        )

    @staticmethod
    def _classify_connection(
        alias: str,
        description: str,
    ) -> str:

        text = (
            f"{alias} {description}"
        ).lower()

        if any(
            token in text
            for token in (
                "wi-fi",
                "wifi",
                "wireless",
                "wlan",
                "802.11",
            )
        ):
            return "Wi-Fi"

        if any(
            token in text
            for token in (
                "ethernet",
                "gigabit",
                "2.5gbe",
                "10gbe",
                "lan",
            )
        ):
            return "Ethernet"

        return "Réseau"

    @staticmethod
    def _normalize_dns(
        value: Any,
    ) -> list[str]:

        if value is None:
            return []

        if isinstance(
            value,
            str,
        ):
            return [
                value
            ]

        if isinstance(
            value,
            list,
        ):
            return [
                str(
                    item
                )
                for item in value
                if item
            ]

        return []

    def _resolve_storage_root(
        self,
    ) -> str:

        try:
            raw = (
                self._storage_root_provider()
            )

            if raw:
                path = Path(
                    str(
                        raw
                    )
                )

                return (
                    path.anchor
                    or str(
                        path
                    )
                )

        except Exception:
            pass

        return (
            Path.cwd().anchor
            or "C:\\"
        )
