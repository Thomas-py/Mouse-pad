import asyncio
from unittest.mock import MagicMock, call

import pytest

from remotepad_server import session as session_mod
from remotepad_server.motion_server import MotionServer, start_motion_server
from remotepad_server.protocol import EventKind, MotionEvent, encode_datagram


class _FakeSessionProvider:
    def __init__(self, session: session_mod.ActiveSession | None) -> None:
        self.active_session = session


TOKEN = bytes(range(32))
CLIENT_ID = "test-client"


def _make_session(**overrides) -> session_mod.ActiveSession:
    defaults = dict(session_id="s1", client_id=CLIENT_ID, token=TOKEN)
    defaults.update(overrides)
    return session_mod.ActiveSession(**defaults)


@pytest.fixture
def injector() -> MagicMock:
    return MagicMock()


def test_valid_move_packet_calls_injector(injector: MagicMock) -> None:
    session = _make_session()
    server = MotionServer(session_provider=_FakeSessionProvider(session), injector=injector)

    datagram = encode_datagram(
        client_id=CLIENT_ID, seq=1, token=TOKEN, events=[MotionEvent(EventKind.MOVE, 3, -2)]
    )
    server.datagram_received(datagram, ("127.0.0.1", 12345))

    injector.move.assert_called_once_with(3, -2)
    assert server.dropped_count == 0


def test_scroll_with_natural_scroll_on_inverts_dy(injector: MagicMock) -> None:
    """F-08: 'cruda desde el cliente; el servidor invierte si natural_scroll está activo'."""
    session = _make_session(natural_scroll=True)
    server = MotionServer(session_provider=_FakeSessionProvider(session), injector=injector)

    datagram = encode_datagram(
        client_id=CLIENT_ID, seq=1, token=TOKEN, events=[MotionEvent(EventKind.SCROLL, 0, -5)]
    )
    server.datagram_received(datagram, ("127.0.0.1", 12345))

    injector.scroll.assert_called_once_with(0, 5)


def test_scroll_with_natural_scroll_off_passes_through_raw(injector: MagicMock) -> None:
    session = _make_session(natural_scroll=False)
    server = MotionServer(session_provider=_FakeSessionProvider(session), injector=injector)

    datagram = encode_datagram(
        client_id=CLIENT_ID, seq=1, token=TOKEN, events=[MotionEvent(EventKind.SCROLL, 0, -5)]
    )
    server.datagram_received(datagram, ("127.0.0.1", 12345))

    injector.scroll.assert_called_once_with(0, -5)


def test_scroll_inversion_only_affects_dy_not_dx(injector: MagicMock) -> None:
    session = _make_session(natural_scroll=True)
    server = MotionServer(session_provider=_FakeSessionProvider(session), injector=injector)

    datagram = encode_datagram(
        client_id=CLIENT_ID, seq=1, token=TOKEN, events=[MotionEvent(EventKind.SCROLL, 7, 3)]
    )
    server.datagram_received(datagram, ("127.0.0.1", 12345))

    injector.scroll.assert_called_once_with(7, -3)


def test_cfg_change_affects_subsequent_scroll_events(injector: MagicMock) -> None:
    """El toggle de natural_scroll (mensaje `cfg`, S-07) se lee en vivo por cada paquete."""
    session = _make_session(natural_scroll=True)
    server = MotionServer(session_provider=_FakeSessionProvider(session), injector=injector)

    first = encode_datagram(
        client_id=CLIENT_ID, seq=1, token=TOKEN, events=[MotionEvent(EventKind.SCROLL, 0, -5)]
    )
    server.datagram_received(first, ("127.0.0.1", 1))
    injector.scroll.assert_called_once_with(0, 5)

    session.natural_scroll = False  # como si hubiera llegado un `cfg` por TCP
    second = encode_datagram(
        client_id=CLIENT_ID, seq=2, token=TOKEN, events=[MotionEvent(EventKind.SCROLL, 0, -5)]
    )
    server.datagram_received(second, ("127.0.0.1", 1))
    assert injector.scroll.call_args_list == [call(0, 5), call(0, -5)]


def test_multiple_events_applied_in_order(injector: MagicMock) -> None:
    session = _make_session(natural_scroll=False)  # sin inversión, para no acoplar este test a F-08
    server = MotionServer(session_provider=_FakeSessionProvider(session), injector=injector)

    events = [
        MotionEvent(EventKind.MOVE, 1, 1),
        MotionEvent(EventKind.MOVE, 2, 2),
        MotionEvent(EventKind.SCROLL, 0, 1),
    ]
    datagram = encode_datagram(client_id=CLIENT_ID, seq=1, token=TOKEN, events=events)
    server.datagram_received(datagram, ("127.0.0.1", 1))

    assert injector.move.call_args_list == [call(1, 1), call(2, 2)]
    injector.scroll.assert_called_once_with(0, 1)


