import pytest

from atlas.security.permissions import PermissionMode
from atlas.security.policy import PermissionEngine
from atlas.security.risk import RiskLevel


@pytest.fixture
def engine():
    return PermissionEngine()


def test_restricted_allows_read_only(engine):

    result = engine.evaluate(
        RiskLevel.READ_ONLY,
        PermissionMode.RESTRICTED,
    )

    assert result.allowed is True
    assert result.confirmation_required is False


def test_restricted_refuses_local_modification(engine):

    result = engine.evaluate(
        RiskLevel.LOCAL_MODIFICATION,
        PermissionMode.RESTRICTED,
    )

    assert result.allowed is False


def test_normal_requires_confirmation_for_local_modification(engine):

    result = engine.evaluate(
        RiskLevel.LOCAL_MODIFICATION,
        PermissionMode.NORMAL,
    )

    assert result.allowed is True
    assert result.confirmation_required is True


def test_normal_refuses_admin(engine):

    result = engine.evaluate(
        RiskLevel.ADMIN,
        PermissionMode.NORMAL,
    )

    assert result.allowed is False


def test_advanced_requires_confirmation_for_admin(engine):

    result = engine.evaluate(
        RiskLevel.ADMIN,
        PermissionMode.ADVANCED,
    )

    assert result.allowed is True
    assert result.confirmation_required is True


def test_administrator_requires_confirmation_for_critical(engine):

    result = engine.evaluate(
        RiskLevel.CRITICAL,
        PermissionMode.ADMINISTRATOR,
    )

    assert result.allowed is True
    assert result.confirmation_required is True


def test_jarvis_allows_admin_without_confirmation(engine):

    result = engine.evaluate(
        RiskLevel.ADMIN,
        PermissionMode.JARVIS,
    )

    assert result.allowed is True
    assert result.confirmation_required is False


def test_jarvis_still_protects_critical_actions(engine):

    result = engine.evaluate(
        RiskLevel.CRITICAL,
        PermissionMode.JARVIS,
    )

    assert result.allowed is True
    assert result.confirmation_required is True