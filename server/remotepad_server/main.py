"""Punto de entrada del servidor RemotePad — CLI (F-25)."""

from __future__ import annotations

import argparse
import logging
import signal
import socket
import threading
from types import FrameType
from typing import Callable

from remotepad_server.discovery import DiscoveryAnnouncer

logger = logging.getLogger(__name__)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="remotepad-server", description="Servidor RemotePad")
    parser.add_argument(
        "--name", default=socket.gethostname(), help="Nombre del host anunciado por mDNS"
    )
    parser.add_argument("--port", type=int, default=52100, help="Puerto TCP de control")
    parser.add_argument("--udp-port", type=int, default=52101, help="Puerto UDP de movimiento")
    return parser


def run(
    *,
    name: str,
    port: int,
    udp_port: int,
    announcer_factory: Callable[..., object] = DiscoveryAnnouncer,
    stop_event: threading.Event | None = None,
    install_signal_handlers: bool = True,
) -> None:
    """Núcleo testeable del servidor: arranca el anuncio mDNS y bloquea hasta señal de cierre."""
    stop_event = stop_event if stop_event is not None else threading.Event()
    announcer = announcer_factory(name=name, port=port, udp_port=udp_port)
    announcer.start()

    if install_signal_handlers:
        def _handle_signal(signum: int, frame: FrameType | None) -> None:
            stop_event.set()

        signal.signal(signal.SIGINT, _handle_signal)
        try:
            signal.signal(signal.SIGTERM, _handle_signal)
        except (ValueError, AttributeError):
            pass  # SIGTERM no disponible en todas las plataformas/hilos

    logger.info("RemotePad server corriendo. Ctrl+C para salir.")
    try:
        stop_event.wait()
    finally:
        logger.info("Cerrando...")
        announcer.stop()


def cli(argv: list[str] | None = None) -> None:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    args = build_parser().parse_args(argv)
    run(name=args.name, port=args.port, udp_port=args.udp_port)


if __name__ == "__main__":
    cli()
