
import os
import re
import sys
import shutil
import tempfile
import threading
import tkinter as tk

from pathlib import Path
from queue import Queue, Empty
from datetime import datetime
from tkinter import ttk, filedialog, messagebox

import yt_dlp
from yt_dlp.utils import DownloadError
from faster_whisper import WhisperModel


APP_NAME = "LectureScribe"
MODEL_NAME = "turbo"

BASE = Path.home() / "Documents" / APP_NAME
OUTPUT = BASE / "Trascrizioni"
OUTPUT.mkdir(parents=True, exist_ok=True)

MEDIA_EXTENSIONS = {
    ".mp4", ".mkv", ".webm", ".mp3",
    ".m4a", ".wav", ".aac", ".mov", ".flac"
}

BROWSERS = {
    "Google Chrome": "chrome",
    "Microsoft Edge": "edge",
    "Mozilla Firefox": "firefox",
    "Brave": "brave",
    "Opera": "opera",
    "Vivaldi": "vivaldi",
    "Chromium": "chromium",
    "Whale": "whale",
}

AUTH_MARKERS = (
    "only available for registered users",
    "login required",
    "login to",
    "sign in",
    "authentication required",
    "cookies-from-browser",
    "cookies from browser",
    "http error 401",
    "http error 403",
    "unauthorized",
    "forbidden",
)


class Cancelled(Exception):
    pass


def timestamp(seconds, srt=False):
    millis = max(0, round(seconds * 1000))
    hours, rem = divmod(millis, 3600000)
    minutes, rem = divmod(rem, 60000)
    secs, ms = divmod(rem, 1000)

    sep = "," if srt else "."

    return (
        f"{hours:02}:{minutes:02}:"
        f"{secs:02}{sep}{ms:03}"
    )


def safe_name(value):
    value = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", value)
    value = value.strip(" .")

    return value[:100] or datetime.now().strftime(
        "Lezione_%Y%m%d_%H%M%S"
    )


def unique_name(name):
    candidate = name
    index = 2

    while any(
        (OUTPUT / f"{candidate}{ext}").exists()
        for ext in (".txt", ".srt", ".mp4", ".mkv", ".webm")
    ):
        candidate = f"{name}_{index}"
        index += 1

    return candidate


class SafeLogger:
    """Non mostra URL firmati, cookie o token."""

    def __init__(self):
        self.messages = []

    def debug(self, message):
        pass

    def warning(self, message):
        self.messages.append(str(message).lower())

    def error(self, message):
        self.messages.append(str(message).lower())


