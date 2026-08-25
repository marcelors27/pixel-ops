# Pixel OPs — Heltec Vision Master E213

Firmware Wi-Fi para usar a tela e-ink de 250×122 como um output híbrido do
Pixel OPs. Com o PC disponível, ele recebe o frame completo. Sem o PC, renderiza
localmente relógio, bateria, conectividade, estado operacional e clima em cache.

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
- `POST /heartbeat`: renova a lease do PC, sincroniza configuração autônoma e
  informa a porta de `/healthz` usada pelo probe reverso.
- `POST /frame`: frame monocromático de 3.904 bytes, MSB primeiro e alinhado
  por linha.
- Cabeçalhos: `X-Pixel-Ops-Width`, `X-Pixel-Ops-Height`,
  `X-Pixel-Ops-SHA256`, `X-Pixel-Ops-Refresh`,
  `X-Pixel-Ops-Dirty-X`, `X-Pixel-Ops-Dirty-Y`,
  `X-Pixel-Ops-Dirty-Width`, `X-Pixel-Ops-Dirty-Height` e
  `X-Pixel-Ops-Encoding: base64`. `X-Pixel-Ops-Battery-Powered: 1` seleciona
  a política econômica sem watchdog contínuo ou probes ativos do PC;
  `X-Pixel-Ops-Battery-Lease-Seconds` define por quanto tempo o último frame
  confirma que o PC continua disponível. `X-Pixel-Ops-Pull-Port` e
  `X-Pixel-Ops-Deep-Sleep-Seconds` configuram o ciclo autônomo de busca.
- No modo bateria, `GET http://<pc>:<pull_port>/eink/frame` devolve o bitmap
  binário atual. O firmware envia `If-None-Match`; `304` evita qualquer refresh.
- Se houver token, use `Authorization: Bearer <token>`.

## Modos autônomos

- `pc`: heartbeat ou probe ativo confirma o runtime do PC.
- `standalone_online`: PC indisponível e internet validada por DNS mais HTTP.
- `standalone_local`: sem PC e sem internet; usa relógio local e cache.

O watchdog exige falhas consecutivas antes do takeover e sucessos consecutivos
na recuperação. A HUD de status mostra o modo atual quando estiver adicionada ao layout. Configuração de latitude,
longitude e offset UTC é enviada pelos campos `standalone_*` do output e-ink e
persistida apenas quando muda. O clima é consultado diretamente na Open-Meteo a
cada 30 minutos e o último resultado continua disponível sem internet.

## Energia e diagnóstico

- A bateria é amostrada a cada minuto sem forçar refresh do painel.
- Frames parciais calculam o menor retângulo alterado no PC e usam `setWindow()`
  no controlador. O primeiro frame e a limpeza periódica continuam atualizando a
  tela inteira para controlar ghosting. Emissores antigos sem coordenadas caem
  com segurança para atualização de tela inteira.
- O output usa fundo branco por padrão e preserva apenas as regiões configuradas
  do layout. A limpeza completa ocorre a cada 100 frames alterados no modo PC e
  a cada 120 ciclos autônomos; atualizações intermediárias continuam parciais.
- Bateria (`eink_battery`), conexão wireless com o PC (`eink_wireless`) e modo
  atual (`eink_status`) são HUDs normais do layout. O Config Studio controla
  posição e tamanho; o runtime sobrepõe a telemetria real no frame monochrome e
  sincroniza as três caixas no heartbeat. O ESP32 persiste esse layout para usar
  os mesmos HUDs quando estiver autônomo. Nenhum indicador operacional é mais
  desenhado em posição fixa sobre frames recebidos do PC.
- Uma janela de oito amostras classifica `charging`, `discharging`, `stable`,
  `low` e `critical`. Durante os primeiros minutos o estado é `unknown`.
- A curva percentual é calibrada para a tensão observada na placa: 4,12 V ou
  mais representa 100%. Os intervalos são não lineares e arredondados; a tensão
  ainda pode variar temporariamente com a carga do ESP32 e do painel.
- O modo autônomo atualiza o painel a cada 5 minutos, passando para 15 minutos
  em bateria baixa e 30 minutos em estado crítico.
- Wi-Fi usa modem sleep. Probes do PC e da internet ficam menos frequentes
  depois que a indisponibilidade foi confirmada.
- Com `device.eink.battery_powered: true`, o primeiro frame grava o endereço do
  runtime, a porta e o intervalo no ESP32. Depois disso ele acorda a cada
  `deep_sleep_seconds` (300 por padrão), liga o Wi-Fi, busca o frame na porta
  `pull_port` (8765 por padrão) e volta ao deep sleep. Se nada mudou, recebe
  `304` e não atualiza o painel. Se a rede ou o PC estiver indisponível, mantém
  a imagem atual e dorme novamente.
- Pressione **BOOT** depois da inicialização para alternar entre resumo e
  diagnóstico. A página de diagnóstico mostra IP, RSSI, uptime, motivo do reset,
  tensão e tendência da bateria. BOOT durante a inicialização continua apagando
  as credenciais Wi-Fi.

O endpoint `/status` expõe esses mesmos diagnósticos para inspeção sem atualizar
o e-ink.
