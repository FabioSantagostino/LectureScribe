# LectureScribe v1.5.0 — DEVELOPMENT CANDIDATE (NOT RELEASED)

LectureScribe accepts Webex playback links, HLS URLs and local media in the same field and queue. Version 1.5.0 is a release candidate.

## Webex nel browser predefinito (Windows)

1. Estrai tutto lo ZIP in una cartella da conservare. Avvia `LectureScribe.exe` e indica quale browser è impostato come predefinito in Windows. LectureScribe salva la scelta e mostra le istruzioni per la variante corretta. Puoi cambiarla da **Avanzate → Browser per Webex**.
2. In **Samsung Internet per Windows**, apri `internet://extensions`. In Chrome, Edge o Brave apri rispettivamente `chrome://extensions`, `edge://extensions` o `brave://extensions`. Attiva **Modalità sviluppatore** e usa **Carica estensione non pacchettizzata** per selezionare la cartella `browser-extension` accanto all'EXE. Questa installazione si fa una volta per profilo del browser.
3. In **Firefox**, apri `about:debugging#/runtime/this-firefox`, scegli **Carica componente aggiuntivo temporaneo** e seleziona `browser-extension/firefox/manifest.json`. L'estensione di questa candidata va ricaricata dopo il riavvio di Firefox. Nel repository sorgente, prepara una copia di `browser-extension` con `manifest.firefox.json` rinominato in `manifest.json`.
4. Incolla il link originale Webex `/playback` in LectureScribe e avvia la trascrizione. Windows apre una nuova scheda nel browser predefinito. Se il player non parte da solo, premi **Play** nella scheda Webex. Quando il player riceve la playlist, LectureScribe inizia il download. Puoi anche incollare un URL HLS valido direttamente, senza estensione.

L'estensione osserva solo le risposte Webex della scheda aperta per la registrazione e invia l'URL della playlist una sola volta a LectureScribe tramite un collegamento su `127.0.0.1`. Il browser continua a gestire la sessione Webex. L'app non legge cookie o credenziali. Gli URL HLS possono scadere. Se l'estensione non viene rilevata, verifica che sia attiva nel profilo usato dal browser predefinito e riprova.

Samsung documenta il caricamento delle estensioni in modalità sviluppatore su Windows. Il flusso resta da verificare sulla registrazione PoliMi e sulla versione di Samsung Internet installata. [Documentazione Samsung sulle estensioni](https://developer.samsung.com/browser/policy/extension-unpublished-availability.html)

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

## Updating inside the app

Open **Advanced → Updates → Check for updates**. The packaged EXE knows the repository it was built from; source users can enter `owner/repo`. The app asks for consent, fetches the public ZIP asset, requires GitHub's SHA-256 asset digest, stages a new EXE and restarts. This is an in-place update, not a privileged installer. The directory must be writable and updates should be tested on an isolated Windows copy first. Use a GitHub Release with an attached `LectureScribe-Windows-x64.zip` asset.

## Development / release

- Edit source; run `python -m unittest discover -s tests -v`.
- Compile through `.github/workflows/release.yml`; `workflow_dispatch` compiles without publishing.
- **Only after release verification**, tag the verified version and push it. GitHub Actions uploads the Windows ZIP to the release.
- Do not upload lectures, transcripts, sessions/cookie files, API keys, or signed Webex URLs.

## Candidate verification

Run `python -m unittest discover -s tests -v` locally. Before tagging, verify the EXE on Windows, a private Webex recording through the default-browser extension and transcription, cloud jobs using real provider credentials, and the optional OpenVINO runtime using prepared models and Intel hardware.

## License

MIT for LectureScribe source. Libraries, models and online providers retain their own terms.
