#!/usr/bin/python3
"""STube: Youtube Video downloader for Fedora (GTK4 + libadwaita, yt-dlp)."""

import json
import os
import subprocess
import threading
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gdk, GLib, Gio, Gtk  # noqa: E402

import yt_dlp  # noqa: E402
from yt_dlp.cookies import extract_cookies_from_browser  # noqa: E402

APP_ID = "io.github.sudomastery.stube_pro"
APP_NAME = "STube"
ACCENT = "#E2603F"
COFFEE_URL = "https://ko-fi.com/sudomastery"
MAX_CONCURRENT = 3
RETRY_DELAYS = [3, 8, 20]

# yt-dlp needs a JS runtime (deno) for YouTube; make sure ~/.local/bin is
# visible even when launched from the app grid.
os.environ["PATH"] = os.pathsep.join(
    [os.path.expanduser("~/.local/bin"), os.environ.get("PATH", "")])

# YouTube's default web client demands PO tokens and 403s media downloads;
# the tv client is the reliable path (verified on this machine).
EXTRACTOR_ARGS = {"youtube": {"player_client": ["tv"]}}

BROWSERS = [
    ("Brave", "brave", "~/.config/BraveSoftware"),
    ("Chrome", "chrome", "~/.config/google-chrome"),
    ("Chromium", "chromium", "~/.config/chromium"),
    ("Edge", "edge", "~/.config/microsoft-edge"),
    ("Firefox", "firefox", "~/.mozilla/firefox"),
]

VIDEO_QUALITIES = [
    ("Best Available", "bv*+ba/b"),
    ("2160p (4K)", "bv*[height<=2160]+ba/b[height<=2160]"),
    ("1440p", "bv*[height<=1440]+ba/b[height<=1440]"),
    ("1080p", "bv*[height<=1080]+ba/b[height<=1080]"),
    ("720p", "bv*[height<=720]+ba/b[height<=720]"),
    ("480p", "bv*[height<=480]+ba/b[height<=480]"),
]

CONFIG_DIR = os.path.join(GLib.get_user_config_dir(), "stube")

# one-time migration from the app's old name
_OLD_CONFIG_DIR = os.path.join(GLib.get_user_config_dir(), "vidfetch")
if os.path.isdir(_OLD_CONFIG_DIR) and not os.path.isdir(CONFIG_DIR):
    try:
        os.rename(_OLD_CONFIG_DIR, CONFIG_DIR)
    except OSError:
        pass
HISTORY_FILE = os.path.join(CONFIG_DIR, "history.json")
SETTINGS_FILE = os.path.join(CONFIG_DIR, "settings.json")

CSS = f"""
@define-color accent_bg_color #BF5B3E;
@define-color accent_fg_color #ffffff;
@define-color accent_color #E8917C;
@define-color dialog_bg_color #242120;
@define-color popover_bg_color #2b2827;
@define-color headerbar_bg_color #262322;
@define-color card_bg_color #292625;
@define-color view_bg_color #1b1918;
@define-color window_bg_color #1b1918;

window {{ background-color: #1b1918; }}
headerbar {{ background-color: #262322; box-shadow: none; }}
.app-title {{ font-size: 12px; letter-spacing: 3px; color: #8f8781;
              font-weight: 700; }}
.hero-title {{ font-size: 42px; font-weight: 800; color: #efeae6; }}
.url-pill {{ background-color: #2b2827; border: 1px solid #383331;
             border-radius: 18px; padding: 6px; }}
.url-pill entry, .url-pill text {{ background: none; border: none;
             box-shadow: none; font-size: 16px; color: #efeae6; }}
.download-btn {{ background-color: #BF5B3E; color: #ffffff;
                 border-radius: 13px; padding: 10px 22px;
                 font-weight: 700; font-size: 15px; }}
.download-btn:hover {{ background-color: #cf6647; }}
.download-btn:disabled {{ background-color: #6b4436; color: #beb4ae; }}
.seg {{ background-color: #2b2827; border: 1px solid #383331;
        border-radius: 13px; padding: 3px; }}
.seg togglebutton {{ background: none; border-radius: 10px;
        padding: 4px 16px; color: #97908b; font-weight: 600; }}
.seg togglebutton:checked {{ background-color: #3b3634; color: #efeae6; }}
.quality-drop > button {{ background-color: #2b2827; border: 1px solid
        #383331; border-radius: 13px; padding: 6px 12px; color: #efeae6; }}
.cards-strip {{ background-color: #232120; border-top: 1px solid #2e2a28; }}
.feature-card {{ background: none; border-radius: 0; padding: 22px 12px; }}
.feature-card:hover {{ background-color: alpha(#ffffff, 0.03); }}
.icon-circle {{ border: 1px solid #453f3c; border-radius: 9999px; }}
.icon-circle.bad {{ border-color: #8a3b33; }}
.icon-green {{ color: #55b45c; }}
.icon-orange {{ color: {ACCENT}; }}
.icon-red {{ color: #e04b3f; }}
.card-title {{ font-weight: 800; font-size: 17px; color: #efeae6; }}
.card-desc {{ color: #8f8781; font-size: 13px; }}
.dim {{ color: #8f8781; }}
.link-ish {{ color: #8f8781; font-size: 13px; }}
.link-ish:hover {{ color: #beb4ae; }}
.thumb {{ border-radius: 10px 0 0 10px; }}
.hover-btn {{ opacity: 0; transition: opacity 150ms ease; }}
row:hover .hover-btn {{ opacity: 1; }}
.star-btn {{ opacity: 0; padding: 2px; transition: opacity 150ms ease; }}
row:hover .star-btn {{ opacity: 1; }}
.star-btn.star-on {{ opacity: 1; color: {ACCENT}; }}
.coffee-emoji {{ font-size: 40px; }}
"""


