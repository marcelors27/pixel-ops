# Graph Report - .  (2026-05-17)

## Corpus Check
- Corpus is ~35,074 words - fits in a single context window. You may not need a graph.

## Summary
- 839 nodes · 1399 edges · 52 communities (36 shown, 16 thin omitted)
- Extraction: 78% EXTRACTED · 22% INFERRED · 0% AMBIGUOUS · INFERRED: 304 edges (avg confidence: 0.62)
- Token cost: 0 input · 0 output

## Community Hubs (Navigation)
- [[_COMMUNITY_Pokemon Ambience Rendering|Pokemon Ambience Rendering]]
- [[_COMMUNITY_Ambient Event Core|Ambient Event Core]]
- [[_COMMUNITY_Pokemon World Loop|Pokemon World Loop]]
- [[_COMMUNITY_Calendar Event Sources|Calendar Event Sources]]
- [[_COMMUNITY_AI Decision Plugin|AI Decision Plugin]]
- [[_COMMUNITY_Core App Runtime|Core App Runtime]]
- [[_COMMUNITY_Discord Integration|Discord Integration]]
- [[_COMMUNITY_Display Outputs|Display Outputs]]
- [[_COMMUNITY_Integration JSON Config|Integration JSON Config]]
- [[_COMMUNITY_Pokemon Encounters|Pokemon Encounters]]
- [[_COMMUNITY_Weather Data Source|Weather Data Source]]
- [[_COMMUNITY_JSON Config Loader|JSON Config Loader]]
- [[_COMMUNITY_Pokemon Map Routing|Pokemon Map Routing]]
- [[_COMMUNITY_Social Signal Classification|Social Signal Classification]]
- [[_COMMUNITY_Display AI Config|Display AI Config]]
- [[_COMMUNITY_Pokemon Selection|Pokemon Selection]]
- [[_COMMUNITY_Pokemon Game Config|Pokemon Game Config]]
- [[_COMMUNITY_USB Display Hardware|USB Display Hardware]]
- [[_COMMUNITY_Work Event Mappings|Work Event Mappings]]
- [[_COMMUNITY_Graphify Detection Metadata|Graphify Detection Metadata]]
- [[_COMMUNITY_Pokemon State Machine|Pokemon State Machine]]
- [[_COMMUNITY_Social Visual Effects|Social Visual Effects]]
- [[_COMMUNITY_Pokemon Data Config|Pokemon Data Config]]
- [[_COMMUNITY_Sprite Extraction Tool|Sprite Extraction Tool]]
- [[_COMMUNITY_Map Sheet Tool|Map Sheet Tool]]
- [[_COMMUNITY_AI Throttle Config|AI Throttle Config]]
- [[_COMMUNITY_Encounter Timing Config|Encounter Timing Config]]
- [[_COMMUNITY_HUD Rendering|HUD Rendering]]
- [[_COMMUNITY_Zoom Integration Stub|Zoom Integration Stub]]
- [[_COMMUNITY_AI Selector Config|AI Selector Config]]
- [[_COMMUNITY_People Config|People Config]]
- [[_COMMUNITY_GitHub Plugin Init|GitHub Plugin Init]]
- [[_COMMUNITY_ICS Plugin Init|ICS Plugin Init]]
- [[_COMMUNITY_Plugin Package Init|Plugin Package Init]]
- [[_COMMUNITY_Events Package Init|Events Package Init]]
- [[_COMMUNITY_Runtime Package Init|Runtime Package Init]]
- [[_COMMUNITY_Discord Plugin Init|Discord Plugin Init]]
- [[_COMMUNITY_Google Calendar Init|Google Calendar Init]]
- [[_COMMUNITY_Integrations Package Init|Integrations Package Init]]
- [[_COMMUNITY_Zoom Plugin Init|Zoom Plugin Init]]
- [[_COMMUNITY_Pokemon Game Init|Pokemon Game Init]]
- [[_COMMUNITY_Plugins Package Init|Plugins Package Init]]
- [[_COMMUNITY_Slack Plugin Init|Slack Plugin Init]]
- [[_COMMUNITY_Teams Plugin Init|Teams Plugin Init]]
- [[_COMMUNITY_Weather Plugin Init|Weather Plugin Init]]

## God Nodes (most connected - your core abstractions)
1. `OverworldScene` - 64 edges
2. `WorkEvent` - 29 edges
3. `PokemonSelector` - 27 edges
4. `game` - 22 edges
5. `MapRouteManager` - 21 edges
6. `pokemon` - 19 edges
7. `GitHubEventSource` - 19 edges
8. `EncounterSystem` - 18 edges
9. `MainScene` - 17 edges
10. `PokemonAiPromptBuilder` - 17 edges

## Surprising Connections (you probably didn't know these)
- `available_plugins()` --calls--> `PokemonPlugin`  [INFERRED]
  pixel_ops/plugins/registry.py → pixel_ops/plugins/pokemon/plugin.py
