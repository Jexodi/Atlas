import logging

import pytest

from atlas.core.event_bus import EventBus
from atlas.security.permissions import PermissionMode
from atlas.security.policy import PermissionEngine
from atlas.security.risk import RiskLevel
from atlas.skills.base import (
    Skill,
    SkillResult,
    SkillValidationError,
)
from atlas.skills.manager import SkillManager
from atlas.skills.registry import SkillRegistry

class DummySkill(Skill):

    name = "test.dummy"

    description = "Skill utilisé uniquement par pytest."

    risk_level = RiskLevel.SAFE

    required_permission = None

    requires_service = False

    def validate(
        self,
        **kwargs,
    ) -> None:

        value = kwargs.get("value")

        if value is None:
            raise SkillValidationError(
                "Le paramètre value est obligatoire."
            )

    def execute(
        self,
        **kwargs,
    ) -> SkillResult:

        return SkillResult(
            success=True,
            message="Exécution réussie.",
            data={
                "value": kwargs["value"],
            },
        )

    @pytest.fixture
    def skill_manager():

        registry = SkillRegistry()

        registry.register(
            DummySkill()
        )

        return SkillManager(
            registry=registry,
            permission_engine=PermissionEngine(),
            event_bus=EventBus(),
            permission_mode=PermissionMode.NORMAL,
            logger=logging.getLogger(
                "atlas.tests"
            ),
        )

    def test_skill_executes_successfully(
        skill_manager,
    ):

        result = skill_manager.execute(
            "test.dummy",
            value="SIDERON",
        )

        assert result.success is True

        assert result.skill_name == "test.dummy"

        assert result.data == {
            "value": "SIDERON",
        }

    def test_unknown_skill_is_rejected(
        skill_manager,
    ):

        result = skill_manager.execute(
            "test.unknown",
        )

        assert result.success is False

    def test_invalid_parameters_are_rejected(
        skill_manager,
    ):

        result = skill_manager.execute(
            "test.dummy",
        )

        assert result.success is False

        assert "Paramètres invalides" in result.message

class ModificationSkill(Skill):

    name = "test.modification"

    description = "Skill de modification."

    risk_level = RiskLevel.LOCAL_MODIFICATION

    required_permission = None

    requires_service = False

    def execute(
        self,
        **kwargs,
    ) -> SkillResult:

        return SkillResult(
            success=True,
            message="Modification effectuée.",
        )

    def test_confirmation_is_required():

        registry = SkillRegistry()

        registry.register(
            ModificationSkill()
        )

        manager = SkillManager(
            registry=registry,
            permission_engine=PermissionEngine(),
            event_bus=EventBus(),
            permission_mode=PermissionMode.NORMAL,
            logger=logging.getLogger(
                "atlas.tests"
            ),
        )

        result = manager.execute(
            "test.modification"
        )

        assert result.success is False
        assert result.confirmation_required is True

    def test_confirmed_skill_executes():

        registry = SkillRegistry()

        registry.register(
            ModificationSkill()
        )

        manager = SkillManager(
            registry=registry,
            permission_engine=PermissionEngine(),
            event_bus=EventBus(),
            permission_mode=PermissionMode.NORMAL,
            logger=logging.getLogger(
                "atlas.tests"
            ),
        )

        result = manager.execute(
            "test.modification",
            confirmed=True,
        )

        assert result.success is True

    def test_skill_completed_event_is_published():

        registry = SkillRegistry()

        registry.register(
            DummySkill()
        )

        event_bus = EventBus()

        events = []

        event_bus.subscribe(
            "skill.completed",
            lambda payload: events.append(
                payload
            ),
        )

        manager = SkillManager(
            registry=registry,
            permission_engine=PermissionEngine(),
            event_bus=event_bus,
            permission_mode=PermissionMode.NORMAL,
            logger=logging.getLogger(
                "atlas.tests"
            ),
        )

        manager.execute(
            "test.dummy",
            value="SIDERON",
        )

        assert len(events) == 1

        assert events[0]["skill"] == "test.dummy"



        