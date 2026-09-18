# RemotePad — Stories de implementación

Orden obligatorio. Cada story es una rama `story/S-xx-nombre` y un PR. No empezar la siguiente sin cerrar la anterior. Cada una referencia funcionalidades (`F-xx`) de `03-ESPECIFICACIONES-FUNCIONALES.md`.

Formato: **Objetivo · Alcance · Fuera de alcance · Hecho cuando**.

> Thomas no tiene Mac (netbook Windows + iPhone 14). Toda story de iOS que diga "compila" o "en el dispositivo real" se verifica vía el pipeline de CI de S-05, no con Xcode local. Ver `00-CONTEXTO.md §4bis`.

---

## Fase 0 — Base

### S-01 Scaffold del repositorio
- **Objetivo**: estructura vacía pero funcional en ambos lados.
- **Alcance**: crear `ios/RemotePad` (fuentes Swift, target iOS 16, SwiftUI, sin dependencias — el `.xcodeproj` lo genera el CI de S-05, no Xcode local), `server/` con `pyproject.toml` (deps: pynput, zeroconf, pydantic; dev: pytest, pytest-asyncio), `README.md` con cómo correr cada lado, `.gitignore`.
- **Fuera**: cualquier lógica.
- **Hecho cuando**: `pytest` corre (0 tests) sin error; `python -m remotepad_server` imprime "hola" y sale; los `.swift` de `App/` existen y quedan pendientes de compilar en CI (S-05).
- **Estado**: hecho. Commit `c215190`.

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
- **Estado**: hecho (tests). El script manual no se corrió en esta sesión — requiere ejecutarlo a mano en la PC real, moverá el mouse de verdad.

---

## Fase 1 — Conexión

### S-04 Descubrimiento mDNS (servidor)
- **Alcance**: F‑20, F‑25 (CLI mínima con `--name`, `--port`, `--udp-port`).
- **Hecho cuando**: `dns-sd -B _remotepad._tcp` (si hay macOS a mano) o, en Windows, un cliente `zeroconf` de prueba (`server/scripts/browse.py`) muestra el servicio con los TXT correctos; al Ctrl+C desaparece.
- **Estado**: hecho (tests, `DiscoveryAnnouncer` con Zeroconf real inyectable). La verificación manual con `browse.py` contra un `remotepad-server` corriendo no se ejecutó en esta sesión.

### S-05 CI de build iOS + firma + Sideloadly
- **Objetivo**: dejar un pipeline que compile la app en un runner `macos-latest` de GitHub Actions y produzca un `.ipa` instalable con Sideloadly desde la netbook Windows, sin depender de una Mac física.
- **Alcance**:
  - Requiere repo en GitHub (push del repo local) y una cuenta Apple ID de Thomas (gratis para arrancar).
  - Generar el `.xcodeproj` real (a mano, una única vez, usando el propio runner de CI o el asistente de `xcodegen`/`tuist` para no depender de Xcode local ni siquiera para crear el proyecto).
  - `.github/workflows/ios-build.yml`: checkout, `xcodebuild -scheme RemotePad -sdk iphoneos build`, firma con certificado + provisioning profile guardados como *GitHub Secrets* (nunca en el repo), sube el `.ipa` como artifact.
  - `docs/SIDELOAD.md`: instrucciones para instalar Sideloadly en Windows, cargar el `.ipa` descargado del artifact, firmar con el mismo Apple ID, confiar el certificado en el iPhone.
- **Fuera**: cualquier lógica de la app más allá del scaffold de S-01.
- **Hecho cuando**: push a `master` dispara el workflow, termina en verde, y el `.ipa` descargado se instala en el iPhone 14 de Thomas con Sideloadly mostrando la pantalla "RemotePad" de S-01.
- **Nota**: con Apple ID gratis el `.ipa` expira a los 7 días (hay que repetir el sideload); es aceptable para desarrollo. Evaluar cuenta paga si molesta.
- **Estado**: pipeline escrito (`ios/project.yml`, `.github/workflows/ios-build.yml` con job sin firmar + job firmado condicionado a secrets, `.github/workflows/server-tests.yml`, `docs/SIDELOAD.md`), pero **nunca ejecutado** — no hay `gh`/Swift acá para probarlo, y requiere repo en GitHub + secrets de Apple que solo Thomas puede cargar. Es la parte de todo este trabajo con más chance de necesitar un ajuste al primer intento real.

### S-06 Descubrimiento de hosts (iOS)
- **Alcance**: F‑01. `HostBrowser` con `NWBrowser`, pantalla `HostListView`. `Info.plist` con `NSLocalNetworkUsageDescription` y `NSBonjourServices = ["_remotepad._tcp"]`.
- **Hecho cuando**: con el servidor corriendo, el host aparece en la lista en < 3 s y desaparece al apagarlo; el aviso de permiso denegado se muestra si se rechaza. Verificado en el iPhone real vía el pipeline de S-05.
- **Estado**: escrito, sin verificar (requiere build en CI, ver S-05). La detección de "permiso denegado" (`HostBrowser.scheduleWaitingCheck`) es una heurística (browser encallado en `.waiting` 3s) porque no se pudo confirmar contra la documentación real de Apple en esta sesión (sin acceso de red confiable) qué error expone `NWBrowser` para ese caso puntual — revisar en dispositivo real.

