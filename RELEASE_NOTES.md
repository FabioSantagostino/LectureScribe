# LectureScribe 1.5.0 — candidate notes (not published)

- Automatic HLS discovery for Webex playback links in Chrome or Playwright Chromium. yt-dlp receives the playlist URL observed in the authorized player. Direct HLS URLs remain supported.
- Dedicated Webex login profile with interactive SSO/MFA, session reuse, and an original-link fallback that can use authorized cookies in memory.
- Session reuse and user-initiated logout/clear.
- Optional matching-model OpenVINO GenAI Whisper backend, GPU/NPU hardware discovery, 12-second automatic benchmark and CPU fallback.
- No hardware selectors in the interface. Existing Groq/Gemini/OpenAI cloud backends retained.

Before publishing, verify a private PoliMi recording through SSO/MFA, playback, download, and transcription. Also verify OpenVINO inference using prepared models and Intel GPU/NPU hardware. The default Windows build uses the standard transcription runtime. OpenVINO remains available for source installations with the optional dependencies and models.
