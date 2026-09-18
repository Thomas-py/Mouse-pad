# RemotePad — Protocolo de comunicación v1

Este archivo es la fuente de verdad. El cliente y el servidor implementan exactamente esto. Si algo cambia, se cambia acá primero y se sube `v`.

## 1. Descubrimiento (mDNS / Bonjour)

- Tipo de servicio: `_remotepad._tcp.local.`
- Nombre de instancia: nombre del host configurado (ej. `PC de Thomas`).
- Puerto anunciado: puerto TCP de control (default `52100`).
- Registros TXT:

| Clave | Valor | Ejemplo |
|---|---|---|
| `v` | versión de protocolo | `1` |
| `udp` | puerto UDP de movimiento | `52101` |
| `os` | `windows` / `macos` / `linux` | `windows` |
| `id` | id único del host (uuid4, persistente) | `3f2a…` |

## 2. Canal de control — TCP, JSON

Framing: cada mensaje es un JSON UTF‑8 en una línea, terminado en `\n`. Tamaño máximo 4 KiB.

Todo mensaje tiene:
```json
{ "t": "<tipo>", "id": "<uuid corto del mensaje>", ...campos }
```
Las respuestas incluyen `"re": "<id del mensaje al que responden>"`.

### 2.1 Handshake (cliente ya emparejado)

Cliente → Servidor
```json
{ "t": "hello", "id": "a1", "v": 1, "client_id": "iphone-…", "nonce": "<16 bytes hex>" }
```
Servidor → Cliente
```json
{ "t": "hello_ok", "re": "a1", "nonce": "<16 bytes hex>", "server_name": "PC de Thomas" }
```
o
```json
{ "t": "error", "re": "a1", "code": "unpaired" }
```
Luego el cliente envía `auth`:
```json
{ "t": "auth", "id": "a2", "client_id": "…", "sig": "<hex HMAC(token, nonce_s + nonce_c)>" }
```
```json
{ "t": "auth_ok", "re": "a2", "session": "<uuid>" }
```
A partir de acá **todos** los mensajes del cliente llevan `"sig"` = hex de `HMAC-SHA256(token, session + id + t)` truncado a 16 hex chars.

### 2.2 Pairing (primera vez)

Cliente → Servidor
```json
{ "t": "pair_start", "id": "p1", "v": 1, "client_id": "…", "client_name": "iPhone de Thomas", "nonce": "<hex>" }
```
Servidor imprime PIN en consola y responde:
```json
{ "t": "pair_challenge", "re": "p1", "nonce": "<hex>", "expires_in": 60 }
```
Cliente (con PIN tipeado por el usuario):
```json
{ "t": "pair_answer", "id": "p2", "proof": "<hex HMAC-SHA256(pin_utf8, nonce_s + nonce_c)>" }
```
Servidor:
```json
{ "t": "pair_ok", "re": "p2" }        // ambos derivan token = HKDF-SHA256(ikm=pin, salt=nonce_s+nonce_c, info="remotepad-v1", len=32)
{ "t": "error", "re": "p2", "code": "bad_pin" }   // máx 5 intentos, luego "locked" 5 min
```
Después de `pair_ok` el cliente hace el handshake normal (`hello` → `auth`).

### 2.3 Eventos de botón (fiables)

```json
{ "t": "btn", "id": "b1", "sig": "…", "button": "left" | "right" | "middle", "action": "click" | "down" | "up", "count": 1 }
```
- `click` con `count: 2` = doble clic (el servidor usa `Controller.click(button, 2)`).
- `down`/`up` se usan para drag.
- El servidor **no** responde a `btn` (fire‑and‑forget sobre TCP). Errores de firma cierran la sesión.

### 2.4 Configuración de sesión

```json
{ "t": "cfg", "id": "c1", "sig": "…", "natural_scroll": true }
```
Sólo lo que el servidor necesita saber; sensibilidad y aceleración se aplican en el cliente.

