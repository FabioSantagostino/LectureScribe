"""Receive one authorized Webex playlist from the user's browser extension."""
from __future__ import annotations

from html import escape
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from secrets import token_urlsafe
from threading import Event, Lock, Thread
from time import monotonic
from urllib.parse import urlsplit
from webbrowser import open as open_browser


class WebexBrowserError(RuntimeError):
    pass


def _webex_path(url: str) -> str:
    try:
        parsed = urlsplit(url)
        host = parsed.hostname or ""
        if (parsed.scheme == "https" and parsed.username is None
                and parsed.port in (None, 443)
                and host.endswith((".webex.com", ".webex.com.cn"))):
            return parsed.path.lower()
    except ValueError:
        pass
    return ""


def is_webex_playback(url: str) -> bool:
    path = _webex_path(url)
    return "playback" in path.split("/") and not path.endswith(".m3u8")


def capture_playlist(url, *, check_cancel, on_playback=lambda: None, timeout=180):
    if not is_webex_playback(url):
        raise WebexBrowserError("webex_capture_failed")
    token = token_urlsafe(32)
    route = f"/scribelane/{token}"
    ready = Event()
    complete = Event()
    result_lock = Lock()
    playlist = None

    class Handler(BaseHTTPRequestHandler):
        def setup(self):
            super().setup()
            self.connection.settimeout(2)

        def log_message(self, *args):
            pass

        def reply(self, status, body=b""):
            self.send_response(status)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("Content-Security-Policy", "default-src 'none'; frame-ancestors 'none'")
            self.end_headers()
            if body:
                self.wfile.write(body)

        def valid_host(self):
            return self.headers.get("Host") == f"127.0.0.1:{self.server.server_port}"

        def do_GET(self):
            if not self.valid_host() or self.path != route:
                self.reply(404)
                return
            self.reply(200, (
                "<!doctype html><meta charset=utf-8><title>ScribeLane</title>"
                "<h1>ScribeLane</h1><p>Install or enable the ScribeLane browser extension "
                "and retry if Webex does not open automatically.</p>"
                f'<a id="playback" href="{escape(url, quote=True)}">Open Webex</a>'
            ).encode("utf-8"))

        def do_POST(self):
            nonlocal playlist
            if not self.valid_host():
                self.reply(404)
                return
            if self.path == route + "/ready":
                ready.set()
                self.reply(204)
                return
            if self.path != route + "/playlist" or not ready.is_set():
                self.reply(404)
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                candidate = self.rfile.read(length).decode("utf-8") if 0 < length <= 16384 else ""
            except (OSError, ValueError):
                self.reply(400)
                return
            if not _webex_path(candidate).endswith(".m3u8") or any(c.isspace() for c in candidate):
                self.reply(400)
                return
            with result_lock:
                if not complete.is_set():
                    playlist = candidate
                    complete.set()
            self.reply(204)

    check_cancel()
    try:
        with ThreadingHTTPServer(("127.0.0.1", 0), Handler) as server:
            thread = Thread(target=server.serve_forever, kwargs={"poll_interval": .2}, daemon=True)
            thread.start()
            try:
                if not open_browser(f"http://127.0.0.1:{server.server_port}{route}", new=2):
                    raise WebexBrowserError("webex_browser_failed")
                deadline = monotonic() + 20
                while not ready.wait(.2):
                    check_cancel()
                    if monotonic() >= deadline:
                        raise WebexBrowserError("webex_extension_missing")
                on_playback()
                deadline = monotonic() + timeout
                while not complete.wait(.2):
                    check_cancel()
                    if monotonic() >= deadline:
                        raise WebexBrowserError("webex_capture_failed")
                check_cancel()
                return playlist
            finally:
                server.shutdown()
                thread.join()
    except OSError:
        raise WebexBrowserError("webex_browser_failed") from None
