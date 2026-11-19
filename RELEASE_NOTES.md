# LectureScribe v1.2.0 — release candidate

**Do not publish this as stable until Windows runtime tests pass.**

## Added
- Multi-recording queue (local media and authorized Webex URLs)
- Markdown alongside TXT/SRT for local transcription
- Optional cloud transcription using the OpenAI `gpt-transcribe` API (user-supplied key; explicit upload consent)
- In-app version checking, verified GitHub release download and opt-in EXE replacement
- Persisted browser/cookie-file choice for repeat Webex recordings
- Optional Intel CPU thread-count benchmarking

## Limitations
- Samsung Internet cannot be read natively; remembering a cookie file avoids reselecting it but does not renew expired cookies
- Cloud mode outputs TXT and Markdown only with approximate chunk timestamps, no reliable SRT
- Intel OpenVINO GPU/NPU acceleration is not included; CPU profiling only
- Requires end-to-end test of bundled executable and private Webex login
