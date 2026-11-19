# LectureScribe 1.0

First major Windows release of LectureScribe.

- Resizable light/dark desktop interface, Italian and English UI
- Transcribe local media and supported Webex recordings
- Browser authentication requested only if a recording requires it
- Detect common installed browsers; cookie-file fallback for Samsung Browser
- Select Whisper model and spoken-language detection
- Choose separate output directories for TXT/SRT and retained videos
- Optional retention of downloaded media; local originals are untouched
- Progress indicator, cancellation, partial output preservation
- Minimal diagnostic event logs without credentials or URLs

Whisper models are downloaded on first use. Browser authentication depends on platform/browser security. Review transcripts for technical terms and formulas. This initial release should be tested on a fresh Windows PC before general distribution.
