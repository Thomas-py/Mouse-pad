# RemotePad — Stories de implementación

Orden obligatorio. Cada story es una rama `story/S-xx-nombre` y un PR. No empezar la siguiente sin cerrar la anterior. Cada una referencia funcionalidades (`F-xx`) de `03-ESPECIFICACIONES-FUNCIONALES.md`.

Formato: **Objetivo · Alcance · Fuera de alcance · Hecho cuando**.

---

## Fase 0 — Base

### S-01 Scaffold del repositorio
- **Objetivo**: estructura vacía pero funcional en ambos lados.
- **Alcance**: crear `ios/RemotePad` (proyecto Xcode, target iOS 16, SwiftUI, sin dependencias), `server/` con `pyproject.toml` (deps: pynput, zeroconf, pydantic; dev: pytest, pytest-asyncio), `README.md` con cómo correr cada lado, `.gitignore`.
- **Fuera**: cualquier lógica.
- **Hecho cuando**: la app compila y muestra "RemotePad"; `pytest` corre (0 tests) sin error; `python -m remotepad_server` imprime "hola" y sale.

### S-02 Modelos de protocolo (servidor)
- **Objetivo**: `protocol.py` con modelos pydantic de todos los mensajes TCP y encoder/decoder del datagrama UDP.
- **Alcance**: F‑(base para todo). Incluir `gen_vectors.py` que imprime los vectores de prueba de `02-PROTOCOLO.md §4`.
- **Fuera**: sockets.
- **Hecho cuando**: tests cubren parse de cada tipo de mensaje, rechazo de JSON inválido, encode/decode UDP round‑trip, y los bytes del vector de prueba coinciden. Copiar el hex generado dentro de `02-PROTOCOLO.md §4`.

### S-03 Inyector de mouse (servidor)
- **Objetivo**: `injector.py` envolviendo `pynput`.
- **Alcance**: F‑23, F‑24. Métodos `move`, `press`, `release`, `click`, `scroll`, `release_all`. Detección de Wayland con error claro.
- **Fuera**: red.
- **Hecho cuando**: script manual `server/scripts/demo_injector.py` mueve el mouse en cuadrado y hace un clic; tests con `pynput` mockeado verifican llamadas.

---

## Fase 1 — Conexión

### S-04 Descubrimiento mDNS (servidor)
- **Alcance**: F‑20, F‑25 (CLI mínima con `--name`, `--port`, `--udp-port`).
- **Hecho cuando**: `dns-sd -B _remotepad._tcp` (macOS) o `avahi-browse` muestra el servicio con los TXT correctos; al Ctrl+C desaparece.

### S-05 Descubrimiento de hosts (iOS)
- **Alcance**: F‑01. `HostBrowser` con `NWBrowser`, pantalla `HostListView`. `Info.plist` con `NSLocalNetworkUsageDescription` y `NSBonjourServices = ["_remotepad._tcp"]`.
- **Hecho cuando**: con el servidor corriendo, el host aparece en la lista en < 3 s y desaparece al apagarlo; el aviso de permiso denegado se muestra si se rechaza.

### S-06 Canal de control TCP + pairing (servidor)
- **Alcance**: F‑21, F‑22 (sesión única, `busy`), handshake `hello/auth`, `ping/pong`, `storage.py`.
- **Hecho cuando**: tests con cliente asyncio simulado cubren: pairing OK, PIN incorrecto ×5 → `locked`, handshake con token válido, token inválido → `bad_sig`, segundo cliente → `busy`, timeout de ping cierra sesión.

### S-07 Canal de control TCP + pairing (iOS)
- **Alcance**: F‑02, F‑03 (sin reconexión aún). `ControlChannel`, `Signer` (CryptoKit HMAC/HKDF), `PairingFlow`, guardado en Keychain, pantalla de PIN.
- **Hecho cuando**: desde el iPhone se empareja con PIN real, se reinicia la app y conecta sin pedir PIN; la barra de estado se pone verde; los logs del servidor muestran `auth_ok` y pings.

