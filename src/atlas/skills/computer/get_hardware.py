from __future__ import annotations

import json
import subprocess
from typing import Any

from atlas.system.powershell import run_fixed_powershell

from atlas.security.risk import RiskLevel
from atlas.skills.base import Skill, SkillResult


POWERSHELL_TIMEOUT_SECONDS = 20.0

POWERSHELL_SCRIPT = r"""
$cpu = Get-CimInstance Win32_Processor | Select-Object `
    Name,
    Manufacturer,
    NumberOfCores,
    NumberOfLogicalProcessors,
    MaxClockSpeed,
    ProcessorId

$gpu = Get-CimInstance Win32_VideoController | Select-Object `
    Name,
    AdapterCompatibility,
    AdapterRAM,
    DriverVersion,
    VideoProcessor,
    CurrentHorizontalResolution,
    CurrentVerticalResolution

$memory = Get-CimInstance Win32_PhysicalMemory | Select-Object `
    Manufacturer,
    PartNumber,
    SerialNumber,
    Capacity,
    Speed,
    ConfiguredClockSpeed,
    DeviceLocator,
    BankLabel

$disks = Get-CimInstance Win32_DiskDrive | Select-Object `
    Model,
    Manufacturer,
    SerialNumber,
    InterfaceType,
    MediaType,
    Size,
    Index,
    FirmwareRevision

$result = [PSCustomObject]@{
    Cpu = @($cpu)
    Gpu = @($gpu)
    Memory = @($memory)
    Disks = @($disks)
}

$result | ConvertTo-Json -Depth 5 -Compress
""".strip()


