#!/usr/bin/python3
"""VidFetch — a simple dark-mode yt-dlp GUI for Fedora (GTK4 + libadwaita)."""

import os
import threading
import urllib.request

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gdk, GLib, Gio, Gtk  # noqa: E402

import yt_dlp  # noqa: E402

APP_ID = "io.github.sudomastery.VidFetch"

# yt-dlp needs a JS runtime (deno) for YouTube; make sure ~/.local/bin is
# visible even when launched from the app grid.
os.environ["PATH"] = os.pathsep.join(
    [os.path.expanduser("~/.local/bin"), os.environ.get("PATH", "")])

# Browsers whose cookies yt-dlp can borrow to avoid YouTube's bot checks,
# listed with the config dir that tells us they're installed.
BROWSERS = [
    ("Brave", "brave", "~/.config/BraveSoftware"),
    ("Chrome", "chrome", "~/.config/google-chrome"),
    ("Chromium", "chromium", "~/.config/chromium"),
    ("Edge", "edge", "~/.config/microsoft-edge"),
    ("Firefox", "firefox", "~/.mozilla/firefox"),
]


# YouTube's default web client now demands PO tokens and 403s the media
# download; the tv client is the reliable path (verified on this machine).
EXTRACTOR_ARGS = {"youtube": {"player_client": ["tv"]}}


def detect_browsers():
    found = [(label, key) for label, key, path in BROWSERS
             if os.path.isdir(os.path.expanduser(path))]
    return found + [("None (anonymous)", None)]

QUALITIES = [
    ("Best available", "bv*+ba/b"),
    ("2160p (4K)", "bv*[height<=2160]+ba/b[height<=2160]"),
    ("1440p", "bv*[height<=1440]+ba/b[height<=1440]"),
    ("1080p", "bv*[height<=1080]+ba/b[height<=1080]"),
    ("720p", "bv*[height<=720]+ba/b[height<=720]"),
    ("480p", "bv*[height<=480]+ba/b[height<=480]"),
    ("Audio only — MP3", "audio:mp3"),
    ("Audio only — M4A", "audio:m4a"),
    ("Audio only — Opus", "audio:opus"),
]


def human_size(n):
    if not n:
        return "?"
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"


class Cancelled(Exception):
    pass


class DownloadRow(Gtk.ListBoxRow):
    """One entry in the download queue."""

    def __init__(self, title, on_cancel):
        super().__init__(activatable=False, selectable=False)
        self.cancelled = False
        self._on_cancel = on_cancel

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6,
                      margin_top=10, margin_bottom=10,
                      margin_start=12, margin_end=12)
        top = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)

        self.title_label = Gtk.Label(label=title, xalign=0, hexpand=True,
                                     ellipsize=3, css_classes=["heading"])
        self.cancel_btn = Gtk.Button(icon_name="process-stop-symbolic",
                                     tooltip_text="Cancel",
                                     valign=Gtk.Align.CENTER,
                                     css_classes=["flat", "circular"])
        self.cancel_btn.connect("clicked", self._cancel_clicked)

        top.append(self.title_label)
        top.append(self.cancel_btn)

        self.progress = Gtk.ProgressBar(show_text=True, text="Queued")
        self.status_label = Gtk.Label(label="", xalign=0,
                                      css_classes=["dim-label", "caption"])

        box.append(top)
        box.append(self.progress)
        box.append(self.status_label)
        self.set_child(box)

    def _cancel_clicked(self, _btn):
        self.cancelled = True
        self.cancel_btn.set_sensitive(False)
        self.set_status("Cancelling…")
        self._on_cancel()

    # All setters below are called via GLib.idle_add from worker threads.
    def set_fraction(self, frac, text):
        self.progress.set_fraction(frac)
        self.progress.set_text(text)

    def set_status(self, text):
        self.status_label.set_label(text)

    def finish(self, ok, message):
        self.cancel_btn.set_sensitive(False)
        self.progress.set_fraction(1.0 if ok else 0.0)
        self.progress.set_text("Done" if ok else "Failed")
        self.progress.add_css_class("success" if ok else "error")
        self.status_label.set_label(message)


