#include <Arduino.h>
#include <ESPmDNS.h>
#include <HTTPClient.h>
#include <Preferences.h>
#include <WebServer.h>
#include <WiFi.h>
#include <WiFiClientSecure.h>
#include <esp_system.h>
#include <esp_sleep.h>
#include <time.h>
#include <heltec-eink-modules.h>
#include <mbedtls/base64.h>

namespace {
constexpr uint16_t kWidth = 250;
constexpr uint16_t kHeight = 122;
constexpr size_t kRowBytes = (kWidth + 7) / 8;
constexpr size_t kFrameBytes = kRowBytes * kHeight;
constexpr uint8_t kBootButtonPin = 0;
constexpr uint8_t kBatteryReadPin = 7;
constexpr uint8_t kBatteryControlPin = 46;
constexpr float kBatteryDividerRatio = 4.9F;
constexpr uint8_t kBatterySampleCount = 16;
constexpr uint32_t kWifiTimeoutMs = 20000;
constexpr uint32_t kPcProbeIntervalMs = 4000;
constexpr uint32_t kPcProbeOfflineIntervalMs = 30000;
constexpr uint32_t kInternetProbeOnlineIntervalMs = 60000;
constexpr uint32_t kInternetProbeOfflineIntervalMs = 30000;
constexpr uint32_t kDefaultPcLeaseMs = 12000;
constexpr uint32_t kBatterySampleIntervalMs = 60000;
constexpr uint32_t kStandaloneRefreshIntervalMs = 300000;
constexpr uint32_t kStandaloneLowBatteryRefreshIntervalMs = 900000;
constexpr uint32_t kStandaloneCriticalRefreshIntervalMs = 1800000;
constexpr uint32_t kWeatherRefreshIntervalMs = 1800000;
constexpr uint8_t kBatteryHistorySize = 8;
constexpr uint8_t kFailureThreshold = 2;
constexpr uint8_t kRecoveryThreshold = 2;
constexpr uint8_t kStandaloneFullRefreshEvery = 120;
const char *kCollectedHeaders[] = {
    "Authorization", "X-Pixel-Ops-Width", "X-Pixel-Ops-Height",
    "X-Pixel-Ops-SHA256", "X-Pixel-Ops-Refresh", "X-Pixel-Ops-Encoding",
    "X-Pixel-Ops-Dirty-X", "X-Pixel-Ops-Dirty-Y", "X-Pixel-Ops-Dirty-Width",
    "X-Pixel-Ops-Dirty-Height", "X-Pixel-Ops-Battery-Powered",
    "X-Pixel-Ops-Battery-Lease-Seconds", "X-Pixel-Ops-Pull-Port",
    "X-Pixel-Ops-Deep-Sleep-Seconds",
    "X-Pixel-Ops-Sequence", "X-Pixel-Ops-Lease-Seconds", "X-Pixel-Ops-Health-Port",
    "X-Pixel-Ops-Weather-Enabled", "X-Pixel-Ops-Latitude", "X-Pixel-Ops-Longitude",
    "X-Pixel-Ops-Utc-Offset-Minutes", "X-Pixel-Ops-Hud-Battery",
    "X-Pixel-Ops-Hud-Wireless", "X-Pixel-Ops-Hud-Status"};

uint8_t frameBuffer[kFrameBytes];

enum class RuntimeMode { Pc, StandaloneOnline, StandaloneLocal };
enum class StandalonePage { Summary, Diagnostics };
enum class BatteryState { Unknown, Charging, Discharging, Stable, Low, Critical };
struct HudBox {
  bool enabled = false;
  uint16_t x = 0;
  uint16_t y = 0;
  uint16_t width = 1;
  uint16_t height = 1;
};

EInkDisplay_VisionMasterE213 display;
Preferences preferences;
WebServer server(80);
String accessToken;
String lastDigest;
uint32_t refreshCount = 0;
bool provisioning = false;
RuntimeMode runtimeMode = RuntimeMode::StandaloneLocal;
IPAddress pcAddress;
uint16_t pcHealthPort = 0;
uint32_t pcLeaseMs = kDefaultPcLeaseMs;
uint32_t lastPcHeartbeatAt = 0;
uint32_t lastPcProbeAt = 0;
uint32_t lastInternetProbeAt = 0;
uint32_t lastBatteryReadAt = 0;
uint32_t lastStandaloneRenderAt = 0;
uint32_t lastWeatherAttemptAt = 0;
uint8_t pcFailures = 0;
uint8_t pcSuccesses = 0;
uint8_t internetFailures = 0;
uint8_t internetSuccesses = 0;
uint8_t standaloneRefreshCount = 0;
bool pcAvailable = false;
bool internetAvailable = false;
bool captivePortal = false;
bool standaloneDirty = true;
bool needsPcFrame = true;
bool batteryPowered = false;
String pullHost;
uint16_t pullPort = 0;
uint32_t deepSleepSeconds = 300;
uint32_t deepSleepAt = 0;
int lastRenderedMinute = -1;
float batteryVoltage = 0.0F;
float batteryHistory[kBatteryHistorySize] = {};
uint32_t batteryHistoryAt[kBatteryHistorySize] = {};
uint8_t batteryHistoryCount = 0;
uint8_t batteryHistoryNext = 0;
BatteryState batteryState = BatteryState::Unknown;
StandalonePage standalonePage = StandalonePage::Summary;
bool lastButtonLevel = HIGH;
uint32_t lastButtonChangeAt = 0;
bool weatherEnabled = false;
bool weatherAvailable = false;
float weatherLatitude = 0.0F;
float weatherLongitude = 0.0F;
float weatherTemperature = 0.0F;
int weatherCode = -1;
int utcOffsetMinutes = -180;
time_t weatherUpdatedAt = 0;
HudBox batteryHud;
HudBox wirelessHud;
HudBox statusHud;

String hudBoxValue(const HudBox &box) {
  if (!box.enabled) return "off";
  return String(box.x) + "," + String(box.y) + "," + String(box.width) + "," + String(box.height);
}

HudBox parseHudBox(const String &value) {
  HudBox box;
  if (value.isEmpty() || value == "off") return box;
  int separators[3] = {-1, -1, -1};
  int found = 0;
  for (int index = 0; index < value.length() && found < 3; ++index) {
    if (value.charAt(index) == ',') separators[found++] = index;
  }
  if (found != 3) return box;
  const int x = value.substring(0, separators[0]).toInt();
  const int y = value.substring(separators[0] + 1, separators[1]).toInt();
  const int width = value.substring(separators[1] + 1, separators[2]).toInt();
  const int height = value.substring(separators[2] + 1).toInt();
  if (x < 0 || y < 0 || x >= kWidth || y >= kHeight || width <= 0 || height <= 0) return box;
  box.enabled = true;
  box.x = static_cast<uint16_t>(x);
  box.y = static_cast<uint16_t>(y);
  box.width = static_cast<uint16_t>(min(width, kWidth - x));
  box.height = static_cast<uint16_t>(min(height, kHeight - y));
  return box;
}

float readBatteryVoltage() {
  // The E213 switches its 390k/100k divider through ADC_CTRL and an NPN stage.
  digitalWrite(kBatteryControlPin, HIGH);
  delay(5);

  uint32_t totalMillivolts = 0;
  for (uint8_t sample = 0; sample < kBatterySampleCount; ++sample) {
    totalMillivolts += analogReadMilliVolts(kBatteryReadPin);
    delay(2);
  }

  digitalWrite(kBatteryControlPin, LOW);
  const float adcMillivolts =
      static_cast<float>(totalMillivolts) / kBatterySampleCount;
  return adcMillivolts * kBatteryDividerRatio / 1000.0F;
}

uint8_t batteryPercent(float voltage) {
  struct Point {
    float voltage;
    uint8_t percent;
  };
  constexpr Point curve[] = {
      {3.20F, 0}, {3.50F, 10}, {3.60F, 20}, {3.70F, 40}, {3.80F, 60},
      {3.90F, 75}, {4.00F, 85}, {4.08F, 94}, {4.12F, 100}};
  if (voltage <= curve[0].voltage) return 0;
  for (size_t i = 1; i < sizeof(curve) / sizeof(curve[0]); ++i) {
    if (voltage <= curve[i].voltage) {
      const float span = curve[i].voltage - curve[i - 1].voltage;
      const float position = (voltage - curve[i - 1].voltage) / span;
      return curve[i - 1].percent + static_cast<uint8_t>(
             position * (curve[i].percent - curve[i - 1].percent) + 0.5F);
    }
  }
  return 100;
}

const char *batteryStateName(BatteryState state) {
  switch (state) {
    case BatteryState::Charging: return "charging";
    case BatteryState::Discharging: return "discharging";
    case BatteryState::Stable: return "stable";
    case BatteryState::Low: return "low";
    case BatteryState::Critical: return "critical";
    case BatteryState::Unknown: return "unknown";
  }
  return "unknown";
}

const char *batteryStateLabel(BatteryState state) {
  switch (state) {
    case BatteryState::Charging: return "Carregando";
    case BatteryState::Discharging: return "Em bateria";
    case BatteryState::Stable: return "Estavel";
    case BatteryState::Low: return "Bateria baixa";
    case BatteryState::Critical: return "BATERIA CRITICA";
    case BatteryState::Unknown: return "Avaliando";
  }
  return "Avaliando";
}

BatteryState classifyBattery() {
  if (batteryVoltage <= 3.35F) return BatteryState::Critical;
  if (batteryVoltage <= 3.50F) return BatteryState::Low;
  if (batteryHistoryCount < 4) return BatteryState::Unknown;
  const uint8_t oldest = batteryHistoryCount < kBatteryHistorySize ? 0 : batteryHistoryNext;
  const uint8_t newest = (batteryHistoryNext + kBatteryHistorySize - 1) % kBatteryHistorySize;
  const uint32_t elapsed = batteryHistoryAt[newest] - batteryHistoryAt[oldest];
  if (elapsed < 180000) return BatteryState::Unknown;
  const float delta = batteryHistory[newest] - batteryHistory[oldest];
  if (delta >= 0.012F) return BatteryState::Charging;
  if (delta <= -0.012F) return BatteryState::Discharging;
  return BatteryState::Stable;
}

void sampleBattery(uint32_t now, bool force = false) {
  if (!force && lastBatteryReadAt != 0 && now - lastBatteryReadAt < kBatterySampleIntervalMs) return;
  batteryVoltage = readBatteryVoltage();
  lastBatteryReadAt = now;
  batteryHistory[batteryHistoryNext] = batteryVoltage;
  batteryHistoryAt[batteryHistoryNext] = now;
  batteryHistoryNext = (batteryHistoryNext + 1) % kBatteryHistorySize;
  if (batteryHistoryCount < kBatteryHistorySize) ++batteryHistoryCount;
  const BatteryState nextState = classifyBattery();
  if (nextState != batteryState) {
    batteryState = nextState;
    standaloneDirty = true;
  }
}

const char *resetReasonName() {
  switch (esp_reset_reason()) {
    case ESP_RST_POWERON: return "power_on";
    case ESP_RST_EXT: return "external";
    case ESP_RST_SW: return "software";
    case ESP_RST_PANIC: return "panic";
    case ESP_RST_INT_WDT: return "interrupt_watchdog";
    case ESP_RST_TASK_WDT: return "task_watchdog";
    case ESP_RST_WDT: return "watchdog";
    case ESP_RST_DEEPSLEEP: return "deep_sleep";
    case ESP_RST_BROWNOUT: return "brownout";
    case ESP_RST_SDIO: return "sdio";
    default: return "unknown";
  }
}

String formatUptime(uint32_t milliseconds) {
  const uint32_t minutes = milliseconds / 60000U;
  const uint32_t days = minutes / 1440U;
  const uint32_t hours = (minutes / 60U) % 24U;
  const uint32_t remainingMinutes = minutes % 60U;
  if (days > 0) return String(days) + "d " + String(hours) + "h";
  return String(hours) + "h " + String(remainingMinutes) + "m";
}

const char *modeName(RuntimeMode mode) {
  switch (mode) {
    case RuntimeMode::Pc: return "pc";
    case RuntimeMode::StandaloneOnline: return "standalone_online";
    case RuntimeMode::StandaloneLocal: return "standalone_local";
  }
  return "standalone_local";
}

void setPcAvailable(bool available) {
  if (pcAvailable != available) {
    pcAvailable = available;
    standaloneDirty = true;
  }
}

void setInternetAvailable(bool available, bool portal = false) {
  if (internetAvailable != available || captivePortal != portal) {
    internetAvailable = available;
    captivePortal = portal;
    standaloneDirty = true;
  }
}

void loadStandaloneConfig() {
  preferences.begin("pixelops", true);
  weatherEnabled = preferences.getBool("wx_enabled", false);
  weatherLatitude = preferences.getFloat("wx_lat", 0.0F);
  weatherLongitude = preferences.getFloat("wx_lon", 0.0F);
  utcOffsetMinutes = preferences.getInt("utc_offset", -180);
  weatherAvailable = preferences.getBool("wx_cached", false);
  weatherTemperature = preferences.getFloat("wx_temp", 0.0F);
  weatherCode = preferences.getInt("wx_code", -1);
  weatherUpdatedAt = static_cast<time_t>(preferences.getULong64("wx_updated", 0));
  batteryHud = parseHudBox(preferences.getString("hud_battery", "off"));
  wirelessHud = parseHudBox(preferences.getString("hud_wireless", "off"));
  statusHud = parseHudBox(preferences.getString("hud_status", "off"));
  preferences.end();
}

void saveWeatherCache() {
  preferences.begin("pixelops", false);
  preferences.putBool("wx_cached", weatherAvailable);
  preferences.putFloat("wx_temp", weatherTemperature);
  preferences.putInt("wx_code", weatherCode);
  preferences.putULong64("wx_updated", static_cast<uint64_t>(weatherUpdatedAt));
  preferences.end();
}

void syncStandaloneConfigFromHeartbeat() {
  const bool requestedWeather = server.header("X-Pixel-Ops-Weather-Enabled") == "1";
  const float requestedLatitude = server.header("X-Pixel-Ops-Latitude").toFloat();
  const float requestedLongitude = server.header("X-Pixel-Ops-Longitude").toFloat();
  const int requestedOffset = constrain(server.header("X-Pixel-Ops-Utc-Offset-Minutes").toInt(), -720, 840);
  const HudBox requestedBatteryHud = parseHudBox(server.header("X-Pixel-Ops-Hud-Battery"));
  const HudBox requestedWirelessHud = parseHudBox(server.header("X-Pixel-Ops-Hud-Wireless"));
  const HudBox requestedStatusHud = parseHudBox(server.header("X-Pixel-Ops-Hud-Status"));
  const bool locationValid = requestedLatitude >= -90.0F && requestedLatitude <= 90.0F &&
                             requestedLongitude >= -180.0F && requestedLongitude <= 180.0F;
  const bool hudChanged = hudBoxValue(requestedBatteryHud) != hudBoxValue(batteryHud) ||
                          hudBoxValue(requestedWirelessHud) != hudBoxValue(wirelessHud) ||
                          hudBoxValue(requestedStatusHud) != hudBoxValue(statusHud);
  const bool changed = requestedWeather != weatherEnabled ||
                       (locationValid && (abs(requestedLatitude - weatherLatitude) > 0.0001F ||
                                          abs(requestedLongitude - weatherLongitude) > 0.0001F)) ||
                       requestedOffset != utcOffsetMinutes || hudChanged;
  if (!changed) return;
  weatherEnabled = requestedWeather;
  if (locationValid) {
    weatherLatitude = requestedLatitude;
    weatherLongitude = requestedLongitude;
  }
  utcOffsetMinutes = requestedOffset;
  batteryHud = requestedBatteryHud;
  wirelessHud = requestedWirelessHud;
  statusHud = requestedStatusHud;
  preferences.begin("pixelops", false);
  preferences.putBool("wx_enabled", weatherEnabled);
  preferences.putFloat("wx_lat", weatherLatitude);
  preferences.putFloat("wx_lon", weatherLongitude);
  preferences.putInt("utc_offset", utcOffsetMinutes);
  preferences.putString("hud_battery", hudBoxValue(batteryHud));
  preferences.putString("hud_wireless", hudBoxValue(wirelessHud));
  preferences.putString("hud_status", hudBoxValue(statusHud));
  preferences.end();
  configTime(utcOffsetMinutes * 60, 0, "pool.ntp.org", "time.cloudflare.com");
  lastWeatherAttemptAt = 0;
  standaloneDirty = true;
}

float jsonNumber(const String &body, const char *key, float fallback) {
  const String marker = "\"" + String(key) + "\":";
  // Open-Meteo emits the same keys in current_units before the numeric current block.
  const int start = body.lastIndexOf(marker);
  if (start < 0) return fallback;
  const int valueStart = start + marker.length();
  int valueEnd = valueStart;
  while (valueEnd < static_cast<int>(body.length())) {
    const char ch = body[valueEnd];
    if (!(isDigit(ch) || ch == '-' || ch == '+' || ch == '.')) break;
    ++valueEnd;
  }
  return body.substring(valueStart, valueEnd).toFloat();
}

bool fetchWeather() {
  if (!weatherEnabled || !internetAvailable) return false;
  String url = "https://api.open-meteo.com/v1/forecast?latitude=" + String(weatherLatitude, 5) +
               "&longitude=" + String(weatherLongitude, 5) +
               "&current=temperature_2m,weather_code&timezone=auto";
  WiFiClientSecure client;
  client.setInsecure();
  HTTPClient http;
  http.setConnectTimeout(3000);
  http.setTimeout(4000);
  if (!http.begin(client, url)) return false;
  const int status = http.GET();
  if (status != 200) {
    http.end();
    return false;
  }
  const String body = http.getString();
  http.end();
  const float temperature = jsonNumber(body, "temperature_2m", NAN);
  const int code = static_cast<int>(jsonNumber(body, "weather_code", -1));
  if (isnan(temperature) || code < 0) return false;
  weatherTemperature = temperature;
  weatherCode = code;
  weatherUpdatedAt = time(nullptr);
  weatherAvailable = true;
  saveWeatherCache();
  standaloneDirty = true;
  return true;
}

void updateWeather(uint32_t now) {
  if (!weatherEnabled || !internetAvailable) return;
  if (lastWeatherAttemptAt != 0 && now - lastWeatherAttemptAt < kWeatherRefreshIntervalMs) return;
  lastWeatherAttemptAt = now;
  fetchWeather();
}

const char *weatherLabel(int code) {
  if (code == 0) return "Limpo";
  if (code <= 3) return "Nublado";
  if (code == 45 || code == 48) return "Neblina";
  if (code >= 51 && code <= 67) return "Chuva";
  if (code >= 71 && code <= 77) return "Neve";
  if (code >= 80 && code <= 82) return "Pancadas";
  if (code >= 95) return "Temporal";
  return "Clima";
}

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

void loadPowerConfig() {
  preferences.begin("pixelops", true);
  batteryPowered = preferences.getBool("battery_mode", false);
  pullHost = preferences.getString("pull_host");
  pullPort = preferences.getUShort("pull_port", 0);
  deepSleepSeconds = preferences.getUInt("sleep_seconds", 300);
  lastDigest = preferences.getString("last_digest");
  preferences.end();
  deepSleepSeconds = constrain(deepSleepSeconds, 30UL, 86400UL);
}

void persistLastDigest(const String &digest) {
  if (digest.isEmpty() || digest == lastDigest) return;
  lastDigest = digest;
  preferences.begin("pixelops", false);
  preferences.putString("last_digest", lastDigest);
  preferences.end();
}

void persistPowerConfig(const String &host, uint16_t port, uint32_t sleepSeconds) {
  sleepSeconds = constrain(sleepSeconds, 30UL, 86400UL);
  if (batteryPowered && pullHost == host && pullPort == port && deepSleepSeconds == sleepSeconds) return;
  batteryPowered = true;
  pullHost = host;
  pullPort = port;
  deepSleepSeconds = sleepSeconds;
  preferences.begin("pixelops", false);
  preferences.putBool("battery_mode", true);
  preferences.putString("pull_host", pullHost);
  preferences.putUShort("pull_port", pullPort);
  preferences.putUInt("sleep_seconds", deepSleepSeconds);
  preferences.end();
}

void renderReceivedFrame(bool fullRefresh, int dirtyX, int dirtyY, int dirtyWidth, int dirtyHeight) {
  const bool updateWholeScreen = fullRefresh || dirtyWidth <= 0 || dirtyHeight <= 0;
  if (fullRefresh) {
    display.fastmodeOff();
    display.landscape();
    display.fullscreen();
  } else {
    display.fastmodeOn();
    display.landscape();
    if (updateWholeScreen) {
      display.fullscreen();
    } else {
      display.setWindow(dirtyX, dirtyY, dirtyWidth, dirtyHeight);
    }
  }
  display.clearMemory();
  const uint16_t drawX = updateWholeScreen ? 0 : dirtyX;
  const uint16_t drawY = updateWholeScreen ? 0 : dirtyY;
  const uint16_t drawWidth = updateWholeScreen ? kWidth : dirtyWidth;
  const uint16_t drawHeight = updateWholeScreen ? kHeight : dirtyHeight;
  for (uint16_t y = drawY; y < drawY + drawHeight; ++y) {
    const size_t row = static_cast<size_t>(y) * kRowBytes;
    for (uint16_t x = drawX; x < drawX + drawWidth; ++x) {
      if (frameBuffer[row + x / 8] & (0x80 >> (x % 8))) display.drawPixel(x, y, BLACK);
    }
  }
  display.update();
}

void enterDeepSleep() {
  WiFi.disconnect(true);
  WiFi.mode(WIFI_OFF);
  esp_sleep_enable_timer_wakeup(static_cast<uint64_t>(deepSleepSeconds) * 1000000ULL);
  delay(50);
  esp_deep_sleep_start();
}

bool pullLatestFrame() {
  if (!batteryPowered || pullHost.isEmpty() || pullPort == 0) return false;
  WiFiClient client;
  HTTPClient http;
  const String url = "http://" + pullHost + ":" + String(pullPort) + "/eink/frame";
  http.setConnectTimeout(4000);
  http.setTimeout(8000);
  if (!http.begin(client, url)) return false;
  const char *responseHeaders[] = {
      "ETag", "X-Pixel-Ops-SHA256", "X-Pixel-Ops-Refresh",
      "X-Pixel-Ops-Dirty-X", "X-Pixel-Ops-Dirty-Y",
      "X-Pixel-Ops-Dirty-Width", "X-Pixel-Ops-Dirty-Height",
      "X-Pixel-Ops-Sleep-Seconds"};
  http.collectHeaders(responseHeaders, sizeof(responseHeaders) / sizeof(responseHeaders[0]));
  if (!accessToken.isEmpty()) http.addHeader("Authorization", "Bearer " + accessToken);
  if (!lastDigest.isEmpty()) http.addHeader("If-None-Match", "\"" + lastDigest + "\"");
  const int status = http.GET();
  const uint32_t requestedSleep = static_cast<uint32_t>(http.header("X-Pixel-Ops-Sleep-Seconds").toInt());
  if (requestedSleep >= 30) persistPowerConfig(pullHost, pullPort, requestedSleep);
  if (status == 304) {
    http.end();
    return true;
  }
  if (status != 200 || http.getSize() != static_cast<int>(kFrameBytes)) {
    http.end();
    return false;
  }
  WiFiClient *stream = http.getStreamPtr();
  const size_t received = stream->readBytes(frameBuffer, kFrameBytes);
  if (received != kFrameBytes) {
    http.end();
    return false;
  }
  const bool fullRefresh = http.header("X-Pixel-Ops-Refresh") == "full";
  const int dirtyX = constrain(http.header("X-Pixel-Ops-Dirty-X").toInt(), 0, kWidth - 1);
  const int dirtyY = constrain(http.header("X-Pixel-Ops-Dirty-Y").toInt(), 0, kHeight - 1);
  const int dirtyWidth = constrain(http.header("X-Pixel-Ops-Dirty-Width").toInt(), 1, kWidth - dirtyX);
  const int dirtyHeight = constrain(http.header("X-Pixel-Ops-Dirty-Height").toInt(), 1, kHeight - dirtyY);
  renderReceivedFrame(fullRefresh, dirtyX, dirtyY, dirtyWidth, dirtyHeight);
  persistLastDigest(http.header("X-Pixel-Ops-SHA256"));
  ++refreshCount;
  http.end();
  return true;
}

bool probePcHealth() {
  if (pcHealthPort == 0 || pcAddress == IPAddress()) {
    return false;
  }
  WiFiClient client;
  client.setTimeout(1000);
  if (!client.connect(pcAddress, pcHealthPort, 1500)) {
    return false;
  }
  client.print("GET /healthz HTTP/1.1\r\nHost: pixelops-pc\r\nConnection: close\r\n\r\n");
  const uint32_t started = millis();
  while (!client.available() && client.connected() && millis() - started < 1000) {
    delay(5);
  }
  const String statusLine = client.readStringUntil('\n');
  client.stop();
  return statusLine.indexOf(" 204 ") >= 0;
}

void updatePcWatchdog(uint32_t now) {
  if (batteryPowered) {
    setPcAvailable(lastPcHeartbeatAt != 0 && now - lastPcHeartbeatAt <= pcLeaseMs);
    return;
  }
  if (lastPcHeartbeatAt != 0 && now - lastPcHeartbeatAt <= pcLeaseMs) {
    pcFailures = 0;
    pcSuccesses = kRecoveryThreshold;
    setPcAvailable(true);
    return;
  }
  const uint32_t probeInterval = pcAvailable ? kPcProbeIntervalMs : kPcProbeOfflineIntervalMs;
  if (now - lastPcProbeAt < probeInterval) {
    return;
  }
  lastPcProbeAt = now;
  if (probePcHealth()) {
    pcFailures = 0;
    pcSuccesses = min<uint8_t>(kRecoveryThreshold, pcSuccesses + 1);
    if (pcSuccesses >= kRecoveryThreshold) setPcAvailable(true);
  } else {
    pcSuccesses = 0;
    pcFailures = min<uint8_t>(kFailureThreshold, pcFailures + 1);
    if (pcFailures >= kFailureThreshold) setPcAvailable(false);
  }
}

bool probeInternet(bool &portal) {
  portal = false;
  if (WiFi.status() != WL_CONNECTED) {
    return false;
  }
  IPAddress resolved;
  if (!WiFi.hostByName("connectivitycheck.gstatic.com", resolved)) {
    return false;
  }
  WiFiClient client;
  HTTPClient http;
  http.setConnectTimeout(2000);
  http.setTimeout(2500);
  if (!http.begin(client, "http://connectivitycheck.gstatic.com/generate_204")) {
    return false;
  }
  const int status = http.GET();
  http.end();
  if (status == 204) return true;
  portal = status >= 200 && status < 400;
  return false;
}

void updateInternetWatchdog(uint32_t now) {
  if (WiFi.status() != WL_CONNECTED) {
    internetFailures = kFailureThreshold;
    internetSuccesses = 0;
    setInternetAvailable(false);
    return;
  }
  uint32_t interval = internetAvailable ? kInternetProbeOnlineIntervalMs : kInternetProbeOfflineIntervalMs;
  if (batteryPowered || batteryState == BatteryState::Low || batteryState == BatteryState::Critical) interval *= 3;
  if (now - lastInternetProbeAt < interval) {
    return;
  }
  lastInternetProbeAt = now;
  bool portal = false;
  if (probeInternet(portal)) {
    internetFailures = 0;
    internetSuccesses = min<uint8_t>(kRecoveryThreshold, internetSuccesses + 1);
    if (internetSuccesses >= kRecoveryThreshold) setInternetAvailable(true);
  } else {
    internetSuccesses = 0;
    internetFailures = min<uint8_t>(kFailureThreshold, internetFailures + 1);
    if (internetFailures >= kFailureThreshold) setInternetAvailable(false, portal);
  }
}

RuntimeMode desiredRuntimeMode() {
  if (pcAvailable) return RuntimeMode::Pc;
  return internetAvailable ? RuntimeMode::StandaloneOnline : RuntimeMode::StandaloneLocal;
}

void updateRuntimeMode() {
  const RuntimeMode desired = desiredRuntimeMode();
  if (runtimeMode != desired) {
    runtimeMode = desired;
    standaloneDirty = runtimeMode != RuntimeMode::Pc;
    if (runtimeMode != RuntimeMode::Pc) needsPcFrame = true;
  }
}

void drawBattery(uint8_t x, uint8_t y, uint8_t percent) {
  display.drawRect(x, y, 28, 13, BLACK);
  display.fillRect(x + 28, y + 4, 3, 5, BLACK);
  const uint8_t fill = static_cast<uint8_t>(24U * percent / 100U);
  if (fill > 0) display.fillRect(x + 2, y + 2, fill, 9, BLACK);
}

void drawHudFrame(const HudBox &box, const char *title) {
  if (!box.enabled) return;
  display.fillRect(box.x, box.y, box.width, box.height, WHITE);
  display.drawRect(box.x, box.y, box.width, box.height, BLACK);
  display.setTextSize(1);
  display.setCursor(box.x + 3, box.y + 3);
  display.print(title);
}

void drawBatteryHud() {
  if (!batteryHud.enabled) return;
  drawHudFrame(batteryHud, "BAT");
  const uint8_t percent = batteryPercent(batteryVoltage);
  const uint16_t valueY = batteryHud.y + max(11, static_cast<int>(batteryHud.height) - 12);
  if (batteryHud.width >= 48 && batteryHud.height >= 22) {
    const uint16_t iconX = batteryHud.x + 4;
    display.drawRect(iconX, valueY, 22, 8, BLACK);
    display.fillRect(iconX + 22, valueY + 2, 2, 4, BLACK);
    const uint8_t fill = static_cast<uint8_t>(18U * percent / 100U);
    if (fill) display.fillRect(iconX + 2, valueY + 2, fill, 4, BLACK);
    display.setCursor(batteryHud.x + 31, valueY);
  } else {
    display.setCursor(batteryHud.x + 3, valueY);
  }
  display.print(percent);
  display.print('%');
}

void drawWirelessHud() {
  if (!wirelessHud.enabled) return;
  drawHudFrame(wirelessHud, "WIRELESS");
  const uint16_t valueY = wirelessHud.y + max(11, static_cast<int>(wirelessHud.height) - 12);
  display.setCursor(wirelessHud.x + 3, valueY);
  display.print("PC ");
  display.print(pcAvailable ? "ON" : "OFF");
  if (wirelessHud.width >= 72) {
    display.print(' ');
    display.print(WiFi.status() == WL_CONNECTED ? WiFi.RSSI() : 0);
  }
}

void drawStatusHud() {
  if (!statusHud.enabled) return;
  drawHudFrame(statusHud, "STATUS");
  const uint16_t valueY = statusHud.y + max(11, static_cast<int>(statusHud.height) - 12);
  display.setCursor(statusHud.x + 3, valueY);
  if (runtimeMode == RuntimeMode::Pc) display.print("PC");
  else if (runtimeMode == RuntimeMode::StandaloneOnline) display.print("ONLINE");
  else display.print("OFFLINE");
}

void drawConfiguredTelemetryHuds() {
  drawBatteryHud();
  drawWirelessHud();
  drawStatusHud();
}

void renderStandalone(bool forceFull = false) {
  if (runtimeMode == RuntimeMode::Pc) return;
  sampleBattery(millis(), batteryHistoryCount == 0);
  const uint8_t percent = batteryPercent(batteryVoltage);
  const bool fullRefresh = forceFull || standaloneRefreshCount % kStandaloneFullRefreshEvery == 0;
  if (fullRefresh) display.fastmodeOff(); else display.fastmodeOn();
  display.landscape();
  display.clearMemory();

  display.setTextSize(1);
  if (standalonePage == StandalonePage::Diagnostics) {
    display.setCursor(7, 6);
    display.print("DIAGNOSTICO LOCAL");
    display.drawLine(6, 19, 243, 19, BLACK);
  }

  if (standalonePage == StandalonePage::Diagnostics) {
    display.setTextSize(1);
    display.setCursor(8, 28);
    display.print("Modo: ");
    display.print(modeName(runtimeMode));
    display.setCursor(8, 42);
    display.print("WiFi: ");
    display.print(WiFi.RSSI());
    display.print(" dBm  IP: ");
    display.print(WiFi.localIP());
    display.setCursor(8, 56);
    display.print("Uptime: ");
    display.print(formatUptime(millis()));
    display.setCursor(8, 70);
    display.print("Reset: ");
    display.print(resetReasonName());
    display.setCursor(8, 84);
    display.print("Bat: ");
    display.print(batteryVoltage, 3);
    display.print("V ");
    display.print(percent);
    display.print("% ");
    display.print(batteryStateLabel(batteryState));
    display.setCursor(8, 103);
    display.print("BOTAO: voltar  WEB: /status");
  } else {
    struct tm localTime;
    const bool hasTime = getLocalTime(&localTime, 20);
    char clockText[8] = "--:--";
    char dateText[20] = "hora indisponivel";
    if (hasTime) {
      strftime(clockText, sizeof(clockText), "%H:%M", &localTime);
      strftime(dateText, sizeof(dateText), "%d/%m/%Y", &localTime);
      lastRenderedMinute = localTime.tm_min;
    }
    display.setTextSize(4);
    display.setCursor(7, 8);
    display.print(clockText);
    display.setTextSize(1);
    display.setCursor(10, 47);
    display.print(dateText);
    display.setCursor(10, 61);
    if (weatherAvailable) {
      display.print(weatherTemperature, 1);
      display.print(" C");
    } else {
      display.print(batteryVoltage, 2);
      display.print(" V");
    }
    display.setCursor(10, 75);
    display.print(weatherAvailable ? weatherLabel(weatherCode) :
                                    (WiFi.status() == WL_CONNECTED ? "WiFi OK" : "WiFi OFF"));
    drawConfiguredTelemetryHuds();
  }
  display.update();
  ++standaloneRefreshCount;
  lastStandaloneRenderAt = millis();
  standaloneDirty = false;
}

void serviceStandalone(uint32_t now) {
  if (runtimeMode == RuntimeMode::Pc) return;
  uint32_t refreshInterval = kStandaloneRefreshIntervalMs;
  if (batteryState == BatteryState::Low) refreshInterval = kStandaloneLowBatteryRefreshIntervalMs;
  if (batteryState == BatteryState::Critical) refreshInterval = kStandaloneCriticalRefreshIntervalMs;
  if (standaloneDirty || now - lastStandaloneRenderAt >= refreshInterval) {
    renderStandalone(standaloneDirty);
  }
}

void serviceButton(uint32_t now) {
  const bool level = digitalRead(kBootButtonPin);
  if (level != lastButtonLevel && now - lastButtonChangeAt >= 50) {
    lastButtonChangeAt = now;
    lastButtonLevel = level;
    if (level == LOW && runtimeMode != RuntimeMode::Pc) {
      standalonePage = standalonePage == StandalonePage::Summary ? StandalonePage::Diagnostics
                                                                 : StandalonePage::Summary;
      standaloneDirty = true;
    }
  }
}

void handleHeartbeat() {
  if (!authorized()) {
    sendJson(401, R"({"error":"unauthorized"})");
    return;
  }
  pcAddress = server.client().remoteIP();
  pcHealthPort = static_cast<uint16_t>(constrain(server.header("X-Pixel-Ops-Health-Port").toInt(), 0, 65535));
  const long requestedLease = server.header("X-Pixel-Ops-Lease-Seconds").toInt();
  pcLeaseMs = static_cast<uint32_t>(constrain(requestedLease > 0 ? requestedLease * 1000L : kDefaultPcLeaseMs, 5000L, 60000L));
  lastPcHeartbeatAt = millis();
  pcFailures = 0;
  pcSuccesses = kRecoveryThreshold;
  setPcAvailable(true);
  syncStandaloneConfigFromHeartbeat();
  updateRuntimeMode();
  sendJson(200, "{\"ok\":true,\"sequence\":" + server.header("X-Pixel-Ops-Sequence") +
                    ",\"lease_ms\":" + String(pcLeaseMs) +
                    ",\"needs_frame\":" + String(needsPcFrame ? "true" : "false") +
                    ",\"battery_voltage\":" + String(batteryVoltage, 3) +
                    ",\"battery_percent\":" + String(batteryPercent(batteryVoltage)) +
                    ",\"battery_state\":\"" + String(batteryStateName(batteryState)) + "\"" +
                    ",\"rssi\":" + String(WiFi.RSSI()) +
                    ",\"pc_available\":" + String(pcAvailable ? "true" : "false") +
                    ",\"internet_available\":" + String(internetAvailable ? "true" : "false") +
                    ",\"mode\":\"" + String(modeName(runtimeMode)) + "\"}");
}

void handleStatus() {
  if (!authorized()) {
    sendJson(401, R"({"error":"unauthorized"})");
    return;
  }
  sampleBattery(millis());
  String json = "{\"model\":\"heltec-vision-master-e213\",\"width\":250,\"height\":122";
  json += ",\"provisioning\":" + String(provisioning ? "true" : "false");
  json += ",\"ip\":\"" + (provisioning ? WiFi.softAPIP().toString() : WiFi.localIP().toString()) + "\"";
  json += ",\"rssi\":" + String(provisioning ? 0 : WiFi.RSSI());
  json += ",\"battery_voltage\":" + String(batteryVoltage, 3);
  json += ",\"battery_percent\":" + String(batteryPercent(batteryVoltage));
  json += ",\"battery_state\":\"" + String(batteryStateName(batteryState)) + "\"";
  json += ",\"battery_samples\":" + String(batteryHistoryCount);
  json += ",\"battery_measurement\":\"voltage_only\"";
  json += ",\"watchdog_protocol\":1";
  json += ",\"deep_sleep_protocol\":1";
  json += ",\"battery_powered\":" + String(batteryPowered ? "true" : "false");
  json += ",\"deep_sleep_seconds\":" + String(deepSleepSeconds);
  json += ",\"pull_host\":\"" + pullHost + "\"";
  json += ",\"pull_port\":" + String(pullPort);
  json += ",\"mode\":\"" + String(modeName(runtimeMode)) + "\"";
  json += ",\"pc_available\":" + String(pcAvailable ? "true" : "false");
  json += ",\"pc_failures\":" + String(pcFailures);
  json += ",\"internet_available\":" + String(internetAvailable ? "true" : "false");
  json += ",\"internet_failures\":" + String(internetFailures);
  json += ",\"captive_portal\":" + String(captivePortal ? "true" : "false");
  json += ",\"uptime_ms\":" + String(millis());
  json += ",\"reset_reason\":\"" + String(resetReasonName()) + "\"";
  json += ",\"standalone_page\":\"" + String(standalonePage == StandalonePage::Summary ? "summary" : "diagnostics") + "\"";
  json += ",\"hud_battery\":\"" + hudBoxValue(batteryHud) + "\"";
  json += ",\"hud_wireless\":\"" + hudBoxValue(wirelessHud) + "\"";
  json += ",\"hud_status\":\"" + hudBoxValue(statusHud) + "\"";
  json += ",\"needs_pc_frame\":" + String(needsPcFrame ? "true" : "false");
  json += ",\"weather_enabled\":" + String(weatherEnabled ? "true" : "false");
  json += ",\"weather_available\":" + String(weatherAvailable ? "true" : "false");
  if (weatherAvailable) {
    json += ",\"weather_temperature\":" + String(weatherTemperature, 1);
    json += ",\"weather_code\":" + String(weatherCode);
    json += ",\"weather_updated_at\":" + String(static_cast<uint32_t>(weatherUpdatedAt));
  }
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

  batteryPowered = server.header("X-Pixel-Ops-Battery-Powered") == "1";
  if (batteryPowered) {
    const long requestedLease = server.header("X-Pixel-Ops-Battery-Lease-Seconds").toInt();
    pcLeaseMs = static_cast<uint32_t>(constrain(requestedLease * 1000L, 30000L, 3600000L));
    const uint16_t requestedPort = static_cast<uint16_t>(constrain(server.header("X-Pixel-Ops-Pull-Port").toInt(), 0, 65535));
    const uint32_t requestedSleep = static_cast<uint32_t>(server.header("X-Pixel-Ops-Deep-Sleep-Seconds").toInt());
    if (requestedPort > 0) persistPowerConfig(server.client().remoteIP().toString(), requestedPort, requestedSleep);
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
  const bool hasDirtyRegion = server.hasHeader("X-Pixel-Ops-Dirty-X") &&
                              server.hasHeader("X-Pixel-Ops-Dirty-Y") &&
                              server.hasHeader("X-Pixel-Ops-Dirty-Width") &&
                              server.hasHeader("X-Pixel-Ops-Dirty-Height");
  const int dirtyX = hasDirtyRegion ? constrain(server.header("X-Pixel-Ops-Dirty-X").toInt(), 0, kWidth - 1) : 0;
  const int dirtyY = hasDirtyRegion ? constrain(server.header("X-Pixel-Ops-Dirty-Y").toInt(), 0, kHeight - 1) : 0;
  const int dirtyWidth = hasDirtyRegion ? constrain(server.header("X-Pixel-Ops-Dirty-Width").toInt(), 1, kWidth - dirtyX) : kWidth;
  const int dirtyHeight = hasDirtyRegion ? constrain(server.header("X-Pixel-Ops-Dirty-Height").toInt(), 1, kHeight - dirtyY) : kHeight;
  renderReceivedFrame(fullRefresh, dirtyX, dirtyY, dirtyWidth, dirtyHeight);
  needsPcFrame = false;
  if (batteryPowered) {
    persistLastDigest(server.header("X-Pixel-Ops-SHA256"));
  } else {
    lastDigest = server.header("X-Pixel-Ops-SHA256");
  }
  ++refreshCount;
  pcAddress = server.client().remoteIP();
  lastPcHeartbeatAt = millis();
  pcFailures = 0;
  pcSuccesses = kRecoveryThreshold;
  setPcAvailable(true);
  runtimeMode = RuntimeMode::Pc;
  sendJson(200, "{\"ok\":true,\"refresh_count\":" + String(refreshCount) + "}");
  if (batteryPowered && pullPort > 0) deepSleepAt = millis() + 750;
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
  WiFi.setSleep(true);
  WiFi.setAutoReconnect(true);
  WiFi.persistent(false);
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
  server.collectHeaders(kCollectedHeaders, sizeof(kCollectedHeaders) / sizeof(kCollectedHeaders[0]));
  server.on("/status", HTTP_GET, handleStatus);
  server.on("/heartbeat", HTTP_POST, handleHeartbeat);
  server.on("/frame", HTTP_POST, handleFrame);
  server.begin();
  configTime(utcOffsetMinutes * 60, 0, "pool.ntp.org", "time.cloudflare.com");
  lastInternetProbeAt = millis() - kInternetProbeOfflineIntervalMs;
  renderStandalone(true);
}
}  // namespace

void setup() {
  Serial.begin(115200);
  delay(500);
  pinMode(kBootButtonPin, INPUT_PULLUP);
  pinMode(kBatteryControlPin, OUTPUT);
  digitalWrite(kBatteryControlPin, LOW);
  analogReadResolution(12);
  analogSetPinAttenuation(kBatteryReadPin, ADC_2_5db);
  sampleBattery(millis(), true);
  loadStandaloneConfig();
  loadPowerConfig();
  if (digitalRead(kBootButtonPin) == LOW) {
    preferences.begin("pixelops", false);
    preferences.clear();
    preferences.end();
    batteryPowered = false;
    pullHost = "";
    pullPort = 0;
    showMessage("RESET WIFI", "Credenciais apagadas");
    delay(1000);
  }
  if (connectWifi()) {
    if (batteryPowered && !pullHost.isEmpty() && pullPort > 0) {
      pullLatestFrame();
      enterDeepSleep();
    } else {
      startReceiver();
    }
  } else if (batteryPowered) {
    enterDeepSleep();
  } else {
    startPortal();
  }
}

void loop() {
  server.handleClient();
  if (deepSleepAt != 0 && static_cast<int32_t>(millis() - deepSleepAt) >= 0) enterDeepSleep();
  if (!provisioning) {
    const uint32_t now = millis();
    sampleBattery(now);
    serviceButton(now);
    updatePcWatchdog(now);
    updateInternetWatchdog(now);
    updateWeather(now);
    updateRuntimeMode();
    serviceStandalone(now);
  }
  delay(2);
}
