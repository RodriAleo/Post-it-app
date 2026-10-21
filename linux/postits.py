#!/usr/bin/python3
"""Post-its de escritorio para Linux: GNOME (X11).

Cada nota es una ventana de tipo "escritorio": queda debajo de todas las
ventanas y solo se ve cuando mirás el escritorio (Super+D o sin ventanas).

- Arrastrar desde la barra superior: mover la nota.
- Click en el título: renombrar.
- Arrastrar desde los bordes: cambiar tamaño.
- Botón ☑ o Ctrl+T: poner/quitar checkbox en la línea (o líneas seleccionadas).
- Click en ☐/☑: marcar/desmarcar. Enter en una línea con checkbox crea otra.

Ejecutar de nuevo el programa mientras está abierto crea una nota nueva.
"""

import os
import signal
import sys

import gi

# En Wayland GNOME ignora la capa "escritorio", no oculta las notas del dock y
# Wnck no funciona: se fuerza X11 (XWayland), que hay que elegir antes de
# importar Gtk.
os.environ["GDK_BACKEND"] = "x11"

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
from gi.repository import Gdk, GdkPixbuf, Gio, GLib, Gtk, Pango  # noqa: E402

try:  # para que la zona al lado de la pestaña no capture clicks
    import cairo
except ImportError:
    cairo = None

try:  # ícono en la barra superior (bandeja), como las apps en segundo plano
    gi.require_version("AppIndicator3", "0.1")
    from gi.repository import AppIndicator3
except (ImportError, ValueError):
    try:
        gi.require_version("AyatanaAppIndicator3", "0.1")
        from gi.repository import AyatanaAppIndicator3 as AppIndicator3
    except (ImportError, ValueError):
        AppIndicator3 = None

try:  # para mantener las notas por encima del fondo de iconos (DING)
    gi.require_version("Wnck", "3.0")
    gi.require_version("GdkX11", "3.0")
    from gi.repository import GdkX11, Wnck
except (ImportError, ValueError):
    Wnck = None

sys.path.insert(0, os.path.join(os.path.dirname(os.path.realpath(__file__)), "..", "common"))
import postits_core as core  # noqa: E402
from postits_core import (  # noqa: E402
    BORDER, BOX_OFF, BOXES, COLORS, DEFAULT_COLOR, DRAG_THRESHOLD, FONT_SIZE,
)

APP_ID = os.environ.get("POSTITS_APP_ID", "ar.local.PostIts")


def css_class(color):
    return "c-" + color.lower()


def build_css():
    css = f"""
    window.note-window {{ background-color: transparent; }}
    .note-outer {{ border-width: 1px; border-style: solid; }}
    .note-tab {{
        border-width: 1px 1px 0 1px; border-style: solid;
        border-radius: 6px 6px 0 0; padding: 1px 3px 0 3px;
    }}
    .note-title {{ font-weight: bold; font-size: {FONT_SIZE}pt; color: #3a3a3a; }}
    .note-title-edit {{
        font-weight: bold; font-size: {FONT_SIZE}pt;
        border: none; padding: 0; margin: 0; background-color: transparent;
    }}
    .note-title-edit text {{
        background-color: transparent; color: #3a3a3a; caret-color: #222;
    }}
    .note-title-edit text selection {{ background-color: rgba(0,0,0,0.20); color: #000; }}
    .note-btn {{
        padding: 0 5px; min-height: 0; min-width: 0; border: none;
        background: transparent; box-shadow: none; color: #4a4a4a;
        font-size: {FONT_SIZE}pt; border-radius: 3px;
    }}
    .note-btn:hover {{ background: rgba(0,0,0,0.10); color: #111; }}
    .note-btn:active {{ background: rgba(0,0,0,0.18); }}
    .note-body, .note-body text {{
        font-size: {FONT_SIZE}pt; color: #2b2b2b; caret-color: #2b2b2b;
    }}
    .note-body text selection {{ background-color: rgba(0,0,0,0.20); color: #000; }}
    .note-body scrollbar {{ background: transparent; border: none; }}
    """
    for name, (bg, head, border) in COLORS.items():
        c = css_class(name)
        css += f"""
        .{c} .note-outer {{ background-color: {bg}; border-color: {border}; }}
        .{c} .note-tab {{ background-color: {head}; border-color: {border}; }}
        .{c} .note-header {{ background-color: {head}; }}
        .{c} .note-body, .{c} .note-body text, .{c} scrolledwindow {{
            background-color: {bg};
        }}
        """
    return css.encode()


