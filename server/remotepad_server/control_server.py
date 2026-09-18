"""Servidor de control TCP: pairing, handshake, sesión única y btn/cfg (F-21, F-22, F-24).

btn/cfg no estaban explícitamente en el alcance de S-07 en docs/04-STORIES.md,
pero no hay otra story que los implemente y son el único lugar razonable para
F-24 (inyección de botones/scroll) — se incluyen acá. Ver commit de S-07.
"""

from __future__ import annotations

import asyncio
import hmac
import logging
import secrets
import time
import uuid
from dataclasses import dataclass
from typing import Callable, Optional

from remotepad_server import session as session_mod
from remotepad_server import storage
from remotepad_server.injector import InputInjector
from remotepad_server.protocol import (
    Auth,
    AuthOk,
    Btn,
    Cfg,
    ErrorMsg,
    Hello,
    HelloOk,
    PairAnswer,
    PairChallenge,
    PairOk,
    PairStart,
    Ping,
    Pong,
    ProtocolError,
    decode_message,
    encode_message,
)
from remotepad_server.storage import TokenStore

logger = logging.getLogger(__name__)


@dataclass
class _PendingHandshake:
    client_id: str
    token: bytes
    nonce_server: bytes
    nonce_client: bytes


@dataclass
class _ConnState:
    pairing_challenge: Optional[session_mod.PairingChallenge] = None
    pending_handshake: Optional[_PendingHandshake] = None
    is_active: bool = False


