#!/bin/sh
# Quita Post-its (las notas guardadas en ~/.local/share/postits se conservan).
pkill -f "postits.py" 2>/dev/null
rm -rf "$HOME/.local/lib/postits"
rm -f "$HOME/.local/bin/postits" \
      "$HOME/.local/share/applications/postits.desktop" \
      "$HOME/.config/autostart/postits.desktop"
echo "Post-its desinstalado."