class WrapLabel(Gtk.Label):
    """Label multilínea cuyo alto depende del ancho que tiene de verdad.

    Un Gtk.Label con wrap le informa a la ventana el alto que tendría con el
    ancho mínimo (una palabra por línea), y la ventana crece de más. Este
    calcula el alto con el ancho asignado y no pide ancho propio.
    """

    def __init__(self, **kw):
        super().__init__(**kw)
        self._width = 0
        self.set_line_wrap(True)
        self.set_line_wrap_mode(Pango.WrapMode.WORD_CHAR)
        self.connect("size-allocate", self._on_allocate)

    def do_get_request_mode(self):
        return Gtk.SizeRequestMode.CONSTANT_SIZE

    def do_get_preferred_width(self):
        return 20, 20

    def do_get_preferred_height(self):
        layout = self.create_pango_layout(self.get_text())
        layout.set_wrap(Pango.WrapMode.WORD_CHAR)
        layout.set_width(max(20, self._width or 200) * Pango.SCALE)
        h = layout.get_pixel_size()[1]
        return h, h

    def _on_allocate(self, widget, alloc):
        if alloc.width != self._width:
            self._width = alloc.width
            GLib.idle_add(self.queue_resize)


class WrapTextView(Gtk.TextView):
    """TextView para editar el título en el lugar.

    No ensancha la nota y pide exactamente el alto que ocupa su texto con el
    ancho de `width_of()` (el del título), así la barra no cambia de tamaño
    al empezar a editar.
    """

    def __init__(self, width_of, **kw):
        super().__init__(**kw)
        self._width_of = width_of
        self.get_buffer().connect("changed", lambda b: self.queue_resize())

    def do_get_request_mode(self):
        return Gtk.SizeRequestMode.CONSTANT_SIZE

    def do_get_preferred_width(self):
        return 20, 20

    def do_get_preferred_height(self):
        buf = self.get_buffer()
        layout = self.create_pango_layout(buf.get_text(buf.get_start_iter(), buf.get_end_iter(), False) or " ")
        layout.set_wrap(Pango.WrapMode.WORD_CHAR)
        layout.set_width(max(20, self._width_of()) * Pango.SCALE)
        h = layout.get_pixel_size()[1]
        return h, h


