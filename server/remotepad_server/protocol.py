"""Modelos y codecs del protocolo RemotePad v1.

Fuente de verdad: docs/02-PROTOCOLO.md. Cualquier cambio acá implica
actualizar ese documento primero (regla del proyecto).
"""

from __future__ import annotations

import hashlib
import hmac
import json
import struct
from dataclasses import dataclass
from enum import IntEnum
from typing import Annotated, Literal, Sequence, Union

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, ValidationError

# ---------------------------------------------------------------------------
# Errores
# ---------------------------------------------------------------------------

ErrorCode = Literal[
    "unpaired", "bad_pin", "locked", "bad_sig", "bad_version", "busy", "internal"
]


class ProtocolError(ValueError):
    """Mensaje TCP o datagrama UDP inválido."""

    def __init__(self, code: ErrorCode, detail: str | None = None) -> None:
        self.code = code
        super().__init__(detail or code)


# ---------------------------------------------------------------------------
# Canal de control — TCP, JSON (docs/02-PROTOCOLO.md §2)
# ---------------------------------------------------------------------------

MAX_TCP_MESSAGE_BYTES = 4096


class _Msg(BaseModel):
    model_config = ConfigDict(extra="forbid")


# Cliente -> Servidor

class Hello(_Msg):
    t: Literal["hello"]
    id: str
    v: int
    client_id: str
    nonce: str


class Auth(_Msg):
    t: Literal["auth"]
    id: str
    client_id: str
    sig: str


class PairStart(_Msg):
    t: Literal["pair_start"]
    id: str
    v: int
    client_id: str
    client_name: str
    nonce: str


class PairAnswer(_Msg):
    t: Literal["pair_answer"]
    id: str
    proof: str


class Btn(_Msg):
    t: Literal["btn"]
    id: str
    sig: str
    button: Literal["left", "right", "middle"]
    action: Literal["click", "down", "up"]
    count: int = 1


class Cfg(_Msg):
    t: Literal["cfg"]
    id: str
    sig: str
    natural_scroll: bool


class Ping(_Msg):
    t: Literal["ping"]
    id: str
    sig: str
    ts: int


# Servidor -> Cliente

class HelloOk(_Msg):
    t: Literal["hello_ok"]
    re: str
    nonce: str
    server_name: str


class ErrorMsg(_Msg):
    t: Literal["error"]
    re: str
    code: ErrorCode


class AuthOk(_Msg):
    t: Literal["auth_ok"]
    re: str
    session: str


class PairChallenge(_Msg):
    t: Literal["pair_challenge"]
    re: str
    nonce: str
    expires_in: int


class PairOk(_Msg):
    t: Literal["pair_ok"]
    re: str


class Pong(_Msg):
    t: Literal["pong"]
    re: str
    ts: int


ClientMessage = Annotated[
    Union[Hello, Auth, PairStart, PairAnswer, Btn, Cfg, Ping],
    Field(discriminator="t"),
]

ServerMessage = Annotated[
    Union[HelloOk, ErrorMsg, AuthOk, PairChallenge, PairOk, Pong],
    Field(discriminator="t"),
]

AnyMessage = Annotated[
    Union[
        Hello, Auth, PairStart, PairAnswer, Btn, Cfg, Ping,
        HelloOk, ErrorMsg, AuthOk, PairChallenge, PairOk, Pong,
    ],
    Field(discriminator="t"),
]

_any_adapter: TypeAdapter[AnyMessage] = TypeAdapter(AnyMessage)


def decode_message(raw: bytes | str) -> AnyMessage:
    """Parsea una línea del canal de control (sin el `\\n` final, opcional)."""
    if isinstance(raw, str):
        raw = raw.encode("utf-8")
    if len(raw) > MAX_TCP_MESSAGE_BYTES:
        raise ProtocolError("internal", "mensaje excede MAX_TCP_MESSAGE_BYTES")
    try:
        text = raw.decode("utf-8").rstrip("\n")
    except UnicodeDecodeError as exc:
        raise ProtocolError("internal", f"bytes no son UTF-8 válido: {exc}") from exc
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ProtocolError("internal", f"json inválido: {exc}") from exc
    try:
        return _any_adapter.validate_python(data)
    except ValidationError as exc:
        raise ProtocolError("internal", str(exc)) from exc


def encode_message(msg: BaseModel) -> bytes:
    """Serializa un mensaje a una línea JSON UTF-8 terminada en `\\n`."""
    return (msg.model_dump_json() + "\n").encode("utf-8")


# ---------------------------------------------------------------------------
# Canal de movimiento — UDP, binario (docs/02-PROTOCOLO.md §3)
# ---------------------------------------------------------------------------

