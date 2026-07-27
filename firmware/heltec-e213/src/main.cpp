#include <Arduino.h>
#include <ESPmDNS.h>
#include <Preferences.h>
#include <WebServer.h>
#include <WiFi.h>
#include <heltec-eink-modules.h>
#include <mbedtls/base64.h>

namespace {
constexpr uint16_t kWidth = 250;
constexpr uint16_t kHeight = 122;
constexpr size_t kRowBytes = (kWidth + 7) / 8;
constexpr size_t kFrameBytes = kRowBytes * kHeight;
constexpr uint8_t kBootButtonPin = 0;
constexpr uint32_t kWifiTimeoutMs = 20000;
const char *kCollectedHeaders[] = {
    "Authorization", "X-Pixel-Ops-Width", "X-Pixel-Ops-Height",
    "X-Pixel-Ops-SHA256", "X-Pixel-Ops-Refresh", "X-Pixel-Ops-Encoding"};
uint8_t frameBuffer[kFrameBytes];

EInkDisplay_VisionMasterE213 display;
Preferences preferences;
WebServer server(80);
String accessToken;
String lastDigest;
uint32_t refreshCount = 0;
bool provisioning = false;

String deviceSuffix() {
  const uint64_t chip = ESP.getEfuseMac();
  char suffix[7];
  snprintf(suffix, sizeof(suffix), "%06llX", chip & 0xFFFFFFULL);
  return String(suffix);
}

void showMessage(const String &title, const String &line1, const String &line2 = "") {
  display.fastmodeOff();
  display.landscape();
  display.clearMemory();
  display.setTextSize(2);
  display.setCursor(8, 24);
  display.println(title);
  display.setTextSize(1);
  display.setCursor(8, 62);
  display.println(line1);
  if (!line2.isEmpty()) {
    display.setCursor(8, 84);
    display.println(line2);
  }
  display.update();
}

bool authorized() {
  if (accessToken.isEmpty()) {
    return true;
  }
  return server.header("Authorization") == "Bearer " + accessToken;
}

void sendJson(int status, const String &body) {
  server.send(status, "application/json", body);
}

void handleStatus() {
  if (!authorized()) {
    sendJson(401, R"({"error":"unauthorized"})");
    return;
  }
  String json = "{\"model\":\"heltec-vision-master-e213\",\"width\":250,\"height\":122";
  json += ",\"provisioning\":" + String(provisioning ? "true" : "false");
  json += ",\"ip\":\"" + (provisioning ? WiFi.softAPIP().toString() : WiFi.localIP().toString()) + "\"";
  json += ",\"rssi\":" + String(provisioning ? 0 : WiFi.RSSI());
  json += ",\"refresh_count\":" + String(refreshCount);
  json += ",\"last_sha256\":\"" + lastDigest + "\"}";
  sendJson(200, json);
}

void handleFrame() {
  if (!authorized()) {
    sendJson(401, R"({"error":"unauthorized"})");
    return;
  }
  if (provisioning) {
    sendJson(409, R"({"error":"wifi_not_configured"})");
    return;
  }
  if (server.header("X-Pixel-Ops-Width") != String(kWidth) ||
      server.header("X-Pixel-Ops-Height") != String(kHeight)) {
    sendJson(422, R"({"error":"invalid_dimensions"})");
    return;
  }

  const String &body = server.arg("plain");
  size_t decodedLength = 0;
  const int decodeResult = mbedtls_base64_decode(
      frameBuffer, sizeof(frameBuffer), &decodedLength,
      reinterpret_cast<const unsigned char *>(body.c_str()), body.length());
  if (server.header("X-Pixel-Ops-Encoding") != "base64" ||
      decodeResult != 0 || decodedLength != kFrameBytes) {
    sendJson(422, "{\"error\":\"invalid_frame_size\",\"expected\":" + String(kFrameBytes) +
                      ",\"encoded\":" + String(body.length()) +
                      ",\"decoded\":" + String(decodedLength) +
                      ",\"decode_result\":" + String(decodeResult) + "}");
    return;
  }

  const bool fullRefresh = server.header("X-Pixel-Ops-Refresh") == "full";
  if (fullRefresh) {
    display.fastmodeOff();
  } else {
    display.fastmodeOn();
  }
  display.landscape();
  display.clearMemory();
  for (uint16_t y = 0; y < kHeight; ++y) {
    const size_t row = static_cast<size_t>(y) * kRowBytes;
    for (uint16_t x = 0; x < kWidth; ++x) {
      if (frameBuffer[row + x / 8] & (0x80 >> (x % 8))) {
        display.drawPixel(x, y, BLACK);
      }
    }
  }
  display.update();
  lastDigest = server.header("X-Pixel-Ops-SHA256");
  ++refreshCount;
  sendJson(200, "{\"ok\":true,\"refresh_count\":" + String(refreshCount) + "}");
}

const char kPortalPage[] PROGMEM = R"HTML(
<!doctype html><html lang="pt-BR"><meta name="viewport" content="width=device-width">
<title>Pixel OPs E213</title><style>
body{font:16px system-ui;max-width:32rem;margin:3rem auto;padding:0 1rem;color:#182018}
label{display:block;margin:1rem 0}.card{border:2px solid #182018;padding:1.5rem}
input{box-sizing:border-box;width:100%;padding:.7rem;margin-top:.35rem}
button{padding:.8rem 1.2rem;background:#182018;color:white;border:0;font-weight:700}
</style><div class="card"><h1>Pixel OPs E213</h1>
<p>Conecte a tela à sua rede Wi-Fi de 2,4 GHz.</p>
<form method="post" action="/configure">
<label>Nome da rede<input name="ssid" required maxlength="32"></label>
<label>Senha Wi-Fi<input name="password" type="password" maxlength="64"></label>
<label>Token opcional<input name="token" maxlength="64"></label>
<button>Salvar e reiniciar</button></form></div></html>
)HTML";

void handleConfigure() {
  const String ssid = server.arg("ssid");
  if (ssid.isEmpty()) {
    server.send(400, "text/plain", "SSID obrigatorio");
    return;
  }
  preferences.begin("pixelops", false);
  preferences.putString("ssid", ssid);
  preferences.putString("password", server.arg("password"));
  preferences.putString("token", server.arg("token"));
  preferences.end();
  server.send(200, "text/html; charset=utf-8", "<h1>Salvo</h1><p>A tela vai reiniciar.</p>");
  delay(800);
  ESP.restart();
}

void startPortal() {
  provisioning = true;
  const String apName = "PixelOps-E213-" + deviceSuffix();
  WiFi.mode(WIFI_AP);
  WiFi.softAP(apName.c_str());
  showMessage("CONFIGURAR", apName, "Abra: 192.168.4.1");
  server.on("/", HTTP_GET, [] { server.send(200, "text/html; charset=utf-8", kPortalPage); });
  server.on("/configure", HTTP_POST, handleConfigure);
  server.on("/status", HTTP_GET, handleStatus);
  server.begin();
}

bool connectWifi() {
  preferences.begin("pixelops", true);
  const String ssid = preferences.getString("ssid");
  const String password = preferences.getString("password");
  accessToken = preferences.getString("token");
  preferences.end();
  if (ssid.isEmpty()) {
    return false;
  }
  WiFi.mode(WIFI_STA);
  WiFi.setHostname("pixelops-e213");
  WiFi.begin(ssid.c_str(), password.c_str());
  const uint32_t started = millis();
  while (WiFi.status() != WL_CONNECTED && millis() - started < kWifiTimeoutMs) {
    delay(250);
  }
  return WiFi.status() == WL_CONNECTED;
}

void startReceiver() {
  provisioning = false;
  MDNS.begin("pixelops-e213");
  server.collectHeaders(kCollectedHeaders, 6);
  server.on("/status", HTTP_GET, handleStatus);
  server.on("/frame", HTTP_POST, handleFrame);
  server.begin();
  showMessage("PIXEL OPS", WiFi.localIP().toString(), "pixelops-e213.local");
}
}  // namespace

void setup() {
  Serial.begin(115200);
  delay(500);
  pinMode(kBootButtonPin, INPUT_PULLUP);
  if (digitalRead(kBootButtonPin) == LOW) {
    preferences.begin("pixelops", false);
    preferences.clear();
    preferences.end();
    showMessage("RESET WIFI", "Credenciais apagadas");
    delay(1000);
  }
  if (connectWifi()) {
    startReceiver();
  } else {
    startPortal();
  }
}

void loop() {
  server.handleClient();
  delay(2);
}
