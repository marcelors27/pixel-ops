# Pixel OPs

Runtime para dashboards pixel-art operacionais. O core cuida de outputs, eventos e hardware; as interfaces visuais ficam em plugins. O plugin padrao atual e `pokemon`.

## Rodar

```bash
python pixel_ops/main.py --plugin pokemon --output preview
python pixel_ops/main.py --plugin pokemon --output gif --seconds 8
python pixel_ops/main.py --plugin pokemon --output turzx --forever --fps 10 --offline
```

Saidas locais:

```text
pixel_ops/output/preview.png
pixel_ops/output/preview.gif
```

## Configuracao

- Pessoas e fusos: `pixel_ops/config/people.yaml`
- Display/FPS: `pixel_ops/config/display.yaml`
- Plugin Pokemon: `pixel_ops/plugins/pokemon/game.yaml`
- PokeAPI/cache/sprites: `pixel_ops/plugins/pokemon/pokemon.yaml`

## Plugins

Plugins ficam em `pixel_ops/plugins/<nome>/` e expõem uma classe com:

- `name`
- `add_arguments(parser)`
- `load_config(plugin_dir, load_yaml)`
- `maybe_handle_command(args, root_dir, config)`
- `fps(config, display_fps)`
- `event_config(config)`
- `build_app(...)`

Para registrar uma nova interface, adicione o plugin em `pixel_ops/plugins/registry.py`.

## Cache Pokemon

Baixar metadata e sprites dos 151 Pokemon classicos:

```bash
python pixel_ops/main.py --plugin pokemon --warm-cache
```

Rodar sem rede:

```bash
python pixel_ops/main.py --plugin pokemon --output preview --offline
```

## Eventos

Calendario via `.ics`:

```bash
python pixel_ops/main.py --ics caminho/calendario.ics
```

GitHub PRs no HUD:

```env
PIXEL_OPS_GITHUB_ENABLED=true
PIXEL_OPS_GITHUB_TOKEN=github_pat_...
PIXEL_OPS_GITHUB_REPOS=owner/repo
PIXEL_OPS_GITHUB_POLL_SECONDS=60
PIXEL_OPS_GITHUB_MAX_PRS=4
```

## Hardware

O envio para display fica isolado em `pixel_ops/hardware/`. Essa lib contem apenas o transporte USB bulk minimo usado pelo app, sem depender do projeto upstream original.
