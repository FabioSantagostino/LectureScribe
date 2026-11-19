"""LectureScribe — local lecture transcription GUI for Windows."""
from __future__ import annotations

import json
import os
import re
import sys
import winreg
import shutil
import tempfile
import threading
import tkinter as tk
from datetime import datetime
from pathlib import Path
from queue import Empty, Queue
from tkinter import filedialog, messagebox
import customtkinter as ctk

import yt_dlp
from faster_whisper import WhisperModel
from yt_dlp.utils import DownloadError
from lecturescribe_cloud import cloud_transcribe
from lecturescribe_updates import VERSION, fetch_release, stage_update, launch_installer, version_tuple, run_update_mode
try:
    from lecturescribe_build import REPO as BUILT_REPO
except ImportError:
    BUILT_REPO = ""

APP = "LectureScribe"
CONFIG_DIR = Path(os.getenv("APPDATA", str(Path.home()))) / APP
CONFIG_FILE = CONFIG_DIR / "settings.json"
DEFAULT_DIR = Path.home() / "Documents" / APP
EXTS = {".mp4", ".mkv", ".webm", ".mov", ".mp3", ".m4a", ".wav", ".flac", ".aac"}
QUALITY_CHOICES = ("fast", "balanced", "accurate")


def effective_model(quality: str, language: str) -> str:
    """Use English-only variants only where a matching variant exists."""
    if quality == "fast":
        return "small.en" if language == "en" else "small"
    if quality == "accurate":
        return "large-v3"
    return "turbo"  # Turbo and large-v3 have no English-only .en counterpart.


def windows_dark_mode() -> bool:
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize")
        with key:
            value, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
        return value == 0
    except (OSError, ValueError):
        return False

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

I18N["it"].update({'step_source': '01  Scegli la registrazione', 'step_source_help': 'Inserisci un collegamento Webex oppure seleziona un file dal PC.', 'original_filename_hint': 'Per impostazione predefinita useremo il titolo originale della registrazione.', 'custom_name': 'Usa un nome personalizzato', 'step_settings': '02  Qualità e lingua', 'step_settings_help': 'Solo due scelte. La variante del modello si adatta automaticamente alla lingua.', 'quality': 'Qualità della trascrizione', 'quality_fast': '⚡ Veloce', 'quality_balanced': '✦ Bilanciata (consigliata)', 'quality_accurate': '◎ Massima qualità', 'spoken_auto': 'Rileva automaticamente', 'spoken_it': 'Italiano', 'spoken_en': 'Inglese', 'quality_help': 'Veloce: Small (Small.en per inglese). Bilanciata: Turbo. Massima: Large-v3. Turbo e Large-v3 sono già multilingue.', 'advanced': 'Opzioni avanzate e salvataggio', 'step_run': '03  Avvia', 'keep_disabled': 'Il video scaricato verrà eliminato dopo la trascrizione.', 'keep_enabled': 'Il video scaricato verrà conservato nella cartella scelta.', 'title_missing': 'Inserisci un nome personalizzato oppure deseleziona la relativa casella.'})
I18N["en"].update({'step_source': '01  Choose recording', 'step_source_help': 'Paste a Webex link or choose a local media file.', 'original_filename_hint': "The recording's original title is used automatically.", 'custom_name': 'Use a custom lecture name', 'step_settings': '02  Quality & language', 'step_settings_help': 'Just two choices. The model variant adapts automatically to the spoken language.', 'quality': 'Transcription quality', 'quality_fast': '⚡ Fast', 'quality_balanced': '✦ Balanced (recommended)', 'quality_accurate': '◎ Highest quality', 'spoken_auto': 'Detect automatically', 'spoken_it': 'Italian', 'spoken_en': 'English', 'quality_help': 'Fast: Small (Small.en for English). Balanced: Turbo. Highest: Large-v3. Turbo and Large-v3 are already multilingual.', 'advanced': 'Advanced options & files', 'step_run': '03  Start', 'keep_disabled': 'Downloaded video is deleted after transcription.', 'keep_enabled': 'Downloaded video is retained in your selected folder.', 'title_missing': 'Enter a custom name or uncheck the custom name option.'})