class Note(Gtk.Window):
    def __init__(self, app, data):
        super().__init__(application=app, type=Gtk.WindowType.TOPLEVEL)
        self.app = app
        self.data = data
        self._drag = None      # ("move"|"resize", edge, x0_root, y0_root, geom0, moved, on_title)
        self._cursor_edge = None

        self.set_title(data.get("title") or "Nota")
        self.set_decorated(False)
        self.pinned = data.get("pinned", False)
        self._apply_layer()
        self.set_skip_taskbar_hint(True)
        self.set_skip_pager_hint(True)
        self.stick()
        self.set_default_size(data["w"], data["h"])
        self.move(data["x"], data["y"])

        # ventana con transparencia: a la izquierda de la pestaña se ve el escritorio
        self.get_style_context().add_class("note-window")
        screen = self.get_screen()
        visual = screen.get_rgba_visual()
        if visual is not None and screen.is_composited():
            self.set_visual(visual)

        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.add(root)

        # --- pestaña arriba a la derecha con las opciones (también sirve para mover)
        self.tab_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        root.pack_start(self.tab_row, False, False, 0)
        self.tab = Gtk.EventBox()
        self.tab.get_style_context().add_class("note-tab")
        self.tab.add_events(
            Gdk.EventMask.POINTER_MOTION_MASK
            | Gdk.EventMask.BUTTON_PRESS_MASK
            | Gdk.EventMask.BUTTON_RELEASE_MASK
        )
        self.tab.connect("button-press-event", self._on_header_press)
        self.tab.connect("motion-notify-event", self._on_pointer_motion)
        self.tab.connect("button-release-event", self._on_release)
        self.tab.connect("realize", self._on_header_realize)
        self.tab_row.pack_end(self.tab, False, False, 0)
        tab_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=1)
        self.tab.add(tab_box)
        self.pin_btn = self._add_btn(tab_box, None, core.PIN_TIP[self.pinned], lambda b: self.set_pinned(not self.pinned))
        self.pin_img = Gtk.Image()
        self.pin_btn.set_image(self.pin_img)
        self._update_pin_button()
        self._add_btn(tab_box, "?", "Ayuda: atajos para checkboxes e ítems", self._show_help)
        self.menu_btn = self._add_btn(tab_box, "⋮", "Color y opciones", self._show_menu)
        self._add_btn(tab_box, "×", "Borrar nota", lambda b: self._confirm_delete())
        self.connect("size-allocate", self._update_input_shape)

        # --- contenedor externo: su margen es la zona de redimensionado
        self.outer = Gtk.EventBox()
        self.outer.get_style_context().add_class("note-outer")
        self.outer.add_events(
            Gdk.EventMask.POINTER_MOTION_MASK
            | Gdk.EventMask.BUTTON_PRESS_MASK
            | Gdk.EventMask.BUTTON_RELEASE_MASK
            | Gdk.EventMask.LEAVE_NOTIFY_MASK
        )
        self.outer.connect("button-press-event", self._on_border_press)
        self.outer.connect("motion-notify-event", self._on_pointer_motion)
        self.outer.connect("button-release-event", self._on_release)
        self.outer.connect("leave-notify-event", lambda *a: self._set_cursor(None))
        root.pack_start(self.outer, True, True, 0)

        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        vbox.set_margin_start(BORDER - 1)
        vbox.set_margin_end(BORDER - 1)
        vbox.set_margin_bottom(BORDER - 1)
        vbox.set_margin_top(BORDER - 1)
        self.outer.add(vbox)

        # --- barra del título (mover + renombrar)
        self.header = Gtk.EventBox()
        self.header.get_style_context().add_class("note-header")
        self.header.add_events(
            Gdk.EventMask.POINTER_MOTION_MASK
            | Gdk.EventMask.BUTTON_PRESS_MASK
            | Gdk.EventMask.BUTTON_RELEASE_MASK
        )
        self.header.connect("button-press-event", self._on_header_press)
        self.header.connect("motion-notify-event", self._on_pointer_motion)
        self.header.connect("button-release-event", self._on_release)
        self.header.connect("realize", self._on_header_realize)
        vbox.pack_start(self.header, False, False, 0)

        hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=2)
        hbox.set_margin_start(6)
        hbox.set_margin_end(6)
        hbox.set_margin_top(3)
        hbox.set_margin_bottom(3)
        self.header.add(hbox)

        self.title_stack = Gtk.Stack()
        # el título se parte en varias líneas para verse siempre completo
        self.title_label = WrapLabel(label=self.get_title(), xalign=0)
        self.title_label.get_style_context().add_class("note-title")
        self.title_label.set_tooltip_text("Click para renombrar · arrastrá la barra para mover")
        # edición: también multilínea (Enter guarda, Esc cancela)
        self.title_edit = WrapTextView(lambda: self.title_stack.get_allocated_width())
        self.title_edit.get_style_context().add_class("note-title-edit")
        self.title_edit.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        # sin márgenes: el texto queda exactamente donde estaba el título
        self.title_edit.set_accepts_tab(False)
        self.title_edit.connect("focus-out-event", lambda *a: self._finish_rename(True))
        self.title_edit.connect("key-press-event", self._on_title_key)
        self.title_edit.connect("key-press-event", self._keep_pointer_visible)
        self.title_stack.add_named(self.title_label, "label")
        self.title_stack.add_named(self.title_edit, "entry")
        # el alto/ancho sigue al hijo visible, no al más grande
        self.title_stack.set_hhomogeneous(False)
        self.title_stack.set_vhomogeneous(False)
        hbox.pack_start(self.title_stack, True, True, 0)

        # --- cuerpo
        scroller = Gtk.ScrolledWindow()
        scroller.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        vbox.pack_start(scroller, True, True, 0)

        self.view = Gtk.TextView()
        self.view.get_style_context().add_class("note-body")
        self.view.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        self.view.set_left_margin(6)
        self.view.set_right_margin(6)
        self.view.set_top_margin(4)
        self.view.set_bottom_margin(4)
        self.view.connect("button-press-event", self._on_text_press)
        self.view.connect("key-press-event", self._on_text_key)
        self.view.connect("key-press-event", self._keep_pointer_visible)
        scroller.add(self.view)

        self.buf = self.view.get_buffer()
        self.tag_done = self.buf.create_tag("done", strikethrough=True, foreground=core.DONE_COLOR)
        self.tag_box = self.buf.create_tag("box", foreground=core.BOX_COLOR)
        self.buf.set_text(data.get("text", ""))
        self._restyle()
        self.buf.connect("changed", self._on_text_changed)

        self._apply_color(data.get("color", DEFAULT_COLOR))
        self.connect("configure-event", self._on_configure)
        self.connect("delete-event", lambda *a: True)  # no cerrar con Alt+F4 por accidente

    # ------------------------------------------------------------ helpers UI
    def _add_btn(self, box, label, tip, cb):
        b = Gtk.Button(label=label) if label else Gtk.Button()
        b.set_relief(Gtk.ReliefStyle.NONE)
        b.set_focus_on_click(False)
        b.set_tooltip_text(tip)
        b.get_style_context().add_class("note-btn")
        b.connect("clicked", cb)
        box.pack_start(b, False, False, 0)
        return b

    # ------------------------------------------------------------ pin
    def _apply_layer(self):
        """Fijada: encima de todas las ventanas. Si no: en la capa del escritorio."""
        if self.pinned:
            self.set_type_hint(Gdk.WindowTypeHint.UTILITY)
            self.set_keep_above(True)
        else:
            self.set_type_hint(Gdk.WindowTypeHint.DESKTOP)
            self.set_keep_above(False)

    def _update_pin_button(self):
        try:
            self.pin_img.set_from_pixbuf(GdkPixbuf.Pixbuf.new_from_file(core.pin_png(self.pinned)))
        except GLib.Error:
            self.pin_btn.set_label("📌" if self.pinned else "○")
        self.pin_btn.set_tooltip_text(core.PIN_TIP[self.pinned])

    def set_pinned(self, pinned):
        if pinned == self.pinned:
            return
        self.pinned = self.data["pinned"] = pinned
        self._update_pin_button()
        # el tipo de ventana solo se puede cambiar con la ventana oculta
        x, y = self.get_position()
        self.hide()
        self._apply_layer()
        self.move(x, y)
        self.show()
        self.stick()
        self.present()
        # el "siempre encima" pedido con la ventana oculta se pierde al mostrarla
        GLib.idle_add(lambda: self.set_keep_above(self.pinned) and False)
        self.app.schedule_save()

    def _apply_color(self, color):
        if color not in COLORS:
            color = DEFAULT_COLOR
        ctx = self.get_style_context()
        for name in COLORS:
            ctx.remove_class(css_class(name))
        ctx.add_class(css_class(color))
        self.data["color"] = color

    def _show_menu(self, button):
        menu = Gtk.Menu()
        for name, (bg, _h, _b) in COLORS.items():
            item = Gtk.MenuItem()
            lbl = Gtk.Label(xalign=0)
            mark = "  ✓" if name == self.data.get("color") else ""
            lbl.set_markup(f'<span foreground="{bg}">⬤</span>  {name}{mark}')
            item.add(lbl)
            item.connect("activate", lambda i, n=name: (self._apply_color(n), self.app.schedule_save()))
            menu.append(item)
        menu.append(Gtk.SeparatorMenuItem())
        item = Gtk.MenuItem(label="Nueva nota")
        item.connect("activate", lambda i: self.app.new_note(near=self))
        menu.append(item)
        item = Gtk.MenuItem(label=f"Acerca de {core.APP_NAME}")
        item.connect("activate", lambda i: self.app.show_about(self))
        menu.append(item)
        item = Gtk.MenuItem(label="Cerrar Post-its (las notas se guardan)")
        item.connect("activate", lambda i: self.app.quit())
        menu.append(item)
        menu.show_all()
        menu.attach_to_widget(self, None)
        menu.popup_at_widget(button, Gdk.Gravity.SOUTH_EAST, Gdk.Gravity.NORTH_EAST, None)

    def _show_help(self, button):
        menu = Gtk.Menu()
        head = Gtk.MenuItem(label="Al inicio de una línea:")
        head.set_sensitive(False)
        menu.append(head)
        for keys, what in core.HELP:
            item = Gtk.MenuItem()
            lbl = Gtk.Label(xalign=0)
            lbl.set_markup(f"<b>{GLib.markup_escape_text(keys)}</b>   →   {GLib.markup_escape_text(what)}")
            item.add(lbl)
            menu.append(item)
        menu.show_all()
        menu.attach_to_widget(self, None)
        menu.popup_at_widget(button, Gdk.Gravity.SOUTH_EAST, Gdk.Gravity.NORTH_EAST, None)

    def _confirm_delete(self):
        if self.buf.get_char_count() == 0:
            self.app.delete_note(self)
            return
        dlg = Gtk.MessageDialog(
            transient_for=self,
            modal=True,
            message_type=Gtk.MessageType.QUESTION,
            buttons=Gtk.ButtonsType.NONE,
            text=f"¿Borrar la nota «{self.get_title()}»?",
        )
        dlg.format_secondary_text("No se puede deshacer.")
        dlg.add_button("Cancelar", Gtk.ResponseType.CANCEL)
        dlg.add_button("Borrar", Gtk.ResponseType.OK).get_style_context().add_class("destructive-action")
        dlg.set_keep_above(True)
        resp = dlg.run()
        dlg.destroy()
        if resp == Gtk.ResponseType.OK:
            self.app.delete_note(self)

    # ------------------------------------------------------------ título
    def _title_offset_at(self, x_root, y_root):
        """Posición (en caracteres) del título bajo un punto de la pantalla."""
        label = self.title_label
        # el label dibuja su layout en get_layout_offsets(), relativo a su GdkWindow
        wx, wy = label.get_window().get_origin()[1:]
        ox, oy = label.get_layout_offsets()
        layout = label.get_layout()
        _inside, index, trailing = layout.xy_to_index(
            int((x_root - wx - ox) * Pango.SCALE), int((y_root - wy - oy) * Pango.SCALE)
        )
        text = layout.get_text().encode()
        return len(text[:index].decode("utf-8", "ignore")) + trailing

    def _start_rename(self, at=None):
        """Editar el título; `at` = punto del click en pantalla, para poner ahí el cursor."""
        title = self.get_title()
        offset = len(title)
        if at is not None:
            try:
                offset = min(len(title), max(0, self._title_offset_at(*at)))
            except (TypeError, ValueError):
                pass
        tbuf = self.title_edit.get_buffer()
        tbuf.set_text(title)
        self.title_stack.set_visible_child_name("entry")
        self.present_with_time(Gtk.get_current_event_time())
        self.title_edit.grab_focus()
        tbuf.place_cursor(tbuf.get_iter_at_offset(offset))

    def _finish_rename(self, accept):
        if self.title_stack.get_visible_child_name() != "entry":
            return False
        if accept:
            tbuf = self.title_edit.get_buffer()
            raw = tbuf.get_text(tbuf.get_start_iter(), tbuf.get_end_iter(), False)
            title = " ".join(raw.split()) or "Nota"  # sin saltos de línea pegados
            self.set_title(title)
            self.title_label.set_text(title)
            self.data["title"] = title
            self.app.schedule_save()
        self.title_stack.set_visible_child_name("label")
        self.view.grab_focus()
        return False

    def _keep_pointer_visible(self, view, event):
        """GTK esconde el puntero del mouse al escribir; lo volvemos a mostrar."""
        GLib.idle_add(self._show_pointer, view)
        return False

    @staticmethod
    def _show_pointer(view):
        win = view.get_window(Gtk.TextWindowType.TEXT)
        if win is not None:
            win.set_cursor(Gdk.Cursor.new_from_name(view.get_display(), "text"))
        return False

    def _on_title_key(self, view, event):
        if event.keyval == Gdk.KEY_Escape:
            self._finish_rename(False)
            return True
        if event.keyval in (Gdk.KEY_Return, Gdk.KEY_KP_Enter):
            self._finish_rename(True)
            return True
        return False

    # ------------------------------------------------------------ mover / redimensionar
    def _on_header_realize(self, widget):
        widget.get_window().set_cursor(Gdk.Cursor.new_from_name(widget.get_display(), "grab"))

    def _set_cursor(self, edge):
        if edge == self._cursor_edge:
            return
        self._cursor_edge = edge
        names = {
            "t": "n-resize", "b": "s-resize", "l": "w-resize", "r": "e-resize",
            "tl": "nw-resize", "tr": "ne-resize", "bl": "sw-resize", "br": "se-resize",
        }
        win = self.outer.get_window()
        if win is None:
            return
        cur = Gdk.Cursor.new_from_name(self.get_display(), names[edge]) if edge else None
        win.set_cursor(cur)

    def _edge_at(self, x_root, y_root):
        """Borde bajo el puntero, medido sobre la nota (sin contar la pestaña)."""
        ox, oy = self.get_window().get_origin()[1:]
        tab_h = self.tab_row.get_allocated_height()
        w, h = self.get_size()
        y = y_root - oy - tab_h
        if y < 0:
            return None
        return core.edge_at(x_root - ox, y, w, h - tab_h)

    def _update_input_shape(self, widget, alloc):
        """La zona transparente al lado de la pestaña deja pasar los clicks al escritorio."""
        if cairo is None or self.get_window() is None:
            return
        w, h = alloc.width, alloc.height
        tab_h = self.tab_row.get_allocated_height()
        tab_w = self.tab.get_allocated_width()
        region = cairo.Region(cairo.RectangleInt(0, tab_h, w, max(0, h - tab_h)))
        region.union(cairo.RectangleInt(max(0, w - tab_w), 0, tab_w, tab_h))
        self.input_shape_combine_region(region)

    def _geom(self):
        x, y = self.get_position()
        w, h = self.get_size()
        return x, y, w, h

    def _on_border_press(self, widget, event):
        if event.button != 1 or event.type != Gdk.EventType.BUTTON_PRESS:
            return False
        edge = self._edge_at(event.x_root, event.y_root)
        if not edge:
            return False
        self._drag = ["resize", edge, event.x_root, event.y_root, self._geom(), False, False]
        return True

    def _on_header_press(self, widget, event):
        if event.button != 1 or event.type != Gdk.EventType.BUTTON_PRESS:
            return False
        edge = self._edge_at(event.x_root, event.y_root)
        if edge:  # la barra llega hasta el borde: dejar que redimensione
            self._drag = ["resize", edge, event.x_root, event.y_root, self._geom(), False, False]
            return True
        if self.title_stack.get_visible_child_name() == "entry":
            self._finish_rename(True)
        # toda la barra del título es "el título": click sin arrastrar = renombrar,
        # con el cursor donde se hizo click
        on_title = (event.x_root, event.y_root) if widget is self.header else None
        self._drag = ["move", None, event.x_root, event.y_root, self._geom(), False, on_title]
        return True

    def _on_pointer_motion(self, widget, event):
        d = self._drag
        if d is None:
            if widget is self.outer:
                self._set_cursor(self._edge_at(event.x_root, event.y_root))
            return False
        kind, edge, x0r, y0r, (x0, y0, w0, h0), moved, _ = d
        dx, dy = int(event.x_root - x0r), int(event.y_root - y0r)
        if not moved and abs(dx) < DRAG_THRESHOLD and abs(dy) < DRAG_THRESHOLD:
            return True
        d[5] = True
        if kind == "move":
            self.move(x0 + dx, y0 + dy)
            return True
        x, y, w, h = core.resized_geometry(edge, (x0, y0, w0, h0), dx, dy)
        if (x, y) != (x0, y0):
            self.move(x, y)
        self.resize(w, h)
        return True

    def _on_release(self, widget, event):
        d, self._drag = self._drag, None
        if d is None or event.button != 1:
            return False
        kind, _edge, *_rest, moved, on_title = d
        if kind == "move" and not moved and on_title is not None:
            self._start_rename(at=on_title)
        elif kind == "move" and not moved:
            self.present_with_time(event.time)
        self.app.schedule_save()
        return True

    def _on_configure(self, widget, event):
        self.app.schedule_save()
        return False

    # ------------------------------------------------------------ checkboxes
    def _line_bounds(self, line):
        start = self.buf.get_iter_at_line(line)
        end = start.copy()
        if not end.ends_line():
            end.forward_to_line_end()
        return start, end

    def _prefix_len(self, line):
        """Largo del prefijo de checkbox de la línea (0 si no tiene)."""
        start, end = self._line_bounds(line)
        return core.prefix_len(self.buf.get_text(start, end, False))

    def _list_prefix(self, line):
        """(carácter, largo) del prefijo de lista de la línea: ☐ ☑ o •."""
        start, end = self._line_bounds(line)
        return core.list_prefix(self.buf.get_text(start, end, False))

    def toggle_checkbox_lines(self):
        if self.buf.get_has_selection():
            a, b = self.buf.get_selection_bounds()
        else:
            a = b = self.buf.get_iter_at_mark(self.buf.get_insert())
        first, last = a.get_line(), b.get_line()
        if last > first and b.starts_line():
            last -= 1  # selección que termina al inicio de la línea siguiente
        lines = range(first, last + 1)
        self.buf.begin_user_action()
        if all(self._prefix_len(n) for n in lines):
            for n in lines:
                s = self.buf.get_iter_at_line(n)
                e = s.copy()
                e.forward_chars(self._prefix_len(n))
                self.buf.delete(s, e)
        else:
            for n in lines:
                if self._prefix_len(n):
                    continue
                char, plen = self._list_prefix(n)
                if char == core.BULLET:  # un ítem pasa a ser checkbox
                    s = self.buf.get_iter_at_line(n)
                    e = s.copy()
                    e.forward_chars(plen)
                    self.buf.delete(s, e)
                self.buf.insert(self.buf.get_iter_at_line(n), BOX_OFF + " ")
        self.buf.end_user_action()
        self.view.grab_focus()

    def _toggle_box(self, line):
        s = self.buf.get_iter_at_line(line)
        e = s.copy()
        e.forward_char()
        new = core.toggled_box(self.buf.get_text(s, e, False))
        self.buf.begin_user_action()
        self.buf.delete(s, e)
        self.buf.insert(self.buf.get_iter_at_line(line), new)
        self.buf.end_user_action()

    def _on_text_press(self, view, event):
        if event.button != 1 or event.type != Gdk.EventType.BUTTON_PRESS:
            return False
        bx, by = view.window_to_buffer_coords(Gtk.TextWindowType.TEXT, int(event.x), int(event.y))
        ok, it = view.get_iter_at_location(bx, by)
        if ok and it.get_line_offset() == 0 and it.get_char() in BOXES:
            self._toggle_box(it.get_line())
            return True
        return False

    def _on_text_key(self, view, event):
        ctrl = event.state & Gdk.ModifierType.CONTROL_MASK
        shift = event.state & Gdk.ModifierType.SHIFT_MASK
        if ctrl and event.keyval in (Gdk.KEY_t, Gdk.KEY_T):
            self.toggle_checkbox_lines()
            return True
        if event.keyval == Gdk.KEY_space and not ctrl and not self.buf.get_has_selection():
            # "[] " -> ☐, "[x] " -> ☑, "* " -> •  (solo al inicio de la línea)
            cur = self.buf.get_iter_at_mark(self.buf.get_insert())
            start = self.buf.get_iter_at_line(cur.get_line())
            repl = core.autoformat(self.buf.get_text(start, cur, False))
            if repl:
                self.buf.begin_user_action()
                self.buf.delete(start, cur)
                self.buf.insert(start, repl)
                self.buf.end_user_action()
                return True
            return False
        if event.keyval in (Gdk.KEY_Return, Gdk.KEY_KP_Enter) and not (ctrl or shift):
            cur = self.buf.get_iter_at_mark(self.buf.get_insert())
            line = cur.get_line()
            char, plen = self._list_prefix(line)
            if not plen or self.buf.get_has_selection():
                return False
            start, end = self._line_bounds(line)
            if not self.buf.get_text(start, end, False)[plen:].strip():
                # checkbox o ítem vacío + Enter: terminar la lista
                self.buf.delete(start, end)
                return True
            if cur.get_line_offset() < plen:
                return False
            self.buf.begin_user_action()
            self.buf.insert_at_cursor("\n" + core.continuation_of(char) + " ")
            self.buf.end_user_action()
            view.scroll_mark_onscreen(self.buf.get_insert())
            return True
        return False

    def _restyle(self):
        buf = self.buf
        buf.remove_tag(self.tag_done, buf.get_start_iter(), buf.get_end_iter())
        buf.remove_tag(self.tag_box, buf.get_start_iter(), buf.get_end_iter())
        for n in range(buf.get_line_count()):
            _char, plen = self._list_prefix(n)
            if not plen:
                continue
            start, end = self._line_bounds(n)
            box_end = start.copy()
            box_end.forward_char()
            buf.apply_tag(self.tag_box, start, box_end)
            if start.get_char() == core.BOX_ON:
                body = start.copy()
                body.forward_chars(plen)
                buf.apply_tag(self.tag_done, body, end)

    def _on_text_changed(self, buf):
        self._restyle()
        self.app.schedule_save()

    # ------------------------------------------------------------ datos
    def snapshot(self):
        x, y, w, h = self._geom()
        self.data.update(
            title=self.get_title(),
            text=self.buf.get_text(self.buf.get_start_iter(), self.buf.get_end_iter(), False),
            x=x, y=y, w=w, h=h,
        )
        return dict(self.data)


