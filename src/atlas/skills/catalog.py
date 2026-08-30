from __future__ import annotations

from atlas.skills.windows.open_app import OpenAppSkill
from atlas.skills.windows.close_app import CloseAppSkill

from atlas.skills.computer.get_info import (
    GetComputerInfoSkill,
)
from atlas.skills.computer.get_uptime import (
    GetComputerUptimeSkill,
)
from atlas.skills.computer.get_hardware import (
    GetComputerHardwareSkill,
)
from atlas.skills.computer.get_battery import (
    GetComputerBatterySkill,
)
from atlas.skills.computer.get_displays import (
    GetComputerDisplaysSkill,
)
from atlas.skills.computer.get_devices import (
    GetComputerDevicesSkill,
)
from atlas.skills.computer.get_drivers import (
    GetComputerDriversSkill,
)

from atlas.skills.process.list_processes import (
    ListProcessesSkill,
)
from atlas.skills.process.get_usage import (
    GetProcessUsageSkill,
)
from atlas.skills.process.kill_process import (
    KillProcessSkill,
)

from atlas.skills.network.get_adapters import (
    GetNetworkAdaptersSkill,
)
from atlas.skills.network.flush_dns import (
    FlushDnsSkill,
)
from atlas.skills.network.renew_dhcp import (
    RenewDhcpSkill,
)
from atlas.skills.network.get_ip_config import (
    GetIpConfigSkill,
)
from atlas.skills.network.ping import (
    PingNetworkSkill,
)
from atlas.skills.network.dns_lookup import (
    DnsLookupSkill,
)
from atlas.skills.network.traceroute import (
    TracerouteNetworkSkill,
)
from atlas.skills.network.test_port import (
    TestPortNetworkSkill,
)
from atlas.skills.network.get_public_ip import (
    GetPublicIpNetworkSkill,
)
from atlas.skills.network.get_routes import (
    GetRoutesNetworkSkill,
)
from atlas.skills.network.get_connections import (
    GetConnectionsNetworkSkill,
)
from atlas.skills.network.get_dns_cache import (
    GetDnsCacheNetworkSkill,
)
from atlas.skills.network.get_arp_table import (
    GetArpTableNetworkSkill,
)
from atlas.skills.network.get_wifi_info import (
    GetWifiInfoNetworkSkill,
)
from atlas.skills.network.get_wifi_networks import (
    GetWifiNetworksNetworkSkill,
)

from atlas.skills.audio.get_volume import (
    GetVolumeSkill,
)
from atlas.skills.audio.set_volume import (
    SetVolumeSkill,
)
from atlas.skills.audio.mute import (
    MuteSkill,
    UnmuteSkill,
)

from atlas.skills.system.cpu import (
    GetCpuUsageSkill,
)
from atlas.skills.system.memory import (
    GetMemoryUsageSkill,
)
from atlas.skills.system.disk import (
    GetDiskUsageSkill,
)
from atlas.skills.system.status import (
    GetSystemStatusSkill,
)
from atlas.skills.system.lock import (
    LockComputerSkill,
)
from atlas.skills.system.restart import (
    RestartComputerSkill,
)
from atlas.skills.system.shutdown import (
    ShutdownComputerSkill,
)
from atlas.skills.system.cancel_shutdown import (
    CancelShutdownSkill,
)

from atlas.skills.file.read_text import (
    ReadTextFileSkill,
)
from atlas.skills.file.search import (
    SearchFileSkill,
)
from atlas.skills.file.import_file import (
    ImportFileSkill,
)

from atlas.skills.directory.list_directory import (
    ListDirectorySkill,
)
from atlas.skills.directory.import_directory import (
    ImportDirectorySkill,
)

from atlas.skills.workspace.create_directory import (
    CreateWorkspaceDirectorySkill,
)
from atlas.skills.workspace.create_file import (
    CreateWorkspaceFileSkill,
)
from atlas.skills.workspace.write_file import (
    WriteWorkspaceFileSkill,
)
from atlas.skills.workspace.open_directory import (
    OpenWorkspaceDirectorySkill,
)
from atlas.skills.workspace.rename import (
    RenameWorkspaceItemSkill,
)
from atlas.skills.workspace.move import (
    MoveWorkspaceItemSkill,
)
from atlas.skills.workspace.delete import (
    DeleteWorkspaceItemSkill,
)

from atlas.skills.service.list_services import (
    ListServicesSkill,
)
from atlas.skills.service.get_status import (
    GetServiceStatusSkill,
)
from atlas.skills.service.start_service import (
    StartServiceSkill,
)
from atlas.skills.service.stop_service import (
    StopServiceSkill,
)
from atlas.skills.service.restart_service import (
    RestartServiceSkill,
)


