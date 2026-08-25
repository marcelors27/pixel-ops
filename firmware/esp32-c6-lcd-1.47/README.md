# Pixel OPs firmware for ESP32-C6-LCD-1.47

Firmware for the Waveshare ESP32-C6-LCD-1.47 (172x320 ST7789). It exposes a
small HTTP output terminal and renders RGB565 frames produced by Pixel OPs.

## Build and upload

```bash
cd firmware/esp32-c6-lcd-1.47
pio run
pio run --target upload --upload-port /dev/cu.usbmodem21301
pio device monitor --port /dev/cu.usbmodem21301
```

On first boot, connect a phone or computer to `PixelOps-LCD-Setup` and select
the local Wi-Fi network. The device then advertises itself as
`http://pixelops-lcd.local` using mDNS.

The backlight is intentionally limited to 50%, following Waveshare's thermal
guidance. To require a bearer token, add a quoted `PIXEL_OPS_LCD_TOKEN` build
define in `platformio.ini` and configure the same token in Pixel OPs.

