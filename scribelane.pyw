"""ScribeLane — local lecture transcription GUI for Windows."""
from __future__ import annotations

import json
from contextlib import ExitStack
from urllib.parse import urlsplit
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from types import SimpleNamespace
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

import imageio_ffmpeg
import yt_dlp
from faster_whisper import WhisperModel
from yt_dlp.utils import DownloadError
from scribelane_credentials import Vault
from scribelane_webex import WebexBrowserError, capture_playlist, is_webex_playback
from scribelane_openvino import (
    OpenVINOUnavailable, prepare_parallel, transcribe_if_available, transcribe_on_device,
)
from scribelane_providers import MODELS, verify_key, transcribe_long, ProviderError, available_gemini_models
from scribelane_updates import VERSION, fetch_release, stage_update, launch_installer, version_tuple, run_update_mode
try:
    from scribelane_build import REPO as BUILT_REPO
except ImportError:
    BUILT_REPO = ""
OFFICIAL_REPO = "FabioSantagostino/ScribeLane"

APP = "ScribeLane"
CONFIG_DIR = Path(os.getenv("APPDATA", str(Path.home()))) / APP
CONFIG_FILE = CONFIG_DIR / "settings.json"
OV_MODELS = CONFIG_DIR / "openvino_models"
OV_BENCH = CONFIG_DIR / "openvino_benchmarks"
DEFAULT_DIR = Path.home() / "Documents" / APP
EXTS = {".mp4", ".mkv", ".webm", ".mov", ".mp3", ".m4a", ".wav", ".flac", ".aac"}
OUTPUT_FORMATS = ("txt", "md", "srt")
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


I18N = {
 "it": {
  "tagline":"Trascrizione locale di lezioni e registrazioni", "source":"Link Webex, URL HLS o file audio/video", "browse":"Sfoglia", "title":"Nome della lezione", "transcripts":"Cartella trascrizioni", "videos":"Cartella video conservati", "choose":"Scegli", "keep":"Conserva il video scaricato", "safety":"I file locali originali non vengono mai eliminati automaticamente.", "model":"Modello Whisper", "speech":"Lingua del parlato", "automatic":"Rilevamento automatico", "italian":"Italiano", "english":"Inglese", "theme":"Tema", "dark":"Scuro", "light":"Chiaro", "lang":"Interfaccia", "start":"Avvia trascrizione", "stop":"Interrompi", "open":"Apri trascrizioni", "progress":"Avanzamento", "ready":"Pronto", "preparing":"Preparazione...", "downloading":"Download in corso...", "loading":"Caricamento del modello (primo avvio: download)...", "transcribing":"Trascrizione", "finished":"Trascrizione completata", "stopped":"Operazione interrotta. Le eventuali trascrizioni parziali sono state conservate.", "error":"Errore", "missing":"Inserisci un URL o seleziona un file.", "notfound":"File non trovato.", "cancel":"Annulla", "download_failed":"Download fallito. Controlla il link e la connessione. Per un URL HLS scaduto, recuperane uno nuovo.", "processing_failed":"Errore nell'elaborazione. Consulta il log diagnostico locale (senza URL o cookie).", "close_running":"L'elaborazione è in corso. Vuoi interromperla e chiudere al termine dell'interruzione?", "model_tip":"Turbo: equilibrio consigliato. Large-v3: più lento. I modelli .en sono solo per inglese.", "output_saved":"File salvati in:", "logs":"Apri cartella log", "model_error":"Modello non disponibile oppure download fallito.", "select_folder":"Seleziona cartella", "permission":"Impossibile scrivere nella cartella di destinazione.", "video_copy":"Conservazione del video...", "bad_source":"Sono supportati file locali e URL http(s).", "no_media":"Il download non ha prodotto un file multimediale.", "privacy":"Trascrizione locale · nessun audio inviato a servizi AI", "duplicate":"Nome già in uso: scelto un nome alternativo.", "model_warn":"Questo modello .en riconosce soltanto l'inglese. Continuare?", "yes":"Sì", "no":"No"
 },
 "en": {
  "tagline":"Local transcription of lectures and recordings", "source":"Webex link, HLS URL or local media", "browse":"Browse", "title":"Lecture name", "transcripts":"Transcripts folder", "videos":"Retained videos folder", "choose":"Choose", "keep":"Keep downloaded video", "safety":"Original local media files are never automatically deleted.", "model":"Whisper model", "speech":"Spoken language", "automatic":"Auto-detect", "italian":"Italian", "english":"English", "theme":"Theme", "dark":"Dark", "light":"Light", "lang":"Interface", "start":"Start transcription", "stop":"Cancel", "open":"Open transcripts", "progress":"Progress", "ready":"Ready", "preparing":"Preparing...", "downloading":"Downloading...", "loading":"Loading model (first run downloads it)...", "transcribing":"Transcribing", "finished":"Transcription completed", "stopped":"Cancelled. Any partial transcripts were retained.", "error":"Error", "missing":"Enter a URL or select a file.", "notfound":"File not found.", "cancel":"Cancel", "download_failed":"Download failed. Check the link and connection. Refresh expired HLS URLs.", "processing_failed":"Processing failed. See the local diagnostics log (no URLs or cookies).", "close_running":"A job is running. Cancel and close once it has stopped?", "model_tip":"Turbo: recommended balance. Large-v3: slower. .en models are English-only.", "output_saved":"Files saved in:", "logs":"Open logs folder", "model_error":"Model unavailable or model download failed.", "select_folder":"Choose folder", "permission":"Cannot write to output folder.", "video_copy":"Saving downloaded video...", "bad_source":"Local media and http(s) URLs are supported.", "no_media":"The download did not produce a media file.", "privacy":"Local transcription · no audio uploaded to AI services", "duplicate":"Name already used; selected an alternate name.", "model_warn":"This .en model only recognizes English. Continue?", "yes":"Yes", "no":"No"
 }
}

I18N["it"].update({'step_source': '01  Scegli la registrazione', 'step_source_help': 'Inserisci un collegamento Webex oppure seleziona un file dal PC.', 'original_filename_hint': 'Per impostazione predefinita useremo il titolo originale della registrazione.', 'custom_name': 'Usa un nome personalizzato', 'step_settings': '02  Qualità e lingua', 'step_settings_help': 'Solo due scelte. La variante del modello si adatta automaticamente alla lingua.', 'quality': 'Qualità della trascrizione', 'quality_fast': '⚡ Veloce', 'quality_balanced': '✦ Bilanciata (consigliata)', 'quality_accurate': '◎ Massima qualità', 'spoken_auto': 'Rileva automaticamente', 'spoken_it': 'Italiano', 'spoken_en': 'Inglese', 'quality_help': 'Veloce: Small (Small.en per inglese). Bilanciata: Turbo. Massima: Large-v3. Turbo e Large-v3 sono già multilingue.', 'advanced': 'Opzioni avanzate e salvataggio', 'step_run': '03  Avvia', 'keep_disabled': 'Il video scaricato verrà eliminato dopo la trascrizione.', 'keep_enabled': 'Il video scaricato verrà conservato nella cartella scelta.', 'title_missing': 'Inserisci un nome personalizzato oppure deseleziona la relativa casella.'})
I18N["en"].update({'step_source': '01  Choose recording', 'step_source_help': 'Paste a Webex link or choose a local media file.', 'original_filename_hint': "The recording's original title is used automatically.", 'custom_name': 'Use a custom lecture name', 'step_settings': '02  Quality & language', 'step_settings_help': 'Just two choices. The model variant adapts automatically to the spoken language.', 'quality': 'Transcription quality', 'quality_fast': '⚡ Fast', 'quality_balanced': '✦ Balanced (recommended)', 'quality_accurate': '◎ Highest quality', 'spoken_auto': 'Detect automatically', 'spoken_it': 'Italian', 'spoken_en': 'English', 'quality_help': 'Fast: Small (Small.en for English). Balanced: Turbo. Highest: Large-v3. Turbo and Large-v3 are already multilingual.', 'advanced': 'Advanced options & files', 'step_run': '03  Start', 'keep_disabled': 'Downloaded video is deleted after transcription.', 'keep_enabled': 'Downloaded video is retained in your selected folder.', 'title_missing': 'Enter a custom name or uncheck the custom name option.'})


