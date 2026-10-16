#!/bin/sh
# Quita Post-its (las notas guardadas en ~/.local/share/postits se conservan).
pkill -f "^/usr/bin/python3 .*/linux/postits\.py" 2>/dev/null
rm -rf "$HOME/.local/lib/postits"
rm -f "$HOME/.local/bin/postits" \
      "$HOME/.local/share/applications/postits.desktop" \
      "$HOME/.config/autostart/postits.desktop" \
      "$HOME"/.local/share/icons/hicolor/*/apps/postits.png \
      "$HOME/.local/share/icons/hicolor/scalable/apps/postits.svg"
echo "Post-its desinstalado."