class PostItsApp(Gtk.Application):
    def __init__(self):
        super().__init__(application_id=APP_ID, flags=Gio.ApplicationFlags.FLAGS_NONE)
        self.notes = []
        self._save_id = 0
        self._started = False
        self.restart_requested = False
        self._indicator = None

    def do_startup(self):
        Gtk.Application.do_startup(self)
        try:
            Gtk.Window.set_default_icon_from_file(core.icon_png(256))
        except GLib.Error:
            Gtk.Window.set_default_icon_name("postits")
        provider = Gtk.CssProvider()
        provider.load_from_data(build_css())
        Gtk.StyleContext.add_provider_for_screen(
            Gdk.Screen.get_default(), provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION + 1
        )
        self.hold()  # seguir vivo aunque no queden notas
        # al cerrar sesión / pkill: guardar antes de salir
        for sig in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
            GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, sig, self._on_signal)
        self._raise_id = 0
        self._wnck = Wnck.Screen.get_default() if Wnck is not None else None
        if self._wnck is not None:
            self._wnck.connect("window-stacking-changed", self._on_stacking_changed)
        self._setup_tray()

    # ------------------------------------------------------------ bandeja
    def _setup_tray(self):
        """Ícono en la barra superior con la versión, Reiniciar y Finalizar."""
        if AppIndicator3 is None:
            return
        ind = AppIndicator3.Indicator.new(
            "postits", core.icon_png(64), AppIndicator3.IndicatorCategory.APPLICATION_STATUS
        )
        ind.set_title(core.version_text())
        menu = Gtk.Menu()
        version = Gtk.MenuItem(label=core.version_text())
        version.set_sensitive(False)  # solo informativo
        menu.append(version)
        menu.append(Gtk.SeparatorMenuItem())
        for label, cb in (("Nueva nota", lambda i: self.new_note()),
                          (None, None),
                          ("Reiniciar", lambda i: self.restart()),
                          ("Finalizar", lambda i: self.quit())):
            item = Gtk.SeparatorMenuItem() if label is None else Gtk.MenuItem(label=label)
            if cb:
                item.connect("activate", cb)
            menu.append(item)
        menu.show_all()
        ind.set_menu(menu)
        ind.set_status(AppIndicator3.IndicatorStatus.ACTIVE)
        self._indicator = ind

    def restart(self):
        """Guarda, cierra y vuelve a abrir la app (ver main())."""
        self.restart_requested = True
        self.quit()

    def do_activate(self):
        if self._started:
            # segunda ejecución: agregar una nota nueva
            self.new_note()
            return
        self._started = True
        for d in core.load_notes():
            self._open(d)
        if not self.notes:
            self.new_note()

    def show_about(self, parent):
        dlg = Gtk.AboutDialog(transient_for=parent, modal=True)
        dlg.set_program_name(core.APP_NAME)
        dlg.set_version(core.VERSION)
        dlg.set_comments("Notas adhesivas ancladas al escritorio.")
        dlg.set_website(core.APP_URL)
        dlg.set_website_label("Código y changelog")
        try:
            dlg.set_logo(GdkPixbuf.Pixbuf.new_from_file(core.icon_png(128)))
        except GLib.Error:
            dlg.set_logo_icon_name("postits")
        dlg.set_keep_above(True)
        dlg.run()
        dlg.destroy()

    def _on_signal(self):
        self.quit()
        return GLib.SOURCE_REMOVE

    def do_shutdown(self):
        self.save_now()
        Gtk.Application.do_shutdown(self)

    # ------------------------------------------------------------ apilado
    def _on_stacking_changed(self, screen):
        if not self._raise_id:
            self._raise_id = GLib.timeout_add(50, self._keep_on_top_of_desktop)

    def _keep_on_top_of_desktop(self):
        """El fondo de escritorio (DING) también es una ventana de tipo
        escritorio; al hacerle click se pone encima de las notas. Las volvemos
        a subir, siempre dentro de la capa del escritorio."""
        self._raise_id = 0
        mine = {n.get_window().get_xid(): n for n in self.notes if n.get_window() and not n.pinned}
        seen_note = False
        for w in self._wnck.get_windows_stacked():  # de abajo hacia arriba
            if w.get_xid() in mine:
                seen_note = True
            elif seen_note and w.get_window_type() == Wnck.WindowType.DESKTOP:
                for n in mine.values():
                    gw = n.get_window()
                    # Mutter ignora el raise si la ventana activa tiene un
                    # "user time" más nuevo: lo actualizamos primero.
                    gw.set_user_time(GdkX11.x11_get_server_time(gw))
                    gw.raise_()
                break
        return False

    # ------------------------------------------------------------ notas
    def _open(self, data):
        note = Note(self, data)
        note.show_all()
        self.notes.append(note)
        return note

    def new_note(self, near=None):
        if near is not None:
            x, y = near.get_position()
            x, y = x + 30, y + 30
        else:
            geo = Gdk.Display.get_default().get_primary_monitor() or Gdk.Display.get_default().get_monitor(0)
            area = geo.get_workarea()
            x = area.x + area.width - 300 - 40 * (len(self.notes) % 6)
            y = area.y + 40 + 40 * (len(self.notes) % 6)
        color = near.data.get("color", DEFAULT_COLOR) if near else DEFAULT_COLOR
        note = self._open(core.new_note_data(x, y, color))
        note.present()
        note.view.grab_focus()
        self.schedule_save()
        return note

    def delete_note(self, note):
        self.notes.remove(note)
        note.destroy()
        self.save_now()

    # ------------------------------------------------------------ guardado
    def schedule_save(self):
        if self._save_id:
            GLib.source_remove(self._save_id)
        self._save_id = GLib.timeout_add(core.SAVE_DELAY_MS, self._save_cb)

    def _save_cb(self):
        self._save_id = 0
        self.save_now()
        return False

    def save_now(self):
        if self._save_id:
            GLib.source_remove(self._save_id)
            self._save_id = 0
        if not self._started:
            return
        core.save_notes([n.snapshot() for n in self.notes])


def main():
    if core.handle_version_flag(sys.argv):
        return 0
    GLib.set_prgname("postits")
    GLib.set_application_name(core.APP_NAME)
    app = PostItsApp()
    status = app.run(sys.argv)
    if app.restart_requested:
        # reemplazar el proceso por uno nuevo (las notas ya se guardaron)
        script = os.path.realpath(__file__)
        os.execv(sys.executable, [sys.executable, script] + sys.argv[1:])
    return status


if __name__ == "__main__":
    sys.exit(main())