I18N["it"].update({
 "queue":"Coda di trascrizione", "add_files":"+ File", "add_link":"+ Link", "clear_queue":"Svuota", "queue_empty":"Nessun elemento in coda", "queue_count":"Elementi in coda", "link_prompt":"Incolla il link Webex / HLS", "backend":"Motore di trascrizione", "local_engine":"Locale · Whisper", "cloud_engine":"Cloud · OpenAI API", "api_key":"Chiave API OpenAI (solo per questa sessione)", "cloud_warning":"Modalità cloud: l'audio sarà inviato a OpenAI. Richiede chiave API e può avere costi. I timestamp sono approssimativi (blocchi), nessun SRT cloud.", "updates":"Aggiornamenti", "update_repo":"Repository GitHub (owner/repo)", "check_update":"Cerca aggiornamenti", "update_found":"Nuova versione disponibile", "no_update":"Hai già l'ultima versione", "install_update":"Scaricare e installare l'aggiornamento? L'app verrà riavviata.", "update_error":"Aggiornamento non riuscito. Controlla repository e connessione.", "cloud_confirm":"La registrazione audio sarà caricata su OpenAI e potrebbe essere fatturata. Continuare?", "cloud_key_missing":"Inserisci la chiave API per il servizio cloud.", "cloud_result":"I tempi della trascrizione cloud indicano blocchi audio approssimativi.", "batch_finished":"Elaborazione della coda completata", "batch_failed":"Alcune registrazioni non sono state elaborate. Vedi log diagnostici."})
I18N["en"].update({
 "queue":"Transcription queue", "add_files":"+ Files", "add_link":"+ Link", "clear_queue":"Clear", "queue_empty":"No queued items", "queue_count":"Queued items", "link_prompt":"Paste Webex / HLS URL", "backend":"Transcription engine", "local_engine":"Local · Whisper", "cloud_engine":"Cloud · OpenAI API", "api_key":"OpenAI API key (session only)", "cloud_warning":"Cloud mode sends audio to OpenAI. Requires a billed API key. Timestamps are approximate chunk markers, no cloud SRT.", "updates":"Updates", "update_repo":"GitHub repository (owner/repo)", "check_update":"Check for updates", "update_found":"A new version is available", "no_update":"You're up to date", "install_update":"Download and install the update? The app will restart.", "update_error":"Update failed. Check repository and connection.", "cloud_confirm":"Audio will be uploaded to OpenAI and may incur charges. Continue?", "cloud_key_missing":"Enter your cloud API key.", "cloud_result":"Cloud timestamps refer to approximate audio chunks.", "batch_finished":"Queue finished", "batch_failed":"Some recordings failed. See diagnostics."})

WEBEX_ERRORS = {"webex_extension_missing", "webex_capture_failed", "webex_browser_failed"}
I18N['it'].update({
    'webex_setup': 'Browser per Webex',
    'ov_model': 'Download del modello OpenVINO…',
    'ov_benchmark': 'Verifica dei dispositivi OpenVINO…',
    'ov_retry_gpu': 'NPU: cache esaurita. Nuovo tentativo su OpenVINO GPU…',
    'webex_setup_help': 'Scegli il browser predefinito di Windows. ScribeLane lo usa solo se il download diretto fallisce.',
    'webex_chromium_help': 'Se un link Webex richiede il browser, puoi usare l’estensione Chromium inclusa. Vedi il README.',
    'webex_firefox_help': 'Se un link Webex richiede il browser, puoi caricare l’estensione da about:debugging.',
    'webex_other': 'Altri browser Chromium',
    'webex_save': 'Salva browser',
    'webex_connect': 'Apertura del browser predefinito…',
    'webex_wait': 'Avvia il video nella scheda Webex per rilevare la playlist…',
    'webex_extension_missing': 'yt-dlp non ha scaricato questo link Webex direttamente. Per riprovare, attiva l’estensione nel browser predefinito o incolla un link HLS valido.',
    'webex_capture_failed': 'Playlist non rilevata. Verifica che il video Webex parta, oppure incolla il link HLS diretto.',
    'webex_browser_failed': 'Impossibile aprire il browser predefinito.',
})
I18N['en'].update({
    'webex_setup': 'Webex browser',
    'ov_model': 'Downloading the OpenVINO model…',
    'ov_benchmark': 'Checking OpenVINO devices…',
    'ov_retry_gpu': 'NPU cache is full. Retrying with OpenVINO GPU…',
    'webex_setup_help': 'Select your Windows default browser. ScribeLane uses it only if direct download fails.',
    'webex_chromium_help': 'If a Webex link needs the browser, use the included Chromium extension. See the README.',
    'webex_firefox_help': 'If a Webex link needs the browser, load the extension from about:debugging.',
    'webex_other': 'Other Chromium browsers',
    'webex_save': 'Save browser',
    'webex_connect': 'Opening the default browser…',
    'webex_wait': 'Start the video in the Webex tab to detect the playlist…',
    'webex_extension_missing': 'yt-dlp could not download this Webex link directly. Enable the extension in the default browser or paste a valid HLS URL.',
    'webex_capture_failed': 'Playlist not detected. Make sure the Webex video plays, or paste a direct HLS link.',
    'webex_browser_failed': 'Could not open the default browser.',
})


class JobCancelled(Exception):
    pass


I18N['it'].update({
    'workspace': 'Trascrivi',
    'preferences': 'Impostazioni',
    'appearance': 'Aspetto e lingua dell’app',
    'output_settings': 'File e cartelle',
    'formats': 'Formati della trascrizione',
    'formats_help': 'Seleziona uno o più formati. Per le trascrizioni cloud, SRT usa tempi approssimativi per blocco.',
    'connections': 'Webex e aggiornamenti',
    'source_hint': 'Incolla un link Webex o HLS, oppure sfoglia i file sul PC.',
    'step_source': 'Registrazione o coda',
    'step_settings': 'Motore, qualità e lingua del parlato',
    'step_run': 'Stato della trascrizione',
    'tagline': 'Trascrizioni da audio, video e Webex',
    'cloud_engine': 'Cloud · API',
    'cloud_confirm': 'L’audio verrà inviato al provider selezionato e il servizio potrebbe addebitare costi. Continuare?',
    'bulk_title': 'Modifica la coda',
    'bulk_button': 'Incolla link…',
    'bulk_help': 'Una registrazione per riga. Puoi incollare tutti i link insieme o usare Nome | link per assegnare un titolo. Per rimuovere un elemento, cancella la sua riga.',
    'bulk_invalid': 'Controlla il link o il file alla riga {line}.',
    'bulk_save': 'Salva coda',
})
I18N['en'].update({
    'workspace': 'Transcribe',
    'preferences': 'Settings',
    'appearance': 'Appearance and app language',
    'output_settings': 'Files and folders',
    'formats': 'Transcript formats',
    'formats_help': 'Select one or more formats. Cloud SRT uses approximate times for each audio chunk.',
    'connections': 'Webex and updates',
    'source_hint': 'Paste a Webex or HLS link, or browse for a file.',
    'step_source': 'Recording or queue',
    'step_settings': 'Engine, quality and spoken language',
    'step_run': 'Transcription status',
    'tagline': 'Transcripts from audio, video and Webex',
    'cloud_engine': 'Cloud · API',
    'cloud_confirm': 'Audio will be sent to the selected provider and charges may apply. Continue?',
    'bulk_title': 'Edit the queue',
    'bulk_button': 'Paste links…',
    'bulk_help': 'One recording per line. Paste all links at once or use Name | link to assign a title. Delete a line to remove its recording.',
    'bulk_invalid': 'Check the link or file on line {line}.',
    'bulk_save': 'Save queue',
})


def millis(seconds: float, srt: bool = False) -> str:
    value = max(0, round(seconds * 1000))
    h, rem = divmod(value, 3_600_000)
    m, rem = divmod(rem, 60_000)
    sec, ms = divmod(rem, 1000)
    return f"{h:02}:{m:02}:{sec:02}{',' if srt else '.'}{ms:03}"


