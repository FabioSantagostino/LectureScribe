"""One-time OpenVINO Whisper model conversion for LectureScribe.

Run after installing the OPTIONAL acceleration toolchain. The main app only
uses exact matching preconverted IR models and otherwise uses faster-whisper.
"""
from __future__ import annotations
import argparse
import os
import subprocess
import sys
from pathlib import Path

MODEL_IDS = {
    'fast': 'openai/whisper-small',
    'fast-en': 'openai/whisper-small.en',
    'balanced': 'openai/whisper-large-v3-turbo',
    'accurate': 'openai/whisper-large-v3',
}
MODEL_DIRS = {
    'fast': 'whisper-small',
    'fast-en': 'whisper-small.en',
    'balanced': 'whisper-large-v3-turbo',
    'accurate': 'whisper-large-v3',
}


def main():
    parser = argparse.ArgumentParser(description='Prepare matching OpenVINO Whisper IR')
    parser.add_argument('quality', choices=MODEL_IDS)
    parser.add_argument('--output', type=Path,
                        default=Path(os.getenv('APPDATA', str(Path.home()))) / 'LectureScribe/openvino_models')
    args = parser.parse_args()
    target = args.output / MODEL_DIRS[args.quality]
    target.parent.mkdir(parents=True, exist_ok=True)
    print('Converting:', MODEL_IDS[args.quality])
    print('Saving to:', target)
    # No shell; no login tokens or secrets are passed.
    cli = Path(sys.executable).with_name('optimum-cli.exe' if os.name == 'nt' else 'optimum-cli')
    if not cli.exists():
        raise SystemExit('optimum-cli is not installed in this Python environment')
    subprocess.run([str(cli), 'export', 'openvino', '--model',
                    MODEL_IDS[args.quality], str(target)], check=True)
    print('Ready:', target)


if __name__ == '__main__':
    main()
