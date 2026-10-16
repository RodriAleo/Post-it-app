# Changelog

Todos los cambios importantes de Post-its. Formato basado en
[Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/); versionado
[semántico](https://semver.org/lang/es/).

La versión se define en un solo lugar: `VERSION` en
[`common/postits_core.py`](common/postits_core.py).

## [1.1.0] - 2026-10-16

### Agregado
- Ícono de la app (`assets/postits.svg`, con PNG en varios tamaños y `.ico`
  para Windows); los instaladores lo usan en el menú y en los accesos directos.
- Número de versión: opción **Acerca de Post-its** en el menú ⋮ y
  `--version` en la línea de comandos.
- Este changelog.

### Corregido
- El instalador/desinstalador de Linux podía cerrar cualquier proceso cuya
  línea de comandos mencionara `postits.py` (por ejemplo un editor); ahora
  solo cierra la app.

## [1.0.0] - 2026-10-16

### Agregado
- Versión para Linux (GNOME en X11, GTK 3): notas como ventanas de tipo
  escritorio, que se mantienen por encima del fondo de íconos de Ubuntu.
- Versión para Windows (Tkinter + Win32): notas ancladas al escritorio que
  siguen visibles con Win+D y vuelven al fondo al cambiar de ventana.
- Mover desde la barra, renombrar con click en el título, redimensionar
  desde los bordes, texto en tamaño 11.
- Checkboxes con el botón ☑ o Ctrl+T; click para marcar (la línea se tacha);
  Enter continúa la lista.
- 6 colores, nueva nota (botón + o abriendo la app de nuevo), borrar con
  confirmación, guardado automático en JSON compartido entre sistemas.
- Instaladores con inicio automático para ambos sistemas.

[1.1.0]: https://github.com/RodriAleo/Post-it-app/compare/v1.0.0...v1.1.0
[1.0.0]: https://github.com/RodriAleo/Post-it-app/releases/tag/v1.0.0
