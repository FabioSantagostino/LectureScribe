"""Isolated API providers for LectureScribe. Never log secrets or raw HTTP responses."""
from __future__ import annotations

import json
import math
import re
import subprocess
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable


MODELS = {
    'groq': ('whisper-large-v3-turbo', 'whisper-large-v3'),
    'openai': ('gpt-transcribe', 'gpt-4o-mini-transcribe', 'gpt-4o-transcribe'),
    'gemini': ('gemini-2.5-flash',),
}


class ProviderError(Exception):
    def __init__(self, category='service', retry_after=None):
        self.category = category
        self.retry_after = retry_after
        super().__init__(category)  # Intentionally NEVER include response or key.


def categorize(status: int, retry_after=None):
    category = {400:'invalid_request', 401:'authentication', 403:'permission',
                404:'model_unavailable', 408:'temporary', 413:'file_too_large',
                429:'rate_limited', 500:'temporary', 502:'temporary',
                503:'temporary', 504:'temporary'}.get(status, 'service')
    if status == 429:
        category = 'rate_limited'  # May also represent exhausted project quota.
    try:
        seconds = min(3600, max(0, float(retry_after))) if retry_after else None
    except (ValueError, TypeError):
        seconds = None
    return ProviderError(category, seconds)


def verify_key(provider, secret):
    """Non-billable metadata request; model access and quota remain unverified."""
    import requests
    urls = {'openai':'https://api.openai.com/v1/models',
            'groq':'https://api.groq.com/openai/v1/models',
            'gemini':'https://generativelanguage.googleapis.com/v1beta/models'}
    if provider not in urls or not secret:
        raise ProviderError('authentication')
    headers = ({'x-goog-api-key':secret} if provider == 'gemini'
               else {'Authorization':f'Bearer {secret}'})
    try:
        res = requests.get(urls[provider], headers=headers, timeout=(8, 20))
    except requests.RequestException:
        raise ProviderError('network') from None
    if res.status_code != 200:
        raise categorize(res.status_code, res.headers.get('Retry-After'))
    return True


def available_gemini_models(secret):
    import requests
    try:
        r = requests.get('https://generativelanguage.googleapis.com/v1beta/models',
                         headers={'x-goog-api-key':secret}, timeout=(8, 20))
    except requests.RequestException:
        raise ProviderError('network') from None
    if r.status_code != 200:
        raise categorize(r.status_code, r.headers.get('Retry-After'))
    # Listing generateContent models alone does NOT prove audio capability.
    return [m['name'].removeprefix('models/') for m in r.json().get('models', [])
            if 'generateContent' in m.get('supportedGenerationMethods', [])
            and 'gemini' in m.get('name','')]


def _duration(ffmpeg, media):
    proc = subprocess.run([ffmpeg, '-hide_banner', '-i', str(media)],
                          capture_output=True, text=True, errors='replace')
    match = re.search(r'Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)', proc.stderr)
    if not match:
        raise ProviderError('media_metadata')
    a,b,c = match.groups()
    return int(a)*3600 + int(b)*60 + float(c)


def chunks(media: Path, output: Path, *, seconds=360, overlap=1.5):
    """Bounded mono speech MP3 chunks; overlap is accounted for in offsets."""
    import imageio_ffmpeg
    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    total = _duration(ffmpeg, media)
    if total <= 0:
        raise ProviderError('media_metadata')
    count = math.ceil(total / seconds)
    for i in range(count):
        start = i*seconds - (overlap if i else 0)
        start = max(0, start)
        duration = min(seconds + (overlap if i else 0), total-start)
        target = output / f'chunk_{i:05}.mp3'
        proc = subprocess.run([ffmpeg, '-nostdin', '-v', 'error', '-ss', str(start),
             '-i', str(media), '-t', str(duration), '-vn', '-ac', '1', '-ar', '16000',
             '-codec:a', 'libmp3lame', '-b:a', '48k', '-y', str(target)],
            capture_output=True)
        if proc.returncode or not target.is_file():
            raise ProviderError('audio_conversion')
        if target.stat().st_size > 20_000_000:
            raise ProviderError('file_too_large')
        yield i, count, start, target


