import pytest

from remotepad_server.protocol import (
    Auth,
    AuthOk,
    Btn,
    Cfg,
    ErrorMsg,
    EventKind,
    Hello,
    HelloOk,
    MAX_TCP_MESSAGE_BYTES,
    MotionEvent,
    PairAnswer,
    PairChallenge,
    PairOk,
    PairStart,
    Ping,
    Pong,
    ProtocolError,
    client_hash,
    decode_datagram,
    decode_message,
    encode_datagram,
    encode_message,
)

# ---------------------------------------------------------------------------
# TCP / JSON — parse de cada tipo de mensaje
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "raw, expected_type",
    [
        ('{"t":"hello","id":"a1","v":1,"client_id":"iphone-1","nonce":"ab12"}', Hello),
        ('{"t":"hello_ok","re":"a1","nonce":"cd34","server_name":"PC de Thomas"}', HelloOk),
        ('{"t":"error","re":"a1","code":"unpaired"}', ErrorMsg),
        ('{"t":"auth","id":"a2","client_id":"iphone-1","sig":"deadbeef"}', Auth),
        ('{"t":"auth_ok","re":"a2","session":"sess-1"}', AuthOk),
        (
            '{"t":"pair_start","id":"p1","v":1,"client_id":"iphone-1",'
            '"client_name":"iPhone de Thomas","nonce":"ab12"}',
            PairStart,
        ),
        ('{"t":"pair_challenge","re":"p1","nonce":"ef56","expires_in":60}', PairChallenge),
        ('{"t":"pair_answer","id":"p2","proof":"feed"}', PairAnswer),
        ('{"t":"pair_ok","re":"p2"}', PairOk),
        (
            '{"t":"btn","id":"b1","sig":"beef","button":"left","action":"click","count":1}',
            Btn,
        ),
        ('{"t":"cfg","id":"c1","sig":"beef","natural_scroll":true}', Cfg),
        ('{"t":"ping","id":"k1","sig":"beef","ts":1234}', Ping),
        ('{"t":"pong","re":"k1","ts":1234}', Pong),
    ],
)
def test_decode_each_message_type(raw: str, expected_type: type) -> None:
    msg = decode_message(raw)
    assert isinstance(msg, expected_type)


def test_decode_strips_trailing_newline() -> None:
    msg = decode_message('{"t":"ping","id":"k1","sig":"beef","ts":1}\n')
    assert isinstance(msg, Ping)


def test_double_click_uses_count_2() -> None:
    msg = decode_message(
        '{"t":"btn","id":"b1","sig":"beef","button":"left","action":"click","count":2}'
    )
    assert isinstance(msg, Btn)
    assert msg.count == 2


def test_encode_roundtrip() -> None:
    original = Ping(t="ping", id="k1", sig="beef", ts=999)
    wire = encode_message(original)
    assert wire.endswith(b"\n")
    decoded = decode_message(wire)
    assert decoded == original


# ---------------------------------------------------------------------------
# TCP / JSON — rechazo de entradas inválidas
# ---------------------------------------------------------------------------


def test_rejects_invalid_json() -> None:
    with pytest.raises(ProtocolError):
        decode_message("no es json")


def test_rejects_invalid_utf8_bytes() -> None:
    with pytest.raises(ProtocolError):
        decode_message(b"\xff\xfe\x00\x01 basura binaria")


def test_rejects_unknown_type() -> None:
    with pytest.raises(ProtocolError):
        decode_message('{"t":"nope","id":"a1"}')


def test_rejects_missing_required_field() -> None:
    with pytest.raises(ProtocolError):
        decode_message('{"t":"hello","id":"a1","v":1,"client_id":"iphone-1"}')


def test_rejects_unknown_extra_field() -> None:
    with pytest.raises(ProtocolError):
        decode_message(
            '{"t":"ping","id":"k1","sig":"beef","ts":1,"unexpected":true}'
        )


def test_rejects_oversized_message() -> None:
    huge_id = "x" * MAX_TCP_MESSAGE_BYTES
    raw = f'{{"t":"ping","id":"k1","sig":"beef","ts":1,"pad":"{huge_id}"}}'
    with pytest.raises(ProtocolError):
        decode_message(raw)


# ---------------------------------------------------------------------------
# UDP / binario — round-trip
# ---------------------------------------------------------------------------