I18N["it"].update({
 "queue":"Coda di trascrizione", "add_files":"+ File", "add_link":"+ Link", "clear_queue":"Svuota", "queue_empty":"Nessun elemento in coda", "queue_count":"Elementi in coda", "link_prompt":"Incolla il link Webex / HLS", "backend":"Motore di trascrizione", "local_engine":"Locale · Whisper", "cloud_engine":"Cloud · OpenAI API", "api_key":"Chiave API OpenAI (solo per questa sessione)", "cloud_warning":"Modalità cloud: l'audio sarà inviato a OpenAI. Richiede chiave API e può avere costi. I timestamp sono approssimativi (blocchi), nessun SRT cloud.", "auth_remember":"Ricorda metodo di accesso per i prossimi video", "updates":"Aggiornamenti", "update_repo":"Repository GitHub (owner/repo)", "check_update":"Cerca aggiornamenti", "update_found":"Nuova versione disponibile", "no_update":"Hai già l'ultima versione", "install_update":"Scaricare e installare l'aggiornamento? L'app verrà riavviata.", "update_error":"Aggiornamento non riuscito. Controlla repository e connessione.", "cloud_confirm":"La registrazione audio sarà caricata su OpenAI e potrebbe essere fatturata. Continuare?", "cloud_key_missing":"Inserisci la chiave API per il servizio cloud.", "cloud_result":"La trascrizione cloud usa timestamp di blocco approssimativi, non sottotitoli sincronizzati.", "batch_finished":"Elaborazione della coda completata", "batch_failed":"Alcune registrazioni non sono state elaborate. Vedi log diagnostici."})
