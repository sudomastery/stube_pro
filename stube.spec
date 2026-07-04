Name:           stube
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
STube is a simple dark-mode downloader for YouTube and about 1800 other
sites, powered by yt-dlp. Paste a link, preview the video, pick a quality
(up to 4K) or extract audio to MP3/M4A/Opus, and watch the queue with live
progress. Supports playlists and embedding subtitles, thumbnails and
metadata. Can borrow YouTube cookies from Brave, Chrome, Chromium, Edge or
Firefox to get past bot checks.

%prep
%autosetup -n youtube-dl-fedora-UI-%{version}

%install
install -Dm644 stube.py %{buildroot}%{_datadir}/stube/stube.py
install -Dm644 stube.desktop %{buildroot}%{_datadir}/applications/stube.desktop
for png in icons/stube-*.png; do
    size=$(basename "$png" .png | cut -d- -f2)
    # hicolor has no 1024x1024 directory; skip that size.
    [ "$size" = 1024 ] && continue
    install -Dm644 "$png" %{buildroot}%{_datadir}/icons/hicolor/${size}x${size}/apps/stube.png
done
install -Dm644 io.github.sudomastery.STube.metainfo.xml %{buildroot}%{_metainfodir}/io.github.sudomastery.STube.metainfo.xml

install -d %{buildroot}%{_bindir}
cat > %{buildroot}%{_bindir}/stube <<'EOF'
#!/usr/bin/bash
exec /usr/bin/python3 /usr/share/stube/stube.py "$@"
EOF
chmod 755 %{buildroot}%{_bindir}/stube

%check
desktop-file-validate %{buildroot}%{_datadir}/applications/stube.desktop
appstream-util validate-relax --nonet %{buildroot}%{_metainfodir}/io.github.sudomastery.STube.metainfo.xml

%files
%license LICENSE
%doc README.md
%{_bindir}/stube
%{_datadir}/stube/
%{_datadir}/applications/stube.desktop
%{_datadir}/icons/hicolor/*/apps/stube.png
%{_metainfodir}/io.github.sudomastery.STube.metainfo.xml

%changelog
* Sat Jul 04 2026 sudomastery <koigu80@gmail.com> - 1.0.0-1
- Initial package
