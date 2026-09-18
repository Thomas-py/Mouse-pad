# RemotePad — Arquitectura y tecnología

## 1. Vista general

```
┌──────────────────────┐        Wi‑Fi / LAN        ┌──────────────────────────┐
│ iPhone (Cliente)     │                           │ PC (Host)                │
│                      │  mDNS  _remotepad._tcp    │                          │
│  PadView (gestos)    │ ◄────────────────────────►│  Discovery (zeroconf)    │
│      │               │                           │                          │
│  GestureEngine       │  TCP 52100  control/JSON  │  ControlServer (asyncio) │
│      │               │ ◄────────────────────────►│      │                   │
│  Transport           │  UDP 52101  motion/binary │  MotionServer (asyncio)  │
│   ├─ ControlChannel  │ ────────────────────────► │      │                   │
│   └─ MotionChannel   │                           │  InputInjector (pynput)  │
└──────────────────────┘                           └──────────────────────────┘
```

Flujo: el dedo se mueve → `PadView` recibe touches → `GestureEngine` los convierte en intenciones (`move`, `click`, `drag`, `scroll`) → `Transport` los serializa y envía → el servidor los parsea → `InputInjector` mueve/clickea el mouse real.

## 2. Cliente iOS

### Stack
- Swift 5.9+, Xcode 15+, iOS 16 mínimo.
- SwiftUI para pantallas (lista de hosts, ajustes, pairing).
- UIKit `UIView` + `touchesBegan/Moved/Ended` para el pad (no `UIGestureRecognizer` para movimiento: agrega latencia y suaviza demasiado). Se usa `UITapGestureRecognizer` sólo para detectar taps con conteo de dedos.
- `Network.framework` (`NWBrowser` para Bonjour, `NWConnection` para TCP y UDP). Prohibido usar sockets BSD a mano.
- `CryptoKit` para HMAC.
- Sin dependencias externas (SPM vacío).

### Módulos (carpetas dentro de `ios/RemotePad/`)

| Módulo | Responsabilidad |
|---|---|
| `App/` | Entry point, navegación, estado global (`AppState`) |
| `Discovery/` | `HostBrowser`: envuelve `NWBrowser`, publica `[DiscoveredHost]` |
| `Transport/` | `ControlChannel` (TCP), `MotionChannel` (UDP), `PacketEncoder`, `Signer` |
| `Pairing/` | `PairingFlow`: pide PIN, negocia token, lo guarda en Keychain |
| `Pad/` | `PadView` (UIViewRepresentable), `GestureEngine`, `MotionFilter` |
| `Settings/` | `SettingsStore` (UserDefaults), pantalla de ajustes |

### GestureEngine — máquina de estados

Estados: `idle`, `touching`, `moving`, `tapCandidate`, `dragging`, `scrolling`.

Parámetros (constantes en `GestureConfig`, todos editables):
- `tapMaxDuration = 180 ms`
- `tapMaxMovement = 10 pt`
- `doubleTapWindow = 250 ms`
- `dragHoldWindow = 250 ms` (tap y luego apoyar de nuevo dentro de esta ventana = inicio de drag)
- `scrollFingers = 2`
- `sampleRate = 120 Hz` (usar `CADisplayLink` para agrupar deltas)

Reglas:
1. Un dedo baja y se mueve > `tapMaxMovement` → `moving`: cada frame emite `move(dx, dy)`.
2. Un dedo baja y sube antes de `tapMaxDuration` sin moverse → `tapCandidate`. Se espera `doubleTapWindow`:
   - si llega otro tap → `doubleClick`;
   - si el dedo vuelve a bajar y se mueve → `dragStart` + `move…` + `dragEnd` al soltar;
   - si no pasa nada → `click`.
   - **Optimización obligatoria**: enviar el `click` inmediatamente y, si luego llega el segundo tap, enviar un segundo `click` (la PC interpreta dos clics rápidos como doble clic). Así el clic simple no tiene 250 ms de retraso. Excepción: si `tapToDrag` está activo, el segundo apoyo se convierte en drag, no en clic.