I18N["en"].update({
 "queue":"Transcription queue", "add_files":"+ Files", "add_link":"+ Link", "clear_queue":"Clear", "queue_empty":"No queued items", "queue_count":"Queued items", "link_prompt":"Paste Webex / HLS URL", "backend":"Transcription engine", "local_engine":"Local · Whisper", "cloud_engine":"Cloud · OpenAI API", "api_key":"OpenAI API key (session only)", "cloud_warning":"Cloud mode sends audio to OpenAI. Requires a billed API key. Timestamps are approximate chunk markers, no cloud SRT.", "auth_remember":"Remember authentication method for future videos", "updates":"Updates", "update_repo":"GitHub repository (owner/repo)", "check_update":"Check for updates", "update_found":"A new version is available", "no_update":"You're up to date", "install_update":"Download and install the update? The app will restart.", "update_error":"Update failed. Check repository and connection.", "cloud_confirm":"Audio will be uploaded to OpenAI and may incur charges. Continue?", "cloud_key_missing":"Enter your cloud API key.", "cloud_result":"Cloud timestamps mark approximate chunks, not synchronized subtitles.", "batch_finished":"Queue finished", "batch_failed":"Some recordings failed. See diagnostics."})

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
        self.pending_sources = []
        self.auth_cached_choice = None
        self.update_asset = None
        self.update_temp = None
        config = self.load_config()
        self.ui_language = tk.StringVar(value=config.get("ui_language", "it"))
        self.ui_theme = tk.StringVar(value=config.get("theme", "auto"))
        self.source = tk.StringVar(value="")
        self.lecture = tk.StringVar(value="")
        self.custom_name = tk.BooleanVar(value=False)
        self.advanced_open = tk.BooleanVar(value=False)
        self.transcripts_dir = tk.StringVar(value=config.get("transcripts", str(DEFAULT_DIR / "Trascrizioni")))
        self.videos_dir = tk.StringVar(value=config.get("videos", str(DEFAULT_DIR / "Video")))
        self.keep_video = tk.BooleanVar(value=config.get("keep_video", False))
        self.model = tk.StringVar(value=config.get("quality", "balanced") if config.get("quality", "balanced") in QUALITY_CHOICES else "balanced")
        self.spoken = tk.StringVar(value=config.get("spoken", "auto"))
        self.engine = tk.StringVar(value=config.get("engine", "local"))
        self.api_key = tk.StringVar(value="")  # Session-only, never stored or logged.
        self.remember_auth = tk.BooleanVar(value=config.get("remember_auth", False))
        self.auth_saved = config.get("auth_choice", None)
        self.cpu_threads = config.get("cpu_threads", min(8, os.cpu_count() or 8))
        self.update_repo = tk.StringVar(value=config.get("update_repo") or BUILT_REPO)
        self.status = tk.StringVar(value=I18N[self.ui_language.get()]["ready"])
        self.progress_value = 0.0
        self._phase = 0
        self._system_dark = windows_dark_mode()
        self._wheel_remainder = 0.0
        self.scroll_area = None
        self.main = None
        root.title("LectureScribe")
        root.geometry("760x620")
        root.minsize(590, 470)
        self.apply_theme()
        self.rebuild()
        root.after(100, self.poll)
        root.after(2500, self.watch_system_theme)
        root.after(350, self.animate_status)
        root.protocol("WM_DELETE_WINDOW", self.on_close)

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
            "keep_video": self.keep_video.get(), "quality": self.model.get(), "spoken": self.spoken.get(),
            "engine": self.engine.get(), "update_repo": self.update_repo.get(),
            "remember_auth": self.remember_auth.get(),
            "auth_choice": self.auth_saved if self.remember_auth.get() else None,
        }
        try:
            CONFIG_DIR.mkdir(parents=True, exist_ok=True)
            CONFIG_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        except OSError:
            pass

    def t(self, key):
        return I18N[self.ui_language.get()].get(key, key)

    def is_dark(self):
        mode = self.ui_theme.get()
        return windows_dark_mode() if mode == "auto" else mode == "dark"

    def palette(self):
        if self.is_dark():
            return dict(bg="#0d1017", panel="#171c26", inset="#242b39",
                        fg="#f5f7fb", muted="#a0aaba", line="#2e3646",
                        accent="#40d6ae", accent_text="#09241b", hover="#30394b")
        return dict(bg="#f5f7fb", panel="#ffffff", inset="#edf1f7",
                    fg="#1b2433", muted="#647084", line="#e3e8f0",
                    accent="#087c68", accent_text="#ffffff", hover="#e5ebf3")

    def apply_theme(self):
        ctk.set_appearance_mode("Dark" if self.is_dark() else "Light")
        ctk.set_default_color_theme("blue")
        self.root.configure(fg_color=self.palette()["bg"])

    def text(self, parent, text, size=12, bold=False, muted=False, **kw):
        c = self.palette()
        return ctk.CTkLabel(parent, text=text,
            font=("Segoe UI", size, "bold" if bold else "normal"),
            text_color=c["muted"] if muted else c["fg"], **kw)

    def panel(self, parent):
        c = self.palette()
        card = ctk.CTkFrame(parent, fg_color=c["panel"], corner_radius=14,
                            border_width=1, border_color=c["line"])
        card.pack(fill="x", pady=(0, 10))
        return card

    def choose_input(self, parent, variable, callback, label):
        c = self.palette()
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", padx=15, pady=(6, 0))
        ctk.CTkEntry(row, textvariable=variable, height=34, corner_radius=8,
                     fg_color=c["inset"], border_width=0, text_color=c["fg"]
                     ).pack(side="left", fill="x", expand=True)
        self.secondary_button(row, label, callback).pack(side="left", padx=(7, 0))
        return row

    def secondary_button(self, parent, title, callback, width=90):
        c = self.palette()
        return ctk.CTkButton(parent, text=title, command=callback, width=width,
            height=34, corner_radius=8, fg_color=c["inset"],
            hover_color=c["hover"], text_color=c["fg"],
            font=("Segoe UI", 12, "bold"))

    def _wheel(self, event):
        """Scroll faster on Windows precision touchpads without stacking handlers.

        The scrollable container is persistent: rebuilding only its children
        avoids duplicate canvases, scrollbars, and CustomTkinter bindings.
        """
        if self.scroll_area is None:
            return "break"
        delta = getattr(event, "delta", 0)
        if not delta:
            return "break"
        # Touchpads frequently report small deltas (<120), while a wheel
        # notch is typically 120. Both should feel immediately responsive.
        steps = min(12, max(3, round(abs(delta) / 120 * 6)))
        direction = -1 if delta > 0 else 1
        self.scroll_area._parent_canvas.yview_scroll(direction * steps, "units")
        return "break"

    def rebuild(self):
        c = self.palette()
        self.apply_theme()

        # CTkScrollableFrame owns a separate parent container and canvas.
        # Destroying/recreating it on each setting change left stale widgets
        # and scrollbars behind. Keep ONE instance for the app lifetime.
        if self.scroll_area is None:
            self.scroll_area = ctk.CTkScrollableFrame(
                self.root, fg_color=c["bg"],
                scrollbar_button_color=c["line"],
                scrollbar_button_hover_color=c["muted"],
                corner_radius=0, border_width=0
            )
            self.scroll_area.pack(fill="both", expand=True)
            self.root.bind_all("<MouseWheel>", self._wheel)
        else:
            self.scroll_area.configure(
                fg_color=c["bg"],
                scrollbar_button_color=c["line"],
                scrollbar_button_hover_color=c["muted"]
            )
            if self.main is not None:
                self.main.destroy()

        self.main = ctk.CTkFrame(
            self.scroll_area, fg_color="transparent", width=650
        )
        self.main.pack(fill="x", expand=True, padx=16, pady=12)

        header = ctk.CTkFrame(self.main, fg_color="transparent")
        header.pack(fill="x", pady=(0, 11))
        branding = ctk.CTkFrame(header, fg_color="transparent")
        branding.pack(side="left", fill="x", expand=True)
        self.text(branding, "◉  LectureScribe", 21, True).pack(anchor="w")
        self.text(branding, self.t("tagline"), 11, muted=True).pack(anchor="w")
        tools = ctk.CTkFrame(header, fg_color="transparent")
        tools.pack(side="right")
        self.secondary_button(tools, "EN" if self.ui_language.get()=="it" else "IT",
                              self.toggle_language, width=40).pack(side="left", padx=(0, 6))
        theme_labels = {"auto":"◐", "light":"☀", "dark":"☾"}
        self.secondary_button(tools, theme_labels[self.ui_theme.get()],
                              self.cycle_theme, width=42).pack(side="left")

        source_card = self.panel(self.main)
        self.text(source_card, self.t("step_source"), 14, True).pack(anchor="w", padx=15, pady=(12, 2))
        self.choose_input(source_card, self.source, self.browse_file, self.t("browse"))
        queue_controls = ctk.CTkFrame(source_card, fg_color="transparent")
        queue_controls.pack(fill="x", padx=15, pady=(8, 0))
        self.text(queue_controls, self.t("queue"), 11, True).pack(side="left", padx=(0, 8))
        self.secondary_button(queue_controls, self.t("add_files"), self.enqueue_files, 66).pack(side="left", padx=(0, 5))
        self.secondary_button(queue_controls, self.t("add_link"), self.enqueue_link, 65).pack(side="left", padx=(0, 5))
        self.secondary_button(queue_controls, self.t("clear_queue"), self.clear_queue, 76).pack(side="left")
        self.queue_label = self.text(source_card, "", 10, muted=True, wraplength=580, justify="left")
        self.queue_label.pack(anchor="w", padx=15, pady=(4, 2))
        self.refresh_queue()
        self.text(source_card, self.t("original_filename_hint"), 10, muted=True,
                  wraplength=580, justify="left").pack(anchor="w", padx=15, pady=(6, 0))
        ctk.CTkCheckBox(source_card, text=self.t("custom_name"), variable=self.custom_name,
            command=self.toggle_custom_name, checkbox_width=17, checkbox_height=17,
            font=("Segoe UI", 11), text_color=c["fg"],
            fg_color=c["accent"], hover_color=c["accent"]).pack(anchor="w", padx=15, pady=(9, 12))
        self.custom_row = ctk.CTkFrame(source_card, fg_color="transparent")
        if self.custom_name.get():
            self.custom_row.pack(fill="x", padx=15, pady=(0, 12))
        ctk.CTkEntry(self.custom_row, textvariable=self.lecture, height=34,
                     fg_color=c["inset"], border_width=0).pack(fill="x")

        settings_card = self.panel(self.main)
        self.text(settings_card, self.t("step_settings"), 14, True).pack(anchor="w", padx=15, pady=(12, 9))
        line = ctk.CTkFrame(settings_card, fg_color="transparent")
        line.pack(fill="x", padx=15, pady=(0, 13))
        line.grid_columnconfigure(0, weight=1, uniform="half")
        line.grid_columnconfigure(1, weight=1, uniform="half")
        self.text(line, self.t("quality"), 11).grid(row=0, column=0, sticky="w")
        self.text(line, self.t("speech"), 11).grid(row=0, column=1, sticky="w", padx=(10,0))
        self.quality_label_map = {self.t("quality_"+x): x for x in QUALITY_CHOICES}
        quality_values = list(self.quality_label_map)
        self.quality_combo = ctk.CTkOptionMenu(line, values=quality_values, height=34,
            fg_color=c["inset"], button_color=c["inset"],
            button_hover_color=c["hover"], text_color=c["fg"],
            dropdown_fg_color=c["panel"], dropdown_text_color=c["fg"],
            command=lambda value: self.change_quality(QUALITY_CHOICES.index(self.quality_label_map[value])))
        self.quality_combo.grid(row=1, column=0, sticky="ew", pady=(5,0))
        self.quality_combo.set(self.t("quality_"+self.model.get()))
        self.language_label_map = {self.t("spoken_"+x): x for x in ("auto","it","en")}
        self.speech_combo = ctk.CTkOptionMenu(line, values=list(self.language_label_map), height=34,
            fg_color=c["inset"], button_color=c["inset"],
            button_hover_color=c["hover"], text_color=c["fg"],
            dropdown_fg_color=c["panel"], dropdown_text_color=c["fg"],
            command=lambda value: self.change_speech(self.language_label_map[value]))
        self.speech_combo.grid(row=1, column=1, sticky="ew", padx=(10,0), pady=(5,0))
        self.speech_combo.set(self.t("spoken_"+self.spoken.get()))

        mode_row = ctk.CTkFrame(settings_card, fg_color="transparent")
        mode_row.pack(fill="x", padx=15, pady=(0, 12))
        self.text(mode_row, self.t("backend"), 11).pack(anchor="w", pady=(0, 4))
        engine_labels = {self.t("local_engine"): "local", self.t("cloud_engine"): "cloud"}
        mode_combo = ctk.CTkOptionMenu(mode_row, values=list(engine_labels), height=32,
            fg_color=c["inset"], button_color=c["inset"], text_color=c["fg"],
            dropdown_fg_color=c["panel"], dropdown_text_color=c["fg"],
            command=lambda value: self.set_engine(engine_labels[value]))
        mode_combo.pack(fill="x")
        mode_combo.set(self.t("cloud_engine") if self.engine.get() == "cloud" else self.t("local_engine"))
        if self.engine.get() == "cloud":
            self.text(mode_row, self.t("api_key"), 10).pack(anchor="w", pady=(7, 3))
            ctk.CTkEntry(mode_row, textvariable=self.api_key, show="•", height=32).pack(fill="x")
            self.text(mode_row, self.t("cloud_warning"), 10, muted=True, wraplength=590, justify="left").pack(anchor="w", pady=(7, 0))

        advanced = self.panel(self.main)
        arrow = "⌄" if self.advanced_open.get() else "›"
        self.secondary_button(advanced, arrow + "  " + self.t("advanced"),
                              self.toggle_advanced, width=245).pack(anchor="w", padx=12, pady=9)
        if self.advanced_open.get():
            self.text(advanced, self.t("transcripts"), 11).pack(anchor="w", padx=15)
            self.choose_input(advanced, self.transcripts_dir, lambda: self.choose_dir(self.transcripts_dir), self.t("choose"))
            self.text(advanced, self.t("videos"), 11).pack(anchor="w", padx=15, pady=(9,0))
            self.choose_input(advanced, self.videos_dir, lambda: self.choose_dir(self.videos_dir), self.t("choose"))
            ctk.CTkCheckBox(advanced, text=self.t("keep"), variable=self.keep_video,
                command=self.save_config, checkbox_width=17, checkbox_height=17,
                font=("Segoe UI", 11), text_color=c["fg"],
                fg_color=c["accent"]).pack(anchor="w", padx=15, pady=(11,9))
            actions = ctk.CTkFrame(advanced, fg_color="transparent")
            actions.pack(anchor="w", padx=15, pady=(0,12))
            self.secondary_button(actions, self.t("open"),
                lambda: self.open_folder(Path(self.transcripts_dir.get())), 148).pack(side="left", padx=(0,7))
            self.secondary_button(actions, self.t("logs"),
                lambda: self.open_folder(CONFIG_DIR), 140).pack(side="left")
            self.text(advanced, self.t("updates") + " · v" + VERSION, 11, True).pack(anchor="w", padx=15, pady=(12,0))
            self.choose_input(advanced, self.update_repo, self.check_updates, self.t("check_update"))
            self.text(advanced, self.t("update_repo"), 10, muted=True).pack(anchor="w", padx=15, pady=(1,12))

        run_card = self.panel(self.main)
        self.text(run_card, self.t("step_run"), 14, True).pack(anchor="w", padx=15, pady=(11,8))
        buttons = ctk.CTkFrame(run_card, fg_color="transparent")
        buttons.pack(fill="x", padx=15)
        self.start_button = ctk.CTkButton(buttons, text="▶  " + self.t("start"),
            command=self.start, height=38, corner_radius=9,
            fg_color=c["accent"], hover_color=c["accent"], text_color=c["accent_text"],
            font=("Segoe UI", 12, "bold"))
        self.start_button.pack(side="left", fill="x", expand=True)
        self.stop_button = self.secondary_button(buttons, "■  " + self.t("stop"), self.cancel, 105)
        self.stop_button.pack(side="left", padx=(8,0))
        self.progress = ctk.CTkProgressBar(run_card, height=6, corner_radius=6,
            progress_color=c["accent"], fg_color=c["inset"])
        self.progress.pack(fill="x", padx=15, pady=(13,5))
        self.progress.set(self.progress_value / 100)
        self.status_label = self.text(run_card, self.status.get(), 10, muted=True)
        self.status_label.pack(anchor="w", padx=15, pady=(0,11))
        self.update_buttons()
        self.text(self.main, "◆  " + self.t("privacy"), 10, muted=True).pack(anchor="center", pady=(0,7))

    def toggle_custom_name(self):
        if self.custom_name.get():
            self.custom_row.pack(fill="x", padx=15, pady=(0, 12))
        else:
            self.custom_row.pack_forget()

    def refresh_queue(self):
        if hasattr(self, "queue_label") and self.queue_label.winfo_exists():
            names = [Path(x).name if not x.startswith(("https://", "http://")) else "Webex / URL" for x in self.pending_sources[:3]]
            label = f"{len(self.pending_sources)} · " + ", ".join(names) if names else self.t("queue_empty")
            self.queue_label.configure(text=label)

    def enqueue_files(self):
        files = filedialog.askopenfilenames(filetypes=[("Media", "*.mp4 *.mkv *.webm *.mov *.mp3 *.m4a *.wav *.flac *.aac")])
        self.pending_sources.extend(files)
        self.refresh_queue()

    def enqueue_link(self):
        from tkinter.simpledialog import askstring
        url = askstring(APP, self.t("link_prompt"), parent=self.root)
        if url and url.strip().startswith(("https://", "http://")):
            self.pending_sources.append(url.strip())
            self.refresh_queue()

    def clear_queue(self):
        if not self.running:
            self.pending_sources.clear()
            self.refresh_queue()

    def set_engine(self, value):
        self.engine.set(value)
        self.update_preferences()

    def check_updates(self):
        self.save_config()
        repo = self.update_repo.get().strip()
        def task():
            try:
                tag, asset = fetch_release(repo)
                if version_tuple(tag) > version_tuple(VERSION):
                    self.send("update_found", (tag, asset))
                else:
                    self.send("update_none")
            except Exception:
                self.send("update_error")
        threading.Thread(target=task, daemon=True).start()

    def confirm_update(self, data):
        tag, asset = data
        if not messagebox.askyesno(APP, f"{self.t('update_found')}: {tag}\n\n{self.t('install_update')}"):
            return
        def task():
            try:
                folder = Path(tempfile.mkdtemp(prefix="lecturescribe_update_"))
                binary = stage_update(asset, folder)
                self.send("update_ready", str(binary))
            except Exception:
                self.send("update_error")
        threading.Thread(target=task, daemon=True).start()

    def toggle_advanced(self):
        self.advanced_open.set(not self.advanced_open.get())
        self.rebuild()

    def change_quality(self, index):
        self.model.set(QUALITY_CHOICES[index])
        self.save_config()

    def change_speech(self, code):
        self.spoken.set(code)
        self.save_config()

    def theme_icon(self):
        labels = {"it": {"auto": "◐  Sistema", "light": "☀  Chiaro", "dark": "☾  Scuro"},
                  "en": {"auto": "◐  System", "light": "☀  Light", "dark": "☾  Dark"}}
        return labels[self.ui_language.get()][self.ui_theme.get()]

    def cycle_theme(self):
        choices = ("auto", "light", "dark")
        self.ui_theme.set(choices[(choices.index(self.ui_theme.get()) + 1) % len(choices)])
        self.update_preferences()

    def toggle_language(self):
        self.ui_language.set("en" if self.ui_language.get() == "it" else "it")
        self.update_preferences()

    def watch_system_theme(self):
        if self.ui_theme.get() == "auto":
            updated = windows_dark_mode()
            if updated != self._system_dark:
                self._system_dark = updated
                self.rebuild()
        self.root.after(2500, self.watch_system_theme)

    def animate_status(self):
        # A subtle animated ellipsis while a job is active, without modifying the source status.
        if self.running and hasattr(self, "status_label"):
            self._phase = (self._phase + 1) % 4
            self.status_label.configure(text=self.status.get() + " " + "·" * self._phase)
        elif hasattr(self, "status_label"):
            self.status_label.configure(text=self.status.get())
        self.root.after(350, self.animate_status)

    def update_preferences(self, _event=None):
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
                    self.progress_value = min(100, max(0, value))
                    self.progress.set(self.progress_value / 100)
                elif kind == "auth":
                    self.auth_popup()
                elif kind == "update_found":
                    self.confirm_update(value)
                elif kind == "update_none":
                    messagebox.showinfo(APP, self.t("no_update"))
                elif kind == "update_error":
                    messagebox.showerror(APP, self.t("update_error"))
                elif kind == "update_ready":
                    if self.running:
                        messagebox.showwarning(APP, "Finish the active job before installing")
                    else:
                        try:
                            launch_installer(value)
                            self.save_config()
                            self.root.destroy()
                        except Exception:
                            messagebox.showerror(APP, self.t("update_error"))
                elif kind == "done_batch":
                    self.running = False
                    self.update_buttons()
                    total, failed, location = value
                    self.status.set(self.t("batch_finished"))
                    messagebox.showinfo(APP, f"{self.t('batch_finished')}: {total-failed}/{total}\n{location}" + ("\n" + self.t("batch_failed") if failed else ""))
                    if self.close_when_done:
                        self.root.destroy()
                        return
                elif kind in ("done", "cancelled", "error"):
                    self.running = False
                    self.update_buttons()
                    if self.close_when_done:
                        self.root.destroy()
                        return
                    if kind == "done":
                        self.progress_value = 100
                        self.progress.set(1)
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
        sources = ([source] if source else []) + self.pending_sources[:]
        sources = list(dict.fromkeys(sources))
        if not sources:
            messagebox.showwarning(APP, self.t("missing"))
            return
        if any(not x.startswith(("http://", "https://")) and not Path(x).is_file() for x in sources):
            messagebox.showerror(APP, self.t("notfound"))
            return
        if self.engine.get() == "cloud":
            if not self.api_key.get().strip():
                messagebox.showwarning(APP, self.t("cloud_key_missing"))
                return
            if not messagebox.askyesno(APP, self.t("cloud_confirm")):
                return
        if self.custom_name.get() and not self.lecture.get().strip():
            messagebox.showwarning(APP, self.t("title_missing"))
            return
        model = effective_model(self.model.get(), self.spoken.get())
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
        # Name resolution happens in the worker after retrieving Webex metadata.
        requested_name = clean_name(self.lecture.get()) if self.custom_name.get() else None
        self.stop_event.clear()
        self.auth_event.clear()
        self.auth_response = None
        self.running = True
        self.progress_value = 0
        self.progress.set(0)
        self.status.set(self.t("preparing"))
        self.update_buttons()
        job = {"source": source, "name": requested_name, "model": model, "spoken": self.spoken.get(), "keep": self.keep_video.get(), "transcripts": transcript_dir, "videos": video_dir, "engine": self.engine.get(), "api_key": self.api_key.get() if self.engine.get() == "cloud" else None}
        self.pending_sources.clear()
        self.refresh_queue()
        threading.Thread(target=self.worker_batch, args=(job, sources), daemon=True).start()

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
        c = self.palette()
        dlg = ctk.CTkToplevel(self.root)
        self.auth_dialog = dlg
        dlg.title(self.t("auth_title"))
        dlg.geometry("480x365")
        dlg.minsize(410, 340)
        dlg.transient(self.root)
        dlg.grab_set()
        panel = ctk.CTkFrame(dlg, fg_color="transparent")
        panel.pack(fill="both", expand=True, padx=20, pady=18)
        self.text(panel, self.t("auth_title"), 17, True).pack(anchor="w", pady=(0,8))
        self.text(panel, self.t("auth_explain"), 11, muted=True, wraplength=415,
                  justify="left").pack(anchor="w", pady=(0,13))
        installed = browser_candidates()
        choices = list(installed) + [self.t("samsung"), self.t("cookies")]
        choice = ctk.StringVar(value=choices[0])
        ctk.CTkOptionMenu(panel, variable=choice, values=choices, height=36,
            fg_color=c["inset"], button_color=c["inset"],
            dropdown_fg_color=c["panel"], text_color=c["fg"]).pack(fill="x")
        self.text(panel, self.t("browser_tip"), 10, muted=True,
                  wraplength=415, justify="left").pack(anchor="w", pady=(10,11))
        def resolve(result):
            self.auth_response = result
            self.auth_event.set()
            if dlg.winfo_exists():
                dlg.destroy()
            self.auth_dialog = None
        def confirm():
            key = choice.get()
            if key in installed:
                resolve(installed[key])
            else:
                path = filedialog.askopenfilename(parent=dlg,
                    filetypes=[("Netscape cookie file", "*.txt"), ("All files", "*.*")])
                if path:
                    resolve(("file", path))
        ctk.CTkCheckBox(panel, text=self.t("auth_remember"), variable=self.remember_auth,
            font=("Segoe UI", 10), checkbox_width=17, checkbox_height=17).pack(anchor="w", pady=(0,10))
        row = ctk.CTkFrame(panel, fg_color="transparent")
        row.pack(fill="x")
        ctk.CTkButton(row, text=self.t("auth_continue"), command=confirm,
                      fg_color=c["accent"], text_color=c["accent_text"]).pack(side="left", fill="x", expand=True)
        self.secondary_button(row, self.t("cancel"), lambda: resolve(None), 110).pack(side="left", padx=(8,0))
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
                result = dl.extract_info(url, download=True)
                return result if isinstance(result, dict) else {}
        self.log("DOWNLOAD_STARTED")
        self.send("status", self.t("downloading"))
        try:
            metadata = attempt()
        except DownloadError as exc:
            self.check_cancel()
            error = (str(exc) + " " + " ".join(logger.errors)).lower()
            if not any(token in error for token in AUTH_WORDS):
                self.log("DOWNLOAD_FAILED_NON_AUTH")
                raise RuntimeError("download_failed") from None
            self.log("AUTH_REQUIRED")
            cached = self.auth_cached_choice or (self.auth_saved if self.remember_auth.get() else None)
            if cached:
                try:
                    if cached[0] == "file" and not Path(cached[1]).is_file():
                        raise OSError("Cookie file missing")
                    extra = {"cookiefile": cached[1]} if cached[0] == "file" else {
                        "cookiesfrombrowser": (cached[1], cached[2]) if cached[2] else (cached[1],)}
                    metadata = attempt(extra)
                    self.check_cancel()
                    candidates = [p for p in folder.iterdir() if p.is_file() and p.suffix.lower() in EXTS]
                    if not candidates:
                        raise RuntimeError("no_media")
                    self.send("progress", 35)
                    return max(candidates, key=lambda p: p.stat().st_size), (metadata.get("title") or metadata.get("fulltitle"))
                except JobCancelled:
                    raise
                except Exception:
                    self.log("CACHED_AUTH_FAILED")
                    self.auth_cached_choice = None
                    self.auth_saved = None
            self.auth_response = None
            self.auth_event.clear()
            self.send("auth")
            self.auth_event.wait()
            self.check_cancel()
            if self.auth_response is None:
                raise JobCancelled()
            selection = self.auth_response
            self.auth_cached_choice = selection
            if self.remember_auth.get():
                self.auth_saved = list(selection)
                self.save_config()
            if selection[0] == "file":
                extra = {"cookiefile": selection[1]}
            else:
                extra = {"cookiesfrombrowser": (selection[1], selection[2]) if selection[2] else (selection[1],)}
            try:
                metadata = attempt(extra)
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
        title = metadata.get("title") or metadata.get("fulltitle")
        return max(candidates, key=lambda p: p.stat().st_size), title

    def transcribe(self, job, media, network_media):
        self.check_cancel()
        self.send("status", self.t("loading"))
        if self.model_instance is None or self.model_name != job["model"]:
            try:
                self.model_instance = WhisperModel(job["model"], device="cpu", compute_type="int8", cpu_threads=self.cpu_threads)
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

    def resolve_name(self, job, media, metadata_title=None):
        desired = job["name"] or metadata_title or media.stem
        # Avoid generic filenames used internally for Webex downloads.
        if not job["name"] and (not desired or desired.lower() in {"recording", "video", "hls"}):
            desired = "Webex_" + datetime.now().strftime("%Y%m%d_%H%M%S")
        base = clean_name(desired)
        folder, videos = job["transcripts"], job["videos"]
        name, num = base, 2
        while (any((folder / f"{name}{sfx}").exists() for sfx in (".txt", ".srt", ".md", ".partial.txt", ".partial.srt", ".partial.md"))
               or any((videos / f"{name}{ext}").exists() for ext in EXTS)):
            name = f"{base}_{num}"
            num += 1
        job["name"] = name

    def worker_batch(self, job, sources):
        failures = 0
        self.auth_cached_choice = None
        for index, source in enumerate(sources, start=1):
            if self.stop_event.is_set():
                self.send("cancelled")
                return
            current = dict(job)
            current["source"] = source
            if job["name"] and len(sources) > 1:
                current["name"] = f"{job['name']}_{index:02}"
            try:
                self.process_one(current)
                self.log("BATCH_ITEM_SUCCESS")
            except JobCancelled:
                self.send("cancelled")
                return
            except Exception:
                failures += 1
                self.log("BATCH_ITEM_FAILED")
            self.send("status", f"{index}/{len(sources)}")
        self.send("done_batch", (len(sources), failures, str(job['transcripts'])))

    def process_one(self, job):
        source = job["source"]
        if source.startswith(("http://", "https://")):
            with tempfile.TemporaryDirectory(prefix="lecturescribe_") as temp:
                media, title = self.download(source, Path(temp))
                self.resolve_name(job, media, title)
                self.transcribe_engine(job, media, True)
                if job["keep"]:
                    self.check_cancel()
                    self.send("status", self.t("video_copy"))
                    shutil.copy2(media, job["videos"] / (job["name"] + media.suffix))
        else:
            media = Path(source)
            if not media.is_file():
                raise RuntimeError("notfound")
            self.resolve_name(job, media)
            self.transcribe_engine(job, media, False)

    def transcribe_engine(self, job, media, network_media):
        if job["engine"] != "cloud":
            txt_path, srt_path = self.transcribe(job, media, network_media)
            self.write_markdown(txt_path, job["name"])
            return
        self.send("status", self.t("transcribing"))
        folder = job["transcripts"]
        txt = folder / (job["name"] + ".txt")
        md = folder / (job["name"] + ".md")
        completed = False
        try:
            def progress(p):
                base, span = (35, 65) if network_media else (0, 100)
                self.send("progress", base + span * p / 100)
            try:
                lines = cloud_transcribe(media, job["api_key"], job["spoken"],
                                         progress, self.stop_event.is_set)
            except InterruptedError:
                raise JobCancelled()
            self.check_cancel()
            txt.write_text("\n".join(lines) + "\n", encoding="utf-8")
            md.write_text("# " + job["name"] + "\n\n> " + self.t("cloud_result") + "\n\n" +
                          "\n\n".join(lines) + "\n", encoding="utf-8")
            completed = True
        finally:
            if not completed:
                for path in (txt, md):
                    if path.exists():
                        path.rename(path.with_name(path.stem + ".partial" + path.suffix))

    def write_markdown(self, txt_path, title):
        content = txt_path.read_text(encoding="utf-8")
        (txt_path.parent / (title + ".md")).write_text(
            "# " + title + "\n\n" + content.replace("\n", "\n\n"), encoding="utf-8")

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
    if len(sys.argv) >= 2 and sys.argv[1] == "--apply-update":
        sys.exit(run_update_mode(sys.argv[2:]))
    root = ctk.CTk()
    App(root)
    root.mainloop()
