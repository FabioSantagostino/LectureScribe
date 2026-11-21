"""Optional GitHub release updater for public repositories on Windows.

The app never executes downloaded files without user confirmation. The released
ZIP must have a GitHub SHA-256 digest and contain exactly the expected EXE.
"""
from __future__ import annotations
import hashlib
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import zipfile
from pathlib import Path

import requests

VERSION = '1.5.2'
ASSET_NAME = 'LectureScribe-Windows-x64.zip'


def version_tuple(text):
    return tuple(int(x) for x in text.lstrip('v').split('.')[:3])


def fetch_release(repo):
    if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', repo):
        raise ValueError('Repository must have owner/repo format')
    resp = requests.get(f'https://api.github.com/repos/{repo}/releases/latest',
                        headers={'Accept': 'application/vnd.github+json'}, timeout=15)
    resp.raise_for_status()
    info = resp.json()
    asset = next((a for a in info.get('assets', []) if a['name'] == ASSET_NAME), None)
    if not asset:
        raise RuntimeError('No Windows release package was found')
    return info['tag_name'], asset


def stage_update(asset, destination):
    """Download and hash-check a release ZIP before extracting only the EXE."""
    digest = asset.get('digest') or ''
    if not re.fullmatch(r'sha256:[0-9a-fA-F]{64}', digest):
        raise RuntimeError('Missing SHA-256 release digest; update refused')
    url = asset.get('browser_download_url', '')
    if not url.startswith('https://github.com/'):
        raise RuntimeError('Untrusted asset URL')
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=True)
    archive = destination / ASSET_NAME
    sha = hashlib.sha256()
    with requests.get(url, stream=True, timeout=(20, 120), allow_redirects=True) as response:
        response.raise_for_status()
        with archive.open('wb') as f:
            for chunk in response.iter_content(256 * 1024):
                if chunk:
                    sha.update(chunk)
                    f.write(chunk)
    if sha.hexdigest().lower() != digest.split(':', 1)[1].lower():
        raise RuntimeError('SHA-256 mismatch; downloaded update rejected')
    with zipfile.ZipFile(archive) as z:
        entry = next((x for x in z.infolist() if x.filename == 'LectureScribe.exe'), None)
        if not entry or entry.file_size > 1_500_000_000:
            raise RuntimeError('Invalid release archive')
        new_exe = destination / 'LectureScribe-new.exe'
        with z.open(entry) as f, new_exe.open('wb') as out:
            shutil.copyfileobj(f, out)
    return new_exe


def run_update_mode(args):
    """Invoked from an isolated copy of the *old* exe after UI exits."""
    if len(args) != 3:
        return 2
    pid, target, new_binary = args
    target, new_binary = Path(target), Path(new_binary)
    for _ in range(120):
        try:
            import ctypes
            PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
            SYNCHRONIZE = 0x00100000
            handle = ctypes.windll.kernel32.OpenProcess(SYNCHRONIZE | PROCESS_QUERY_LIMITED_INFORMATION, False, int(pid))
            if not handle:
                break
            result = ctypes.windll.kernel32.WaitForSingleObject(handle, 1000)
            ctypes.windll.kernel32.CloseHandle(handle)
            if result == 0:
                break
        except (ValueError, OSError):
            break
        time.sleep(.1)
    try:
        if not target.is_file() or not new_binary.is_file():
            return 3
        replacement = target.with_suffix('.updated.exe')
        shutil.copy2(new_binary, replacement)
        os.replace(str(replacement), str(target))
        subprocess.Popen([str(target)], close_fds=True)
        return 0
    except OSError:
        return 4


def launch_installer(new_binary):
    """Keep app update opt-in; no elevation, persistence, or silent install."""
    if not getattr(sys, 'frozen', False):
        raise RuntimeError('In-app install requires the packaged EXE')
    target = Path(sys.executable).resolve()
    if not os.access(target.parent, os.W_OK):
        raise RuntimeError('Install location is read-only')
    helper = Path(new_binary).parent / 'LectureScribe-updater.exe'
    shutil.copy2(target, helper)
    subprocess.Popen([str(helper), '--apply-update', str(os.getpid()),
                      str(target), str(new_binary)], close_fds=True)
