publishSession();
window.setInterval(publishSession, 30000);
document.addEventListener("visibilitychange", () => {
  if (!document.hidden) publishSession();
});

function publishSession() {
  chrome.runtime.sendMessage({ type: "pixel-ops-crosshero-session-seen" });
}
