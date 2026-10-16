"""Post-its de escritorio para Windows (Tkinter + Win32).

Las notas quedan debajo de todas las ventanas y solo se ven cuando mirás el
escritorio (Win+D o sin ventanas encima).

- Arrastrar desde la barra superior: mover la nota.
- Click en el título: renombrar.
- Arrastrar desde los bordes: cambiar tamaño.
- Botón ☑ o Ctrl+T: poner/quitar checkbox en la línea (o líneas seleccionadas).
- Click en ☐/☑: marcar/desmarcar. Enter en una línea con checkbox crea otra.
- Ctrl+Z / Ctrl+Y: deshacer / rehacer.

Ejecutar de nuevo el programa mientras está abierto crea una nota nueva.
"""

import os
import queue
import socket
import subprocess
import sys
import threading
import tkinter as tk
import tkinter.font as tkfont
from tkinter import messagebox

HERE = os.path.dirname(os.path.realpath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "common"))
import postits_core as core  # noqa: E402
from postits_core import BOX_OFF, BOXES, COLORS, DEFAULT_COLOR, DRAG_THRESHOLD  # noqa: E402

try:  # ícono en el área de notificación (opcional: pip install pystray pillow)
    import pystray
    from PIL import Image
except ImportError:
    pystray = None

IS_WIN = sys.platform == "win32"
if IS_WIN:
    import win32_desktop
else:  # permite probar la interfaz en Linux, sin el anclado al escritorio
    win32_desktop = None

if IS_WIN:
    CURSORS = {"t": "size_ns", "b": "size_ns", "l": "size_we", "r": "size_we",
               "tl": "size_nw_se", "br": "size_nw_se", "tr": "size_ne_sw", "bl": "size_ne_sw"}
else:
    CURSORS = {"t": "top_side", "b": "bottom_side", "l": "left_side", "r": "right_side",
               "tl": "top_left_corner", "tr": "top_right_corner",
               "bl": "bottom_left_corner", "br": "bottom_right_corner"}

# color "invisible" de la ventana (a la izquierda de la pestaña): en Windows se
# vuelve transparente y los clicks pasan al escritorio
TRANSPARENT = "#ff00fe" if IS_WIN else "#808080"
TITLE_COLOR = "#3a3a3a"
BTN_COLOR = "#4a4a4a"
HANDSHAKE = b"postits-new\n"


def shade(hex_color, factor):
    """Oscurece un color #rrggbb (factor < 1)."""
    r, g, b = (int(hex_color[i:i + 2], 16) for i in (1, 3, 5))
    return "#%02x%02x%02x" % tuple(max(0, min(255, int(c * factor))) for c in (r, g, b))