def transcribe_chunk(provider, model, secret, audio:Path, language='auto'):
    """Return literal text only. No fake word-aligned timestamps."""
    if provider in ('groq','openai'):
        import requests
        url = ('https://api.groq.com/openai/v1/audio/transcriptions' if provider == 'groq'
               else 'https://api.openai.com/v1/audio/transcriptions')
        fields = {'model':model, 'response_format':'json'}
        if language in ('it','en'):
            fields['language'] = language
        try:
            with audio.open('rb') as src:
                res = requests.post(url, headers={'Authorization':f'Bearer {secret}'},
                    files={'file':('audio.mp3',src,'audio/mpeg')}, data=fields, timeout=(15,600))
        except requests.RequestException:
            raise ProviderError('network') from None
        if res.status_code != 200:
            raise categorize(res.status_code, res.headers.get('Retry-After'))
        return res.json().get('text','').strip()
    if provider == 'gemini':
        try:
            from google import genai
        except ImportError:
            raise ProviderError('missing_dependency') from None
        try:
            with genai.Client(api_key=secret) as client:
                uploaded = client.files.upload(file=str(audio))
                try:
                    response = client.models.generate_content(
                        model=model,
                        contents=[uploaded, 'Transcribe every audible word verbatim in the original language. '
                                  'Preserve code switching, technical terms and repetitions. '
                                  'Do not translate, summarize, infer, or add context. '
                                  'Return ONLY the transcription text.'])
                    return (response.text or '').strip()
                finally:
                    try:
                        client.files.delete(name=uploaded.name)
                    except Exception:
                        pass
        except ProviderError:
            raise
        except Exception as exc:
            # Avoid showing SDK exception messages that could include sensitive data.
            code = getattr(exc, 'code', None) or getattr(exc, 'status_code', None)
            if isinstance(code, int):
                raise categorize(code) from None
            raise ProviderError('service') from None
    raise ProviderError('unsupported_provider')


def stitch(previous, current):
    """Conservative exact-token overlap removal; uncertain repeats are retained."""
    prev_tokens, cur_tokens = previous.split(), current.split()
    upto = min(25, len(prev_tokens), len(cur_tokens))
    for n in range(upto, 2, -1):
        def norm(tokens):
            return [re.sub(r'\W+', '', t).casefold() for t in tokens]
        if norm(prev_tokens[-n:]) == norm(cur_tokens[:n]):
            return ' '.join(cur_tokens[n:])
    return current


def transcribe_long(media, *, provider, model, secret, language='auto', output_dir,
                    job_id, key_id="", progress=lambda _:None, cancelled=lambda:False):
    """Persistent per-chunk checkpoint, resumable without repeating completed paid uploads."""
    output_dir = Path(output_dir)
    checkpoint = output_dir / f'{job_id}.cloud-checkpoint.json'
    saved = {}
    if checkpoint.exists():
        try:
            saved = json.loads(checkpoint.read_text(encoding='utf-8'))
        except (ValueError, OSError):
            pass
    signature = {'provider':provider,'model':model,'language':language,
                 'size':media.stat().st_size,'mtime':media.stat().st_mtime_ns,
                 'key_id':key_id}
    # Do not reuse results across a different model, key/provider or modified recording.
    if saved.get('signature') != signature:
        saved = {'signature':signature,'completed':{}}
    with tempfile.TemporaryDirectory(prefix='lecturescribe_chunks_') as td:
        for i, total, start, part in chunks(media, Path(td)):
            if cancelled():
                raise InterruptedError('Cancelled')
            key = str(i)
            if key not in saved['completed']:
                result = transcribe_chunk(provider, model, secret, part, language)
                saved['completed'][key] = {'offset':start,'text':result}
                temp = checkpoint.with_suffix('.tmp')
                temp.write_text(json.dumps(saved,ensure_ascii=False), encoding='utf-8')
                temp.replace(checkpoint)
            progress((i+1)/total*100)
    lines, previous = [], ''
    for idx in sorted(saved['completed'], key=int):
        segment = saved['completed'][idx]
        content = stitch(previous, segment['text']) if previous else segment['text']
        previous = segment['text']
        h,rem = divmod(int(segment['offset']),3600)
        m,s = divmod(rem,60)
        lines.append(f'[~{h:02}:{m:02}:{s:02} chunk] {content}')
    return lines
