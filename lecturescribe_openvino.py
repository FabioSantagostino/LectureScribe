"""Optional OpenVINO GenAI Whisper backend with automatic device benchmarking.

Only use a prepared IR for the exact selected Whisper model. Never silently
substitute a smaller model. If unavailable or slower, use faster-whisper CPU.
"""
from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
import subprocess
import tempfile
import time
import wave
from pathlib import Path


class OpenVINOUnavailable(Exception):
    def __init__(self, reason):
        super().__init__(reason)
        self.reason = reason


MODEL_MAP = {
    'small': 'whisper-small',
    'small.en': 'whisper-small.en',
    'turbo': 'whisper-large-v3-turbo',
    'large-v3': 'whisper-large-v3',
}


def model_directory(cache: Path, whisper_name: str) -> Path:
    return cache / MODEL_MAP[whisper_name]


def resolve_model(models_root, name, on_status):
    prepared = model_directory(models_root, name)
    if (prepared / 'openvino_encoder_model.xml').is_file():
        return prepared
    from huggingface_hub import snapshot_download

    on_status('ov_model')
    try:
        return Path(snapshot_download(
            repo_id=f'OpenVINO/{MODEL_MAP[name]}-int8-ov',
            cache_dir=models_root / 'downloads',
            allow_patterns=['*.xml', '*.bin', '*.json', '*.txt', '*.model', 'LICENSE'],
        ))
    except Exception as exc:
        raise OpenVINOUnavailable('MODEL_DOWNLOAD') from exc


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
    with wave.open(str(wav_path), 'rb') as f:
        if f.getframerate() != 16000 or f.getnchannels() != 1 or f.getsampwidth() != 2:
            raise OpenVINOUnavailable('AUDIO_FORMAT')
        return decode_pcm(f.readframes(f.getnframes()))


def decode_pcm(pcm):
    import numpy as np
    return (np.frombuffer(pcm, dtype='<i2').astype('float32') / 32768.0).tolist()


def make_pipe(model_dir, device):
    try:
        import openvino_genai
        return openvino_genai.WhisperPipeline(str(model_dir), device)
    except Exception as exc:
        raise OpenVINOUnavailable('MODEL_COMPILE') from exc


def generate(pipe, speech, language=None):
    kwargs = {'task': 'transcribe', 'return_timestamps': True,
              'max_new_tokens': 448}
    if language in ('it', 'en'):
        kwargs['language'] = '<|' + language + '|>'
    return pipe.generate(speech, **kwargs)


