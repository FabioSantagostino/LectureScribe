// Only the short-lived local ScribeLane page can arm a tab.
if (/^\/scribelane\/[A-Za-z0-9_-]{43}$/.test(location.pathname)) {
  const target = document.getElementById("playback");
  if (target) {
    chrome.runtime.sendMessage({ type: "ready" }, (ok) => {
      if (chrome.runtime.lastError || !ok) return;
      const italian = navigator.language.toLowerCase().startsWith("it");
      document.body.classList.add("scribelane-bridge");
      document.querySelector("h1").textContent = "ScribeLane Webex";
      document.querySelector("p").textContent = italian
        ? "Se continui, l’estensione invierà il link della playlist Webex all’app ScribeLane sullo stesso computer. Il browser userà la sessione Webex già aperta."
        : "If you continue, the extension sends this Webex recording’s playlist URL to the ScribeLane app on this computer. Your browser uses its existing Webex session.";
      target.textContent = italian ? "Apri Webex e invia il link all’app" : "Open Webex and send the playlist to ScribeLane";
      target.addEventListener("click", event => {
        event.preventDefault();
        chrome.runtime.sendMessage({ type: "capture", target: target.href }, (armed) => {
          if (chrome.runtime.lastError || !armed) return;
          location.replace(target.href);
        });
      });
    });
  }
}
