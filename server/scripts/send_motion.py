"""Prueba manual: manda datagramas UDP de movimiento reales a un motion_server
corriendo en la misma PC. Requiere una sesión activa (pairing + handshake
hechos por otro cliente) para que el servidor no descarte los paquetes por
"no_active_session" — pensado para usarse junto con un test manual del
control_server, no aislado.

Uso: python -m scripts.send_motion --token <hex> --client-id <id> --port 52101
"""

from __future__ import annotations

import argparse
import socket
import time

from remotepad_server.protocol import EventKind, MotionEvent, encode_datagram


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=52101)
    parser.add_argument("--client-id", required=True)
    parser.add_argument("--token", required=True, help="token hex de la sesión (64 chars)")
    args = parser.parse_args()

    token = bytes.fromhex(args.token)
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    print("Moviendo el mouse en cuadrado vía UDP real...")
    steps = [(80, 0), (0, 80), (-80, 0), (0, -80)]
    for i, (dx, dy) in enumerate(steps, start=1):
        datagram = encode_datagram(
            client_id=args.client_id, seq=i, token=token, events=[MotionEvent(EventKind.MOVE, dx, dy)]
        )
        sock.sendto(datagram, (args.host, args.port))
        time.sleep(0.3)

    print("Listo.")


if __name__ == "__main__":
    main()
