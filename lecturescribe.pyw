"""LectureScribe — local lecture transcription GUI for Windows."""
from __future__ import annotations

import json
import os
import re
import shutil
import tempfile
import threading
import tkinter as tk
from datetime import datetime
from pathlib import Path
from queue import Empty, Queue
from tkinter import filedialog, messagebox, ttk

import yt_dlp
from faster_whisper import WhisperModel
from faster_whisper.utils import available_models
from yt_dlp.utils import DownloadError

APP = "LectureScribe"
CONFIG_DIR = Path(os.getenv("APPDATA", str(Path.home()))) / APP
CONFIG_FILE = CONFIG_DIR / "settings.json"
DEFAULT_DIR = Path.home() / "Documents" / APP
EXTS = {".mp4", ".mkv", ".webm", ".mov", ".mp3", ".m4a", ".wav", ".flac", ".aac"}
MODELS = list(dict.fromkeys([m for m in ["turbo", "large-v3", "medium", "small", "base", "tiny"] if m in available_models()] + available_models()))
BROWSER_MAP = {"Chrome": "chrome", "Edge": "edge", "Firefox": "firefox", "Brave": "brave", "Opera": "opera", "Vivaldi": "vivaldi", "Chromium": "chromium", "Whale": "whale"}
AUTH_WORDS = ("registered users", "login required", "login to", "sign in", "authentication required", "cookies-from-browser", "cookies from browser", "http error 401", "http error 403", "unauthorized", "forbidden")

I18N = {
 "it": {
  "tagline":"Trascrizione locale di lezioni e registrazioni", "source":"Link Webex, URL HLS o file audio/video", "browse":"Sfoglia", "title":"Nome della lezione", "transcripts":"Cartella trascrizioni", "videos":"Cartella video conservati", "choose":"Scegli", "keep":"Conserva il video scaricato", "safety":"I file locali originali non vengono mai eliminati automaticamente.", "model":"Modello Whisper", "speech":"Lingua del parlato", "automatic":"Rilevamento automatico", "italian":"Italiano", "english":"Inglese", "theme":"Tema", "dark":"Scuro", "light":"Chiaro", "lang":"Interfaccia", "start":"Avvia trascrizione", "stop":"Interrompi", "open":"Apri trascrizioni", "progress":"Avanzamento", "ready":"Pronto", "preparing":"Preparazione...", "downloading":"Download in corso...", "loading":"Caricamento del modello (primo avvio: download)...", "transcribing":"Trascrizione", "finished":"Trascrizione completata", "stopped":"Operazione interrotta. Le eventuali trascrizioni parziali sono state conservate.", "error":"Errore", "missing":"Inserisci un URL o seleziona un file.", "notfound":"File non trovato.", "auth_title":"Autenticazione Webex", "auth_explain":"La registrazione richiede l'accesso. Seleziona il browser in cui sei già autenticato, oppure usa un file cookie Netscape.", "auth_browser":"Browser", "auth_continue":"Continua", "cancel":"Annulla", "cookies":"File cookie Netscape (anche Samsung Browser)", "samsung":"Samsung Browser (file cookie)", "no_browsers":"Nessun browser supportato rilevato: puoi usare un file cookie.", "auth_failed":"Accesso non riuscito. Controlla il login nel browser, il profilo o il file cookie.", "download_failed":"Download fallito. Controlla il link e la connessione. Per un URL HLS scaduto, recuperane uno nuovo.", "processing_failed":"Errore nell'elaborazione. Consulta il log diagnostico locale (senza URL o cookie).", "close_running":"L'elaborazione è in corso. Vuoi interromperla e chiudere al termine dell'interruzione?", "model_tip":"Turbo: equilibrio consigliato. Large-v3: più lento. I modelli .en sono solo per inglese.", "output_saved":"File salvati in:", "logs":"Apri cartella log", "model_error":"Modello non disponibile oppure download fallito.", "select_folder":"Seleziona cartella", "permission":"Impossibile scrivere nella cartella di destinazione.", "browser_tip":"La lettura dei cookie può fallire per le protezioni del browser. Non condividere mai file cookie.", "video_copy":"Conservazione del video...", "bad_source":"Sono supportati file locali e URL http(s).", "no_media":"Il download non ha prodotto un file multimediale.", "privacy":"Trascrizione locale · nessun audio inviato a servizi AI", "duplicate":"Nome già in uso: scelto un nome alternativo.", "model_warn":"Questo modello .en riconosce soltanto l'inglese. Continuare?", "yes":"Sì", "no":"No"
 },
 "en": {
  "tagline":"Local transcription of lectures and recordings", "source":"Webex link, HLS URL or local media", "browse":"Browse", "title":"Lecture name", "transcripts":"Transcripts folder", "videos":"Retained videos folder", "choose":"Choose", "keep":"Keep downloaded video", "safety":"Original local media files are never automatically deleted.", "model":"Whisper model", "speech":"Spoken language", "automatic":"Auto-detect", "italian":"Italian", "english":"English", "theme":"Theme", "dark":"Dark", "light":"Light", "lang":"Interface", "start":"Start transcription", "stop":"Cancel", "open":"Open transcripts", "progress":"Progress", "ready":"Ready", "preparing":"Preparing...", "downloading":"Downloading...", "loading":"Loading model (first run downloads it)...", "transcribing":"Transcribing", "finished":"Transcription completed", "stopped":"Cancelled. Any partial transcripts were retained.", "error":"Error", "missing":"Enter a URL or select a file.", "notfound":"File not found.", "auth_title":"Webex authentication", "auth_explain":"This recording requires sign-in. Select a browser with an active session or choose a Netscape cookie file.", "auth_browser":"Browser", "auth_continue":"Continue", "cancel":"Cancel", "cookies":"Netscape cookie file (also Samsung Browser)", "samsung":"Samsung Browser (cookie file)", "no_browsers":"No supported browser detected; you can use a cookie file.", "auth_failed":"Authentication failed. Check your browser session, profile or cookie file.", "download_failed":"Download failed. Check the link and connection. Refresh expired HLS URLs.", "processing_failed":"Processing failed. See the local diagnostics log (no URLs or cookies).", "close_running":"A job is running. Cancel and close once it has stopped?", "model_tip":"Turbo: recommended balance. Large-v3: slower. .en models are English-only.", "output_saved":"Files saved in:", "logs":"Open logs folder", "model_error":"Model unavailable or model download failed.", "select_folder":"Choose folder", "permission":"Cannot write to output folder.", "browser_tip":"Browser security may prevent cookie extraction. Never share cookie files.", "video_copy":"Saving downloaded video...", "bad_source":"Local media and http(s) URLs are supported.", "no_media":"The download did not produce a media file.", "privacy":"Local transcription · no audio uploaded to AI services", "duplicate":"Name already used; selected an alternate name.", "model_warn":"This .en model only recognizes English. Continue?", "yes":"Yes", "no":"No"
 }
}

