Name:           stube
Version:        1.0.8
Release:        1%{?dist}
Summary:        Dark-mode GTK4 downloader for YouTube and 1800+ sites (yt-dlp GUI)
License:        MIT
URL:            https://github.com/sudomastery/stube_pro
Source0:        %{url}/archive/v%{version}/stube-%{version}.tar.gz
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
%autosetup -n stube_pro-%{version}

%install
install -Dm644 stube.py %{buildroot}%{_datadir}/stube/stube.py
install -Dm644 io.github.sudomastery.stube_pro.desktop %{buildroot}%{_datadir}/applications/io.github.sudomastery.stube_pro.desktop
for png in icons/stube-*.png; do
    size=$(basename "$png" .png | cut -d- -f2)
    # hicolor has no 1024x1024 directory; skip that size.
    [ "$size" = 1024 ] && continue
    install -Dm644 "$png" %{buildroot}%{_datadir}/icons/hicolor/${size}x${size}/apps/io.github.sudomastery.stube_pro.png
done
install -Dm644 io.github.sudomastery.stube_pro.metainfo.xml %{buildroot}%{_metainfodir}/io.github.sudomastery.stube_pro.metainfo.xml

install -d %{buildroot}%{_bindir}
cat > %{buildroot}%{_bindir}/stube <<'EOF'
#!/usr/bin/bash
exec /usr/bin/python3 /usr/share/stube/stube.py "$@"
EOF
chmod 755 %{buildroot}%{_bindir}/stube

%check
desktop-file-validate %{buildroot}%{_datadir}/applications/io.github.sudomastery.stube_pro.desktop
appstream-util validate-relax --nonet %{buildroot}%{_metainfodir}/io.github.sudomastery.stube_pro.metainfo.xml

%files
%license LICENSE
%doc README.md
%{_bindir}/stube
%{_datadir}/stube/
%{_datadir}/applications/io.github.sudomastery.stube_pro.desktop
%{_datadir}/icons/hicolor/*/apps/io.github.sudomastery.stube_pro.png
%{_metainfodir}/io.github.sudomastery.stube_pro.metainfo.xml

%changelog
* Tue Jul 14 2026 sudomastery <koigu80@gmail.com> - 1.0.8-1
- Uniform width for the bottom feature cards

* Tue Jul 14 2026 sudomastery <koigu80@gmail.com> - 1.0.7-1
- Fix cookie decryption on KDE Plasma (read the key from KWallet over D-Bus)
- Bundle the yt-dlp EJS challenge solver so all video qualities are available

* Tue Jul 14 2026 sudomastery <koigu80@gmail.com> - 1.0.6-1
- Fix browser cookie import when running as a Flatpak

* Tue Jul 14 2026 sudomastery <koigu80@gmail.com> - 1.0.5-1
- Show the app version in the Buy Coffee dialog

* Tue Jul 14 2026 sudomastery <koigu80@gmail.com> - 1.0.4-1
- Show the video title instead of the URL while downloading

* Mon Jul 13 2026 sudomastery <koigu80@gmail.com> - 1.0.3-1
- Rename application ID to io.github.sudomastery.stube_pro

* Sun Jul 05 2026 sudomastery <koigu80@gmail.com> - 1.0.1-1
- Point Buy Coffee link at Ko-fi

* Sat Jul 04 2026 sudomastery <koigu80@gmail.com> - 1.0.0-1
- Initial package
