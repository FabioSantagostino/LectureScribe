import importlib.machinery
import importlib.util
import tempfile
import unittest
from pathlib import Path
from threading import Event
from types import SimpleNamespace
from unittest.mock import Mock, patch

from yt_dlp.utils import DownloadError

from lecturescribe_webex import _playlist_url, is_webex_playback


PLAYBACK = "https://campus.webex.com/recording/example/playback?siteurl=campus"
PLAYLIST = "https://media.webex.com/recording/hls.m3u8?sig=a%2Fb&part=1"
SOURCE = Path(__file__).resolve().parents[1] / "lecturescribe.pyw"
loader = importlib.machinery.SourceFileLoader("lecturescribe_gui", str(SOURCE))
spec = importlib.util.spec_from_loader(loader.name, loader)
gui = importlib.util.module_from_spec(spec)
loader.exec_module(gui)


class WebexPlaylistTests(unittest.TestCase):
    def test_matches_playback_without_treating_query_as_path(self):
        self.assertTrue(is_webex_playback(PLAYBACK))
        self.assertTrue(is_webex_playback("https://campus.webex.com/recording/playback/example"))
        for url in (PLAYLIST, "http://campus.webex.com/playback",
                    "https://campus.webex.com.evil.test/playback",
                    "https://user@webex.com/playback", "https://webex.com:8443/playback",
                    "https://webex.com/?path=/playback"):
            with self.subTest(url=url):
                self.assertFalse(is_webex_playback(url))

    def test_keeps_observed_signed_url_and_rejects_nonmedia_responses(self):
        response = SimpleNamespace(url=PLAYLIST, status=200, headers={
            "content-type": "application/vnd.apple.mpegurl",
        })
        self.assertEqual(_playlist_url(response), PLAYLIST)
        response.status = 403
        self.assertIsNone(_playlist_url(response))
        response.status = 200
        response.headers["content-type"] = "text/html; charset=utf-8"
        self.assertIsNone(_playlist_url(response))


class DownloadTests(unittest.TestCase):
    def setUp(self):
        folder = self.enterContext(tempfile.TemporaryDirectory())
        self.root = Path(folder)
        self.profile = self.root / "profile"
        self.enterContext(patch.object(gui, "WEBEX_PROFILE", self.profile))
        self.app = SimpleNamespace(
            check_cancel=Mock(), send=Mock(), t=lambda key: key, log=Mock(),
            inspect_webex_session=Mock(return_value=(PLAYLIST, [])),
            auth_cached_choice=None, auth_saved=None, remember_auth=Mock(),
            auth_event=Event(), save_config=Mock(),
        )
        self.ydl = self.enterContext(patch.object(gui.yt_dlp, "YoutubeDL"))
        self.ydl.side_effect = self.make_download
        self.options = []
        self.urls = []
        self.fail = set()

    def make_download(self, options):
        self.options.append(options)

        def extract(url, *, download):
            self.urls.append(url)
            path = Path(options["outtmpl"].replace("%(ext)s", "mp4"))
            if url in self.fail:
                path.write_bytes(b"incomplete")
                raise DownloadError("Unsupported URL")
            path.write_bytes(b"media")
            return {"title": "Lecture"}

        session = Mock()
        session.extract_info.side_effect = extract
        wrapper = unittest.mock.MagicMock()
        wrapper.__enter__.return_value = session
        return wrapper

    def test_observed_playlist_goes_directly_to_ytdlp(self):
        self.profile.mkdir()
        self.app.inspect_webex_session.return_value = (PLAYLIST, [{"name": "unused"}])
        with patch.object(gui, "add_to_ytdlp_cookiejar") as add_cookies:
            path, title = gui.App.download(self.app, PLAYBACK, self.root)
        self.assertEqual(self.urls, [PLAYLIST])
        self.assertEqual(path.read_bytes(), b"media")
        self.assertEqual(title, "Lecture")
        self.app.inspect_webex_session.assert_called_once_with(PLAYBACK, self.profile, False)
        add_cookies.assert_not_called()

    def test_direct_playlist_bypasses_browser_and_login(self):
        gui.App.download(self.app, PLAYLIST, self.root)
        self.assertEqual(self.urls, [PLAYLIST])
        self.app.inspect_webex_session.assert_not_called()

    def test_failed_playlist_falls_back_without_reusing_partial_media(self):
        self.fail.add(PLAYLIST)
        path, _ = gui.App.download(self.app, PLAYBACK, self.root)
        self.assertEqual(self.urls, [PLAYLIST, PLAYBACK])
        self.assertEqual(path.read_bytes(), b"media")

    def test_unsupported_playback_falls_back_to_interactive_login(self):
        self.fail.add(PLAYBACK)
        self.app.inspect_webex_session.side_effect = [(None, []), (PLAYLIST, [])]

        def select_login(message, *args):
            if message == "auth":
                self.app.auth_response = ("persistent",)
                self.app.auth_event.set()

        self.app.send.side_effect = select_login
        gui.App.download(self.app, PLAYBACK, self.root)
        self.assertEqual(self.urls, [PLAYBACK, PLAYLIST])
        self.app.inspect_webex_session.assert_called_with(PLAYBACK, self.profile, True)