# --------------------------------------------------------------- helpers
def load_json(path, default):
    try:
        with open(path) as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def save_json(path, data):
    os.makedirs(CONFIG_DIR, exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f, indent=1)


def human_size(n):
    if not n:
        return "?"
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"


def xdg_open(path):
    subprocess.Popen(["xdg-open", path])


NETWORK_HINTS = ("getaddrinfo", "name or service", "network is unreachable",
                 "connection reset", "connection refused", "timed out",
                 "temporary failure", "no route to host", "unable to resolve",
                 "failed to resolve", "errno 101", "network error")
PERMANENT_HINTS = ("video unavailable", "private video", "unsupported url",
                   "is not a valid url", "account associated", "removed by",
                   "copyright", "members-only", "age-restricted")


def diagnose(msg):
    """Turn a raw yt-dlp error into (kind, human_message, retryable)."""
    m = msg.lower()
    if any(h in m for h in NETWORK_HINTS):
        return ("network",
                "Access to the internet seems to have been lost. "
                "Check your connection.", True)
    if "sign in to confirm" in m or "not a bot" in m:
        return ("cookies",
                "YouTube wants proof you're not a robot. Cookies may not "
                "be set up. Click 'Cookies Setup' below to fix this.", True)
    if "403" in m or "429" in m or "forbidden" in m:
        return ("blocked",
                "YouTube temporarily blocked the request. Waiting a bit "
                "and trying again.", True)
    if "drm protected" in m or "requested format is not available" in m:
        return ("cookies",
                "YouTube restricted this session. This usually means "
                "browser cookies aren't set up. Click 'Cookies Setup' "
                "below to fix this.", False)
    if any(h in m for h in PERMANENT_HINTS):
        return ("permanent",
                "This video can't be downloaded. It may be private, "
                "removed, or the link isn't supported.", False)
    if "ffmpeg" in m and ("not found" in m or "not installed" in m):
        return ("ffmpeg",
                "ffmpeg is missing. Install it with: "
                "sudo dnf install ffmpeg-free", False)
    return ("unknown", None, True)


class Cancelled(Exception):
    pass


def test_browser_cookies(key):
    """True if the browser has readable YouTube/Google cookies."""
    try:
        jar = extract_cookies_from_browser(key)
        return any("youtube" in (c.domain or "") or
                   "google" in (c.domain or "") for c in jar)
    except Exception:
        return False


def find_working_browser():
    for _label, key, path in BROWSERS:
        if (os.path.isdir(os.path.expanduser(path))
                and test_browser_cookies(key)):
            return key
    return None


def parse_links(text):
    """One URL per line; ignores blanks, comments and duplicates."""
    urls, seen = [], set()
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("http") and line not in seen:
            seen.add(line)
            urls.append(line)
    return urls


class History:
    """Persistent record of completed downloads."""

    def __init__(self):
        self.items = load_json(HISTORY_FILE, [])

    def add(self, record):
        self.items.insert(0, record)
        save_json(HISTORY_FILE, self.items)

    def remove(self, record):
        if record in self.items:
            self.items.remove(record)
            save_json(HISTORY_FILE, self.items)


