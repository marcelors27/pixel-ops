#pragma once
#include <NimBLEDevice.h>
#include <freertos/FreeRTOS.h>
#include <freertos/queue.h>

// BLE callbacks only enqueue bytes. The Arduino loop owns decoding and display RAM.
class LcdBleReceiver {
 public:
  static constexpr const char* SERVICE = "c0de0001-504f-4c43-8000-000000000001";
  static constexpr const char* COMMAND = "c0de0002-504f-4c43-8000-000000000001";
  static constexpr const char* DATA = "c0de0003-504f-4c43-8000-000000000001";
  static constexpr const char* STATUS = "c0de0004-504f-4c43-8000-000000000001";
  static constexpr const char* INFO = "c0de0005-504f-4c43-8000-000000000001";

  bool begin(uint8_t* buffer, size_t capacity) {
    buffer_ = buffer;
    capacity_ = capacity;
    queue_ = xQueueCreate(4, sizeof(Packet));
    if (!queue_) return false;
    NimBLEDevice::init("PixelOps-LCD");
    NimBLEDevice::setMTU(247);
    auto* server = NimBLEDevice::createServer();
    server->setCallbacks(&serverCallbacks_, false);
    auto* service = server->createService(SERVICE);
    auto* command = service->createCharacteristic(COMMAND, NIMBLE_PROPERTY::WRITE, 17);
    auto* data = service->createCharacteristic(DATA, NIMBLE_PROPERTY::WRITE, 240);
    status_ = service->createCharacteristic(STATUS, NIMBLE_PROPERTY::NOTIFY, 40);
    auto* info = service->createCharacteristic(INFO, NIMBLE_PROPERTY::READ, 40);
    info->setValue("PXOPS LCD BLE 2 172 320");
    command->setCallbacks(&commandCallbacks_);
    data->setCallbacks(&dataCallbacks_);
    server->start();
    auto* advertising = NimBLEDevice::getAdvertising();
    advertising->setName("PixelOps-LCD");
    advertising->addServiceUUID(SERVICE);
    advertising->enableScanResponse(true);
    return advertising->start();
  }

  uint16_t x() const { return x_; }
  uint16_t y() const { return y_; }
  uint16_t width() const { return width_; }
  uint16_t height() const { return height_; }
  bool busy() const { return receiving_; }

  // Returns true only when a complete, verified raw RGB565 frame is ready.
  bool process(bool bufferAvailable) {
    if (!queue_) return false;
    if (receiving_ && millis() - lastByteAt_ > 15000) fail("ERROR timeout");
    Packet packet;
    if (xQueueReceive(queue_, &packet, 0) != pdTRUE) return false;
    if (packet.kind == 2) {
      receiving_ = false;
      return false;
    }
    if (packet.kind == 0) {
      if (!bufferAvailable) { reply("ERROR busy"); return false; }
      if (packet.size != 17 || packet.bytes[0] > 1) { fail("ERROR header"); return false; }
      encodedSize_ = read32(packet.bytes + 1);
      checksum_ = read32(packet.bytes + 5);
      x_ = read16(packet.bytes + 9);
      y_ = read16(packet.bytes + 11);
      width_ = read16(packet.bytes + 13);
      height_ = read16(packet.bytes + 15);
      if (!width_ || !height_ || x_ + width_ > 172 || y_ + height_ > 320) {
        fail("ERROR region"); return false;
      }
      frameSize_ = size_t(width_) * height_ * 2;
      if (frameSize_ > capacity_) { fail("ERROR size"); return false; }
      rle_ = packet.bytes[0] == 1;
      if (!encodedSize_ || encodedSize_ > frameSize_ || encodedSize_ % (rle_ ? 4 : 2) ||
          (!rle_ && encodedSize_ != frameSize_)) { fail("ERROR size"); return false; }
      received_ = decoded_ = 0;
      receiving_ = true;
      lastByteAt_ = millis();
      reply("READY");
      return false;
    }
    if (!receiving_) { reply("ERROR no frame"); return false; }
    if (!packet.size || received_ + packet.size > encodedSize_ || packet.size % (rle_ ? 4 : 2)) {
      fail("ERROR size"); return false;
    }
    if (rle_) {
      for (size_t i = 0; i < packet.size; i += 4) {
        const size_t count = (packet.bytes[i] << 8) | packet.bytes[i + 1];
        if (!count || decoded_ + count * 2 > frameSize_) { fail("ERROR run"); return false; }
        for (size_t j = 0; j < count; ++j) {
          buffer_[decoded_++] = packet.bytes[i + 2];
          buffer_[decoded_++] = packet.bytes[i + 3];
        }
      }
    } else {
      memcpy(buffer_ + decoded_, packet.bytes, packet.size);
      decoded_ += packet.size;
    }
    received_ += packet.size;
    lastByteAt_ = millis();
    if (received_ < encodedSize_) { reply("NEXT"); return false; }
    if (decoded_ != frameSize_) { fail("ERROR decoded size"); return false; }
    uint32_t crc = 0xffffffff;
    for (size_t i = 0; i < frameSize_; ++i) {
      crc ^= buffer_[i];
      for (int bit = 0; bit < 8; ++bit) crc = (crc >> 1) ^ (0xedb88320 & (0 - (crc & 1)));
    }
    if ((crc ^ 0xffffffff) != checksum_) { fail("ERROR checksum"); return false; }
    return true;
  }

