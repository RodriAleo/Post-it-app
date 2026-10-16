#!/bin/sh
# Instala Post-its para el usuario actual y lo arranca al iniciar sesión.
set -e
REPO="$(cd "$(dirname "$0")/.." && pwd)"
LIB="$HOME/.local/lib/postits"

# cerrar una instancia anterior (guarda las notas al recibir SIGTERM)
pkill -f "^/usr/bin/python3 .*/linux/postits\.py" 2>/dev/null && sleep 1 || true

mkdir -p "$LIB" "$HOME/.local/bin" "$HOME/.local/share/applications" "$HOME/.config/autostart"
rm -rf "$LIB/common" "$LIB/linux" "$LIB/assets"
cp -r "$REPO/common" "$REPO/linux" "$REPO/assets" "$LIB/"
rm -rf "$LIB"/*/__pycache__

# ícono
ICONS="$HOME/.local/share/icons/hicolor"
for s in 16 24 32 48 64 128 256; do
    mkdir -p "$ICONS/${s}x${s}/apps"
    cp "$REPO/assets/png/postits-$s.png" "$ICONS/${s}x${s}/apps/postits.png"
done
mkdir -p "$ICONS/scalable/apps"
cp "$REPO/assets/postits.svg" "$ICONS/scalable/apps/postits.svg"
gtk-update-icon-cache -q -t "$ICONS" 2>/dev/null || true

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
Icon=postits
Terminal=false
Categories=Utility;
StartupNotify=false
DESKTOP

cp "$HOME/.local/share/applications/postits.desktop" "$HOME/.config/autostart/postits.desktop"
echo "X-GNOME-Autostart-enabled=true" >> "$HOME/.config/autostart/postits.desktop"

nohup "$HOME/.local/bin/postits" >/dev/null 2>&1 &
echo "$("$HOME/.local/bin/postits" --version) instalado. Notas en ~/.local/share/postits/notes.json"
