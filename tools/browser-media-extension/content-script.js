let lastSignature = "";
let lastSentAt = 0;

publish();
setInterval(publish, 2000);
document.addEventListener("play", publish, true);
document.addEventListener("pause", publish, true);
document.addEventListener("visibilitychange", publish);

function publish() {
  const payload = readMediaState();
  const signature = JSON.stringify(payload);
  const now = Date.now();
  if (signature === lastSignature && now - lastSentAt < 5000) {
    return;
  }
  lastSignature = signature;
  lastSentAt = now;
  chrome.runtime.sendMessage({ type: "pixel-ops-media", payload });
}

function readMediaState() {
  const video = document.querySelector("video");
  const metadata = navigator.mediaSession && navigator.mediaSession.metadata;
  const title = cleanTitle((metadata && metadata.title) || document.title || "");
  const artist = cleanText((metadata && metadata.artist) || channelName() || sourceName());
  const album = cleanText((metadata && metadata.album) || "");
  const artwork = metadata && metadata.artwork && metadata.artwork.length ? metadata.artwork[metadata.artwork.length - 1].src : "";
  return {
    title,
    artist,
    album,
    source: sourceName(),
    url: location.href,
    artwork_url: artwork,
    is_playing: Boolean(video && !video.paused && !video.ended)
  };
}

function sourceName() {
  return location.hostname.includes("music.youtube.com") ? "YouTube Music" : "YouTube";
}

function channelName() {
  const selectors = [
    "ytmusic-player-bar .subtitle",
    "ytmusic-player-bar yt-formatted-string.byline",
    "#owner #channel-name a",
    "ytd-video-owner-renderer #channel-name a"
  ];
  for (const selector of selectors) {
    const element = document.querySelector(selector);
    const value = cleanText(element && element.textContent);
    if (value) {
      return value;
    }
  }
  return "";
}

function cleanTitle(value) {
  return cleanText(value).replace(/\s+-\s+YouTube(?: Music)?$/i, "");
}

function cleanText(value) {
  return String(value || "").replace(/\s+/g, " ").trim();
}
