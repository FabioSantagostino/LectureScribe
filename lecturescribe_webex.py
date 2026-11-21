"""Observe the Webex player in an isolated Playwright browser.

No password interception; only cookies scoped to Webex domains are copied into
an in-memory cookie jar for the legacy yt-dlp fallback.
"""
from __future__ import annotations

from http.cookiejar import Cookie
from pathlib import Path
from time import monotonic
from urllib.parse import urlsplit


class WebexBrowserError(RuntimeError):
    pass


WEBEX_HOST_SUFFIXES = (".webex.com", ".webex.com.cn")


def _allowed_domain(domain: str) -> bool:
    domain = domain.lower().lstrip('.')
    return any(domain == suffix[1:] or domain.endswith(suffix)
               for suffix in WEBEX_HOST_SUFFIXES)


def _webex_url(url: str):
    try:
        parsed = urlsplit(url)
        if (parsed.scheme == 'https' and _allowed_domain(parsed.hostname or '')
                and parsed.username is None and parsed.port in (None, 443)):
            return parsed
    except ValueError:
        pass
    return None


def is_webex_playback(url: str) -> bool:
    parsed = _webex_url(url)
    if parsed is None:
        return False
    path = parsed.path.lower()
    return 'playback' in path.split('/') and not path.endswith('.m3u8')


def _playlist_url(response):
    parsed = _webex_url(response.url)
    if not parsed or not parsed.path.lower().endswith('.m3u8') or response.status != 200:
        return None
    content_type = response.headers.get('content-type', '').partition(';')[0].strip().lower()
    if content_type in ('text/html', 'application/xhtml+xml', 'application/json'):
        return None
    return response.url


def add_to_ytdlp_cookiejar(ydl, cookies):
    """Do not export session credentials to a plaintext Netscape file."""
    count = 0
    for item in cookies:
        domain = str(item.get('domain') or '')
        name = item.get('name')
        if not name or not _allowed_domain(domain):
            continue
        host_only = not domain.startswith('.')
        path = str(item.get('path') or '/')
        expires = item.get('expires', -1)
        cookie = Cookie(
            version=0, name=str(name), value=str(item.get('value', '')),
            port=None, port_specified=False,
            domain=domain, domain_specified=not host_only,
            domain_initial_dot=not host_only,
            path=path, path_specified=True,
            secure=bool(item.get('secure', False)),
            expires=int(expires) if expires is not None and expires > 0 else None,
            discard=expires is None or expires <= 0,
            comment=None, comment_url=None, rest={'HttpOnly': item.get('httpOnly', False)},
            rfc2109=False,
        )
        ydl.cookiejar.set_cookie(cookie)
        count += 1
    return count


def inspect_webex(profile_dir: Path | None, login_url: str, *, interactive=False,
                  on_browser_ready=None, check_cancel=lambda: None):
    """Return the observed HLS URL and cookies for the original-link fallback."""
    if not _webex_url(login_url):
        raise WebexBrowserError('Expected HTTPS Webex recording URL')
    try:
        from playwright.sync_api import Error, sync_playwright
    except ImportError:
        raise WebexBrowserError('Playwright is missing') from None

    check_cancel()
    try:
        with sync_playwright() as p:
            # The anonymous probe uses a temporary profile. Login takes place
            # only in the app-owned profile, never in a personal browser profile.
            channel = {} if Path(p.chromium.executable_path).is_file() else {'channel': 'chrome'}
            context = p.chromium.launch_persistent_context(
                user_data_dir=str(profile_dir) if profile_dir else '', **channel,
                headless=not interactive, accept_downloads=False, chromium_sandbox=True,
            )
            try:
                playlists = []

                def observe(response):
                    url = _playlist_url(response)
                    if url and url not in playlists:
                        playlists.append(url)

                if interactive or is_webex_playback(login_url):
                    context.on('response', observe)
                    page = context.pages[0] if context.pages else context.new_page()
                    try:
                        page.goto(login_url, wait_until='commit', timeout=10000)
                    except Error:
                        # A slow load or SSO redirect can still complete.
                        pass
                    check_cancel()
                    if interactive and on_browser_ready:
                        on_browser_ready()
                    if is_webex_playback(login_url):
                        deadline = monotonic() + 8
                        while not playlists and monotonic() < deadline:
                            check_cancel()
                            # Pump Playwright events while the player loads.
                            page.wait_for_timeout(200)
                check_cancel()
                cookies = context.cookies([login_url]) if profile_dir else []
                return playlists[0] if playlists else None, cookies
            finally:
                context.close()
    except Error:
        raise WebexBrowserError('Could not open the Webex browser session') from None


def logout(profile_dir: Path):
    """Remove dedicated profile; caller must confirm and close any active browser."""
    import shutil
    if profile_dir.exists():
        shutil.rmtree(profile_dir)