MOTION_MAGIC = b"\x52\x50"
MOTION_VERSION = 1
MAX_UDP_DATAGRAM_BYTES = 512
MAX_EVENTS_PER_DATAGRAM = 32

# magic(2s) version(B) count(B) seq(I) client_hash(8s) sig(8s) = 24 bytes
_HEADER_STRUCT = struct.Struct(">2sBBI8s8s")
# kind(B) flags(B) dx(h) dy(h) = 6 bytes
_EVENT_STRUCT = struct.Struct(">BBhh")


class EventKind(IntEnum):
    MOVE = 0x01
    SCROLL = 0x02


@dataclass(frozen=True)
class MotionEvent:
    kind: EventKind
    dx: int
    dy: int


def client_hash(client_id: str) -> bytes:
    """Primeros 8 bytes de SHA-256(client_id)."""
    return hashlib.sha256(client_id.encode("utf-8")).digest()[:8]


def _pack_events(events: Sequence[MotionEvent]) -> bytes:
    return b"".join(
        _EVENT_STRUCT.pack(int(event.kind), 0, event.dx, event.dy) for event in events
    )


def _compute_sig(token: bytes, header_prefix: bytes, events_bytes: bytes) -> bytes:
    """Primeros 8 bytes de HMAC-SHA256(token, header_prefix + eventos)."""
    return hmac.new(token, header_prefix + events_bytes, hashlib.sha256).digest()[:8]


def encode_datagram(
    *, client_id: str, seq: int, token: bytes, events: Sequence[MotionEvent]
) -> bytes:
    if not events:
        raise ValueError("events no puede estar vacío")
    if len(events) > MAX_EVENTS_PER_DATAGRAM:
        raise ValueError(f"máximo {MAX_EVENTS_PER_DATAGRAM} eventos por datagrama")
    if not 0 <= seq <= 0xFFFFFFFF:
        raise ValueError("seq fuera de rango uint32")

    header_prefix = (
        MOTION_MAGIC
        + bytes((MOTION_VERSION, len(events)))
        + struct.pack(">I", seq)
        + client_hash(client_id)
    )
    events_bytes = _pack_events(events)
    sig = _compute_sig(token, header_prefix, events_bytes)
    datagram = header_prefix + sig + events_bytes

    if len(datagram) > MAX_UDP_DATAGRAM_BYTES:
        raise ValueError("datagrama excede MAX_UDP_DATAGRAM_BYTES")
    return datagram


@dataclass(frozen=True)
class MotionDatagram:
    seq: int
    client_hash: bytes
    sig: bytes
    header_prefix: bytes
    events: tuple[MotionEvent, ...]

    def verify(self, token: bytes) -> bool:
        expected = _compute_sig(token, self.header_prefix, _pack_events(self.events))
        return hmac.compare_digest(expected, self.sig)


def decode_datagram(data: bytes) -> MotionDatagram:
    if len(data) < _HEADER_STRUCT.size:
        raise ProtocolError("internal", "datagrama más corto que el header")
    if len(data) > MAX_UDP_DATAGRAM_BYTES:
        raise ProtocolError("internal", "datagrama excede MAX_UDP_DATAGRAM_BYTES")

    magic, version, count, seq, ch, sig = _HEADER_STRUCT.unpack_from(data, 0)
    if magic != MOTION_MAGIC:
        raise ProtocolError("internal", "magic inválido")
    if version != MOTION_VERSION:
        raise ProtocolError("bad_version", f"versión de motion no soportada: {version}")
    if not 1 <= count <= MAX_EVENTS_PER_DATAGRAM:
        raise ProtocolError("internal", f"count fuera de rango (1-{MAX_EVENTS_PER_DATAGRAM}): {count}")

    events_bytes = data[_HEADER_STRUCT.size :]
    if len(events_bytes) != count * _EVENT_STRUCT.size:
        raise ProtocolError("internal", "longitud de eventos inconsistente con count")

    events = []
    for i in range(count):
        chunk = events_bytes[i * _EVENT_STRUCT.size : (i + 1) * _EVENT_STRUCT.size]
        kind_raw, _flags, dx, dy = _EVENT_STRUCT.unpack(chunk)
        try:
            kind = EventKind(kind_raw)
        except ValueError as exc:
            raise ProtocolError("internal", f"kind de evento desconocido: {kind_raw}") from exc
        events.append(MotionEvent(kind=kind, dx=dx, dy=dy))

    return MotionDatagram(
        seq=seq,
        client_hash=ch,
        sig=sig,
        header_prefix=data[:16],
        events=tuple(events),
    )
