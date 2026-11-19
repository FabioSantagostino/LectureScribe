
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from pathlib import Path
from datetime import datetime
from threading import Thread
from queue import Queue, Empty
from tempfile import TemporaryDirectory
import shutil
import yt_dlp
from faster_whisper import WhisperModel
import os

ROOT = Path(os.environ["USERPROFILE"]) / "Documents" / "LectureScribe"
OUTPUT = ROOT / "Trascrizioni"
OUTPUT.mkdir(parents=True, exist_ok=True)


def timestamp(seconds, srt=False):
    ms = max(0, round(seconds * 1000))
    h, rem = divmod(ms, 3600000)
    m, rem = divmod(rem, 60000)
    s, milli = divmod(rem, 1000)
    sep = "," if srt else "."
    return f"{h:02}:{m:02}:{s:02}{sep}{milli:03}"


class LectureScribe:
    def __init__(self, root):
        self.root = root
        self.queue = Queue()
        self.running = False

        root.title("LectureScribe")
        root.geometry("640x485")
        root.minsize(550, 440)

        frame = ttk.Frame(root, padding=22)
        frame.pack(fill="both", expand=True)

        ttk.Label(
            frame,
            text="LectureScribe",
            font=("Segoe UI", 22, "bold")
        ).pack(anchor="w")

        ttk.Label(
            frame,
            text="Trascrivi lezioni Webex e registrazioni locali"
        ).pack(anchor="w", pady=(0, 22))

        ttk.Label(
            frame, text="Link Webex, URL HLS o file locale"
        ).pack(anchor="w")

        input_row = ttk.Frame(frame)
        input_row.pack(fill="x", pady=(5, 15))

        self.source = tk.StringVar()
        ttk.Entry(
            input_row, textvariable=self.source
        ).pack(side="left", fill="x", expand=True)

        ttk.Button(
            input_row,
            text="Sfoglia",
            command=self.browse
        ).pack(side="left", padx=(8, 0))

        ttk.Label(
            frame, text="Nome della lezione"
        ).pack(anchor="w")

        self.name = tk.StringVar()
        ttk.Entry(
            frame, textvariable=self.name
        ).pack(fill="x", pady=(5, 15))

        self.keep_video = tk.BooleanVar(value=False)

        ttk.Checkbutton(
            frame,
            text="Conserva il video scaricato",
            variable=self.keep_video
        ).pack(anchor="w")

        ttk.Label(
            frame,
            text="I file locali originali non vengono mai eliminati.",
            foreground="gray"
        ).pack(anchor="w", pady=(3, 17))

        ttk.Label(
            frame, text="Avanzamento"
        ).pack(anchor="w")

        self.progress = ttk.Progressbar(
            frame, mode="determinate", maximum=100
        )
        self.progress.pack(fill="x", pady=(8, 8))

        self.status = tk.StringVar(value="Pronto")
        ttk.Label(
            frame,
            textvariable=self.status,
            wraplength=550
        ).pack(anchor="w")

        self.start_button = ttk.Button(
            frame,
            text="Avvia trascrizione",
            command=self.start
        )
        self.start_button.pack(fill="x", pady=(24, 8))

        ttk.Button(
            frame,
            text="Apri cartella trascrizioni",
            command=self.open_output
        ).pack(fill="x")

        self.root.after(100, self.poll_queue)

    def browse(self):
        path = filedialog.askopenfilename(
            filetypes=[
                ("File multimediali",
                 "*.mp4 *.mkv *.webm *.mp3 *.m4a *.wav"),
                ("Tutti i file", "*.*")
            ]
        )
        if path:
            self.source.set(path)

    def open_output(self):
        import os
        os.startfile(OUTPUT)

    def send(self, kind, value):
        self.queue.put((kind, value))

    def poll_queue(self):
        try:
            while True:
                kind, value = self.queue.get_nowait()

                if kind == "status":
                    self.status.set(value)

                elif kind == "progress":
                    self.progress["value"] = value

                elif kind == "finished":
                    self.running = False
                    self.start_button["state"] = "normal"
                    messagebox.showinfo(
                        "LectureScribe", value
                    )

                elif kind == "error":
                    self.running = False
                    self.start_button["state"] = "normal"
                    messagebox.showerror(
                        "Errore", value
                    )
        except Empty:
            pass

        self.root.after(100, self.poll_queue)

    def start(self):
        if self.running:
            return

        source = self.source.get().strip().strip('"')
        if not source:
            messagebox.showwarning(
                "Input mancante",
                "Inserisci un link o scegli un file."
            )
            return

        name = self.name.get().strip()
        if not name:
            name = datetime.now().strftime(
                "Lezione_%Y%m%d_%H%M%S"
            )

        name = "".join(
            c if c.isalnum() or c in "-_" else "_"
            for c in name
        )

        # Evita sovrascritture.
        base = name
        index = 2
        while any(
            (OUTPUT / f"{name}{ext}").exists()
            for ext in (".txt", ".srt", ".mp4")
        ):
            name = f"{base}_{index}"
            index += 1

        self.running = True
        self.start_button["state"] = "disabled"
        self.progress["value"] = 0

        Thread(
            target=self.worker,
            args=(source, name, self.keep_video.get()),
            daemon=True
        ).start()

    def worker(self, source, name, keep):
        try:
            with TemporaryDirectory() as directory:
                temp = Path(directory)
                is_url = source.startswith(
                    ("http://", "https://")
                )

                if is_url:
                    self.send(
                        "status", "Download in corso..."
                    )

                    def hook(data):
                        if data.get("status") == "downloading":
                            total = (
                                data.get("total_bytes")
                                or data.get("total_bytes_estimate")
                            )
                            done = data.get(
                                "downloaded_bytes", 0
                            )
                            if total:
                                pct = done / total * 100
                                self.send(
                                    "progress", min(pct, 100)
                                )

                    options = {
                        "outtmpl": str(
                            temp / "registrazione.%(ext)s"
                        ),
                        "format": "best[ext=mp4]/best",
                        "noplaylist": True,
                        "concurrent_fragment_downloads": 4,
                        "retries": 3,
                        "fragment_retries": 3,
                        "progress_hooks": [hook],
                        "quiet": True,
                        "noprogress": True,
                    }

                    with yt_dlp.YoutubeDL(options) as ydl:
                        ydl.download([source])

                    candidates = [
                        p for p in temp.iterdir()
                        if p.suffix.lower() in {
                            ".mp4", ".mkv", ".webm",
                            ".m4a", ".mp3"
                        }
                    ]

                    if not candidates:
                        raise RuntimeError(
                            "Download non completato. "
                            "Prova l'URL HLS della registrazione."
                        )

                    media = max(
                        candidates,
                        key=lambda p: p.stat().st_size
                    )

                else:
                    media = Path(source).expanduser()
                    if not media.is_file():
                        raise FileNotFoundError(
                            "File locale non trovato."
                        )

                self.send(
                    "status", "Caricamento Whisper Turbo..."
                )
                self.send("progress", 0)

                model = WhisperModel(
                    "turbo",
                    device="cpu",
                    compute_type="int8",
                    cpu_threads=8
                )

                self.send(
                    "status", "Trascrizione in corso..."
                )

                segments, info = model.transcribe(
                    str(media),
                    language="it",
                    beam_size=5,
                    vad_filter=True,
                    condition_on_previous_text=True
                )

                duration = info.duration or 0

                txt_path = OUTPUT / f"{name}.txt"
                srt_path = OUTPUT / f"{name}.srt"

                with (
                    open(txt_path, "w", encoding="utf-8") as txt,
                    open(srt_path, "w", encoding="utf-8") as srt
                ):
                    for i, segment in enumerate(segments, 1):
                        content = segment.text.strip()
                        if not content:
                            continue

                        txt.write(
                            f"[{timestamp(segment.start)}] "
                            f"{content}\n"
                        )

                        srt.write(
                            f"{i}\n"
                            f"{timestamp(segment.start, True)}"
                            " --> "
                            f"{timestamp(segment.end, True)}\n"
                            f"{content}\n\n"
                        )

                        txt.flush()
                        srt.flush()

                        if duration:
                            percent = min(
                                100,
                                segment.end / duration * 100
                            )
                            self.send(
                                "progress", percent
                            )

                        self.send(
                            "status",
                            f"Trascritto fino a "
                            f"{timestamp(segment.end)}"
                        )

                # Il toggle riguarda solo video
                # scaricati da questa app.
                if is_url and keep:
                    destination = OUTPUT / (
                        f"{name}{media.suffix}"
                    )
                    shutil.copy2(media, destination)

                # I file nella cartella temporanea
                # vengono eliminati automaticamente.
                # I file locali non vengono toccati.

            self.send("progress", 100)
            self.send(
                "status", "Trascrizione completata!"
            )
            self.send(
                "finished",
                f"File creati:\n{name}.txt\n{name}.srt"
            )

        except Exception as exc:
            self.send("error", str(exc))


if __name__ == "__main__":
    root = tk.Tk()
    app = LectureScribe(root)
    root.mainloop()
