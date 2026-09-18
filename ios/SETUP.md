# Crear el proyecto Xcode

Los archivos Swift de `RemotePad/App/` ya existen, pero el `.xcodeproj` no se generó acá porque este scaffold se hizo sin Xcode disponible (máquina Windows). Para dejarlo compilando en macOS:

1. Abrir Xcode → **File → New → Project → iOS → App**.
2. Nombre: `RemotePad`. Interface: **SwiftUI**. Language: **Swift**. Sin Core Data, sin tests (por ahora).
3. Target mínimo: **iOS 16.0**.
4. Guardar el proyecto en `ios/` (va a crear `ios/RemotePad.xcodeproj` y su propio `ios/RemotePad/`).
5. Borrar el `ContentView.swift` y `RemotePadApp.swift` que genera Xcode por defecto y reemplazarlos por los de `App/` de este repo (o simplemente arrastrar la carpeta `App/` existente al navegador del proyecto, sin copiar, reemplazando los duplicados).
6. Verificar: **Product → Build** compila sin errores y el simulador muestra el texto "RemotePad".
7. Confirmar cero dependencias SPM (`Package Dependencies` vacío) — regla dura del proyecto.

A partir de acá, cada story agrega sus propios grupos/carpetas (`Discovery/`, `Transport/`, `Pairing/`, `Pad/`, `Settings/`) dentro de `RemotePad/`, según `01-ARQUITECTURA.md`.
