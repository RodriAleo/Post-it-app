"""Partes compartidas entre la versión de Linux y la de Windows.

Constantes visuales, formato del archivo de notas y la lógica de checkboxes
sobre texto plano. Nada acá depende del toolkit gráfico.
"""

import json
import os
import sys
import uuid

# Única fuente del número de versión (ver CHANGELOG.md).
VERSION = "1.3.0"
APP_NAME = "Post-its"
APP_URL = "https://github.com/RodriAleo/Post-it-app"

ASSETS_DIR = os.path.join(os.path.dirname(os.path.realpath(__file__)), "..", "assets")
ICON_SVG = os.path.join(ASSETS_DIR, "postits.svg")
ICON_ICO = os.path.join(ASSETS_DIR, "postits.ico")


def icon_png(size=256):
    return os.path.join(ASSETS_DIR, "png", f"postits-{size}.png")


def pin_png(pinned, size=16):
    return os.path.join(ASSETS_DIR, "png", f"pin-{'on' if pinned else 'off'}-{size}.png")


PIN_TIP = {
    False: "Fijar: mantener la nota siempre visible, encima de las ventanas",
    True: "Desfijar: volver la nota al escritorio",
}


def version_text():
    return f"{APP_NAME} {VERSION}"


def handle_version_flag(argv):
    """`--version` / `-V`: imprime la versión y devuelve True."""
    if any(a in ("--version", "-V") for a in argv[1:]):
        print(version_text())
        return True
    return False

FONT_SIZE = 11  # pt
BORDER = 6      # px sensibles para redimensionar
CORNER = 16     # px de esquina que redimensionan en diagonal
MIN_W, MIN_H = 160, 110
DEFAULT_W, DEFAULT_H = 260, 220
DRAG_THRESHOLD = 4
SAVE_DELAY_MS = 600

BOX_OFF = "☐"
BOX_ON = "☑"
BOXES = (BOX_OFF, BOX_ON)
BULLET = "•"

# lo que se escribe al inicio de una línea (seguido de espacio) y en qué se convierte
AUTOFORMAT = {"[]": BOX_OFF, "[ ]": BOX_OFF, "[x]": BOX_ON, "[X]": BOX_ON, "*": BULLET}

# texto del botón de ayuda (?)
HELP = [
    ("[] y espacio", "pone un checkbox ☐"),
    ("[x] y espacio", "checkbox ya marcado ☑"),
    ("* y espacio", "ítem de lista •"),
    ("Click en ☐", "marcar / desmarcar (se tacha)"),
    ("Enter", "sigue la lista; en uno vacío la termina"),
    ("Ctrl+T", "poner / quitar checkbox en la línea"),
]

# nombre: (fondo, barra, borde)
COLORS = {
    "Amarillo": ("#fff7a8", "#f5e77a", "#d9c84f"),
    "Rosa": ("#ffd1e0", "#f9b4cb", "#e08fab"),
    "Verde": ("#d4f0b8", "#bde39a", "#94c46c"),
    "Celeste": ("#c9ecfb", "#a9dcf3", "#7fbfdc"),
    "Naranja": ("#ffdcae", "#fcc788", "#e0a35a"),
    "Lila": ("#e2d8f5", "#cfc0ec", "#a995d4"),
}
DEFAULT_COLOR = "Amarillo"
TEXT_COLOR = "#2b2b2b"
DONE_COLOR = "#8a8a8a"
BOX_COLOR = "#555555"


# ---------------------------------------------------------------- checkboxes
def prefix_len(line):
    """Largo del prefijo de checkbox de una línea ("☐ " → 2, sin checkbox → 0)."""
    if line[:1] in BOXES:
        return 2 if line[1:2] == " " else 1
    return 0


def list_prefix(line):
    """Prefijo de lista de una línea: (carácter, largo) o (None, 0).

    Sirve para checkboxes (☐/☑) e ítems (•); Enter continúa la lista con
    `continuation_of()`.
    """
    if line[:1] in BOXES or line[:1] == BULLET:
        return line[0], 2 if line[1:2] == " " else 1
    return None, 0


