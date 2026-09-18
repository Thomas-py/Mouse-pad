import asyncio
from unittest.mock import MagicMock

from remotepad_server.main import build_parser, run_async


def test_parser_defaults() -> None:
    args = build_parser().parse_args([])
    assert args.port == 52100
    assert args.udp_port == 52101
    assert args.log_level == "INFO"
    assert args.name  # default = hostname, no vacío


def test_parser_overrides() -> None:
    args = build_parser().parse_args(
        ["--name", "PC de Thomas", "--port", "9000", "--udp-port", "9001", "--log-level", "DEBUG"]
    )
    assert args.name == "PC de Thomas"
    assert args.port == 9000
    assert args.udp_port == 9001
    assert args.log_level == "DEBUG"


def test_parser_rejects_invalid_log_level() -> None:
    import pytest

    with pytest.raises(SystemExit):
        build_parser().parse_args(["--log-level", "NOPE"])


class _FakeAnnouncer:
    events: list = []

    def __init__(self, *, name: str, port: int, udp_port: int) -> None:
        self.events.append(("init", name, port, udp_port))

    def start(self) -> None:
        self.events.append(("start",))

    def stop(self) -> None:
        self.events.append(("stop",))


async def test_run_async_wires_control_and_motion_servers_for_real(tmp_path, monkeypatch) -> None:
    """Usa el ControlServer y el motion_server REALES en loopback (puerto 0);
    solo se mockean el injector (no tocar el mouse real) y el announcer (no
    tocar mDNS/red real). TokenStore y el host_id se redirigen a tmp_path
    para no escribir en el ~/.remotepad/ real de quien corre los tests."""
    monkeypatch.setattr("remotepad_server.main.TokenStore", lambda: MagicMock())
    monkeypatch.setattr("remotepad_server.discovery.HOST_ID_FILE", tmp_path / "host_id.json")

    _FakeAnnouncer.events = []
    fake_injector = MagicMock()
    args = build_parser().parse_args(["--port", "0", "--udp-port", "0"])

    stop_event = asyncio.Event()
    stop_event.set()  # que no bloquee: probamos arranque + apagado prolijo

    await run_async(
        args,
        injector_factory=lambda: fake_injector,
        announcer_factory=_FakeAnnouncer,
        stop_event=stop_event,
        install_signal_handlers=False,
    )

    assert _FakeAnnouncer.events[0][0] == "init"
    assert ("start",) in _FakeAnnouncer.events
    assert ("stop",) in _FakeAnnouncer.events
    # el "stop" del announcer tiene que pasar ANTES que termine run_async,
    # es decir ya está en la lista para cuando llegamos acá — alcanza con
    # que la corrutina haya terminado sin excepciones: confirma que
    # ControlServer.start()/close() y start_motion_server()/transport.close()
    # funcionaron de verdad sobre sockets reales.


async def test_run_async_closes_cleanly_even_with_zero_ports(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("remotepad_server.main.TokenStore", lambda: MagicMock())
    monkeypatch.chdir(tmp_path)

    args = build_parser().parse_args(["--port", "0", "--udp-port", "0"])
    stop_event = asyncio.Event()
    stop_event.set()

    # No debe lanzar.
    await run_async(
        args,
        injector_factory=lambda: MagicMock(),
        announcer_factory=_FakeAnnouncer,
        stop_event=stop_event,
        install_signal_handlers=False,
    )
