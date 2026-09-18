# RemotePad

iPhone como trackpad inalámbrico para la PC, sin botones en pantalla, pensado para usarse con el brazo relajado.

## Estructura del repositorio

```
remotepad/
├── docs/                 ← documentación del proyecto (leer antes de tocar código)
├── ios/RemotePad/        ← proyecto Xcode (cliente iOS)
├── server/               ← servidor Python (host PC)
│   ├── remotepad_server/
│   ├── tests/
│   └── pyproject.toml
└── README.md
```

## Cómo correr el servidor (PC)

```bash
cd server
python -m venv .venv
.venv/Scripts/activate       # Windows; en macOS/Linux: source .venv/bin/activate
pip install -e ".[dev]"
python -m remotepad_server   # S-01: solo imprime "hola" y sale
pytest                       # 0 tests por ahora
```

## Cómo correr la app (iPhone)

El `.xcodeproj` se crea en Xcode (macOS) — ver `ios/SETUP.md` para los pasos exactos. Una vez creado:

1. Abrir `ios/RemotePad.xcodeproj` en Xcode.
2. Conectar el iPhone por cable, seleccionarlo como destino.
3. Product → Run. La primera vez, en el iPhone: Ajustes → General → VPN y gestión de dispositivos → confiar en el certificado de desarrollador.

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
