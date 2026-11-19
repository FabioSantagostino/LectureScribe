# LectureScribe

A privacy-conscious **Windows desktop lecture transcriber**. Built with CustomTkinter, yt-dlp, faster-whisper and an optional OpenAI transcription API. The UI is available in Italian and English.

## Version 1.2.0 — release candidate

This version is **not yet verified end-to-end on Windows**. Test downloads, session handling, transcription, updating, and the packaged EXE before publishing a stable tag.

### What's new

- **Batch queue**: use the normal source field and/or add multiple files and recording URLs. Jobs are processed sequentially; one failed item doesn't stop the rest. Existing cancellation applies to the batch.
- **Markdown export**: local transcription creates `.txt`, `.srt`, and `.md` files. Cloud creates `.txt` and `.md` with approximate chunk markers, **not** a fabricated SRT.
- **Intel CPU tuning**: retains efficient CTranslate2 INT8 CPU inference and cached Whisper models; the optional `benchmark_intel.py` compares thread counts on your own sample and saves the fastest setting. **Intel GPU/NPU OpenVINO is not integrated in this build**; it requires a separately validated backend.
- **In-app updates**: uses GitHub's release API to find a newer version, downloads the official Windows ZIP, checks the SHA-256 digest returned by GitHub, stages an EXE and installs only after explicit confirmation. Works with the *packaged EXE* on a writable install path. The Windows release workflow embeds its repository address automatically. Source runs can enter `owner/repo` in Advanced Settings. No auto-update silently in the background.
- **Remember Webex authentication**: opt in when selecting a browser or Netscape cookie file. Saves the **browser identity or path to an existing cookie export**, *not its cookie values*. On later private recording downloads, the chosen method is retried automatically; the dialog reappears only if access fails. One selection can also be reused across batch items. **Samsung Internet's encrypted cookie store is not directly supported**, so it can't refresh expired cookies automatically; you must re-export/update the file when the Webex session expires.
- **Cloud transcription (optional)**: explicit OpenAI API opt-in with `gpt-transcribe`. Session-only API key input, never saved to settings or logs. Requires your own OpenAI API account and credits; **ChatGPT Plus does not include API credits**. Media audio is converted to 7-minute compressed MP3 chunks and uploaded to OpenAI, with approximate chunk-start markers. Transcript privacy differs from local mode. You can choose Local at any time.

### Existing features retained

- Light/dark/system theme and responsive, compact CustomTkinter layout
- Italian/English UI and automated choice of language-compatible models
- Three understandable local profiles: Fast (`small`/`small.en`), Balanced (`turbo`), Highest quality (`large-v3`)
- Video filename/title used automatically, optional custom name
- Original Webex links via yt-dlp, optional authorized browser cookies, Samsung exported Netscape cookies
- Separate transcript and retained-download directories; originals are never automatically deleted
- Progress indicators, cooperative cancellation, diagnostic codes without URLs or cookie contents
- HLS URLs, existing local video/audio files, TXT/SRT/Markdown exports

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

Choose **Cloud · OpenAI API**, paste your API key (for this session only), and confirm every batch before upload. Cloud audio is split into MP3 chunks of up to 7 minutes, designed to stay below the provider's 25 MB upload limit. The service may charge usage. This is a direct transcription API, **not ChatGPT chat or an autonomous agent**. The app does not offer an unauthenticated free service: such providers have no dependable privacy/uptime guarantee. The cloud option currently does **not** provide accurate word/segment timestamps, so cloud SRT export is intentionally disabled.

The local mode does not transmit your lecture to a transcription service. Online recording retrieval and model downloads may still access their providers.

## Samsung Internet on Windows

`yt-dlp` cannot officially import Samsung Internet's protected cookie store. In the authentication dialog choose Samsung Browser / Netscape file once, then check **Remember authentication method**. Keep the exported file in a private location outside your repository. Subsequent recordings reuse that file *while the Webex login stays valid*. When cookies expire, manually replace the Netscape export. Do not email, commit, sync publicly or share it. Native Samsung session refresh remains future work, pending a secure browser integration.

## Updating inside the app

Open **Advanced → Updates → Check for updates**. The packaged EXE knows the repository it was built from; source users can enter `owner/repo`. The app asks for consent, fetches the public ZIP asset, requires GitHub's SHA-256 asset digest, stages a new EXE and restarts. This is an in-place update, not a privileged installer. The directory must be writable and updates should be tested on an isolated Windows copy first. Use a GitHub Release with an attached `LectureScribe-Windows-x64.zip` asset.

## Development / release

- Edit source; run `python -m unittest discover -s tests -v`.
- Compile through `.github/workflows/release.yml`; `workflow_dispatch` compiles without publishing.
- **Only after real Windows tests**, tag `v1.2.0` once and push it. GitHub Actions uploads the Windows ZIP to the release.
- Do not upload lectures, transcripts, sessions/cookie files, API keys, or signed Webex URLs.

## Limitations

- Full Samsung browser authentication extraction is not implemented, only remembered authorized cookie-file reuse.
- OpenVINO GPU/NPU acceleration is not integrated; this release tunes CPU thread scheduling only.
- Cloud timestamps are approximations based on chunk start; SRT would be misleading.
- The updater requires EXE mode and a writable installation directory; it will not elevate privileges or modify protected directories.
- GitHub Actions building successfully is **not** proof that every runtime path works. Test on an actual Windows laptop or a clean VM.

## License

MIT for LectureScribe source; all libraries, models and online providers retain their own terms.