def choose_device(model_dir: Path, short_speech, cache_dir: Path, *,
                  available, cancelled, max_benchmark_seconds=150):
    """Benchmark only actual compatible devices; do not assume NPU is fastest.

    Cache decision by model and devices. Always compare against a CPU baseline
    separately in the caller before using accelerated inference.
    """
    try:
        import openvino
        driver = openvino.get_version()
    except Exception:
        driver = 'unknown'
    key = '|'.join(['v2', str(model_dir.resolve()), ','.join(available), driver])
    cache_dir.mkdir(parents=True, exist_ok=True)
    settings = cache_dir / 'benchmarks.json'
    try:
        data = json.loads(settings.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        data = {}
    if isinstance(data, dict) and data.get('key') == key and data.get('device') in available:
        return data['device'], None
    scores = {}
    fastest_pipe = None
    fastest_time = float('inf')
    for device in available:
        if cancelled():
            raise InterruptedError()
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
                if elapsed < fastest_time:
                    fastest_pipe, fastest_time = pipe, elapsed
        except Exception:
            continue
    if not (scores.keys() & {'GPU', 'NPU'}):
        raise OpenVINOUnavailable('NO_COMPATIBLE_ACCELERATOR')
    device = min(scores, key=scores.get)
    if len(scores) == len(available):
        settings.write_text(json.dumps({'key': key, 'device': device, 'scores': scores}), encoding='utf-8')
    return device, fastest_pipe


def transcribe_if_available(media: Path, model: str, language: str | None,
                            models_root: Path, bench_root: Path, cancelled=lambda: False,
                            on_status=lambda phase: None):
    """Transcribe on a measured GPU/NPU when it wins the OpenVINO benchmark."""
    available = device_list()
    if not available:
        raise OpenVINOUnavailable('RUNTIME_UNAVAILABLE')
    # Some NPU Whisper models can return an empty or incomplete result instead
    # of raising when auto-detection exhausts the decoder cache.
    if language is None:
        available = [device for device in available if device != 'NPU']
    if not ({'GPU', 'NPU'} & set(available)):
        raise OpenVINOUnavailable('NO_ACCELERATOR')
    model_dir = resolve_model(models_root, model, on_status)
    if cancelled():
        raise InterruptedError()
    on_status('ov_benchmark')
    with tempfile.TemporaryDirectory(prefix='lecturescribe_ov_') as temp:
        test = Path(temp) / 'sample.wav'
        convert_audio(media, test, seconds=12)
        speech = read_audio(test)
        device, pipe = choose_device(model_dir, speech, bench_root,
                                     available=available, cancelled=cancelled)
        if cancelled():
            raise InterruptedError()
        # The existing faster-whisper CPU remains the preferred CPU path.
        # Do not switch merely because OpenVINO CPU happened to win its own race.
        if device == 'CPU':
            raise OpenVINOUnavailable('CPU_BENCHMARK')
        if pipe is None:
            pipe = make_pipe(model_dir, device)
    try:
        return transcribe_on_device(media, language, pipe, device, cancelled, on_status), device
    except OpenVINOUnavailable as exc:
        if exc.reason != 'NPU_KV_CACHE' or 'GPU' not in available:
            raise
        if cancelled():
            raise InterruptedError()
        on_status('ov_retry_gpu')
        pipe = make_pipe(model_dir, 'GPU')
        return transcribe_on_device(media, language, pipe, 'GPU', cancelled, on_status), 'GPU'


def transcribe_on_device(media, language, pipe, device, cancelled, on_status=lambda phase: None):
    with tempfile.TemporaryDirectory(prefix='lecturescribe_audio_ov_') as temp:
        full_path = Path(temp) / 'full.wav'
        convert_audio(media, full_path)
        if cancelled():
            raise InterruptedError()
        overlap_samples = 1 * 16000
        # Include the overlap in Whisper's 30-second input window.
        chunk_samples = 30 * 16000 - overlap_samples
        output = []
        on_status(device)
        with wave.open(str(full_path), 'rb') as audio:
            for cursor in range(0, audio.getnframes(), chunk_samples):
                if cancelled():
                    raise InterruptedError()
                end = min(audio.getnframes(), cursor + chunk_samples)
                start = max(0, cursor - overlap_samples)
                audio.setpos(start)
                try:
                    result = generate(pipe, decode_pcm(audio.readframes(end - start)), language)
                except RuntimeError as exc:
                    if device == 'NPU' and 'kv-cache is full' in str(exc).lower():
                        raise OpenVINOUnavailable('NPU_KV_CACHE') from exc
                    raise
                chunks = getattr(result, 'chunks', None) or ()
                if not chunks and str(result).strip():
                    raise OpenVINOUnavailable('TIMESTAMPS_UNAVAILABLE')
                offset = start / 16000
                accepted_until = cursor / 16000
                for c in chunks:
                    abs_start = offset + float(c.start_ts)
                    abs_end = offset + float(c.end_ts)
                    if abs_end <= accepted_until:
                        continue
                    text = str(c.text).strip()
                    if text:
                        output.append((max(abs_start, accepted_until), abs_end, text))
        if not output:
            raise OpenVINOUnavailable('EMPTY_TRANSCRIPTION')
        return output


def prepare_parallel(media, model, language, models_root, cancelled, on_status):
    if language is None:
        return None
    available = device_list()
    if not {'GPU', 'NPU'}.issubset(available):
        return None
    model_dir = resolve_model(models_root, model, on_status)
    on_status('ov_benchmark')
    with tempfile.TemporaryDirectory(prefix='lecturescribe_ov_sample_') as temp:
        samples = []
        for index, source in enumerate(media):
            if cancelled():
                raise InterruptedError()
            path = Path(temp) / f'{index}.wav'
            convert_audio(source, path, seconds=30)
            samples.append(read_audio(path))

    def run(pipe, sample):
        if cancelled():
            raise InterruptedError()
        return bool(str(generate(pipe, sample, language)).strip())

    pipes, serial_times = {}, []
    for device in available:
        if cancelled():
            raise InterruptedError()
        try:
            pipe = make_pipe(model_dir, device)
            # Warm up inference before timing the two requests.
            run(pipe, samples[0])
            start = time.perf_counter()
            results = [run(pipe, sample) for sample in samples]
            if not all(results):
                return None
            serial_times.append(time.perf_counter() - start)
            if device in ('GPU', 'NPU'):
                pipes[device] = pipe
        except OpenVINOUnavailable:
            if device != 'CPU':
                return None
    with ThreadPoolExecutor(max_workers=2) as workers:
        start = time.perf_counter()
        futures = [workers.submit(run, pipe, sample)
                   for pipe, sample in zip(pipes.values(), samples)]
        results = [future.result() for future in futures]
        if all(results) and time.perf_counter() - start < min(serial_times) * .90:
            return pipes
    return None
