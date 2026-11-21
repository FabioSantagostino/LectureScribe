// Only the short-lived local LectureScribe page can arm a tab.
if (/^\/lecturescribe\/[A-Za-z0-9_-]{43}$/.test(location.pathname)) {
  const target = document.getElementById("playback");
  if (target) {
    chrome.runtime.sendMessage({ type: "capture", target: target.href }, (ok) => {
      if (chrome.runtime.lastError || !ok) return;
      location.replace(target.href);
    });
  }
}
