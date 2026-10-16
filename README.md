# Post-its de escritorio

Notas adhesivas ancladas al escritorio, para **Linux (GNOME)** y **Windows**.
Las notas quedan debajo de todas las ventanas: solo se ven cuando mirás el
escritorio (Super+D / Win+D, o sin ventanas encima).

## Uso

| Acción | Cómo |
|---|---|
| Mover una nota | Arrastrar desde la barra de arriba |
| Renombrar | Click en el título (Enter guarda, Esc cancela) |
| Cambiar tamaño | Arrastrar desde cualquier borde o esquina |
| Escribir | Click adentro de la nota (letra tamaño 11) |
| Poner/quitar checkbox | Botón ☑ o **Ctrl+T** (sobre la línea actual o las líneas seleccionadas) |
| Marcar/desmarcar | Click sobre el ☐ / ☑ (la línea marcada se tacha) |
| Lista de tareas | Enter en una línea con checkbox crea otra; Enter en un checkbox vacío termina la lista |
| Nueva nota | Botón **+**, o abrir la app otra vez |
| Color / salir | Botón **⋮** |
| Borrar nota | Botón **×** (si tiene texto, pide confirmación) |

Todo se guarda solo: texto, título, posición, tamaño y color.

## Instalación

### Linux (Ubuntu / GNOME en X11)

Usa Python 3 y GTK 3, que ya vienen con Ubuntu.

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
ya trae Tkinter). Después, doble click en:

```
windows\install.bat
```

Copia la app a `%LOCALAPPDATA%\PostIts\app`, crea accesos directos en el menú
Inicio y en Inicio automático, y la abre. Notas en `%APPDATA%\PostIts\notes.json`.
Para quitarlo: `windows\uninstall.bat`.

## Estructura

```
common/postits_core.py   lógica compartida: colores, tamaños, guardado JSON,
                         checkboxes y cálculo de bordes/redimensionado
linux/                   versión GTK 3: ventanas de tipo "escritorio" de X11
windows/                 versión Tkinter: ventanas propiedad de Progman (Win32/ctypes)
```

Las dos versiones usan el mismo formato de `notes.json`, así que podés copiar
las notas de un sistema al otro.

Para probar sin tocar tus notas reales: `POSTITS_DATA=/tmp/prueba ./linux/postits.py`
(en Windows, `set POSTITS_DATA=...` antes de `pythonw windows\postits.pyw`).
