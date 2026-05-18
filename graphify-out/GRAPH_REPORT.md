# Graph Report - .  (2026-05-17)

## Corpus Check
- Corpus is ~36,177 words - fits in a single context window. You may not need a graph.

## Summary
- 885 nodes · 1512 edges · 54 communities (35 shown, 19 thin omitted)
- Extraction: 78% EXTRACTED · 22% INFERRED · 0% AMBIGUOUS · INFERRED: 334 edges (avg confidence: 0.61)
- Token cost: 0 input · 0 output

## Community Hubs (Navigation)
- [[_COMMUNITY_AI Usage Telemetry|AI Usage Telemetry]]
- [[_COMMUNITY_Pokemon Ambience Rendering|Pokemon Ambience Rendering]]
- [[_COMMUNITY_AI Decision Plugin|AI Decision Plugin]]
- [[_COMMUNITY_Core App Runtime|Core App Runtime]]
- [[_COMMUNITY_AI Usage Config|AI Usage Config]]
- [[_COMMUNITY_Pokemon World Loop|Pokemon World Loop]]
- [[_COMMUNITY_Display Outputs|Display Outputs]]
- [[_COMMUNITY_Social Signal Classification|Social Signal Classification]]
- [[_COMMUNITY_Pokemon Event Config|Pokemon Event Config]]
- [[_COMMUNITY_Pokemon Encounters|Pokemon Encounters]]
- [[_COMMUNITY_Weather Data Source|Weather Data Source]]
- [[_COMMUNITY_Sprite Animation|Sprite Animation]]
- [[_COMMUNITY_JSON Config Loader|JSON Config Loader]]
- [[_COMMUNITY_Encounter Timing Config|Encounter Timing Config]]
- [[_COMMUNITY_Pokemon Map Routing|Pokemon Map Routing]]
- [[_COMMUNITY_Display AI Config|Display AI Config]]
- [[_COMMUNITY_Pokemon Selection|Pokemon Selection]]
- [[_COMMUNITY_Integration Plugin Core|Integration Plugin Core]]
- [[_COMMUNITY_GitHub Events|GitHub Events]]
- [[_COMMUNITY_Event Bus|Event Bus]]
- [[_COMMUNITY_USB Display Hardware|USB Display Hardware]]
- [[_COMMUNITY_Calendar Event Sources|Calendar Event Sources]]
- [[_COMMUNITY_Discord Integration|Discord Integration]]
- [[_COMMUNITY_Provider Plugins|Provider Plugins]]
- [[_COMMUNITY_Pokemon State Machine|Pokemon State Machine]]
- [[_COMMUNITY_HUD Rendering|HUD Rendering]]
- [[_COMMUNITY_Social Visual Effects|Social Visual Effects]]
- [[_COMMUNITY_Meeting Ceremonies|Meeting Ceremonies]]
- [[_COMMUNITY_Slack Integration|Slack Integration]]
- [[_COMMUNITY_Google Calendar|Google Calendar]]
- [[_COMMUNITY_ICS Integration|ICS Integration]]
- [[_COMMUNITY_Weather Plugin|Weather Plugin]]
- [[_COMMUNITY_Teams Zoom Stubs|Teams Zoom Stubs]]
- [[_COMMUNITY_Graphify Metadata|Graphify Metadata]]
- [[_COMMUNITY_Pokemon Data Config|Pokemon Data Config]]
- [[_COMMUNITY_Runtime Package Init|Runtime Package Init]]
- [[_COMMUNITY_People Config|People Config]]
- [[_COMMUNITY_Pokemon Package Init|Pokemon Package Init]]
- [[_COMMUNITY_Plugins Package Init|Plugins Package Init]]
- [[_COMMUNITY_Hardware Package Init|Hardware Package Init]]
- [[_COMMUNITY_Outputs Package Init|Outputs Package Init]]
- [[_COMMUNITY_Core Package Init|Core Package Init]]
- [[_COMMUNITY_AI Package Init|AI Package Init]]
- [[_COMMUNITY_Integrations Init|Integrations Init]]
- [[_COMMUNITY_Sprite Tools|Sprite Tools]]
- [[_COMMUNITY_Map Sheet Tool|Map Sheet Tool]]
- [[_COMMUNITY_Pokemon API|Pokemon API]]

## God Nodes (most connected - your core abstractions)
1. `OverworldScene` - 65 edges
2. `WorkEvent` - 35 edges
3. `PokemonSelector` - 27 edges
4. `game` - 22 edges
5. `EventCategory` - 22 edges
6. `EventPriority` - 22 edges
7. `MapRouteManager` - 21 edges
8. `pokemon` - 19 edges
9. `GitHubEventSource` - 19 edges
10. `EncounterSystem` - 18 edges

## Surprising Connections (you probably didn't know these)
- `PokemonPlugin` --uses--> `CalendarEvent`  [INFERRED]
  plugins/pokemon/plugin.py → data_sources/calendar.py