# ------------------------------------------------------- download engine
class DownloadManager:
    """Runs jobs on a bounded pool with auto-retry and self-healing."""

    def __init__(self, max_workers=MAX_CONCURRENT):
        self.pool = ThreadPoolExecutor(max_workers=max_workers,
                                       thread_name_prefix="dl")

    def submit(self, job, ui):
        """job: dict; ui: object with queued/progress/status/done/failed
        callbacks (already thread-safe)."""
        ui.status("Waiting for a download slot…")
        return self.pool.submit(self._run, job, ui)

    def _run(self, job, ui):
        attempt = 0
        healed = False
        while True:
            if ui.is_cancelled():
                ui.failed("Cancelled", cancelled=True)
                return
            try:
                records = []
                with yt_dlp.YoutubeDL(
                        self._build_opts(job, ui, records)) as ydl:
                    ydl.download([job["url"]])
                ui.done(records)
                return
            except Cancelled:
                ui.failed("Cancelled", cancelled=True)
                return
            except Exception as e:
                kind, human, retryable = diagnose(str(e))
                # self-heal: cookie problems with no browser attached;
                # find a working browser and retry with its cookies
                if (kind == "cookies" and not job.get("browser")
                        and not healed):
                    healed = True
                    ui.status("Cookies weren't set up. Looking for a "
                              "browser to borrow them from…")
                    browser = find_working_browser()
                    if browser:
                        job["browser"] = browser
                        label = next(l for l, k, _p in BROWSERS
                                     if k == browser)
                        ui.status(f"Connected {label} cookies "
                                  "automatically. Retrying…")
                        continue
                    ui.failed("YouTube wants cookies, but no browser with "
                              "a YouTube session was found. Open a browser, "
                              "visit youtube.com once, then use "
                              "'Cookies Setup'.")
                    return
                if retryable and attempt < len(RETRY_DELAYS):
                    delay = RETRY_DELAYS[attempt]
                    attempt += 1
                    ui.status(
                        f"{human or 'Download hiccup.'} "
                        f"Retrying in {delay}s "
                        f"(attempt {attempt}/{len(RETRY_DELAYS)})…")
                    for _ in range(delay * 2):
                        if ui.is_cancelled():
                            ui.failed("Cancelled", cancelled=True)
                            return
                        time.sleep(0.5)
                    continue
                ui.failed(human or f"Download failed: {str(e)[:160]}")
                return

    @staticmethod
    def _build_opts(job, ui, records):
        last = [0.0]

        def hook(d):
            if ui.is_cancelled():
                raise Cancelled()
            ui.set_title((d.get("info_dict") or {}).get("title"))
            if d["status"] == "downloading":
                now = time.monotonic()
                if now - last[0] < 0.15:       # throttle UI updates
                    return
                last[0] = now
                total = d.get("total_bytes") or d.get("total_bytes_estimate")
                done = d.get("downloaded_bytes", 0)
                frac = done / total if total else 0.0
                speed = d.get("speed")
                eta = d.get("eta")
                status = f"{human_size(done)} / {human_size(total)}"
                if speed:
                    status += f"  ·  {human_size(speed)}/s"
                if eta:
                    status += f"  ·  {int(eta)}s left"
                ui.progress(frac, status)
            elif d["status"] == "finished":
                ui.progress(1.0, "Processing with ffmpeg…")

        def post_hook(filepath):
            try:
                size = os.path.getsize(filepath)
            except OSError:
                size = 0
            records.append({
                "title": os.path.splitext(os.path.basename(filepath))[0],
                "url": job["url"],
                "path": filepath,
                "size": size,
                "date": time.time(),
            })

        opts = {
            "outtmpl": os.path.join(job["outdir"],
                                    "%(title)s [%(id)s].%(ext)s"),
            "progress_hooks": [hook],
            "post_hooks": [post_hook],
            "noplaylist": not job.get("playlist"),
            "quiet": True,
            "noprogress": True,
            "postprocessors": [],
            "extractor_args": EXTRACTOR_ARGS,
            "socket_timeout": 30,
        }
        if job.get("browser"):
            opts["cookiesfrombrowser"] = (job["browser"],)

        fmt = job["fmt"]                        # "mp4" | "mp3" | "wav"
        if fmt == "mp4":
            opts["format"] = job["quality_fmt"]
            opts["merge_output_format"] = "mp4"
        else:
            opts["format"] = "ba/b"
            opts["postprocessors"].append({
                "key": "FFmpegExtractAudio",
                "preferredcodec": fmt,
                "preferredquality": "0",
            })

        if job.get("subs"):
            opts["writesubtitles"] = True
            opts["subtitleslangs"] = ["en.*"]
            opts["postprocessors"].append({"key": "FFmpegEmbedSubtitle"})
        if job.get("thumb"):
            opts["writethumbnail"] = True
            opts["postprocessors"].append({"key": "EmbedThumbnail"})
        if job.get("meta", True):
            opts["postprocessors"].append({"key": "FFmpegMetadata"})
        return opts


# ------------------------------------------------------------ UI widgets
class FeatureCard(Gtk.Button):
    def __init__(self, icon, color_class, title, desc, callback):
        super().__init__(css_classes=["feature-card", "flat"],
                         hexpand=True)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10,
                      halign=Gtk.Align.CENTER)
        self.circle = Gtk.Box(css_classes=["icon-circle"],
                              halign=Gtk.Align.CENTER)
        if len(icon) <= 2:                      # emoji "icon"
            self.icon = Gtk.Label(label=icon, css_classes=[color_class],
                                  margin_top=13, margin_bottom=13,
                                  margin_start=13, margin_end=13)
            self.icon.set_markup(f'<span size="16000">{icon}</span>')
            self.icon.set_from_icon_name = lambda *_: None
        else:
            self.icon = Gtk.Image(icon_name=icon, pixel_size=22,
                                  css_classes=[color_class],
                                  margin_top=15, margin_bottom=15,
                                  margin_start=15, margin_end=15)
        self.circle.append(self.icon)
        self.title = Gtk.Label(label=title, css_classes=["card-title"])
        self.desc = Gtk.Label(label=desc, css_classes=["card-desc"],
                              wrap=True, justify=Gtk.Justification.CENTER,
                              max_width_chars=26)
        box.append(self.circle)
        box.append(self.title)
        box.append(self.desc)
        self.set_child(box)
        self.connect("clicked", lambda *_: callback())

    def set_state(self, icon, color_class, desc=None):
        self.icon.set_from_icon_name(icon)
        self.icon.set_css_classes([color_class])
        self.circle.set_css_classes(
            ["icon-circle"] + (["bad"] if color_class == "icon-red" else []))
        if desc is not None:
            self.desc.set_label(desc)


class ActiveRow(Gtk.ListBoxRow):
    """An in-progress download entry."""

    def __init__(self, title):
        super().__init__(activatable=False, selectable=False)
        self.cancelled = False

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6,
                      margin_top=10, margin_bottom=10,
                      margin_start=12, margin_end=12)
        top = Gtk.Box(spacing=8)
        self.title_label = Gtk.Label(label=title, xalign=0, hexpand=True,
                                     ellipsize=3, css_classes=["heading"])
        self.cancel_btn = Gtk.Button(icon_name="process-stop-symbolic",
                                     tooltip_text="Cancel",
                                     valign=Gtk.Align.CENTER,
                                     css_classes=["flat", "circular"])
        self.cancel_btn.connect("clicked", self._cancel)
        top.append(self.title_label)
        top.append(self.cancel_btn)
        self.bar = Gtk.ProgressBar(show_text=True, text="Queued")
        self.status = Gtk.Label(label="", xalign=0, wrap=True,
                                css_classes=["dim-label", "caption"])
        box.append(top)
        box.append(self.bar)
        box.append(self.status)
        self.set_child(box)

    def _cancel(self, _b):
        self.cancelled = True
        self.cancel_btn.set_sensitive(False)
        self.status.set_label("Cancelling…")