class JobCancelled(Exception):
    pass


def millis(seconds: float, srt: bool = False) -> str:
    value = max(0, round(seconds * 1000))
    h, rem = divmod(value, 3_600_000)
    m, rem = divmod(rem, 60_000)
    sec, ms = divmod(rem, 1000)
    return f"{h:02}:{m:02}:{sec:02}{',' if srt else '.'}{ms:03}"


def clean_name(name: str) -> str:
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name).strip(" .")
    return name[:90] or datetime.now().strftime("Lecture_%Y%m%d_%H%M%S")


def browser_candidates() -> dict[str, tuple]:
    local = Path(os.getenv("LOCALAPPDATA", ""))
    roaming = Path(os.getenv("APPDATA", ""))
    locations = {
        "Chrome": local / "Google/Chrome/User Data",
        "Edge": local / "Microsoft/Edge/User Data",
        "Firefox": roaming / "Mozilla/Firefox",
        "Brave": local / "BraveSoftware/Brave-Browser/User Data",
        "Opera": roaming / "Opera Software/Opera Stable",
        "Opera GX": roaming / "Opera Software/Opera GX Stable",
        "Vivaldi": local / "Vivaldi/User Data",
        "Chromium": local / "Chromium/User Data",
        "Whale": local / "Naver/Naver Whale/User Data",
    }
    found = {}
    for name, folder in locations.items():
        if folder.exists():
            if name == "Opera GX":
                found[name] = ("browser", "opera", str(folder))
            else:
                found[name] = ("browser", BROWSER_MAP[name], None)
    return found


def ensure_writable(folder: Path):
    folder.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryFile(dir=folder):
        pass


