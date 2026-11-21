# LectureScribe v1.5.2

- **Correzione NPU.** Con lingua esplicita, LectureScribe invia a Whisper blocchi più brevi sulla NPU e riprova sulla GPU se la cache del decoder si esaurisce. Con lingua automatica, usa GPU o CPU. Se OpenVINO non restituisce testo, l’app riprova con Whisper su CPU.

## Novità introdotte in v1.5.1

- **Webex prova prima il download diretto con yt-dlp.** L’estensione interviene solo se il link `/playback` non è scaricabile direttamente. Puoi continuare a usare playlist HLS e file locali senza estensione.
- **Impostazione del browser più chiara.** I browser Chromium compatibili senza una voce dedicata usano la categoria **Altri browser Chromium**.
- **OpenVINO incluso nell’EXE Windows.** Per la trascrizione locale su hardware Intel compatibile, il modello Whisper INT8 della qualità selezionata viene scaricato al primo utilizzo. L’app confronta CPU, GPU e NPU disponibili e mostra il dispositivo utilizzato. Il registro diagnostico spiega il ritorno alla CPU.
- **Code locali su GPU e NPU.** Per due o più file locali con lingua esplicita, LectureScribe può trascrivere due registrazioni in parallelo quando una prova sui campioni mostra un vantaggio. Una singola registrazione continua a usare il dispositivo selezionato automaticamente.

Scarica ed estrai il pacchetto Windows completo se ti servono i file dell’estensione. Per l’installazione e i casi d’uso, consulta il README.
