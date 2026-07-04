Name:           vidfetch
Version:        1.0.0
Release:        1%{?dist}
Summary:        Dark-mode GTK4 downloader for YouTube and 1800+ sites (yt-dlp GUI)
License:        MIT
URL:            https://github.com/sudomastery/youtube-dl-fedora-UI
Source0:        %{url}/archive/v%{version}/youtube-dl-fedora-UI-%{version}.tar.gz
BuildArch:      noarch

BuildRequires:  desktop-file-utils
BuildRequires:  libappstream-glib

Requires:       python3
Requires:       python3-gobject
Requires:       gtk4
Requires:       libadwaita
Requires:       yt-dlp
Requires:       python3-secretstorage
Requires:       /usr/bin/ffmpeg

%description
VidFetch is a simple dark-mode downloader for YouTube and about 1800 other
sites, powered by yt-dlp. Paste a link, preview the video, pick a quality
(up to 4K) or extract audio to MP3/M4A/Opus, and watch the queue with live
progress. Supports playlists and embedding subtitles, thumbnails and
metadata. Can borrow YouTube cookies from Brave, Chrome, Chromium, Edge or
Firefox to get past bot checks.

%prep
%autosetup -n youtube-dl-fedora-UI-%{version}

%install
install -Dm644 vidfetch.py %{buildroot}%{_datadir}/vidfetch/vidfetch.py
install -Dm644 vidfetch.desktop %{buildroot}%{_datadir}/applications/vidfetch.desktop
for png in icons/downloader-*.png; do
    size=$(basename "$png" .png | cut -d- -f2)
    install -Dm644 "$png" %{buildroot}%{_datadir}/icons/hicolor/${size}x${size}/apps/vidfetch.png
done
install -Dm644 io.github.sudomastery.VidFetch.metainfo.xml %{buildroot}%{_metainfodir}/io.github.sudomastery.VidFetch.metainfo.xml

install -d %{buildroot}%{_bindir}
cat > %{buildroot}%{_bindir}/vidfetch <<'EOF'
#!/usr/bin/bash
exec /usr/bin/python3 /usr/share/vidfetch/vidfetch.py "$@"
EOF
chmod 755 %{buildroot}%{_bindir}/vidfetch

%check
desktop-file-validate %{buildroot}%{_datadir}/applications/vidfetch.desktop
appstream-util validate-relax --nonet %{buildroot}%{_metainfodir}/io.github.sudomastery.VidFetch.metainfo.xml

%files
%license LICENSE
%doc README.md
%{_bindir}/vidfetch
%{_datadir}/vidfetch/
%{_datadir}/applications/vidfetch.desktop
%{_datadir}/icons/hicolor/*/apps/vidfetch.png
%{_metainfodir}/io.github.sudomastery.VidFetch.metainfo.xml

%changelog
* Sat Jul 04 2026 sudomastery <koigu80@gmail.com> - 1.0.0-1
- Initial package
