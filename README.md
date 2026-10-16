# Post-its de escritorio

<img src="assets/postits.svg" width="96" align="right" alt="">

Notas adhesivas ancladas al escritorio, para **Linux (GNOME)** y **Windows**.
Las notas quedan debajo de todas las ventanas: solo se ven cuando mirás el
escritorio (Super+D / Win+D, o sin ventanas encima).

## Uso

| Acción | Cómo |
|---|---|
| Mover una nota | Arrastrar desde la barra del título o la pestaña |
| Renombrar | Click en la barra del título (Enter guarda, Esc cancela); los títulos largos se ven completos en varias líneas |
| Cambiar tamaño | Arrastrar desde cualquier borde o esquina |
| Escribir | Click adentro de la nota (letra tamaño 11) |
| Poner/quitar checkbox | Botón ☑ de la pestaña o **Ctrl+T** (sobre la línea actual o las líneas seleccionadas) |
| Marcar/desmarcar | Click sobre el ☐ / ☑ (la línea marcada se tacha) |
| Lista de tareas | Enter en una línea con checkbox crea otra; Enter en un checkbox vacío termina la lista |
| Opciones | En la pestaña de arriba a la derecha de cada nota |
| Nueva nota | Botón **+**, o abrir la app otra vez |
| Color / salir | Botón **⋮** |
| Versión, reiniciar o finalizar | Ícono de Post-its en la barra (arriba a la derecha en Ubuntu, área de notificación en Windows) |
| Borrar nota | Botón **×** (si tiene texto, pide confirmación) |

Todo se guarda solo: texto, título, posición, tamaño y color.

## Instalación

### Linux (Ubuntu / GNOME en X11)

Usa Python 3 y GTK 3, que ya vienen con Ubuntu. El ícono en la barra superior
usa AppIndicator (`gir1.2-appindicator3-0.1` y la extensión de indicadores de
Ubuntu, ambos incluidos por defecto).

```bash
./linux/install.sh
```

Instala en `~/.local/lib/postits`, agrega **Post-its** al menú de aplicaciones
y lo arranca al iniciar sesión. Notas en `~/.local/share/postits/notes.json`.
Para quitarlo: `./linux/uninstall.sh`.

> En Wayland GNOME no deja que las apps se pongan en la capa del escritorio;
> hace falta la sesión "Ubuntu en Xorg".

### Windows 10 / 11

Necesita [Python 3](https://www.python.org/downloads/) (el instalador oficial
ya trae Tkinter). El instalador agrega `pystray` y `pillow` con pip para el
ícono en el área de notificación. Después, doble click en:

```
windows\install.bat
```

Copia la app a `%LOCALAPPDATA%\PostIts\app`, crea accesos directos en el menú
Inicio y en Inicio automático, y la abre. Notas en `%APPDATA%\PostIts\notes.json`.
Para quitarlo: `windows\uninstall.bat`.

## Estructura

```
common/postits_core.py   lógica compartida: versión, colores, tamaños, guardado
                         JSON, checkboxes y cálculo de bordes/redimensionado
linux/                   versión GTK 3: ventanas de tipo "escritorio" de X11
windows/                 versión Tkinter: ventanas propiedad de Progman (Win32/ctypes)
assets/                  ícono (SVG fuente + PNG y .ico generados)
tools/build_icons.py     regenera los PNG y el .ico si cambiás el SVG
```

Las dos versiones usan el mismo formato de `notes.json`, así que podés copiar
las notas de un sistema al otro.

Para probar sin tocar tus notas reales: `POSTITS_DATA=/tmp/prueba ./linux/postits.py`
(en Windows, `set POSTITS_DATA=...` antes de `pythonw windows\postits.pyw`).

## Versiones

El número de versión vive **solo** en `VERSION` dentro de
[`common/postits_core.py`](common/postits_core.py); de ahí lo toman las dos
apps (menú ⋮ → *Acerca de*, `--version`) y los instaladores. Para sacar una
versión nueva:

1. Cambiar `VERSION` (versionado semántico).
2. Agregar la sección correspondiente en [CHANGELOG.md](CHANGELOG.md).
3. Commit y tag: `git tag vX.Y.Z && git push --tags`.