  void complete() { receiving_ = false; reply("OK"); }

 private:
  struct Packet { uint8_t kind; uint16_t size; uint8_t bytes[240]; };
  uint16_t x_ = 0, y_ = 0, width_ = 172, height_ = 320;
  size_t frameSize_ = 0;
  static uint16_t read16(const uint8_t* p) { return (uint16_t(p[0]) << 8) | p[1]; }
  uint16_t activeHandle_ = 0xffff;
  QueueHandle_t queue_ = nullptr;
  NimBLECharacteristic* status_ = nullptr;
  uint8_t* buffer_ = nullptr;
  size_t capacity_ = 0, received_ = 0, decoded_ = 0, encodedSize_ = 0;
  uint32_t checksum_ = 0, lastByteAt_ = 0;
  bool receiving_ = false, rle_ = false;
  static uint32_t read32(const uint8_t* p) {
    return (uint32_t(p[0]) << 24) | (uint32_t(p[1]) << 16) | (uint32_t(p[2]) << 8) | p[3];
  }
  void reply(const char* message) { status_->setValue(message); status_->notify(); }
  void fail(const char* message) { receiving_ = false; reply(message); }
  void enqueue(uint8_t kind, const uint8_t* data, size_t size) {
    if (!queue_ || size > 240) return;
    Packet packet{};
    packet.kind = kind;
    packet.size = size;
    if (size) memcpy(packet.bytes, data, size);
    // A stop-and-wait client has at most one pending packet.
    if (xQueueSend(queue_, &packet, 0) != pdTRUE) {
      NimBLEDevice::getServer()->disconnect(activeHandle_);
    }
  }
  class WriteCallbacks : public NimBLECharacteristicCallbacks {
   public:
    WriteCallbacks(LcdBleReceiver& owner, uint8_t kind) : owner_(owner), kind_(kind) {}
    void onWrite(NimBLECharacteristic* characteristic, NimBLEConnInfo& info) override {
      if (info.getConnHandle() != owner_.activeHandle_) return;
      auto value = characteristic->getValue();
      owner_.enqueue(kind_, value.data(), value.size());
    }
   private:
    LcdBleReceiver& owner_;
    uint8_t kind_;
  } commandCallbacks_{*this, 0}, dataCallbacks_{*this, 1};
  class ServerCallbacks : public NimBLEServerCallbacks {
   public:
    explicit ServerCallbacks(LcdBleReceiver& owner) : owner_(owner) {}
    void onConnect(NimBLEServer* server, NimBLEConnInfo& info) override {
      if (owner_.activeHandle_ != 0xffff) { server->disconnect(info.getConnHandle()); return; }
      owner_.activeHandle_ = info.getConnHandle();
      server->updateConnParams(info.getConnHandle(), 12, 24, 0, 200);
    }
    void onDisconnect(NimBLEServer*, NimBLEConnInfo& info, int) override {
      if (info.getConnHandle() != owner_.activeHandle_) return;
      owner_.activeHandle_ = 0xffff;
      owner_.enqueue(2, nullptr, 0);
      NimBLEDevice::startAdvertising();
    }
   private:
    LcdBleReceiver& owner_;
  } serverCallbacks_{*this};
};
