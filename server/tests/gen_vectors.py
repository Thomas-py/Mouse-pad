"""Genera los vectores de prueba de docs/02-PROTOCOLO.md §4.

Correr con: python -m tests.gen_vectors (desde server/, con el venv activo)
El hex impreso se copia a mano en 02-PROTOCOLO.md y se hardcodea en
test_protocol.py::test_vector_matches_docs para que ambos lados (server
y, eventualmente, iOS) verifiquen contra el mismo vector fijo.
"""

from remotepad_server.protocol import EventKind, MotionEvent, client_hash, encode_datagram


def main() -> None:
    token = bytes(range(32))
    cid = "test-client"
    seq = 7
    events = [MotionEvent(kind=EventKind.MOVE, dx=3, dy=-2)]

    datagram = encode_datagram(client_id=cid, seq=seq, token=token, events=events)

    print("full datagram:", " ".join(f"{b:02X}" for b in datagram))
    print("client_hash  :", client_hash(cid).hex().upper())
    print("sig          :", datagram[16:24].hex().upper())


if __name__ == "__main__":
    main()
