"""Optional OpenVINO GenAI Whisper backend with automatic device benchmarking.

Only use a prepared IR for the exact selected Whisper model. Never silently
substitute a smaller model. If unavailable or slower, use faster-whisper CPU.
"""
from __future__ import annotations

import json
import math
import subprocess
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path


class OpenVINOUnavailable(Exception):
    pass


MODEL_MAP = {
    'small': 'whisper-small',
    'small.en': 'whisper-small.en',
    'turbo': 'whisper-large-v3-turbo',
    'large-v3': 'whisper-large-v3',
}


def model_directory(cache: Path, whisper_name: str) -> Path:
    return cache / MODEL_MAP[whisper_name]


def device_list():
    try:
        import openvino as ov
        available = ov.Core().available_devices
        return [d for d in ('GPU', 'NPU', 'CPU') if any(x == d or x.startswith(d + '.') for x in available)]
    except (ImportError, OSError, RuntimeError):
        return []


def convert_audio(media: Path, dest: Path, *, seconds=None):
    """Decode to PCM 16 kHz mono using the bundled ffmpeg when available."""
    import imageio_ffmpeg
    exe = imageio_ffmpeg.get_ffmpeg_exe()
    cmd = [exe, '-hide_banner', '-loglevel', 'error', '-y', '-i', str(media)]
    if seconds is not None:
        cmd.extend(['-t', str(seconds)])
    cmd.extend(['-ar', '16000', '-ac', '1', '-c:a', 'pcm_s16le', str(dest)])
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def read_audio(wav_path):
    import wave
    import numpy as np
    with wave.open(str(wav_path), 'rb') as f:
        if f.getframerate() != 16000 or f.getnchannels() != 1 or f.getsampwidth() != 2:
            raise OpenVINOUnavailable('Expected 16kHz mono PCM16 WAV')
        pcm = f.readframes(f.getnframes())
    return (np.frombuffer(pcm, dtype='<i2').astype('float32') / 32768.0).tolist()


def make_pipe(model_dir, device):
    try:
        import openvino_genai
        return openvino_genai.WhisperPipeline(str(model_dir), device)
    except Exception as exc:
        raise OpenVINOUnavailable('OpenVINO model compilation failed') from exc


def generate(pipe, speech, language=None):
    kwargs = {'task': 'transcribe', 'return_timestamps': True,
              'max_new_tokens': 448}
    if language in ('it', 'en'):
        kwargs['language'] = '<|' + language + '|>'
    return pipe.generate(speech, **kwargs)


def choose_device(model_dir: Path, short_speech, cache_dir: Path, *,
                  max_benchmark_seconds=150):
    """Benchmark only actual compatible devices; do not assume NPU is fastest.

    Cache decision by model and devices. Always compare against a CPU baseline
    separately in the caller before using accelerated inference.
    """
    available = device_list()
    if not available or not model_dir.exists():
        raise OpenVINOUnavailable('OpenVINO model or devices unavailable')
    try:
        import openvino
        driver = openvino.get_version()
    except Exception:
        driver = 'unknown'
    key = '|'.join([str(model_dir.resolve()), ','.join(available), driver])
    cache_dir.mkdir(parents=True, exist_ok=True)
    settings = cache_dir / 'benchmarks.json'
    try:
        data = json.loads(settings.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        data = {}
    if data.get('key') == key and data.get('device') in available:
        return data['device'], None
    scores = {}
    for device in available:
        started = time.perf_counter()
        try:
            pipe = make_pipe(model_dir, device)
            # Keep compilation out of inference measurement.
            infer_start = time.perf_counter()
            result = generate(pipe, short_speech)
            if not str(result):
                continue
            elapsed = time.perf_counter() - infer_start
            if elapsed <= max_benchmark_seconds:
                scores[device] = elapsed
        except Exception:
            continue
    if not scores:
        raise OpenVINOUnavailable('No compatible OpenVINO backend')
    device = min(scores, key=scores.get)
    settings.write_text(json.dumps({'key': key, 'device': device, 'scores': scores}), encoding='utf-8')
    return device, scores


def transcribe_if_available(media: Path, model: str, language: str | None,
                            models_root: Path, bench_root: Path, cancelled=lambda: False):
    """Yield start/end/text tuples; None if optional acceleration is absent.

    Benchmark 12 seconds of real input; OpenVINO backend must outperform the
    default CPU estimate (no score fabricated). Actual selection is based on
    measured OpenVINO GPU/NPU/CPU performance, and caller has fallback.
    """
    model_dir = model_directory(models_root, model)
    if not model_dir.exists() or not device_list():
        raise OpenVINOUnavailable('Matching converted model unavailable')
    with tempfile.TemporaryDirectory(prefix='lecturescribe_ov_') as temp:
        test = Path(temp) / 'sample.wav'
        convert_audio(media, test, seconds=12)
        speech = read_audio(test)
        device, _ = choose_device(model_dir, speech, bench_root)
        if cancelled():
            raise InterruptedError()
        # The existing faster-whisper CPU remains the preferred CPU path.
        # Do not switch merely because OpenVINO CPU happened to win its own race.
        if device == 'CPU':
            raise OpenVINOUnavailable('CPU is fastest; use existing CPU backend')
        pipe = make_pipe(model_dir, device)
        full_path = Path(temp) / 'full.wav'
        convert_audio(media, full_path)
        full_audio = read_audio(full_path)
        if cancelled():
            raise InterruptedError()
        chunk_samples = 120 * 16000
        overlap_samples = 1 * 16000
        output = []
        cursor = 0
        while cursor < len(full_audio):
            if cancelled():
                raise InterruptedError()
            end = min(len(full_audio), cursor + chunk_samples)
            start = max(0, cursor - overlap_samples if cursor else 0)
            result = generate(pipe, full_audio[start:end], language)
            chunks = getattr(result, 'chunks', None)
            if not chunks:
                raise OpenVINOUnavailable('Missing timestamped segments')
            offset = start / 16000
            accepted_until = cursor / 16000
            for c in chunks:
                abs_start = offset + float(c.start_ts)
                abs_end = offset + float(c.end_ts)
                if abs_end <= accepted_until:
                    continue
                text = str(c.text).strip()
                if text:
                    output.append((max(abs_start,accepted_until), abs_end, text))
            cursor = end
        return output, device
