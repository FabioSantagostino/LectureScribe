\# LectureScribe



A free, open-source Windows application for transcribing university lectures and online recordings locally using Whisper AI.



\## Features



\- Simple desktop interface

\- Support for local audio and video files

\- Webex recording download via yt-dlp (compatibility may vary)

\- Multilingual transcription with Whisper Turbo

\- Timestamped TXT and SRT exports

\- Optional retention of downloaded videos

\- Local transcription without uploading media to an AI transcription service



\## Installation



Download `LectureScribe.exe` from the latest GitHub Release and launch it on Windows.



The Whisper model is downloaded on first use. An internet connection is required for the initial model download and for accessing online recordings.



\## Usage



1\. Paste a supported recording URL or select a local media file.

2\. Enter a name for the lecture.

3\. Choose whether to retain downloaded video files.

4\. Start transcription.

5\. Find your TXT and SRT files in the output folder.



\## Limitations



Transcription is not guaranteed to be accurate, especially for technical terminology, mathematical formulas, and unclear speech.



Webex recordings may require authentication or may not be accessible through their original playback links.



\## Privacy



Transcription is performed locally. Online recordings are downloaded to the user's computer, and models may be obtained from external model repositories.



Do not publish recordings, transcripts, authentication tokens, or session cookies without authorization.



\## Built with



Python · faster-whisper · yt-dlp · Tkinter



\## License



MIT — subject to inclusion of the LICENSE file and applicable third-party license notices.