- `PokemonPlugin` --uses--> `EventSource`  [INFERRED]
  plugins/pokemon/plugin.py → events/base.py
- `MainScene` --uses--> `CalendarEvent`  [INFERRED]
  plugins/pokemon/scenes/main_scene.py → data_sources/calendar.py
- `MainScene` --uses--> `PersonTime`  [INFERRED]
  plugins/pokemon/scenes/main_scene.py → data_sources/timezones.py
- `OverworldScene` --uses--> `AIUsageSnapshot`  [INFERRED]
  plugins/pokemon/scenes/overworld_scene.py → data_sources/ai_usage.py

## Communities (54 total, 19 thin omitted)

### Community 0 - "AI Usage Telemetry"
Cohesion: 0.05
Nodes (47): AIUsageGauge, AIUsageSnapshot, AIUsageSource, _aware(), _claude_row(), _codex_row(), _compact_number(), _find_first_string() (+39 more)

### Community 1 - "Pokemon Ambience Rendering"
Cohesion: 0.05
Nodes (32): day_night_palette(), DayNightPalette, apply_battle_ambience(), _draw_arena_marks(), _blend_region(), _draw_crowd(), _draw_embers(), _draw_glyphs() (+24 more)

### Community 2 - "AI Decision Plugin"
Cohesion: 0.07
Nodes (25): AiDecisionPlugin, AiDecisionRequest, build_ai_plugin(), _env_bool(), OpenAiChatGptPlugin, Generic Pixel OPs AI decision plugin backed by the OpenAI Responses API., AiPokemonChoice, AiThrottle (+17 more)

### Community 3 - "Core App Runtime"
Cohesion: 0.07
Nodes (32): AIUsageSource, PixelOpsApp, PixelOpsScene, PullRequestSource, Hardware-agnostic frame producer for a Pixel OPs interface plugin., WeatherSource, parse_hhmm(), status_for() (+24 more)

### Community 4 - "AI Usage Config"
Cohesion: 0.05
Nodes (43): claude_projects_path, codex_home, enabled, openai_admin_key_env, poll_seconds, providers, thresholds, timeout_seconds (+35 more)

### Community 5 - "Pokemon World Loop"
Cohesion: 0.08
Nodes (16): World, font(), _activity_label(), _ai_usage_label(), _draw_ai_usage_gauges(), _draw_flag(), draw_hud(), _draw_timezone_card() (+8 more)

### Community 6 - "Display Outputs"
Cohesion: 0.06
Nodes (13): ABC, DisplayOutput, DisplayOutput, Transport boundary for rendered frames.      The core renderer always produces P, GifOutput, Collects frames and writes an animated GIF when stopped., PreviewOutput, Writes preview PNG frames locally without requiring display hardware. (+5 more)

### Community 7 - "Social Signal Classification"
Cohesion: 0.08
Nodes (19): classify_discord_dispatch(), _discord_actor(), _discord_timestamp(), classify_text_kind(), classify_text_signal(), signal_to_work_event(), _actor(), classify_slack_event() (+11 more)

### Community 8 - "Pokemon Event Config"
Cohesion: 0.06
Nodes (36): ambient, async, candidate_limit, enabled, throttle, ai_usage, build_broken, deploy_completed (+28 more)

### Community 9 - "Pokemon Encounters"
Cohesion: 0.09
Nodes (13): Encounter, EncounterSpawner, PokemonPlugin, PokeApiClient, get_pokemon(), pokemon, api_base_url, cache_dir (+5 more)

### Community 10 - "Weather Data Source"
Cohesion: 0.1
Nodes (15): _effects(), OpenMeteoWeatherSource, Polls Open-Meteo current weather for a configured city., WeatherState, MoodEngine, Compatibility name for the global world mood engine., _event_weight(), _is_friday() (+7 more)

### Community 11 - "Sprite Animation"
Cohesion: 0.13
Nodes (16): AnimationClock, SpriteAnimation, _apply_transparency(), ash_direction_frame(), ash_frame(), AshSpriteSet, battle_ash_frame(), _load_battle_ash_frames() (+8 more)

### Community 12 - "JSON Config Loader"
Cohesion: 0.12
Nodes (21): config_path(), ConfigWatcher, load_config(), load_config_prefer_json(), build_parser(), env_bool(), env_int(), env_value() (+13 more)

### Community 13 - "Encounter Timing Config"
Cohesion: 0.07
Nodes (27): appears_seconds, caught_seconds, shake_seconds, start_seconds, throw_seconds, walking_seconds, game, ash_sprite_file (+19 more)

### Community 14 - "Pokemon Map Routing"
Cohesion: 0.13
Nodes (8): _classify_area(), _crop_box(), _direction_for_delta(), _indoor_kind(), _is_light(), _is_walkable(), MapArea, MapRouteManager

