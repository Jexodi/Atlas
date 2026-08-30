from __future__ import annotations

import json
import subprocess
from typing import Any

from atlas.system.powershell import run_fixed_powershell

from atlas.security.risk import RiskLevel
from atlas.skills.base import Skill, SkillResult


POWERSHELL_TIMEOUT_SECONDS = 12.0
MAX_RECORDS = 500

POWERSHELL_SCRIPT = (
    "Get-DnsClientCache | "
    "Select-Object "
    "Entry,Name,Data,Type,Status,Section,TimeToLive | "
    "Sort-Object Entry,Type | "
    "ConvertTo-Json -Depth 3 -Compress"
)


class GetDnsCacheNetworkSkill(Skill):

    name = "network.get_dns_cache"

    description = (
        "Récupère le cache DNS local de Windows avec les noms, "
        "données, types d'enregistrements et durées de vie."
    )

    parameters = {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": (
                    "Filtre optionnel appliqué aux noms et aux données DNS."
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
        query: str = "",
        **kwargs: Any,
    ) -> SkillResult:

        if not isinstance(
            query,
            str,
        ):

            return SkillResult(
                success=False,
                message=(
                    "Le filtre DNS fourni est invalide."
                ),
            )

        normalized_query = (
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
                    "La récupération du cache DNS "
                    "a dépassé le délai autorisé."
                ),
            )

        except OSError as exc:

            return SkillResult(
                success=False,
                message=(
                    "Impossible de récupérer le cache DNS."
                ),
                data={
                    "error": str(exc),
                },
            )

        if completed.returncode != 0:

            return SkillResult(
                success=False,
                message=(
                    "Windows n'a pas pu retourner le cache DNS."
                ),
                data={
                    "returncode": completed.returncode,
                    "stdout": completed.stdout.strip(),
                    "stderr": completed.stderr.strip(),
                },
            )

        raw_output = completed.stdout.strip()

        if not raw_output:

            records: list[dict[str, Any]] = []

        else:

            try:

                parsed = json.loads(
                    raw_output
                )

            except json.JSONDecodeError as exc:

                return SkillResult(
                    success=False,
                    message=(
                        "Le cache DNS retourné par Windows "
                        "n'a pas pu être interprété."
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

                records = [
                    parsed
                ]

            elif isinstance(
                parsed,
                list,
            ):

                records = [
                    item
                    for item in parsed
                    if isinstance(
                        item,
                        dict,
                    )
                ]

            else:

                records = []

        if normalized_query:

            filtered_records = []

            for record in records:

                searchable_values = [
                    record.get("Entry"),
                    record.get("Name"),
                    record.get("Data"),
                    record.get("Type"),
                ]

                searchable_text = " ".join(
                    str(value)
                    for value in searchable_values
                    if value is not None
                ).casefold()

                if normalized_query in searchable_text:

                    filtered_records.append(
                        record
                    )

            records = filtered_records

        truncated = (
            len(records)
            > MAX_RECORDS
        )

        if truncated:

            records = records[
                :MAX_RECORDS
            ]

        type_counts: dict[str, int] = {}

        for record in records:

            record_type = str(
                record.get(
                    "Type",
                    "UNKNOWN",
                )
            )

            type_counts[
                record_type
            ] = (
                type_counts.get(
                    record_type,
                    0,
                )
                + 1
            )

        if normalized_query:

            message = (
                f"{len(records)} enregistrement(s) DNS "
                f"correspondant au filtre '{query.strip()}' récupéré(s)."
            )

        else:

            message = (
                f"{len(records)} enregistrement(s) du cache DNS "
                "récupéré(s)."
            )

        return SkillResult(
            success=True,
            message=message,
            data={
                "records": records,
                "count": len(records),
                "type_counts": type_counts,
                "query": query.strip(),
                "truncated": truncated,
                "max_records": MAX_RECORDS,
            },
        )
