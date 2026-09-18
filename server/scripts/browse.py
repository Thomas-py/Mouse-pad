"""Cliente zeroconf de prueba para verificar el anuncio mDNS desde Windows.

En macOS se usaría `dns-sd -B _remotepad._tcp`; en Linux, `avahi-browse`.
Windows no trae ninguno de los dos, así que este script cumple el mismo
rol usando la misma librería `zeroconf` que el servidor.

Correr con el servidor ya arrancado en otra terminal:
    python -m scripts.browse
Ctrl+C para salir.
"""

from __future__ import annotations

import time

from zeroconf import ServiceBrowser, ServiceListener, Zeroconf

from remotepad_server.discovery import SERVICE_TYPE


class _PrintingListener(ServiceListener):
    def add_service(self, zc: Zeroconf, type_: str, name: str) -> None:
        info = zc.get_service_info(type_, name)
        if info is None:
            print(f"+ {name} (sin info)")
            return
        props = {k.decode(): (v.decode() if v is not None else None) for k, v in info.properties.items()}
        addresses = info.parsed_addresses()
        print(f"+ {name} @ {addresses} puerto={info.port} txt={props}")

    def remove_service(self, zc: Zeroconf, type_: str, name: str) -> None:
        print(f"- {name}")

    def update_service(self, zc: Zeroconf, type_: str, name: str) -> None:
        pass


def main() -> None:
    zc = Zeroconf()
    listener = _PrintingListener()
    ServiceBrowser(zc, SERVICE_TYPE, listener)
    print(f"Buscando {SERVICE_TYPE} ... Ctrl+C para salir.")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        zc.close()


if __name__ == "__main__":
    main()
