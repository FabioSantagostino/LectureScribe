# LectureScribe

Trascrivi lezioni e registrazioni su Windows. Puoi partire da un link Webex, da una playlist HLS `.m3u8` o da un file audio o video. La trascrizione locale usa Whisper. In modalità cloud puoi scegliere Groq, OpenAI o Gemini. L'interfaccia è disponibile in italiano e inglese.

## Installazione su Windows 10 e 11

1. Scarica `LectureScribe-Windows-x64.zip` dalla [pagina delle release](https://github.com/FabioSantagostino/LectureScribe/releases/latest).
2. Estrai **tutto lo ZIP** in una cartella stabile e avvia `LectureScribe.exe`. Tieni la cartella `browser-extension` accanto all'EXE se usi Webex.
3. Al primo avvio, indica il browser predefinito di Windows. Per Samsung Internet scegli **Altri browser Chromium (Samsung Internet incluso)**. La scelta viene salvata e puoi aggiornarla da **Avanzate → Browser per Webex**.

Se provieni dalla v1.3.0, scarica ed estrai lo ZIP completo. L'aggiornamento dall'app sostituisce l'EXE. L'estensione va installata dal nuovo pacchetto.

## Trascrivere un file o un link HLS diretto

1. Seleziona un file o incolla il link `.m3u8`. Per aggiungere più elementi usa **+ File** o **+ Link** nella coda.
2. Scegli il motore di trascrizione, la lingua del parlato e le cartelle di destinazione. Con Whisper puoi scegliere la qualità. In modalità cloud scegli il provider e il modello.
3. Premi **Avvia trascrizione**. Il modello Whisper viene scaricato al primo utilizzo. L'opzione **Conserva il video scaricato** salva una copia del download nella cartella indicata. I file locali originali vengono conservati.

## Trascrivere da un link Webex `/playback`

### Installa l'estensione per il tuo browser

Per i browser Chromium, apri la pagina delle estensioni, abilita **Modalità sviluppatore** e scegli **Carica estensione non pacchettizzata**. Seleziona la cartella `browser-extension` accanto a `LectureScribe.exe`. L'installazione si fa una volta per profilo del browser. Mantieni la cartella nella posizione in cui l'hai caricata.

| Browser | Pagina delle estensioni |
| --- | --- |
| Samsung Internet per Windows | `internet://extensions` |
| Google Chrome | `chrome://extensions` |
| Microsoft Edge | `edge://extensions` |
| Brave | `brave://extensions` |

In **Firefox**, apri `about:debugging#/runtime/this-firefox`, seleziona **Carica componente aggiuntivo temporaneo** e apri `browser-extension/firefox/manifest.json`. Firefox rimuove questa installazione temporanea quando si chiude. Ricaricala dopo il riavvio. Se usi il repository sorgente, copia `browser-extension` in una cartella distinta e sostituisci `manifest.json` con `manifest.firefox.json` rinominato.

### Avvia la registrazione

1. Incolla il link Webex originale in LectureScribe e premi **Avvia trascrizione**.
2. L'estensione accompagna la nuova scheda al player nel browser predefinito di Windows. Se Webex richiede l'accesso, completalo sul sito nella sessione del tuo browser. Premi **Play** se il video rimane in pausa.
3. Quando il player riceve la playlist HLS, LectureScribe la scarica con yt-dlp e avvia la trascrizione. Per una coda con più registrazioni, ripeti la riproduzione nelle schede che la richiedono.

### Cosa fa l'estensione

L'estensione osserva le risposte Webex della sola scheda avviata per quel lavoro. Invia l'indirizzo della playlist, con i parametri originali, all'app attraverso una connessione temporanea su `127.0.0.1`. Il browser gestisce la sessione Webex. LectureScribe non legge né esporta cookie o password.

Se compare **Estensione LectureScribe non rilevata**, controlla che sia attiva nel profilo aperto dal browser predefinito e riprova. Se il player si apre ma la playlist non viene rilevata, avvia il video e controlla che la registrazione sia riproducibile. Se hai già una playlist HLS valida puoi incollarla direttamente, anche senza estensione. Se è scaduta, riparti dal link Webex. Tieni privati i link firmati.

## Trascrizione cloud e file di uscita

In modalità **Cloud**, scegli Groq, OpenAI o Gemini. Aggiungi e verifica una chiave da **Gestisci chiavi API** e conferma l'invio dell'audio prima di avviare la coda. Windows Credential Manager conserva le chiavi. La trascrizione cloud usa blocchi MP3 con una breve sovrapposizione e salva checkpoint locali per riprendere i lavori interrotti. Le richieste possono generare costi presso il provider.

Whisper locale esporta TXT, Markdown e SRT. I provider cloud esportano TXT e Markdown con timestamp approssimativi per blocco. In modalità locale l'audio viene trascritto sul dispositivo.

## OpenVINO sperimentale (da sorgente)

Per la trascrizione locale è disponibile un backend OpenVINO GenAI opzionale. Con un modello IR compatibile, l'app confronta CPU e dispositivi Intel disponibili su un breve campione e può scegliere automaticamente GPU o NPU. Whisper su CPU resta disponibile quando OpenVINO manca o non viene scelto. L'EXE distribuito usa il runtime standard. OpenVINO richiede un avvio da sorgente con librerie e modelli aggiuntivi.

In un ambiente separato, installa `requirements-accelerated.txt` ed esegui `python prepare_openvino.py balanced` (o `fast` / `accurate`). Per usare il modello preparato, installa `openvino-genai` anche nell'ambiente Python da cui avvii LectureScribe. Il modello viene salvato in `%APPDATA%\LectureScribe\openvino_models`.

## Avvio da sorgente

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe lecturescribe.pyw
```

Per eseguire i test, usa `python -m unittest discover -s tests -v` nell'ambiente Python dell'app. Il workflow GitHub **Build Windows release** compila e verifica il pacchetto Windows.

## Licenza

MIT per il codice di LectureScribe. Librerie, modelli e servizi online mantengono le rispettive licenze e condizioni.
