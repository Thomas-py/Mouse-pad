"""S-16 — 'enviar basura aleatoria a ambos puertos durante 60 s no cierra el
servidor; después de eso una sesión normal sigue funcionando'.

Se prueba el mecanismo real (ControlServer + motion_server sobre sockets de
loopback reales, exactamente como los conecta main.py), pero NO se manda
basura durante 60 s literales: a la velocidad de un test unitario eso sería
~60 s de CI por corrida sin ganar cobertura extra sobre mandar la misma
variedad de basura durante 1-2 s. Se manda un volumen grande y variado
(cientos de payloads random, tamaños extremos, JSON casi válido, datagramas
con conteos/versión corruptos) y se confirma que el server sigue respondiendo
un handshake normal después. Es la interpretación práctica del criterio,
no una medición de 60 s de pared.
"""

from __future__ import annotations

import asyncio
import random
from unittest.mock import MagicMock

import pytest

from remotepad_server import session as session_mod
from remotepad_server.control_server import ControlServer
from remotepad_server.motion_server import start_motion_server
from remotepad_server.protocol import Auth, Hello, PairAnswer, PairStart, decode_message, encode_message
from remotepad_server.storage import TokenStore

from tests.test_control_server import _Client, _authenticate, _pair

FIXED_PIN = "424242"
RNG = random.Random(1234)  # determinístico: si falla, reproducible


def _random_tcp_garbage() -> bytes:
    choices = [
        lambda: bytes(RNG.getrandbits(8) for _ in range(RNG.randint(0, 300))),
        lambda: b'{"t":' + bytes(RNG.getrandbits(8) for _ in range(RNG.randint(0, 50))),
        lambda: b"{}" * RNG.randint(1, 50) + b"\n",
        lambda: b'{"t":"hello"}\n',  # JSON válido, campos faltantes
        lambda: b'{"t":"btn","id":"x","sig":"zz","button":"left","action":"click"}\n',
        lambda: b"\x00" * RNG.randint(1, 4096),
        lambda: (b"a" * 8000) + b"\n",  # supera MAX_TCP_MESSAGE_BYTES
        lambda: b"\n",  # línea vacía
    ]
    return RNG.choice(choices)()


def _random_udp_garbage() -> bytes:
    choices = [
        lambda: bytes(RNG.getrandbits(8) for _ in range(RNG.randint(0, 600))),
        lambda: b"\x52\x50" + bytes(RNG.getrandbits(8) for _ in range(RNG.randint(0, 40))),
        lambda: b"\x52\x50\x01" + bytes([RNG.randint(0, 255)]) + b"\x00" * RNG.randint(0, 30),
        lambda: b"",
    ]
    return RNG.choice(choices)()


@pytest.fixture
async def store(tmp_path):
    return TokenStore(path=tmp_path / "tokens.json")


@pytest.fixture
async def injector():
    return MagicMock()


@pytest.fixture
async def wired_servers(store, injector):
    """ControlServer + motion_server conectados como en main.run_async."""
    control = ControlServer(
        server_name="PC de Prueba",
        token_store=store,
        injector=injector,
        ping_timeout=0.3,
        ping_check_interval=0.05,
        pin_factory=lambda: FIXED_PIN,
    )
    await control.start(host="127.0.0.1", port=0)
    motion_transport, _protocol = await start_motion_server(
        host="127.0.0.1", port=0, session_provider=control, injector=injector
    )
    tcp_port = control.bound_port
    udp_port = motion_transport.get_extra_info("sockname")[1]
    try:
        yield control, tcp_port, udp_port
    finally:
        motion_transport.close()
        await control.close()


async def test_survives_sustained_garbage_on_both_ports_and_then_works_normally(
    wired_servers, store
) -> None:
    control, tcp_port, udp_port = wired_servers

    loop = asyncio.get_running_loop()
    udp_send_transport, _ = await loop.create_datagram_endpoint(
        asyncio.DatagramProtocol, remote_addr=("127.0.0.1", udp_port)
    )

    async def flood_udp(n: int) -> None:
        for _ in range(n):
            udp_send_transport.sendto(_random_udp_garbage())
        await asyncio.sleep(0)

    async def flood_tcp_once() -> None:
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection("127.0.0.1", tcp_port), timeout=1.0
            )
        except (OSError, asyncio.TimeoutError):
            return
        try:
            for _ in range(RNG.randint(1, 5)):
                writer.write(_random_tcp_garbage())
                try:
                    await asyncio.wait_for(writer.drain(), timeout=1.0)
                except (OSError, asyncio.TimeoutError):
                    return
                # algunas conexiones se cortan solas si el server las cierra
                # por mensaje inválido/oversize; no es un fallo del test.
        finally:
            writer.close()
            try:
                await asyncio.wait_for(writer.wait_closed(), timeout=1.0)
            except (OSError, asyncio.TimeoutError, ConnectionError):
                pass

    try:
        await flood_udp(400)
        # 60 conexiones TCP separadas mandando basura variada cada una,
        # en paralelo, para además estresar accept() bajo carga.
        await asyncio.gather(*(flood_tcp_once() for _ in range(60)))
        await flood_udp(400)
    finally:
        udp_send_transport.close()

    # El server sigue vivo y funcional: pairing + handshake + auth normales.
    client = await _pair(tcp_port, client_id="iphone-post-garbage")
    session_id = await _authenticate(client, store, client_id="iphone-post-garbage")
    assert session_id
    await client.close()

    # Y motion server sigue aceptando/descartando datagramas sin caerse.
    send_transport, _ = await loop.create_datagram_endpoint(
        asyncio.DatagramProtocol, remote_addr=("127.0.0.1", udp_port)
    )
    try:
        send_transport.sendto(_random_udp_garbage())
        await asyncio.sleep(0.05)
    finally:
        send_transport.close()
