# Pokemon Plugin

App isolado para renderizar um dashboard estilo RPG portatil classico em um
TURZX/Turing/UsbMonitor 3.5".

A comunicacao com o display usa a lib interna minima em
`pixel_ops/hardware/`.

## Preview local

```bash
python pixel_ops/main.py --plugin pokemon --output preview
```

Saida:

```text
pixel_ops/output/preview.png
```

## GIF local

```bash
python pixel_ops/main.py --plugin pokemon --output gif --seconds 8
```

## Display

```bash
python pixel_ops/main.py --plugin pokemon --output turzx --seconds 30 --fps 12
```

Para rodar sem parar:

```bash
python pixel_ops/main.py --plugin pokemon --output turzx --forever --fps 10 --offline
```

Os flags antigos continuam funcionando como aliases:

- `--preview` equivale a `--output preview`
- `--gif` equivale a `--output gif`
- `--display` equivale a `--output turzx`

## Outputs

O core gera frames `PIL.Image`. Transporte para hardware ou arquivo fica
isolado em `outputs/` pela interface `DisplayOutput.start/send/stop`.

```text
core/render -> PIL.Image -> DisplayOutput.send(frame)
```

Outputs atuais:

- `preview`: salva PNG local sem hardware.
- `gif`: salva uma animacao GIF curta.
- `turzx`: envia frames para TURZX/Turing via USB bulk.

## Config

- Pessoas e fusos: `config/people.yaml`
- Display/FPS/paleta: `config/display.yaml`
- Loop de jogo/cena: `pixel_ops/plugins/pokemon/game.yaml`
- PokeAPI/cache/sprites: `pixel_ops/plugins/pokemon/pokemon.yaml`

## Cena overworld

O app roda a cena `scenes/overworld_scene.py`, que separa a experiencia em:

- `game/state_machine.py`: fluxo `WALKING -> ENCOUNTER_START -> POKEMON_APPEARS -> ASH_THROWS -> BALL_SHAKE -> CAUGHT -> RESUME_WALKING`
- `game/encounter.py`: spawn aleatorio dos 151 Pokemon classicos
- `game/world.py`: scroll/parallax simples e alternancia entre cidade, rota, grama, vila e Pokemon Center
- `game/day_night.py`: paletas por horario local principal
- `render/hud.py`: HUD compacto de timezones e proxima reuniao
- `render/text_box.py`: caixa de texto estilo jogo
- `render/tiles.py`: tiles/props gerados como fallback visual

O primeiro alvo e validar localmente com PNG/GIF:

```bash
python pixel_ops/main.py --plugin pokemon --gif --seconds 12 --fps 10 --offline
```

## Pokemon API e cache

Baixar metadata e sprites oficiais da PokeAPI para os 151 classicos:

```bash
python pixel_ops/main.py --plugin pokemon --warm-cache
```

Cache local:

```text
pixel_ops/plugins/pokemon/assets/cache/api/
pixel_ops/plugins/pokemon/assets/cache/pokemon/front/
pixel_ops/plugins/pokemon/assets/cache/pokemon/animated/
```

Rodar sem rede, usando apenas o cache:

```bash
python pixel_ops/main.py --plugin pokemon --display --offline
```

Sprites usados:

- Front: `https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/{id}.png`
- Animated Gen V: `https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/versions/generation-v/black-white/animated/{id}.gif`

## Sprites do Ash

O renderer agora suporta spritesheets locais para o Ash/trainer. Coloque os
PNGs em:

```text
pixel_ops/plugins/pokemon/assets/sprites/ash/
```

Arquivos simples suportados sem configuracao:

```text
walk_right.png
idle.png
catch.png
```

Para rips com frames 16x20, spacing, margin ou multiplas linhas, crie
`assets/sprites/ash/manifest.yaml`. Veja o exemplo em
`assets/sprites/ash/README.md`.

Fontes para baixar manualmente:

- The Spriters Resource > Pokemon FireRed / LeafGreen overworld sprites
- The Spriters Resource > Pokemon Emerald overworld sprites

O app nao baixa nem redistribui esses rips automaticamente. Se nenhum PNG do
Ash existir, ele usa um fallback gerado para manter preview/display rodando.
Para exigir uma spritesheet real/local do Ash, ajuste `require_ash_sprite: true`
em `config/game.yaml`.

Fonte configurada para o Ash/Red overworld:

```text
https://www.spriters-resource.com/game_boy_advance/pokemonfireredleafgreen/asset/52432/
```

Baixe o PNG dessa pagina e salve como:

```text
pixel_ops/plugins/pokemon/assets/sprites/ash/ash_overworld.png
```

Depois copie `manifest.example.yaml` para `manifest.yaml` e ajuste os indices
dos frames conforme a linha/coluna da sheet baixada.

Tambem ha um extrator para separar os primeiros sprites do Ash/Red:

```bash
python pixel_ops/plugins/pokemon/tools/extract_ash_from_sheet.py caminho/para/player_sprites.png
```

## Calendario

Hoje ha duas fontes:

- mock automatico, para desenvolvimento
- arquivo `.ics` local via `--ics caminho/calendario.ics`

Google Calendar API pode ser adicionada depois em `data_sources/calendar.py`
sem mexer na cena ou no backend do display.

## GitHub

Para listar PRs abertos no HUD e gerar encontros de revisao, configure:

```env
PIXEL_OPS_GITHUB_ENABLED=true
PIXEL_OPS_GITHUB_TOKEN=github_pat_...
PIXEL_OPS_GITHUB_REPOS=The-Fitness-Doctor/tfd-monorepo
PIXEL_OPS_GITHUB_POLL_SECONDS=60
PIXEL_OPS_GITHUB_MAX_PRS=4
```

O token precisa apenas de leitura dos repositorios configurados.
