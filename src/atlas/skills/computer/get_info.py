from __future__ import annotations

import json
import subprocess
from typing import Any

from atlas.system.powershell import run_fixed_powershell

from atlas.security.risk import RiskLevel
from atlas.skills.base import Skill, SkillResult


POWERSHELL_TIMEOUT_SECONDS = 15.0

POWERSHELL_SCRIPT = r"""
$computer = Get-CimInstance Win32_ComputerSystem
$os = Get-CimInstance Win32_OperatingSystem
$bios = Get-CimInstance Win32_BIOS
$board = Get-CimInstance Win32_BaseBoard

$result = [PSCustomObject]@{
    ComputerName = $env:COMPUTERNAME
    Manufacturer = $computer.Manufacturer
    Model = $computer.Model
    SystemType = $computer.SystemType
    Domain = $computer.Domain
    PartOfDomain = $computer.PartOfDomain
    TotalPhysicalMemoryBytes = [Int64]$computer.TotalPhysicalMemory

    WindowsCaption = $os.Caption
    WindowsVersion = $os.Version
    WindowsBuild = $os.BuildNumber
    Architecture = $os.OSArchitecture
    InstallDate = $os.InstallDate
    LastBootUpTime = $os.LastBootUpTime

    BiosManufacturer = $bios.Manufacturer
    BiosVersion = ($bios.SMBIOSBIOSVersion -join ", ")
    BiosSerialNumber = $bios.SerialNumber
    BiosReleaseDate = $bios.ReleaseDate

    BaseBoardManufacturer = $board.Manufacturer
    BaseBoardProduct = $board.Product
    BaseBoardSerialNumber = $board.SerialNumber
}

$result | ConvertTo-Json -Depth 3 -Compress
""".strip()


class GetComputerInfoSkill(Skill):

    name = "computer.get_info"

    description = (
        "Récupère les informations principales de l'ordinateur Windows : "
        "constructeur, modèle, système, BIOS, carte mère, mémoire et domaine."
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
                    "La récupération des informations de l'ordinateur "
                    "a dépassé le délai autorisé."
                ),
            )

        except OSError as exc:

            return SkillResult(
                success=False,
                message=(
                    "Impossible de récupérer les informations "
                    "de l'ordinateur."
                ),
                data={
                    "error": str(exc),
                },
            )

        if completed.returncode != 0:

            return SkillResult(
                success=False,
                message=(
                    "Windows n'a pas pu retourner les informations "
                    "de l'ordinateur."
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
                    "Windows n'a retourné aucune information "
                    "sur l'ordinateur."
                ),
            )

        try:

            info = json.loads(
                raw_output
            )

        except json.JSONDecodeError as exc:

            return SkillResult(
                success=False,
                message=(
                    "Les informations retournées par Windows "
                    "n'ont pas pu être interprétées."
                ),
                data={
                    "error": str(exc),
                    "raw": raw_output,
                },
            )

        if not isinstance(
            info,
            dict,
        ):

            return SkillResult(
                success=False,
                message=(
                    "Le format des informations de l'ordinateur "
                    "est invalide."
                ),
            )

        total_memory_bytes = info.get(
            "TotalPhysicalMemoryBytes"
        )

        total_memory_gb = None

        if isinstance(
            total_memory_bytes,
            (int, float),
        ):

            total_memory_gb = round(
                float(total_memory_bytes)
                / (1024 ** 3),
                2,
            )

        normalized = {
            "computer_name": info.get(
                "ComputerName"
            ),
            "manufacturer": info.get(
                "Manufacturer"
            ),
            "model": info.get(
                "Model"
            ),
            "system_type": info.get(
                "SystemType"
            ),
            "domain": info.get(
                "Domain"
            ),
            "part_of_domain": info.get(
                "PartOfDomain"
            ),
            "total_physical_memory_bytes": (
                total_memory_bytes
            ),
            "total_physical_memory_gb": (
                total_memory_gb
            ),
            "windows": {
                "caption": info.get(
                    "WindowsCaption"
                ),
                "version": info.get(
                    "WindowsVersion"
                ),
                "build": info.get(
                    "WindowsBuild"
                ),
                "architecture": info.get(
                    "Architecture"
                ),
                "install_date": info.get(
                    "InstallDate"
                ),
                "last_boot_time": info.get(
                    "LastBootUpTime"
                ),
            },
            "bios": {
                "manufacturer": info.get(
                    "BiosManufacturer"
                ),
                "version": info.get(
                    "BiosVersion"
                ),
                "serial_number": info.get(
                    "BiosSerialNumber"
                ),
                "release_date": info.get(
                    "BiosReleaseDate"
                ),
            },
            "baseboard": {
                "manufacturer": info.get(
                    "BaseBoardManufacturer"
                ),
                "product": info.get(
                    "BaseBoardProduct"
                ),
                "serial_number": info.get(
                    "BaseBoardSerialNumber"
                ),
            },
        }

        computer_name = (
            normalized.get(
                "computer_name"
            )
            or "cet ordinateur"
        )

        manufacturer = normalized.get(
            "manufacturer"
        )

        model = normalized.get(
            "model"
        )

        if manufacturer or model:

            identity = " ".join(
                str(value)
                for value in (
                    manufacturer,
                    model,
                )
                if value
            )

            message = (
                f"Informations de '{computer_name}' récupérées : "
                f"{identity}."
            )

        else:

            message = (
                f"Informations de '{computer_name}' récupérées."
            )

        return SkillResult(
            success=True,
            message=message,
            data=normalized,
        )
