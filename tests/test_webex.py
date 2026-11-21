import importlib.machinery
import importlib.util
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock, patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from yt_dlp.utils import DownloadError
from lecturescribe_webex import capture_playlist, is_webex_playback

PLAYBACK = "https://campus.webex.com/recording/playback/example"
PLAYLIST = "https://media.webex.com/recording/hls.m3u8?sig=a%2Fb&part=1"
source = Path(__file__).resolve().parents[1] / "lecturescribe.pyw"
loader = importlib.machinery.SourceFileLoader("lecturescribe_gui", str(source))
spec = importlib.util.spec_from_loader(loader.name, loader)
gui = importlib.util.module_from_spec(spec)
loader.exec_module(gui)


class WebexTests(unittest.TestCase):
    def test_matches_actual_webex_playback_paths(self):
        self.assertTrue(is_webex_playback(PLAYBACK))
        self.assertTrue(is_webex_playback("https://campus.webex.com/recording/example/playback"))
        for url in (PLAYLIST, "http://campus.webex.com/playback",
                    "https://campus.webex.com.evil.test/playback",
                    "https://user@webex.com/playback", "https://webex.com:8443/playback",
                    "https://webex.com/?path=/playback"):
            self.assertFalse(is_webex_playback(url), url)

    def test_loopback_receives_only_the_scoped_webex_playlist(self):
        def post(url, data=b""):
            with urlopen(Request(url, data=data), timeout=3) as response:
                self.assertEqual(response.status, 204)

        def extension(bridge, *, new):
            self.assertEqual(new, 2)
            with urlopen(bridge, timeout=3) as response:
                self.assertIn(PLAYBACK, response.read().decode("utf-8"))
                self.assertEqual(response.headers["Referrer-Policy"], "no-referrer")
            with self.assertRaises(HTTPError) as wrong_token:
                post(bridge + "bad/ready")
            self.assertEqual(wrong_token.exception.code, 404)
            post(bridge + "/ready")
            with self.assertRaises(HTTPError) as wrong_host:
                post(bridge + "/playlist", b"https://webex.com.other.invalid/video.m3u8")
            self.assertEqual(wrong_host.exception.code, 400)
            post(bridge + "/playlist", PLAYLIST.encode())
            return True

        callback = Mock()
        with patch("lecturescribe_webex.open_browser", side_effect=extension):
            self.assertEqual(capture_playlist(PLAYBACK, check_cancel=Mock(), on_playback=callback), PLAYLIST)
        callback.assert_called_once()

    def test_download_tries_original_url_without_opening_browser(self):
        app = SimpleNamespace(check_cancel=Mock(), send=Mock(), t=lambda key: key, log=Mock())
        for source_url in (PLAYBACK, PLAYLIST):
            with self.subTest(source_url=source_url), tempfile.TemporaryDirectory() as tmp:
                folder = Path(tmp)
                (folder / "recording.mp4").write_bytes(b"media")
                downloader = MagicMock()
                downloader.__enter__.return_value.extract_info.return_value = {"title": "Lecture"}
                with patch.object(gui, "capture_playlist", return_value=PLAYLIST) as capture:
                    with patch.object(gui.yt_dlp, "YoutubeDL", return_value=downloader) as yt:
                        path, title = gui.App.download(app, source_url, folder)
                        self.assertNotIn("cookiefile", yt.call_args.args[0])
                        self.assertNotIn("cookiesfrombrowser", yt.call_args.args[0])
                self.assertEqual(path.name, "recording.mp4")
                self.assertEqual(title, "Lecture")
                downloader.__enter__.return_value.extract_info.assert_called_once_with(source_url, download=True)
                capture.assert_not_called()

    def test_failed_webex_download_uses_extension_and_isolates_partial_files(self):
        app = SimpleNamespace(check_cancel=Mock(), send=Mock(), t=lambda key: key, log=Mock())
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            first, second = MagicMock(), MagicMock()
            (folder / "recording.mp4").write_bytes(b"partial media")

            def download_playlist(*args, **kwargs):
                (folder / "hls" / "recording.mp4").write_bytes(b"complete")
                return {"title": "Lecture"}

            first.__enter__.return_value.extract_info.side_effect = DownloadError("unavailable")
            second.__enter__.return_value.extract_info.side_effect = download_playlist
            with patch.object(gui, "capture_playlist", return_value=PLAYLIST) as capture:
                with patch.object(gui.yt_dlp, "YoutubeDL", side_effect=[first, second]):
                    path, _ = gui.App.download(app, PLAYBACK, folder)
            capture.assert_called_once()
            second.__enter__.return_value.extract_info.assert_called_once_with(PLAYLIST, download=True)
            self.assertEqual(path.read_bytes(), b"complete")
