from __future__ import annotations

import json
import subprocess
from typing import Any

from atlas.system.powershell import run_fixed_powershell

from atlas.security.risk import RiskLevel
from atlas.skills.base import Skill, SkillResult


POWERSHELL_TIMEOUT_SECONDS = 20.0
MAX_DEVICES = 500

POWERSHELL_SCRIPT = (
    "Get-PnpDevice | "
    "Select-Object "
    "Status,"
    "Class,"
    "FriendlyName,"
    "InstanceId,"
    "Problem,"
    "Present | "
    "Sort-Object Class,FriendlyName | "
    "ConvertTo-Json -Depth 3 -Compress"
)


class GetComputerDevicesSkill(Skill):

    name = "computer.get_devices"

    description = (
        "Liste les périphériques Plug and Play connus de Windows "
        "avec leur classe, état et éventuels problèmes."
    )

    parameters = {
        "type": "object",
        "properties": {
            "status": {
                "type": "string",
                "default": "all",
                "description": (
                    "Filtre optionnel sur l'état, par exemple OK, Error, "
                    "Unknown ou all."
                ),
            },
            "device_class": {
                "type": "string",
                "default": "",
                "description": (
                    "Filtre optionnel sur la classe du périphérique, "
                    "par exemple Display, Net, USB ou Bluetooth."
                ),
            },
            "query": {
                "type": "string",
                "default": "",
                "description": (
                    "Filtre optionnel sur le nom ou l'identifiant du périphérique."
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
        status: str = "all",
        device_class: str = "",
        query: str = "",
        **kwargs: Any,
    ) -> SkillResult:

        for value, label in (
            (status, "état"),
            (device_class, "classe"),
            (query, "recherche"),
        ):

            if not isinstance(
                value,
                str,
            ):

                return SkillResult(
                    success=False,
                    message=(
                        f"Le filtre de {label} fourni est invalide."
                    ),
                )

        status_filter = (
            status.strip().casefold()
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
                    "La récupération des périphériques "
                    "a dépassé le délai autorisé."
                ),
            )

        except OSError as exc:

            return SkillResult(
                success=False,
                message=(
                    "Impossible de récupérer les périphériques Windows."
                ),
                data={
                    "error": str(exc),
                },
            )

        if completed.returncode != 0:

            return SkillResult(
                success=False,
                message=(
                    "Windows n'a pas pu retourner la liste des périphériques."
                ),
                data={
                    "returncode": completed.returncode,
                    "stdout": completed.stdout.strip(),
                    "stderr": completed.stderr.strip(),
                },
            )

        raw_output = completed.stdout.strip()

        if not raw_output:

            devices: list[dict[str, Any]] = []

        else:

            try:

                parsed = json.loads(
                    raw_output
                )

            except json.JSONDecodeError as exc:

                return SkillResult(
                    success=False,
                    message=(
                        "La liste des périphériques retournée par Windows "
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

                devices = [
                    parsed
                ]

            elif isinstance(
                parsed,
                list,
            ):

                devices = [
                    item
                    for item in parsed
                    if isinstance(
                        item,
                        dict,
                    )
                ]

            else:

                devices = []

        filtered_devices = []

        for device in devices:

            device_status = str(
                device.get(
                    "Status",
                    "",
                )
            ).casefold()

            device_class_value = str(
                device.get(
                    "Class",
                    "",
                )
            ).casefold()

            friendly_name = str(
                device.get(
                    "FriendlyName",
                    "",
                )
            )

            instance_id = str(
                device.get(
                    "InstanceId",
                    "",
                )
            )

            if (
                status_filter
                and status_filter != "all"
                and device_status != status_filter
            ):
                continue

            if (
                class_filter
                and class_filter not in device_class_value
            ):
                continue

            if query_filter:

                searchable = (
                    f"{friendly_name} {instance_id}"
                    .casefold()
                )

                if query_filter not in searchable:
                    continue

            filtered_devices.append(
                {
                    "status": device.get(
                        "Status"
                    ),
                    "class": device.get(
                        "Class"
                    ),
                    "friendly_name": device.get(
                        "FriendlyName"
                    ),
                    "instance_id": device.get(
                        "InstanceId"
                    ),
                    "problem": device.get(
                        "Problem"
                    ),
                    "present": device.get(
                        "Present"
                    ),
                }
            )

        truncated = (
            len(filtered_devices)
            > MAX_DEVICES
        )

        if truncated:

            filtered_devices = (
                filtered_devices[
                    :MAX_DEVICES
                ]
            )

        problem_devices = [
            device
            for device in filtered_devices
            if str(
                device.get(
                    "status",
                    "",
                )
            ).casefold()
            not in {
                "",
                "ok",
            }
            or (
                device.get(
                    "problem"
                )
                not in {
                    None,
                    0,
                    "0",
                }
            )
        ]

        return SkillResult(
            success=True,
            message=(
                f"{len(filtered_devices)} périphérique(s) Windows récupéré(s), "
                f"dont {len(problem_devices)} avec un état ou problème à vérifier."
            ),
            data={
                "devices": filtered_devices,
                "problem_devices": problem_devices,
                "count": len(
                    filtered_devices
                ),
                "problem_count": len(
                    problem_devices
                ),
                "filters": {
                    "status": status.strip(),
                    "device_class": device_class.strip(),
                    "query": query.strip(),
                },
                "truncated": truncated,
                "max_devices": MAX_DEVICES,
            },
        )
