const PIXEL_OPS_ENDPOINT = "http://127.0.0.1:47832/media/now-playing";
const PIXEL_OPS_TOKEN = "";
const snapshots = new Map();

chrome.runtime.onMessage.addListener((message, sender) => {
  if (!message || message.type !== "pixel-ops-media") {
    return;
  }
  const tabId = sender.tab && Number.isFinite(sender.tab.id) ? sender.tab.id : null;
  if (tabId === null) {
    return;
  }
  snapshots.set(tabId, {
    ...sanitize(message.payload || {}),
    tabId,
    audible: Boolean(sender.tab && sender.tab.audible),
    updatedAt: Date.now()
  });
  publishBestSnapshot();
});

chrome.tabs.onRemoved.addListener((tabId) => {
  snapshots.delete(tabId);
  publishBestSnapshot();
});

chrome.tabs.onUpdated.addListener((tabId, changeInfo, tab) => {
  if (changeInfo.audible !== undefined && snapshots.has(tabId)) {
    const snapshot = snapshots.get(tabId);
    snapshots.set(tabId, { ...snapshot, audible: Boolean(tab.audible), updatedAt: Date.now() });
    publishBestSnapshot();
  }
});

setInterval(() => {
  publishBestSnapshot();
}, 5000);

function sanitize(payload) {
  return {
    provider: providerForUrl(payload.url),
    title: String(payload.title || "").slice(0, 240),
    artist: String(payload.artist || "").slice(0, 160),
    album: String(payload.album || "").slice(0, 160),
    source: String(payload.source || "").slice(0, 80),
    url: String(payload.url || "").slice(0, 1000),
    artwork_url: String(payload.artwork_url || "").slice(0, 1000),
    is_playing: Boolean(payload.is_playing)
  };
}

function providerForUrl(url) {
  const value = String(url || "").toLowerCase();
  if (value.includes("music.youtube.com")) {
    return "youtube_music";
  }
  if (value.includes("youtube.com") || value.includes("youtu.be")) {
    return "youtube";
  }
  return "browser";
}

function publishBestSnapshot() {
  const now = Date.now();
  const candidates = [...snapshots.values()].filter((snapshot) => now - snapshot.updatedAt < 15000);
  const playing = candidates.filter((snapshot) => snapshot.is_playing && snapshot.title);
  const snapshot = selectBest(playing) || selectBest(candidates);
  if (!snapshot) {
    postSnapshot({ provider: "browser", title: "", is_playing: false });
    return;
  }
  postSnapshot(snapshot);
}

function selectBest(candidates) {
  if (!candidates.length) {
    return null;
  }
  return candidates
    .slice()
    .sort((left, right) => score(right) - score(left) || right.updatedAt - left.updatedAt)[0];
}

function score(snapshot) {
  let value = 0;
  if (snapshot.audible) value += 100;
  if (snapshot.provider === "youtube_music") value += 30;
  if (snapshot.is_playing) value += 20;
  if (snapshot.artist) value += 10;
  if (/music|audio|lyric|jazz|vinyl|lo-?fi|playlist|mix|set/i.test(snapshot.title)) value += 8;
  if (/list=RD/i.test(snapshot.url)) value += 8;
  return value;
}

async function postSnapshot(snapshot) {
  const headers = { "Content-Type": "application/json" };
  if (PIXEL_OPS_TOKEN) {
    headers["X-Pixel-Ops-Token"] = PIXEL_OPS_TOKEN;
  }
  try {
    await fetch(PIXEL_OPS_ENDPOINT, {
      method: "POST",
      headers,
      body: JSON.stringify(snapshot)
    });
  } catch (_error) {
    // Pixel OPs may be stopped; the next content update will try again.
  }
}