class HistoryRow(Adw.ActionRow):
    """A completed download; click to play, hover for folder button."""

    def __init__(self, record, on_remove):
        super().__init__(activatable=True)
        self.record = record
        self.set_title(GLib.markup_escape_text(record["title"]))
        when = time.strftime("%b %d, %H:%M",
                             time.localtime(record.get("date", 0)))
        self.set_subtitle(f"{when}  ·  {human_size(record.get('size'))}")
        self.add_prefix(Gtk.Image(icon_name="video-x-generic-symbolic"))
        self.connect("activated", lambda *_: xdg_open(record["path"]))

        folder = Gtk.Button(icon_name="folder-open-symbolic",
                            tooltip_text="Open file location",
                            valign=Gtk.Align.CENTER,
                            css_classes=["flat", "hover-btn"])
        folder.connect("clicked", self._open_folder)
        remove = Gtk.Button(icon_name="user-trash-symbolic",
                            tooltip_text="Remove from history (keeps file)",
                            valign=Gtk.Align.CENTER,
                            css_classes=["flat", "hover-btn"])
        remove.connect("clicked", lambda *_: on_remove(self))
        self.add_suffix(folder)
        self.add_suffix(remove)

    def _open_folder(self, _b):
        xdg_open(os.path.dirname(self.record["path"]))


class RowUI:
    """Thread-safe bridge between a worker and its ActiveRow + window."""

    def __init__(self, win, row, batch_id, title):
        self.win = win
        self.row = row
        self.batch_id = batch_id
        self.title = title

    def is_cancelled(self):
        return self.row.cancelled

    def set_title(self, title):
        """Swap the row label from the URL to the real video title."""
        if not title or title == self.title:
            return
        self.title = title
        GLib.idle_add(self.row.title_label.set_label, title)

    def status(self, text):
        GLib.idle_add(self.row.status.set_label, text)

    def progress(self, frac, status):
        def apply():
            self.row.bar.set_fraction(frac)
            self.row.bar.set_text(f"{frac * 100:.0f}%")
            self.row.status.set_label(status)
        GLib.idle_add(apply)

    def done(self, records):
        def apply():
            self.row.bar.set_fraction(1.0)
            self.row.bar.set_text("Done")
            self.row.bar.add_css_class("success")
            self.row.cancel_btn.set_sensitive(False)
            self.row.status.set_label("Saved")
            self.win.job_finished(self, True, records)
        GLib.idle_add(apply)

    def failed(self, message, cancelled=False):
        def apply():
            self.row.bar.set_text("Cancelled" if cancelled else "Failed")
            self.row.bar.add_css_class("error")
            self.row.cancel_btn.set_sensitive(False)
            self.row.status.set_label(message)
            if not cancelled:
                self.win.job_finished(self, False, [], message)
        GLib.idle_add(apply)


