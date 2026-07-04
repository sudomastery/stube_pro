# STube Youtube Downloader

Youtube Video downloader for Fedora. A dark-mode GTK4 / libadwaita app
powered by [yt-dlp](https://github.com/yt-dlp/yt-dlp), the maintained
successor to youtube-dl. Works on GNOME and KDE.

## Features

- Paste a link (YouTube or any of yt-dlp's ~1800 supported sites) and hit
  Download
- MP4 video (Best Available, 4K, 1440p, 1080p, 720p, 480p) or audio-only
  MP3 / WAV
- Star any quality in the dropdown to make it your permanent default
- My Downloads: full history of everything you've fetched. Click an item
  to play it, hover for open-folder and remove buttons
- Bulk Download: point it at a .txt file with one link per line and it
  queues everything, 3 at a time
- Cookies Setup: borrows YouTube cookies from Brave, Chrome, Chromium,
  Edge or Firefox so YouTube treats downloads like normal viewing. Live
  status icon shows green when configured, red when not
- Self-healing downloads: automatic retries with plain-English error
  messages ("Access to the internet seems to have been lost"), and if
  cookies are missing it finds a working browser by itself
- Desktop notifications for finished and failed downloads, with a single
  summary notification for bulk batches
- Playlist support, subtitle / thumbnail / metadata embedding under
  More options

## Install

```bash
./install.sh
```

The script installs the few Fedora system packages it needs
(`python3-gobject`, `gtk4`, `libadwaita`, `yt-dlp`, `ffmpeg-free`) if
they're missing, then puts STube in your app grid and on your `$PATH`.

## Run

Launch **STube Youtube Downloader** from the app grid, or:

```bash
stube
```

Or straight from the repo without installing:

```bash
/usr/bin/python3 stube.py
```

> Note: it deliberately uses `/usr/bin/python3` (not pyenv/conda pythons)
> so it can see the system GTK bindings.

## Packaging

`stube.spec` builds a native RPM:

```bash
rpmbuild -ba stube.spec
```

## Uninstall

```bash
rm -rf ~/.local/share/stube ~/.local/bin/stube \
       ~/.local/share/applications/stube.desktop \
       ~/.local/share/icons/hicolor/*/apps/stube.png
```
