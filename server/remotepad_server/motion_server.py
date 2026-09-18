"""Servidor de movimiento UDP: verifica firma, descarta replays, inyecta (F-23).

La inversión de scroll por `natural_scroll` (F-08/cfg) se aplica en S-13,
no acá — S-09 solo pasa los deltas crudos al inyector.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Optional, Protocol, Tuple

from remotepad_server import session as session_mod
from remotepad_server.injector import InputInjector
from remotepad_server.protocol import (
    EventKind,
    MotionEvent,
    ProtocolError,
    client_hash,
    decode_datagram,
)

logger = logging.getLogger(__name__)


class SessionProvider(Protocol):
    @property
    def active_session(self) -> Optional[session_mod.ActiveSession]: ...


def _accept_seq(session: session_mod.ActiveSession, seq: int) -> bool:
    """Regla del protocolo (§3): aceptar si seq > last, o si hay wrap de uint32."""
    last = session.last_udp_seq
    if last is None or seq > last or (last - seq) > 2**31:
        session.last_udp_seq = seq
        return True
    return False


class MotionServer(asyncio.DatagramProtocol):
    def __init__(self, *, session_provider: SessionProvider, injector: InputInjector) -> None:
        self._sessions = session_provider
        self._injector = injector
        self._transport: Optional[asyncio.DatagramTransport] = None
        self.dropped_count = 0

    def connection_made(self, transport: asyncio.BaseTransport) -> None:
        self._transport = transport  # type: ignore[assignment]

    def datagram_received(self, data: bytes, addr: Tuple[str, int]) -> None:
        try:
            datagram = decode_datagram(data)
        except ProtocolError as exc:
            self._drop(f"decode_error: {exc}")
            return

        session = self._sessions.active_session
        if session is None:
            self._drop("no_active_session")
            return

        if datagram.client_hash != client_hash(session.client_id):
            self._drop("client_hash_mismatch")
            return

        if not datagram.verify(session.token):
            self._drop("bad_sig")
            return

        if not _accept_seq(session, datagram.seq):
            self._drop("replay")
            return

        for event in datagram.events:
            self._apply_event(event)

    def error_received(self, exc: Exception) -> None:
        logger.debug("Error de socket UDP: %s", exc)

    def _apply_event(self, event: MotionEvent) -> None:
        if event.kind == EventKind.MOVE:
            self._injector.move(event.dx, event.dy)
        elif event.kind == EventKind.SCROLL:
            self._injector.scroll(event.dx, event.dy)

    def _drop(self, reason: str) -> None:
        self.dropped_count += 1
        logger.debug("Datagrama de movimiento descartado (%s) — total=%d", reason, self.dropped_count)


async def start_motion_server(
    *, host: str, port: int, session_provider: SessionProvider, injector: InputInjector
) -> Tuple[asyncio.DatagramTransport, MotionServer]:
    loop = asyncio.get_running_loop()
    transport, protocol = await loop.create_datagram_endpoint(
        lambda: MotionServer(session_provider=session_provider, injector=injector),
        local_addr=(host, port),
    )
    return transport, protocol  # type: ignore[return-value]