- `MainScene` --uses--> `PokeApiClient`  [INFERRED]
  pixel_ops/plugins/pokemon/scenes/main_scene.py → pixel_ops/plugins/pokemon/pokemon_api.py
- `OverworldScene` --uses--> `PokeApiClient`  [INFERRED]
  pixel_ops/plugins/pokemon/scenes/overworld_scene.py → pixel_ops/plugins/pokemon/pokemon_api.py
- `PokemonSelection` --uses--> `PokeApiClient`  [INFERRED]
  pixel_ops/plugins/pokemon/game/pokemon_selector.py → pixel_ops/plugins/pokemon/pokemon_api.py
- `PokemonSelector` --uses--> `PokeApiClient`  [INFERRED]
  pixel_ops/plugins/pokemon/game/pokemon_selector.py → pixel_ops/plugins/pokemon/pokemon_api.py

## Communities (52 total, 16 thin omitted)

### Community 0 - "Pokemon Ambience Rendering"
Cohesion: 0.06
Nodes (25): day_night_palette(), DayNightPalette, apply_battle_ambience(), _draw_arena_marks(), draw_text_box(), _load_text_box_frame(), scroll_line_start(), _scroll_lines() (+17 more)

### Community 1 - "Ambient Event Core"
Cohesion: 0.07
Nodes (29): Enum, ambient_signal_to_work_event(), AmbientProvider, AmbientSignal, AmbientSignalKind, _event_shape(), EventCategory, EventPriority (+21 more)

### Community 2 - "Pokemon World Loop"
Cohesion: 0.06
Nodes (24): World, AnimationClock, SpriteAnimation, font(), palette_for_hour(), PixelRenderer, _apply_transparency(), ash_direction_frame() (+16 more)

### Community 3 - "Calendar Event Sources"
Cohesion: 0.06
Nodes (23): download_ics(), EventSource, Return new events since the last poll., CalendarEventSource, Polls an ICS calendar and emits meeting encounters., GitHubIntegrationPlugin, plugin(), GoogleCalendarIntegrationPlugin (+15 more)

### Community 4 - "AI Decision Plugin"
Cohesion: 0.07
Nodes (25): AiDecisionPlugin, AiDecisionRequest, build_ai_plugin(), _env_bool(), OpenAiChatGptPlugin, Generic Pixel OPs AI decision plugin backed by the OpenAI Responses API., AiPokemonChoice, AiThrottle (+17 more)

### Community 5 - "Core App Runtime"
Cohesion: 0.07
Nodes (31): PixelOpsApp, PixelOpsScene, PullRequestSource, Hardware-agnostic frame producer for a Pixel OPs interface plugin., WeatherSource, parse_hhmm(), status_for(), CalendarEvent (+23 more)

### Community 6 - "Discord Integration"
Cohesion: 0.06
Nodes (15): DiscordBusEventSource, DiscordGatewayAdapter, Gateway dispatch adapter.      The project intentionally avoids a runtime websoc, DiscordIntegrationPlugin, plugin(), BusEnvelope, EventBus, Tiny in-process bus for sequential ambient events.      The display loop is sing (+7 more)

### Community 7 - "Display Outputs"
Cohesion: 0.06
Nodes (13): ABC, DisplayOutput, DisplayOutput, Transport boundary for rendered frames.      The core renderer always produces P, GifOutput, Collects frames and writes an animated GIF when stopped., PreviewOutput, Writes preview PNG frames locally without requiring display hardware. (+5 more)

### Community 8 - "Integration JSON Config"
Cohesion: 0.06
Nodes (34): enabled, enabled, fetch_pull_requests, max_pull_requests, poll_seconds, repos, timeout_seconds, token_env (+26 more)

### Community 9 - "Pokemon Encounters"
Cohesion: 0.09
Nodes (13): Encounter, EncounterSpawner, PokemonPlugin, PokeApiClient, get_pokemon(), pokemon, api_base_url, cache_dir (+5 more)

### Community 10 - "Weather Data Source"
Cohesion: 0.1
Nodes (15): _effects(), OpenMeteoWeatherSource, Polls Open-Meteo current weather for a configured city., WeatherState, MoodEngine, Compatibility name for the global world mood engine., _event_weight(), _is_friday() (+7 more)

### Community 11 - "JSON Config Loader"
Cohesion: 0.12
Nodes (21): config_path(), ConfigWatcher, load_config(), load_config_prefer_json(), build_parser(), env_bool(), env_int(), env_value() (+13 more)

### Community 12 - "Pokemon Map Routing"
Cohesion: 0.13
Nodes (8): _classify_area(), _crop_box(), _direction_for_delta(), _indoor_kind(), _is_light(), _is_walkable(), MapArea, MapRouteManager

### Community 13 - "Social Signal Classification"
Cohesion: 0.11
Nodes (17): classify_discord_dispatch(), _discord_actor(), _discord_timestamp(), classify_text_kind(), classify_text_signal(), signal_to_work_event(), _actor(), classify_slack_event() (+9 more)

