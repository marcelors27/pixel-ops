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


## Atualizar dados por USB

Instale este firmware uma vez: no Config Studio, abra **Firmware dos painéis
ESP32**, selecione **Waveshare ESP32-C6 LCD 1.47**, escolha a porta e use
**Instalar atualização**.

No editor do ecrã Waveshare, escolha `usb` em **Ligação para atualizar dados**.
Deixe **Porta USB** vazia para detetar um único ESP32 USB nativo, ou indique a
porta apresentada na secção de firmware. Guarde e reinicie o runtime com
**Stop run / Start run**. Os dados passam a atualizar continuamente pelo cabo,
sem depender de Wi-Fi. Com vários ESP32 ligados, indique a porta explicitamente.
Escolha `http` para voltar à ligação Wi-Fi.

Configuração JSON do dispositivo LCD:

```json
{"lcd": {"transport": "usb", "port": "", "timeout_seconds": 10, "min_frame_interval_seconds": 0.1}}
```

USB CDC usa 115200 baud e o mesmo formato RGB565 big-endian (172×320).
`PXOPS?\n` identifica a versão (`PXOPS LCD 172 320 2`). O host envia
`PXOPS2 110080 <crc32-hex>\n`, aguarda `PXOPS READY`, envia 110080 bytes e
aguarda `PXOPS OK`. O dispositivo rejeita dimensão incorreta, checksum inválido
ou transferência parada por cinco segundos. Apenas frames completos são
apresentados. O acesso USB é local e físico; o token continua a proteger HTTP.

A versão 2 confirma cada bloco de 1024 bytes com `PXOPS NEXT` (o último
recebe `PXOPS OK`), evitando saturar o buffer USB do ESP32.

## Atualizar dados por Bluetooth

No Config Studio, escolha `bluetooth` em **Ligação para atualizar dados** do
Waveshare. O firmware anuncia `PixelOps-LCD`; a deteção automática procura apenas
o serviço Bluetooth do Pixel OPs. Com vários painéis, preencha **Identificador
Bluetooth** (no Mac, o UUID devolvido pela deteção). Guarde e reinicie o runtime.
O cabo pode fornecer apenas energia; as imagens seguem por Bluetooth.

O Python usa `bleak` (incluído em `requirements.txt`). Se o macOS pedir acesso
Bluetooth, permita-o à aplicação que executa Pixel OPs. A aplicação empacotada
inclui a descrição de uso Bluetooth no Info.plist.

```json
{"lcd": {"transport": "bluetooth", "bluetooth_address": "", "bluetooth_frame_interval_seconds": 1, "timeout_seconds": 15}}
```

BLE v1 anuncia o serviço `c0de0001-504f-4c43-8000-000000000001`. Os UUIDs com
sufixos iniciais `0002`, `0003`, `0004` e `0005` representam comando, dados,
notificações e identificação. O comando tem 9 bytes: modo (0 = RGB565 cru,
1 = RLE), comprimento codificado uint32 big-endian e CRC32 dos pixels originais.
RLE consiste em pares uint16 big-endian de contagem e cor. Cada bloco tem no
máximo 240 bytes, respeita o MTU e recebe `NEXT`; o último recebe `OK` apenas
após validar e apresentar o frame. `READY` confirma o cabeçalho.

O Bluetooth aceita um cliente e não exige emparelhamento. USB e Wi-Fi continuam
disponíveis selecionando `usb` ou `http`. O novo firmware usa uma partição de
aplicação de 3 MB para acomodar os três transportes.

BLE v2 acrescenta x/y/largura/altura (uint16 big-endian) ao comando, totalizando
17 bytes. Apenas o retângulo alterado é enviado e desenhado; a primeira imagem
após ligar/religar é completa. O host mantém compatibilidade com BLE v1, mas
firmware v2 é necessário para acelerar atualizações parciais do HUD.
