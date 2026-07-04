#!/usr/bin/env bash
# Install VidFetch for the current user (no sudo needed).
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

install -Dm755 vidfetch.py "$HOME/.local/share/vidfetch/vidfetch.py"
install -Dm644 vidfetch.desktop "$HOME/.local/share/applications/vidfetch.desktop"
install -Dm644 vidfetch.svg "$HOME/.local/share/icons/hicolor/scalable/apps/vidfetch.svg"

# Convenience launcher on PATH
install -d "$HOME/.local/bin"
cat > "$HOME/.local/bin/vidfetch" <<'EOF'
#!/usr/bin/env bash
exec /usr/bin/python3 "$HOME/.local/share/vidfetch/vidfetch.py" "$@"
EOF
chmod +x "$HOME/.local/bin/vidfetch"

gtk4-update-icon-cache -q "$HOME/.local/share/icons/hicolor" 2>/dev/null || true
update-desktop-database "$HOME/.local/share/applications" 2>/dev/null || true

echo "Installed. Launch with 'vidfetch' or from the app grid (VidFetch)."
