# Compilar e instalar sin Mac

Thomas no tiene Mac — netbook Windows + iPhone 14. No hay forma de correr Xcode localmente (no existe SDK de iOS para Windows).

El plan es **story S-05** (`docs/04-STORIES.md`): CI en GitHub Actions (`macos-latest`) compila y firma el `.ipa`, y se instala en el iPhone con **Sideloadly** desde Windows por cable. Ver `docs/00-CONTEXTO.md §4bis` para el detalle de la decisión.

No se implementa acá todavía porque requiere, de parte de Thomas:
- El repo empujado a GitHub (remoto).
- Un Apple ID (alcanza el gratuito para empezar; expira el sideload cada 7 días).

Hasta que se resuelva S-05, los archivos de `RemotePad/App/` quedan como código fuente sin compilar verificado.
