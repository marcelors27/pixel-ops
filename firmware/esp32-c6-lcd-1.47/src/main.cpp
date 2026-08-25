#include <Arduino.h>
#include <Arduino_GFX_Library.h>
#include <ESPmDNS.h>
#include <WebServer.h>
#include <WiFi.h>
#include <WiFiManager.h>

namespace {
constexpr uint16_t LCD_WIDTH = 172;
constexpr uint16_t LCD_HEIGHT = 320;
constexpr size_t FRAME_BYTES = LCD_WIDTH * LCD_HEIGHT * 2;
constexpr int LCD_MOSI = 6;
constexpr int LCD_SCLK = 7;
constexpr int LCD_CS = 14;
constexpr int LCD_DC = 15;
constexpr int LCD_RST = 21;
constexpr int LCD_BL = 22;
constexpr uint8_t BACKLIGHT_DUTY = 127;  // Waveshare recommends <= 50%.

Arduino_DataBus *bus = new Arduino_ESP32SPI(LCD_DC, LCD_CS, LCD_SCLK, LCD_MOSI, GFX_NOT_DEFINED);
Arduino_GFX *display = new Arduino_ST7789(bus, LCD_RST, 0, true, LCD_WIDTH, LCD_HEIGHT, 34, 0, 34, 0);
WebServer server(80);
uint8_t *frameBuffer = nullptr;
size_t uploadOffset = 0;
bool uploadAccepted = false;
bool uploadComplete = false;
uint32_t framesReceived = 0;
uint32_t lastFrameAt = 0;

String decodeHex(const char *encoded) {
  String decoded;
  const size_t length = strlen(encoded);
  decoded.reserve(length / 2);
  for (size_t index = 0; index + 1 < length; index += 2) {
    char pair[] = {encoded[index], encoded[index + 1], '\0'};
    decoded += static_cast<char>(strtoul(pair, nullptr, 16));
  }
  return decoded;
}

bool authorized() {
#ifdef PIXEL_OPS_LCD_TOKEN
  const String expected = String("Bearer ") + PIXEL_OPS_LCD_TOKEN;
  return server.header("Authorization") == expected;
#else
  return true;
#endif
}

void drawMessage(const char *title, const String &detail) {
  display->fillScreen(0x0000);
  display->setTextColor(0xFFFF);
  display->setTextSize(2);
  display->setCursor(10, 22);
  display->println(title);
  display->setTextSize(1);
  display->setCursor(10, 58);
  display->println(detail);
}

void handleStatus() {
  if (!authorized()) {
    server.send(401, "application/json", "{\"error\":\"unauthorized\"}");
    return;
  }
  const String json = String("{\"ok\":true,\"device\":\"ESP32-C6-LCD-1.47\",\"width\":172,\"height\":320,") +
                      "\"frames_received\":" + framesReceived + ",\"last_frame_ms\":" + lastFrameAt +
                      ",\"ip\":\"" + WiFi.localIP().toString() + "\"}";
  server.send(200, "application/json", json);
}

void handleFrameUpload() {
  HTTPUpload &upload = server.upload();
  if (upload.status == UPLOAD_FILE_START) {
    uploadOffset = 0;
    uploadComplete = false;
    uploadAccepted = authorized() && frameBuffer != nullptr;
    return;
  }
  if (!uploadAccepted) return;
  if (upload.status == UPLOAD_FILE_WRITE) {
    if (uploadOffset + upload.currentSize > FRAME_BYTES) {
      uploadAccepted = false;
      return;
    }
    memcpy(frameBuffer + uploadOffset, upload.buf, upload.currentSize);
    uploadOffset += upload.currentSize;
    return;
  }
  if (upload.status == UPLOAD_FILE_END) {
    uploadComplete = uploadOffset == FRAME_BYTES;
  } else if (upload.status == UPLOAD_FILE_ABORTED) {
    uploadAccepted = false;
  }
}

void finishFrameUpload() {
  if (!authorized()) {
    server.send(401, "application/json", "{\"error\":\"unauthorized\"}");
    return;
  }
  if (!uploadAccepted || !uploadComplete) {
    server.send(400, "application/json", "{\"error\":\"frame must be 172x320 RGB565\"}");
    return;
  }
  auto *pixels = reinterpret_cast<uint16_t *>(frameBuffer);
  for (size_t index = 0; index < LCD_WIDTH * LCD_HEIGHT; ++index) {
    pixels[index] = __builtin_bswap16(pixels[index]);
  }
  display->draw16bitRGBBitmap(0, 0, pixels, LCD_WIDTH, LCD_HEIGHT);
  ++framesReceived;
  lastFrameAt = millis();
  server.send(204);
}
}  // namespace

void setup() {
  Serial.begin(115200);
  display->begin(80000000);
  display->setRotation(0);
  display->invertDisplay(false);
  ledcAttach(LCD_BL, 5000, 8);
  ledcWrite(LCD_BL, BACKLIGHT_DUTY);
  drawMessage("PIXEL OPS", "Connecting to Wi-Fi...");

  frameBuffer = static_cast<uint8_t *>(malloc(FRAME_BYTES));
  if (frameBuffer == nullptr) {
    drawMessage("MEMORY ERROR", "Unable to allocate frame buffer");
    return;
  }

  bool connected = false;
#if defined(WIFI_SSID_HEX) && defined(WIFI_PASS_HEX)
  const String configuredSsid = decodeHex(WIFI_SSID_HEX);
  const String configuredPassword = decodeHex(WIFI_PASS_HEX);
  WiFi.begin(configuredSsid.c_str(), configuredPassword.c_str());
  for (uint8_t attempt = 0; attempt < 40 && WiFi.status() != WL_CONNECTED; ++attempt) {
    delay(500);
  }
  connected = WiFi.status() == WL_CONNECTED;
#endif

  WiFiManager wifiManager;
  wifiManager.setConfigPortalTimeout(180);
  if (!connected && !wifiManager.autoConnect("PixelOps-LCD-Setup")) {
    drawMessage("WI-FI SETUP", "Connect to PixelOps-LCD-Setup");
    delay(3000);
    ESP.restart();
  }

  MDNS.begin("pixelops-lcd");
  MDNS.addService("http", "tcp", 80);
  const char *headers[] = {"Authorization"};
  server.collectHeaders(headers, 1);
  server.on("/", HTTP_GET, [] { server.sendHeader("Location", "/status"); server.send(302); });
  server.on("/status", HTTP_GET, handleStatus);
  server.on("/frame", HTTP_POST, finishFrameUpload, handleFrameUpload);
  server.begin();
  drawMessage("PIXEL OPS READY", String("http://") + WiFi.localIP().toString());
  Serial.printf("Pixel OPs LCD ready at http://%s and http://pixelops-lcd.local\n", WiFi.localIP().toString().c_str());
}

void loop() {
  server.handleClient();
  delay(1);
}
