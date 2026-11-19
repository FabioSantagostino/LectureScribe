# LectureScribe v1.1.2 — Interface stability and touchpad scrolling

- Fixed duplicated scrollbars and shrinking content area when switching UI language or theme, or expanding advanced settings
- Keeps the CustomTkinter scrollable container alive and rebuilds only its contents
- Increased vertical scrolling response for Windows precision touchpads, including small wheel deltas
- Preserved the compact UI, theme follow-system mode, language switching, Webex authentication, and transcription workflow

This version has passed Python syntax and source-structure checks. Verify the interface on Windows, especially repeated theme/language changes and touchpad scrolling, before tagging a release.
