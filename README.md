# LectureScribe

Trascrivi lezioni e registrazioni su Windows. Puoi partire da un link Webex, da una playlist HLS `.m3u8` o da un file audio o video. La trascrizione locale usa Whisper. In modalità cloud puoi scegliere Groq, OpenAI o Gemini. L'interfaccia è disponibile in italiano e inglese.

## Installazione su Windows 10 e 11

1. Scarica `LectureScribe-Windows-x64.zip` dalla [pagina delle release](https://github.com/FabioSantagostino/LectureScribe/releases/latest).
2. Estrai **tutto lo ZIP** in una cartella stabile e avvia `LectureScribe.exe`. Tieni la cartella `browser-extension` accanto all'EXE se usi Webex.
3. Al primo avvio, indica il browser predefinito di Windows. La scelta viene salvata e puoi aggiornarla da **Avanzate → Browser per Webex**.

Per installare anche l’estensione o aggiornarne i file, scarica ed estrai lo ZIP completo. L’aggiornamento dall’app sostituisce l’EXE.

## Trascrivere un file o un link HLS diretto

1. Seleziona un file o incolla il link `.m3u8`. Per aggiungere più elementi usa **+ File** o **+ Link** nella coda.
2. Scegli il motore di trascrizione, la lingua del parlato e le cartelle di destinazione. Con Whisper puoi scegliere la qualità. In modalità cloud scegli il provider e il modello.
3. Premi **Avvia trascrizione**. Il modello Whisper viene scaricato al primo utilizzo. L'opzione **Conserva il video scaricato** salva una copia del download nella cartella indicata. I file locali originali vengono conservati.

## Trascrivere da un link Webex `/playback`

Incolla il link Webex originale e premi **Avvia trascrizione**. LectureScribe prova prima a scaricarlo con yt-dlp. Se ci riesce, il lavoro continua senza aprire il browser. Questo dipende dalla registrazione e da ciò che Webex permette a yt-dlp di recuperare direttamente. Il browser predefinito entra in gioco solo se serve il secondo tentativo. Anche i link HLS diretti funzionano senza estensione.

### Installa l'estensione solo se il link richiede il browser

Per i browser Chromium, apri la pagina delle estensioni, abilita **Modalità sviluppatore** e scegli **Carica estensione non pacchettizzata**. Seleziona la cartella `browser-extension` accanto a `LectureScribe.exe`. L'installazione si fa una volta per profilo del browser. Mantieni la cartella nella posizione in cui l'hai caricata.

Se il tuo browser è basato su Chromium e non compare per nome nelle impostazioni dell’app, seleziona **Altri browser Chromium**.

| Browser | Pagina delle estensioni |
| --- | --- |
| Google Chrome | `chrome://extensions` |
| Microsoft Edge | `edge://extensions` |
| Brave | `brave://extensions` |
| Altri browser Chromium | Apri la pagina **Estensioni** dal menu del browser |

In **Firefox**, apri `about:debugging#/runtime/this-firefox`, seleziona **Carica componente aggiuntivo temporaneo** e apri `browser-extension/firefox/manifest.json`. Firefox rimuove questa installazione temporanea quando si chiude. Ricaricala dopo il riavvio. Se usi il repository sorgente, copia `browser-extension` in una cartella distinta e sostituisci `manifest.json` con `manifest.firefox.json` rinominato.

### Avvia la registrazione

1. Dopo aver installato l’estensione, riprova il link Webex originale in LectureScribe.
2. L'estensione accompagna la nuova scheda al player nel browser predefinito di Windows. Se Webex richiede l'accesso, completalo sul sito nella sessione del tuo browser. Premi **Play** se il video rimane in pausa.
3. Quando il player riceve la playlist HLS, LectureScribe la scarica con yt-dlp e avvia la trascrizione. Per una coda con più registrazioni, ripeti la riproduzione nelle schede che la richiedono.

### Cosa fa l'estensione

L'estensione osserva le risposte Webex della sola scheda avviata per quel lavoro. Invia l'indirizzo della playlist, con i parametri originali, all'app attraverso una connessione temporanea su `127.0.0.1`. Il browser gestisce la sessione Webex. LectureScribe non legge né esporta cookie o password.

Se LectureScribe segnala che il download diretto non è riuscito, puoi attivare l’estensione nel profilo del browser predefinito oppure incollare un URL HLS valido. Se il player si apre ma la playlist non viene rilevata, avvia il video e controlla che la registrazione sia riproducibile. Se hai già una playlist HLS valida puoi incollarla direttamente, anche senza estensione. Se è scaduta, riparti dal link Webex. Tieni privati i link firmati.

## Trascrizione cloud e file di uscita

In modalità **Cloud**, scegli Groq, OpenAI o Gemini. Aggiungi e verifica una chiave da **Gestisci chiavi API** e conferma l'invio dell'audio prima di avviare la coda. Windows Credential Manager conserva le chiavi. La trascrizione cloud usa blocchi MP3 con una breve sovrapposizione e salva checkpoint locali per riprendere i lavori interrotti. Le richieste possono generare costi presso il provider.

Whisper locale esporta TXT, Markdown e SRT. I provider cloud esportano TXT e Markdown con timestamp approssimativi per blocco. In modalità locale l'audio viene trascritto sul dispositivo.

## Accelerazione locale Intel con OpenVINO

Dalla v1.5.1 il runtime OpenVINO è incluso nell’EXE Windows. In modalità **Locale**, LectureScribe cerca una GPU o NPU Intel esposta dai driver. Se la trova, scarica al primo utilizzo il modello Whisper INT8 ufficiale corrispondente alla qualità selezionata, salvo che sia già disponibile. Conserva il modello per i lavori successivi in `%APPDATA%\LectureScribe\openvino_models`. I modelli richiedono spazio su disco e, al primo utilizzo, una connessione.

L’app confronta i dispositivi compatibili su un breve campione, poi mostra durante la trascrizione **OpenVINO GPU**, **OpenVINO NPU** o **CPU**. La CPU resta disponibile se è più veloce nel confronto, se un modello non è compatibile o se manca un acceleratore. Durante la trascrizione cloud l'inferenza viene svolta dal provider.

Per una coda di almeno due file locali, con lingua del parlato impostata esplicitamente, l’app prova anche a elaborare due registrazioni contemporaneamente su **GPU + NPU**. Usa questa modalità quando i due acceleratori sono compatibili e il confronto sui campioni indica che insieme sono almeno il 10% più veloci del miglior dispositivo singolo. La verifica iniziale include il caricamento dei modelli. Se un acceleratore si interrompe, i lavori rimanenti possono proseguire in serie. Con la lingua automatica, la scelta del dispositivo è tra GPU e CPU per evitare trascrizioni incomplete su alcuni modelli NPU.

Il log diagnostico indica il dispositivo usato (`OPENVINO_ACTIVE_GPU`, `OPENVINO_ACTIVE_NPU`) o il motivo del ritorno alla CPU (voci `OPENVINO_FALLBACK_…`). Per i requisiti dei driver, consulta la [documentazione OpenVINO per NPU](https://docs.openvino.ai/2026/openvino-workflow-generative/inference-with-genai/inference-with-genai-on-npu.html).

Per usare un modello preparato da sorgente puoi ancora installare `requirements-accelerated.txt` in un ambiente separato ed eseguire `python prepare_openvino.py balanced` (o `fast` / `accurate`).

## Avvio da sorgente

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe lecturescribe.pyw
```

Per eseguire i test, usa `python -m unittest discover -s tests -v` nell'ambiente Python dell'app. Il workflow GitHub **Build Windows release** compila e verifica il pacchetto Windows.

## Licenza

MIT per il codice di LectureScribe. Librerie, modelli e servizi online mantengono le rispettive licenze e condizioni.
