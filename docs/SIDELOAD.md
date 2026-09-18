# Instalar RemotePad en el iPhone sin Mac

Guía para Thomas. Sin Mac, la única forma de tener la app en el iPhone 14 es: CI compila un `.ipa` **sin firmar**, **Sideloadly** lo firma con tu Apple ID gratis e instala, desde la netbook Windows. Ver la decisión completa en `00-CONTEXTO.md §4bis`.

## ⚠️ Dos bloqueos ya encontrados (y resueltos)

- **GitHub Actions bloqueado por billing** de la cuenta `Thomas-py` (tarjeta rechazada). Bloquea Actions en todos los repos, público o privado; hacer el repo público no lo esquiva. Mientras no se arregle (`github.com/settings/billing`), usamos **Codemagic** en su lugar (gratis, sin tarjeta, `codemagic.yaml` ya en la raíz del repo) — conectate en [codemagic.io](https://codemagic.io) con tu cuenta de GitHub (OAuth) y agregá la app `Thomas-py/Mouse-pad`.
- **`developer.apple.com` no muestra "Certificates, Identifiers & Profiles"** con Apple ID gratis — Apple restringió ese panel web a cuentas con Apple Developer Program pago (u$s99/año). Por eso **no generamos certificado a mano**: el `.ipa` sale sin firmar del CI y **Sideloadly lo firma él solo**, usando el mismo mecanismo gratuito que usa Xcode con "Personal Team". No hace falta el portal web de Apple para nada de esto.

## 0. Lo que esto NO resuelve solo

Nadie más que vos puede hacer estos pasos:

1. Conectar el repo a Codemagic (o arreglar el billing de GitHub) — ya hecho si estás leyendo esto después de la primera vez.
2. Instalar Sideloadly en la netbook.
3. Descargar el `.ipa` sin firmar del build y sideloadearlo con tu Apple ID.
4. Repetir el sideload cada 7 días (Apple ID gratis) o pagar Apple Developer Program (u$s99/año) si eso molesta.

## 1. Generar el .ipa sin firmar

En **Codemagic** (o en GitHub Actions si el billing ya está resuelto), el workflow ya compila un `.ipa` sin firmar para dispositivo real en cada push a `main`:

- Codemagic: pestaña **Builds** de la app `Mouse-pad` → build más reciente en verde → step "Build sin firmar para el iPhone" → artifact `RemotePad-unsigned.ipa`.
- GitHub Actions (si está desbloqueado): pestaña **Actions** → job `build-unsigned-device-ipa` → artifact `RemotePad-unsigned-ipa`.

Bajalo a la netbook.

## 2. Sideloadly

1. Descargar de **sideloadly.io** (versión Windows), instalar.
2. Conectar el iPhone 14 por cable, confiar en la PC si lo pide (tanto en el iPhone como en iTunes/Apple Mobile Device si Windows lo pide para reconocer el dispositivo).
3. Abrir Sideloadly, arrastrar `RemotePad-unsigned.ipa`.
4. Poner tu Apple ID y contraseña en Sideloadly (los usa localmente para firmar vía el mismo mecanismo de Xcode "Personal Team" — no pasan por RemotePad ni por este repo).
5. **Start**. Sideloadly genera el certificado y provisioning profile automáticamente la primera vez, firma el `.ipa` y lo instala.
6. En el iPhone: **Ajustes → General → VPN y gestión de dispositivos** → tocar tu Apple ID → **Confiar**.
7. Abrir RemotePad. Con Apple ID gratis, la app deja de abrir a los **7 días** (límite de Apple, no de Sideloadly) — repetir desde el paso 3 con el `.ipa` más reciente. Con cuenta paga (u$s99/año) dura 1 año y podés firmar hasta 100 dispositivos sin este límite.

## 3. (Opcional, más adelante) Firmar directo en CI

Si en algún momento pagás el Apple Developer Program, se puede volver a un CI que firma y produce el `.ipa` final sin pasar por Sideloadly — el job `build-signed-device` de `.github/workflows/ios-build.yml` ya está armado para eso (queda saltado hasta que cargues los 4 GitHub Secrets que pide: `APPLE_TEAM_ID`, `APPLE_CERTIFICATE_P12`, `APPLE_CERTIFICATE_PASSWORD`, `APPLE_PROVISIONING_PROFILE`). No es necesario para el flujo actual.

## Problemas comunes

- **Sideloadly no encuentra el iPhone**: instalar/reinstalar los drivers de Apple Mobile Device Support (vienen con iTunes de Microsoft Store o el instalador de Apple) y reconectar el cable.
- **"Unable to install" en Sideloadly**: normalmente se resuelve reintentando — a veces Apple limita cuántos certificados de desarrollo gratis se pueden generar por semana (máximo 2). Si pegó el límite, esperar unos días o revisar los certificados activos en Sideloadly.
- **La app se cierra sola al abrir**: falta confiar el certificado (paso 2.6).
- **Después de 7 días la app no abre**: esperado con Apple ID gratis — repetir el sideload.
