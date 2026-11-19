# LectureScribe

Local lecture transcription for Windows. **Italiano / English UI**. Convert local media or supported Webex recordings into time-stamped `.txt` and `.srt` files using faster-whisper. Transcription runs locally; it does not upload media to a hosted transcription API.

## Windows download

Open **Releases** and download `LectureScribe-Windows-x64.zip`. Extract and run `LectureScribe.exe`. Windows may warn about an unsigned, newly distributed executable. **Do not disable security protections automatically**; inspect the source and verify the release before running. The first run of a model requires internet access and disk space to download its weights.

## Features

- Resizable desktop interface, dark/light appearance
- Italian and English interface; spoken-language auto-detect, Italian or English override
- Local video/audio and supported Webex recording URLs
- Attempts public playback first, then asks for an authenticated browser when required
- Installed browser detection: Chrome, Edge, Firefox, Brave, Opera, Opera GX, Vivaldi, Chromium, Whale
- Samsung Browser and other browsers: Netscape-format cookie file fallback (not direct browser extraction)
- Choose distinct transcript and video destination folders
- Optional retention of downloaded videos; **existing local files are never deleted**
- TXT and SRT with timestamps, incremental output, cancellation, `.partial` outputs if cancelled
- Privacy-friendly diagnostic event codes in `%APPDATA%/LectureScribe/diagnostics.log`

## Choosing a model

The model list uses faster-whisper model aliases. Larger models generally need more time, RAM and disk space. Actual speed/accuracy depends on computer and language.

| Model | When to choose |
|---|---|
| `tiny`, `base` | Fastest experiments; low transcription accuracy for technical speech |
| `small` | Low-resource multilingual transcription |
| `medium` | Better multilingual accuracy; slower than small |
| `turbo` / `large-v3-turbo` | **Recommended default** for mixed Italian and English technical lectures based on our test |
| `large-v3` / `large` | Quality comparison or difficult speech; more demanding and may repeat speech |
| `large-v1`, `large-v2` | Older large models for compatibility or comparison |
| `distil-large-v2`, `distil-large-v3`, `distil-large-v3.5` | Distilled variants; may prioritize English, not ideal default for Italian |
| `*.en` (`tiny.en`, `base.en`, `small.en`, `medium.en`, `distil-small.en`, `distil-medium.en`) | **English-only**, not for Italian lectures |

Transcriptions are *not authoritative*: confirm formulas, identifiers, negations and unusual technical terms against original recordings/slides. The app does not transcribe what is only visible on screen.

## Development

Windows 10/11, Python 3.12 recommended:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe lecturescribe.pyw
```

`requirements.txt` uses the tested PyAV 18 compatibility workaround. Upgrade and re-test before changing the major PyAV version.

To build manually:

```powershell
.\.venv\Scripts\python.exe -m pip install pyinstaller
.\.venv\Scripts\python.exe -m PyInstaller --noconfirm --clean --onefile --windowed --name LectureScribe --collect-all faster_whisper --collect-all ctranslate2 --collect-all av --collect-all yt_dlp lecturescribe.pyw
```

The executable is in `dist/LectureScribe.exe`.

## GitHub release automation

`.github/workflows/release.yml` builds on Windows for tags named `v*` and attaches a ZIP to the release. First test the app manually, then create and push a tag:

```powershell
git add .
git commit -m "Prepare LectureScribe 1.0"
git push origin main
git tag v1.0.0
git push origin v1.0.0
```

GitHub Actions needs permission to write release contents (`contents: write` is set in workflow; repository settings can also restrict actions). Check the workflow succeeds before sharing the binary.

## Authentication and privacy

- Use recordings you have permission to access.
- `yt-dlp` initially tries downloading without cookies. If Webex reports an authentication error, it asks you to select an installed browser or a Netscape cookie file. Some Chromium installations restrict access to their cookies; you may need an authorized cookie export.
- **Samsung Browser on Windows is not a first-class yt-dlp cookie backend.** Its GUI option uses a user-supplied Netscape cookie file only.
- Cookie files can grant access to your accounts. Never upload, commit, email or publish them, and delete temporary exported copies when no longer needed.
- The diagnostic log contains only fixed event identifiers. No URL, cookie, file path or media content is intentionally logged.
- Settings (non-secret paths, theme, model) are stored at `%APPDATA%/LectureScribe/settings.json`.

## Known limitations

- The cancellation button stops at cooperative checkpoints: downloading a fragment or decoding a long chunk can take time.
- An interrupted transfer or crash may leave incomplete output; a normal cancellation marks transcript files `.partial`.
- Speech detection and model selection are fallible, and downloaded models can be large.
- Webex permissions and available formats vary by institution; authentication is not guaranteed on all browser configurations.
- The GitHub workflow builds an executable but does not replace end-to-end manual testing on a clean Windows install.

## License

MIT for the LectureScribe source. Bundled third-party libraries and model weights retain their own licenses; review them separately for redistribution.
