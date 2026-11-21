# ScribeLane v1.6.0

- **ScribeLane** è il nuovo nome del progetto. App Windows, archivio, estensione Webex, documentazione e sistema di aggiornamento adottano il nuovo nome.
- Per passare da una versione precedente, scarica `ScribeLane-Windows-x64.zip` ed estrai tutti i file. Avvia `ScribeLane.exe` e configura il nuovo profilo. Se usi Webex o i servizi cloud, carica l’estensione inclusa o aggiungi le chiavi in Gestisci chiavi API.

## Correzioni introdotte in v1.5.2

- **Correzione NPU.** Con lingua esplicita, ScribeLane riprova sulla GPU se la NPU esaurisce la cache del decoder. Con lingua automatica, usa GPU o CPU. Se OpenVINO non restituisce testo, l’app riprova con Whisper su CPU.

## Novità introdotte in v1.5.1

- **Webex prova prima il download diretto con yt-dlp.** L’estensione interviene solo se il link `/playback` non è scaricabile direttamente. Puoi continuare a usare playlist HLS e file locali senza estensione.
- **Impostazione del browser più chiara.** I browser Chromium compatibili senza una voce dedicata usano la categoria **Altri browser Chromium**.
- **OpenVINO incluso nell’EXE Windows.** Per la trascrizione locale su hardware Intel compatibile, il modello Whisper INT8 della qualità selezionata viene scaricato al primo utilizzo. L’app confronta CPU, GPU e NPU disponibili e mostra il dispositivo utilizzato. Il registro diagnostico spiega il ritorno alla CPU.
- **Code locali su GPU e NPU.** Per due o più file locali con lingua esplicita, ScribeLane può trascrivere due registrazioni in parallelo quando una prova sui campioni mostra un vantaggio. Una singola registrazione continua a usare il dispositivo selezionato automaticamente.

Scarica ed estrai il pacchetto Windows completo se ti servono i file dell’estensione. Per l’installazione e i casi d’uso, consulta il README.
