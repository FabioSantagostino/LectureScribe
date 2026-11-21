const api = globalThis.browser || chrome;
const webex = ["https://*.webex.com/*", "https://*.webex.com.cn/*"];
const keyFor = (id) => `capture_${id}`;

function webexURL(value) {
  try {
    const url = new URL(value);
    if (url.protocol === "https:" && !url.username && !url.password && !url.port &&
        /\.webex\.com(?:\.cn)?$/.test(url.hostname)) return url;
  } catch {
    // Ignore malformed event URLs.
  }
  return null;
}

api.runtime.onMessage.addListener((message, sender, respond) => {
  if (sender.frameId !== 0 || sender.tab?.id == null) return;
  const bridge = sender.url;
  if (!/^http:\/\/127\.0\.0\.1:\d{1,5}\/scribelane\/[A-Za-z0-9_-]{43}$/.test(bridge)) return;
  if (message.type === "ready") {
    fetch(bridge + "/ready", { method: "POST" })
      .then(response => respond(response.ok), () => respond(false));
    return true;
  }
  if (message.type !== "capture") return;
  const target = webexURL(message.target);
  if (!target?.pathname.toLowerCase().split("/").includes("playback")) return;
  const key = keyFor(sender.tab.id);
  api.storage.session.set({ [key]: { bridge, expiry: Date.now() + 200000 } })
    .then(() => respond(true), () => respond(false));
  return true;
});

api.webRequest.onHeadersReceived.addListener(async (request) => {
  if (request.tabId < 0 || request.statusCode !== 200 ||
      !webexURL(request.url)?.pathname.toLowerCase().endsWith(".m3u8") ||
      !webexURL(request.initiator || request.documentUrl || request.originUrl || "")) return;
  const contentType = request.responseHeaders?.find(h => h.name.toLowerCase() === "content-type")?.value;
  if (/^(text\/html|application\/(?:xhtml\+xml|json))\b/i.test(contentType || "")) return;
  const key = keyFor(request.tabId);
  const job = (await api.storage.session.get(key))[key];
  if (!job) return;
  if (Date.now() > job.expiry) {
    await api.storage.session.remove(key);
    return;
  }
  try {
    const response = await fetch(job.bridge + "/playlist", { method: "POST", body: request.url });
    if (response.ok) await api.storage.session.remove(key);
  } catch {
    // The queue item may have been cancelled and its local port closed.
  }
}, { urls: webex }, ["responseHeaders"]);

api.tabs.onRemoved.addListener((id) => api.storage.session.remove(keyFor(id)));