class VidFetchWindow(Adw.ApplicationWindow):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.set_title("VidFetch")
        self.set_default_size(560, 760)

        self.download_dir = (
            GLib.get_user_special_dir(GLib.UserDirectory.DIRECTORY_VIDEOS)
            or os.path.expanduser("~/Videos")
        )
        os.makedirs(self.download_dir, exist_ok=True)
        self._current_info = None

        toolbar = Adw.ToolbarView()
        header = Adw.HeaderBar()
        header.set_title_widget(Adw.WindowTitle(title="VidFetch",
                                                subtitle="yt-dlp for Fedora"))

        folder_btn = Gtk.Button(icon_name="folder-open-symbolic",
                                tooltip_text="Choose download folder")
        folder_btn.connect("clicked", self.on_choose_folder)
        header.pack_start(folder_btn)
        toolbar.add_top_bar(header)

        self.toasts = Adw.ToastOverlay()
        scroll = Gtk.ScrolledWindow(vexpand=True)
        page = Adw.Clamp(maximum_size=640, margin_top=18, margin_bottom=18,
                         margin_start=14, margin_end=14)
        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=18)

        # --- URL entry ---------------------------------------------------
        url_group = Adw.PreferencesGroup(title="Video URL")
        url_box = Gtk.Box(spacing=8)
        self.url_entry = Gtk.Entry(hexpand=True,
                                   placeholder_text="Paste a YouTube (or any supported) link…")
        self.url_entry.connect("activate", self.on_fetch_info)
        paste_btn = Gtk.Button(icon_name="edit-paste-symbolic",
                               tooltip_text="Paste from clipboard")
        paste_btn.connect("clicked", self.on_paste)
        self.fetch_btn = Gtk.Button(label="Fetch", css_classes=["suggested-action"])
        self.fetch_btn.connect("clicked", self.on_fetch_info)
        url_box.append(self.url_entry)
        url_box.append(paste_btn)
        url_box.append(self.fetch_btn)
        url_group.add(url_box)
        content.append(url_group)

        # --- Preview card ------------------------------------------------
        self.preview = Adw.PreferencesGroup(visible=False)
        pbox = Gtk.Box(spacing=12, css_classes=["card"],
                       margin_top=4, margin_bottom=4)
        self.thumb = Gtk.Picture(content_fit=Gtk.ContentFit.COVER,
                                 width_request=160, height_request=90,
                                 css_classes=["thumb"])
        info_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4,
                           margin_top=10, margin_bottom=10, margin_end=10,
                           valign=Gtk.Align.CENTER, hexpand=True)
        self.info_title = Gtk.Label(xalign=0, wrap=True, lines=2, ellipsize=3,
                                    css_classes=["heading"])
        self.info_meta = Gtk.Label(xalign=0, css_classes=["dim-label", "caption"])
        info_box.append(self.info_title)
        info_box.append(self.info_meta)
        pbox.append(self.thumb)
        pbox.append(info_box)
        self.preview.add(pbox)
        content.append(self.preview)

        # --- Options -----------------------------------------------------
        opts = Adw.PreferencesGroup(title="Options")

        self.quality_row = Adw.ComboRow(title="Quality")
        model = Gtk.StringList()
        for label, _ in QUALITIES:
            model.append(label)
        self.quality_row.set_model(model)
        opts.add(self.quality_row)

        self.playlist_row = Adw.SwitchRow(
            title="Download full playlist",
            subtitle="If the link is a playlist, grab every video")
        opts.add(self.playlist_row)

        self.subs_row = Adw.SwitchRow(title="Embed subtitles",
                                      subtitle="English, when available")
        opts.add(self.subs_row)

        self.thumb_row = Adw.SwitchRow(title="Embed thumbnail")
        opts.add(self.thumb_row)

        self.meta_row = Adw.SwitchRow(title="Embed metadata", active=True)
        opts.add(self.meta_row)

        self.browsers = detect_browsers()
        self.cookies_row = Adw.ComboRow(
            title="Browser cookies",
            subtitle="Sign requests with your browser's YouTube session")
        cmodel = Gtk.StringList()
        for label, _key in self.browsers:
            cmodel.append(label)
        self.cookies_row.set_model(cmodel)
        opts.add(self.cookies_row)

        self.folder_row = Adw.ActionRow(title="Save to",
                                        subtitle=self.download_dir,
                                        activatable=True)
        self.folder_row.add_suffix(Gtk.Image(icon_name="folder-open-symbolic"))
        self.folder_row.connect("activated", self.on_choose_folder)
        opts.add(self.folder_row)
        content.append(opts)

        # --- Download button ----------------------------------------------
        self.dl_btn = Gtk.Button(label="Download",
                                 css_classes=["suggested-action", "pill"],
                                 halign=Gtk.Align.CENTER,
                                 margin_top=2)
        self.dl_btn.connect("clicked", self.on_download)
        content.append(self.dl_btn)

        # --- Queue ---------------------------------------------------------
        queue_group = Adw.PreferencesGroup(title="Downloads")
        self.queue = Gtk.ListBox(css_classes=["boxed-list"],
                                 selection_mode=Gtk.SelectionMode.NONE)
        self.queue_placeholder = Gtk.Label(
            label="Nothing downloading yet",
            css_classes=["dim-label"], margin_top=12, margin_bottom=12)
        self.queue.set_placeholder(self.queue_placeholder)
        queue_group.add(self.queue)
        content.append(queue_group)

        page.set_child(content)
        scroll.set_child(page)
        self.toasts.set_child(scroll)
        toolbar.set_content(self.toasts)
        self.set_content(toolbar)

        css = Gtk.CssProvider()
        css.load_from_string(".thumb { border-radius: 10px 0 0 10px; }")
        Gtk.StyleContext.add_provider_for_display(
            Gdk.Display.get_default(), css,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

    # ------------------------------------------------------------------ UI
    def toast(self, text):
        self.toasts.add_toast(Adw.Toast(title=text, timeout=4))

    def on_paste(self, _btn):
        def got_text(clipboard, result):
            try:
                text = clipboard.read_text_finish(result)
                if text:
                    self.url_entry.set_text(text.strip())
                    self.on_fetch_info(None)
            except GLib.Error:
                pass
        self.get_clipboard().read_text_async(None, got_text)

    def on_choose_folder(self, *_a):
        dialog = Gtk.FileDialog(title="Choose download folder")
        def done(dlg, result):
            try:
                folder = dlg.select_folder_finish(result)
            except GLib.Error:
                return
            self.download_dir = folder.get_path()
            self.folder_row.set_subtitle(self.download_dir)
        dialog.select_folder(self, None, done)

    # ----------------------------------------------------------- metadata
    def on_fetch_info(self, _w):
        url = self.url_entry.get_text().strip()
        if not url:
            self.toast("Paste a link first")
            return
        self.fetch_btn.set_sensitive(False)
        self.fetch_btn.set_label("Fetching…")
        threading.Thread(target=self._fetch_info,
                         args=(url, self.selected_browser()),
                         daemon=True).start()

    def selected_browser(self):
        return self.browsers[self.cookies_row.get_selected()][1]

    def _fetch_info(self, url, browser):
        try:
            opts = {"quiet": True, "noplaylist": True,
                    "extract_flat": "in_playlist",
                    "extractor_args": EXTRACTOR_ARGS}
            if browser:
                opts["cookiesfrombrowser"] = (browser,)
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=False)
            texture = None
            if info.get("thumbnail"):
                try:
                    req = urllib.request.Request(
                        info["thumbnail"], headers={"User-Agent": "Mozilla/5.0"})
                    data = urllib.request.urlopen(req, timeout=10).read()
                    texture = Gdk.Texture.new_from_bytes(GLib.Bytes.new(data))
                except Exception:
                    pass
            GLib.idle_add(self._show_info, url, info, texture)
        except Exception as e:
            GLib.idle_add(self._info_failed, str(e))

    def _info_failed(self, msg):
        self.fetch_btn.set_sensitive(True)
        self.fetch_btn.set_label("Fetch")
        self.toast(f"Could not read link: {msg[:120]}")

    def _show_info(self, url, info, texture):
        self.fetch_btn.set_sensitive(True)
        self.fetch_btn.set_label("Fetch")
        self._current_info = {"url": url, "title": info.get("title") or url}
        self.info_title.set_label(self._current_info["title"])
        parts = []
        if info.get("uploader"):
            parts.append(info["uploader"])
        if info.get("duration"):
            m, s = divmod(int(info["duration"]), 60)
            h, m = divmod(m, 60)
            parts.append(f"{h}:{m:02}:{s:02}" if h else f"{m}:{s:02}")
        if info.get("_type") == "playlist":
            parts.append("playlist")
        self.info_meta.set_label("  ·  ".join(parts))
        if texture:
            self.thumb.set_paintable(texture)
        self.preview.set_visible(True)

    # ----------------------------------------------------------- download
    def on_download(self, _btn):
        url = self.url_entry.get_text().strip()
        if not url:
            self.toast("Paste a link first")
            return
        title = (self._current_info["title"]
                 if self._current_info and self._current_info["url"] == url
                 else url)

        row = DownloadRow(title, on_cancel=lambda: None)
        self.queue.prepend(row)

        label, fmt = QUALITIES[self.quality_row.get_selected()]
        job = {
            "url": url,
            "fmt": fmt,
            "playlist": self.playlist_row.get_active(),
            "subs": self.subs_row.get_active(),
            "thumb": self.thumb_row.get_active(),
            "meta": self.meta_row.get_active(),
            "outdir": self.download_dir,
            "browser": self.selected_browser(),
        }
        threading.Thread(target=self._download, args=(job, row), daemon=True).start()

    def _build_opts(self, job, row):
        def hook(d):
            if row.cancelled:
                raise Cancelled()
            if d["status"] == "downloading":
                total = d.get("total_bytes") or d.get("total_bytes_estimate")
                done = d.get("downloaded_bytes", 0)
                frac = done / total if total else 0.0
                speed = d.get("speed")
                eta = d.get("eta")
                status = f"{human_size(done)} / {human_size(total)}"
                if speed:
                    status += f"  ·  {human_size(speed)}/s"
                if eta:
                    status += f"  ·  {eta}s left"
                GLib.idle_add(row.set_fraction, frac, f"{frac * 100:.0f}%")
                GLib.idle_add(row.set_status, status)
            elif d["status"] == "finished":
                GLib.idle_add(row.set_fraction, 1.0, "Processing…")
                GLib.idle_add(row.set_status, "Merging / converting with ffmpeg")

        opts = {
            "outtmpl": os.path.join(job["outdir"], "%(title)s [%(id)s].%(ext)s"),
            "progress_hooks": [hook],
            "noplaylist": not job["playlist"],
            "quiet": True,
            "noprogress": True,
            "postprocessors": [],
            "extractor_args": EXTRACTOR_ARGS,
        }
        if job["browser"]:
            opts["cookiesfrombrowser"] = (job["browser"],)

        if job["fmt"].startswith("audio:"):
            codec = job["fmt"].split(":")[1]
            opts["format"] = "ba/b"
            opts["postprocessors"].append({
                "key": "FFmpegExtractAudio",
                "preferredcodec": codec,
                "preferredquality": "0",
            })
        else:
            opts["format"] = job["fmt"]
            opts["merge_output_format"] = "mp4"

        if job["subs"]:
            opts["writesubtitles"] = True
            opts["subtitleslangs"] = ["en.*"]
            opts["postprocessors"].append({"key": "FFmpegEmbedSubtitle"})
        if job["thumb"]:
            opts["writethumbnail"] = True
            opts["postprocessors"].append({"key": "EmbedThumbnail"})
        if job["meta"]:
            opts["postprocessors"].append({"key": "FFmpegMetadata"})
        return opts

    def _download(self, job, row):
        GLib.idle_add(row.set_status, "Starting…")
        try:
            with yt_dlp.YoutubeDL(self._build_opts(job, row)) as ydl:
                ydl.download([job["url"]])
            GLib.idle_add(row.finish, True, f"Saved to {job['outdir']}")
            GLib.idle_add(self.toast, "Download finished")
        except Cancelled:
            GLib.idle_add(row.finish, False, "Cancelled")
        except Exception as e:
            GLib.idle_add(row.finish, False, str(e)[:200])
            GLib.idle_add(self.toast, "Download failed")


class VidFetchApp(Adw.Application):
    def __init__(self):
        super().__init__(application_id=APP_ID,
                         flags=Gio.ApplicationFlags.DEFAULT_FLAGS)

    def do_activate(self):
        Adw.StyleManager.get_default().set_color_scheme(
            Adw.ColorScheme.FORCE_DARK)
        win = self.get_active_window() or VidFetchWindow(application=self)
        win.present()


if __name__ == "__main__":
    raise SystemExit(VidFetchApp().run(None))