class LectureScribe:
    def __init__(self, root):
        self.root = root
        self.queue = Queue()

        self.running = False
        self.stop_event = threading.Event()

        self.auth_event = threading.Event()
        self.auth_result = None
        self.auth_dialog = None

        self.model = None

        root.title("LectureScribe")
        root.geometry("690x570")
        root.minsize(580, 500)

        self.build_interface()

        root.after(100, self.poll_queue)
        root.protocol("WM_DELETE_WINDOW", self.on_close)

    def build_interface(self):
        frame = ttk.Frame(self.root, padding=24)
        frame.pack(fill="both", expand=True)

        ttk.Label(
            frame,
            text="LectureScribe",
            font=("Segoe UI", 24, "bold")
        ).pack(anchor="w")

        ttk.Label(
            frame,
            text="Trascrizione locale di lezioni e registrazioni",
        ).pack(anchor="w", pady=(2, 23))

        ttk.Label(
            frame,
            text="Link Webex, URL HLS o file locale"
        ).pack(anchor="w")

        source_row = ttk.Frame(frame)
        source_row.pack(fill="x", pady=(7, 18))

        self.source_var = tk.StringVar()

        ttk.Entry(
            source_row,
            textvariable=self.source_var
        ).pack(side="left", fill="x", expand=True)

        ttk.Button(
            source_row,
            text="Sfoglia",
            command=self.browse
        ).pack(side="left", padx=(8, 0))

        ttk.Label(
            frame,
            text="Nome della lezione"
        ).pack(anchor="w")

        self.name_var = tk.StringVar()

        ttk.Entry(
            frame,
            textvariable=self.name_var
        ).pack(fill="x", pady=(7, 19))

        self.keep_video = tk.BooleanVar(value=False)

        ttk.Checkbutton(
            frame,
            text="Conserva il video scaricato",
            variable=self.keep_video
        ).pack(anchor="w")

        ttk.Label(
            frame,
            text=(
                "Se disattivato, elimina il download temporaneo. "
                "I file locali originali non vengono mai eliminati."
            ),
            foreground="gray",
            wraplength=620
        ).pack(anchor="w", pady=(5, 22))

        ttk.Label(
            frame,
            text="Avanzamento"
        ).pack(anchor="w")

        self.progress = ttk.Progressbar(
            frame,
            maximum=100,
            mode="determinate"
        )
        self.progress.pack(fill="x", pady=(9, 9))

        self.status_var = tk.StringVar(value="Pronto")

        ttk.Label(
            frame,
            textvariable=self.status_var,
            wraplength=620
        ).pack(anchor="w", pady=(0, 8))

        self.start_btn = ttk.Button(
            frame,
            text="Avvia trascrizione",
            command=self.start
        )
        self.start_btn.pack(fill="x", pady=(17, 7))

        self.stop_btn = ttk.Button(
            frame,
            text="Interrompi",
            command=self.stop,
            state="disabled"
        )
        self.stop_btn.pack(fill="x", pady=(0, 7))

        ttk.Button(
            frame,
            text="Apri cartella trascrizioni",
            command=self.open_output
        ).pack(fill="x")

        ttk.Label(
            frame,
            text="Modello: Whisper Turbo | CPU INT8",
            foreground="gray"
        ).pack(anchor="w", pady=(20, 0))

    def browse(self):
        path = filedialog.askopenfilename(
            filetypes=[
                (
                    "Audio e video",
                    "*.mp4 *.mkv *.webm *.mp3 "
                    "*.m4a *.wav *.aac *.mov *.flac"
                ),
                ("Tutti i file", "*.*")
            ]
        )

        if path:
            self.source_var.set(path)

    def open_output(self):
        OUTPUT.mkdir(parents=True, exist_ok=True)
        os.startfile(str(OUTPUT))

    def send(self, kind, value=None):
        self.queue.put((kind, value))

    def poll_queue(self):
        try:
            while True:
                kind, value = self.queue.get_nowait()

                if kind == "status":
                    self.status_var.set(value)

                elif kind == "progress":
                    self.progress["value"] = max(
                        0, min(100, value)
                    )

                elif kind == "auth_required":
                    self.show_auth_dialog()

                elif kind in ("finished", "error", "cancelled"):
                    self.running = False
                    self.start_btn["state"] = "normal"
                    self.stop_btn["state"] = "disabled"

                    if kind == "finished":
                        self.progress["value"] = 100
                        self.status_var.set("Completato")
                        messagebox.showinfo(
                            "LectureScribe", value
                        )

                    elif kind == "cancelled":
                        self.status_var.set("Interrotto")
                        messagebox.showinfo(
                            "LectureScribe", value
                        )

                    else:
                        self.status_var.set("Errore")
                        messagebox.showerror(
                            "LectureScribe", value
                        )

        except Empty:
            pass

        self.root.after(100, self.poll_queue)

    def start(self):
        if self.running:
            return

        source = self.source_var.get().strip().strip('"')

        if not source:
            messagebox.showwarning(
                "Input mancante",
                "Inserisci un link o seleziona un file."
            )
            return

        name = safe_name(self.name_var.get())
        name = unique_name(name)

        self.running = True
        self.stop_event.clear()
        self.auth_event.clear()
        self.auth_result = None

        self.progress["value"] = 0
        self.status_var.set("Preparazione...")

        self.start_btn["state"] = "disabled"
        self.stop_btn["state"] = "normal"

        threading.Thread(
            target=self.worker,
            args=(source, name, self.keep_video.get()),
            daemon=True
        ).start()

    def stop(self):
        if not self.running:
            return

        self.stop_event.set()
        self.auth_event.set()
        self.status_var.set(
            "Interruzione richiesta..."
        )
        self.stop_btn["state"] = "disabled"

        if (
            self.auth_dialog is not None
            and self.auth_dialog.winfo_exists()
        ):
            self.auth_dialog.destroy()
            self.auth_dialog = None

    def check_cancel(self):
        if self.stop_event.is_set():
            raise Cancelled()

    def show_auth_dialog(self):
        if self.stop_event.is_set():
            self.auth_event.set()
            return

        dialog = tk.Toplevel(self.root)
        self.auth_dialog = dialog

        dialog.title("Autenticazione Webex")
        dialog.geometry("480x335")
        dialog.resizable(False, False)
        dialog.transient(self.root)
        dialog.grab_set()

        frame = ttk.Frame(dialog, padding=20)
        frame.pack(fill="both", expand=True)

        ttk.Label(
            frame,
            text="Accesso richiesto",
            font=("Segoe UI", 15, "bold")
        ).pack(anchor="w")

        ttk.Label(
            frame,
            text=(
                "La registrazione potrebbe richiedere "
                "l'autenticazione. Seleziona il browser "
                "dove hai effettuato l'accesso a Webex."
            ),
            wraplength=420
        ).pack(anchor="w", pady=(10, 15))

        choices = list(BROWSERS.keys()) + [
            "Opera GX",
            "Samsung Browser (file cookie)",
            "Altro browser (file cookie)"
        ]

        selected = tk.StringVar(value="Google Chrome")

        combo = ttk.Combobox(
            frame,
            textvariable=selected,
            values=choices,
            state="readonly"
        )
        combo.pack(fill="x")

        ttk.Label(
            frame,
            text=(
                "Samsung Browser non è supportato "
                "direttamente da yt-dlp. Occorre un file "
                "cookie Netscape esportato in modo sicuro."
            ),
            foreground="gray",
            wraplength=420
        ).pack(anchor="w", pady=(12, 12))

        def finish(result):
            self.auth_result = result
            self.auth_event.set()

            if dialog.winfo_exists():
                dialog.destroy()

            self.auth_dialog = None

        def confirm():
            browser = selected.get()

            if "file cookie" in browser:
                path = filedialog.askopenfilename(
                    parent=dialog,
                    title="Seleziona cookies.txt",
                    filetypes=[
                        ("File cookie", "*.txt"),
                        ("Tutti i file", "*.*")
                    ]
                )

                if path:
                    finish(("file", path))
                return

            if browser == "Opera GX":
                profile = (
                    Path(os.environ["APPDATA"])
                    / "Opera Software"
                    / "Opera GX Stable"
                )

                finish(("browser", "opera", str(profile)))
                return

            finish(("browser", BROWSERS[browser], None))

        ttk.Button(
            frame,
            text="Continua",
            command=confirm
        ).pack(fill="x", pady=(8, 7))

        ttk.Button(
            frame,
            text="Annulla",
            command=lambda: finish(None)
        ).pack(fill="x")

        dialog.protocol(
            "WM_DELETE_WINDOW",
            lambda: finish(None)
        )

    def download(self, url, folder):
        self.send(
            "status", "Verifica della registrazione..."
        )

        logger = SafeLogger()

        def progress_hook(data):
            self.check_cancel()

            if data.get("status") != "downloading":
                return

            total = (
                data.get("total_bytes")
                or data.get("total_bytes_estimate")
            )
            done = data.get("downloaded_bytes", 0)

            if total:
                # Download occupa il primo 35%
                self.send(
                    "progress",
                    min(35, done / total * 35)
                )

        base_options = {
            "outtmpl": str(
                folder / "registrazione.%(ext)s"
            ),
            "noplaylist": True,
            "concurrent_fragment_downloads": 4,
            "retries": 3,
            "fragment_retries": 3,
            "progress_hooks": [progress_hook],
            "quiet": True,
            "no_warnings": True,
            "logger": logger,
        }

        def run_download(extra=None):
            options = dict(base_options)

            if extra:
                options.update(extra)

            with yt_dlp.YoutubeDL(options) as ydl:
                ydl.download([url])

        self.check_cancel()

        try:
            # Primo tentativo: nessun cookie.
            run_download()

        except DownloadError as exc:
            self.check_cancel()

            combined_error = (
                str(exc).lower()
                + " "
                + " ".join(logger.messages)
            )

            requires_auth = any(
                marker in combined_error
                for marker in AUTH_MARKERS
            )

            if not requires_auth:
                raise RuntimeError(
                    "Download non riuscito. Controlla "
                    "l'URL, la connessione e i permessi "
                    "della registrazione."
                ) from None

            self.send(
                "status",
                "Webex richiede l'autenticazione."
            )

            self.auth_result = None
            self.auth_event.clear()

            self.send("auth_required")

            # Attesa eseguita nel worker, non nella GUI.
            self.auth_event.wait()
            self.check_cancel()

            choice = self.auth_result

            if choice is None:
                raise Cancelled()

            extra = {}

            if choice[0] == "file":
                extra["cookiefile"] = choice[1]

            else:
                _, browser, profile = choice

                if profile:
                    extra["cookiesfrombrowser"] = (
                        browser, profile
                    )
                else:
                    extra["cookiesfrombrowser"] = (
                        browser,
                    )

            self.send(
                "status",
                "Download con autenticazione..."
            )

            try:
                run_download(extra)

            except Exception:
                self.check_cancel()
                raise RuntimeError(
                    "Autenticazione o download falliti. "
                    "Verifica di essere collegato a Webex "
                    "nel browser selezionato. Prova anche "
                    "a chiudere il browser e ritentare."
                ) from None

        self.check_cancel()

        candidates = [
            path for path in folder.iterdir()
            if (
                path.is_file()
                and path.suffix.lower() in MEDIA_EXTENSIONS
            )
        ]

        if not candidates:
            raise RuntimeError(
                "Nessun file multimediale scaricato."
            )

        self.send("progress", 35)

        return max(
            candidates,
            key=lambda item: item.stat().st_size
        )

    def transcribe(self, media, name, is_url):
        self.send(
            "status", "Caricamento Whisper Turbo..."
        )

        self.check_cancel()

        if self.model is None:
            self.model = WhisperModel(
                MODEL_NAME,
                device="cpu",
                compute_type="int8",
                cpu_threads=8
            )

        self.check_cancel()

        self.send(
            "status", "Trascrizione in corso..."
        )

        segments, info = self.model.transcribe(
            str(media),
            language="it",
            beam_size=5,
            vad_filter=True,
            condition_on_previous_text=True
        )

        duration = info.duration or 0

        txt_path = OUTPUT / f"{name}.txt"
        srt_path = OUTPUT / f"{name}.srt"

        completed = False
        count = 0

        try:
            with (
                open(txt_path, "w", encoding="utf-8") as txt,
                open(srt_path, "w", encoding="utf-8") as srt
            ):
                for segment in segments:
                    self.check_cancel()

                    content = segment.text.strip()
                    if not content:
                        continue

                    count += 1

                    txt.write(
                        f"[{timestamp(segment.start)}] "
                        f"{content}\n"
                    )

                    srt.write(
                        f"{count}\n"
                        f"{timestamp(segment.start, True)}"
                        " --> "
                        f"{timestamp(segment.end, True)}\n"
                        f"{content}\n\n"
                    )

                    txt.flush()
                    srt.flush()

                    if duration:
                        base = 35 if is_url else 0
                        span = 65 if is_url else 100

                        percent = (
                            base
                            + min(
                                1, segment.end / duration
                            ) * span
                        )

                        self.send("progress", percent)

                    self.send(
                        "status",
                        "Trascritto fino a "
                        f"{timestamp(segment.end)}"
                    )

            self.check_cancel()
            completed = True

        finally:
            # In caso di interruzione, manteniamo
            # i dati già trascritti, indicandoli
            # chiaramente come incompleti.
            if not completed:
                for path in (txt_path, srt_path):
                    if path.exists():
                        partial = path.with_name(
                            path.stem + ".partial"
                            + path.suffix
                        )
                        path.replace(partial)

        return txt_path, srt_path

    def worker(self, source, name, keep_video):
        try:
            is_url = source.startswith(
                ("https://", "http://")
            )

            if not is_url:
                media = Path(source).expanduser()

                if not media.is_file():
                    raise RuntimeError(
                        "File locale non trovato."
                    )

                self.transcribe(media, name, False)

            else:
                with tempfile.TemporaryDirectory(
                    prefix="lecturescribe_"
                ) as directory:

                    folder = Path(directory)
                    media = self.download(source, folder)

                    self.transcribe(media, name, True)

                    if keep_video:
                        self.send(
                            "status",
                            "Conservazione del video..."
                        )

                        destination = (
                            OUTPUT
                            / f"{name}{media.suffix}"
                        )

                        shutil.copy2(media, destination)

                # TemporaryDirectory elimina il video
                # scaricato, anche quando keep_video
                # è disattivato.

            self.send(
                "finished",
                "Trascrizione completata!\n\n"
                f"File generati:\n{name}.txt\n{name}.srt"
            )

        except Cancelled:
            self.send(
                "cancelled",
                "Operazione interrotta.\n\n"
                "Gli eventuali file di trascrizione "
                "parziali sono stati conservati."
            )

        except Exception as exc:
            # Non mostriamo eccezioni potenzialmente
            # contenenti URL firmati o cookie.
            if isinstance(exc, RuntimeError):
                message = str(exc)
            else:
                message = (
                    "Si è verificato un errore "
                    "durante l'elaborazione. "
                    "Controlla il file, i permessi "
                    "o la connessione."
                )

            self.send("error", message)

    def on_close(self):
        if self.running:
            answer = messagebox.askyesno(
                "LectureScribe",
                "È in corso un'elaborazione.\n"
                "Vuoi interromperla e chiudere?"
            )

            if not answer:
                return

            self.stop_event.set()
            self.auth_event.set()

        self.root.destroy()


if __name__ == "__main__":
    root = tk.Tk()
    app = LectureScribe(root)
    root.mainloop()