# -------------------------------------------------------------- window
class MainWindow(Adw.ApplicationWindow):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.set_title(f"{APP_NAME} Youtube Downloader")
        self.set_default_size(1020, 860)

        self.settings = load_json(SETTINGS_FILE, {})
        self.history = History()
        self.manager = DownloadManager()
        self.batches = {}
        self._batch_seq = 0
        self._active_count = 0
        self._current_info = None

        self.download_dir = (
            GLib.get_user_special_dir(GLib.UserDirectory.DIRECTORY_VIDEOS)
            or os.path.expanduser("~/Videos"))
        os.makedirs(self.download_dir, exist_ok=True)

        css = Gtk.CssProvider()
        css.load_from_string(CSS)
        Gtk.StyleContext.add_provider_for_display(
            Gdk.Display.get_default(), css,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

        self.toasts = Adw.ToastOverlay()
        self.nav = Adw.NavigationView()
        self.nav.add(self.build_home_page())
        self.downloads_page = self.build_downloads_page()
        self.toasts.set_child(self.nav)
        self.set_content(self.toasts)

        threading.Thread(target=self._check_cookies_startup,
                         daemon=True).start()

    # --------------------------------------------------------- home page
    def build_home_page(self):
        view = Adw.ToolbarView()
        header = Adw.HeaderBar()
        header.set_title_widget(
            Gtk.Label(label="STUBE  DOWNLOADER", css_classes=["app-title"]))
        view.add_top_bar(header)

        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)

        # ---- hero ----
        hero = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=26,
                       valign=Gtk.Align.CENTER, vexpand=True)
        clamp = Adw.Clamp(maximum_size=760, margin_start=24, margin_end=24)

        title = Gtk.Label(use_markup=True, css_classes=["hero-title"],
                          label=('Fetch your <span foreground="'
                                 f'{ACCENT}">media.</span>'))
        hero.append(title)

        pill = Gtk.Box(spacing=8, css_classes=["url-pill"])
        self.url_entry = Gtk.Entry(
            hexpand=True,
            placeholder_text="Paste video URL from YouTube, Vimeo, or Twitter…")
        self.url_entry.connect("activate", self.on_download)
        dl_content = Adw.ButtonContent(label="Download",
                                       icon_name="go-down-symbolic")
        self.dl_btn = Gtk.Button(child=dl_content,
                                 css_classes=["download-btn"])
        self.dl_btn.connect("clicked", self.on_download)
        pill.append(self.url_entry)
        pill.append(self.dl_btn)
        hero.append(pill)

        # ---- format + quality row ----
        controls = Gtk.Box(spacing=14, halign=Gtk.Align.CENTER)
        seg = Gtk.Box(css_classes=["seg"])
        self.fmt_buttons = {}
        group = None
        for fmt in ("MP4", "MP3", "WAV"):
            b = Gtk.ToggleButton(label=fmt, group=group,
                                 css_classes=["flat"])
            group = group or b
            b.connect("toggled", self.on_format_toggled)
            self.fmt_buttons[fmt.lower()] = b
            seg.append(b)
        controls.append(seg)

        self.quality_drop = Gtk.DropDown.new_from_strings(
            [q[0] for q in VIDEO_QUALITIES])
        self.quality_drop.add_css_class("quality-drop")
        self.quality_drop.set_selected(
            min(self.settings.get("default_quality", 0),
                len(VIDEO_QUALITIES) - 1))
        self._quality_stars = {}
        list_factory = Gtk.SignalListItemFactory()
        list_factory.connect("setup", self._quality_item_setup)
        list_factory.connect("bind", self._quality_item_bind)
        list_factory.connect("unbind", self._quality_item_unbind)
        self.quality_drop.set_list_factory(list_factory)
        controls.append(self.quality_drop)
        self.fmt_buttons["mp4"].set_active(True)
        hero.append(controls)

        # ---- bulk + more options ----
        extra = Gtk.Box(spacing=4, halign=Gtk.Align.CENTER,
                        orientation=Gtk.Orientation.VERTICAL)
        bulk = Gtk.Button(label="Bulk Download",
                          css_classes=["flat", "link-ish"])
        bulk.connect("clicked", self.on_bulk_import)
        extra.append(bulk)

        more = Gtk.Expander(css_classes=["dim"], halign=Gtk.Align.CENTER)
        more.set_label("More options")
        mo = Adw.PreferencesGroup(margin_top=8)
        self.default_quality_row = Adw.ComboRow(
            title="Default quality",
            subtitle="Selected automatically every time the app opens")
        dq_model = Gtk.StringList()
        for label, _ in VIDEO_QUALITIES:
            dq_model.append(label)
        self.default_quality_row.set_model(dq_model)
        self.default_quality_row.set_selected(
            min(self.settings.get("default_quality", 0),
                len(VIDEO_QUALITIES) - 1))
        def on_default_quality(row, _pspec):
            self.settings["default_quality"] = row.get_selected()
            save_json(SETTINGS_FILE, self.settings)
            self.quality_drop.set_selected(row.get_selected())
        self.default_quality_row.connect("notify::selected",
                                         on_default_quality)
        mo.add(self.default_quality_row)
        self.playlist_row = Adw.SwitchRow(title="Download full playlist")
        self.subs_row = Adw.SwitchRow(title="Embed subtitles (English)")
        self.thumb_row = Adw.SwitchRow(title="Embed thumbnail")
        self.folder_row = Adw.ActionRow(title="Save to",
                                        subtitle=self.download_dir,
                                        activatable=True)
        self.folder_row.add_suffix(
            Gtk.Image(icon_name="folder-open-symbolic"))
        self.folder_row.connect("activated", self.on_choose_folder)
        for r in (self.playlist_row, self.subs_row, self.thumb_row,
                  self.folder_row):
            mo.add(r)
        more.set_child(mo)
        extra.append(more)
        hero.append(extra)

        clamp.set_child(hero)
        outer.append(clamp)

        # ---- feature cards strip ----
        strip = Gtk.Box(css_classes=["cards-strip"])
        self.cookie_card = FeatureCard(
            "content-loading-symbolic", "icon-green", "Cookies Setup",
            "Import browser cookies to download private or "
            "subscriber-only content.", self.on_cookies_setup)
        self.downloads_card = FeatureCard(
            "go-down-symbolic", "icon-orange", "My Downloads",
            "Browse, manage, and re-open every file you have fetched.",
            self.on_my_downloads)
        self.coffee_card = FeatureCard(
            "☕", "icon-orange", "Buy Coffee",
            "Support development and keep the downloads flowing.",
            self.on_coffee)
        strip.append(self.cookie_card)
        strip.append(Gtk.Separator(orientation=Gtk.Orientation.VERTICAL,
                                   margin_top=24, margin_bottom=24))
        strip.append(self.downloads_card)
        self._coffee_sep = Gtk.Separator(
            orientation=Gtk.Orientation.VERTICAL,
            margin_top=24, margin_bottom=24)
        strip.append(self._coffee_sep)
        strip.append(self.coffee_card)
        self._strip = strip
        if self.settings.get("coffee_hidden"):
            strip.remove(self._coffee_sep)
            strip.remove(self.coffee_card)
        outer.append(strip)

        view.set_content(outer)
        return Adw.NavigationPage(child=view, title="STube", tag="home")

    # ---------------------------------------------------- downloads page
    def build_downloads_page(self):
        view = Adw.ToolbarView()
        view.add_top_bar(Adw.HeaderBar())

        scroll = Gtk.ScrolledWindow(vexpand=True)
        page = Adw.Clamp(maximum_size=760, margin_top=18, margin_bottom=18,
                         margin_start=14, margin_end=14)
        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=18)

        active_group = Adw.PreferencesGroup(title="In progress")
        self.queue_list = Gtk.ListBox(css_classes=["boxed-list"],
                                      selection_mode=Gtk.SelectionMode.NONE)
        self.queue_list.set_placeholder(Gtk.Label(
            label="Nothing downloading right now",
            css_classes=["dim-label"], margin_top=12, margin_bottom=12))
        active_group.add(self.queue_list)
        content.append(active_group)

        hist_group = Adw.PreferencesGroup(
            title="History",
            description="Click an item to play it")
        self.hist_list = Gtk.ListBox(css_classes=["boxed-list"],
                                     selection_mode=Gtk.SelectionMode.NONE)
        self.hist_list.set_placeholder(Gtk.Label(
            label="No downloads yet",
            css_classes=["dim-label"], margin_top=12, margin_bottom=12))
        for record in self.history.items:
            self.hist_list.append(HistoryRow(record, self.on_remove_history))
        hist_group.add(self.hist_list)
        content.append(hist_group)

        page.set_child(content)
        scroll.set_child(page)
        view.set_content(scroll)
        return Adw.NavigationPage(child=view, title="My Downloads",
                                  tag="downloads")

    # ------------------------------------------- quality dropdown stars
    def _quality_item_setup(self, _f, item):
        box = Gtk.Box(spacing=8)
        label = Gtk.Label(xalign=0, hexpand=True)
        star = Gtk.Button(css_classes=["flat", "circular", "star-btn"],
                          valign=Gtk.Align.CENTER,
                          tooltip_text="Always use this quality by default")
        box.append(label)
        box.append(star)
        item.set_child(box)

    def _quality_item_bind(self, _f, item):
        box = item.get_child()
        label = box.get_first_child()
        star = label.get_next_sibling()
        pos = item.get_position()
        label.set_label(VIDEO_QUALITIES[pos][0])
        self._quality_stars[pos] = star
        self._refresh_star(star, pos)
        star._handler = star.connect("clicked",
                                     self._on_star_clicked, pos)

    def _quality_item_unbind(self, _f, item):
        star = item.get_child().get_first_child().get_next_sibling()
        if getattr(star, "_handler", None):
            star.disconnect(star._handler)
            star._handler = None
        self._quality_stars = {p: s for p, s in
                               self._quality_stars.items() if s is not star}

    def _refresh_star(self, star, pos):
        is_default = self.settings.get("default_quality", 0) == pos
        star.set_icon_name("starred-symbolic" if is_default
                           else "non-starred-symbolic")
        if is_default:
            star.add_css_class("star-on")
        else:
            star.remove_css_class("star-on")

    def _on_star_clicked(self, _btn, pos):
        self.settings["default_quality"] = pos
        save_json(SETTINGS_FILE, self.settings)
        for p, s in self._quality_stars.items():
            self._refresh_star(s, p)
        if hasattr(self, "default_quality_row"):
            self.default_quality_row.set_selected(pos)
        self.quality_drop.set_selected(pos)
        self.toast(f"{VIDEO_QUALITIES[pos][0]} is now your default quality")

    # ----------------------------------------------------------- actions
    def on_format_toggled(self, _b):
        if hasattr(self, "quality_drop"):
            self.quality_drop.set_sensitive(
                self.fmt_buttons["mp4"].get_active())

    def selected_format(self):
        for name, b in self.fmt_buttons.items():
            if b.get_active():
                return name
        return "mp4"

    def on_my_downloads(self):
        if self.nav.get_visible_page() is not self.downloads_page:
            self.nav.push(self.downloads_page)

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

    def toast(self, text):
        self.toasts.add_toast(Adw.Toast(title=text, timeout=4))

    def notify_desktop(self, title, body):
        n = Gio.Notification.new(title)
        n.set_body(body)
        n.set_icon(Gio.ThemedIcon.new("stube"))
        self.get_application().send_notification(None, n)

    # ------------------------------------------------------------ coffee
    def on_coffee(self):
        dialog = Adw.Dialog(title="Buy Coffee", content_width=460)
        view = Adw.ToolbarView()
        view.add_top_bar(Adw.HeaderBar())

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16,
                      margin_top=4, margin_bottom=24,
                      margin_start=28, margin_end=28)
        circle = Gtk.Box(css_classes=["icon-circle"],
                         halign=Gtk.Align.CENTER)
        emoji = Gtk.Label(label="☕", css_classes=["coffee-emoji"],
                          margin_top=14, margin_bottom=14,
                          margin_start=18, margin_end=18)
        circle.append(emoji)
        box.append(circle)

        msg = Gtk.Label(
            label="Hello! STube is open source. If it helped you, "
                  "consider buying me a coffee :)",
            wrap=True, justify=Gtk.Justification.CENTER,
            halign=Gtk.Align.CENTER, css_classes=["dim"])
        box.append(msg)

        buy = Gtk.Button(label="Buy Coffee",
                         css_classes=["download-btn"],
                         halign=Gtk.Align.CENTER)
        never = Gtk.Button(label="Never show again",
                           css_classes=["flat", "link-ish"],
                           halign=Gtk.Align.CENTER)
        box.append(buy)
        box.append(never)

        def on_buy(_b):
            Gtk.UriLauncher(uri=COFFEE_URL).launch(self, None, None)
            dialog.close()

        def on_never(_b):
            self.settings["coffee_hidden"] = True
            save_json(SETTINGS_FILE, self.settings)
            self._strip.remove(self._coffee_sep)
            self._strip.remove(self.coffee_card)
            dialog.close()
            self.toast("Okay, the coffee button is gone for good")

        buy.connect("clicked", on_buy)
        never.connect("clicked", on_never)
        view.set_content(box)
        dialog.set_child(view)
        dialog.present(self)

    # ----------------------------------------------------------- cookies
    def _check_cookies_startup(self):
        preferred = self.settings.get("browser")
        order = ([b for b in BROWSERS if b[1] == preferred]
                 + [b for b in BROWSERS if b[1] != preferred])
        for label, key, path in order:
            if not os.path.isdir(os.path.expanduser(path)):
                continue
            if self._test_cookies(key):
                self.settings["browser"] = key
                save_json(SETTINGS_FILE, self.settings)
                GLib.idle_add(self.cookie_card.set_state,
                              "object-select-symbolic", "icon-green",
                              f"Using {label} cookies. You're all set "
                              "for YouTube.")
                return
        GLib.idle_add(self.cookie_card.set_state,
                      "window-close-symbolic", "icon-red",
                      "Not set up. Click here to connect a browser.")
        self.settings.pop("browser", None)

    _test_cookies = staticmethod(test_browser_cookies)

    def on_cookies_setup(self):
        dialog = Adw.Dialog(title="Cookies Setup 🍪",
                            content_width=560)
        view = Adw.ToolbarView()
        view.add_top_bar(Adw.HeaderBar())

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16,
                      margin_top=8, margin_bottom=24,
                      margin_start=24, margin_end=24)
        intro = Gtk.Label(
            label="STube borrows YouTube cookies from a browser on this "
                  "computer so YouTube treats downloads like normal "
                  "viewing. Open the browser you use, visit youtube.com "
                  "once (signed in works best), then pick it here and "
                  "press Test & Save.",
            wrap=True, xalign=0, css_classes=["dim"])
        box.append(intro)

        listbox = Gtk.ListBox(css_classes=["boxed-list"],
                              selection_mode=Gtk.SelectionMode.NONE)
        current = self.settings.get("browser")
        first_check = None
        for label, key, path in BROWSERS:
            installed = os.path.isdir(os.path.expanduser(path))
            row = Adw.ActionRow(
                title=label,
                subtitle="Detected" if installed else "Not installed")
            check = Gtk.CheckButton(valign=Gtk.Align.CENTER,
                                    group=first_check)
            first_check = first_check or check
            check.browser_key = key
            check.set_sensitive(installed)
            if key == current or (current is None and installed
                                  and not hasattr(listbox, "_preset")):
                check.set_active(True)
                listbox._preset = True
            row.add_prefix(check)
            row.set_activatable_widget(check)
            listbox.append(row)
        box.append(listbox)

        test_btn = Gtk.Button(label="Test & Save",
                              css_classes=["download-btn"],
                              halign=Gtk.Align.CENTER, margin_top=4)
        box.append(test_btn)

        view.set_content(box)
        dialog.set_child(view)

        def on_test(_b):
            key = None
            child = listbox.get_first_child()
            while child is not None:
                if isinstance(child, Adw.ActionRow):
                    w = child.get_activatable_widget()
                    if isinstance(w, Gtk.CheckButton) and w.get_active():
                        key = w.browser_key
                        break
                child = child.get_next_sibling()
            if key is None:
                self.toast("Pick a browser first")
                return
            test_btn.set_sensitive(False)
            test_btn.set_label("Testing…")
            def worker():
                ok = self._test_cookies(key)
                label = next(l for l, k, _p in BROWSERS if k == key)
                def apply():
                    test_btn.set_sensitive(True)
                    test_btn.set_label("Test & Save")
                    if ok:
                        self.settings["browser"] = key
                        save_json(SETTINGS_FILE, self.settings)
                        self.cookie_card.set_state(
                            "object-select-symbolic", "icon-green",
                            f"Using {label} cookies. You're all set "
                            "for YouTube.")
                        self.toast(f"{label} cookies work. Saved!")
                        dialog.close()
                    else:
                        self.cookie_card.set_state(
                            "window-close-symbolic", "icon-red",
                            "Not set up. Click here to connect a browser.")
                        self.toast(
                            f"Couldn't read YouTube cookies from {label}. "
                            "Open it, visit youtube.com, then try again.")
                GLib.idle_add(apply)
            threading.Thread(target=worker, daemon=True).start()

        test_btn.connect("clicked", on_test)
        dialog.present(self)

    # --------------------------------------------------------- downloads
    def on_download(self, *_a):
        url = self.url_entry.get_text().strip()
        if not url:
            self.toast("Paste a link first")
            return
        self.enqueue([url], batch=False)
        self.url_entry.set_text("")

    def on_bulk_import(self, *_a):
        dialog = Adw.Dialog(title="Bulk Download", content_width=560)
        view = Adw.ToolbarView()
        view.add_top_bar(Adw.HeaderBar())

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14,
                      margin_top=8, margin_bottom=24,
                      margin_start=24, margin_end=24)
        intro = Gtk.Label(
            label="Save your links in a plain text file (.txt), one video "
                  "link per line, then pick the file here.",
            wrap=True, xalign=0, css_classes=["dim"])
        box.append(intro)

        points = Gtk.ListBox(css_classes=["boxed-list"],
                             selection_mode=Gtk.SelectionMode.NONE)
        for icon, title, subtitle in (
                ("text-x-generic-symbolic", "One link per line",
                 "Blank lines and duplicate links are skipped"),
                ("go-down-symbolic",
                 f"{MAX_CONCURRENT} downloads at a time",
                 "The rest queue up and start automatically"),
                ("emblem-ok-symbolic", "Uses your current settings",
                 "The format and quality on the main screen apply to "
                 "every link"),
                ("preferences-system-notifications-symbolic",
                 "One tidy notification",
                 "Failed videos retry on their own; you get a single "
                 "summary at the end")):
            row = Adw.ActionRow(title=title, subtitle=subtitle,
                                activatable=False)
            img = Gtk.Image(icon_name=icon, css_classes=["icon-orange"])
            row.add_prefix(img)
            points.append(row)
        box.append(points)

        choose = Gtk.Button(label="Choose File…",
                            css_classes=["download-btn"],
                            halign=Gtk.Align.CENTER, margin_top=6)
        def on_choose(_b):
            dialog.close()
            self._pick_bulk_file()
        choose.connect("clicked", on_choose)
        box.append(choose)

        view.set_content(box)
        dialog.set_child(view)
        dialog.present(self)

    def _pick_bulk_file(self):
        f = Gtk.FileFilter()
        f.set_name("Text files")
        f.add_pattern("*.txt")
        filters = Gio.ListStore.new(Gtk.FileFilter)
        filters.append(f)
        dialog = Gtk.FileDialog(title="Pick a .txt file (one link per line)",
                                filters=filters)

        def done(dlg, result):
            try:
                gfile = dlg.open_finish(result)
            except GLib.Error:
                return
            try:
                with open(gfile.get_path()) as fh:
                    lines = fh.read().splitlines()
            except OSError as e:
                self.toast(f"Couldn't read file: {e}")
                return
            urls = parse_links("\n".join(lines))
            if not urls:
                self.toast("No links found in that file")
                return
            self.enqueue(urls, batch=True)
            self.toast(f"Queued {len(urls)} links, downloading "
                       f"{MAX_CONCURRENT} at a time")
        dialog.open(self, None, done)

    def enqueue(self, urls, batch):
        batch_id = None
        if batch and len(urls) > 1:
            self._batch_seq += 1
            batch_id = self._batch_seq
            self.batches[batch_id] = {"total": len(urls), "ok": 0,
                                      "fail": 0, "first_error": None}
        fmt = self.selected_format()
        quality_fmt = VIDEO_QUALITIES[
            self.quality_drop.get_selected()][1]
        for url in urls:
            title = url
            if (not batch and self._current_info
                    and self._current_info.get("url") == url):
                title = self._current_info["title"]
            row = ActiveRow(title)
            self.queue_list.prepend(row)
            job = {
                "url": url,
                "fmt": fmt,
                "quality_fmt": quality_fmt,
                "playlist": self.playlist_row.get_active(),
                "subs": self.subs_row.get_active(),
                "thumb": self.thumb_row.get_active(),
                "meta": True,
                "outdir": self.download_dir,
                "browser": self.settings.get("browser"),
            }
            ui = RowUI(self, row, batch_id, title)
            self.manager.submit(job, ui)
            self._active_count += 1
        self._update_downloads_badge()
        self.on_my_downloads()

    def _update_downloads_badge(self):
        if self._active_count > 0:
            self.downloads_card.desc.set_label(
                f"{self._active_count} download"
                f"{'s' if self._active_count != 1 else ''} in progress…")
        else:
            self.downloads_card.desc.set_label(
                "Browse, manage, and re-open every file you have fetched.")

    def job_finished(self, ui, ok, records, error=None):
        """Called on main thread when a job ends (not for cancels)."""
        self._active_count = max(0, self._active_count - 1)
        self._update_downloads_badge()
        for record in records:
            self.history.add(record)
            self.hist_list.prepend(
                HistoryRow(record, self.on_remove_history))

        if ui.batch_id is not None:
            b = self.batches.get(ui.batch_id)
            if b is None:
                return
            if ok:
                b["ok"] += 1
            else:
                b["fail"] += 1
                b["first_error"] = b["first_error"] or error
            if b["ok"] + b["fail"] == b["total"]:
                del self.batches[ui.batch_id]
                body = f"{b['ok']} saved to {self.download_dir}"
                if b["fail"]:
                    body += (f", {b['fail']} failed: "
                             f"{b['first_error'] or 'see the app'}")
                self.notify_desktop("Batch download finished", body)
        else:
            title = records[0]["title"] if records else ui.title
            if ok:
                self.notify_desktop("Download complete", title)
            else:
                self.notify_desktop("Download failed",
                                    error or "See the app for details")

    def on_remove_history(self, row):
        self.history.remove(row.record)
        self.hist_list.remove(row)


class App(Adw.Application):
    def __init__(self):
        super().__init__(application_id=APP_ID,
                         flags=Gio.ApplicationFlags.DEFAULT_FLAGS)

    def do_activate(self):
        Adw.StyleManager.get_default().set_color_scheme(
            Adw.ColorScheme.FORCE_DARK)
        win = self.get_active_window() or MainWindow(application=self)
        win.present()


if __name__ == "__main__":
    raise SystemExit(App().run(None))