def test_no_active_session_drops_packet(injector: MagicMock) -> None:
    server = MotionServer(session_provider=_FakeSessionProvider(None), injector=injector)
    datagram = encode_datagram(
        client_id=CLIENT_ID, seq=1, token=TOKEN, events=[MotionEvent(EventKind.MOVE, 1, 1)]
    )
    server.datagram_received(datagram, ("127.0.0.1", 1))
    injector.move.assert_not_called()
    assert server.dropped_count == 1


def test_bad_signature_drops_packet_without_touching_session(injector: MagicMock) -> None:
    session = _make_session()
    server = MotionServer(session_provider=_FakeSessionProvider(session), injector=injector)

    wrong_token = bytes(range(32, 64))
    datagram = encode_datagram(
        client_id=CLIENT_ID, seq=1, token=wrong_token, events=[MotionEvent(EventKind.MOVE, 1, 1)]
    )
    server.datagram_received(datagram, ("127.0.0.1", 1))

    injector.move.assert_not_called()
    assert server.dropped_count == 1
    assert session.last_udp_seq is None  # no se tocó el anti-replay


def test_client_hash_mismatch_drops_packet(injector: MagicMock) -> None:
    session = _make_session(client_id="otro-cliente")
    server = MotionServer(session_provider=_FakeSessionProvider(session), injector=injector)

    datagram = encode_datagram(
        client_id=CLIENT_ID, seq=1, token=TOKEN, events=[MotionEvent(EventKind.MOVE, 1, 1)]
    )
    server.datagram_received(datagram, ("127.0.0.1", 1))

    injector.move.assert_not_called()


def test_malformed_datagram_is_dropped_not_raised(injector: MagicMock) -> None:
    session = _make_session()
    server = MotionServer(session_provider=_FakeSessionProvider(session), injector=injector)
    server.datagram_received(b"basura", ("127.0.0.1", 1))
    injector.move.assert_not_called()
    assert server.dropped_count == 1


def test_replayed_seq_is_dropped(injector: MagicMock) -> None:
    session = _make_session()
    server = MotionServer(session_provider=_FakeSessionProvider(session), injector=injector)

    datagram = encode_datagram(
        client_id=CLIENT_ID, seq=5, token=TOKEN, events=[MotionEvent(EventKind.MOVE, 1, 1)]
    )
    server.datagram_received(datagram, ("127.0.0.1", 1))
    assert injector.move.call_count == 1

    replay = encode_datagram(
        client_id=CLIENT_ID, seq=5, token=TOKEN, events=[MotionEvent(EventKind.MOVE, 9, 9)]
    )
    server.datagram_received(replay, ("127.0.0.1", 1))
    assert injector.move.call_count == 1  # no se aplicó el replay

    older = encode_datagram(
        client_id=CLIENT_ID, seq=3, token=TOKEN, events=[MotionEvent(EventKind.MOVE, 9, 9)]
    )
    server.datagram_received(older, ("127.0.0.1", 1))
    assert injector.move.call_count == 1


def test_seq_wraparound_is_accepted(injector: MagicMock) -> None:
    session = _make_session(last_udp_seq=4_000_000_000)
    server = MotionServer(session_provider=_FakeSessionProvider(session), injector=injector)

    datagram = encode_datagram(
        client_id=CLIENT_ID, seq=10, token=TOKEN, events=[MotionEvent(EventKind.MOVE, 1, 1)]
    )
    server.datagram_received(datagram, ("127.0.0.1", 1))

    injector.move.assert_called_once_with(1, 1)
    assert session.last_udp_seq == 10


def test_seq_small_backward_jump_without_wrap_is_rejected(injector: MagicMock) -> None:
    session = _make_session(last_udp_seq=100)
    server = MotionServer(session_provider=_FakeSessionProvider(session), injector=injector)

    datagram = encode_datagram(
        client_id=CLIENT_ID, seq=50, token=TOKEN, events=[MotionEvent(EventKind.MOVE, 1, 1)]
    )
    server.datagram_received(datagram, ("127.0.0.1", 1))

    injector.move.assert_not_called()


async def test_real_udp_socket_end_to_end(injector: MagicMock) -> None:
    session = _make_session()
    provider = _FakeSessionProvider(session)
    transport, protocol = await start_motion_server(
        host="127.0.0.1", port=0, session_provider=provider, injector=injector
    )
    try:
        port = transport.get_extra_info("sockname")[1]
        loop = asyncio.get_running_loop()
        send_transport, _ = await loop.create_datagram_endpoint(
            asyncio.DatagramProtocol, remote_addr=("127.0.0.1", port)
        )
        try:
            datagram = encode_datagram(
                client_id=CLIENT_ID, seq=1, token=TOKEN, events=[MotionEvent(EventKind.MOVE, 7, 7)]
            )
            send_transport.sendto(datagram)
            await asyncio.sleep(0.2)
            injector.move.assert_called_once_with(7, 7)
        finally:
            send_transport.close()
    finally:
        transport.close()
