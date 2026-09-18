# RemotePad

iPhone como trackpad inalámbrico para la PC, sin botones en pantalla, pensado para usarse con el brazo relajado.

## Estructura del repositorio

```
remotepad/
├── docs/                    ← documentación del proyecto (leer antes de tocar código)
│   └── SIDELOAD.md          ← guía completa para instalar en el iPhone sin Mac
├── .github/workflows/       ← CI: tests del server + build iOS (macos-latest)
├── ios/
│   ├── project.yml          ← spec de XcodeGen (el .xcodeproj se genera en CI, no vive en el repo)
│   └── RemotePad/           ← fuentes Swift (App/, Discovery/, Transport/, Pairing/, Pad/, Settings/)
├── server/                  ← servidor Python (host PC)
│   ├── remotepad_server/
│   ├── tests/
│   └── pyproject.toml
└── README.md
```

## Cómo correr el servidor (PC)

Requiere Python 3.11+.

```bash
cd server
python -m venv .venv
.venv/Scripts/activate       # Windows; en macOS/Linux: source .venv/bin/activate
pip install -e ".[dev]"
pytest                       # 104 tests, deberían quedar todos verdes
remotepad-server              # o: python -m remotepad_server -- arranca control (TCP), movimiento (UDP) y anuncio mDNS
```

Opciones de `remotepad-server` (ver `server/remotepad_server/main.py`):

| Flag | Default | Qué hace |
|---|---|---|
| `--name` | hostname de la PC | Nombre que ve el iPhone al buscar hosts |
| `--port` | `52100` | Puerto TCP de control |
| `--udp-port` | `52101` | Puerto UDP de movimiento |
| `--log-level` | `INFO` | `DEBUG`/`INFO`/`WARNING`/`ERROR`/`CRITICAL` |

El PIN de emparejamiento (6 dígitos, expira a los 60 s) se imprime en esta misma consola cuando el iPhone inicia el pairing.

### Por sistema operativo

- **Windows**: `pynput` no pide permisos especiales. Si el iPhone no encuentra el host, revisar el firewall (ver Troubleshooting abajo).
- **macOS**: el proceso que corre `remotepad-server` (Terminal, o el ejecutable si se empaqueta con `pyinstaller`) necesita permiso de **Accesibilidad**: Ajustes del Sistema → Privacidad y Seguridad → Accesibilidad. El servidor avisa en la consola si falta.
- **Linux**: solo **X11**. Si `$XDG_SESSION_TYPE=wayland`, el servidor aborta al arrancar con un mensaje explícito — iniciar sesión en X11/Xorg.

## Cómo instalar la app en el iPhone (sin Mac)

Thomas no tiene Mac — el flujo es 100% distinto al de "abrir Xcode y darle Run". Resumen (guía completa y con todos los comandos en **`docs/SIDELOAD.md`**):

1. Pushear este repo a GitHub (`gh repo create remotepad --private --source=. --remote=origin && git push -u origin master`, o a mano desde github.com).
2. Crear un Apple ID de desarrollador (el gratuito alcanza para empezar) y generar certificado + provisioning profile desde la web de developer.apple.com (sin Xcode) — cargarlos como GitHub Secrets.
3. El workflow `.github/workflows/ios-build.yml` compila y firma el `.ipa` en un runner `macos-latest` y lo deja como artifact descargable.
4. Instalar **Sideloadly** (sideloadly.io) en la netbook Windows, conectar el iPhone 14 por cable, arrastrar el `.ipa`, firmar con el Apple ID.
5. En el iPhone: Ajustes → General → VPN y gestión de dispositivos → confiar en el certificado.

Con Apple ID gratis la app deja de abrir a los **7 días** y hay que repetir el sideload con el `.ipa` más reciente; con cuenta paga (u$s99/año) dura 1 año.

## Troubleshooting