class GetComputerHardwareSkill(Skill):

    name = "computer.get_hardware"

    description = (
        "Récupère les détails matériels de l'ordinateur : "
        "processeur, cartes graphiques, barrettes mémoire et disques physiques."
    )

    parameters = {
        "type": "object",
        "properties": {},
        "additionalProperties": False,
    }

    risk_level = RiskLevel.READ_ONLY

    required_permission = None

    requires_service = False

    def execute(
        self,
        **kwargs: Any,
    ) -> SkillResult:

        try:

            completed = run_fixed_powershell(
                POWERSHELL_SCRIPT,
                timeout=POWERSHELL_TIMEOUT_SECONDS,
            )

        except FileNotFoundError:

            return SkillResult(
                success=False,
                message=(
                    "PowerShell est introuvable sur ce système."
                ),
            )

        except subprocess.TimeoutExpired:

            return SkillResult(
                success=False,
                message=(
                    "La récupération des informations matérielles "
                    "a dépassé le délai autorisé."
                ),
            )

        except OSError as exc:

            return SkillResult(
                success=False,
                message=(
                    "Impossible de récupérer les informations matérielles."
                ),
                data={
                    "error": str(exc),
                },
            )

        if completed.returncode != 0:

            return SkillResult(
                success=False,
                message=(
                    "Windows n'a pas pu retourner les informations matérielles."
                ),
                data={
                    "returncode": completed.returncode,
                    "stdout": completed.stdout.strip(),
                    "stderr": completed.stderr.strip(),
                },
            )

        raw_output = completed.stdout.strip()

        if not raw_output:

            return SkillResult(
                success=False,
                message=(
                    "Windows n'a retourné aucune information matérielle."
                ),
            )

        try:

            parsed = json.loads(
                raw_output
            )

        except json.JSONDecodeError as exc:

            return SkillResult(
                success=False,
                message=(
                    "Les informations matérielles retournées par Windows "
                    "n'ont pas pu être interprétées."
                ),
                data={
                    "error": str(exc),
                    "raw": raw_output,
                },
            )

        if not isinstance(
            parsed,
            dict,
        ):

            return SkillResult(
                success=False,
                message=(
                    "Le format des informations matérielles est invalide."
                ),
            )

        cpu = self._ensure_list(
            parsed.get(
                "Cpu"
            )
        )

        gpu = self._ensure_list(
            parsed.get(
                "Gpu"
            )
        )

        memory = self._ensure_list(
            parsed.get(
                "Memory"
            )
        )

        disks = self._ensure_list(
            parsed.get(
                "Disks"
            )
        )

        normalized_memory = []

        total_memory_bytes = 0

        for module in memory:

            capacity = module.get(
                "Capacity"
            )

            capacity_bytes = (
                int(capacity)
                if isinstance(
                    capacity,
                    (int, float),
                )
                else None
            )

            if capacity_bytes is not None:
                total_memory_bytes += capacity_bytes

            normalized_memory.append(
                {
                    "manufacturer": module.get(
                        "Manufacturer"
                    ),
                    "part_number": self._clean_string(
                        module.get(
                            "PartNumber"
                        )
                    ),
                    "serial_number": self._clean_string(
                        module.get(
                            "SerialNumber"
                        )
                    ),
                    "capacity_bytes": capacity_bytes,
                    "capacity_gb": (
                        round(
                            capacity_bytes
                            / (1024 ** 3),
                            2,
                        )
                        if capacity_bytes is not None
                        else None
                    ),
                    "speed_mhz": module.get(
                        "Speed"
                    ),
                    "configured_speed_mhz": module.get(
                        "ConfiguredClockSpeed"
                    ),
                    "device_locator": module.get(
                        "DeviceLocator"
                    ),
                    "bank_label": module.get(
                        "BankLabel"
                    ),
                }
            )

        normalized_disks = []

        total_disk_bytes = 0

        for disk in disks:

            size = disk.get(
                "Size"
            )

            size_bytes = (
                int(size)
                if isinstance(
                    size,
                    (int, float),
                )
                else None
            )

            if size_bytes is not None:
                total_disk_bytes += size_bytes

            normalized_disks.append(
                {
                    "model": self._clean_string(
                        disk.get(
                            "Model"
                        )
                    ),
                    "manufacturer": self._clean_string(
                        disk.get(
                            "Manufacturer"
                        )
                    ),
                    "serial_number": self._clean_string(
                        disk.get(
                            "SerialNumber"
                        )
                    ),
                    "interface_type": disk.get(
                        "InterfaceType"
                    ),
                    "media_type": disk.get(
                        "MediaType"
                    ),
                    "size_bytes": size_bytes,
                    "size_gb": (
                        round(
                            size_bytes
                            / (1024 ** 3),
                            2,
                        )
                        if size_bytes is not None
                        else None
                    ),
                    "index": disk.get(
                        "Index"
                    ),
                    "firmware_revision": self._clean_string(
                        disk.get(
                            "FirmwareRevision"
                        )
                    ),
                }
            )

        normalized_gpu = []

        for adapter in gpu:

            adapter_ram = adapter.get(
                "AdapterRAM"
            )

            adapter_ram_bytes = (
                int(adapter_ram)
                if isinstance(
                    adapter_ram,
                    (int, float),
                )
                and adapter_ram >= 0
                else None
            )

            normalized_gpu.append(
                {
                    "name": adapter.get(
                        "Name"
                    ),
                    "manufacturer": adapter.get(
                        "AdapterCompatibility"
                    ),
                    "video_processor": adapter.get(
                        "VideoProcessor"
                    ),
                    "driver_version": adapter.get(
                        "DriverVersion"
                    ),
                    "adapter_ram_bytes": adapter_ram_bytes,
                    "adapter_ram_gb": (
                        round(
                            adapter_ram_bytes
                            / (1024 ** 3),
                            2,
                        )
                        if adapter_ram_bytes is not None
                        else None
                    ),
                    "current_resolution": (
                        f"{adapter.get('CurrentHorizontalResolution')}x"
                        f"{adapter.get('CurrentVerticalResolution')}"
                        if (
                            adapter.get(
                                "CurrentHorizontalResolution"
                            )
                            and adapter.get(
                                "CurrentVerticalResolution"
                            )
                        )
                        else None
                    ),
                }
            )

        normalized_cpu = []

        for processor in cpu:

            normalized_cpu.append(
                {
                    "name": self._clean_string(
                        processor.get(
                            "Name"
                        )
                    ),
                    "manufacturer": processor.get(
                        "Manufacturer"
                    ),
                    "cores": processor.get(
                        "NumberOfCores"
                    ),
                    "logical_processors": processor.get(
                        "NumberOfLogicalProcessors"
                    ),
                    "max_clock_mhz": processor.get(
                        "MaxClockSpeed"
                    ),
                    "processor_id": processor.get(
                        "ProcessorId"
                    ),
                }
            )

        return SkillResult(
            success=True,
            message=(
                f"Informations matérielles récupérées : "
                f"{len(normalized_cpu)} processeur(s), "
                f"{len(normalized_gpu)} carte(s) graphique(s), "
                f"{len(normalized_memory)} barrette(s) mémoire "
                f"et {len(normalized_disks)} disque(s) physique(s)."
            ),
            data={
                "cpu": normalized_cpu,
                "gpu": normalized_gpu,
                "memory": normalized_memory,
                "disks": normalized_disks,
                "summary": {
                    "cpu_count": len(
                        normalized_cpu
                    ),
                    "gpu_count": len(
                        normalized_gpu
                    ),
                    "memory_module_count": len(
                        normalized_memory
                    ),
                    "total_memory_bytes": (
                        total_memory_bytes
                    ),
                    "total_memory_gb": round(
                        total_memory_bytes
                        / (1024 ** 3),
                        2,
                    ),
                    "disk_count": len(
                        normalized_disks
                    ),
                    "total_disk_bytes": (
                        total_disk_bytes
                    ),
                    "total_disk_gb": round(
                        total_disk_bytes
                        / (1024 ** 3),
                        2,
                    ),
                },
            },
        )

    @staticmethod
    def _ensure_list(
        value: Any,
    ) -> list[dict[str, Any]]:

        if isinstance(
            value,
            dict,
        ):

            return [
                value
            ]

        if isinstance(
            value,
            list,
        ):

            return [
                item
                for item in value
                if isinstance(
                    item,
                    dict,
                )
            ]

        return []

    @staticmethod
    def _clean_string(
        value: Any,
    ) -> str | None:

        if value is None:
            return None

        text = str(
            value
        ).strip()

        return (
            text
            if text
            else None
        )