class PrivateLogger:
    """yt-dlp messages remain in memory for auth classification; never persist URLs."""
    def __init__(self):
        self.errors = []
    def debug(self, msg):
        pass
    def warning(self, msg):
        self.errors.append(str(msg).lower()[:1500])
    def error(self, msg):
        self.errors.append(str(msg).lower()[:1500])


class App:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.queue = Queue()
        self.stop_event = threading.Event()
        self.auth_event = threading.Event()
        self.auth_response = None
        self.auth_dialog = None
        self.running = False
        self.close_when_done = False
        self.model_instance = None
        self.model_name = None
        config = self.load_config()
        self.ui_language = tk.StringVar(value=config.get("ui_language", "it"))
        self.ui_theme = tk.StringVar(value=config.get("theme", "dark"))
        self.source = tk.StringVar(value="")
        self.lecture = tk.StringVar(value="")
        self.transcripts_dir = tk.StringVar(value=config.get("transcripts", str(DEFAULT_DIR / "Trascrizioni")))
        self.videos_dir = tk.StringVar(value=config.get("videos", str(DEFAULT_DIR / "Video")))
        self.keep_video = tk.BooleanVar(value=config.get("keep_video", False))
        self.model = tk.StringVar(value=config.get("model", "turbo"))
        self.spoken = tk.StringVar(value=config.get("spoken", "auto"))
        self.status = tk.StringVar()
        self.style = ttk.Style(root)
        root.title("LectureScribe 1.0")
        root.geometry("790x720")
        root.minsize(590, 620)
        root.columnconfigure(0, weight=1)
        root.rowconfigure(0, weight=1)
        self.apply_theme()
        self.rebuild()
        root.after(100, self.poll)
        root.protocol("WM_DELETE_WINDOW", self.on_close)

    def t(self, key):
        return I18N[self.ui_language.get()][key]

    def load_config(self):
        try:
            data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except (OSError, ValueError):
            return {}

    def save_config(self):
        data = {
            "ui_language": self.ui_language.get(), "theme": self.ui_theme.get(),
            "transcripts": self.transcripts_dir.get(), "videos": self.videos_dir.get(),
            "keep_video": self.keep_video.get(), "model": self.model.get(), "spoken": self.spoken.get(),
        }
        try:
            CONFIG_DIR.mkdir(parents=True, exist_ok=True)
            CONFIG_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        except OSError:
            pass

    def apply_theme(self):
        dark = self.ui_theme.get() == "dark"
        bg, panel, fg, input_bg, accent = ("#151922", "#202634", "#f0f3f9", "#2a3243", "#57bca7") if dark else ("#f5f7fb", "#ffffff", "#162033", "#ffffff", "#137965")
        self.root.configure(bg=bg)
        self.style.theme_use("clam")
        self.style.configure("TFrame", background=bg)
        self.style.configure("TLabel", background=bg, foreground=fg, font=("Segoe UI", 10))
        self.style.configure("Title.TLabel", background=bg, foreground=fg, font=("Segoe UI Semibold", 22))
        self.style.configure("Hint.TLabel", background=bg, foreground="#aab4c4" if dark else "#576275", font=("Segoe UI", 9))
        self.style.configure("TButton", background=panel, foreground=fg, padding=8, borderwidth=0)
        self.style.map("TButton", background=[("active", input_bg)])
        self.style.configure("TEntry", fieldbackground=input_bg, foreground=fg, insertcolor=fg, padding=5)
        self.style.configure("TCombobox", fieldbackground=input_bg, foreground=fg, background=panel, arrowcolor=fg, padding=4)
        self.style.map("TCombobox", fieldbackground=[("readonly", input_bg)], foreground=[("readonly", fg)])
        self.style.configure("TCheckbutton", background=bg, foreground=fg)
        self.style.map("TCheckbutton", background=[("active", bg)])
        self.style.configure("TProgressbar", troughcolor=panel, background=accent, borderwidth=0)
        self.style.configure("TSeparator", background=panel)

    def rebuild(self):
        if hasattr(self, "canvas"):
            self.canvas.destroy()
            self.scrollbar.destroy()
        self.apply_theme()
        self.canvas = tk.Canvas(self.root, borderwidth=0, highlightthickness=0,
                                bg="#151922" if self.ui_theme.get() == "dark" else "#f5f7fb")
        self.scrollbar = ttk.Scrollbar(self.root, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=self.scrollbar.set)
        self.canvas.grid(row=0, column=0, sticky="nsew")
        self.scrollbar.grid(row=0, column=1, sticky="ns")
        self.main = ttk.Frame(self.canvas, padding=20)
        self.window_id = self.canvas.create_window((0, 0), window=self.main, anchor="nw")
        self.main.bind("<Configure>", lambda event: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.bind("<Configure>", lambda event: self.canvas.itemconfigure(self.window_id, width=event.width))
        self.canvas.bind("<MouseWheel>", lambda event: self.canvas.yview_scroll(-int(event.delta / 120), "units"))
        self.main.columnconfigure(1, weight=1)
        row = 0
        ttk.Label(self.main, text="LectureScribe", style="Title.TLabel").grid(row=row, column=0, columnspan=3, sticky="w")
        row += 1
        ttk.Label(self.main, text=self.t("tagline"), style="Hint.TLabel").grid(row=row, column=0, columnspan=3, sticky="w", pady=(0, 14))
        row += 1
        bar = ttk.Frame(self.main)
        bar.grid(row=row, column=0, columnspan=3, sticky="ew", pady=(0, 14))
        ttk.Label(bar, text=self.t("lang")).pack(side="left", padx=(0, 6))
        lang = ttk.Combobox(bar, textvariable=self.ui_language, values=["it", "en"], width=5, state="readonly")
        lang.pack(side="left", padx=(0, 18))
        lang.bind("<<ComboboxSelected>>", self.update_preferences)
        ttk.Label(bar, text=self.t("theme")).pack(side="left", padx=(0, 6))
        theme = ttk.Combobox(bar, textvariable=self.ui_theme, values=["dark", "light"], width=9, state="readonly")
        theme.pack(side="left")
        theme.bind("<<ComboboxSelected>>", self.update_preferences)
        row += 1
        row = self.entry_row(row, "source", self.source, self.browse_file, "browse")
        row = self.entry_row(row, "title", self.lecture)
        row = self.entry_row(row, "transcripts", self.transcripts_dir, lambda: self.choose_dir(self.transcripts_dir), "choose")
        row = self.entry_row(row, "videos", self.videos_dir, lambda: self.choose_dir(self.videos_dir), "choose")
        ttk.Checkbutton(self.main, text=self.t("keep"), variable=self.keep_video).grid(row=row, column=0, columnspan=3, sticky="w", pady=(3, 2))
        row += 1
        ttk.Label(self.main, text=self.t("safety"), style="Hint.TLabel", wraplength=590).grid(row=row, column=0, columnspan=3, sticky="w", pady=(0, 10))
        row += 1
        ttk.Label(self.main, text=self.t("model")).grid(row=row, column=0, sticky="w", pady=4)
        ttk.Combobox(self.main, textvariable=self.model, values=MODELS, state="readonly").grid(row=row, column=1, columnspan=2, sticky="ew", pady=4)
        row += 1
        ttk.Label(self.main, text=self.t("model_tip"), style="Hint.TLabel", wraplength=650).grid(row=row, column=0, columnspan=3, sticky="w", pady=(0, 10))
        row += 1
        ttk.Label(self.main, text=self.t("speech")).grid(row=row, column=0, sticky="w", pady=4)
        ttk.Combobox(self.main, textvariable=self.spoken, values=["auto", "it", "en"], state="readonly").grid(row=row, column=1, columnspan=2, sticky="ew", pady=4)
        row += 1
        ttk.Separator(self.main).grid(row=row, column=0, columnspan=3, sticky="ew", pady=(13, 13))
        row += 1
        ttk.Label(self.main, text=self.t("progress")).grid(row=row, column=0, columnspan=3, sticky="w")
        row += 1
        self.progress = ttk.Progressbar(self.main, maximum=100)
        self.progress.grid(row=row, column=0, columnspan=3, sticky="ew", pady=(7, 7))
        row += 1
        self.status.set(self.t("ready") if not self.running else self.status.get())
        ttk.Label(self.main, textvariable=self.status, wraplength=650).grid(row=row, column=0, columnspan=3, sticky="w", pady=(0, 14))
        row += 1
        self.start_button = ttk.Button(self.main, text=self.t("start"), command=self.start)
        self.start_button.grid(row=row, column=0, columnspan=3, sticky="ew", pady=3)
        row += 1
        self.stop_button = ttk.Button(self.main, text=self.t("stop"), command=self.cancel)
        self.stop_button.grid(row=row, column=0, columnspan=3, sticky="ew", pady=3)
        row += 1
        self.update_buttons()
        linkrow = ttk.Frame(self.main)
        linkrow.grid(row=row, column=0, columnspan=3, sticky="ew", pady=(4, 4))
        ttk.Button(linkrow, text=self.t("open"), command=lambda: self.open_folder(Path(self.transcripts_dir.get()))).pack(side="left", fill="x", expand=True, padx=(0, 5))
        ttk.Button(linkrow, text=self.t("logs"), command=lambda: self.open_folder(CONFIG_DIR)).pack(side="left", fill="x", expand=True)
        row += 1
        ttk.Label(self.main, text=self.t("privacy"), style="Hint.TLabel").grid(row=row, column=0, columnspan=3, sticky="w", pady=(8, 0))

    def entry_row(self, row, label_key, var, browse=None, button_key=None):
        ttk.Label(self.main, text=self.t(label_key)).grid(row=row, column=0, sticky="w", padx=(0, 12), pady=7)
        ttk.Entry(self.main, textvariable=var).grid(row=row, column=1, sticky="ew", pady=7)
        if browse:
            ttk.Button(self.main, text=self.t(button_key), command=browse).grid(row=row, column=2, padx=(8, 0), pady=7)
        return row+1

    def update_preferences(self, _event=None):
        if self.running:
            # Rendering during an active job is harmless: state is kept in variables.
            pass
        self.save_config()
        self.rebuild()

    def choose_dir(self, var):
        chosen = filedialog.askdirectory(initialdir=var.get(), title=self.t("select_folder"))
        if chosen:
            var.set(chosen)
            self.save_config()

    def browse_file(self):
        selected = filedialog.askopenfilename(filetypes=[("Media", "*.mp4 *.mkv *.webm *.mov *.mp3 *.m4a *.wav *.flac *.aac"), ("All files", "*.*")])
        if selected:
            self.source.set(selected)

    def open_folder(self, folder):
        folder.mkdir(parents=True, exist_ok=True)
        os.startfile(str(folder))

    def update_buttons(self):
        if hasattr(self, "start_button"):
            self.start_button.configure(state="disabled" if self.running else "normal")
            self.stop_button.configure(state="normal" if self.running else "disabled")

    def send(self, kind, value=None):
        self.queue.put((kind, value))

    def log(self, code):
        # Log event codes only: never URLs, passwords, browser cookies or exception strings.
        try:
            CONFIG_DIR.mkdir(parents=True, exist_ok=True)
            with (CONFIG_DIR / "diagnostics.log").open("a", encoding="utf-8") as file:
                file.write(f"{datetime.now().isoformat(timespec='seconds')} {code}\n")
        except OSError:
            pass

    def poll(self):
        try:
            while True:
                kind, value = self.queue.get_nowait()
                if kind == "status":
                    self.status.set(value)
                elif kind == "progress":
                    self.progress["value"] = min(100, max(0, value))
                elif kind == "auth":
                    self.auth_popup()
                elif kind in ("done", "cancelled", "error"):
                    self.running = False
                    self.update_buttons()
                    if self.close_when_done:
                        self.root.destroy()
                        return
                    if kind == "done":
                        self.progress["value"] = 100
                        self.status.set(self.t("finished"))
                        messagebox.showinfo(APP, self.t("finished") + "\n" + self.t("output_saved") + "\n" + value)
                    elif kind == "cancelled":
                        self.status.set(self.t("stopped"))
                        messagebox.showinfo(APP, self.t("stopped"))
                    else:
                        self.status.set(self.t("error"))
                        messagebox.showerror(APP, self.t(value))
        except Empty:
            pass
        self.root.after(100, self.poll)

    def start(self):
        if self.running:
            return
        source = self.source.get().strip().strip('"')
        if not source:
            messagebox.showwarning(APP, self.t("missing"))
            return
        if not source.startswith(("http://", "https://")) and not Path(source).is_file():
            messagebox.showerror(APP, self.t("notfound"))
            return
        model = self.model.get()
        if model.endswith(".en") and self.spoken.get() == "it":
            if not messagebox.askyesno(APP, self.t("model_warn")):
                return
        transcript_dir = Path(self.transcripts_dir.get()).expanduser()
        video_dir = Path(self.videos_dir.get()).expanduser()
        try:
            ensure_writable(transcript_dir)
            if self.keep_video.get():
                ensure_writable(video_dir)
        except OSError:
            messagebox.showerror(APP, self.t("permission"))
            return
        self.save_config()
        name = clean_name(self.lecture.get())
        num = 2
        base = name
        while any((transcript_dir / f"{name}{suffix}").exists() for suffix in (".txt", ".srt", ".partial.txt", ".partial.srt")) or any((video_dir / f"{name}{suffix}").exists() for suffix in EXTS):
            name = f"{base}_{num}"
            num += 1
        self.stop_event.clear()
        self.auth_event.clear()
        self.auth_response = None
        self.running = True
        self.progress["value"] = 0
        self.status.set(self.t("preparing"))
        self.update_buttons()
        job = {"source": source, "name": name, "model": model, "spoken": self.spoken.get(), "keep": self.keep_video.get(), "transcripts": transcript_dir, "videos": video_dir}
        threading.Thread(target=self.worker, args=(job,), daemon=True).start()

    def cancel(self):
        if not self.running:
            return
        self.stop_event.set()
        self.auth_event.set()
        if self.auth_dialog is not None and self.auth_dialog.winfo_exists():
            self.auth_dialog.destroy()
        self.auth_dialog = None
        self.stop_button.configure(state="disabled")

    def check_cancel(self):
        if self.stop_event.is_set():
            raise JobCancelled()

    def auth_popup(self):
        if self.stop_event.is_set():
            self.auth_event.set()
            return
        dlg = tk.Toplevel(self.root)
        self.auth_dialog = dlg
        dlg.title(self.t("auth_title"))
        dlg.geometry("530x285")
        dlg.minsize(410, 245)
        dlg.transient(self.root)
        dlg.grab_set()
        frame = ttk.Frame(dlg, padding=20)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text=self.t("auth_explain"), wraplength=480).pack(anchor="w", pady=(0, 12))
        installed = browser_candidates()
        options = list(installed) + [self.t("samsung"), self.t("cookies")]
        selection = tk.StringVar(value=options[0])
        ttk.Label(frame, text=self.t("auth_browser")).pack(anchor="w")
        ttk.Combobox(frame, textvariable=selection, values=options, state="readonly").pack(fill="x", pady=(6, 8))
        ttk.Label(frame, text=self.t("browser_tip"), style="Hint.TLabel", wraplength=480).pack(anchor="w", pady=(0, 8))
        def resolve(choice):
            self.auth_response = choice
            self.auth_event.set()
            if dlg.winfo_exists():
                dlg.destroy()
            self.auth_dialog = None
        def confirm():
            key = selection.get()
            if key in installed:
                resolve(installed[key])
            else:
                cookie_file = filedialog.askopenfilename(parent=dlg, filetypes=[("Netscape cookie file", "*.txt"), ("All files", "*.*")])
                if cookie_file:
                    resolve(("file", cookie_file))
        ttk.Button(frame, text=self.t("auth_continue"), command=confirm).pack(fill="x", pady=(7, 3))
        ttk.Button(frame, text=self.t("cancel"), command=lambda: resolve(None)).pack(fill="x")
        dlg.protocol("WM_DELETE_WINDOW", lambda: resolve(None))

    def download(self, url, folder):
        logger = PrivateLogger()
        def hook(data):
            self.check_cancel()
            if data.get("status") != "downloading":
                return
            total = data.get("total_bytes") or data.get("total_bytes_estimate")
            if total:
                self.send("progress", min(35, 35 * data.get("downloaded_bytes", 0) / total))
        base_opts = {
            "outtmpl": str(folder / "recording.%(ext)s"),
            "noplaylist": True,
            "concurrent_fragment_downloads": 4,
            "retries": 3,
            "fragment_retries": 3,
            "progress_hooks": [hook],
            "logger": logger,
            "quiet": True,
            "no_warnings": True,
            "noprogress": True,
        }
        def attempt(extra=None):
            opts = {**base_opts, **(extra or {})}
            with yt_dlp.YoutubeDL(opts) as dl:
                dl.download([url])
        self.log("DOWNLOAD_STARTED")
        self.send("status", self.t("downloading"))
        try:
            attempt()
        except DownloadError as exc:
            self.check_cancel()
            error = (str(exc) + " " + " ".join(logger.errors)).lower()
            if not any(token in error for token in AUTH_WORDS):
                self.log("DOWNLOAD_FAILED_NON_AUTH")
                raise RuntimeError("download_failed") from None
            self.log("AUTH_REQUIRED")
            self.auth_response = None
            self.auth_event.clear()
            self.send("auth")
            self.auth_event.wait()
            self.check_cancel()
            if self.auth_response is None:
                raise JobCancelled()
            selection = self.auth_response
            if selection[0] == "file":
                extra = {"cookiefile": selection[1]}
            else:
                extra = {"cookiesfrombrowser": (selection[1], selection[2]) if selection[2] else (selection[1],)}
            try:
                attempt(extra)
            except Exception:
                self.check_cancel()
                self.log("AUTH_RETRY_FAILED")
                raise RuntimeError("auth_failed") from None
        self.check_cancel()
        candidates = [p for p in folder.iterdir() if p.is_file() and p.suffix.lower() in EXTS]
        if not candidates:
            raise RuntimeError("no_media")
        self.log("DOWNLOAD_FINISHED")
        self.send("progress", 35)
        return max(candidates, key=lambda p: p.stat().st_size)

    def transcribe(self, job, media, network_media):
        self.check_cancel()
        self.send("status", self.t("loading"))
        if self.model_instance is None or self.model_name != job["model"]:
            try:
                self.model_instance = WhisperModel(job["model"], device="cpu", compute_type="int8", cpu_threads=8)
                self.model_name = job["model"]
            except Exception:
                self.log("MODEL_LOAD_FAILED")
                raise RuntimeError("model_error") from None
        self.check_cancel()
        language = None if job["spoken"] == "auto" else job["spoken"]
        segments, info = self.model_instance.transcribe(str(media), language=language, beam_size=5, vad_filter=True, condition_on_previous_text=True)
        duration = info.duration or 0
        folder = job["transcripts"]
        txt_path, srt_path = folder / (job["name"] + ".txt"), folder / (job["name"] + ".srt")
        count = 0
        completed = False
        self.log("TRANSCRIPTION_STARTED")
        try:
            with txt_path.open("w", encoding="utf-8") as txt, srt_path.open("w", encoding="utf-8") as srt:
                for segment in segments:
                    self.check_cancel()
                    sentence = segment.text.strip()
                    if not sentence:
                        continue
                    count += 1
                    txt.write(f"[{millis(segment.start)}] {sentence}\n")
                    srt.write(f"{count}\n{millis(segment.start, True)} --> {millis(segment.end, True)}\n{sentence}\n\n")
                    txt.flush()
                    srt.flush()
                    if duration:
                        start, portion = (35, 65) if network_media else (0, 100)
                        self.send("progress", start + min(1, segment.end / duration) * portion)
                    self.send("status", f"{self.t('transcribing')}: {millis(segment.end)}")
            self.check_cancel()
            completed = True
        finally:
            if not completed:
                for file in (txt_path, srt_path):
                    if file.exists():
                        file.replace(file.with_name(file.stem + ".partial" + file.suffix))
        self.log("TRANSCRIPTION_FINISHED")
        return txt_path, srt_path

    def worker(self, job):
        try:
            source = job["source"]
            is_url = source.startswith(("http://", "https://"))
            if is_url:
                with tempfile.TemporaryDirectory(prefix="lecturescribe_") as temp:
                    media = self.download(source, Path(temp))
                    self.transcribe(job, media, True)
                    if job["keep"]:
                        self.check_cancel()
                        self.send("status", self.t("video_copy"))
                        target = job["videos"] / (job["name"] + media.suffix)
                        shutil.copy2(media, target)
            else:
                media = Path(source)
                if not media.is_file():
                    raise RuntimeError("notfound")
                self.transcribe(job, media, False)
            self.send("done", str(job["transcripts"]))
        except JobCancelled:
            self.log("JOB_CANCELLED")
            self.send("cancelled")
        except RuntimeError as error:
            # All intentionally raised errors are translation keys, never raw URLs.
            code = str(error)
            if code not in I18N["en"]:
                code = "processing_failed"
            self.log("JOB_ERROR_" + code.upper())
            self.send("error", code)
        except Exception:
            self.log("JOB_ERROR_UNEXPECTED")
            self.send("error", "processing_failed")

    def on_close(self):
        if self.running:
            if not messagebox.askyesno(APP, self.t("close_running")):
                return
            self.close_when_done = True
            self.cancel()
            return
        self.save_config()
        self.root.destroy()


if __name__ == "__main__":
    root = tk.Tk()
    App(root)
    root.mainloop()
