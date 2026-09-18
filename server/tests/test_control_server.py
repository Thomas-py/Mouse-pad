import asyncio
from unittest.mock import MagicMock

import pytest

from remotepad_server import session as session_mod
from remotepad_server.control_server import ControlServer
from remotepad_server.protocol import (
    Auth,
    Btn,
    Cfg,
    Hello,
    PairAnswer,
    PairStart,
    Ping,
    decode_message,
    encode_message,
)
from remotepad_server.storage import TokenStore

FIXED_PIN = "424242"


class _Client:
    """Cliente asyncio simulado que habla el protocolo de control sobre TCP real."""

    def __init__(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        self.reader = reader
        self.writer = writer

    @classmethod
    async def connect(cls, port: int) -> "_Client":
        reader, writer = await asyncio.open_connection("127.0.0.1", port)
        return cls(reader, writer)

    async def send(self, msg) -> None:
        self.writer.write(encode_message(msg))
        await self.writer.drain()

    async def recv(self, timeout: float = 2.0):
        line = await asyncio.wait_for(self.reader.readline(), timeout=timeout)
        assert line, "la conexión se cerró sin responder"
        return decode_message(line)

    async def recv_none_or_eof(self, timeout: float = 1.0) -> bool:
        """True si la conexión se cerró (EOF) dentro del timeout."""
        try:
            line = await asyncio.wait_for(self.reader.readline(), timeout=timeout)
        except asyncio.TimeoutError:
            return False
        return line == b""

    async def close(self) -> None:
        self.writer.close()
        try:
            await self.writer.wait_closed()
        except (ConnectionError, OSError):
            pass


@pytest.fixture
async def store(tmp_path):
    return TokenStore(path=tmp_path / "tokens.json")


@pytest.fixture
async def injector():
    return MagicMock()


@pytest.fixture
async def server(store, injector):
    srv = ControlServer(
        server_name="PC de Prueba",
        token_store=store,
        injector=injector,
        ping_timeout=0.3,
        ping_check_interval=0.05,
        pin_factory=lambda: FIXED_PIN,
    )
    await srv.start(host="127.0.0.1", port=0)
    yield srv
    await srv.close()


async def _pair(port: int, client_id: str = "iphone-1", client_name: str = "iPhone de prueba") -> _Client:
    """Corre el flujo de pairing completo (PIN fijo FIXED_PIN) y deja la conexión abierta."""
    client = await _Client.connect(port)
    nonce_client = bytes(range(16))
    await client.send(
        PairStart(t="pair_start", id="p1", v=1, client_id=client_id, client_name=client_name, nonce=nonce_client.hex())
    )
    challenge = await client.recv()
    assert challenge.t == "pair_challenge"

    nonce_server = bytes.fromhex(challenge.nonce)
    proof = session_mod.compute_pair_proof(FIXED_PIN, nonce_server, nonce_client).hex()
    await client.send(PairAnswer(t="pair_answer", id="p2", proof=proof))
    ok = await client.recv()
    assert ok.t == "pair_ok"
    return client


async def _authenticate(client: _Client, store: TokenStore, client_id: str = "iphone-1") -> str:
    """Corre hello/auth sobre una conexión ya emparejada. Devuelve el session id."""
    paired = store.get(client_id)
    assert paired is not None
    token = bytes.fromhex(paired.token)

    nonce_client = bytes(range(16, 32))
    await client.send(Hello(t="hello", id="a1", v=1, client_id=client_id, nonce=nonce_client.hex()))
    hello_ok = await client.recv()
    assert hello_ok.t == "hello_ok"
    nonce_server = bytes.fromhex(hello_ok.nonce)

    sig = session_mod.compute_auth_sig(token, nonce_server, nonce_client).hex()
    await client.send(Auth(t="auth", id="a2", client_id=client_id, sig=sig))
    auth_ok = await client.recv()
    assert auth_ok.t == "auth_ok"
    return auth_ok.session


# ---------------------------------------------------------------------------
# Pairing OK
# ---------------------------------------------------------------------------


async def test_pairing_succeeds_and_persists_token(server, store) -> None:
    client = await _pair(server.bound_port)
    try:
        assert store.get("iphone-1") is not None
        assert store.get("iphone-1").client_name == "iPhone de prueba"
    finally:
        await client.close()


# ---------------------------------------------------------------------------
# PIN incorrecto x5 -> locked
# ---------------------------------------------------------------------------


async def test_wrong_pin_five_times_locks(server) -> None:
    client = await _Client.connect(server.bound_port)
    try:
        nonce_client = bytes(range(16))
        await client.send(
            PairStart(t="pair_start", id="p1", v=1, client_id="iphone-2", client_name="x", nonce=nonce_client.hex())
        )
        challenge = await client.recv()
        nonce_server = bytes.fromhex(challenge.nonce)

        wrong_proof = session_mod.compute_pair_proof("000000", nonce_server, nonce_client).hex()
        assert wrong_proof != session_mod.compute_pair_proof(FIXED_PIN, nonce_server, nonce_client).hex()

        for attempt in range(4):
            await client.send(PairAnswer(t="pair_answer", id=f"p{attempt}", proof=wrong_proof))
            resp = await client.recv()
            assert resp.t == "error"
            assert resp.code == "bad_pin"

        await client.send(PairAnswer(t="pair_answer", id="p-last", proof=wrong_proof))
        resp = await client.recv()
        assert resp.t == "error"
        assert resp.code == "locked"
    finally:
        await client.close()


async def test_locked_client_id_rejected_on_new_pair_start(server) -> None:
    client = await _Client.connect(server.bound_port)
    try:
        nonce_client = bytes(range(16))
        wrong_proof_nonce_server = None

        async def attempt_wrong_pin() -> None:
            nonlocal wrong_proof_nonce_server
            await client.send(
                PairStart(t="pair_start", id="p", v=1, client_id="iphone-3", client_name="x", nonce=nonce_client.hex())
            )
            challenge = await client.recv()
            nonce_server = bytes.fromhex(challenge.nonce)
            wrong_proof = session_mod.compute_pair_proof("000000", nonce_server, nonce_client).hex()
            await client.send(PairAnswer(t="pair_answer", id="p", proof=wrong_proof))
            await client.recv()

        for _ in range(5):
            await attempt_wrong_pin()

        await client.send(
            PairStart(t="pair_start", id="p-new", v=1, client_id="iphone-3", client_name="x", nonce=nonce_client.hex())
        )
        resp = await client.recv()
        assert resp.t == "error"
        assert resp.code == "locked"
    finally:
        await client.close()


# ---------------------------------------------------------------------------
# Handshake con token válido
# ---------------------------------------------------------------------------


async def test_handshake_with_valid_token_succeeds(server, store) -> None:
    pairing_client = await _pair(server.bound_port)
    await pairing_client.close()

    client = await _Client.connect(server.bound_port)
    try:
        session_id = await _authenticate(client, store)
        assert session_id
        assert server.active_session is not None
        assert server.active_session.session_id == session_id
    finally:
        await client.close()


# ---------------------------------------------------------------------------
# Token inválido -> bad_sig
# ---------------------------------------------------------------------------


async def test_auth_with_invalid_signature_returns_bad_sig(server, store) -> None:
    pairing_client = await _pair(server.bound_port)
    await pairing_client.close()

    client = await _Client.connect(server.bound_port)
    try:
        nonce_client = bytes(range(16, 32))
        await client.send(Hello(t="hello", id="a1", v=1, client_id="iphone-1", nonce=nonce_client.hex()))
        hello_ok = await client.recv()

        await client.send(Auth(t="auth", id="a2", client_id="iphone-1", sig="0" * 64))
        resp = await client.recv()
        assert resp.t == "error"
        assert resp.code == "bad_sig"

        assert await client.recv_none_or_eof(timeout=1.0)
    finally:
        await client.close()


async def test_hello_for_unpaired_client_returns_unpaired(server) -> None:
    client = await _Client.connect(server.bound_port)
    try:
        await client.send(Hello(t="hello", id="a1", v=1, client_id="never-paired", nonce="00" * 16))
        resp = await client.recv()
        assert resp.t == "error"
        assert resp.code == "unpaired"
    finally:
        await client.close()


# ---------------------------------------------------------------------------
# Segundo cliente -> busy
# ---------------------------------------------------------------------------


async def test_second_client_gets_busy(server, store) -> None:
    p1 = await _pair(server.bound_port, client_id="iphone-1", client_name="uno")
    await p1.close()
    p2 = await _pair(server.bound_port, client_id="iphone-2", client_name="dos")
    await p2.close()

    client_a = await _Client.connect(server.bound_port)
    client_b = await _Client.connect(server.bound_port)
    try:
        await _authenticate(client_a, store, client_id="iphone-1")

        nonce_client = bytes(range(16, 32))
        await client_b.send(Hello(t="hello", id="b1", v=1, client_id="iphone-2", nonce=nonce_client.hex()))
        hello_ok = await client_b.recv()
        nonce_server = bytes.fromhex(hello_ok.nonce)
        paired = store.get("iphone-2")
        token = bytes.fromhex(paired.token)
        sig = session_mod.compute_auth_sig(token, nonce_server, nonce_client).hex()
        await client_b.send(Auth(t="auth", id="b2", client_id="iphone-2", sig=sig))
        resp = await client_b.recv()
        assert resp.t == "error"
        assert resp.code == "busy"
    finally:
        await client_a.close()
        await client_b.close()


# ---------------------------------------------------------------------------
# Timeout de ping cierra la sesión
# ---------------------------------------------------------------------------


async def test_ping_timeout_closes_session(server, store, injector) -> None:
    pairing_client = await _pair(server.bound_port)
    await pairing_client.close()

    client = await _Client.connect(server.bound_port)
    try:
        await _authenticate(client, store)
        assert server.active_session is not None

        # ping_timeout=0.3s, ping_check_interval=0.05s en el fixture `server`
        await asyncio.sleep(0.6)

        assert server.active_session is None
        injector.release_all.assert_called()
        assert await client.recv_none_or_eof(timeout=1.0)
    finally:
        await client.close()


async def test_ping_keeps_session_alive(server, store) -> None:
    pairing_client = await _pair(server.bound_port)
    await pairing_client.close()

    client = await _Client.connect(server.bound_port)
    try:
        session_id = await _authenticate(client, store)
        paired = store.get("iphone-1")
        token = bytes.fromhex(paired.token)

        for i in range(4):
            await asyncio.sleep(0.15)
            sig = session_mod.compute_message_sig(token, session_id, f"k{i}", "ping")
            await client.send(Ping(t="ping", id=f"k{i}", sig=sig, ts=i))
            pong = await client.recv()
            assert pong.t == "pong"
            assert pong.ts == i

        assert server.active_session is not None
    finally:
        await client.close()


# ---------------------------------------------------------------------------
# btn / cfg (F-24) y bad_sig post-auth
# ---------------------------------------------------------------------------


async def test_btn_click_calls_injector(server, store, injector) -> None:
    pairing_client = await _pair(server.bound_port)
    await pairing_client.close()

    client = await _Client.connect(server.bound_port)
    try:
        session_id = await _authenticate(client, store)
        paired = store.get("iphone-1")
        token = bytes.fromhex(paired.token)

        sig = session_mod.compute_message_sig(token, session_id, "b1", "btn")
        await client.send(Btn(t="btn", id="b1", sig=sig, button="left", action="click", count=1))
        await asyncio.sleep(0.1)  # btn es fire-and-forget, no hay respuesta

        injector.click.assert_called_once_with("left", 1)
    finally:
        await client.close()


async def test_cfg_updates_natural_scroll(server, store) -> None:
    pairing_client = await _pair(server.bound_port)
    await pairing_client.close()

    client = await _Client.connect(server.bound_port)
    try:
        session_id = await _authenticate(client, store)
        paired = store.get("iphone-1")
        token = bytes.fromhex(paired.token)

        sig = session_mod.compute_message_sig(token, session_id, "c1", "cfg")
        await client.send(Cfg(t="cfg", id="c1", sig=sig, natural_scroll=False))
        await asyncio.sleep(0.1)

        assert server.active_session.natural_scroll is False
    finally:
        await client.close()


async def test_bad_sig_on_btn_closes_session(server, store, injector) -> None:
    pairing_client = await _pair(server.bound_port)
    await pairing_client.close()

    client = await _Client.connect(server.bound_port)
    try:
        await _authenticate(client, store)

        await client.send(Btn(t="btn", id="b1", sig="0" * 16, button="left", action="click", count=1))
        assert await client.recv_none_or_eof(timeout=1.0)

        assert server.active_session is None
        injector.release_all.assert_called()
    finally:
        await client.close()


async def test_disconnect_releases_session(server, store, injector) -> None:
    pairing_client = await _pair(server.bound_port)
    await pairing_client.close()

    client = await _Client.connect(server.bound_port)
    await _authenticate(client, store)
    assert server.active_session is not None

    await client.close()
    await asyncio.sleep(0.2)

    assert server.active_session is None
    injector.release_all.assert_called()