**El iPhone no encuentra la PC en la lista de hosts**
- Confirmar que ambos están en la misma red Wi-Fi (no en una red de invitados que aísla clientes).
- iOS pide permiso de **Red Local** la primera vez que la app busca hosts (`NSLocalNetworkUsageDescription`) — si se rechazó, Ajustes → RemotePad → activar "Red Local".
- **Firewall de Windows**: por default bloquea el tráfico entrante a `remotepad-server`. Abrir los puertos (PowerShell como administrador):
  ```powershell
  New-NetFirewallRule -DisplayName "RemotePad TCP" -Direction Inbound -Protocol TCP -LocalPort 52100 -Action Allow
  New-NetFirewallRule -DisplayName "RemotePad UDP" -Direction Inbound -Protocol UDP -LocalPort 52101 -Action Allow
  ```
  (equivalente con `netsh`: `netsh advfirewall firewall add rule name="RemotePad TCP" dir=in action=allow protocol=TCP localport=52100`, e igual para UDP 52101).
- **Linux con Wayland**: `remotepad-server` aborta al arrancar con un error explícito — no es un bug, es la limitación documentada de `pynput` (solo X11 en v1). Iniciar sesión en X11/Xorg.

**El `.ipa` dejó de abrir en el iPhone**
- Apple ID gratis: expira a los 7 días. Volver a bajar el `.ipa` del último run verde en GitHub Actions y repetir el sideload (`docs/SIDELOAD.md §4`). Con cuenta de pago (u$s99/año) dura 1 año.

**"No signing certificate found" en el job `build-signed-device` del CI**
- El `.p12` cargado como secret no coincide con el certificado del provisioning profile, o `APPLE_CERTIFICATE_PASSWORD` está mal. Ver `docs/SIDELOAD.md §3`.

**Un dispositivo distinto se conecta y mueve el mouse**
- No debería pasar: cada paquete UDP y cada mensaje TCP post-auth van firmados con HMAC-SHA256 sobre un token derivado por HKDF del PIN de pairing (`docs/01-ARQUITECTURA.md §5`). Si pasa, es un bug — revisar que el PIN no haya quedado visible/compartido y reportarlo.

## Cómo usar los docs con una IA

Pegar al inicio de cada sesión (o cargar como contexto de proyecto), en este orden:

1. `docs/00-CONTEXTO.md` — qué es, alcance, decisiones cerradas, reglas. **Siempre.**
2. `docs/01-ARQUITECTURA.md` — stack, módulos, máquina de estados de gestos, latencia, seguridad.
3. `docs/02-PROTOCOLO.md` — formato exacto de mensajes TCP y UDP. Fuente de verdad para ambos lados.
4. `docs/03-ESPECIFICACIONES-FUNCIONALES.md` — comportamiento detallado por funcionalidad (`F-xx`).
5. `docs/04-STORIES.md` — orden de implementación, una story por PR, con criterio de "hecho".

Prompt sugerido para arrancar una story:

```
Leé docs/00-CONTEXTO.md, 01-ARQUITECTURA.md, 02-PROTOCOLO.md y 03-ESPECIFICACIONES-FUNCIONALES.md.
Vamos a implementar la story S-xx de docs/04-STORIES.md. Antes de escribir código, listá los archivos
que vas a crear/modificar y qué tests vas a agregar. No implementes nada fuera del alcance de la story.
```

## Resumen técnico en 5 líneas

- iOS: Swift/SwiftUI + UIKit touches, `Network.framework`, `CryptoKit`. Sin dependencias.
- PC: Python 3.11, `pynput` + `zeroconf` + `asyncio`. Windows / macOS / Linux X11.
- Descubrimiento por Bonjour, control por TCP/JSON, movimiento por UDP binario a 120 Hz.
- Pairing por PIN → token HKDF; cada paquete firmado con HMAC, anti‑replay por `seq`.
- Gestos: 1 dedo mueve · tap clic · doble tap doble clic · 2 dedos tap clic derecho · tap‑y‑arrastrar drag · 2 dedos deslizar scroll.
