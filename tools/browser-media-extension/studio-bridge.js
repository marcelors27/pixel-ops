window.addEventListener("message", (event) => {
  if (event.source !== window || !event.data || event.data.type !== "pixel-ops-crosshero-cookie-request") return;
  chrome.runtime.sendMessage({ type: "pixel-ops-crosshero-cookie-request" });
});

chrome.runtime.onMessage.addListener((message) => {
  if (!message || message.type !== "pixel-ops-crosshero-cookie-result") return;
  window.postMessage({
    type: "pixel-ops-crosshero-cookie-result",
    result: message.result || { ok: false, message: "A extensão não retornou uma resposta." }
  }, window.location.origin);
});
