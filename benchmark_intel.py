"""Optional local CPU tuning: benchmark Whisper on a 60-second excerpt.

Usage: python benchmark_intel.py recording.mp4
Requires dependencies from requirements.txt. Never uploads recording data.
"""
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path
import imageio_ffmpeg
from faster_whisper import WhisperModel


def main():
    if len(sys.argv) != 2 or not Path(sys.argv[1]).is_file():
        raise SystemExit('Usage: python benchmark_intel.py <your-audio-or-video>')
    path = Path(sys.argv[1]); ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    with tempfile.TemporaryDirectory() as tmp:
        sample = Path(tmp) / 'sample.wav'
        subprocess.run([ffmpeg, '-nostdin', '-v', 'error', '-y', '-i', str(path),
                        '-t', '60', '-vn', '-ar', '16000', '-ac', '1', str(sample)], check=True)
        results = {}
        variants = sorted({4, 6, 8, min(12, os.cpu_count() or 8)})
        for n in variants:
            print(f'Testing {n} CPU threads...')
            start = time.monotonic()
            model = WhisperModel('turbo', device='cpu', compute_type='int8', cpu_threads=n)
            segments, _ = model.transcribe(str(sample), language='it', beam_size=5)
            for _ in segments: pass
            elapsed = time.monotonic() - start
            results[n] = round(elapsed, 2)
            print(f'  {elapsed:.1f} s')
    winner = min(results, key=results.get)
    print('Recommended cpu_threads:', winner)
    config_dir = Path(os.getenv('APPDATA', str(Path.home()))) / 'LectureScribe'
    config_dir.mkdir(parents=True, exist_ok=True)
    config = config_dir / 'settings.json'
    try: saved = json.loads(config.read_text(encoding='utf-8'))
    except (OSError, ValueError): saved = {}
    saved['cpu_threads'] = winner
    config.write_text(json.dumps(saved, indent=2, ensure_ascii=False), encoding='utf-8')
    print('Saved CPU thread tuning to:', config)


if __name__ == '__main__':
    main()
