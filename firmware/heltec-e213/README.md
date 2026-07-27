# Pixel OPs — Heltec Vision Master E213

Firmware Wi-Fi para usar a tela e-ink de 250×122 como um output do Pixel OPs.

## Gravar

```bash
cd firmware/heltec-e213
pio run -t upload
```

Na primeira inicialização, conecte o celular ou computador à rede
`PixelOps-E213-XXXXXX` e abra `http://192.168.4.1`. Informe uma rede Wi-Fi de
2,4 GHz. O token é opcional, mas precisa ser igual ao configurado no runtime.

Para apagar as credenciais, mantenha **BOOT** pressionado enquanto reinicia a
placa. A tela volta a exibir o portal de configuração.

O modo `invert` é opcional. O layout padrão mantém os painéis claros e o texto
escuro sem inversão.

## Protocolo

- `GET /status`: estado e dimensões nativas.
- `POST /frame`: frame monocromático de 3.904 bytes, MSB primeiro e alinhado
  por linha.
- Cabeçalhos: `X-Pixel-Ops-Width`, `X-Pixel-Ops-Height`,
  `X-Pixel-Ops-SHA256`, `X-Pixel-Ops-Refresh` e
  `X-Pixel-Ops-Encoding: base64`.
- Se houver token, use `Authorization: Bearer <token>`.
