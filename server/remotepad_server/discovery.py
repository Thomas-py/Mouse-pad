"""Anuncio mDNS del servicio RemotePad (F-20)."""

from __future__ import annotations

import json
import logging
import platform
import socket
import uuid
from pathlib import Path
from typing import Optional

from zeroconf import ServiceInfo, Zeroconf

logger = logging.getLogger(__name__)

SERVICE_TYPE = "_remotepad._tcp.local."
PROTOCOL_VERSION = "1"

STATE_DIR = Path.home() / ".remotepad"
HOST_ID_FILE = STATE_DIR / "host_id.json"


def _detect_os() -> str:
    system = platform.system().lower()
    if system == "darwin":
        return "macos"
    if system == "windows":
        return "windows"
    return "linux"


def get_or_create_host_id() -> str:
    """UUID4 persistente que identifica esta instancia del servidor (TXT `id`)."""
    try:
        data = json.loads(HOST_ID_FILE.read_text(encoding="utf-8"))
        host_id = data.get("id")
        if isinstance(host_id, str) and host_id:
            return host_id
    except (FileNotFoundError, json.JSONDecodeError):
        pass

    host_id = str(uuid.uuid4())
    HOST_ID_FILE.parent.mkdir(parents=True, exist_ok=True)
    HOST_ID_FILE.write_text(json.dumps({"id": host_id}), encoding="utf-8")
    return host_id


def _local_ip() -> str:
    """IP local de la LAN usada para publicar el servicio (no requiere internet real: UDP connect no envía nada)."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.connect(("8.8.8.8", 80))
        return sock.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        sock.close()


class DiscoveryAnnouncer:
    """Registra y desregistra el servicio Bonjour `_remotepad._tcp` del host."""

    def __init__(
        self,
        *,
        name: str,
        port: int,
        udp_port: int,
        host_id: Optional[str] = None,
        zeroconf: Optional[Zeroconf] = None,
    ) -> None:
        self.name = name
        self.port = port
        self.udp_port = udp_port
        self.host_id = host_id or get_or_create_host_id()
        self._zc = zeroconf if zeroconf is not None else Zeroconf()
        self._owns_zc = zeroconf is None
        self._info = self._build_info()
        self._registered = False

    def _build_info(self) -> ServiceInfo:
        properties = {
            "v": PROTOCOL_VERSION,
            "udp": str(self.udp_port),
            "os": _detect_os(),
            "id": self.host_id,
        }
        return ServiceInfo(
            type_=SERVICE_TYPE,
            name=f"{self.name}.{SERVICE_TYPE}",
            port=self.port,
            properties=properties,
            server=f"{socket.gethostname()}.local.",
            parsed_addresses=[_local_ip()],
        )

    def start(self) -> None:
        self._zc.register_service(self._info)
        self._registered = True
        logger.info(
            "mDNS registrado: %s (tcp=%s udp=%s os=%s id=%s)",
            self.name,
            self.port,
            self.udp_port,
            _detect_os(),
            self.host_id,
        )

    def stop(self) -> None:
        if self._registered:
            self._zc.unregister_service(self._info)
            self._registered = False
            logger.info("mDNS desregistrado: %s", self.name)
        if self._owns_zc:
            self._zc.close()

    def __enter__(self) -> "DiscoveryAnnouncer":
        self.start()
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.stop()
