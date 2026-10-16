#!/bin/sh
# Instala Post-its para el usuario actual y lo arranca al iniciar sesión.
set -e
REPO="$(cd "$(dirname "$0")/.." && pwd)"
LIB="$HOME/.local/lib/postits"

# cerrar una instancia anterior (guarda las notas al recibir SIGTERM)
pkill -f "postits.py" 2>/dev/null && sleep 1 || true

mkdir -p "$LIB" "$HOME/.local/bin" "$HOME/.local/share/applications" "$HOME/.config/autostart"
rm -rf "$LIB/common" "$LIB/linux"
cp -r "$REPO/common" "$REPO/linux" "$LIB/"
rm -rf "$LIB"/*/__pycache__

cat > "$HOME/.local/bin/postits" <<WRAPPER
#!/bin/sh
exec /usr/bin/python3 "$LIB/linux/postits.py" "\$@"
WRAPPER
chmod 755 "$HOME/.local/bin/postits"

cat > "$HOME/.local/share/applications/postits.desktop" <<DESKTOP
[Desktop Entry]
Type=Application
Name=Post-its
Comment=Notas adhesivas en el escritorio (abrirlo de nuevo crea una nota)
Exec=$HOME/.local/bin/postits
Icon=accessories-text-editor
Terminal=false
Categories=Utility;
StartupNotify=false
DESKTOP

cp "$HOME/.local/share/applications/postits.desktop" "$HOME/.config/autostart/postits.desktop"
echo "X-GNOME-Autostart-enabled=true" >> "$HOME/.config/autostart/postits.desktop"

nohup "$HOME/.local/bin/postits" >/dev/null 2>&1 &
echo "Post-its instalado. Notas en ~/.local/share/postits/notes.json"
