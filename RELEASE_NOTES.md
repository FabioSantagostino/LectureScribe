# LectureScribe v1.5.0

Da questa versione puoi partire dal link Webex originale e scaricare la registrazione dalla sessione già aperta nel tuo browser. La v1.5.0 completa anche il supporto cloud multiprovider e introduce un backend Intel OpenVINO sperimentale.

## Novità da v1.3.0

- **Webex nel browser predefinito.** Incolla il link `/playback`, avvia la trascrizione e riproduci il video nella scheda che si apre. L'estensione inclusa rileva la playlist HLS del player e la passa a yt-dlp. I link `.m3u8` diretti continuano a funzionare.
- **Configurazione del browser al primo avvio.** La scelta resta salvata e si può modificare dalle opzioni avanzate. Samsung Internet usa la variante **Altri browser Chromium**. È inclusa anche una variante Firefox per installazione temporanea.
- **Sessione Webex gestita dal browser.** Il nuovo flusso usa la sessione abituale ed elimina il login dedicato e l'importazione di cookie. Il trasferimento della playlist avviene in locale, per la sola scheda avviata da LectureScribe.
- **Groq, OpenAI e Gemini.** L'interfaccia permette di scegliere provider e modello, verificare l'accesso e gestire più chiavi con etichette. Windows Credential Manager conserva le chiavi. L'upload richiede conferma, e la trascrizione può riprendere dai blocchi già elaborati grazie ai checkpoint locali.
- **Coda più flessibile.** L'editor ridimensionabile accetta insieme percorsi locali e link, con un nome opzionale per ogni registrazione. I titoli in conflitto ricevono un suffisso per proteggere i file già salvati.
- **OpenVINO GenAI sperimentale.** Su un'installazione da sorgente con modelli compatibili, LectureScribe può confrontare automaticamente CPU, GPU e NPU Intel su un breve campione. Se il backend opzionale manca o non è adatto, usa Whisper su CPU.

## Come aggiornare

Scarica **LectureScribe-Windows-x64.zip**, estrai tutti i file e avvia `LectureScribe.exe`. Per i link Webex originali, carica l'estensione inclusa seguendo il [README](https://github.com/FabioSantagostino/LectureScribe/blob/v1.5.0/README.md). Il pacchetto Windows usa il runtime standard. Il backend OpenVINO richiede le dipendenze opzionali da sorgente.

La suite automatica e le prove Windows coprono l'avvio dell'app, il rilevamento HLS su una pagina di prova in Samsung Internet, il download HLS diretto e la trascrizione locale con esportazione. La registrazione privata PoliMi, le chiamate con credenziali cloud reali e l'inferenza su GPU/NPU Intel restano da verificare.

[Confronto completo con v1.3.0](https://github.com/FabioSantagostino/LectureScribe/compare/v1.3.0...v1.5.0)
