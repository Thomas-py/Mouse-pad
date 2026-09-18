# RemotePad — Especificaciones funcionales

Cada funcionalidad tiene un código `F-xx` que las stories (`04-STORIES.md`) referencian.

## Cliente iOS

### F-01 Descubrimiento de hosts
- Al abrir la app se muestra la lista de hosts encontrados por Bonjour (`_remotepad._tcp`), con nombre, SO (ícono) y estado (`emparejado` / `nuevo`).
- La lista se actualiza en vivo al aparecer/desaparecer hosts.
- Si el permiso "Red local" está denegado, mostrar aviso con botón a Ajustes del sistema.
- Si no hay hosts a los 5 s, mostrar texto: "Asegurate de que el servidor esté corriendo en la misma Wi‑Fi" + botón **"Conectar por IP"**.
- **Fallback manual** (agregado tras probar en un router de ISP que bloquea multicast mDNS aunque el resto de la LAN funcione — ver `00-CONTEXTO.md §4bis`): ícono en la barra superior y botón en el estado vacío abren una pantalla para tipear la IP de la PC directamente, sin pasar por Bonjour. Asume los puertos default del servidor (52100 TCP / 52101 UDP); si el usuario cambió `--port`/`--udp-port`, no alcanza.

### F-02 Emparejamiento
- Tocar un host `nuevo` abre pantalla de PIN (6 dígitos, teclado numérico, autofocus).
- El PIN aparece en la consola del servidor.
- PIN incorrecto: mensaje inline, sin cerrar la pantalla. 5 fallos: mostrar "Bloqueado 5 minutos".
- Éxito: token guardado en Keychain con `kSecAttrAccessibleAfterFirstUnlock`; el host pasa a `emparejado` y se conecta automáticamente.
- Opción "Olvidar host" en la lista (swipe) borra el token.

### F-03 Conexión y estado
- Tocar un host emparejado conecta (handshake) y abre el Pad.
- Indicador de estado en la parte superior del Pad (barra fina): verde conectado, amarillo reconectando, rojo sin conexión. Sin texto salvo en amarillo/rojo.
- Reconexión automática con backoff 0.5 s → 1 s → 2 s → 4 s (máx), mientras el Pad esté visible.
- Al ir a background, cerrar sockets. Al volver, reconectar.
- La app mantiene la pantalla encendida mientras el Pad está activo (`isIdleTimerDisabled = true`).

### F-04 Pad — movimiento
- Toda la pantalla (menos la barra de estado de 4 pt y una zona superior de 24 pt para salir con swipe‑down) es superficie de pad.
- Un dedo deslizando mueve el cursor. Se envían deltas relativos a 120 Hz.
- Sub‑pixel accumulation: movimientos muy lentos deben mover el cursor 1 px eventualmente, no quedarse en 0.
- Levantar el dedo y volver a apoyar en otro lugar **no** mueve el cursor (es relativo, como un trackpad).

### F-05 Pad — clic y doble clic
- Tap con un dedo = clic izquierdo. Se envía inmediatamente (sin esperar la ventana de doble tap).
- Segundo tap dentro de 250 ms = se envía otro clic; la PC lo interpreta como doble clic.
- Un tap que se mueve más de 10 pt o dura más de 180 ms no es tap.
- Feedback háptico ligero (`UIImpactFeedbackGenerator .light`) en cada tap. Se puede desactivar.

### F-06 Pad — clic derecho
- Tap con dos dedos simultáneos (ambos bajan y suben dentro de 180 ms, sin moverse) = clic derecho.
- Háptico medio.

### F-07 Pad — arrastre (drag)
- Tap y luego volver a apoyar dentro de 250 ms y mover = `down` izquierdo + movimiento + `up` al soltar.
- Si `tapToDrag` está desactivado en ajustes, este gesto no existe y el segundo tap es un doble clic normal.
- Alternativa siempre disponible: mantener presionado 400 ms sin mover → háptico → drag hasta soltar.

### F-08 Pad — scroll
- Dos dedos deslizando = scroll. Se usa el delta promedio de ambos dedos.
- Escala: 1 "línea" cada 12 pt de desplazamiento. Se acumula resto.
- Dirección: cruda desde el cliente; el servidor invierte si `natural_scroll` está activo.

### F-09 Ajustes
| Ajuste | Rango / valores | Default |
|---|---|---|
| Sensibilidad | 0.5 – 3.0 | 1.5 |
| Aceleración | 0 – 0.05 | 0.02 |
| Scroll natural | on/off | on |
| Tap para arrastrar | on/off | on |
| Háptico | on/off | on |
| Mostrar debug (RTT, pps) | on/off | off |
- Persisten en `UserDefaults`. Se aplican al instante, sin reconectar.

### F-10 Salir del Pad
- Swipe hacia abajo desde la franja superior de 24 pt, o botón "Cerrar" que aparece al tocar esa franja. Vuelve a la lista de hosts sin desconectar.

## Servidor PC

### F-20 Anuncio mDNS
- Al iniciar, registra el servicio con los TXT de `02-PROTOCOLO.md`. Al cerrar (Ctrl+C), lo desregistra limpiamente.
- `--name` configurable; default: hostname del sistema.

### F-21 Pairing
- `pair_start` genera PIN aleatorio de 6 dígitos, lo imprime grande en consola y arranca timer de 60 s.
- Verifica `proof`; 5 fallos → bloqueo 5 min por `client_id`.
- Guarda `{client_id, client_name, token, paired_at}` en `~/.remotepad/tokens.json` (permisos 600).

### F-22 Sesiones
- Una sola sesión activa a la vez. Un segundo cliente recibe `busy`.
- Sesión se cierra por: cierre de TCP, 10 s sin `ping`, `bad_sig` en TCP.
- Al cerrar sesión, soltar cualquier botón que haya quedado presionado (`release all`) para no dejar un drag colgado.

### F-23 Inyección de movimiento
- Aplica `move(dx, dy)` con `pynput` por cada evento del datagrama, en orden.
- Descarta paquetes según reglas del protocolo; loguea descartes a nivel DEBUG con contador.

### F-24 Inyección de botones y scroll
- `btn` → `press`/`release`/`click(n)`.
- `scroll` → `Controller.scroll(dx, dy)` invirtiendo `dy` si `natural_scroll`.

### F-25 CLI y logs
- `remotepad-server [--name NOMBRE] [--port 52100] [--udp-port 52101] [--log-level INFO]`
- Logs con `logging` a stdout; nivel DEBUG muestra cada evento.
- Al arrancar imprime: nombre, puertos, SO, y en macOS si falta permiso de Accesibilidad.

### F-26 Empaquetado (opcional, v1.1)
- `pyinstaller --onefile` para Windows y macOS. Fuera del alcance de las stories obligatorias.
