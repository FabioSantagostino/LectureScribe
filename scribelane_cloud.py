"""Optional, explicit cloud transcription. No credentials are saved by this module."""
from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path


def cloud_transcribe(media: Path, api_key: str, language: str, progress, cancelled):
    """Transcribe successive 7-minute MP3 clips via OpenAI's speech-to-text API.

    Returns (lines, notes). Timestamps represent *chunk starts*, not precise
    speech timestamps, and no fake SRT timings are generated.
    """
    import requests
    import imageio_ffmpeg

    if not api_key:
        raise ValueError("Cloud API key required")
    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    probe = subprocess.run(
        [ffmpeg, '-hide_banner', '-i', str(media)],
        capture_output=True, text=True, errors='replace'
    )
    import re
    duration_match = re.search(r'Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)', probe.stderr)
    if not duration_match:
        raise RuntimeError('Could not determine media duration')
    hh, mm, ss = duration_match.groups()
    duration = int(hh)*3600 + int(mm)*60 + float(ss)
    chunk_seconds = 420
    import math
    chunks = max(1, math.ceil(duration / chunk_seconds))
    lines = []
    for i in range(chunks):
        if cancelled():
            raise InterruptedError('Cloud transcription cancelled')
        start = i * chunk_seconds
        if start >= duration:
            break
        with tempfile.TemporaryDirectory(prefix='scribelane_cloud_') as tmp:
            audio = Path(tmp) / 'clip.mp3'
            proc = subprocess.run(
                [ffmpeg, '-nostdin', '-v', 'error', '-ss', str(start),
                 '-i', str(media), '-t', str(min(chunk_seconds, duration-start)),
                 '-vn', '-ac', '1', '-ar', '16000', '-codec:a', 'libmp3lame',
                 '-b:a', '48k', '-y', str(audio)],
                capture_output=True, text=True, errors='replace')
            if proc.returncode != 0 or not audio.is_file():
                raise RuntimeError('Audio compression failed; see local FFmpeg setup')
            if audio.stat().st_size > 24_000_000:
                raise RuntimeError('Audio chunk exceeds service upload limit')
            with audio.open('rb') as fh:
                response = requests.post(
                    'https://api.openai.com/v1/audio/transcriptions',
                    headers={'Authorization': 'Bearer ' + api_key},
                    data={'model': 'gpt-transcribe', **({'language': language} if language in ('it','en') else {})},
                    files={'file': ('lecture.mp3', fh, 'audio/mpeg')},
                    timeout=(20, 900))
            if response.status_code != 200:
                # Do not include response body or authentication information in logs.
                raise RuntimeError(f'Cloud API failed (HTTP {response.status_code})')
            spoken = response.json().get('text', '').strip()
            h, r = divmod(int(start), 3600)
            m, s = divmod(r, 60)
            lines.append(f'[~{h:02}:{m:02}:{s:02} chunk] {spoken}')
        progress(min(100, ((i + 1) * chunk_seconds / max(duration,1)) * 100))
    return lines
