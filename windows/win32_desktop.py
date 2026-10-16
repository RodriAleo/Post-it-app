"""Anclar ventanas Tk al escritorio de Windows (ctypes, sin dependencias).

Truco clásico de los "gadgets": la nota pasa a ser *propiedad* de Progman
(la ventana del escritorio). Así:
- no aparece en la barra de tareas ni en Alt+Tab,
- sigue visible con Win+D / "Mostrar escritorio",
- y cada vez que deja de estar activa se manda al fondo, debajo de todas las
  ventanas: solo se ve cuando mirás el escritorio.
"""

import ctypes
from ctypes import wintypes

user32 = ctypes.WinDLL("user32", use_last_error=True)

LRESULT = ctypes.c_ssize_t
LONG_PTR = ctypes.c_ssize_t
WNDPROC = ctypes.WINFUNCTYPE(LRESULT, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)

GA_ROOT = 2
GWLP_WNDPROC = -4
GWLP_HWNDPARENT = -8
GWL_EXSTYLE = -20
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_APPWINDOW = 0x00040000
WM_ACTIVATE = 0x0006
WA_INACTIVE = 0
HWND_BOTTOM = 1
HWND_TOPMOST = -1
HWND_NOTOPMOST = -2
SWP_NOSIZE = 0x0001
SWP_NOMOVE = 0x0002
SWP_NOACTIVATE = 0x0010

user32.GetAncestor.argtypes = [wintypes.HWND, wintypes.UINT]
user32.GetAncestor.restype = wintypes.HWND
user32.FindWindowW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR]
user32.FindWindowW.restype = wintypes.HWND
user32.SetWindowPos.argtypes = [
    wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, wintypes.UINT,
]
user32.SetWindowPos.restype = wintypes.BOOL
user32.CallWindowProcW.argtypes = [LONG_PTR, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
user32.CallWindowProcW.restype = LRESULT

# En Python de 32 bits no existen las variantes "Ptr".
_SetWindowLongPtr = getattr(user32, "SetWindowLongPtrW", user32.SetWindowLongW)
_GetWindowLongPtr = getattr(user32, "GetWindowLongPtrW", user32.GetWindowLongW)
_SetWindowLongPtr.argtypes = [wintypes.HWND, ctypes.c_int, LONG_PTR]
_SetWindowLongPtr.restype = LONG_PTR
_GetWindowLongPtr.argtypes = [wintypes.HWND, ctypes.c_int]
_GetWindowLongPtr.restype = LONG_PTR

_subclassed = {}  # hwnd -> (nuevo wndproc, wndproc original); evita que el GC los libere
_pinned = set()   # notas fijadas: siempre encima, no vuelven al fondo


def make_dpi_aware():
    """Texto nítido en pantallas con escalado. Llamar antes de crear Tk."""
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except (AttributeError, OSError):
        try:
            user32.SetProcessDPIAware()
        except (AttributeError, OSError):
            pass


def _hwnd(tk_window):
    return user32.GetAncestor(tk_window.winfo_id(), GA_ROOT)


def send_to_bottom(tk_window):
    hwnd = _hwnd(tk_window)
    user32.SetWindowPos(hwnd, HWND_BOTTOM, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE)


def pin_to_desktop(tk_window):
    """Llamar con la ventana ya mapeada (después de update_idletasks)."""
    hwnd = _hwnd(tk_window)

    progman = user32.FindWindowW("Progman", None)
    if progman:
        _SetWindowLongPtr(hwnd, GWLP_HWNDPARENT, progman)

    ex = _GetWindowLongPtr(hwnd, GWL_EXSTYLE)
    _SetWindowLongPtr(hwnd, GWL_EXSTYLE, (ex | WS_EX_TOOLWINDOW) & ~WS_EX_APPWINDOW)

    if hwnd not in _subclassed:
        old = _GetWindowLongPtr(hwnd, GWLP_WNDPROC)

        def proc(h, msg, wparam, lparam):
            if msg == WM_ACTIVATE and (wparam & 0xFFFF) == WA_INACTIVE and h not in _pinned:
                # al pasar a otra ventana, la nota vuelve al fondo
                user32.SetWindowPos(h, HWND_BOTTOM, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE)
            return user32.CallWindowProcW(old, h, msg, wparam, lparam)

        cb = WNDPROC(proc)
        _subclassed[hwnd] = (cb, old)
        _SetWindowLongPtr(hwnd, GWLP_WNDPROC, ctypes.cast(cb, ctypes.c_void_p).value)

    send_to_bottom(tk_window)


def set_pinned(tk_window, pinned):
    """Fijada: siempre encima de todas las ventanas (sin dueño Progman).
    Desfijada: vuelve a ser una nota del escritorio."""
    hwnd = _hwnd(tk_window)
    flags = SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE
    if pinned:
        _pinned.add(hwnd)
        _SetWindowLongPtr(hwnd, GWLP_HWNDPARENT, 0)
        user32.SetWindowPos(hwnd, HWND_TOPMOST, 0, 0, 0, 0, flags)
    else:
        _pinned.discard(hwnd)
        user32.SetWindowPos(hwnd, HWND_NOTOPMOST, 0, 0, 0, 0, flags)
        progman = user32.FindWindowW("Progman", None)
        if progman:
            _SetWindowLongPtr(hwnd, GWLP_HWNDPARENT, progman)
        send_to_bottom(tk_window)


def unpin(tk_window):
    """Restaurar el wndproc original antes de destruir la ventana."""
    hwnd = _hwnd(tk_window)
    _pinned.discard(hwnd)
    entry = _subclassed.pop(hwnd, None)
    if entry:
        _SetWindowLongPtr(hwnd, GWLP_WNDPROC, entry[1])
