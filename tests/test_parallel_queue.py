import tempfile
import unittest
from pathlib import Path
from threading import Event
from unittest.mock import Mock, patch

from test_webex import gui


class ParallelQueueTests(unittest.TestCase):
    def test_device_error_retries_item_and_preserves_unique_output_names(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            sources = []
            for index in range(4):
                media = folder / f"sample-{index}.wav"
                media.touch()
                sources.append({"source": str(media), "name": "Same name"})

            app = gui.App.__new__(gui.App)
            app.stop_event = Event()
            app.log = Mock()
            app.send = Mock()
            app.t = lambda key: key
            app.process_one = Mock()

            def infer(media, language, pipe, device, cancelled):
                if device == "NPU":
                    raise RuntimeError("device lost")
                return [(0, 1, media.stem)]

            job = {"engine": "local", "model": "small", "spoken": "en",
                   "name": None, "transcripts": folder, "videos": folder}
            with patch.object(gui, "prepare_parallel", return_value={"GPU": object(), "NPU": object()}):
                with patch.object(gui, "transcribe_on_device", side_effect=infer):
                    app.worker_batch(job, sources)

            retry = app.process_one.call_args.args[0]
            self.assertEqual(app.process_one.call_count, 1)
            self.assertEqual(retry["source"], sources[1]["source"])
            self.assertEqual(retry["name"], "Same name_2")
            for name in ("Same name", "Same name_3", "Same name_4"):
                self.assertTrue((folder / f"{name}.txt").is_file())
                self.assertTrue((folder / f"{name}.srt").is_file())
                self.assertTrue((folder / f"{name}.md").is_file())
            app.send.assert_called_with("done_batch", (4, 0, str(folder)))
