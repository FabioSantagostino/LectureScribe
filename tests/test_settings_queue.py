import itertools
import subprocess
import tempfile
import unittest
from pathlib import Path
from threading import Event
from types import SimpleNamespace
from unittest.mock import Mock

from test_webex import PLAYBACK, PLAYLIST, gui


class SettingsAndQueueTests(unittest.TestCase):
    def test_download_only_preserves_format_without_transcribing(self):
        app = gui.App.__new__(gui.App)
        app.send, app.log = Mock(), Mock()
        app.stop_event = Event()
        app.transcribe_engine = Mock()
        app.try_parallel_queue = Mock()
        app.t = lambda key: key
        app.run_media_command = Mock()

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
            self.assertEqual({p.name: p.read_bytes() for p in folder.iterdir()},
                             {"Lecture.webm": b"video", "Lecture_2.webm": b"video"})
            app.run_media_command.assert_not_called()
            app.transcribe_engine.assert_not_called()
            app.try_parallel_queue.assert_not_called()
            app.send.assert_called_with("done_downloads", (2, 0, str(folder)))

    def test_split_preserves_codec_and_respects_size_limit(self):
        import av

        app = gui.App.__new__(gui.App)
        app.send, app.log = Mock(), Mock()
        app.t = lambda key: key
        app.stop_event = Event()
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            media = folder / "source.mp4"
            subprocess.run([
                gui.imageio_ffmpeg.get_ffmpeg_exe(), "-nostdin", "-v", "error",
                "-f", "lavfi", "-i", "testsrc2=size=160x120:rate=10", "-t", "6",
                "-c:v", "mpeg4", "-g", "10", str(media),
            ], check=True, capture_output=True)
            limit = media.stat().st_size // 2
            app.save_recording(media, folder / "Lecture.mp4", limit)
            parts = sorted((folder / "Lecture - parts").glob("Part-*.mp4"))
            self.assertGreater(len(parts), 1)
            self.assertFalse((folder / "Lecture.mp4").exists())
            frames = 0
            for part in parts:
                self.assertLessEqual(part.stat().st_size, limit)
                with av.open(str(part)) as recording:
                    self.assertEqual(recording.streams.video[0].codec_context.name, "mpeg4")
                    frames += sum(1 for _ in recording.decode(video=0))
            self.assertEqual(frames, 60)

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