class ControlServer:
    """Una sola sesión activa a la vez; el resto de conexiones solo pueden emparejar."""

    def __init__(
        self,
        *,
        server_name: str,
        token_store: Optional[TokenStore] = None,
        injector: Optional[InputInjector] = None,
        ping_timeout: float = session_mod.PING_TIMEOUT_SECONDS,
        ping_check_interval: float = 1.0,
        pin_factory: Callable[[], str] = session_mod.generate_pin,
    ) -> None:
        self.server_name = server_name
        self._store = token_store if token_store is not None else TokenStore()
        self._injector = injector
        self._ping_timeout = ping_timeout
        self._ping_check_interval = ping_check_interval
        self._pin_factory = pin_factory

        self._active: Optional[session_mod.ActiveSession] = None
        self._active_writer: Optional[asyncio.StreamWriter] = None
        self._lockouts: dict[str, session_mod.LockoutState] = {}

        self._server: Optional[asyncio.AbstractServer] = None
        self._watchdog_task: Optional[asyncio.Task] = None

    @property
    def active_session(self) -> Optional[session_mod.ActiveSession]:
        return self._active

    @property
    def bound_port(self) -> Optional[int]:
        if self._server is None or not self._server.sockets:
            return None
        return self._server.sockets[0].getsockname()[1]

    async def start(self, host: str = "0.0.0.0", port: int = 52100) -> asyncio.AbstractServer:
        self._server = await asyncio.start_server(self._handle_client, host, port)
        self._watchdog_task = asyncio.create_task(self._watch_ping_timeout())
        return self._server

    async def close(self) -> None:
        if self._watchdog_task is not None:
            self._watchdog_task.cancel()
            self._watchdog_task = None
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()
            self._server = None
        self._close_active_session("shutdown")

    # -- ciclo de vida de la sesión activa --------------------------------

    def _close_active_session(self, reason: str) -> None:
        if self._active is None:
            return
        logger.info("Sesión %s cerrada (%s)", self._active.session_id, reason)
        if self._injector is not None:
            self._injector.release_all()
        writer, self._active_writer = self._active_writer, None
        self._active = None
        if writer is not None and not writer.is_closing():
            writer.close()

    async def _watch_ping_timeout(self) -> None:
        while True:
            await asyncio.sleep(self._ping_check_interval)
            if self._active is not None and self._active.is_ping_stale(timeout=self._ping_timeout):
                self._close_active_session("ping timeout")

    # -- conexión -----------------------------------------------------------

    async def _handle_client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        conn = _ConnState()
        peer = writer.get_extra_info("peername")
        logger.info("Conexión de control abierta: %s", peer)
        try:
            while True:
                try:
                    line = await reader.readline()
                except (asyncio.LimitOverrunError, ConnectionError):
                    break
                if not line:
                    break
                try:
                    msg = decode_message(line)
                except ProtocolError as exc:
                    logger.debug("Mensaje TCP inválido de %s (%s), ignorado", peer, exc)
                    continue

                try:
                    keep_open = await self._process_message(msg, writer, conn)
                except ConnectionError:
                    break
                if not keep_open:
                    break
        finally:
            if conn.is_active:
                self._close_active_session("desconexión")
            writer.close()
            logger.info("Conexión de control cerrada: %s", peer)

    @staticmethod
    async def _send(writer: asyncio.StreamWriter, msg) -> None:
        writer.write(encode_message(msg))
        await writer.drain()

    async def _process_message(self, msg, writer: asyncio.StreamWriter, conn: _ConnState) -> bool:
        if isinstance(msg, PairStart):
            await self._handle_pair_start(msg, writer, conn)
            return True
        if isinstance(msg, PairAnswer):
            return await self._handle_pair_answer(msg, writer, conn)
        if isinstance(msg, Hello):
            await self._handle_hello(msg, writer, conn)
            return True
        if isinstance(msg, Auth):
            return await self._handle_auth(msg, writer, conn)

        if not conn.is_active:
            logger.debug("Mensaje post-auth sin sesión activa en esta conexión: %s", msg.t)
            return False

        if isinstance(msg, Ping):
            return await self._handle_ping(msg, writer, conn)
        if isinstance(msg, Btn):
            return self._handle_btn(msg, conn)
        if isinstance(msg, Cfg):
            return self._handle_cfg(msg, conn)
        return True

    # -- pairing (F-21) ------------------------------------------------------

    async def _handle_pair_start(self, msg: PairStart, writer: asyncio.StreamWriter, conn: _ConnState) -> None:
        lockout = self._lockouts.setdefault(msg.client_id, session_mod.LockoutState())
        if lockout.is_locked():
            await self._send(writer, ErrorMsg(t="error", re=msg.id, code="locked"))
            return

        pin = self._pin_factory()
        nonce_server = secrets.token_bytes(16)
        conn.pairing_challenge = session_mod.PairingChallenge(
            client_id=msg.client_id,
            client_name=msg.client_name,
            pin=pin,
            nonce_server=nonce_server,
            nonce_client=bytes.fromhex(msg.nonce),
        )

        print(f"\n=== RemotePad: PIN de emparejamiento para {msg.client_name!r}: {pin} ===\n")
        logger.info("Pairing iniciado: %s (%s)", msg.client_name, msg.client_id)

        await self._send(
            writer,
            PairChallenge(
                t="pair_challenge",
                re=msg.id,
                nonce=nonce_server.hex(),
                expires_in=int(session_mod.PAIR_TTL_SECONDS),
            ),
        )

    async def _handle_pair_answer(self, msg: PairAnswer, writer: asyncio.StreamWriter, conn: _ConnState) -> bool:
        challenge = conn.pairing_challenge
        if challenge is None:
            await self._send(writer, ErrorMsg(t="error", re=msg.id, code="internal"))
            return False

        lockout = self._lockouts.setdefault(challenge.client_id, session_mod.LockoutState())

        if challenge.is_expired():
            lockout.register_failure()
            code = "locked" if lockout.is_locked() else "bad_pin"
            await self._send(writer, ErrorMsg(t="error", re=msg.id, code=code))
            conn.pairing_challenge = None
            return True

        expected = session_mod.compute_pair_proof(
            challenge.pin, challenge.nonce_server, challenge.nonce_client
        ).hex()
        if not hmac.compare_digest(expected, msg.proof):
            lockout.register_failure()
            code = "locked" if lockout.is_locked() else "bad_pin"
            await self._send(writer, ErrorMsg(t="error", re=msg.id, code=code))
            return True

        token = session_mod.derive_token(challenge.pin, challenge.nonce_server, challenge.nonce_client)
        self._store.save(
            storage.PairedClient(
                client_id=challenge.client_id,
                client_name=challenge.client_name,
                token=token.hex(),
                paired_at=time.time(),
            )
        )
        lockout.reset()
        conn.pairing_challenge = None
        await self._send(writer, PairOk(t="pair_ok", re=msg.id))
        return True

    # -- handshake (F-22) -----------------------------------------------------

    async def _handle_hello(self, msg: Hello, writer: asyncio.StreamWriter, conn: _ConnState) -> None:
        paired = self._store.get(msg.client_id)
        if paired is None:
            await self._send(writer, ErrorMsg(t="error", re=msg.id, code="unpaired"))
            return

        nonce_server = secrets.token_bytes(16)
        conn.pending_handshake = _PendingHandshake(
            client_id=msg.client_id,
            token=bytes.fromhex(paired.token),
            nonce_server=nonce_server,
            nonce_client=bytes.fromhex(msg.nonce),
        )
        await self._send(
            writer,
            HelloOk(t="hello_ok", re=msg.id, nonce=nonce_server.hex(), server_name=self.server_name),
        )

    async def _handle_auth(self, msg: Auth, writer: asyncio.StreamWriter, conn: _ConnState) -> bool:
        pending = conn.pending_handshake
        if pending is None or pending.client_id != msg.client_id:
            await self._send(writer, ErrorMsg(t="error", re=msg.id, code="bad_sig"))
            return False

        expected = session_mod.compute_auth_sig(
            pending.token, pending.nonce_server, pending.nonce_client
        ).hex()
        if not hmac.compare_digest(expected, msg.sig):
            await self._send(writer, ErrorMsg(t="error", re=msg.id, code="bad_sig"))
            return False

        if self._active is not None:
            await self._send(writer, ErrorMsg(t="error", re=msg.id, code="busy"))
            return False

        session_id = str(uuid.uuid4())
        self._active = session_mod.ActiveSession(
            session_id=session_id, client_id=pending.client_id, token=pending.token
        )
        self._active_writer = writer
        conn.is_active = True
        conn.pending_handshake = None

        await self._send(writer, AuthOk(t="auth_ok", re=msg.id, session=session_id))
        return True

    # -- mensajes post-auth (F-22, F-24) --------------------------------------

    async def _handle_ping(self, msg: Ping, writer: asyncio.StreamWriter, conn: _ConnState) -> bool:
        assert self._active is not None
        if not self._verify_message_sig(msg):
            self._close_active_session("bad_sig")
            return False
        self._active.touch_ping()
        await self._send(writer, Pong(t="pong", re=msg.id, ts=msg.ts))
        return True

    def _handle_btn(self, msg: Btn, conn: _ConnState) -> bool:
        assert self._active is not None
        if not self._verify_message_sig(msg):
            self._close_active_session("bad_sig")
            return False

        if self._injector is not None:
            if msg.action == "click":
                self._injector.click(msg.button, msg.count)
            elif msg.action == "down":
                self._injector.press(msg.button)
            elif msg.action == "up":
                self._injector.release(msg.button)
        return True

    def _handle_cfg(self, msg: Cfg, conn: _ConnState) -> bool:
        assert self._active is not None
        if not self._verify_message_sig(msg):
            self._close_active_session("bad_sig")
            return False
        self._active.natural_scroll = msg.natural_scroll
        return True

    def _verify_message_sig(self, msg) -> bool:
        assert self._active is not None
        expected = session_mod.compute_message_sig(
            self._active.token, self._active.session_id, msg.id, msg.t
        )
        return hmac.compare_digest(expected, msg.sig)
