# ScribeLane Webex Extension Privacy Policy

Effective November 21, 2026.

ScribeLane Webex connects a Webex recording to the ScribeLane desktop app. The extension operates on a Webex tab opened for a job that you start in the desktop app. The local connection page explains the handoff and asks you to continue before the extension captures a playlist.

## Data handled

- The original Webex playback address is used to open the recording. In that tab, the extension inspects the status and content type of matching Webex responses to identify an HLS playlist.
- The extension passes the playlist URL, including any query parameters and temporary signed access tokens, to ScribeLane on the same computer. The handoff uses the loopback address `127.0.0.1` and an unpredictable, short-lived job token.
- The extension temporarily keeps the tab identifier, local job address and expiry in browser session storage. This state stops authorizing capture after expiry. It is removed after a successful handoff, when the tab is closed, or when the browser session ends.

The extension does not read your browser history, passwords, cookies, audio or transcripts. It does not send the playlist URL to the developer or to a hosted relay, and includes no analytics, advertising or data sale. The desktop app uses the URL to contact the Webex media server and download the recording. If you choose cloud transcription in the desktop app, the desktop app separately asks for consent before sending the relevant audio to the selected provider.

You can stop the handoff by closing the tab or cancelling the desktop job. You can disable or remove the extension in your browser’s extensions settings. That does not delete any downloads or transcripts already saved by the desktop app.

The extension follows the Chrome Web Store User Data Policy, including the Limited Use requirements.

Questions about this policy can be submitted through the [ScribeLane issue tracker](https://github.com/FabioSantagostino/ScribeLane/issues). Please do not include private recording links or signed URLs in public issues.