def clean_name(name: str) -> str:
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name).strip(" .")
    return name[:90] or datetime.now().strftime("Lecture_%Y%m%d_%H%M%S")


def ensure_writable(folder: Path):
    folder.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryFile(dir=folder):
        pass


class PrivateLogger:
    """Discard downloader messages that may contain signed URLs."""
    def debug(self, msg):
        pass

    warning = error = debug


def parse_queue(text):
    sources = {}
    for index, line in enumerate(text.splitlines(), start=1):
        line = line.strip()
        if not line:
            continue
        title, source = "", line
        if not line.startswith(("https://", "http://")) and "|" in line:
            title, source = (part.strip() for part in line.split("|", 1))
        source = source.strip('"')
        try:
            url = urlsplit(source)
            valid = ((url.scheme in ("https", "http") and bool(url.hostname)
                      and not any(c.isspace() for c in source))
                     if source.startswith(("https://", "http://"))
                     else bool(source) and Path(source).is_file())
        except (ValueError, OSError):
            valid = False
        if not valid:
            raise ValueError(index)
        if title or source not in sources:
            sources[source] = {"source": source, "name": title or None}
    return list(sources.values())


class App:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.queue = Queue()
        self.stop_event = threading.Event()
        self.running = False
        self.close_when_done = False
        self.model_instance = None
        self.model_name = None
        self.pending_sources = []  # {source, name} per item
        self.vault = Vault(CONFIG_DIR / "api_keys.json")
        config = self.load_config()
        self.cloud_provider = tk.StringVar(value=config.get("cloud_provider", "groq"))
        self.cloud_model = tk.StringVar(value=config.get("cloud_model", "whisper-large-v3-turbo"))
        self.cloud_key_id = tk.StringVar(value=config.get("cloud_key_id", ""))
        self.update_asset = None
        self.update_temp = None
        self.ui_language = tk.StringVar(value=config.get("ui_language", "it"))
        self.ui_theme = tk.StringVar(value=config.get("theme", "auto"))
        self.source = tk.StringVar(value="")
        self.lecture = tk.StringVar(value="")
        self.custom_name = tk.BooleanVar(value=False)
        self.current_page = "workspace"
        stored_formats = config.get("formats")
        selected = {fmt for fmt in OUTPUT_FORMATS if fmt in (stored_formats if isinstance(stored_formats, list) else [])}
        self.formats = {fmt: tk.BooleanVar(value=fmt in selected or not selected)
                        for fmt in OUTPUT_FORMATS}
        self.transcripts_dir = tk.StringVar(value=config.get("transcripts", str(DEFAULT_DIR / "Trascrizioni")))
        self.videos_dir = tk.StringVar(value=config.get("videos", str(DEFAULT_DIR / "Video")))
        self.keep_video = tk.BooleanVar(value=config.get("keep_video", False))
        self.model = tk.StringVar(value=config.get("quality", "balanced") if config.get("quality", "balanced") in QUALITY_CHOICES else "balanced")
        self.spoken = tk.StringVar(value=config.get("spoken", "auto"))
        self.engine = tk.StringVar(value=config.get("engine", "local"))
        self.api_key = tk.StringVar(value="")  # Session-only, never stored or logged.
        saved_browser = config.get("webex_browser", "")
        self.webex_browser = saved_browser
        if saved_browser and saved_browser not in ("Chrome", "Edge", "Brave", "Firefox"):
            self.webex_browser = "chromium"
        self.cpu_threads = config.get("cpu_threads", min(8, os.cpu_count() or 8))
        self.update_repo = tk.StringVar(value=OFFICIAL_REPO)
        self.status = tk.StringVar(value=I18N[self.ui_language.get()]["ready"])
        self.progress_value = 0.0
        self._phase = 0
        self._system_dark = windows_dark_mode()
        self._wheel_remainder = 0.0
        self._last_palette = None
        self.scroll_area = None
        self.main = None
        root.title("ScribeLane")
        root.geometry("800x680")
        root.minsize(590, 495)
        self.apply_theme()
        self.rebuild()
        self._rendered_language = self.ui_language.get()
        if not self.webex_browser:
            root.after(250, self.browser_setup)
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
            "webex_browser": self.webex_browser,
            "formats": [fmt for fmt, enabled in self.formats.items() if enabled.get()],
            "cpu_threads": self.cpu_threads,
            "engine": self.engine.get(), "cloud_provider":self.cloud_provider.get(),
            "cloud_model":self.cloud_model.get(), "cloud_key_id":self.cloud_key_id.get(),
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
            return dict(bg="#10141e", panel="#192232", inset="#233148",
                        fg="#f5f7fb", muted="#a0aaba", line="#2e3646",
                        accent="#80dac6", accent_text="#0d302d", hover="#30425d")
        return dict(bg="#f1f4f9", panel="#ffffff", inset="#e8eef8",
                    fg="#1b2433", muted="#647084", line="#e3e8f0",
                    accent="#135e62", accent_text="#ffffff", hover="#d9e3f3")

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
        """Pixel-based Windows touchpad scrolling; never rebuild the content."""
        if self.scroll_area is None or event.widget.winfo_toplevel() != self.root:
            return None
        delta = getattr(event, "delta", 0)
        if not delta:
            return None
        canvas = self.scroll_area._parent_canvas
        region = canvas.bbox("all")
        if not region:
            return None
        scrollable = max(0, region[3] - canvas.winfo_height())
        if not scrollable:
            return None
        # Precision touchpads can emit dozens of tiny deltas. Scroll in
        # pixels rather than Tk units, which are very small on high-DPI PCs.
        pixels = min(220.0, max(12.0, abs(delta) * 1.25))
        pos = canvas.yview()[0] * scrollable
        pos -= pixels if delta > 0 else -pixels
        canvas.yview_moveto(max(0.0, min(1.0, pos / scrollable)))
        return "break"

    def cloud_manage_popup(self):
        """Manage provider credentials without orphaned StringVar entry callbacks."""
        c = self.palette()
        it = self.ui_language.get() == "it"
        t = (lambda a, b: a if it else b)
        dlg = ctk.CTkToplevel(self.root)
        dlg.title(t("Provider AI e chiavi API", "AI providers and API keys"))
        dlg.geometry("740x600")
        dlg.minsize(630, 470)
        dlg.transient(self.root)
        dlg.grid_columnconfigure(0, weight=1)
        dlg.grid_rowconfigure(0, weight=1)

        # This dialog intentionally does not bind CTkEntry widgets to Tk
        # StringVar objects: callback traces may outlive destroyed widgets.
        outer = ctk.CTkFrame(dlg, fg_color=c["bg"], corner_radius=0)
        outer.grid(row=0, column=0, sticky="nsew", padx=15, pady=12)
        outer.grid_columnconfigure(0, weight=1)
        outer.grid_rowconfigure(1, weight=1)

        form = ctk.CTkFrame(outer, corner_radius=12)
        form.grid(row=0, column=0, sticky="ew", pady=(0, 12))
        form.grid_columnconfigure(0, weight=1)
        self.text(form, t("Aggiungi una chiave API", "Add an API key"), 17, True).grid(
            row=0, column=0, sticky="w", padx=16, pady=(14, 3))
        self.text(form, t("Le chiavi vengono conservate nell'archivio credenziali di Windows.",
                          "Keys are stored in Windows Credential Manager."), 11, muted=True).grid(
            row=1, column=0, sticky="w", padx=16, pady=(0, 9))

        self.text(form, t("Provider", "Provider"), 12, True).grid(
            row=2, column=0, sticky="w", padx=16)
        provider_box = ctk.CTkOptionMenu(form, values=list(MODELS))
        provider_box.grid(row=3, column=0, sticky="ew", padx=16, pady=(4, 10))
        if self.cloud_provider.get() in MODELS:
            provider_box.set(self.cloud_provider.get())

        self.text(form, t("Nome identificativo", "Key label"), 12, True).grid(
            row=4, column=0, sticky="w", padx=16)
        label_entry = ctk.CTkEntry(form, height=35)
        label_entry.grid(row=5, column=0, sticky="ew", padx=16, pady=(4, 10))

        self.text(form, t("Chiave API segreta", "Secret API key"), 12, True).grid(
            row=6, column=0, sticky="w", padx=16)
        secret_entry = ctk.CTkEntry(form, height=35, show="•")
        secret_entry.grid(row=7, column=0, sticky="ew", padx=16, pady=(4, 10))

        listing_box = ctk.CTkFrame(outer, corner_radius=12)
        listing_box.grid(row=1, column=0, sticky="nsew", pady=(0, 4))
        listing_box.grid_columnconfigure(0, weight=1)
        listing_box.grid_rowconfigure(1, weight=1)
        self.text(listing_box, t("Chiavi salvate", "Saved keys"), 15, True).grid(
            row=0, column=0, sticky="w", padx=14, pady=(12, 5))
        listing = ctk.CTkScrollableFrame(listing_box, fg_color="transparent")
        listing.grid(row=1, column=0, sticky="nsew", padx=8, pady=(0, 10))

        def reload():
            for widget in listing.winfo_children():
                widget.destroy()
            if not self.vault.items:
                self.text(listing, t("Nessuna chiave salvata", "No saved keys"),
                          11, muted=True).pack(anchor="w", padx=8, pady=10)
                return
            for entry in list(self.vault.items):
                row = ctk.CTkFrame(listing, fg_color="transparent")
                row.pack(fill="x", pady=3)
                row.grid_columnconfigure(0, weight=1)
                state = t("Attiva", "Enabled") if entry['enabled'] else t("Disattivata", "Disabled")
                self.text(row, f"{entry['provider']} · {entry['name']} · {state}", 11).grid(
                    row=0, column=0, sticky="w", padx=(5, 6))
                def action(fn, item=entry):
                    try:
                        fn(item)
                    except Exception:
                        messagebox.showerror(APP, t("Operazione sulle credenziali non riuscita",
                                                    "Credential operation failed"), parent=dlg)
                    reload()
                def use(item=entry):
                    self.cloud_provider.set(item['provider'])
                    self.cloud_key_id.set(item['id'])
                    self.cloud_model.set(MODELS[item['provider']][0])
                    self.save_config()
                    dlg.destroy()
                    self.root.after_idle(self.rebuild)
                buttons = [
                    (t("Usa", "Use"), use),
                    ("On/Off", lambda item=entry: action(lambda x: self.vault.edit(
                        x['id'], enabled=not x['enabled']), item)),
                    (t("Modifica", "Edit"), lambda item=entry: edit_key(item)),
                    ("Test", lambda item=entry: test_key(item)),
                    (t("Elimina", "Delete"), lambda item=entry: remove_key(item)),
                ]
                for i, (caption, command) in enumerate(buttons, 1):
                    self.secondary_button(row, caption, command,
                                          57 if i != 3 else 67).grid(row=0, column=i, padx=2)

        def edit_key(item):
            from tkinter import simpledialog
            new_name = simpledialog.askstring(APP, t("Nuovo nome (vuoto = invariato)",
                                                    "New label (blank = unchanged)"), parent=dlg)
            if new_name:
                self.vault.edit(item['id'], name=new_name)
            new_secret = simpledialog.askstring(APP, t("Sostituisci chiave (vuoto = invariato)",
                                                      "Replace key (blank = unchanged)"),
                                                parent=dlg, show="*")
            if new_secret:
                self.vault.edit(item['id'], secret=new_secret)
            reload()

        def remove_key(item):
            if messagebox.askyesno(APP, t("Eliminare definitivamente questa chiave?",
                                         "Permanently delete this key?"), parent=dlg):
                self.vault.delete(item['id'])
                if self.cloud_key_id.get() == item['id']:
                    self.cloud_key_id.set("")
                reload()

        def test_key(item):
            key = self.vault.get_secret(item['id'])
            if not key:
                messagebox.showwarning(APP, t("Credenziale non accessibile", "Credential inaccessible"),
                                       parent=dlg)
                return
            def background():
                try:
                    verify_key(item['provider'], key)
                    result = t("Autenticazione riuscita. Quota non verificata.",
                               "Authenticated. Quota not checked.")
                except ProviderError as err:
                    result = f"Test failed: {err.category}"
                except Exception:
                    result = t("Test di connessione non riuscito", "Connection test failed")
                def notify():
                    if dlg.winfo_exists():
                        messagebox.showinfo(APP, result, parent=dlg)
                try:
                    self.root.after(0, notify)
                except RuntimeError:
                    pass
            threading.Thread(target=background, daemon=True).start()

        def add_key():
            provider = provider_box.get()
            name = label_entry.get().strip()
            secret = secret_entry.get().strip()
            if not name or not secret:
                messagebox.showwarning(APP, t("Inserisci nome e chiave API.",
                                             "Enter a label and API key."), parent=dlg)
                return
            try:
                self.vault.add(provider, name, secret)
            except Exception:
                messagebox.showerror(APP, t("Salvataggio nel gestore credenziali fallito",
                                            "Could not save to Credential Manager"), parent=dlg)
                return
            # Clear entry widgets directly, without StringVar traces.
            secret_entry.delete(0, "end")
            label_entry.delete(0, "end")
            reload()

        ctk.CTkButton(form, text=t("+ Aggiungi chiave", "+ Add key"),
                      command=add_key).grid(row=8, column=0, sticky="ew",
                                            padx=16, pady=(3, 15))
        reload()
        dlg.after(100, dlg.lift)

    def cloud_change_provider(self,value):
        self.cloud_provider.set(value)
        self.cloud_model.set(MODELS[value][0])
        self.save_config()
        self.refresh_cloud_options()

    def queue_editor(self):
        if self.running:
            return
        c = self.palette()
        dlg = ctk.CTkToplevel(self.root)
        dlg.title(self.t("bulk_title"))
        dlg.geometry("690x470")
        dlg.minsize(480, 330)
        dlg.transient(self.root)
        dlg.grab_set()
        self.text(dlg, self.t("bulk_title"), 20, True).pack(anchor="w", padx=20, pady=(18, 4))
        self.text(dlg, self.t("bulk_help"), 12, muted=True, wraplength=455,
                  justify="left").pack(anchor="w", padx=20, pady=(0, 10))
        editor = ctk.CTkTextbox(dlg, wrap="none", fg_color=c["inset"], corner_radius=11,
                                border_width=1, border_color=c["line"], font=("Consolas", 13))
        editor.pack(fill="both", expand=True, padx=20)
        for item in self.pending_sources:
            prefix = f"{item['name']} | " if item.get("name") else ""
            editor.insert("end", prefix + item["source"] + "\n")
        editor.mark_set("insert", "end-1c")
        editor.see("insert")
        row = ctk.CTkFrame(dlg, fg_color="transparent")
        row.pack(fill="x", padx=20, pady=14)
        error = self.text(row, "", 11, muted=True, justify="left", wraplength=230)
        error.pack(side="left", fill="x")

        def save():
            try:
                items = parse_queue(editor.get("1.0", "end-1c"))
            except ValueError as exc:
                line = exc.args[0]
                error.configure(text=self.t("bulk_invalid").format(line=line))
                editor.mark_set("insert", f"{line}.0")
                editor.see("insert")
                editor.focus_set()
                return
            self.pending_sources = items
            self.refresh_queue()
            dlg.destroy()

        ctk.CTkButton(row, text=self.t("bulk_save"), command=save, height=36,
                      fg_color=c["accent"], text_color=c["accent_text"]).pack(side="right")
        self.secondary_button(row, self.t("cancel"), dlg.destroy).pack(side="right", padx=8)
        dlg.bind("<Escape>", lambda _: dlg.destroy())
        dlg.after(50, editor.focus_set)

    def rebuild(self):
        c = self.palette()
        self.apply_theme()
        self._last_palette = c.copy()

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
        self.main.pack(fill="x", expand=True, padx=22, pady=16)

        header = ctk.CTkFrame(self.main, fg_color="transparent")
        header.pack(fill="x", pady=(0, 11))
        branding = ctk.CTkFrame(header, fg_color="transparent")
        branding.pack(side="left", fill="x", expand=True)
        self.text(branding, "ScribeLane", 26, True).pack(anchor="w")
        self.text(branding, self.t("tagline"), 11, muted=True).pack(anchor="w")
        tools = ctk.CTkFrame(header, fg_color="transparent")
        tools.pack(side="right")
        self.workspace_tab = self.secondary_button(tools, self.t("workspace"), lambda: self.show_page("workspace"), 120)
        self.workspace_tab.pack(side="left", padx=(0, 6))
        self.settings_tab = self.secondary_button(tools, self.t("preferences"), lambda: self.show_page("settings"), 120)
        self.settings_tab.pack(side="left")
        self.workspace_page = ctk.CTkFrame(self.main, fg_color="transparent")
        self.settings_page = ctk.CTkFrame(self.main, fg_color="transparent")

        source_card = self.panel(self.workspace_page)
        self.text(source_card, self.t("step_source"), 14, True).pack(anchor="w", padx=15, pady=(12, 2))
        self.text(source_card, self.t("source_hint"), 12, muted=True).pack(anchor="w", padx=15)
        self.choose_input(source_card, self.source, self.browse_file, self.t("browse"))
        queue_controls = ctk.CTkFrame(source_card, fg_color="transparent")
        queue_controls.pack(fill="x", padx=15, pady=(8, 0))
        self.text(queue_controls, self.t("queue"), 11, True).pack(side="left", padx=(0, 8))
        self.secondary_button(queue_controls, self.t("add_files"), self.enqueue_files, 66).pack(side="left", padx=(0, 5))
        self.secondary_button(queue_controls, self.t("bulk_button"), self.queue_editor, 138).pack(side="left", padx=(0, 5))
        self.secondary_button(queue_controls, self.t("clear_queue"), self.clear_queue, 76).pack(side="left")
        self.queue_label = self.text(source_card, "", 10, muted=True, wraplength=580, justify="left")
        self.queue_label.pack(anchor="w", padx=15, pady=(4, 2))
        self.refresh_queue()
        ctk.CTkCheckBox(source_card, text=self.t("custom_name"), variable=self.custom_name,
            command=self.toggle_custom_name, checkbox_width=17, checkbox_height=17,
            font=("Segoe UI", 11), text_color=c["fg"],
            fg_color=c["accent"], hover_color=c["accent"]).pack(anchor="w", padx=15, pady=(9, 12))
        self.custom_row = ctk.CTkFrame(source_card, fg_color="transparent")
        if self.custom_name.get():
            self.custom_row.pack(fill="x", padx=15, pady=(0, 12))
        ctk.CTkEntry(self.custom_row, textvariable=self.lecture, height=34,
                     fg_color=c["inset"], border_width=0).pack(fill="x")

        appearance = self.panel(self.settings_page)
        self.text(appearance, self.t("appearance"), 16, True).pack(anchor="w", padx=15, pady=(12, 5))
        preferences_row = ctk.CTkFrame(appearance, fg_color="transparent")
        preferences_row.pack(anchor="w", padx=15, pady=(0, 12))
        self.language_button = self.secondary_button(preferences_row, "English" if self.ui_language.get() == "it" else "Italiano",
                                                     self.toggle_language, 105)
        self.language_button.pack(side="left", padx=(0, 8))
        self.theme_button = self.secondary_button(preferences_row, self.theme_icon(), self.cycle_theme, 112)
        self.theme_button.pack(side="left")

        settings_card = self.panel(self.settings_page)
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
        self.engine_combo = ctk.CTkOptionMenu(mode_row, values=list(engine_labels), height=32,
            fg_color=c["inset"], button_color=c["inset"], text_color=c["fg"],
            dropdown_fg_color=c["panel"], dropdown_text_color=c["fg"],
            command=lambda value: self.set_engine("cloud" if value == self.t("cloud_engine") else "local"))
        self.engine_combo.pack(fill="x")
        self.engine_combo.set(self.t("cloud_engine") if self.engine.get() == "cloud" else self.t("local_engine"))
        # Cloud fields are created once and toggled via pack/pack_forget.
        self.cloud_fields = ctk.CTkFrame(mode_row, fg_color="transparent")
        self.cloud_title = self.text(self.cloud_fields, "Provider AI" if self.ui_language.get()=="it" else "AI provider", 10)
        self.cloud_title.pack(anchor="w", pady=(8, 3))
        self.cloud_provider_combo = ctk.CTkOptionMenu(
            self.cloud_fields, values=list(MODELS), command=self.cloud_change_provider)
        self.cloud_provider_combo.pack(fill="x")
        self.cloud_provider_combo.set(self.cloud_provider.get())
        self.cloud_active_label = self.text(self.cloud_fields, "", 10, muted=True)
        self.cloud_active_label.pack(anchor="w", pady=3)
        self.cloud_manage_btn = self.secondary_button(
            self.cloud_fields, "Gestisci chiavi API" if self.ui_language.get()=="it" else "Manage API keys",
            self.cloud_manage_popup, 230)
        self.cloud_manage_btn.pack(anchor="w", pady=5)
        self.cloud_model_combo = ctk.CTkOptionMenu(
            self.cloud_fields, values=list(MODELS[self.cloud_provider.get()]),
            command=self.change_cloud_model)
        self.cloud_model_combo.pack(fill="x", pady=5)
        self.cloud_warning_label = self.text(self.cloud_fields,
            "Le richieste cloud possono essere a pagamento. Serve consenso prima di ogni coda." if self.ui_language.get()=="it" else
            "Cloud requests may incur charges. Consent required per batch.", 10, muted=True, wraplength=570)
        self.cloud_warning_label.pack(anchor="w")
        self.refresh_cloud_options()
        if self.engine.get() == "cloud":
            self.cloud_fields.pack(fill="x")

        advanced_body = self.panel(self.settings_page)
        self.text(advanced_body, self.t("output_settings"), 16, True).pack(anchor="w", padx=15, pady=(12, 5))
        self.text(advanced_body, self.t("formats"), 12).pack(anchor="w", padx=15, pady=(0, 5))
        formats_row = ctk.CTkFrame(advanced_body, fg_color="transparent")
        formats_row.pack(anchor="w", padx=15, pady=(0, 5))
        for fmt, enabled in self.formats.items():
            ctk.CTkCheckBox(formats_row, text=fmt.upper(), width=76, variable=enabled,
                            fg_color=c["accent"], hover_color=c["accent"],
                            command=lambda fmt=fmt: self.save_format(fmt)).pack(side="left", padx=(0, 8))
        self.text(advanced_body, self.t("formats_help"), 11, muted=True, wraplength=515,
                  justify="left").pack(anchor="w", padx=15, pady=(0, 11))
        self.text(advanced_body, self.t("transcripts"), 11).pack(anchor="w", padx=15)
        self.choose_input(advanced_body, self.transcripts_dir, lambda: self.choose_dir(self.transcripts_dir), self.t("choose"))
        self.text(advanced_body, self.t("videos"), 11).pack(anchor="w", padx=15, pady=(9, 0))
        self.choose_input(advanced_body, self.videos_dir, lambda: self.choose_dir(self.videos_dir), self.t("choose"))
        ctk.CTkCheckBox(advanced_body, text=self.t("keep"), variable=self.keep_video,
            command=self.save_config, checkbox_width=17, checkbox_height=17,
            font=("Segoe UI", 11), text_color=c["fg"],
            fg_color=c["accent"]).pack(anchor="w", padx=15, pady=(11, 9))
        actions = ctk.CTkFrame(advanced_body, fg_color="transparent")
        actions.pack(anchor="w", padx=15, pady=(0, 12))
        self.secondary_button(actions, self.t("open"),
            lambda: self.open_folder(Path(self.transcripts_dir.get())), 148).pack(side="left", padx=(0, 7))
        self.secondary_button(actions, self.t("logs"),
            lambda: self.open_folder(CONFIG_DIR), 140).pack(side="left")
        settings_card.pack(before=appearance)
        advanced_body.pack(before=settings_card)
        connections = self.panel(self.settings_page)
        self.text(connections, self.t("connections"), 16, True).pack(anchor="w", padx=15, pady=(12, 5))
        links = ctk.CTkFrame(connections, fg_color="transparent")
        links.pack(anchor="w", padx=15, pady=(0, 12))
        self.secondary_button(links, self.t("webex_setup"), self.browser_setup, 155).pack(side="left")
        self.secondary_button(links, self.t("check_update"), self.check_updates, 172).pack(side="left", padx=8)
        self.text(links, "v" + VERSION, 11, muted=True).pack(side="left", padx=5)

        run_card = self.panel(self.workspace_page)
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
        self.job_summary = self.text(self.workspace_page, "", 11, muted=True, wraplength=490)
        self.job_summary.pack(anchor="w", pady=(0, 7))
        self.show_page(self.current_page)

    def save_format(self, fmt):
        if not any(var.get() for var in self.formats.values()):
            self.formats[fmt].set(True)
        self.save_config()

    def show_page(self, page):
        if self.current_page == "settings" and page != "settings":
            self.save_config()
        self.current_page = page
        colors = self.palette()
        for key, frame, button in (("workspace", self.workspace_page, self.workspace_tab),
                                   ("settings", self.settings_page, self.settings_tab)):
            active = key == page
            button.configure(state="disabled" if active else "normal",
                             fg_color=colors["accent"] if active else colors["inset"],
                             text_color_disabled=colors["accent_text"])
            if key == page:
                frame.pack(fill="both", expand=True)
            else:
                frame.pack_forget()
        formats = " · ".join(fmt.upper() for fmt, enabled in self.formats.items() if enabled.get())
        engine = self.t("local_engine") if self.engine.get() == "local" else self.t("cloud_engine")
        self.job_summary.configure(text=f"{engine}    |    {formats}")
        self.root.after_idle(lambda: self.scroll_area._parent_canvas.yview_moveto(0))


    def toggle_custom_name(self):
        if self.custom_name.get():
            self.custom_row.pack(fill="x", padx=15, pady=(0, 12))
        else:
            self.custom_row.pack_forget()

    def refresh_queue(self):
        if hasattr(self, "queue_label") and self.queue_label.winfo_exists():
            names = []
            for item in self.pending_sources[:3]:
                source = item["source"]
                fallback = urlsplit(source).hostname if source.startswith(("http://", "https://")) else Path(source).name
                names.append(item.get("name") or fallback or "URL")
            size = len(self.pending_sources)
            if size > len(names):
                names.append(f"+{size - len(names)}")
            label = f"{size} · " + " · ".join(names) if names else self.t("queue_empty")
            self.queue_label.configure(text=label)

    def enqueue_files(self):
        files = filedialog.askopenfilenames(filetypes=[("Media", "*.mp4 *.mkv *.webm *.mov *.mp3 *.m4a *.wav *.flac *.aac")])
        self.pending_sources.extend({"source":x,"name":None} for x in files)
        self.refresh_queue()

    def clear_queue(self):
        if not self.running:
            self.pending_sources.clear()
            self.refresh_queue()

    def set_engine(self, value):
        self.engine.set(value)
        if value == "cloud":
            self.cloud_fields.pack(fill="x")
        else:
            self.cloud_fields.pack_forget()
        self.save_config()

    def change_cloud_model(self, value):
        self.cloud_model.set(value)
        self.refresh_cloud_options()
        self.save_config()

    def refresh_cloud_options(self):
        if not hasattr(self, "cloud_model_combo"):
            return
        models = list(MODELS.get(self.cloud_provider.get(), ()))
        if not models:
            return
        if self.cloud_model.get() not in models:
            self.cloud_model.set(models[0])
        self.cloud_model_combo.configure(values=models)
        self.cloud_model_combo.set(self.cloud_model.get())
        self.cloud_provider_combo.set(self.cloud_provider.get())
        self.cloud_active_label.configure(
            text=f"Active: {self.cloud_provider.get()} / {self.cloud_model.get()}")

    def check_updates(self):
        self.save_config()
        repo = OFFICIAL_REPO
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
                folder = Path(tempfile.mkdtemp(prefix="scribelane_update_"))
                binary = stage_update(asset, folder)
                self.send("update_ready", str(binary))
            except Exception:
                self.send("update_error")
        threading.Thread(target=task, daemon=True).start()

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
                self.apply_live_theme()
        self.root.after(2500, self.watch_system_theme)

    def animate_status(self):
        # A subtle animated ellipsis while a job is active, without modifying the source status.
        if self.running and hasattr(self, "status_label"):
            self._phase = (self._phase + 1) % 4
            self.status_label.configure(text=self.status.get() + " " + "·" * self._phase)
        elif hasattr(self, "status_label"):
            self.status_label.configure(text=self.status.get())
        self.root.after(350, self.animate_status)

    def _all_widgets(self, parent):
        for child in parent.winfo_children():
            yield child
            yield from self._all_widgets(child)

    def refresh_translations(self):
        """Update visible labels in place, without destroying user inputs."""
        if not self.main or not self.main.winfo_exists():
            return
        old_language = self._rendered_language
        if old_language == self.ui_language.get():
            return
        old_dict, new_dict = I18N[old_language], I18N[self.ui_language.get()]
        translations = {str(value): str(new_dict[key])
                        for key, value in old_dict.items() if key in new_dict}
        prefixes = ("▶  ", "■  ", "⌄  ", "›  ")
        for widget in self._all_widgets(self.main):
            if not isinstance(widget, (ctk.CTkLabel, ctk.CTkButton, ctk.CTkCheckBox)):
                continue
            try:
                old_text = widget.cget("text")
                new_text = translations.get(old_text)
                if new_text is None:
                    for prefix in prefixes:
                        if old_text.startswith(prefix) and old_text[len(prefix):] in translations:
                            new_text = prefix + translations[old_text[len(prefix):]]
                            break
                if new_text is None and isinstance(old_text, str):
                    for prefix in ("",):
                        key = "updates"
                        if old_text == old_dict[key] + " · v" + VERSION:
                            new_text = new_dict[key] + " · v" + VERSION
                if new_text is not None:
                    widget.configure(text=new_text)
            except (tk.TclError, ValueError, AttributeError):
                pass
        self.language_button.configure(text="English" if self.ui_language.get() == "it" else "Italiano")
        self.theme_button.configure(text=self.theme_icon())
        self.show_page(self.current_page)
        self.quality_label_map = {self.t("quality_" + key): key for key in QUALITY_CHOICES}
        self.quality_combo.configure(values=list(self.quality_label_map))
        self.quality_combo.set(self.t("quality_" + self.model.get()))
        self.language_label_map = {self.t("spoken_" + key): key for key in ("auto", "it", "en")}
        self.speech_combo.configure(values=list(self.language_label_map))
        self.speech_combo.set(self.t("spoken_" + self.spoken.get()))
        self.engine_combo.configure(values=[self.t("local_engine"), self.t("cloud_engine")])
        self.engine_combo.set(self.t("cloud_engine") if self.engine.get() == "cloud" else self.t("local_engine"))
        self.cloud_title.configure(text="Provider AI" if self.ui_language.get() == "it" else "AI provider")
        self.cloud_manage_btn.configure(text="Gestisci chiavi API" if self.ui_language.get() == "it" else "Manage API keys")
        self.cloud_warning_label.configure(text=(
            "Le richieste cloud possono essere a pagamento. Serve consenso prima di ogni coda."
            if self.ui_language.get() == "it" else
            "Cloud requests may incur charges. Consent required per batch."))
        self.refresh_queue()
        self._rendered_language = self.ui_language.get()

    def apply_live_theme(self):
        """Repaint existing CTk controls; preserve their identity and focus."""
        old = self._last_palette or self.palette()
        new = self.palette()
        self.apply_theme()
        color_fields = ("fg_color", "bg_color", "text_color", "text_color_disabled", "border_color",
                        "hover_color", "button_color", "button_hover_color",
                        "dropdown_fg_color", "dropdown_text_color", "progress_color",
                        "scrollbar_button_color", "scrollbar_button_hover_color")
        for widget in (self.scroll_area, *self._all_widgets(self.main)):
            for field in color_fields:
                try:
                    old_value = widget.cget(field)
                    if isinstance(old_value, str):
                        for role, color in old.items():
                            if old_value.lower() == color.lower():
                                widget.configure(**{field: new[role]})
                                break
                except (tk.TclError, ValueError, AttributeError, TypeError):
                    pass
        self._last_palette = new.copy()
        self.theme_button.configure(text=self.theme_icon())

    def update_preferences(self, _event=None):
        self.save_config()
        self.apply_live_theme()
        self.refresh_translations()


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
                elif kind == "webex_error":
                    messagebox.showwarning(APP, self.t(value))
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
        sources = ([{"source":source,"name":None}] if source else []) + self.pending_sources[:]
        sources = list({item["source"]:item for item in sources}.values())
        if not sources:
            messagebox.showwarning(APP, self.t("missing"))
            return
        if any(not x.startswith(("http://", "https://")) and not Path(x).is_file() for x in (item["source"] for item in sources)):
            messagebox.showerror(APP, self.t("notfound"))
            return
        if self.engine.get() == "cloud":
            chosen = next((entry for entry in self.vault.items
                if entry.get("id") == self.cloud_key_id.get()
                and entry.get("enabled")
                and entry.get("provider") == self.cloud_provider.get()), None)
            if chosen is None or not self.vault.get_secret(self.cloud_key_id.get()):
                messagebox.showwarning(APP, "Select an enabled API key for this provider")
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
        self.running = True
        self.progress_value = 0
        self.progress.set(0)
        self.status.set(self.t("preparing"))
        self.update_buttons()
        job = {"source": source, "name": requested_name, "model": model, "spoken": self.spoken.get(), "keep": self.keep_video.get(), "transcripts": transcript_dir, "videos": video_dir, "engine": self.engine.get(), "cloud_provider":self.cloud_provider.get(),"cloud_model":self.cloud_model.get(),
               "cloud_key_id":self.cloud_key_id.get(),
               "formats": tuple(fmt for fmt, selected in self.formats.items() if selected.get())}
        self.pending_sources.clear()
        self.refresh_queue()
        threading.Thread(target=self.worker_batch, args=(job, sources), daemon=True).start()

    def cancel(self):
        if not self.running:
            return
        self.stop_event.set()
        self.stop_button.configure(state="disabled")

    def check_cancel(self):
        if self.stop_event.is_set():
            raise JobCancelled()

    def browser_setup(self):
        if self.running:
            return
        dlg = ctk.CTkToplevel(self.root)
        dlg.title(self.t("webex_setup"))
        dlg.geometry("500x255")
        dlg.transient(self.root)
        dlg.grab_set()
        pane = ctk.CTkFrame(dlg)
        pane.pack(fill="both", expand=True, padx=16, pady=16)
        self.text(pane, self.t("webex_setup_help"), 12, wraplength=425,
                  justify="left").pack(padx=14, pady=(14, 10))
        browsers = {
            self.t("webex_other"): "chromium",
            "Chrome": "Chrome",
            "Edge": "Edge",
            "Brave": "Brave",
            "Firefox": "Firefox",
        }
        selected_label = next((label for label, browser in browsers.items()
                               if browser == self.webex_browser), self.t("webex_other"))
        selected = ctk.StringVar(value=selected_label)
        ctk.CTkOptionMenu(pane, variable=selected, values=list(browsers)).pack(pady=4)
        instruction = self.text(pane, "", 11, wraplength=420, justify="left")
        instruction.pack(padx=12, pady=8)

        def update(*_):
            key = "webex_firefox_help" if selected.get() == "Firefox" else "webex_chromium_help"
            instruction.configure(text=self.t(key))

        def save():
            self.webex_browser = browsers[selected.get()]
            self.save_config()
            dlg.destroy()

        selected.trace_add("write", update)
        update()
        self.secondary_button(pane, self.t("webex_save"), save, 160).pack(pady=4)

    def download(self, url, folder):
        def hook(data):
            self.check_cancel()
            if data.get("status") == "downloading":
                total = data.get("total_bytes") or data.get("total_bytes_estimate")
                if total:
                    self.send("progress", min(35, 35 * data.get("downloaded_bytes", 0) / total))

        self.log("DOWNLOAD_STARTED")
        self.send("status", self.t("downloading"))
        opts = {
            "noplaylist": True,
            "ffmpeg_location": imageio_ffmpeg.get_ffmpeg_exe(),
            "socket_timeout": 15,
            "concurrent_fragment_downloads": 4,
            "retries": 3,
            "fragment_retries": 3,
            "skip_unavailable_fragments": False,
            "progress_hooks": [hook],
            "logger": PrivateLogger(),
            "quiet": True,
            "no_warnings": True,
            "noprogress": True,
        }
        def attempt(target, destination):
            destination.mkdir(exist_ok=True)
            self.send("status", self.t("downloading"))
            with yt_dlp.YoutubeDL({**opts, "outtmpl": str(destination / "recording.%(ext)s")}) as dl:
                metadata = dl.extract_info(target, download=True) or {}
            self.check_cancel()
            candidates = [p for p in destination.iterdir() if p.is_file() and p.suffix.lower() in EXTS]
            if not candidates:
                raise DownloadError("no_media")
            return candidates, metadata

        try:
            candidates, metadata = attempt(url, folder)
        except DownloadError:
            self.check_cancel()
            if not is_webex_playback(url):
                self.log("DOWNLOAD_FAILED")
                raise RuntimeError("download_failed") from None
            self.log("WEBEX_DIRECT_DOWNLOAD_FAILED")
            self.send("status", self.t("webex_connect"))
            try:
                target = capture_playlist(
                    url, check_cancel=self.check_cancel,
                    on_playback=lambda: self.send("status", self.t("webex_wait")),
                )
            except WebexBrowserError as exc:
                self.check_cancel()
                self.log("WEBEX_CAPTURE_FAILED")
                raise RuntimeError(str(exc)) from None
            self.log("WEBEX_HLS_FOUND")
            try:
                candidates, metadata = attempt(target, folder / "hls")
            except DownloadError:
                self.check_cancel()
                self.log("WEBEX_HLS_DOWNLOAD_FAILED")
                raise RuntimeError("download_failed") from None
        self.log("DOWNLOAD_FINISHED")
        self.send("progress", 35)
        return max(candidates, key=lambda p: p.stat().st_size), (metadata.get("title") or metadata.get("fulltitle"))

    def transcribe(self, job, media, network_media):
        self.check_cancel()
        self.send("status", self.t("loading"))
        language = None if job["spoken"] == "auto" else job["spoken"]
        ov_result = None

        def accelerator_status(phase):
            if phase in ("GPU", "NPU"):
                self.log("OPENVINO_ACTIVE_" + phase)
                self.send("status", f"{self.t('transcribing')} · OpenVINO {phase}")
            else:
                if phase == "ov_retry_gpu":
                    self.log("OPENVINO_NPU_KV_CACHE_RETRY_GPU")
                self.send("status", self.t(phase))

        try:
            ov_result = transcribe_if_available(
                media, job["model"], language, OV_MODELS, OV_BENCH,
                cancelled=self.stop_event.is_set, on_status=accelerator_status)
        except InterruptedError:
            raise JobCancelled()
        except OpenVINOUnavailable as exc:
            self.check_cancel()
            self.log("OPENVINO_FALLBACK_" + exc.reason)
        except Exception:
            self.check_cancel()
            self.log("OPENVINO_FALLBACK_ERROR")
        if ov_result:
            items, device = ov_result
            backend = "OpenVINO " + device
            segments = (SimpleNamespace(start=a, end=b, text=t) for a,b,t in items)
            duration = items[-1][1] if items else 0
        else:
            backend = "CPU"
            self.send("status", f"{self.t('loading')} · {backend}")
            if self.model_instance is None or self.model_name != job["model"]:
                try:
                    self.model_instance = WhisperModel(job["model"], device="cpu", compute_type="int8", cpu_threads=self.cpu_threads)
                    self.model_name = job["model"]
                except Exception:
                    self.log("MODEL_LOAD_FAILED")
                    raise RuntimeError("model_error") from None
            self.check_cancel()
            segments, info = self.model_instance.transcribe(str(media), language=language, beam_size=5, vad_filter=True, condition_on_previous_text=True)
            duration = info.duration or 0
        return self.write_local_transcript(job, segments, duration, backend, network_media)

    def write_local_transcript(self, job, segments, duration=0, backend="", network_media=False,
                               approximate=False):
        folder = job["transcripts"]
        paths = {fmt: folder / f"{job['name']}.{fmt}" for fmt in job.get("formats", OUTPUT_FORMATS)}
        opened = {}
        count = 0
        completed = False
        self.log("TRANSCRIPTION_STARTED")
        try:
            with ExitStack() as stack:
                for fmt, path in paths.items():
                    opened[fmt] = stack.enter_context(path.open("w", encoding="utf-8"))
                if "md" in opened:
                    opened["md"].write(f"# {job['name']}\n\n")
                    if approximate:
                        opened["md"].write(f"> {self.t('cloud_result')}\n\n")
                for segment in segments:
                    self.check_cancel()
                    sentence = segment.text.strip()
                    if not sentence:
                        continue
                    count += 1
                    stamp = f"~{millis(segment.start).split('.')[0]} chunk" if approximate else millis(segment.start)
                    if "txt" in opened:
                        opened["txt"].write(f"[{stamp}] {sentence}\n")
                    if "md" in opened:
                        opened["md"].write(f"[{stamp}] {sentence}\n\n")
                    if "srt" in opened:
                        opened["srt"].write(
                            f"{count}\n{millis(segment.start, True)} --> {millis(segment.end, True)}\n{sentence}\n\n")
                    for stream in opened.values():
                        stream.flush()
                    if duration:
                        start, portion = (35, 65) if network_media else (0, 100)
                        self.send("progress", start + min(1, segment.end / duration) * portion)
                    if backend:
                        self.send("status", f"{self.t('transcribing')} · {backend} · {millis(segment.end)}")
                self.check_cancel()
            completed = True
        finally:
            if not completed:
                for fmt in opened:
                    file = paths[fmt]
                    file.replace(file.with_name(file.stem + ".partial" + file.suffix))
        self.log("TRANSCRIPTION_FINISHED")
        return paths

    def resolve_name(self, job, media, metadata_title=None, reserved=()):
        desired = job["name"] or metadata_title or media.stem
        # Avoid generic filenames used internally for Webex downloads.
        if not job["name"] and (not desired or desired.lower() in {"recording", "video", "hls"}):
            desired = "Webex_" + datetime.now().strftime("%Y%m%d_%H%M%S")
        base = clean_name(desired)
        folder, videos = job["transcripts"], job["videos"]
        name, num = base, 2
        while (name.casefold() in reserved or any((folder / f"{name}{sfx}").exists() for sfx in (".txt", ".srt", ".md", ".partial.txt", ".partial.srt", ".partial.md"))
               or any((videos / f"{name}{ext}").exists() for ext in EXTS)):
            name = f"{base}_{num}"
            num += 1
        job["name"] = name

    def worker_batch(self, job, sources):
        jobs = []
        for index, source in enumerate(sources, start=1):
            current = dict(job, source=source["source"])
            if source.get("name"):
                current["name"] = clean_name(source["name"])
            elif job["name"] and len(sources) > 1:
                current["name"] = f"{job['name']}_{index:02}"
            jobs.append(current)

        failures = 0
        try:
            if job["engine"] == "local" and len(jobs) >= 2:
                jobs, failures = self.try_parallel_queue(jobs)
            completed = len(sources) - len(jobs)
            for current in jobs:
                self.check_cancel()
                try:
                    self.process_one(current)
                    self.log("BATCH_ITEM_SUCCESS")
                except JobCancelled:
                    raise
                except Exception as exc:
                    failures += 1
                    self.log("BATCH_ITEM_FAILED")
                    if isinstance(exc, RuntimeError) and str(exc) in WEBEX_ERRORS:
                        self.send("webex_error", str(exc))
                completed += 1
                self.send("status", f"{completed}/{len(sources)}")
        except (JobCancelled, InterruptedError):
            self.send("cancelled")
            return
        self.send("done_batch", (len(sources), failures, str(job['transcripts'])))

    def try_parallel_queue(self, jobs):
        media = [Path(job["source"]) for job in jobs]
        if any(job["source"].startswith(("http://", "https://")) or not path.is_file()
               for job, path in zip(jobs, media)):
            return jobs, 0
        language = None if jobs[0]["spoken"] == "auto" else jobs[0]["spoken"]
        try:
            pipes = prepare_parallel(
                media[:2], jobs[0]["model"], language, OV_MODELS,
                self.stop_event.is_set, lambda phase: self.send("status", self.t(phase)),
            )
        except InterruptedError:
            raise
        except Exception:
            self.log("OPENVINO_QUEUE_FALLBACK")
            return jobs, 0
        if not pipes:
            return jobs, 0

        reserved = set()
        for current, path in zip(jobs, media):
            self.resolve_name(current, path, reserved=reserved)
            reserved.add(current["name"].casefold())
        remaining = iter(enumerate(media))
        in_progress, retry = {}, []
        failures = completed = 0
        self.log("OPENVINO_QUEUE_GPU_NPU")
        self.send("status", f"{self.t('transcribing')} · OpenVINO GPU + NPU")
        with ThreadPoolExecutor(max_workers=2) as workers:
            def assign(device):
                self.check_cancel()
                item = next(remaining, None)
                if item is not None:
                    index, path = item
                    future = workers.submit(
                        transcribe_on_device, path, language, pipes[device],
                        device, self.stop_event.is_set,
                    )
                    in_progress[future] = (device, index)

            for device in pipes:
                assign(device)
            while in_progress:
                self.check_cancel()
                ready, _ = wait(in_progress, timeout=.2, return_when=FIRST_COMPLETED)
                for future in ready:
                    device, index = in_progress.pop(future)
                    try:
                        items = future.result()
                    except InterruptedError:
                        raise
                    except Exception:
                        retry.append(index)
                        self.log("OPENVINO_QUEUE_RETRY_" + device)
                        continue
                    assign(device)
                    try:
                        segments = (SimpleNamespace(start=a, end=b, text=text) for a, b, text in items)
                        self.write_local_transcript(jobs[index], segments)
                        self.log("BATCH_ITEM_SUCCESS")
                    except JobCancelled:
                        raise
                    except Exception:
                        failures += 1
                        self.log("BATCH_ITEM_FAILED")
                    completed += 1
                    self.send("progress", 100 * completed / len(jobs))
                    self.send("status", f"OpenVINO GPU + NPU · {completed}/{len(jobs)}")

        retry.extend(index for index, _ in remaining)
        return [jobs[index] for index in sorted(retry)], failures

    def process_one(self, job):
        source = job["source"]
        if source.startswith(("http://", "https://")):
            with tempfile.TemporaryDirectory(prefix="scribelane_") as temp:
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
            self.transcribe(job, media, network_media)
            return
        self.send("status", self.t("transcribing"))

        def progress(value):
            start, span = (35, 65) if network_media else (0, 100)
            self.send("progress", start + span * value / 100)

        try:
            secret = self.vault.get_secret(job["cloud_key_id"])
            if not secret:
                raise ProviderError("credential_missing")
            blocks = transcribe_long(
                media, provider=job["cloud_provider"], model=job["cloud_model"],
                secret=secret, language=job["spoken"], output_dir=job["transcripts"],
                job_id=job["name"], key_id=job["cloud_key_id"], progress=progress,
                cancelled=self.stop_event.is_set, timed=True,
            )
        except InterruptedError:
            raise JobCancelled()
        except ProviderError as err:
            self.log("CLOUD_" + err.category.upper())
            raise RuntimeError("Cloud provider error: " + err.category) from None
        self.check_cancel()
        segments = (SimpleNamespace(start=start, end=end, text=text) for start, end, text in blocks)
        self.write_local_transcript(job, segments, approximate=True)

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