def register_default_skills(
    registry,
    storage,
    service_client,
    event_bus,
) -> None:

    # =================================================
    # Windows
    # =================================================

    registry.register(
        OpenAppSkill()
    )

    registry.register(
        CloseAppSkill()
    )

    # =================================================
    # Ordinateur
    # =================================================

    registry.register(
        GetComputerInfoSkill()
    )

    registry.register(
        GetComputerUptimeSkill()
    )

    registry.register(
        GetComputerHardwareSkill()
    )

    registry.register(
        GetComputerBatterySkill()
    )

    registry.register(
        GetComputerDisplaysSkill()
    )

    registry.register(
        GetComputerDevicesSkill()
    )

    registry.register(
        GetComputerDriversSkill()
    )

    # =================================================
    # Processus
    # =================================================

    registry.register(
        ListProcessesSkill()
    )

    registry.register(
        GetProcessUsageSkill()
    )

    registry.register(
        KillProcessSkill(
            service_client=(
                service_client
            )
        )
    )

    # =================================================
    # Réseau
    # =================================================

    registry.register(
        GetNetworkAdaptersSkill()
    )

    registry.register(
        FlushDnsSkill(
            service_client=(
                service_client
            )
        )
    )

    registry.register(
        RenewDhcpSkill(
            service_client=(
                service_client
            )
        )
    )

    registry.register(
        GetIpConfigSkill()
    )

    registry.register(
        PingNetworkSkill()
    )

    registry.register(
        DnsLookupSkill()
    )

    registry.register(
        TracerouteNetworkSkill()
    )

    registry.register(
        TestPortNetworkSkill()
    )

    registry.register(
        GetPublicIpNetworkSkill()
    )

    registry.register(
        GetRoutesNetworkSkill()
    )

    registry.register(
        GetConnectionsNetworkSkill()
    )

    registry.register(
        GetDnsCacheNetworkSkill()
    )

    registry.register(
        GetArpTableNetworkSkill()
    )

    registry.register(
        GetWifiInfoNetworkSkill()
    )

    registry.register(
        GetWifiNetworksNetworkSkill()
    )

    # =================================================
    # Audio
    # =================================================

    registry.register(
        GetVolumeSkill()
    )

    registry.register(
        SetVolumeSkill()
    )

    registry.register(
        MuteSkill()
    )

    registry.register(
        UnmuteSkill()
    )

    # =================================================
    # Système
    # =================================================

    registry.register(
        GetCpuUsageSkill()
    )

    registry.register(
        GetMemoryUsageSkill()
    )

    registry.register(
        GetDiskUsageSkill()
    )

    registry.register(
        GetSystemStatusSkill()
    )

    registry.register(
        LockComputerSkill()
    )

    registry.register(
        RestartComputerSkill(
            service_client=(
                service_client
            )
        )
    )

    registry.register(
        ShutdownComputerSkill(
            service_client=(
                service_client
            )
        )
    )

    registry.register(
        CancelShutdownSkill(
            service_client=(
                service_client
            )
        )
    )

    # =================================================
    # Fichiers / dossiers
    # =================================================

    registry.register(
        ReadTextFileSkill(
            storage=storage
        )
    )

    registry.register(
        SearchFileSkill(
            storage=storage
        )
    )

    registry.register(
        ListDirectorySkill(
            storage=storage
        )
    )

    registry.register(
        ImportFileSkill(
            storage=storage
        )
    )

    registry.register(
        ImportDirectorySkill(
            storage=storage
        )
    )

    # =================================================
    # Workspace
    # =================================================

    registry.register(
        CreateWorkspaceDirectorySkill(
            storage=storage
        )
    )

    registry.register(
        CreateWorkspaceFileSkill(
            storage=storage
        )
    )

    registry.register(
        WriteWorkspaceFileSkill(
            storage=storage
        )
    )

    registry.register(
        RenameWorkspaceItemSkill(
            storage=storage
        )
    )

    registry.register(
        MoveWorkspaceItemSkill(
            storage=storage
        )
    )

    registry.register(
        DeleteWorkspaceItemSkill(
            storage=storage
        )
    )

    registry.register(
        OpenWorkspaceDirectorySkill(
            storage=storage,
            event_bus=event_bus,
        )
    )

    # =================================================
    # Services Windows
    # =================================================

    registry.register(
        ListServicesSkill()
    )

    registry.register(
        GetServiceStatusSkill()
    )

    registry.register(
        StartServiceSkill(
            service_client=(
                service_client
            )
        )
    )

    registry.register(
        StopServiceSkill(
            service_client=(
                service_client
            )
        )
    )

    registry.register(
        RestartServiceSkill(
            service_client=(
                service_client
            )
        )
    )