### Community 14 - "Display AI Config"
Cohesion: 0.08
Nodes (23): api_key_env, cache_dir, cache_enabled, enabled, model, provider, reasoning_effort, timeout_seconds (+15 more)

### Community 15 - "Pokemon Selection"
Cohesion: 0.15
Nodes (7): repo_types(), time_types(), _env_bool(), _metadata_types(), PokemonSelector, _priority_index(), rarity_for_priority()

### Community 16 - "Pokemon Game Config"
Cohesion: 0.1
Nodes (20): game, ash_sprite_file, ash_sprite_source, ash_x, ash_y, encounter_x, fps, hud_height (+12 more)

### Community 17 - "USB Display Hardware"
Cohesion: 0.19
Nodes (5): image_to_rgb565(), Command, Minimal USB bulk transport for TURZX/Turing Rev. A style displays., UsbBulkRevA, IntEnum

### Community 18 - "Work Event Mappings"
Cohesion: 0.13
Nodes (15): build_broken, deploy_completed, deploy_started, incident, meeting, merge, message_important, pr_approved (+7 more)

### Community 19 - "Graphify Detection Metadata"
Cohesion: 0.15
Nodes (12): files, code, document, image, paper, video, graphifyignore_patterns, needs_graph (+4 more)

### Community 20 - "Pokemon State Machine"
Cohesion: 0.27
Nodes (3): GameStateMachine, _next_phase(), progress()

### Community 21 - "Social Visual Effects"
Cohesion: 0.46
Nodes (7): _blend_region(), _draw_crowd(), _draw_embers(), _draw_glyphs(), _draw_lanterns(), draw_social_world_effects(), _draw_sparks()

### Community 22 - "Pokemon Data Config"
Cohesion: 0.25
Nodes (8): knowledge_path, mock_events, queue_limit, repo_biomes, events, backend, frontend, infra

### Community 23 - "Sprite Extraction Tool"
Cohesion: 0.43
Nodes (6): build_parser(), clean_frame(), close_color(), crop_strip(), main(), write_manifest()

### Community 24 - "Map Sheet Tool"
Cohesion: 0.52
Nodes (6): component_is_map(), connected_components(), is_background(), main(), slugify(), split_sheet()

### Community 25 - "AI Throttle Config"
Cohesion: 0.29
Nodes (7): throttle, cooldown_seconds, enabled, max_pending, max_requests_per_window, skip_sources, window_seconds

### Community 26 - "Encounter Timing Config"
Cohesion: 0.29
Nodes (7): appears_seconds, caught_seconds, shake_seconds, start_seconds, throw_seconds, walking_seconds, encounter

### Community 27 - "HUD Rendering"
Cohesion: 0.67
Nodes (6): _activity_label(), _draw_flag(), draw_hud(), _draw_timezone_card(), _draw_timezone_chip(), _fit_text()

### Community 29 - "AI Selector Config"
Cohesion: 0.4
Nodes (5): ambient, async, candidate_limit, enabled, ai_selector

## Knowledge Gaps
- **123 isolated node(s):** `code`, `document`, `paper`, `image`, `video` (+118 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **16 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `OverworldScene` connect `Pokemon Ambience Rendering` to `Ambient Event Core`, `Pokemon World Loop`, `AI Decision Plugin`, `Core App Runtime`, `Pokemon Encounters`, `Weather Data Source`, `Pokemon Map Routing`, `Pokemon Selection`, `Pokemon State Machine`?**
  _High betweenness centrality (0.288) - this node is a cross-community bridge._
- **Why does `WorkEvent` connect `Ambient Event Core` to `Pokemon Ambience Rendering`, `Calendar Event Sources`, `AI Decision Plugin`, `Weather Data Source`, `Pokemon Selection`?**
  _High betweenness centrality (0.131) - this node is a cross-community bridge._
- **Why does `PokemonPlugin` connect `Pokemon Encounters` to `Pokemon Ambience Rendering`, `Calendar Event Sources`, `AI Decision Plugin`, `Core App Runtime`, `JSON Config Loader`?**
  _High betweenness centrality (0.103) - this node is a cross-community bridge._
- **Are the 20 inferred relationships involving `OverworldScene` (e.g. with `PokemonPlugin` and `CalendarEvent`) actually correct?**
  _`OverworldScene` has 20 INFERRED edges - model-reasoned connections that need verification._
- **Are the 28 inferred relationships involving `WorkEvent` (e.g. with `OverworldScene` and `AiPokemonChoice`) actually correct?**
  _`WorkEvent` has 28 INFERRED edges - model-reasoned connections that need verification._
- **Are the 13 inferred relationships involving `PokemonSelector` (e.g. with `OverworldScene` and `WeatherState`) actually correct?**
  _`PokemonSelector` has 13 INFERRED edges - model-reasoned connections that need verification._
- **Are the 2 inferred relationships involving `MapRouteManager` (e.g. with `OverworldScene` and `.__init__()`) actually correct?**
  _`MapRouteManager` has 2 INFERRED edges - model-reasoned connections that need verification._