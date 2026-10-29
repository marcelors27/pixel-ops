#include <Arduino.h>
#include <Arduino_GFX_Library.h>
#include <ESPmDNS.h>
#include <WebServer.h>
#include <WiFi.h>
#include <WiFiManager.h>
#include "lcd_ble.h"

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
WiFiManager wifiManager;
LcdBleReceiver bleReceiver;
bool httpStarted = false;
bool usbReceiving = false;
uint32_t usbLastByteAt = 0;
uint32_t usbChecksum = 0;
size_t usbOffset = 0;
String usbLine;
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

void renderFrame(uint16_t x = 0, uint16_t y = 0, uint16_t width = LCD_WIDTH, uint16_t height = LCD_HEIGHT) {
  auto *pixels = reinterpret_cast<uint16_t *>(frameBuffer);
  for (size_t index = 0; index < size_t(width) * height; ++index) {
    pixels[index] = __builtin_bswap16(pixels[index]);
  }
  display->draw16bitRGBBitmap(x, y, pixels, width, height);
  ++framesReceived;
  lastFrameAt = millis();
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
  renderFrame();
  server.send(204);
}
// USB uses the same big-endian RGB565 frame as HTTP, with CRC32 and acknowledgements.
void serviceUsb() {
  if (!frameBuffer) return;
  if (usbReceiving && millis() - usbLastByteAt > 5000) {
    usbReceiving = false;
    Serial.println("PXOPS ERROR timeout");
  }
  size_t budget = 4096;
  while (Serial.available() && budget--) {
    const uint8_t value = Serial.read();
    if (usbReceiving) {
      frameBuffer[usbOffset++] = value;
      usbLastByteAt = millis();
      if (usbOffset == FRAME_BYTES) {
        uint32_t crc = 0xffffffff;
        for (size_t i = 0; i < FRAME_BYTES; ++i) {
          crc ^= frameBuffer[i];
          for (int bit = 0; bit < 8; ++bit) crc = (crc >> 1) ^ (0xedb88320 & (0 - (crc & 1)));
        }
        usbReceiving = false;
        if ((crc ^ 0xffffffff) != usbChecksum) {
          Serial.println("PXOPS ERROR checksum");
        } else {
          renderFrame();
          Serial.println("PXOPS OK");
        }
      } else if (usbOffset % 1024 == 0) {
        Serial.println("PXOPS NEXT");
      }
    } else if (value == '\n') {
      if (usbLine == "PXOPS?") {
        Serial.println("PXOPS LCD 172 320 2");
      } else {
        unsigned int length = 0, checksum = 0;
        char extra;
        if (sscanf(usbLine.c_str(), "PXOPS2 %u %x %c", &length, &checksum, &extra) == 2 && length == FRAME_BYTES) {
          usbOffset = 0;
          usbChecksum = checksum;
          usbLastByteAt = millis();
          usbReceiving = true;
          Serial.println("PXOPS READY");
        } else {
          Serial.println("PXOPS ERROR header");
        }
      }
      usbLine = "";
    } else if (usbLine.length() < 80) {
      usbLine += static_cast<char>(value);
    } else {
      usbLine = "";
    }
  }
}
void startHttpWhenConnected() {
  if (httpStarted || WiFi.status() != WL_CONNECTED) return;
  wifiManager.stopConfigPortal();
  MDNS.begin("pixelops-lcd");
  MDNS.addService("http", "tcp", 80);
  const char *headers[] = {"Authorization"};
  server.collectHeaders(headers, 1);
  server.on("/", HTTP_GET, [] { server.sendHeader("Location", "/status"); server.send(302); });
  server.on("/status", HTTP_GET, handleStatus);
  server.on("/frame", HTTP_POST, finishFrameUpload, handleFrameUpload);
  server.begin();
  httpStarted = true;
}
}  // namespace

void setup() {
  Serial.setRxBufferSize(4096);
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

  bleReceiver.begin(frameBuffer, FRAME_BYTES);

  bool connected = false;
#if defined(WIFI_SSID_HEX) && defined(WIFI_PASS_HEX)
  const String configuredSsid = decodeHex(WIFI_SSID_HEX);
  const String configuredPassword = decodeHex(WIFI_PASS_HEX);
  WiFi.begin(configuredSsid.c_str(), configuredPassword.c_str());
  for (uint8_t attempt = 0; attempt < 200 && WiFi.status() != WL_CONNECTED; ++attempt) {
    serviceUsb();
    delay(10);
  }
  connected = WiFi.status() == WL_CONNECTED;
#endif

  wifiManager.setConfigPortalBlocking(false);
  wifiManager.setConnectTimeout(2);
  if (!connected) wifiManager.autoConnect("PixelOps-LCD-Setup");

  if (framesReceived == 0) drawMessage("PIXEL OPS READY", "USB ready. Wi-Fi: PixelOps-LCD-Setup");

}

void loop() {
  if (bleReceiver.process(!usbReceiving)) {
    renderFrame(bleReceiver.x(), bleReceiver.y(), bleReceiver.width(), bleReceiver.height());
    bleReceiver.complete();
  }
  if (!bleReceiver.busy()) serviceUsb();
  if (!usbReceiving && !bleReceiver.busy()) {
    wifiManager.process();
    startHttpWhenConnected();
    if (httpStarted) server.handleClient();
  }
  delay(1);
}
