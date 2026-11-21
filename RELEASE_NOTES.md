# LectureScribe 1.5.0 — candidate notes (not published)

- Webex playback opens in the Windows default browser and uses the profile already active there.
- The included extension detects the playlist only for the opened Webex tab and returns it locally to yt-dlp. Direct HLS input still works.
- First-run browser selection is saved. Includes Chromium and Firefox extension variants. Firefox uses a temporary installation in this candidate.
- Optional matching-model OpenVINO GenAI Whisper backend, GPU/NPU hardware discovery, 12-second automatic benchmark and CPU fallback.
- No hardware selectors in the interface. Existing Groq/Gemini/OpenAI cloud backends retained.

Before publishing, verify a private PoliMi recording through default-browser playback, extension capture, download, and transcription. Also verify OpenVINO inference using prepared models and Intel GPU/NPU hardware. The default Windows build uses the standard transcription runtime. OpenVINO remains available for source installations with the optional dependencies and models.
