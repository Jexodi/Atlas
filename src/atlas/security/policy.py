from atlas.security.permissions import (
    PermissionDecision,
    PermissionMode,
)
from atlas.security.risk import RiskLevel


class PermissionEngine:

    def evaluate(
        self,
        risk_level: RiskLevel,
        permission_mode: PermissionMode,
    ) -> PermissionDecision:

        if permission_mode == PermissionMode.RESTRICTED:
            return self._restricted_policy(risk_level)

        if permission_mode == PermissionMode.NORMAL:
            return self._normal_policy(risk_level)

        if permission_mode == PermissionMode.ADVANCED:
            return self._advanced_policy(risk_level)

        if permission_mode == PermissionMode.ADMINISTRATOR:
            return self._administrator_policy(risk_level)

        if permission_mode == PermissionMode.JARVIS:
            return self._jarvis_policy(risk_level)

        return PermissionDecision(
            allowed=False,
            confirmation_required=False,
            reason="Mode de permission inconnu.",
        )

    def _restricted_policy(
        self,
        risk_level: RiskLevel,
    ) -> PermissionDecision:

        if risk_level <= RiskLevel.SAFE:
            return PermissionDecision(
                allowed=True,
                confirmation_required=False,
                reason="Action autorisée en mode restreint.",
            )

        return PermissionDecision(
            allowed=False,
            confirmation_required=False,
            reason="Action interdite en mode restreint.",
        )

    def _normal_policy(
        self,
        risk_level: RiskLevel,
    ) -> PermissionDecision:

        if risk_level <= RiskLevel.SAFE:
            return PermissionDecision(
                allowed=True,
                confirmation_required=False,
                reason="Action sûre autorisée.",
            )

        if risk_level == RiskLevel.LOCAL_MODIFICATION:
            return PermissionDecision(
                allowed=True,
                confirmation_required=True,
                reason="Modification locale nécessitant confirmation.",
            )

        return PermissionDecision(
            allowed=False,
            confirmation_required=False,
            reason="Action trop sensible pour le mode normal.",
        )

    def _advanced_policy(
        self,
        risk_level: RiskLevel,
    ) -> PermissionDecision:

        if risk_level <= RiskLevel.LOCAL_MODIFICATION:
            return PermissionDecision(
                allowed=True,
                confirmation_required=False,
                reason="Action autorisée en mode avancé.",
            )

        if risk_level == RiskLevel.ADMIN:
            return PermissionDecision(
                allowed=True,
                confirmation_required=True,
                reason="Action administrateur nécessitant confirmation.",
            )

        return PermissionDecision(
            allowed=False,
            confirmation_required=False,
            reason="Action critique interdite en mode avancé.",
        )

    def _administrator_policy(
        self,
        risk_level: RiskLevel,
    ) -> PermissionDecision:

        if risk_level <= RiskLevel.ADMIN:
            return PermissionDecision(
                allowed=True,
                confirmation_required=False,
                reason="Action autorisée en mode administrateur.",
            )

        return PermissionDecision(
            allowed=True,
            confirmation_required=True,
            reason="Action critique nécessitant confirmation.",
        )

    def _jarvis_policy(
        self,
        risk_level: RiskLevel,
    ) -> PermissionDecision:

        if risk_level < RiskLevel.CRITICAL:
            return PermissionDecision(
                allowed=True,
                confirmation_required=False,
                reason="Action autorisée en mode JARVIS.",
            )

        return PermissionDecision(
            allowed=True,
            confirmation_required=True,
            reason="Action critique protégée par confirmation.",
        )