#!/usr/bin/env bash
# Install STube for the current user (no sudo needed).
set -euo pipefail
cd "$(dirname "$0")"

# Runtime deps are Fedora system packages; install if missing.
missing=()
rpm -q python3-gobject >/dev/null 2>&1 || missing+=(python3-gobject)
rpm -q gtk4            >/dev/null 2>&1 || missing+=(gtk4)
rpm -q libadwaita      >/dev/null 2>&1 || missing+=(libadwaita)
rpm -q yt-dlp          >/dev/null 2>&1 || missing+=(yt-dlp)
rpm -q ffmpeg-free >/dev/null 2>&1 || rpm -q ffmpeg >/dev/null 2>&1 || missing+=(ffmpeg-free)
if [ ${#missing[@]} -gt 0 ]; then
    echo "Installing system packages: ${missing[*]}"
    sudo dnf install -y "${missing[@]}"
fi

install -Dm755 stube.py "$HOME/.local/share/stube/stube.py"
# Point Exec at the absolute launcher path so the app grid entry works
# regardless of the session's PATH.
sed "s|^Exec=stube|Exec=$HOME/.local/bin/stube|" io.github.sudomastery.stube_pro.desktop \
    > "$HOME/.local/share/applications/io.github.sudomastery.stube_pro.desktop"
for png in icons/stube-*.png; do
    size=$(basename "$png" .png | cut -d- -f2)
    # hicolor has no 1024x1024 directory; skip that size.
    [ "$size" = 1024 ] && continue
    install -Dm644 "$png" \
        "$HOME/.local/share/icons/hicolor/${size}x${size}/apps/io.github.sudomastery.stube_pro.png"
done

# Convenience launcher on PATH
install -d "$HOME/.local/bin"
cat > "$HOME/.local/bin/stube" <<'EOF'
#!/usr/bin/env bash
exec /usr/bin/python3 "$HOME/.local/share/stube/stube.py" "$@"
EOF
chmod +x "$HOME/.local/bin/stube"

gtk4-update-icon-cache -q "$HOME/.local/share/icons/hicolor" 2>/dev/null || true
update-desktop-database "$HOME/.local/share/applications" 2>/dev/null || true

echo "Installed. Launch with 'stube' or from the app grid (STube)."
