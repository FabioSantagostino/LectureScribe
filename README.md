# LectureScribe

**LectureScribe** is a privacy-conscious Windows desktop app for transcribing university lectures and other recordings into timestamped TXT and SRT files using faster-whisper. The app speaks **Italian and English**, and speech recognition runs on your PC.

## Download and install

Open the latest **GitHub Releases** entry, download `LectureScribe-Windows-x64.zip`, extract the archive and run `LectureScribe.exe`. The initial model download requires an internet connection. Windows SmartScreen may warn about an unsigned app; review the code and verify the release rather than disabling security software.

## Modern compact interface

- Compact resizable interface with rounded controls, a slim modern scroll bar and a simple three-step flow
- **System theme** by default: follows Windows light/dark preference and reacts to changes; optional Light and Dark overrides using ☀ / ☾ controls
- English and Italian UI, switchable from the top bar
- Original recording title used automatically; **Use a custom lecture name** displays the name field only if checked
- Just **three quality profiles** instead of a long list of internal model names
- Choose spoken language: **Auto**, **Italian**, or **English**. The matching English-only model is selected automatically *when it exists*
- Subtle animated processing status, modern progress indicator and cancellation
- Faster mouse-wheel and Windows precision-touchpad two-finger scrolling, with a single persistent scrollbar
- CustomTkinter-based controls rather than classic Windows/Tk widgets
- Advanced settings collapse by default: output directories, retain downloaded video, transcripts/logs shortcuts

## Quality profiles and languages

| Quality setting | Italian or Auto | English | Suggested use |
|---|---|---|---|
| ⚡ **Fast** | `small` | `small.en` | Rapid drafts on low-end laptops |
| ✦ **Balanced** (default) | `turbo` | `turbo` | **Recommended** for most lectures, especially mixed Italian/English terminology |
| ◎ **Highest quality** | `large-v3` | `large-v3` | Difficult speech; slower and uses more resources |

Turbo and Large-v3 are multilingual; they do **not** have official `turbo.en` or `large-v3.en` variants. Automatic language recognition uses multilingual models. Larger models are not invariably more accurate; verify formulas, negations, function names and code identifiers using the original recording.

## How to use

1. Paste the original Webex recording link (or a supported HLS URL), or browse for a local audio/video file.
2. Optionally check **Use a custom lecture name**. Otherwise the app uses the local filename or the recording title returned by yt-dlp. If metadata has no meaningful title, it falls back to a dated name.
3. Select **quality** and **spoken language**. Start transcription.
4. TXT and SRT files are written incrementally into your configured transcript folder. You can customize both output folders under **Advanced options**.

Online videos are downloaded temporarily, then removed after transcription unless **Keep downloaded video** is enabled. Original local files are **never** automatically removed.

## Private Webex recordings

The app first attempts to open a recording **without credentials**. If authentication is required, it opens a browser selector showing supported detected browsers such as Chrome, Edge, Firefox, Brave, Opera, Opera GX, Vivaldi and Chromium. Some browser cookie stores are protected by Windows and cannot be read automatically. **Samsung Browser on Windows** requires an authorized Netscape-format cookie file; it is not natively supported by yt-dlp's browser-cookie import.

Cookies are account credentials. Never commit or share a cookie export or a temporary signed streaming URL. Use recordings you have permission to access.

## Run from source

Requires Windows 10/11 and Python 3.12:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe lecturescribe.pyw
```

The requirements file pins PyAV 18 due to a compatibility issue observed with the tested faster-whisper version. Future upgrades should be tested first.

## Build a Windows executable

```powershell
.\.venv\Scripts\python.exe -m pip install pyinstaller
.\.venv\Scripts\python.exe -m PyInstaller --noconfirm --clean --onefile --windowed --name LectureScribe --collect-all faster_whisper --collect-all ctranslate2 --collect-all av --collect-all yt_dlp --collect-all customtkinter lecturescribe.pyw
```

The output is `dist/LectureScribe.exe`. The GitHub Actions workflow also supports a **manual build** without publishing a release and a **tag-triggered release** with the ZIP automatically attached. For a new version, push code and then create **one** new tag (`v1.1.1`, for example); don't separately create another GitHub release.

## Privacy and limitations

- Audio transcription is local; online recording retrieval and model downloads require internet access.
- The diagnostics log at `%APPDATA%\LectureScribe\diagnostics.log` records event codes, not media, signed URLs, cookies or file paths.
- Settings (non-secret UI preferences and output paths) are in `%APPDATA%\LectureScribe\settings.json`.
- Cancellation is cooperative and can wait for a block/fragment to finish. Incomplete TXT/SRT are preserved with `.partial` names on normal cancellation.
- Transcription does not extract content shown only in slides or video frames.
- Recording metadata and access permissions vary by Webex installation; automatic download is not guaranteed for every Webex URL.
- GitHub CI verifying syntax and building an EXE does **not** replace testing the binary on a clean Windows installation.

## License

LectureScribe is MIT-licensed. Third-party libraries and model weights retain their respective licenses.
