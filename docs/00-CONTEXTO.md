# RemotePad — Contexto del proyecto

> Leer este archivo COMPLETO antes de tocar cualquier código. Todo lo que no esté acá o en los demás archivos de `/remotepad` NO está decidido: preguntar antes de asumir.

## 1. Qué es

RemotePad convierte un iPhone en un trackpad inalámbrico para una PC en la misma red local (LAN/Wi‑Fi). El usuario apoya el celular donde tenga la mano (sobre la pierna, el apoyabrazos, la mesa) y mueve el cursor de la PC deslizando el dedo por la pantalla. **No hay botones en pantalla**: toda la superficie es el pad. Clic, doble clic, clic derecho, arrastre y scroll se hacen con gestos.

## 2. Problema que resuelve

Usar un mouse obliga a tener el brazo levantado sobre el escritorio. El objetivo es poder controlar el cursor con el brazo relajado y abajo, con latencia imperceptible (< 30 ms en LAN).

## 3. Alcance del MVP (v1)

**Incluido**
- App iOS (iPhone) que descubre la PC en la red y se conecta con un tap.
- Servidor en la PC (Windows 10/11, macOS y Linux X11) que inyecta eventos de mouse.
- Gestos: mover, tap = clic izquierdo, doble tap = doble clic, tap con dos dedos = clic derecho, tap‑y‑arrastrar = drag, dos dedos deslizando = scroll.
- Ajustes: sensibilidad, aceleración, scroll natural/inverso, tap-to-click on/off.
- Emparejamiento con PIN de 6 dígitos la primera vez.

**Excluido (no implementar en v1)**
- Teclado remoto, gestos de 3+ dedos, multi‑PC, iPad, App Store, Bluetooth, control fuera de la LAN, Wayland en Linux.

## 4. Decisiones ya tomadas (no reabrir sin hablar con Thomas)

| Tema | Decisión | Por qué |
|---|---|---|
| App móvil | Swift 5.9+, SwiftUI + UIKit para gestos, iOS 16+ | Acceso nativo a gestos de baja latencia; nada de React Native/Flutter para gestos de 60–120 Hz |
| Transporte | UDP para movimiento/scroll, TCP para control (pairing, clics, config) | UDP no bloquea ni reordena en cola; perder un delta de movimiento es aceptable, perder un clic no |
| Descubrimiento | Bonjour / mDNS (`_remotepad._tcp`) | Cero configuración; el usuario no tipea IPs |
| Servidor PC | Python 3.11+ con `pynput` (inyección), `zeroconf` (mDNS), `asyncio` (sockets) | `pynput` es multiplataforma y estable; las libs Node de inyección (`robotjs`, `nut-js`) tienen builds rotos o licencias pagas |
| Formato mensajes | JSON en TCP, binario compacto en UDP | Debug fácil donde no importa el tamaño; eficiencia donde sí |
| Seguridad v1 | PIN en pairing + token compartido firmando cada paquete UDP (HMAC‑SHA256 truncado) | Evitar que otro dispositivo de la red mueva el mouse |
| Distribución iOS | Build en CI (GitHub Actions, runner `macos-latest`) + instalación con **Sideloadly** desde la netbook Windows | Thomas no tiene Mac. Sin Mac no hay Xcode local posible (no existe SDK de iOS para Windows). Apple ID gratis: el `.ipa` expira a los 7 días y hay que reinstalar; con cuenta de pago (u$s99/año) dura 1 año — decisión de Thomas, no bloqueante para empezar |
| Distribución PC | Script Python + `pyinstaller` opcional | Mínimo esfuerzo |

## 4bis. Sin Mac — implicancias

- **No hay Xcode local.** Todo build de la app se hace en CI (`macos-latest`). Nadie en este proyecto abre Xcode a mano; los `.swift` se escriben como texto y el CI los compila.
- **Firma de código**: requiere Apple ID + certificado de desarrollo. Los secretos (Apple ID, contraseña de aplicación, certificado `.p12`, provisioning profile) van como *GitHub Secrets*, nunca en el repo ni en el chat.
- **Instalación en el iPhone 14**: `.ipa` generado por CI → Sideloadly (Windows, por cable) → confiar en el certificado en Ajustes → General → VPN y gestión de dispositivos.
- **Iteración más lenta** que con Xcode local: cada cambio de UI pasa por push → CI → descarga de artifact → sideload. Evaluar `xcodebuild -parallelizeTargets` y builds incrementales cuando moleste.
- El workflow de CI y el detalle de firma se resuelven en una story dedicada antes de necesitar correr algo en el dispositivo real (ver `04-STORIES.md`, story de CI/distribución).

## 5. Restricciones duras

- La app **no** debe requerir permisos de ubicación ni Bluetooth. Solo "Local Network" (obligatorio en iOS 14+ para mDNS/UDP local).
- El servidor **no** abre puertos hacia internet. Solo escucha en interfaces locales.
- Nunca enviar posición absoluta desde el teléfono: siempre **deltas relativos** (dx, dy). La posición absoluta la conoce sólo la PC.
- Frecuencia máxima de envío de movimiento: 120 paquetes/s. Agrupar deltas si el gesto genera más.
- Nada de dependencias no listadas en `01-ARQUITECTURA.md` sin justificarlo en el PR.

## 6. Glosario

- **Delta**: desplazamiento relativo del dedo entre dos muestras, en puntos de pantalla del iPhone.
- **Pad**: la vista a pantalla completa que captura gestos.
- **Host**: la PC que corre el servidor.
- **Cliente**: la app iOS.
- **Sesión**: conexión TCP viva + token acordado.
- **Pairing**: primer intercambio con PIN que genera el token persistente.

## 7. Estructura del repositorio

```
remotepad/
├── docs/                 ← estos archivos
├── ios/RemotePad/        ← proyecto Xcode
├── server/               ← servidor Python
│   ├── remotepad_server/
│   ├── tests/
│   └── pyproject.toml
└── README.md
```

## 8. Reglas para la IA que implemente esto

1. Una story por rama/PR. No mezclar stories.
2. Cada story define "Hecho cuando…"; no cerrar sin cumplirlo.
3. Si el protocolo (`02-PROTOCOLO.md`) necesita cambiar, primero se edita el doc, después el código, en ambos lados.
4. Tests en el servidor son obligatorios para el parser de protocolo y el motor de gestos → eventos.
5. Escribir código en inglés, comentarios y docs en español.
6. No inventar APIs de iOS: si hay duda sobre una firma, verificar en la documentación de Apple antes de escribir.