class Note:
    def __init__(self, app, data):
        self.app = app
        self.data = data
        self._drag = None   # [kind, edge, x0_root, y0_root, geom0, moved, on_title]
        self._cursor = ""

        self.top = top = tk.Toplevel(app.root)
        top.withdraw()
        top.overrideredirect(True)
        top.title(data["title"])
        top.geometry(f'{data["w"]}x{data["h"]}+{data["x"]}+{data["y"]}')
        top.config(bg=TRANSPARENT)
        if IS_WIN:
            top.attributes("-transparentcolor", TRANSPARENT)

        # --- pestaña arriba a la derecha con las opciones (también sirve para mover)
        self.tab_row = tk.Frame(top, bd=0, bg=TRANSPARENT)
        self.tab_row.pack(fill="x")
        self.tab = tk.Frame(self.tab_row, bd=0, highlightthickness=1, padx=2, cursor="fleur")
        self.tab.pack(side="right")
        self.buttons = []
        self._add_btn("×", "Borrar nota", self._confirm_delete)
        self.menu_btn = self._add_btn("⋮", "Color y opciones", self._show_menu)
        self._add_btn("+", "Nueva nota", lambda: self.app.new_note(near=self))
        self._add_btn(core.BOX_ON, "Checkbox en la línea (Ctrl+T)", self.toggle_checkbox_lines)
        self.tab.bind("<ButtonPress-1>", self._on_header_press)
        self.tab.bind("<B1-Motion>", self._on_drag)
        self.tab.bind("<ButtonRelease-1>", self._on_release)

        # --- marco externo: su margen es la zona de redimensionado
        self.outer = tk.Frame(top, bd=0, highlightthickness=1)
        self.outer.pack(fill="both", expand=True)
        for seq, cb in (("<Motion>", self._on_outer_motion), ("<Leave>", lambda e: self._set_cursor(None)),
                        ("<ButtonPress-1>", self._on_border_press), ("<B1-Motion>", self._on_drag),
                        ("<ButtonRelease-1>", self._on_release)):
            self.outer.bind(seq, cb)

        self.inner = tk.Frame(self.outer, bd=0)
        self.inner.pack(fill="both", expand=True, padx=core.BORDER - 1, pady=core.BORDER - 1)

        # --- barra del título (mover + renombrar)
        self.header = tk.Frame(self.inner, bd=0, cursor="fleur")
        self.header.pack(fill="x")

        # el título se parte en varias líneas para verse siempre completo
        self.title_label = tk.Label(self.header, text=data["title"], anchor="w", justify="left",
                                    font=app.title_font, fg=TITLE_COLOR, padx=6, pady=3, bd=0, cursor="fleur")
        self.title_label.pack(side="left", fill="x", expand=True)
        self.header.bind("<Configure>", self._update_title_wrap)
        # edición: también multilínea (Enter guarda, Esc cancela)
        # mismas medidas y color que el label: se edita en el lugar, sin saltos
        self.title_edit = tk.Text(self.header, font=app.title_font, wrap="word", width=1, height=1,
                                  relief="flat", bd=0, highlightthickness=0,
                                  padx=int(self.title_label["padx"]), pady=int(self.title_label["pady"]),
                                  undo=True, fg=TITLE_COLOR, insertbackground="#222222",
                                  selectforeground="#000000")
        self.title_edit.bind("<Return>", lambda e: self._finish_rename(True))
        self.title_edit.bind("<KP_Enter>", lambda e: self._finish_rename(True))
        self.title_edit.bind("<Escape>", lambda e: self._finish_rename(False))
        self.title_edit.bind("<FocusOut>", lambda e: self._finish_rename(True))
        self.title_edit.bind("<Tab>", lambda e: "break")
        self.title_edit.bind("<<Modified>>", self._on_title_modified)
        self.title_edit.bind("<Configure>", lambda e: self._fit_title_edit())

        for w in (self.header, self.title_label):
            w.bind("<ButtonPress-1>", self._on_header_press)
            w.bind("<B1-Motion>", self._on_drag)
            w.bind("<ButtonRelease-1>", self._on_release)

        # --- cuerpo
        body = tk.Frame(self.inner, bd=0)
        body.pack(fill="both", expand=True)
        self.scroll = tk.Scrollbar(body, orient="vertical", width=10)
        self.text = tk.Text(body, wrap="word", font=app.text_font, bd=0, relief="flat",
                            highlightthickness=0, padx=6, pady=4, undo=True, maxundo=-1,
                            fg=core.TEXT_COLOR, insertbackground=core.TEXT_COLOR,
                            selectforeground="#000000", yscrollcommand=self._on_yscroll)
        self.scroll.config(command=self.text.yview)
        self.text.pack(side="left", fill="both", expand=True)
        self.text.tag_configure("done", overstrike=True, foreground=core.DONE_COLOR)
        self.text.tag_configure("box", foreground=core.BOX_COLOR)
        self.text.insert("1.0", data.get("text", ""))
        self.text.edit_reset()
        self.text.edit_modified(False)
        self._restyle()
        self.text.bind("<<Modified>>", self._on_modified)
        self.text.bind("<ButtonPress-1>", self._on_text_press)
        self.text.bind("<Control-t>", self._on_toggle_key)
        self.text.bind("<Control-T>", self._on_toggle_key)
        self.text.bind("<Return>", self._on_return)
        self.text.bind("<KP_Enter>", self._on_return)
        self.text.bind("<Control-y>", self._on_redo)

        self.apply_color(data.get("color", DEFAULT_COLOR))

        top.deiconify()
        top.update_idletasks()
        if win32_desktop:
            win32_desktop.pin_to_desktop(top)

    # ------------------------------------------------------------ helpers UI
    def _add_btn(self, label, tip, cb):
        b = tk.Label(self.tab, text=label, font=self.app.btn_font, fg=BTN_COLOR, padx=5, cursor="hand2")
        b.pack(side="right")
        b.bind("<Enter>", lambda e: b.config(bg=shade(self._head, 0.9)))
        b.bind("<Leave>", lambda e: b.config(bg=self._head))
        b.bind("<ButtonPress-1>", lambda e: b.config(bg=shade(self._head, 0.82)))

        def release(e):
            b.config(bg=self._head)
            if 0 <= e.x < b.winfo_width() and 0 <= e.y < b.winfo_height():
                cb()
        b.bind("<ButtonRelease-1>", release)
        self.buttons.append(b)
        Tooltip(b, tip)
        return b

    def apply_color(self, color):
        if color not in COLORS:
            color = DEFAULT_COLOR
        bg, head, border = COLORS[color]
        self._head = head
        self.data["color"] = color
        self.outer.config(bg=bg, highlightbackground=border, highlightcolor=border)
        self.inner.config(bg=bg)
        self.tab.config(bg=head, highlightbackground=border, highlightcolor=border)
        self.header.config(bg=head)
        self.title_label.config(bg=head)
        self.title_edit.config(bg=head, selectbackground=shade(head, 0.8))
        for b in self.buttons:
            b.config(bg=head)
        self.text.config(bg=bg, selectbackground=shade(bg, 0.8))
        self.text.master.config(bg=bg)

    def _on_yscroll(self, first, last):
        if float(first) <= 0.0 and float(last) >= 1.0:
            self.scroll.pack_forget()
        elif not self.scroll.winfo_ismapped():
            self.scroll.pack(side="right", fill="y", before=self.text)
        self.scroll.set(first, last)

    def _show_menu(self):
        menu = tk.Menu(self.top, tearoff=0)
        var = tk.StringVar(value=self.data["color"])
        menu._var = var  # que no lo junte el GC mientras el menú está abierto
        for name in COLORS:
            menu.add_radiobutton(label=name, variable=var, value=name,
                                 command=lambda n=name: (self.apply_color(n), self.app.schedule_save()))
        menu.add_separator()
        menu.add_command(label="Nueva nota", command=lambda: self.app.new_note(near=self))
        menu.add_command(label=f"Acerca de {core.APP_NAME}", command=lambda: self.app.show_about(self))
        menu.add_command(label="Cerrar Post-its (las notas se guardan)", command=self.app.quit)
        b = self.menu_btn
        menu.tk_popup(b.winfo_rootx(), b.winfo_rooty() + b.winfo_height())

    def _confirm_delete(self):
        if self.text.get("1.0", "end-1c") and not messagebox.askyesno(
            "Borrar nota", f"¿Borrar la nota «{self.data['title']}»?\nNo se puede deshacer.",
            icon="warning", parent=self.top,
        ):
            return
        self.app.delete_note(self)

    def destroy(self):
        if win32_desktop:
            win32_desktop.unpin(self.top)
        self.top.destroy()

    # ------------------------------------------------------------ título
    def _update_title_wrap(self, e=None):
        pad = 2 * int(self.title_label["padx"])
        wrap = max(20, self.header.winfo_width() - pad)
        if int(self.title_label["wraplength"]) != wrap:
            self.title_label.config(wraplength=wrap)

    def _fit_title_edit(self):
        """Alto del campo de edición = cantidad de líneas que ocupa el título."""
        t = self.title_edit
        try:
            lines = int(t.tk.call(t._w, "count", "-displaylines", "1.0", "end-1c")) + 1
        except (tk.TclError, ValueError):
            lines = 1
        if int(t["height"]) != lines:
            t.config(height=lines)

    def _on_title_modified(self, e):
        if self.title_edit.edit_modified():
            self.title_edit.after_idle(self._fit_title_edit)
            self.title_edit.edit_modified(False)

    def _start_rename(self, at=None):
        """Editar el título; `at` = punto del click en pantalla, para poner ahí el cursor."""
        t = self.title_edit
        lines = max(1, round((self.title_label.winfo_height() - 2 * int(self.title_label["pady"]))
                             / self.app.title_font.metrics("linespace")))
        t.config(height=lines)  # mismo alto que el título desde el primer momento
        t.delete("1.0", "end")
        t.insert("1.0", self.data["title"])
        t.edit_reset()
        self.title_label.pack_forget()
        t.pack(side="left", fill="x", expand=True)
        t.update_idletasks()
        idx = "end-1c"
        if at is not None:
            x, y = at[0] - t.winfo_rootx(), at[1] - t.winfo_rooty()
            idx = t.index(f"@{x},{y}")
            bbox = t.bbox(idx)
            if bbox and x > bbox[0] + bbox[2] / 2 and t.compare(idx, "<", f"{idx} lineend"):
                idx = t.index(f"{idx}+1c")  # click en la mitad derecha: cursor después
        t.mark_set("insert", idx)
        t.focus_force()
        t.after_idle(self._fit_title_edit)

    def _finish_rename(self, accept):
        if not self.title_edit.winfo_ismapped():
            return "break"
        if accept:
            raw = self.title_edit.get("1.0", "end-1c")
            title = " ".join(raw.split()) or "Nota"  # sin saltos de línea pegados
            self.data["title"] = title
            self.title_label.config(text=title)
            self.top.title(title)
            self.app.schedule_save()
        self.title_edit.pack_forget()
        self.title_label.pack(side="left", fill="x", expand=True)
        self.text.focus_set()
        return "break"

    # ------------------------------------------------------------ mover / redimensionar
    def _geom(self):
        t = self.top
        return t.winfo_rootx(), t.winfo_rooty(), t.winfo_width(), t.winfo_height()

    def _edge_at(self, e):
        """Borde bajo el puntero, medido sobre la nota (sin contar la pestaña)."""
        x, y, w, h = self._geom()
        tab_h = self.tab_row.winfo_height()
        rel_y = e.y_root - y - tab_h
        if rel_y < 0:
            return None
        return core.edge_at(e.x_root - x, rel_y, w, h - tab_h)

    def _set_cursor(self, edge):
        cur = CURSORS[edge] if edge else ""
        if cur != self._cursor:
            self._cursor = cur
            self.outer.config(cursor=cur)

    def _on_outer_motion(self, e):
        if self._drag is None:
            self._set_cursor(self._edge_at(e))

    def _on_border_press(self, e):
        edge = self._edge_at(e)
        if edge:
            self._drag = ["resize", edge, e.x_root, e.y_root, self._geom(), False, False]
        return "break"

    def _on_header_press(self, e):
        edge = self._edge_at(e)
        if edge:  # la barra llega hasta el borde: dejar que redimensione
            self._drag = ["resize", edge, e.x_root, e.y_root, self._geom(), False, False]
            return "break"
        if self.title_edit.winfo_ismapped():
            self._finish_rename(True)
        # toda la barra del título es "el título": click sin arrastrar = renombrar
        on_title = (e.x_root, e.y_root) if e.widget in (self.header, self.title_label) else None
        self._drag = ["move", None, e.x_root, e.y_root, self._geom(), False, on_title]
        return "break"

    def _on_drag(self, e):
        d = self._drag
        if d is None:
            return None
        kind, edge, x0r, y0r, (x0, y0, w0, h0), moved, _ = d
        dx, dy = e.x_root - x0r, e.y_root - y0r
        if not moved and abs(dx) < DRAG_THRESHOLD and abs(dy) < DRAG_THRESHOLD:
            return "break"
        d[5] = True
        if kind == "move":
            self.top.geometry(f"+{x0 + dx}+{y0 + dy}")
        else:
            x, y, w, h = core.resized_geometry(edge, (x0, y0, w0, h0), dx, dy)
            self.top.geometry(f"{w}x{h}+{x}+{y}")
        return "break"

    def _on_release(self, e):
        d, self._drag = self._drag, None
        if d is None:
            return None
        kind, moved, on_title = d[0], d[5], d[6]
        if kind == "move" and not moved:
            if on_title is not None:
                self._start_rename(at=on_title)
            else:
                self.top.focus_force()
        self.app.schedule_save()
        return "break"

    # ------------------------------------------------------------ checkboxes
    def _line_text(self, n):
        return self.text.get(f"{n}.0", f"{n}.end")

    def _line_count(self):
        return int(self.text.index("end-1c").split(".")[0])

    def toggle_checkbox_lines(self):
        t = self.text
        if t.tag_ranges("sel"):
            a, b = t.index("sel.first"), t.index("sel.last")
        else:
            a = b = t.index("insert")
        first, last = int(a.split(".")[0]), int(b.split(".")[0])
        if last > first and b.endswith(".0"):
            last -= 1  # selección que termina al inicio de la línea siguiente
        lines = range(first, last + 1)
        t.edit_separator()
        if core.all_have_box([self._line_text(n) for n in lines]):
            for n in lines:
                t.delete(f"{n}.0", f"{n}.{core.prefix_len(self._line_text(n))}")
        else:
            for n in lines:
                if not core.prefix_len(self._line_text(n)):
                    t.insert(f"{n}.0", BOX_OFF + " ")
        t.edit_separator()
        t.focus_set()

    def _toggle_box(self, n):
        t = self.text
        new = core.toggled_box(t.get(f"{n}.0"))
        insert = t.index("insert")
        t.edit_separator()
        t.delete(f"{n}.0")
        t.insert(f"{n}.0", new)
        t.edit_separator()
        t.mark_set("insert", insert)

    def _on_toggle_key(self, e):
        self.toggle_checkbox_lines()
        return "break"

    def _on_redo(self, e):
        try:
            self.text.edit_redo()
        except tk.TclError:
            pass
        return "break"

    def _on_text_press(self, e):
        self.text.focus_force()
        idx = self.text.index(f"@{e.x},{e.y}")
        line, col = (int(p) for p in idx.split("."))
        if col == 0 and self.text.get(idx) in BOXES:
            bbox = self.text.bbox(idx)
            if bbox and bbox[0] <= e.x < bbox[0] + bbox[2]:
                self._toggle_box(line)
                return "break"
        return None

    def _on_return(self, e):
        t = self.text
        if e.state & 0x0005:  # Shift o Ctrl: salto de línea normal
            return None
        if t.tag_ranges("sel"):
            return None
        line, col = (int(p) for p in t.index("insert").split("."))
        text = self._line_text(line)
        plen = core.prefix_len(text)
        if not plen:
            return None
        if not text[plen:].strip():
            # checkbox vacío + Enter: terminar la lista
            t.delete(f"{line}.0", f"{line}.end")
            return "break"
        if col < plen:
            return None
        t.edit_separator()
        t.insert("insert", "\n" + BOX_OFF + " ")
        t.see("insert")
        return "break"

    def _restyle(self):
        t = self.text
        t.tag_remove("done", "1.0", "end")
        t.tag_remove("box", "1.0", "end")
        for n in range(1, self._line_count() + 1):
            line = self._line_text(n)
            plen = core.prefix_len(line)
            if not plen:
                continue
            t.tag_add("box", f"{n}.0")
            if line[0] == core.BOX_ON:
                t.tag_add("done", f"{n}.{plen}", f"{n}.end")

    def _on_modified(self, e):
        if not self.text.edit_modified():
            return
        self._restyle()
        self.app.schedule_save()
        self.text.edit_modified(False)

    # ------------------------------------------------------------ datos
    def snapshot(self):
        x, y, w, h = self._geom()
        self.data.update(text=self.text.get("1.0", "end-1c"), x=x, y=y, w=w, h=h)
        return dict(self.data)


