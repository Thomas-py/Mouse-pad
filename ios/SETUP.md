# Compilar e instalar sin Mac

Thomas no tiene Mac. El `.xcodeproj` no vive en el repo — lo genera **XcodeGen** a partir de `ios/project.yml` en cada corrida de CI (`.github/workflows/ios-build.yml`, runner `macos-latest`). Nadie necesita abrir Xcode para editar el proyecto: se edita `project.yml` a mano.

- Build sin firmar (simulador) corre en cada push/PR que toque `ios/` — sirve para detectar errores de compilación, no genera nada instalable.
- Build firmado + `.ipa` instalable requiere secrets de Apple que solo Thomas puede cargar — ver `docs/SIDELOAD.md` para el paso a paso completo (Apple ID, certificado, GitHub Secrets, Sideloadly).

A medida que cada story agrega una carpeta nueva bajo `RemotePad/` (`Discovery/`, `Transport/`, `Pairing/`, `Pad/`, `Settings/`), se agrega también a la lista `sources:` de `project.yml` — si un story agrega Swift y `project.yml` no lo referencia, el CI no lo va a compilar.
