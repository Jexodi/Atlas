from __future__ import annotations

import json
import subprocess
from typing import Any

from atlas.system.powershell import run_fixed_powershell

from atlas.security.risk import RiskLevel
from atlas.skills.base import Skill, SkillResult


POWERSHELL_TIMEOUT_SECONDS = 25.0
MAX_DRIVERS = 500

POWERSHELL_SCRIPT = (
    "Get-CimInstance Win32_PnPSignedDriver | "
    "Select-Object "
    "DeviceName,"
    "DeviceClass,"
    "Manufacturer,"
    "DriverProviderName,"
    "DriverVersion,"
    "DriverDate,"
    "InfName,"
    "IsSigned,"
    "Signer,"
    "DeviceID | "
    "Sort-Object DeviceClass,DeviceName | "
    "ConvertTo-Json -Depth 3 -Compress"
)


class GetComputerDriversSkill(Skill):

    name = "computer.get_drivers"

    description = (
        "Liste les pilotes de périphériques installés dans Windows avec "
        "leur version, fournisseur, date, signature et fichier INF."
    )

    parameters = {
        "type": "object",
        "properties": {
            "device_class": {
                "type": "string",
                "default": "",
                "description": (
                    "Filtre optionnel sur la classe du périphérique."
                ),
            },
            "query": {
                "type": "string",
                "default": "",
                "description": (
                    "Filtre optionnel sur le nom du périphérique, "
                    "le fournisseur, la version ou le fichier INF."
                ),
            },
            "unsigned_only": {
                "type": "boolean",
                "default": False,
                "description": (
                    "Si vrai, ne retourne que les pilotes non signés."
                ),
            },
        },
        "additionalProperties": False,
    }

    risk_level = RiskLevel.READ_ONLY

    required_permission = None

    requires_service = False

    def execute(
        self,
        device_class: str = "",
        query: str = "",
        unsigned_only: bool = False,
        **kwargs: Any,
    ) -> SkillResult:

        if not isinstance(
            device_class,
            str,
        ):

            return SkillResult(
                success=False,
                message=(
                    "Le filtre de classe fourni est invalide."
                ),
            )

        if not isinstance(
            query,
            str,
        ):

            return SkillResult(
                success=False,
                message=(
                    "Le filtre de recherche fourni est invalide."
                ),
            )

        if not isinstance(
            unsigned_only,
            bool,
        ):

            return SkillResult(
                success=False,
                message=(
                    "Le filtre de signature fourni est invalide."
                ),
            )

        class_filter = (
            device_class.strip().casefold()
        )

        query_filter = (
            query.strip().casefold()
        )

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
                    "La récupération des pilotes "
                    "a dépassé le délai autorisé."
                ),
            )

        except OSError as exc:

            return SkillResult(
                success=False,
                message=(
                    "Impossible de récupérer les pilotes Windows."
                ),
                data={
                    "error": str(exc),
                },
            )

        if completed.returncode != 0:

            return SkillResult(
                success=False,
                message=(
                    "Windows n'a pas pu retourner la liste des pilotes."
                ),
                data={
                    "returncode": completed.returncode,
                    "stdout": completed.stdout.strip(),
                    "stderr": completed.stderr.strip(),
                },
            )

        raw_output = completed.stdout.strip()

        if not raw_output:

            drivers: list[dict[str, Any]] = []

        else:

            try:

                parsed = json.loads(
                    raw_output
                )

            except json.JSONDecodeError as exc:

                return SkillResult(
                    success=False,
                    message=(
                        "La liste des pilotes retournée par Windows "
                        "n'a pas pu être interprétée."
                    ),
                    data={
                        "error": str(exc),
                        "raw": raw_output,
                    },
                )

            if isinstance(
                parsed,
                dict,
            ):

                drivers = [
                    parsed
                ]

            elif isinstance(
                parsed,
                list,
            ):

                drivers = [
                    item
                    for item in parsed
                    if isinstance(
                        item,
                        dict,
                    )
                ]

            else:

                drivers = []

        filtered_drivers = []

        for driver in drivers:

            device_name = str(
                driver.get(
                    "DeviceName",
                    "",
                )
            )

            device_class_value = str(
                driver.get(
                    "DeviceClass",
                    "",
                )
            )

            manufacturer = str(
                driver.get(
                    "Manufacturer",
                    "",
                )
            )

            provider = str(
                driver.get(
                    "DriverProviderName",
                    "",
                )
            )

            version = str(
                driver.get(
                    "DriverVersion",
                    "",
                )
            )

            inf_name = str(
                driver.get(
                    "InfName",
                    "",
                )
            )

            is_signed = driver.get(
                "IsSigned"
            )

            if (
                class_filter
                and class_filter not in device_class_value.casefold()
            ):

                continue

            if unsigned_only and is_signed is True:

                continue

            if query_filter:

                searchable = " ".join(
                    [
                        device_name,
                        device_class_value,
                        manufacturer,
                        provider,
                        version,
                        inf_name,
                    ]
                ).casefold()

                if query_filter not in searchable:
                    continue

            filtered_drivers.append(
                {
                    "device_name": (
                        driver.get(
                            "DeviceName"
                        )
                    ),
                    "device_class": (
                        driver.get(
                            "DeviceClass"
                        )
                    ),
                    "manufacturer": (
                        driver.get(
                            "Manufacturer"
                        )
                    ),
                    "provider": (
                        driver.get(
                            "DriverProviderName"
                        )
                    ),
                    "version": (
                        driver.get(
                            "DriverVersion"
                        )
                    ),
                    "driver_date": (
                        driver.get(
                            "DriverDate"
                        )
                    ),
                    "inf_name": (
                        driver.get(
                            "InfName"
                        )
                    ),
                    "is_signed": (
                        is_signed
                    ),
                    "signer": (
                        driver.get(
                            "Signer"
                        )
                    ),
                    "device_id": (
                        driver.get(
                            "DeviceID"
                        )
                    ),
                }
            )

        truncated = (
            len(filtered_drivers)
            > MAX_DRIVERS
        )

        if truncated:

            filtered_drivers = (
                filtered_drivers[
                    :MAX_DRIVERS
                ]
            )

        unsigned_count = sum(
            1
            for driver in filtered_drivers
            if driver.get(
                "is_signed"
            ) is False
        )

        return SkillResult(
            success=True,
            message=(
                f"{len(filtered_drivers)} pilote(s) récupéré(s), "
                f"dont {unsigned_count} non signé(s)."
            ),
            data={
                "drivers": filtered_drivers,
                "count": len(
                    filtered_drivers
                ),
                "unsigned_count": (
                    unsigned_count
                ),
                "filters": {
                    "device_class": (
                        device_class.strip()
                    ),
                    "query": (
                        query.strip()
                    ),
                    "unsigned_only": (
                        unsigned_only
                    ),
                },
                "truncated": truncated,
                "max_drivers": MAX_DRIVERS,
            },
        )