def continuation_of(char):
    return BULLET if char == BULLET else BOX_OFF


def autoformat(before_cursor):
    """Si lo escrito desde el inicio de la línea es un atajo ("[]", "*"...),
    devuelve el prefijo por el que se reemplaza al apretar espacio."""
    char = AUTOFORMAT.get(before_cursor)
    return f"{char} " if char else None


def all_have_box(lines):
    """True si todas las líneas ya tienen checkbox (el botón entonces los quita)."""
    return all(prefix_len(line) for line in lines)


def toggled_box(char):
    return BOX_OFF if char == BOX_ON else BOX_ON


# ---------------------------------------------------------------- geometría
def edge_at(x, y, w, h):
    """Borde/esquina bajo el puntero (coordenadas relativas a la nota).

    Devuelve "t", "b", "l", "r", "tl", "tr", "bl", "br" o None.
    """
    t, b = y < BORDER, y >= h - BORDER
    l, r = x < BORDER, x >= w - BORDER
    if l or r:
        t, b = t or y < CORNER, b or y >= h - CORNER
    if t or b:
        l, r = l or x < CORNER, r or x >= w - CORNER
    edge = ("t" if t else "b" if b else "") + ("l" if l else "r" if r else "")
    return edge or None


def resized_geometry(edge, geom0, dx, dy):
    """Nueva geometría (x, y, w, h) al arrastrar `edge` por (dx, dy)."""
    x0, y0, w0, h0 = geom0
    x, y, w, h = geom0
    if "r" in edge:
        w = max(MIN_W, w0 + dx)
    if "l" in edge:
        w = max(MIN_W, w0 - dx)
        x = x0 + (w0 - w)
    if "b" in edge:
        h = max(MIN_H, h0 + dy)
    if "t" in edge:
        h = max(MIN_H, h0 - dy)
        y = y0 + (h0 - h)
    return x, y, w, h


# ---------------------------------------------------------------- guardado
def data_dir():
    if os.environ.get("POSTITS_DATA"):
        return os.environ["POSTITS_DATA"]
    if sys.platform == "win32":
        base = os.environ.get("APPDATA") or os.path.expanduser("~")
        return os.path.join(base, "PostIts")
    base = os.environ.get("XDG_DATA_HOME") or os.path.expanduser("~/.local/share")
    return os.path.join(base, "postits")


def data_file():
    return os.path.join(data_dir(), "notes.json")


def new_note_data(x, y, color=DEFAULT_COLOR):
    return {
        "id": uuid.uuid4().hex, "title": "Nota", "text": "",
        "x": int(x), "y": int(y), "w": DEFAULT_W, "h": DEFAULT_H, "color": color,
        "pinned": False,
    }


def load_notes():
    path = data_file()
    try:
        with open(path, encoding="utf-8") as f:
            notes = json.load(f).get("notes", [])
    except FileNotFoundError:
        return []
    except (OSError, ValueError) as e:
        print(f"postits: no pude leer {path}: {e}", file=sys.stderr)
        return []
    out = []
    for d in notes:
        d.setdefault("id", uuid.uuid4().hex)
        d.setdefault("title", "Nota")
        d.setdefault("text", "")
        d["pinned"] = bool(d.get("pinned", False))
        if d.get("color") not in COLORS:
            d["color"] = DEFAULT_COLOR
        d["x"], d["y"] = int(d.get("x", 100)), int(d.get("y", 100))
        d["w"] = max(MIN_W, int(d.get("w", DEFAULT_W)))
        d["h"] = max(MIN_H, int(d.get("h", DEFAULT_H)))
        out.append(d)
    return out


def save_notes(notes):
    """Guarda la lista de notas (dicts) de forma atómica."""
    os.makedirs(data_dir(), exist_ok=True)
    path = data_file()
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump({"version": 1, "notes": notes}, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)
