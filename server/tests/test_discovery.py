import uuid

import pytest

from remotepad_server.discovery import (
    PROTOCOL_VERSION,
    SERVICE_TYPE,
    DiscoveryAnnouncer,
    get_or_create_host_id,
)


class FakeZeroconf:
    """Doble de Zeroconf sin sockets reales, para no depender de red en tests."""

    def __init__(self) -> None:
        self.registered: list = []
        self.unregistered: list = []
        self.closed = False

    def register_service(self, info) -> None:
        self.registered.append(info)

    def unregister_service(self, info) -> None:
        self.unregistered.append(info)

    def close(self) -> None:
        self.closed = True


@pytest.fixture
def zc() -> FakeZeroconf:
    return FakeZeroconf()


def test_start_registers_service_with_correct_txt(zc: FakeZeroconf) -> None:
    announcer = DiscoveryAnnouncer(
        name="PC de Prueba", port=52100, udp_port=52101, host_id="fixed-id", zeroconf=zc
    )
    announcer.start()

    assert len(zc.registered) == 1
    info = zc.registered[0]
    assert info.type == SERVICE_TYPE
    assert info.port == 52100
    props = info.properties
    assert props[b"v"] == PROTOCOL_VERSION.encode()
    assert props[b"udp"] == b"52101"
    assert props[b"id"] == b"fixed-id"
    assert props[b"os"] in {b"windows", b"macos", b"linux"}


def test_stop_unregisters_service(zc: FakeZeroconf) -> None:
    announcer = DiscoveryAnnouncer(name="x", port=1, udp_port=2, host_id="id", zeroconf=zc)
    announcer.start()
    announcer.stop()
    assert len(zc.unregistered) == 1


def test_stop_without_start_is_noop(zc: FakeZeroconf) -> None:
    announcer = DiscoveryAnnouncer(name="x", port=1, udp_port=2, host_id="id", zeroconf=zc)
    announcer.stop()
    assert zc.unregistered == []


def test_injected_zeroconf_is_not_closed_on_stop(zc: FakeZeroconf) -> None:
    """El Zeroconf inyectado (no creado por el announcer) no se cierra: puede ser compartido."""
    announcer = DiscoveryAnnouncer(name="x", port=1, udp_port=2, host_id="id", zeroconf=zc)
    announcer.start()
    announcer.stop()
    assert zc.closed is False


def test_context_manager_starts_and_stops(zc: FakeZeroconf) -> None:
    with DiscoveryAnnouncer(name="x", port=1, udp_port=2, host_id="id", zeroconf=zc):
        assert len(zc.registered) == 1
        assert len(zc.unregistered) == 0
    assert len(zc.unregistered) == 1


def test_host_id_persists_across_calls(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("remotepad_server.discovery.HOST_ID_FILE", tmp_path / "host_id.json")
    first = get_or_create_host_id()
    second = get_or_create_host_id()
    assert first == second
    uuid.UUID(first)  # no debe lanzar: es un uuid válido


def test_host_id_creates_missing_parent_dirs(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    target = tmp_path / "nested" / "dir" / "host_id.json"
    monkeypatch.setattr("remotepad_server.discovery.HOST_ID_FILE", target)
    host_id = get_or_create_host_id()
    assert target.exists()
    uuid.UUID(host_id)


def test_host_id_recovers_from_corrupt_file(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    target = tmp_path / "host_id.json"
    target.write_text("no es json", encoding="utf-8")
    monkeypatch.setattr("remotepad_server.discovery.HOST_ID_FILE", target)
    host_id = get_or_create_host_id()
    uuid.UUID(host_id)