3. Dos dedos bajan y suben rápido sin moverse → `rightClick`.
4. Dos dedos bajan y se mueven → `scrolling`: emite `scroll(dx, dy)` con el delta promedio.
5. Cualquier cambio de cantidad de dedos resetea a `idle` salvo que esté en `dragging`.

### MotionFilter
- Aplica `sensibilidad` (multiplicador 0.5–3.0) y `aceleración` (curva `delta * (1 + k * |delta|)`, k configurable, default 0.02).
- Redondea a enteros antes de enviar; acumula el resto para no perder precisión (sub‑pixel accumulation).

## 3. Servidor PC

### Stack
- Python 3.11+.
- `pynput` 1.7+ para inyectar mouse.
- `zeroconf` 0.13x para anunciar el servicio mDNS.
- `asyncio` stdlib para TCP y UDP.
- `pydantic` para validar mensajes JSON.
- `pytest` + `pytest-asyncio` para tests.
- `pyinstaller` (opcional) para empaquetar.

### Módulos (`server/remotepad_server/`)

| Módulo | Responsabilidad |
|---|---|
| `main.py` | CLI (`remotepad-server --name "PC de Thomas" --port 52100`), arranca todo |
| `discovery.py` | Registra `_remotepad._tcp.local.` con TXT: `v=1`, `name=…`, `udp=52101` |
| `control_server.py` | TCP: pairing, handshake, clics, config, keepalive |
| `motion_server.py` | UDP: recibe, verifica firma, aplica deltas |
| `protocol.py` | Modelos pydantic + encoder/decoder binario UDP (compartido con tests) |
| `injector.py` | Wrapper sobre `pynput.mouse.Controller`: `move(dx,dy)`, `press/release(button)`, `click(button, n)`, `scroll(dx,dy)` |
| `session.py` | Estado de sesión: token, cliente activo, último paquete, contador anti‑replay |
| `storage.py` | Persistencia del token en `~/.remotepad/tokens.json` |

### Consideraciones por SO
- **macOS**: requiere permiso de Accesibilidad para el proceso Python/Terminal. Documentar en README.
- **Windows**: `pynput` funciona sin permisos; si se empaqueta con `pyinstaller`, firmar o aceptar warning de SmartScreen.
- **Linux**: sólo X11 en v1 (`pynput` no soporta Wayland). Detectar `$XDG_SESSION_TYPE` y abortar con mensaje claro si es Wayland.

## 4. Latencia — presupuesto

| Etapa | Objetivo |
|---|---|
| Touch → GestureEngine | < 2 ms |
| Agrupado a 120 Hz | ≤ 8 ms |
| Red LAN (UDP) | 1–5 ms |
| Parse + inyección | < 1 ms |
| **Total** | **< 20 ms** |

Medición: story `S-14` incluye un modo debug que muestra RTT del keepalive y paquetes/s.

## 5. Seguridad

1. Pairing por PIN mostrado en la consola del servidor (6 dígitos, expira a los 60 s).
2. Se deriva `token = HKDF(pin + nonce_server + nonce_client)` de 32 bytes. Se guarda en Keychain (iOS) y en `tokens.json` (PC, mapeado a `client_id`).
3. Cada paquete UDP lleva `client_id`, `seq` (uint32 creciente) y `sig` = primeros 8 bytes de `HMAC-SHA256(token, header+payload)`. El servidor rechaza `seq` ≤ último visto (anti‑replay).
4. TCP no va cifrado en v1 (asumido LAN confiable); los mensajes de control después del handshake llevan el mismo esquema de firma. TLS queda para v2.

## 6. Decisiones descartadas (para no volver a discutirlas)

- **Bluetooth HID**: iOS no permite que una app se presente como periférico HID.
- **WebSocket único**: agrega framing y ordenamiento innecesarios para movimiento; queda como fallback si UDP falla (v2).
- **Node + robotjs**: build nativo roto en Node ≥ 20 en varios entornos; `nut-js` requiere licencia para versiones recientes.
- **Posición absoluta**: distinta resolución de pantallas, multi‑monitor y DPI lo hacen frágil; deltas relativos siempre.