---

## Fase 2 — Pad

### S-08 Canal UDP de movimiento (servidor)
- **Alcance**: F‑23. `motion_server.py` con verificación de firma, anti‑replay, y llamada al inyector.
- **Hecho cuando**: tests cubren paquete válido → `move` llamado; firma mala → descartado; `seq` repetido → descartado; wrap de `seq`; un script de prueba `scripts/send_motion.py` mueve el mouse real desde la misma PC.

### S-09 PadView y movimiento (iOS)
- **Alcance**: F‑04, F‑10. `PadView` con `touchesBegan/Moved/Ended`, `MotionFilter` (sensibilidad fija 1.5 por ahora, acumulación sub‑pixel), `MotionChannel` UDP agrupando a 120 Hz.
- **Fuera**: taps, scroll, ajustes.
- **Hecho cuando**: el cursor de la PC sigue el dedo con fluidez perceptible como "inmediata"; movimientos lentos mueven el cursor 1 px; levantar y reapoyar no salta.

### S-10 GestureEngine — clic, doble clic, clic derecho
- **Alcance**: F‑05, F‑06. Máquina de estados de `01-ARQUITECTURA.md §2`, envío de `btn` por TCP, háptico.
- **Hecho cuando**: tests unitarios del `GestureEngine` con secuencias de touches simuladas (tap, doble tap, tap‑con‑movimiento = no tap, dos dedos) producen exactamente los eventos esperados; en el dispositivo real el clic simple se siente sin retraso y el doble clic abre carpetas.

### S-11 GestureEngine — drag
- **Alcance**: F‑07 (tap‑y‑arrastrar y mantener‑presionado). `release_all` del servidor al perder sesión (ya existe en S‑06, verificar).
- **Hecho cuando**: se puede arrastrar un archivo en el escritorio y seleccionar texto; si la app se cierra a mitad de un drag, el botón se suelta en la PC en < 10 s.

### S-12 Scroll con dos dedos
- **Alcance**: F‑08 (cliente y servidor), mensaje `cfg` con `natural_scroll`.
- **Hecho cuando**: scroll en un navegador es suave y respeta la dirección configurada; tests del servidor cubren inversión.

---

## Fase 3 — Pulido

### S-13 Ajustes
- **Alcance**: F‑09 completo. `SettingsStore`, pantalla, aplicación en vivo.
- **Hecho cuando**: cambiar sensibilidad se nota sin reconectar; los valores persisten tras reiniciar la app.

### S-14 Reconexión y modo debug
- **Alcance**: F‑03 (backoff, background/foreground), overlay debug con RTT del ping y paquetes/s.
- **Hecho cuando**: apagar y prender el servidor con el Pad abierto reconecta solo en < 5 s; bloquear y desbloquear el iPhone reconecta; el RTT mostrado en LAN es < 10 ms.

### S-15 Robustez del servidor
- **Alcance**: F‑22 completo, F‑25 (log‑level, mensajes de arranque, aviso de Accesibilidad en macOS), manejo de excepciones para que ningún paquete malformado tire el proceso.
- **Hecho cuando**: enviar basura aleatoria a ambos puertos durante 60 s no cierra el servidor; después de eso una sesión normal sigue funcionando.

### S-16 Documentación de uso y checklist de release
- **Alcance**: README final (instalar servidor por SO, permisos, cómo compilar la app en el iPhone propio), sección de troubleshooting (permiso Red local, firewall de Windows en puertos 52100/52101, Wayland).
- **Hecho cuando**: una persona que no participó del proyecto lo instala siguiendo sólo el README.

---

## Backlog (v2, no tomar)
- TLS en TCP. · Teclado remoto. · Gestos de 3 dedos (cambiar ventana). · Fallback WebSocket. · Multi‑host y cambio rápido. · Wayland vía `evdev`/`uinput`. · Empaquetado firmado. · iPad.
