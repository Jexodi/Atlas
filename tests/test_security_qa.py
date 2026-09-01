from __future__ import annotations

import subprocess
from unittest.mock import patch

import pytest

from atlas.ai.tool_router import RealtimeToolRouter
from atlas.core.event_bus import EventBus
from atlas.security.permissions import PermissionMode
from atlas.security.policy import PermissionEngine
from atlas.security.risk import RiskLevel
from atlas.skills.automation.cancel_task import CancelAutomationTaskSkill
from atlas.skills.automation.create_reminder import CreateReminderSkill
from atlas.skills.automation.list_tasks import ListAutomationTasksSkill
from atlas.skills.base import Skill, SkillResult, SkillValidationError
from atlas.skills.manager import SkillManager
from atlas.skills.registry import SkillRegistry
from atlas.skills.windows.open_app import OpenAppSkill


class LoggerStub:
    def debug(self, *args, **kwargs):
        pass

    def info(self, *args, **kwargs):
        pass

    def warning(self, *args, **kwargs):
        pass

    def exception(self, *args, **kwargs):
        pass


class CriticalSkill(Skill):
    name = "test.critical"
    description = "Action critique de test."
    risk_level = RiskLevel.CRITICAL
    parameters = {
        "type": "object",
        "properties": {},
        "required": [],
        "additionalProperties": False,
    }

    def __init__(self):
        self.executions = 0

    def execute(self, **kwargs):
        self.executions += 1
        return SkillResult(success=True, message="ok")


class AutomationStub:
    STATUSES = {"pending", "completed", "cancelled"}
    MAX_DELAY_SECONDS = 365 * 24 * 60 * 60

    @staticmethod
    def validate_message(value):
        return value

    @staticmethod
    def validate_delay(value):
        return value

    @staticmethod
    def parse_run_at(value):
        return value

    @staticmethod
    def validate_task_id(value):
        return value


def test_open_app_rejects_shell_command_injection():
    skill = OpenAppSkill()

    with pytest.raises(SkillValidationError):
        skill.validate(app="notepad.exe & whoami")

    with pytest.raises(SkillValidationError):
        skill.validate(app="powershell.exe -Command Get-Process")


def test_open_app_uses_shell_false_and_resolved_executable():
    skill = OpenAppSkill()

    with (
        patch("atlas.skills.windows.open_app.shutil.which", return_value=r"C:\\Windows\\notepad.exe"),
        patch("atlas.skills.windows.open_app.subprocess.Popen") as popen,
    ):
        skill.validate(app="notepad")
        result = skill.execute(app="notepad")

    assert result.success is True
    popen.assert_called_once_with([r"C:\\Windows\\notepad.exe"], shell=False)


def test_automation_skills_cannot_request_arbitrary_commands():
    automation = AutomationStub()
    skills = [
        CreateReminderSkill(automation),
        ListAutomationTasksSkill(automation),
        CancelAutomationTaskSkill(automation),
    ]
    forbidden_fields = {"action", "command", "powershell", "script", "executable"}

    for skill in skills:
        assert skill.risk_level <= RiskLevel.SAFE
        assert skill.requires_service is False
        properties = set(skill.parameters.get("properties", {}))
        assert forbidden_fields.isdisjoint(properties)


def test_critical_tool_confirmation_is_one_time():
    registry = SkillRegistry()
    skill = CriticalSkill()
    registry.register(skill)

    manager = SkillManager(
        registry=registry,
        permission_engine=PermissionEngine(),
        event_bus=EventBus(),
        permission_mode=PermissionMode.JARVIS,
        logger=LoggerStub(),
    )
    router = RealtimeToolRouter(registry, manager, LoggerStub())
    router.build_tools()

    first = router.execute("test_critical", {})
    confirmation_id = first["data"]["confirmation_id"]

    assert first["confirmation_required"] is True
    assert skill.executions == 0

    confirmed = router.execute(
        "atlas_confirm_action",
        {"confirmation_id": confirmation_id},
    )
    replay = router.execute(
        "atlas_confirm_action",
        {"confirmation_id": confirmation_id},
    )

    assert confirmed["success"] is True
    assert skill.executions == 1
    assert replay["success"] is False
    assert skill.executions == 1