### S-07 Canal de control TCP + pairing (servidor)
- **Alcance**: F‑21, F‑22 (sesión única, `busy`), handshake `hello/auth`, `ping/pong`, `storage.py`.
- **Hecho cuando**: tests con cliente asyncio simulado cubren: pairing OK, PIN incorrecto ×5 → `locked`, handshake con token válido, token inválido → `bad_sig`, segundo cliente → `busy`, timeout de ping cierra sesión.
- **Estado**: hecho. Tests con clientes asyncio reales sobre loopback (no mocks de red) — 30 tests nuevos. Se incluyó también el manejo de `btn`/`cfg` (F-24), que ninguna otra story tenía asignado explícitamente; ver nota al principio de `control_server.py`.

### S-08 Canal de control TCP + pairing (iOS)
- **Alcance**: F‑02, F‑03 (sin reconexión aún). `ControlChannel`, `Signer` (CryptoKit HMAC/HKDF), `PairingFlow`, guardado en Keychain, pantalla de PIN.
- **Hecho cuando**: desde el iPhone se empareja con PIN real, se reinicia la app y conecta sin pedir PIN; la barra de estado se pone verde; los logs del servidor muestran `auth_ok` y pings.
- **Estado**: escrito, sin verificar (requiere build en CI, ver S-05). `Signer.swift` replica byte a byte la firma/HKDF de `session.py` — no se pudo correr `swift test` en esta sesión para confirmarlo cruzado contra el server real; es lo primero a probar cuando haya build. La barra de estado verde/amarillo/rojo (parte de F-03) queda pendiente de S-15 (reconexión).

---

## Fase 2 — Pad

### S-09 Canal UDP de movimiento (servidor)
- **Alcance**: F‑23. `motion_server.py` con verificación de firma, anti‑replay, y llamada al inyector.
- **Hecho cuando**: tests cubren paquete válido → `move` llamado; firma mala → descartado; `seq` repetido → descartado; wrap de `seq`; un script de prueba `scripts/send_motion.py` mueve el mouse real desde la misma PC.

### S-10 PadView y movimiento (iOS)
- **Alcance**: F‑04, F‑10. `PadView` con `touchesBegan/Moved/Ended`, `MotionFilter` (sensibilidad fija 1.5 por ahora, acumulación sub‑pixel), `MotionChannel` UDP agrupando a 120 Hz.
- **Fuera**: taps, scroll, ajustes.
- **Hecho cuando**: el cursor de la PC sigue el dedo con fluidez perceptible como "inmediata"; movimientos lentos mueven el cursor 1 px; levantar y reapoyar no salta.

### S-11 GestureEngine — clic, doble clic, clic derecho
- **Alcance**: F‑05, F‑06. Máquina de estados de `01-ARQUITECTURA.md §2`, envío de `btn` por TCP, háptico.
- **Hecho cuando**: tests unitarios del `GestureEngine` con secuencias de touches simuladas (tap, doble tap, tap‑con‑movimiento = no tap, dos dedos) producen exactamente los eventos esperados; en el dispositivo real el clic simple se siente sin retraso y el doble clic abre carpetas.

### S-12 GestureEngine — drag
- **Alcance**: F‑07 (tap‑y‑arrastrar y mantener‑presionado). `release_all` del servidor al perder sesión (ya existe en S‑07, verificar).
- **Hecho cuando**: se puede arrastrar un archivo en el escritorio y seleccionar texto; si la app se cierra a mitad de un drag, el botón se suelta en la PC en < 10 s.

### S-13 Scroll con dos dedos
- **Alcance**: F‑08 (cliente y servidor), mensaje `cfg` con `natural_scroll`.
- **Hecho cuando**: scroll en un navegador es suave y respeta la dirección configurada; tests del servidor cubren inversión.

---

## Fase 3 — Pulido

### S-14 Ajustes
- **Alcance**: F‑09 completo. `SettingsStore`, pantalla, aplicación en vivo.
- **Hecho cuando**: cambiar sensibilidad se nota sin reconectar; los valores persisten tras reiniciar la app.

### S-15 Reconexión y modo debug
- **Alcance**: F‑03 (backoff, background/foreground), overlay debug con RTT del ping y paquetes/s.
- **Hecho cuando**: apagar y prender el servidor con el Pad abierto reconecta solo en < 5 s; bloquear y desbloquear el iPhone reconecta; el RTT mostrado en LAN es < 10 ms.

### S-16 Robustez del servidor
- **Alcance**: F‑22 completo, F‑25 (log‑level, mensajes de arranque, aviso de Accesibilidad en macOS), manejo de excepciones para que ningún paquete malformado tire el proceso.
- **Hecho cuando**: enviar basura aleatoria a ambos puertos durante 60 s no cierra el servidor; después de eso una sesión normal sigue funcionando.

### S-17 Documentación de uso y checklist de release
- **Alcance**: README final (instalar servidor por SO, permisos, cómo instalar la app en el iPhone vía CI + Sideloadly), sección de troubleshooting (permiso Red local, firewall de Windows en puertos 52100/52101, Wayland, expiración del `.ipa` a los 7 días con Apple ID gratis).
- **Hecho cuando**: una persona que no participó del proyecto lo instala siguiendo sólo el README.

---

## Backlog (v2, no tomar)
- TLS en TCP. · Teclado remoto. · Gestos de 3 dedos (cambiar ventana). · Fallback WebSocket. · Multi‑host y cambio rápido. · Wayland vía `evdev`/`uinput`. · Empaquetado firmado. · iPad. · Cuenta Apple Developer paga (si la expiración de 7 días molesta antes).