def test_udp_roundtrip_single_move_event() -> None:
    token = bytes(range(32))
    events = [MotionEvent(kind=EventKind.MOVE, dx=3, dy=-2)]

    datagram = encode_datagram(client_id="test-client", seq=7, token=token, events=events)
    decoded = decode_datagram(datagram)

    assert decoded.seq == 7
    assert decoded.client_hash == client_hash("test-client")
    assert decoded.events == tuple(events)
    assert decoded.verify(token) is True


def test_udp_roundtrip_multiple_events() -> None:
    token = b"\x01" * 32
    events = [
        MotionEvent(kind=EventKind.MOVE, dx=-100, dy=32000),
        MotionEvent(kind=EventKind.SCROLL, dx=0, dy=-5),
        MotionEvent(kind=EventKind.MOVE, dx=1, dy=1),
    ]

    datagram = encode_datagram(client_id="iphone-abc", seq=4294967295, token=token, events=events)
    decoded = decode_datagram(datagram)

    assert decoded.seq == 4294967295
    assert decoded.events == tuple(events)
    assert decoded.verify(token) is True


def test_udp_verify_fails_with_wrong_token() -> None:
    token = bytes(range(32))
    other_token = bytes(range(32, 64))
    datagram = encode_datagram(
        client_id="test-client", seq=1, token=token, events=[MotionEvent(EventKind.MOVE, 1, 1)]
    )
    decoded = decode_datagram(datagram)
    assert decoded.verify(other_token) is False


def test_encode_rejects_empty_events() -> None:
    with pytest.raises(ValueError):
        encode_datagram(client_id="c", seq=0, token=b"\x00" * 32, events=[])


def test_encode_rejects_too_many_events() -> None:
    events = [MotionEvent(EventKind.MOVE, 1, 1) for _ in range(33)]
    with pytest.raises(ValueError):
        encode_datagram(client_id="c", seq=0, token=b"\x00" * 32, events=events)


def test_decode_rejects_bad_magic() -> None:
    token = bytes(range(32))
    datagram = bytearray(
        encode_datagram(
            client_id="test-client", seq=1, token=token, events=[MotionEvent(EventKind.MOVE, 1, 1)]
        )
    )
    datagram[0] = 0x00
    with pytest.raises(ProtocolError):
        decode_datagram(bytes(datagram))


def test_decode_rejects_bad_version() -> None:
    token = bytes(range(32))
    datagram = bytearray(
        encode_datagram(
            client_id="test-client", seq=1, token=token, events=[MotionEvent(EventKind.MOVE, 1, 1)]
        )
    )
    datagram[2] = 99
    with pytest.raises(ProtocolError):
        decode_datagram(bytes(datagram))


def test_decode_rejects_truncated_datagram() -> None:
    with pytest.raises(ProtocolError):
        decode_datagram(b"\x52\x50\x01")


def test_decode_rejects_count_zero() -> None:
    # header válido con count=0 (offset 3) y sin bytes de eventos.
    header = bytes([0x52, 0x50, 0x01, 0x00]) + b"\x00" * 20
    with pytest.raises(ProtocolError):
        decode_datagram(header)


def test_decode_rejects_count_over_max() -> None:
    # count=255 (offset 3), sin proveer 255*6 bytes de eventos: header válido
    # pero count fuera de rango debe rechazarse ANTES de mirar la longitud.
    header = bytes([0x52, 0x50, 0x01, 0xFF]) + b"\x00" * 20
    with pytest.raises(ProtocolError):
        decode_datagram(header)


def test_decode_rejects_oversized_datagram() -> None:
    token = bytes(range(32))
    events = [MotionEvent(EventKind.MOVE, 1, 1) for _ in range(32)]  # el máximo válido
    datagram = encode_datagram(client_id="c", seq=1, token=token, events=events)
    padded = datagram + b"\x00" * 300  # supera MAX_UDP_DATAGRAM_BYTES (512)
    with pytest.raises(ProtocolError):
        decode_datagram(padded)


# ---------------------------------------------------------------------------
# UDP / binario — vector fijo de docs/02-PROTOCOLO.md §4
# ---------------------------------------------------------------------------


def test_vector_matches_docs() -> None:
    token = bytes(range(32))
    events = [MotionEvent(kind=EventKind.MOVE, dx=3, dy=-2)]

    datagram = encode_datagram(client_id="test-client", seq=7, token=token, events=events)

    expected_hex = (
        "52 50 01 01 00 00 00 07 D5 FE 82 51 31 96 CA 97 "
        "19 70 FC 7A BE 0F 4D 6F 01 00 00 03 FF FE"
    )
    actual_hex = " ".join(f"{b:02X}" for b in datagram)
    assert actual_hex == expected_hex
