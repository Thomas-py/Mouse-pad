"""Punto de entrada del servidor RemotePad — CLI (F-25) y wiring real de todo.

Hasta S-15 el CLI solo arrancaba el anuncio mDNS: control_server.py (S-07)
y motion_server.py (S-09) existían pero nada los conectaba a `remotepad-server`.
Sin esto el servidor no hacía nada útil — se corrige acá (S-16) junto con el
resto de la robustez (F-25: log-level, banner de arranque, aviso de
Accesibilidad en macOS).
"""

from __future__ import annotations

import argparse
import asyncio
import ctypes
import logging
import signal
import socket
import sys
import threading
from types import FrameType
from typing import Callable, Optional

from remotepad_server.control_server import ControlServer
from remotepad_server.discovery import DiscoveryAnnouncer, get_or_create_host_id
from remotepad_server.injector import InputInjector, WaylandNotSupportedError
from remotepad_server.motion_server import start_motion_server
from remotepad_server.storage import TokenStore

logger = logging.getLogger(__name__)

_LOG_LEVELS = ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="remotepad-server", description="Servidor RemotePad")
    parser.add_argument(
        "--name", default=socket.gethostname(), help="Nombre del host anunciado por mDNS"
    )
    parser.add_argument("--port", type=int, default=52100, help="Puerto TCP de control")
    parser.add_argument("--udp-port", type=int, default=52101, help="Puerto UDP de movimiento")
    parser.add_argument(
        "--log-level", default="INFO", choices=_LOG_LEVELS, help="Nivel de logging (default INFO)"
    )
    return parser


def _detect_os_label() -> str:
    system = sys.platform
    if system == "darwin":
        return "macos"
    if system == "win32":
        return "windows"
    return "linux"


def _macos_accessibility_hint() -> None:
    """F-25: avisar si falta el permiso de Accesibilidad en macOS.

    Best-effort: no se pudo probar en un Mac real en esta sesión. Cualquier
    fallo al cargar el framework se ignora — esto nunca debe bloquear el
    arranque del servidor, es solo un aviso.
    """
    if sys.platform != "darwin":
        return
    try:
        lib = ctypes.CDLL(
            "/System/Library/Frameworks/ApplicationServices.framework/ApplicationServices"
        )
        trusted = bool(lib.AXIsProcessTrusted())
    except OSError:
        return
    if not trusted:
        print(
            "AVISO: RemotePad necesita permiso de Accesibilidad en macOS para mover "
            "el mouse.\n"
            "  Ajustes del Sistema -> Privacidad y Seguridad -> Accesibilidad "
            "-> agregar la Terminal (o el binario empaquetado)."
        )


def _print_startup_banner(*, name: str, port: int, udp_port: int, host_id: str) -> None:
    print("=== RemotePad server ===")
    print(f"  nombre : {name}")
    print(f"  SO     : {_detect_os_label()}")
    print(f"  id     : {host_id}")
    print(f"  TCP    : {port} (control)")
    print(f"  UDP    : {udp_port} (movimiento)")
    print("Ctrl+C para salir.")


async def run_async(
    args: argparse.Namespace,
    *,
    injector_factory: Callable[[], InputInjector] = InputInjector,
    control_server_factory: Callable[..., ControlServer] = ControlServer,
    announcer_factory: Callable[..., DiscoveryAnnouncer] = DiscoveryAnnouncer,
    stop_event: Optional[asyncio.Event] = None,
    install_signal_handlers: bool = True,
) -> None:
    """Núcleo testeable: arranca todo, bloquea hasta `stop_event`, cierra todo."""
    stop_event = stop_event if stop_event is not None else asyncio.Event()

    _macos_accessibility_hint()

    injector = injector_factory()
    store = TokenStore()
    control = control_server_factory(server_name=args.name, token_store=store, injector=injector)
    await control.start(host="0.0.0.0", port=args.port)

    motion_transport, _motion_protocol = await start_motion_server(
        host="0.0.0.0", port=args.udp_port, session_provider=control, injector=injector
    )

    announcer = announcer_factory(name=args.name, port=args.port, udp_port=args.udp_port)
    announcer.start()

    _print_startup_banner(name=args.name, port=args.port, udp_port=args.udp_port, host_id=get_or_create_host_id())
    logger.info("RemotePad server corriendo (tcp=%s udp=%s)", args.port, args.udp_port)

    if install_signal_handlers:
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.add_signal_handler(sig, stop_event.set)
            except (NotImplementedError, RuntimeError):
                # Windows (ProactorEventLoop) no soporta add_signal_handler:
                # Ctrl+C llega como KeyboardInterrupt normal y se maneja en cli().
                pass

    try:
        await stop_event.wait()
    finally:
        logger.info("Cerrando...")
        announcer.stop()
        motion_transport.close()
        await control.close()


def cli(argv: Optional[list[str]] = None) -> None:
    args = build_parser().parse_args(argv)
    logging.basicConfig(
        level=getattr(logging, args.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    try:
        asyncio.run(run_async(args))
    except KeyboardInterrupt:
        pass
    except WaylandNotSupportedError as exc:
        logger.error("%s", exc)
        raise SystemExit(1) from exc


if __name__ == "__main__":
    cli()
