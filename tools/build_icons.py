#!/usr/bin/python3
"""Genera los PNG y el .ico a partir de assets/postits.svg.

Requiere (Linux): python3-gi, gir1.2-rsvg-2.0, python3-cairo, python3-pil.
Los archivos generados se versionan, así que solo hace falta correrlo si
cambia el SVG.
"""

import io
import os

import cairo
import gi

gi.require_version("Rsvg", "2.0")
from gi.repository import Rsvg  # noqa: E402
from PIL import Image  # noqa: E402

ASSETS = os.path.join(os.path.dirname(os.path.realpath(__file__)), "..", "assets")
SVG = os.path.join(ASSETS, "postits.svg")
PNG_SIZES = (16, 24, 32, 48, 64, 128, 256)


def render(size):
    handle = Rsvg.Handle.new_from_file(SVG)
    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, size, size)
    ctx = cairo.Context(surface)
    vp = Rsvg.Rectangle()
    vp.x, vp.y, vp.width, vp.height = 0, 0, size, size
    handle.render_document(ctx, vp)
    buf = io.BytesIO()
    surface.write_to_png(buf)
    return Image.open(io.BytesIO(buf.getvalue())).convert("RGBA")


def main():
    images = {s: render(s) for s in PNG_SIZES}
    os.makedirs(os.path.join(ASSETS, "png"), exist_ok=True)
    for s, img in images.items():
        img.save(os.path.join(ASSETS, "png", f"postits-{s}.png"))
    images[256].save(
        os.path.join(ASSETS, "postits.ico"),
        sizes=[(s, s) for s in PNG_SIZES],
        append_images=[images[s] for s in PNG_SIZES if s != 256],
    )
    print("Íconos generados en", os.path.normpath(ASSETS))


if __name__ == "__main__":
    main()