### Community 15 - "Display AI Config"
Cohesion: 0.08
Nodes (23): api_key_env, cache_dir, cache_enabled, enabled, model, provider, reasoning_effort, timeout_seconds (+15 more)

### Community 16 - "Pokemon Selection"
Cohesion: 0.15
Nodes (7): repo_types(), time_types(), _env_bool(), _metadata_types(), PokemonSelector, _priority_index(), rarity_for_priority()

### Community 17 - "Integration Plugin Core"
Cohesion: 0.12
Nodes (9): IntegrationPlugin, NullAIUsageSource, NullPullRequestSource, NullWeatherSource, build_integration_runtime(), IntegrationRuntime, _load_plugin(), _merge() (+1 more)

### Community 18 - "GitHub Events"
Cohesion: 0.19
Nodes (4): _env_bool(), GitHubEventSource, _parse_github_datetime(), Polls GitHub for open pull requests and keeps a compact HUD list.

### Community 19 - "Event Bus"
Cohesion: 0.13
Nodes (6): BusEnvelope, EventBus, Tiny in-process bus for sequential ambient events.      The display loop is sing, SlackEventSource, SlackBusEventSource, SlackBusEventSource

### Community 20 - "USB Display Hardware"
Cohesion: 0.19
Nodes (5): image_to_rgb565(), Command, Minimal USB bulk transport for TURZX/Turing Rev. A style displays., UsbBulkRevA, IntEnum

### Community 21 - "Calendar Event Sources"
Cohesion: 0.2
Nodes (5): download_ics(), CalendarEventSource, Polls an ICS calendar and emits meeting encounters., GoogleCalendarIntegrationPlugin, plugin()

### Community 22 - "Discord Integration"
Cohesion: 0.2
Nodes (5): DiscordBusEventSource, DiscordGatewayAdapter, Gateway dispatch adapter.      The project intentionally avoids a runtime websoc, DiscordIntegrationPlugin, plugin()

### Community 23 - "Provider Plugins"
Cohesion: 0.25
Nodes (5): GitHubIntegrationPlugin, plugin(), IcsIntegrationPlugin, plugin(), IntegrationContribution

### Community 24 - "Pokemon State Machine"
Cohesion: 0.27
Nodes (3): GameStateMachine, _next_phase(), progress()

### Community 25 - "HUD Rendering"
Cohesion: 0.32
Nodes (3): IntegrationContext, plugin(), WeatherIntegrationPlugin

### Community 26 - "Social Visual Effects"
Cohesion: 0.43
Nodes (6): build_parser(), clean_frame(), close_color(), crop_strip(), main(), write_manifest()

### Community 27 - "Meeting Ceremonies"
Cohesion: 0.52
Nodes (6): component_is_map(), connected_components(), is_background(), main(), slugify(), split_sheet()

## Knowledge Gaps
- **121 isolated node(s):** `social_bus_limit`, `enabled`, `app_token_env`, `bot_token_env`, `bot_user_id` (+116 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **19 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `OverworldScene` connect `Pokemon Ambience Rendering` to `AI Usage Telemetry`, `AI Decision Plugin`, `Core App Runtime`, `Pokemon World Loop`, `Pokemon Encounters`, `Weather Data Source`, `Sprite Animation`, `Pokemon Map Routing`, `Pokemon Selection`, `Pokemon State Machine`?**
  _High betweenness centrality (0.287) - this node is a cross-community bridge._
- **Why does `WorkEvent` connect `AI Usage Telemetry` to `Pokemon Ambience Rendering`, `AI Decision Plugin`, `Weather Data Source`, `Pokemon Selection`, `GitHub Events`, `Calendar Event Sources`?**
  _High betweenness centrality (0.142) - this node is a cross-community bridge._
- **Why does `EventSource` connect `AI Usage Telemetry` to `Core App Runtime`, `Pokemon Encounters`, `Integration Plugin Core`, `Provider Plugins`, `HUD Rendering`?**
  _High betweenness centrality (0.114) - this node is a cross-community bridge._
- **Are the 21 inferred relationships involving `OverworldScene` (e.g. with `PokemonPlugin` and `AIUsageSnapshot`) actually correct?**
  _`OverworldScene` has 21 INFERRED edges - model-reasoned connections that need verification._
- **Are the 34 inferred relationships involving `WorkEvent` (e.g. with `OverworldScene` and `AiPokemonChoice`) actually correct?**
  _`WorkEvent` has 34 INFERRED edges - model-reasoned connections that need verification._
- **Are the 13 inferred relationships involving `PokemonSelector` (e.g. with `OverworldScene` and `WeatherState`) actually correct?**
  _`PokemonSelector` has 13 INFERRED edges - model-reasoned connections that need verification._
- **Are the 19 inferred relationships involving `EventCategory` (e.g. with `PokemonSelection` and `PokemonSelector`) actually correct?**
  _`EventCategory` has 19 INFERRED edges - model-reasoned connections that need verification._