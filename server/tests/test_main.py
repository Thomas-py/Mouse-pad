import threading

from remotepad_server.main import build_parser, run


def test_parser_defaults() -> None:
    args = build_parser().parse_args([])
    assert args.port == 52100
    assert args.udp_port == 52101
    assert args.name  # default = hostname, no vacío


def test_parser_overrides() -> None:
    args = build_parser().parse_args(
        ["--name", "PC de Thomas", "--port", "9000", "--udp-port", "9001"]
    )
    assert args.name == "PC de Thomas"
    assert args.port == 9000
    assert args.udp_port == 9001


class _FakeAnnouncer:
    events: list = []

    def __init__(self, *, name: str, port: int, udp_port: int) -> None:
        self.events.append(("init", name, port, udp_port))

    def start(self) -> None:
        self.events.append(("start",))

    def stop(self) -> None:
        self.events.append(("stop",))


def test_run_starts_and_stops_announcer_around_stop_event() -> None:
    _FakeAnnouncer.events = []
    stop_event = threading.Event()
    stop_event.set()  # ya "cerrado": run() no debe bloquear

    run(
        name="PC de Prueba",
        port=1234,
        udp_port=1235,
        announcer_factory=_FakeAnnouncer,
        stop_event=stop_event,
        install_signal_handlers=False,
    )

    assert _FakeAnnouncer.events == [
        ("init", "PC de Prueba", 1234, 1235),
        ("start",),
        ("stop",),
    ]
