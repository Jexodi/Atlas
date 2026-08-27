import json
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from atlas.ipc import telemetry
from atlas.ipc.telemetry import AtlasTelemetryPublisher


@pytest.fixture
def publisher(monkeypatch):
    instance = AtlasTelemetryPublisher(Mock(), Mock(), lambda: 'C:\\Atlas')
    monkeypatch.setattr(telemetry.time, 'monotonic', lambda: 100.0)
    monkeypatch.setattr(telemetry.psutil, 'net_if_stats', lambda: {
        'Ethernet 4': SimpleNamespace(isup=True, speed=4294),
    })
    monkeypatch.setattr(telemetry.psutil, 'net_io_counters', lambda **kw: {})
    return instance


@pytest.mark.parametrize('mbps', [100, 1000, 2500, 5000, 10000, 25000, 100000])
def test_windows_speed_reaches_telemetry(publisher, monkeypatch, mbps):
    runner = Mock(return_value=SimpleNamespace(returncode=0, stdout=json.dumps({
        'interface_alias': 'Ethernet 4', 'ipv4': '192.168.1.139',
        'link_speed_bps': mbps * 1_000_000,
    })))
    monkeypatch.setattr(telemetry, 'run_fixed_powershell', runner)
    assert publisher._collect_network_snapshot()['link_speed_mbps'] == mbps
    assert publisher._collect_network_snapshot()['link_speed_mbps'] == mbps
    runner.assert_called_once()


@pytest.mark.parametrize('raw', [None, 0, -1, True, '10 Gbps', {}, []])
def test_unknown_windows_speed_never_exposes_saturation(raw):
    assert AtlasTelemetryPublisher._resolve_link_speed_mbps(
        'Ethernet 4', {'interface_alias': 'Ethernet 4', 'link_speed_bps': raw},
        SimpleNamespace(isup=True, speed=4294),
    ) is None


@pytest.mark.parametrize('speed, expected', [(0, None), (-1, None), (1000, 1000), (2500, 2500), (10000, 10000)])
def test_psutil_fallback(speed, expected):
    assert AtlasTelemetryPublisher._resolve_link_speed_mbps(
        'Ethernet 4', {}, SimpleNamespace(isup=True, speed=speed),
    ) == expected


@pytest.mark.parametrize('stats', [None, SimpleNamespace(isup=False, speed=10000)])
def test_disconnected_interface_has_no_speed(stats):
    assert AtlasTelemetryPublisher._resolve_link_speed_mbps(
        'Ethernet 4', {'interface_alias': 'Ethernet 4', 'link_speed_bps': 10_000_000_000}, stats,
    ) is None


def test_different_adapter_does_not_inherit_cached_speed():
    assert AtlasTelemetryPublisher._resolve_link_speed_mbps(
        'Ethernet', {'interface_alias': 'Ethernet 4', 'link_speed_bps': 10_000_000_000},
        SimpleNamespace(isup=True, speed=1000),
    ) == 1000


@pytest.mark.parametrize('failure', ['exit', 'empty', 'json', 'timeout'])
def test_expired_speed_is_discarded_on_refresh_failure(publisher, monkeypatch, failure):
    publisher._network_config = {
        'interface_alias': 'Ethernet 4', 'ipv4': '192.168.1.139',
        'link_speed_bps': 10_000_000_000,
    }
    runner = Mock(return_value=SimpleNamespace(
        returncode=1 if failure == 'exit' else 0,
        stdout='broken' if failure == 'json' else '',
    ))
    if failure == 'timeout':
        runner.side_effect = TimeoutError()
    monkeypatch.setattr(telemetry, 'run_fixed_powershell', runner)
    assert publisher._collect_network_snapshot()['link_speed_mbps'] is None


def test_rates_remain_bytes_per_second(publisher, monkeypatch):
    counters = iter([
        SimpleNamespace(bytes_recv=100, bytes_sent=200),
        SimpleNamespace(bytes_recv=1750000100, bytes_sent=250000200),
    ])
    clock = iter([100.0, 102.0])
    monkeypatch.setattr(telemetry.time, 'monotonic', lambda: next(clock))
    monkeypatch.setattr(telemetry.psutil, 'net_io_counters', lambda **kw: {'Ethernet 4': next(counters)})
    assert publisher._calculate_network_rates('Ethernet 4') == (0.0, 0.0)
    assert publisher._calculate_network_rates('Ethernet 4') == (875000000.0, 125000000.0)
