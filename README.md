# VidFetch

A simple, dark-mode video downloader for **Fedora**, in the spirit of
[Stacher](https://stacher.io/) — a native GTK4 / libadwaita front-end for
[yt-dlp](https://github.com/yt-dlp/yt-dlp) (the maintained successor to
youtube-dl).

![dark mode GTK4 app](vidfetch.svg)

## Features

- Paste a link (YouTube or any of yt-dlp's ~1800 supported sites), get an
  instant preview with thumbnail, title, channel and duration
- Quality picker: best / 4K / 1440p / 1080p / 720p / 480p
- Audio-only extraction to MP3, M4A or Opus
- Full playlist downloads
- Embed subtitles, thumbnail and metadata into the file
- Download queue with live progress, speed, ETA and cancel
- Choose any destination folder (defaults to `~/Videos`)
- Always dark. No settings needed.

## Install

```bash
./install.sh
```

The script installs the few Fedora system packages it needs (`python3-gobject`,
`gtk4`, `libadwaita`, `yt-dlp`, `ffmpeg-free`) if they're missing, then puts
VidFetch in your app grid and on your `$PATH`.

## Run

Launch **VidFetch** from the app grid, or:

```bash
vidfetch
```

Or straight from the repo without installing:

```bash
/usr/bin/python3 vidfetch.py
```

> Note: it deliberately uses `/usr/bin/python3` (not pyenv/conda pythons) so it
> can see the system GTK bindings.

## Uninstall

```bash
rm -rf ~/.local/share/vidfetch ~/.local/bin/vidfetch \
       ~/.local/share/applications/vidfetch.desktop \
       ~/.local/share/icons/hicolor/scalable/apps/vidfetch.svg
```
