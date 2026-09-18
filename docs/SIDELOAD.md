# Instalar RemotePad en el iPhone sin Mac

Guía para Thomas. Sin Mac, la única forma de tener la app en el iPhone 14 es: CI compila y firma el `.ipa`, vos lo instalás con Sideloadly desde la netbook Windows. Ver la decisión completa en `00-CONTEXTO.md §4bis`.

## 0. Lo que esto NO resuelve solo

Nadie más que vos puede hacer estos pasos — necesitan tu cuenta de Apple y tu GitHub:

1. Crear el repositorio en GitHub y pushear este código.
2. Tener (o crear) un Apple ID, generar el certificado + provisioning profile, y cargarlos como *GitHub Secrets*.
3. Instalar Sideloadly en la netbook.
4. Descargar el primer `.ipa` del workflow y sideloadearlo.

El resto de esta guía es el detalle de cada uno.

## 1. Push a GitHub

```
gh repo create remotepad --private --source=. --remote=origin
git push -u origin master
```

(o creá el repo a mano en github.com y agregá el remoto con `git remote add origin <url>`).

Con eso ya corre `.github/workflows/server-tests.yml` y la mitad "sin firmar" de `ios-build.yml` (compila para simulador, sirve para detectar errores de compilación en cada push, no genera `.ipa` todavía).

## 2. Apple ID y certificado de desarrollo

No hace falta Xcode para esto — todo se hace desde la web de Apple Developer.

1. Entrá a **developer.apple.com** con tu Apple ID (el gratuito alcanza para empezar; **Certificates, IDs & Profiles** requiere haber aceptado el acuerdo de desarrollador, que aparece solo al entrar la primera vez).
2. **Identifiers** → **+** → App IDs → App → Bundle ID explícito: `com.thomaslescano.remotepad` (tiene que ser exactamente ese, es el que usa `ios/project.yml`). Capabilities: ninguna especial.
3. **Certificates** → **+** → "Apple Development" → subís un CSR. Generar el CSR sin Mac:
   ```
   openssl req -new -newkey rsa:2048 -nodes -keyout ios_key.pem -out ios_csr.csr -subj "/CN=Thomas Lescano/"
   ```
   Subís `ios_csr.csr`, descargás el `.cer` que te da Apple.
4. Convertir el `.cer` + tu clave privada a `.p12` (con OpenSSL, desde Windows):
   ```
   openssl x509 -in development.cer -inform DER -out development.pem -outform PEM
   openssl pkcs12 -export -inkey ios_key.pem -in development.pem -out development.p12 -password pass:UNA_CONTRASEÑA_TUYA
   ```
5. **Devices** → **+** → agregá el UDID del iPhone 14. Conseguir el UDID sin Xcode: conectá el iPhone a la netbook, abrí iTunes o el Explorador de Windows, o más fácil, abrí **Sideloadly** (paso 4 de esta guía) y conectá el teléfono — Sideloadly lo muestra. También sirve `ideviceinfo` si tenés `libimobiledevice` instalado.
6. **Profiles** → **+** → iOS App Development → elegís el App ID `com.thomaslescano.remotepad`, tu certificado, y el dispositivo agregado. Descargás el `.mobileprovision`.
7. Tu **Team ID** está en developer.apple.com → **Membership** (10 caracteres, ej. `ABCDE12345`).

## 3. Cargar los secrets en GitHub

En el repo → **Settings → Secrets and variables → Actions → New repository secret**:

| Secret | Valor |
|---|---|
| `APPLE_TEAM_ID` | tu Team ID, tal cual (ej. `ABCDE12345`) |
| `APPLE_CERTIFICATE_P12` | el `.p12` del paso 4, en base64: `certutil -encode development.p12 cert_b64.txt` (Windows) y pegás el contenido sin las líneas `-----BEGIN/END-----` — o `openssl base64 -in development.p12 -out cert_b64.txt` y pegás todo el archivo, `base64 --decode` en CI ignora saltos de línea |
| `APPLE_CERTIFICATE_PASSWORD` | la contraseña que pusiste al exportar el `.p12` |
| `APPLE_PROVISIONING_PROFILE` | el `.mobileprovision` del paso 6, en base64 (mismo comando) |

Con los 4 cargados, el job `build-signed-device` de `.github/workflows/ios-build.yml` deja de saltearse y en cada push a `master` sube un artifact `RemotePad-ipa`.

## 4. Sideloadly

1. Descargar de **sideloadly.io** (versión Windows), instalar.
2. Conectar el iPhone 14 por cable, confiar en la PC si lo pide.
3. Bajar el `.ipa` del artifact del workflow (pestaña **Actions** del repo → el run más reciente en verde → `RemotePad-ipa`).
4. Abrir Sideloadly, arrastrar el `.ipa`, poner tu Apple ID (pide la contraseña, la usa solo localmente para firmar vía AltServer, no la manda a nada de RemotePad).
5. Start. Instala la app en el iPhone.
6. En el iPhone: **Ajustes → General → VPN y gestión de dispositivos** → tocar tu Apple ID → **Confiar**.
7. Abrir RemotePad. Con Apple ID gratis, la app deja de abrir a los **7 días** — repetir desde el paso 3 con el `.ipa` más reciente. Con cuenta paga (u$s99/año) dura 1 año.

## Problemas comunes

- **"Unable to install" en Sideloadly**: el UDID del iPhone no está en el provisioning profile (revisar paso 2.5) o el profile expiró.
- **CI falla en `build-signed-device` con "No signing certificate found"**: el `.p12` subido no coincide con el certificado del provisioning profile, o la contraseña en `APPLE_CERTIFICATE_PASSWORD` está mal.
- **La app se cierra sola al abrir**: falta confiar el certificado (paso 4.6).
