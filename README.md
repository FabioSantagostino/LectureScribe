# LectureScribe v1.5.0 — DEVELOPMENT CANDIDATE (NOT RELEASED)

LectureScribe accepts Webex playback links, HLS URLs and local media in the same field and queue. Version 1.5.0 is a release candidate.

## Webex recording downloads

1. Paste the original Webex `/playback` link. LectureScribe opens the authorized Webex player in a dedicated browser and watches for a successful `.m3u8` response.
2. If the recording needs sign-in or playback needs a click, choose **LectureScribe Webex** when prompted. Complete any university SSO/MFA or recording password prompt in the browser window. Start playback, then click **Continue** in LectureScribe.
3. LectureScribe sends the observed playlist URL, including its original query string, to yt-dlp. If discovery fails or the playlist can't be downloaded, it can retry the original link through yt-dlp, using the authorized session or the browser/cookie-file method selected in the authentication dialog.
4. If you already have an authorized HLS URL, paste it directly. An expired link can be replaced with a fresh one or with the original Webex playback link.

Webex discovery uses installed Google Chrome or Playwright Chromium. For source installations without Chrome, install Chromium with `python -m playwright install chromium` in the application environment. The Windows candidate includes the Playwright driver and uses installed Chrome or an existing compatible Playwright Chromium installation.

The dedicated browser profile lives under `%APPDATA%\LectureScribe\webex_browser_profile`. Use **Advanced → Disconnect Webex** to clear the session when no job is running. The HLS handoff carries the observed URL in memory. The original-link fallback can use Webex cookies in memory. Keep recording URLs, tokenized playlists, browser profiles and cookie exports private.

## Experimental automatic Intel acceleration

No CPU/GPU/NPU selector is exposed. LectureScribe checks for **exactly matching** converted OpenVINO IR models, probes compatible devices, benchmarks a short speech sample and chooses the fastest supported device. If OpenVINO is absent, the model fails to compile, or the CPU wins, it uses the existing `faster-whisper` CPU backend. A benchmark on a 12-second sample does **not** guarantee the fastest results for an entire lecture. Devices are selected, not automatically run simultaneously.

In a **separate conversion environment**, install `requirements-accelerated.txt` and convert a model once:

```powershell
python -m pip install -r requirements-accelerated.txt
python prepare_openvino.py fast
# or: python prepare_openvino.py balanced
# or: python prepare_openvino.py accurate
```

The converted model is saved under `%APPDATA%\LectureScribe\openvino_models`. The full target model must have a compatible OpenVINO GenAI export; conversion can fail for a particular architecture or version. This runtime is **optional**: for source runs also install `openvino-genai` in LectureScribe's application environment. The published PyInstaller binary does not yet bundle the optional OpenVINO runtime, so **do not advertise GPU/NPU acceleration as working in the distributed EXE until a Windows build with that runtime is tested**. Compiling a model on NPU can require substantial time and updated Intel NPU drivers. Some Whisper IRs run on GPU but not NPU.

Use `python -m unittest discover -s tests -p 'test_v15.py' -v` for the isolated v1.5 security/model tests. For a real check, inspect `%APPDATA%\LectureScribe\diagnostics.log` for `OPENVINO_ACTIVE_GPU` or `OPENVINO_ACTIVE_NPU`. The mere presence of a GPU/NPU in Device Manager does not prove it was used.

## Installation (Windows 10/11)

For normal users, download the packaged `LectureScribe-Windows-x64.zip` from a tested GitHub Release, extract and launch `LectureScribe.exe`. The Whisper model downloads on first use. New cloud/updater functions require network access. The EXE is currently unsigned, so inspect provenance and test before installing.

From source using Python 3.12:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe lecturescribe.pyw
```

For Intel CPU tuning, optional:

```powershell
.\.venv\Scripts\python.exe benchmark_intel.py "C:\path\to\sample.mp4"
```

The benchmark uses a 60-second audio excerpt and saves the preferred `cpu_threads` setting. It may take several minutes; it never uploads the sample.

## Batch transcriptions

Use **+ Files** to add multiple local files or **+ Link** for recording URLs. The normal source field can also contain one file/URL, which will be processed together with queued items. The resulting status shows successes versus failures. If a custom lecture name is set for several inputs, the app adds a numeric suffix.

## Cloud mode / privacy

Choose **Cloud**, select Groq, OpenAI or Gemini, and confirm each batch before upload. Manage labeled API credentials through **Manage API keys**. Windows Credential Manager stores the secrets. LectureScribe compresses the audio into bounded MP3 chunks with a short overlap and stores private transcript checkpoints for resuming interrupted cloud jobs. Cloud exports TXT and Markdown with approximate chunk timestamps. Local Whisper exports TXT, Markdown and SRT.

Local transcription runs on the device. The recording provider and model host are contacted when downloading media or models.

## Samsung Internet on Windows

`yt-dlp` cannot officially import Samsung Internet's protected cookie store. In the authentication dialog choose Samsung Browser / Netscape file once, then check **Remember authentication method**. Keep the exported file in a private location outside your repository. Subsequent recordings reuse that file *while the Webex login stays valid*. When cookies expire, manually replace the Netscape export. Do not email, commit, sync publicly or share it. Native Samsung session refresh remains future work, pending a secure browser integration.

## Updating inside the app

Open **Advanced → Updates → Check for updates**. The packaged EXE knows the repository it was built from; source users can enter `owner/repo`. The app asks for consent, fetches the public ZIP asset, requires GitHub's SHA-256 asset digest, stages a new EXE and restarts. This is an in-place update, not a privileged installer. The directory must be writable and updates should be tested on an isolated Windows copy first. Use a GitHub Release with an attached `LectureScribe-Windows-x64.zip` asset.

## Development / release

- Edit source; run `python -m unittest discover -s tests -v`.
- Compile through `.github/workflows/release.yml`; `workflow_dispatch` compiles without publishing.
- **Only after release verification**, tag the verified version and push it. GitHub Actions uploads the Windows ZIP to the release.
- Do not upload lectures, transcripts, sessions/cookie files, API keys, or signed Webex URLs.

## Candidate verification

Run `python -m unittest discover -s tests -v` locally. Before tagging, verify the EXE on Windows, a private Webex recording through SSO/MFA and transcription, cloud jobs using real provider credentials, and the optional OpenVINO runtime using prepared models and Intel hardware.

## License

MIT for LectureScribe source. Libraries, models and online providers retain their own terms.
