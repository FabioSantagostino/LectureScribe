import itertools
import tempfile
import unittest
from pathlib import Path
from threading import Event
from types import SimpleNamespace
from unittest.mock import Mock

from test_webex import PLAYBACK, PLAYLIST, gui


class SettingsAndQueueTests(unittest.TestCase):
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