### 2.5 Keepalive

Cada 2 s el cliente envía `{ "t": "ping", "id": "k1", "sig": "…", "ts": <ms epoch> }` y el servidor responde `{ "t": "pong", "re": "k1", "ts": <mismo> }`. Tres pings sin respuesta → el cliente marca "desconectado" y reintenta.

### 2.6 Códigos de error

`unpaired`, `bad_pin`, `locked`, `bad_sig`, `bad_version`, `busy` (otro cliente activo), `internal`.

## 3. Canal de movimiento — UDP, binario

Cada datagrama = **header** + 1..N **eventos**. Big‑endian. Máximo 512 bytes.

### Header (24 bytes)
| Offset | Tam | Campo | Descripción |
|---|---|---|---|
| 0 | 2 | magic | `0x52 0x50` ("RP") |
| 2 | 1 | version | `1` |
| 3 | 1 | count | cantidad de eventos (1–32) |
| 4 | 4 | seq | uint32, creciente por cliente, reinicia en 0 al reconectar |
| 8 | 8 | client_hash | primeros 8 bytes de SHA‑256(client_id) |
| 16 | 8 | sig | primeros 8 bytes de HMAC‑SHA256(token, bytes[0..16] + eventos) |

### Evento (6 bytes)
| Offset | Tam | Campo | Descripción |
|---|---|---|---|
| 0 | 1 | kind | `0x01` move, `0x02` scroll |
| 1 | 1 | flags | reservado, `0` |
| 2 | 2 | dx | int16, píxeles (ya con sensibilidad aplicada) |
| 4 | 2 | dy | int16 |

Para `scroll`, `dx`/`dy` están en "líneas" (int16, normalmente −10..10). Signo ya ajustado según `natural_scroll` **no**: el servidor invierte según `cfg`, el cliente manda el gesto crudo (dedo arriba = dy negativo).

### Reglas del servidor
1. Descartar si `magic`/`version` no coinciden.
2. Descartar si `client_hash` no corresponde a la sesión activa.
3. Verificar `sig`; si falla, descartar y loguear (no cerrar sesión: UDP puede traer basura).
4. Descartar si `seq` ≤ último aceptado (con ventana: aceptar si `seq > last` o si `last - seq > 2^31` por wrap).
5. Aplicar eventos en orden.

### Reglas del cliente
1. Agrupar todos los deltas de un frame (`CADisplayLink` a 120 Hz) en un solo datagrama.
2. Nunca enviar más de 120 datagramas/s.
3. Si no hay movimiento, no enviar nada (no hay heartbeat en UDP; eso es el `ping` TCP).

## 4. Vectores de prueba

Para los tests del encoder/decoder (ambos lados deben producir exactamente estos bytes):

```
token      = 32 bytes 0x00..0x1F
client_id  = "test-client"
seq        = 7
eventos    = [move(dx=3, dy=-2)]

bytes esperados (hex completo, generado por `server/tests/gen_vectors.py`):
52 50 01 01 00 00 00 07 D5 FE 82 51 31 96 CA 97 19 70 FC 7A BE 0F 4D 6F 01 00 00 03 FF FE

Desglosado:
- header sin sig: `52 50 01 01 00 00 00 07 D5 FE 82 51 31 96 CA 97` (magic, version, count, seq, client_hash)
- sig: `19 70 FC 7A BE 0F 4D 6F`
- evento move(dx=3, dy=-2): `01 00 00 03 FF FE`
```
`client_hash` = SHA-256("test-client")[:8]. `sig` = HMAC-SHA256(token=bytes(range(32)), header_sin_sig + evento)[:8]. Regenerar con `python -m tests.gen_vectors` desde `server/` si cambia el formato; el resultado debe coincidir byte a byte con lo de arriba (test `test_protocol.py::test_vector_matches_docs`) y con lo que implemente el cliente iOS.