class Tooltip:
    def __init__(self, widget, text):
        self.widget, self.text, self.win, self.job = widget, text, None, None
        widget.bind("<Enter>", self._schedule, add="+")
        widget.bind("<Leave>", self._hide, add="+")
        widget.bind("<ButtonPress-1>", self._hide, add="+")

    def _schedule(self, e):
        self.job = self.widget.after(600, self._show)

    def _show(self):
        self.job = None
        w = self.widget
        self.win = tk.Toplevel(w)
        self.win.overrideredirect(True)
        self.win.attributes("-topmost", True)
        tk.Label(self.win, text=self.text, bg="#ffffe1", fg="#000000", relief="solid", bd=1,
                 padx=4, pady=1).pack()
        self.win.geometry(f"+{w.winfo_rootx()}+{w.winfo_rooty() + w.winfo_height() + 2}")

    def _hide(self, e=None):
        if self.job:
            self.widget.after_cancel(self.job)
            self.job = None
        if self.win:
            self.win.destroy()
            self.win = None


class App:
    def __init__(self, server):
        self.server = server
        self.root = tk.Tk()
        self.root.withdraw()
        self.root.title(core.APP_NAME)
        self._set_icon()
        family = self._pick_family()
        self.text_font = tkfont.Font(family=family, size=core.FONT_SIZE)
        self.title_font = tkfont.Font(family=family, size=core.FONT_SIZE, weight="bold")
        self.btn_font = tkfont.Font(family=family, size=core.FONT_SIZE)
        self.notes = []
        self._save_job = None
        self._closing = False
        self.restart_requested = False
        self._tray = None
        self._tray_actions = queue.Queue()  # el menú del ícono corre en otro hilo

    def _set_icon(self):
        try:
            if IS_WIN:
                self.root.iconbitmap(default=core.ICON_ICO)  # también para los diálogos
            else:
                self._icon = tk.PhotoImage(file=core.icon_png(64))
                self.root.iconphoto(True, self._icon)
        except tk.TclError:
            pass

    def show_about(self, note):
        messagebox.showinfo(
            f"Acerca de {core.APP_NAME}",
            f"{core.version_text()}\n\nNotas adhesivas ancladas al escritorio.\n{core.APP_URL}",
            parent=note.top,
        )

    def _pick_family(self):
        families = set(tkfont.families(self.root))
        for f in ("Segoe UI", "Ubuntu", "Cantarell", "DejaVu Sans"):
            if f in families:
                return f
        return tkfont.nametofont("TkDefaultFont").actual("family")

    def run(self):
        for d in core.load_notes():
            self.notes.append(Note(self, d))
        if not self.notes:
            self.new_note()
        self._start_tray()
        self.root.after(300, self._poll_server)
        self.root.mainloop()

    # ------------------------------------------------------------ bandeja
    def _start_tray(self):
        """Ícono en el área de notificación con la versión, Reiniciar y Finalizar."""
        if pystray is None:
            return
        act = self._tray_actions.put
        menu = pystray.Menu(
            pystray.MenuItem(core.version_text(), None, enabled=False),  # solo informativo
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Nueva nota", lambda icon, item: act("new")),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Reiniciar", lambda icon, item: act("restart")),
            pystray.MenuItem("Finalizar", lambda icon, item: act("quit")),
        )
        try:
            image = Image.open(core.icon_png(64))
            self._tray = pystray.Icon("postits", image, core.version_text(), menu)
            threading.Thread(target=self._tray.run, daemon=True, name="postits-tray").start()
        except Exception as e:  # sin bandeja disponible: la app sigue igual
            print(f"postits: no pude crear el ícono de bandeja: {e}", file=sys.stderr)
            self._tray = None

    def _process_tray_actions(self):
        while not self._closing:
            try:
                action = self._tray_actions.get_nowait()
            except queue.Empty:
                return
            if action == "new":
                self.new_note()
            elif action == "restart":
                self.restart()
            elif action == "quit":
                self.quit()

    def restart(self):
        """Guarda, cierra y vuelve a abrir la app (ver main())."""
        self.restart_requested = True
        self.quit()

    # ------------------------------------------------------------ notas
    def new_note(self, near=None):
        if near is not None:
            x, y, *_ = near._geom()
            x, y = x + 30, y + 30
            color = near.data["color"]
        else:
            k = len(self.notes) % 6
            x = self.root.winfo_screenwidth() - core.DEFAULT_W - 60 - 40 * k
            y = 60 + 40 * k
            color = DEFAULT_COLOR
        note = Note(self, core.new_note_data(x, y, color))
        self.notes.append(note)
        note.top.focus_force()
        note.text.focus_set()
        self.schedule_save()
        return note

    def delete_note(self, note):
        self.notes.remove(note)
        note.destroy()
        self.save_now()

    def quit(self):
        if self._closing:
            return
        self._closing = True
        self.save_now()
        if self._tray is not None:
            self._tray.stop()
        self.server.close()  # libera la instancia única (importante al reiniciar)
        self.root.destroy()

    # ------------------------------------------------------------ guardado
    def schedule_save(self):
        if self._save_job:
            self.root.after_cancel(self._save_job)
        self._save_job = self.root.after(core.SAVE_DELAY_MS, self.save_now)

    def save_now(self):
        if self._save_job:
            self.root.after_cancel(self._save_job)
            self._save_job = None
        core.save_notes([n.snapshot() for n in self.notes])

    # ------------------------------------------------------------ instancia única
    def _poll_server(self):
        self._process_tray_actions()
        if self._closing:
            return
        try:
            while True:
                conn, _ = self.server.accept()
                with conn:
                    conn.settimeout(1)
                    if conn.recv(64) == HANDSHAKE:
                        conn.sendall(b"ok")
                        self.new_note()
        except (BlockingIOError, socket.timeout, OSError):
            pass
        self.root.after(300, self._poll_server)


def port_file():
    return os.path.join(core.data_dir(), "instance.port")


def notify_running_instance():
    """Si ya hay una instancia abierta, le pide una nota nueva y devuelve True."""
    try:
        with open(port_file()) as f:
            port = int(f.read().strip())
        with socket.create_connection(("127.0.0.1", port), timeout=1) as s:
            s.sendall(HANDSHAKE)
            return s.recv(8) == b"ok"
    except (OSError, ValueError):
        return False


def start_server():
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.bind(("127.0.0.1", 0))
    srv.listen(4)
    srv.setblocking(False)
    os.makedirs(core.data_dir(), exist_ok=True)
    with open(port_file(), "w") as f:
        f.write(str(srv.getsockname()[1]))
    return srv


def main():
    if core.handle_version_flag(sys.argv):
        return
    if notify_running_instance():
        return
    if win32_desktop:
        win32_desktop.make_dpi_aware()
    app = App(start_server())
    app.run()
    if app.restart_requested:
        # abrir una instancia nueva (las notas ya se guardaron)
        subprocess.Popen([sys.executable, os.path.realpath(__file__)] + sys.argv[1:], close_fds=True)


if __name__ == "__main__":
    main()
