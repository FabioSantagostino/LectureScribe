import itertools
import tempfile
import unittest
from pathlib import Path
from threading import Event
from types import SimpleNamespace
from unittest.mock import Mock

from test_webex import PLAYBACK, PLAYLIST, gui


class SettingsAndQueueTests(unittest.TestCase):
    def test_download_only_compresses_without_transcribing(self):
        app = gui.App.__new__(gui.App)
        app.send, app.log = Mock(), Mock()
        app.stop_event = Event()
        app.transcribe_engine = Mock()
        app.try_parallel_queue = Mock()
        app.compress_recording = Mock()

        def download(url, temp):
            media = temp / "recording.webm"
            media.write_bytes(b"video")
            return media, "Lecture"

        app.download = download
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            job = {"name": None, "transcripts": folder, "videos": folder, "keep": False,
                   "download_only": True, "engine": "local"}
            app.worker_batch(job, [{"source": PLAYBACK}, {"source": PLAYLIST}])
            self.assertEqual(app.compress_recording.call_count, 2)
            self.assertEqual(app.compress_recording.call_args.args[1], folder / "Lecture.mp4")
            app.transcribe_engine.assert_not_called()
            app.try_parallel_queue.assert_not_called()
            app.send.assert_called_with("done_downloads", (2, 0, str(folder)))

    def test_kept_download_survives_transcription_failure(self):
        app = gui.App.__new__(gui.App)
        app.send = Mock()
        app.log = Mock()
        app.t = lambda key: key
        app.stop_event = Event()
        app.transcribe_engine = Mock(side_effect=RuntimeError("transcription failed"))

        def download(url, temp):
            media = temp / "recording.mp4"
            media.write_bytes(b"video")
            return media, "Lecture"

        app.download = download
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            job = {"source": PLAYBACK, "name": None, "transcripts": folder,
                   "videos": folder, "keep": True}
            with self.assertRaisesRegex(RuntimeError, "transcription failed"):
                app.process_one(job)
            retained = folder / "Lecture.mp4"
            self.assertEqual(retained.read_bytes(), b"video")
            app.transcribe_engine.assert_called_once_with(job, retained, True)

    def test_bulk_links_keep_titles_order_and_signed_query(self):
        items = gui.parse_queue(f"{PLAYBACK}\n\nFirst lesson | {PLAYBACK}\n{PLAYLIST}\n")
        self.assertEqual(items, [
            {"source": PLAYBACK, "name": "First lesson"},
            {"source": PLAYLIST, "name": None},
        ])
        with self.assertRaisesRegex(ValueError, "3"):
            gui.parse_queue(f"{PLAYBACK}\n\nnot-a-link")

    def test_exports_only_selected_formats(self):
        app = gui.App.__new__(gui.App)
        app.stop_event = Event()
        app.log = Mock()
        app.t = lambda key: key
        segment = SimpleNamespace(start=1.25, end=2.5, text="Example")
        for size in range(1, 4):
            for formats in itertools.combinations(gui.OUTPUT_FORMATS, size):
                with self.subTest(formats=formats), tempfile.TemporaryDirectory() as tmp:
                    folder = Path(tmp)
                    job = {"name": "Lecture", "transcripts": folder, "formats": formats}
                    exports = app.write_local_transcript(job, [segment], approximate=True)
                    self.assertEqual(set(exports), set(formats))
                    self.assertEqual({p.suffix[1:] for p in folder.iterdir()}, set(formats))
                    if "srt" in exports:
                        self.assertIn("00:00:01,250 --> 00:00:02,500", exports["srt"].read_text())
                    if "md" in exports:
                        self.assertIn("# Lecture", exports["md"].read_text(encoding="utf-8"))
