import {
  Activity,
  Bot,
  CalendarDays,
  Check,
  CloudSun,
  Code2,
  Cpu,
  Github,
  GripVertical,
  Monitor,
  MoveDiagonal2,
  RefreshCw,
  Save,
  Settings2,
  Users,
} from "lucide-react";
import { useEffect, useId, useMemo, useState } from "react";
import type { ComponentType, DragEvent, MouseEvent, ReactNode } from "react";
import mascotAlertImg from "./assets/pixelops-mascot-angry.png";
import mascotImg from "./assets/pixelops-mascot.png";
import mascotSleepyImg from "./assets/pixelops-mascot-sleepy.png";
import { PixelMascot } from "./components/PixelMascot";
import { cloneConfig, loadConfig, loadConfigManifest, saveConfig } from "./lib/configApi";
import type { ConfigManifest, DetectedPlugin, DiscordPersonConfig, IntegrationToggle, LayoutBox, LayoutKey, PersonConfig, RuntimeConfig } from "./types";

type SaveState = "idle" | "saving" | "saved" | "error";

const integrationIcons: Record<string, IconComponent> = {
  github: Github,
  google_calendar: CalendarDays,
  ics: CalendarDays,
  weather: CloudSun,
  ai_usage: Activity,
  slack: Bot,
  discord: Bot,
};

const visualPluginIcons: Record<string, IconComponent> = {
  pokemon: Code2,
};

const layoutItems: Array<{ key: LayoutKey; label: string; tone: string }> = [
  { key: "timezones", label: "Timezones", tone: "#7fb2e6" },
  { key: "gauges", label: "Gauges", tone: "#7ee0bd" },
  { key: "weather", label: "Weather", tone: "#e8c766" },
  { key: "activity", label: "Activity", tone: "#ef846d" },
  { key: "route_signal", label: "Route", tone: "#f0a35d" },
  { key: "game", label: "Game", tone: "#8fbf7a" },
  { key: "text_box", label: "Text box", tone: "#d8d0ff" },
];

const resizeDirections = ["n", "s", "e", "w", "nw", "ne", "sw", "se"] as const;
type ResizeDirection = (typeof resizeDirections)[number];

const equipmentOptions = [
  { target: "window", label: "Window", width: 320, height: 480, output: "window" },
  { target: "turzx_35", label: "TURZX 3.5", width: 320, height: 480, output: "turzx" },
  { target: "turzx_94", label: "TURZX 9.4", width: 480, height: 320, output: "turzx" },
  { target: "preview", label: "Preview PNG", width: 320, height: 480, output: "preview" },
  { target: "gif", label: "GIF", width: 320, height: 480, output: "gif" },
] as const;

const discordSpriteVariants = Array.from({ length: 55 }, (_, index) => index);
const fallbackTimezones = [
  "America/Sao_Paulo",
  "America/Mexico_City",
  "America/Phoenix",
  "America/Los_Angeles",
  "America/Denver",
  "America/Chicago",
  "America/New_York",
  "Asia/Kolkata",
  "Europe/Lisbon",
  "UTC",
];

export function App() {
  const [manifest, setManifest] = useState<ConfigManifest | null>(null);
  const [selectedPluginKeys, setSelectedPluginKeys] = useState<string[]>([]);
  const [config, setConfig] = useState<RuntimeConfig | null>(null);
  const [baseline, setBaseline] = useState<RuntimeConfig | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [saveState, setSaveState] = useState<SaveState>("idle");
  const [selectedLayout, setSelectedLayout] = useState<LayoutKey>("game");
  const [draggingPersonIndex, setDraggingPersonIndex] = useState<number | null>(null);
  const timezoneOptions = useMemo(() => buildTimezoneOptions(), []);

  useEffect(() => {
    void refreshManifest();
  }, []);

  useEffect(() => {
    if (!manifest) return;
    void refreshConfig(selectedPluginKeys);
  }, [manifest, selectedPluginKeys]);

  const dirty = useMemo(() => JSON.stringify(config) !== JSON.stringify(baseline), [baseline, config]);

  async function refreshManifest() {
    setError(null);
    const detected = await loadConfigManifest();
    setManifest(detected);
    const stored = readSelectedPlugins();
    const available = new Set(detected.visualPlugins.map((plugin) => plugin.key));
    const selected = stored.filter((plugin) => available.has(plugin));
    setSelectedPluginKeys(selected.length ? selected : detected.visualPlugins.slice(0, 1).map((plugin) => plugin.key));
  }

  async function refreshConfig(plugins = selectedPluginKeys) {
    setError(null);
    const loaded = await loadConfig(plugins);
    const normalized = ensureConfigDefaults(loaded);
    setConfig(normalized);
    setBaseline(cloneConfig(normalized));
    setSaveState("idle");
  }

  async function persistConfig() {
    if (!config) return;
    setSaveState("saving");
    setError(null);
    try {
      await saveConfig(config);
      setBaseline(cloneConfig(config));
      setSaveState("saved");
      window.setTimeout(() => setSaveState("idle"), 1600);
    } catch (caught) {
      setSaveState("error");
      setError(caught instanceof Error ? caught.message : String(caught));
    }
  }

  function mutate(mutator: (draft: RuntimeConfig) => void) {
    setConfig((current) => {
      if (!current) return current;
      const draft = cloneConfig(current);
      mutator(draft);
      return draft;
    });
  }

  function toggleVisualPlugin(pluginKey: string) {
    setSelectedPluginKeys((current) => {
      const next = current.includes(pluginKey) ? current.filter((key) => key !== pluginKey) : [...current, pluginKey];
      window.localStorage.setItem("pixel-ops.config-studio.plugins", JSON.stringify(next));
      return next;
    });
  }

  function movePerson(fromIndex: number, toIndex: number) {
    if (fromIndex === toIndex) return;
    mutate((draft) => {
      const [person] = draft.people.people.splice(fromIndex, 1);
      draft.people.people.splice(toIndex, 0, person);
    });
  }

  if (!config || !manifest) {
    return (
      <main className="loading-shell">
        <RefreshCw className="spin" size={24} />
        <span>Loading runtime config</span>
      </main>
    );
  }

  const display = config.display.display;
  const game = config.game?.game;
  const pokemon = config.pokemon?.pokemon;
  const aiSelector = game?.events.ai_selector;
  const hasPokemonPlugin = selectedPluginKeys.includes("pokemon") && Boolean(game && pokemon && config.pokemon_companions);
  const discordPeopleConfig = config.discord_people?.discord_people ?? { max_recent: 50, people: {} };
  const discordPeople = discordPersonEntries(discordPeopleConfig.people);
  const enabledCount = manifest.integrations.filter(({ key }) => Boolean(integrationConfig(config, key).enabled)).length;

  return (
    <div className="app-shell">
      <header className="topbar">
        <div className="brand">
          <div>
            <strong>Pixel OPs</strong>
            <span>Config Studio</span>
          </div>
        </div>
        <nav>
          <a href="#layout">Layout</a>
          <a href="#display">Display</a>
          <a href="#plugins">Plugins</a>
          <a href="#integrations">Integrations</a>
          <a href="#people">People</a>
          {hasPokemonPlugin ? <a href="#pokemon">Pokemon</a> : null}
        </nav>
      </header>

      <main>
        <section className="hero">
          <div className="hero-copy">
            <span className="hero-status">orchestrator daemon · online</span>
            <h1>
              Configure your <span>GACO</span>
              <br />
              in just a few pixels.
            </h1>
            <p>
              A local pixel-art console to assemble your Gamified Ambient Companion Orchestrator -
              pick where it shows up, which brain drives it and what it watches while you work.
            </p>
            <div className="hero-actions">
              <a className="hero-button primary" href="#display">
                Start setup
              </a>
              <a className="hero-button secondary" href="#integrations">
                View summary
              </a>
            </div>
          </div>
          <div className="hero-mascot">
            <PixelMascot src={mascotImg} sleepySrc={mascotSleepyImg} alertSrc={mascotAlertImg} />
          </div>
          <div className="hero-chip xp">
            <strong>XP</strong>
            <span>+24</span>
          </div>
          <div className="hero-chip hp">
            <strong>HP</strong>
            <span>▰▰▰▰▰▰▱▱</span>
          </div>
        </section>

        <section className="status-strip" aria-label="Runtime summary">
          <Metric icon={Monitor} label="Canvas" value={`${display.width}x${display.height}`} />
          <Metric icon={Cpu} label="FPS" value={game ? `${display.fps} display / ${game.fps} game` : `${display.fps} display`} />
          <Metric icon={Activity} label="Integrations" value={`${enabledCount} enabled`} />
          <Metric icon={Bot} label="AI model" value={display.ai.enabled ? display.ai.model : "off"} />
        </section>

        {error ? <div className="error-banner">{error}</div> : null}

        <section id="plugins" className="wide-panel">
          <div className="section-heading">
            <Code2 size={20} />
            <div>
              <h2>Visual Plugins</h2>
              <p>Detected interface plugins determine which plugin-owned JSON configs are loaded.</p>
            </div>
          </div>
          <div className="integration-grid">
            {manifest.visualPlugins.map((plugin) => (
              <PluginCard
                key={plugin.key}
                plugin={plugin}
                selected={selectedPluginKeys.includes(plugin.key)}
                onToggle={() => toggleVisualPlugin(plugin.key)}
              />
            ))}
          </div>
        </section>

        <LayoutPreview
          config={config}
          selected={selectedLayout}
          onSelect={setSelectedLayout}
          onChange={(key, box) => mutate((draft) => void (draft.display.display.layout[key] = box))}
          onEquipment={(target) => mutate((draft) => applyEquipment(draft, target))}
        />

        <section id="display" className="panel-grid">
          <Panel title="Display" icon={Monitor} subtitle="Frame size, backend and output paths">
            <Field label="Equipment">
              <Select
                value={display.device.target}
                options={equipmentOptions.map((option) => option.target)}
                onChange={(value) => mutate((draft) => applyEquipment(draft, value))}
              />
            </Field>
            <Field label="Output">
              <Select
                value={display.device.output}
                options={["window", "preview", "gif", "turzx"]}
                onChange={(value) => mutate((draft) => void (draft.display.display.device.output = value))}
              />
            </Field>
            <Field label="Width">
              <NumberInput value={display.width} onChange={(value) => mutate((draft) => void (draft.display.display.width = value))} />
            </Field>
            <Field label="Height">
              <NumberInput value={display.height} onChange={(value) => mutate((draft) => void (draft.display.display.height = value))} />
            </Field>
            <Field label="Display FPS">
              <NumberInput value={display.fps} onChange={(value) => mutate((draft) => void (draft.display.display.fps = value))} />
            </Field>
            <Field label="Window scale">
              <NumberInput
                value={display.device.window_scale}
                onChange={(value) => mutate((draft) => void (draft.display.display.device.window_scale = value))}
              />
            </Field>
            <Field label="Seconds">
              <NumberInput value={display.device.seconds} onChange={(value) => mutate((draft) => void (draft.display.display.device.seconds = value))} />
            </Field>
            <Field label="Forever">
              <Switch checked={display.device.forever} onChange={(value) => mutate((draft) => void (draft.display.display.device.forever = value))} />
            </Field>
            <Field label="Preview sequence">
              <Switch
                checked={display.device.preview_sequence}
                onChange={(value) => mutate((draft) => void (draft.display.display.device.preview_sequence = value))}
              />
            </Field>
            <Field label="Full frame">
              <Switch
                checked={display.device.full_frame}
                onChange={(value) => mutate((draft) => void (draft.display.display.device.full_frame = value))}
              />
            </Field>
            <Field label="Backend">
              <TextInput value={display.backend} onChange={(value) => mutate((draft) => void (draft.display.display.backend = value))} />
            </Field>
            <Field label="Primary timezone">
              <TimezoneSelect
                value={display.timezone_primary}
                options={timezoneOptions}
                onChange={(value) => mutate((draft) => void (draft.display.display.timezone_primary = value))}
              />
            </Field>
            <Field label="Scanlines">
              <Switch checked={display.scanlines} onChange={(value) => mutate((draft) => void (draft.display.display.scanlines = value))} />
            </Field>
          </Panel>

          <Panel title="AI Decisions" icon={Bot} subtitle="Provider-agnostic AI config used by Pokemon selection">
            <Field label="Enabled">
              <Switch checked={display.ai.enabled} onChange={(value) => mutate((draft) => void (draft.display.display.ai.enabled = value))} />
            </Field>
            <Field label="Provider">
              <TextInput value={display.ai.provider} onChange={(value) => mutate((draft) => void (draft.display.display.ai.provider = value))} />
            </Field>
            <Field label="Model">
              <TextInput value={display.ai.model} onChange={(value) => mutate((draft) => void (draft.display.display.ai.model = value))} />
            </Field>
            <Field label="Reasoning effort">
              <Select
                value={display.ai.reasoning_effort}
                options={["low", "medium", "high"]}
                onChange={(value) => mutate((draft) => void (draft.display.display.ai.reasoning_effort = value))}
              />
            </Field>
            <Field label="Timeout seconds">
              <NumberInput
                value={display.ai.timeout_seconds}
                onChange={(value) => mutate((draft) => void (draft.display.display.ai.timeout_seconds = value))}
              />
            </Field>
            <Field label="Cache enabled">
              <Switch checked={display.ai.cache_enabled} onChange={(value) => mutate((draft) => void (draft.display.display.ai.cache_enabled = value))} />
            </Field>
          </Panel>
        </section>

        <section id="integrations" className="wide-panel">
          <div className="section-heading">
            <Settings2 size={20} />
            <div>
              <h2>Integration Runtime</h2>
              <p>Provider settings normalize into ambient events. Secrets stay as environment variable names.</p>
            </div>
          </div>
          <div className="integration-grid">
            {manifest.integrations.map(({ key, label }) => {
              const item = integrationConfig(config, key);
              const Icon = integrationIcons[key] ?? Bot;
              return (
                <button
                  className={`integration-card ${item.enabled ? "is-on" : ""}`}
                  key={key}
                  type="button"
                  onClick={() =>
                    mutate((draft) => {
                      const current = integrationConfig(draft, key);
                      draft.integrations.integrations[key] = { ...current, enabled: !current.enabled };
                    })
                  }
                >
                  <Icon size={18} />
                  <span>{label}</span>
                  <strong>{item.enabled ? "ON" : "OFF"}</strong>
                </button>
              );
            })}
          </div>

          <div className="settings-grid">
            <Panel title="GitHub" icon={Github} subtitle="Pull requests in the compact HUD">
              <Field label="Repos">
                <TextArea
                  value={config.integrations.integrations.github.repos.join("\n")}
                  onChange={(value) => mutate((draft) => void (draft.integrations.integrations.github.repos = lines(value)))}
                />
              </Field>
              <Field label="Poll seconds">
                <NumberInput
                  value={config.integrations.integrations.github.poll_seconds}
                  onChange={(value) => mutate((draft) => void (draft.integrations.integrations.github.poll_seconds = value))}
                />
              </Field>
              <Field label="Max pull requests">
                <NumberInput
                  value={config.integrations.integrations.github.max_pull_requests}
                  onChange={(value) => mutate((draft) => void (draft.integrations.integrations.github.max_pull_requests = value))}
                />
              </Field>
              <Field label="Deploy signals">
                <Switch
                  checked={config.integrations.integrations.github.fetch_deployments}
                  onChange={(value) => mutate((draft) => void (draft.integrations.integrations.github.fetch_deployments = value))}
                />
              </Field>
              <Field label="Deploy workflows">
                <TextArea
                  value={config.integrations.integrations.github.deployment_workflows.join("\n")}
                  onChange={(value) => mutate((draft) => void (draft.integrations.integrations.github.deployment_workflows = lines(value)))}
                />
              </Field>
            </Panel>

            <Panel title="Weather" icon={CloudSun} subtitle="Weather-like mood source">
              <Field label="Provider">
                <Select
                  value={config.integrations.integrations.weather.provider}
                  options={["open_meteo", "wttr_in", "openweathermap"]}
                  onChange={(value) => mutate((draft) => void (draft.integrations.integrations.weather.provider = value))}
                />
              </Field>
              <Field label="City">
                <TextInput
                  value={config.integrations.integrations.weather.city}
                  onChange={(value) => mutate((draft) => void (draft.integrations.integrations.weather.city = value))}
                />
              </Field>
              <Field label="Country code">
                <TextInput
                  value={config.integrations.integrations.weather.country_code}
                  onChange={(value) => mutate((draft) => void (draft.integrations.integrations.weather.country_code = value.toUpperCase()))}
                />
              </Field>
              <Field label="Poll seconds">
                <NumberInput
                  value={config.integrations.integrations.weather.poll_seconds}
                  onChange={(value) => mutate((draft) => void (draft.integrations.integrations.weather.poll_seconds = value))}
                />
              </Field>
              <Field label="Timeout seconds">
                <NumberInput
                  value={config.integrations.integrations.weather.timeout_seconds}
                  onChange={(value) => mutate((draft) => void (draft.integrations.integrations.weather.timeout_seconds = value))}
                />
              </Field>
              <Field label="API key env">
                <TextInput
                  value={config.integrations.integrations.weather.api_key_env}
                  onChange={(value) => mutate((draft) => void (draft.integrations.integrations.weather.api_key_env = value))}
                />
              </Field>
            </Panel>

            <Panel title="Calendars" icon={CalendarDays} subtitle="Meeting encounters from Google Calendar or ICS">
              <Field label="Google ICS URLs">
                <TextArea
                  value={config.integrations.integrations.google_calendar.ics_urls.join("\n")}
                  onChange={(value) => mutate((draft) => void (draft.integrations.integrations.google_calendar.ics_urls = lines(value)))}
                />
              </Field>
              <Field label="Local ICS paths">
                <TextArea
                  value={config.integrations.integrations.ics.paths.join("\n")}
                  onChange={(value) => mutate((draft) => void (draft.integrations.integrations.ics.paths = lines(value)))}
                />
              </Field>
            </Panel>

            <Panel title="Discord" icon={Bot} subtitle="Local Gateway voice companions and channel access events">
              <Field label="Bot token env">
                <TextInput
                  value={config.integrations.integrations.discord.bot_token_env}
                  onChange={(value) => mutate((draft) => void (draft.integrations.integrations.discord.bot_token_env = value))}
                />
              </Field>
              <Field label="Server ID">
                <TextInput
                  value={config.integrations.integrations.discord.guild_id}
                  onChange={(value) => mutate((draft) => void (draft.integrations.integrations.discord.guild_id = digits(value)))}
                />
              </Field>
              <Field label="My user ID">
                <TextInput
                  value={config.integrations.integrations.discord.focus_user_id}
                  onChange={(value) => mutate((draft) => void (draft.integrations.integrations.discord.focus_user_id = digits(value)))}
                />
              </Field>
              <Field label="Companions">
                <NumberInput
                  value={config.integrations.integrations.discord.max_companions}
                  onChange={(value) => mutate((draft) => void (draft.integrations.integrations.discord.max_companions = clampNumber(value, 0, 30)))}
                />
              </Field>
              <Field label="Reconnect seconds">
                <NumberInput
                  value={config.integrations.integrations.discord.gateway_reconnect_seconds}
                  onChange={(value) =>
                    mutate((draft) => void (draft.integrations.integrations.discord.gateway_reconnect_seconds = clampNumber(value, 1, 120)))
                  }
                />
              </Field>
              <Field label="Remember nicks">
                <NumberInput
                  value={discordPeopleConfig.max_recent}
                  onChange={(value) =>
                    mutate((draft) => {
                      draft.discord_people = draft.discord_people ?? { discord_people: { max_recent: 50, people: {} } };
                      draft.discord_people.discord_people.max_recent = clampNumber(value, 1, 200);
                    })
                  }
                />
              </Field>
              <div className="field field-wide">
                <span>Recent Discord people</span>
                <div className="companion-list">
                  {discordPeople.length ? (
                    discordPeople.map(([userId, person]) => (
                      <DiscordPersonRow key={userId} userId={userId} person={person} />
                    ))
                  ) : (
                    <span className="empty-note">No Discord voice people seen yet.</span>
                  )}
                </div>
              </div>
            </Panel>

            <Panel title="AI Usage" icon={Activity} subtitle="Ambient provider gauges">
              <Field label="Providers">
                <TextInput
                  value={config.integrations.integrations.ai_usage.providers.join(", ")}
                  onChange={(value) => mutate((draft) => void (draft.integrations.integrations.ai_usage.providers = csv(value)))}
                />
              </Field>
              <Field label="Monthly budget USD">
                <NumberInput
                  value={config.integrations.integrations.ai_usage.openai_api_monthly_budget_usd}
                  onChange={(value) => mutate((draft) => void (draft.integrations.integrations.ai_usage.openai_api_monthly_budget_usd = value))}
                />
              </Field>
              <Field label="Thresholds">
                <TextInput
                  value={config.integrations.integrations.ai_usage.thresholds.join(", ")}
                  onChange={(value) => mutate((draft) => void (draft.integrations.integrations.ai_usage.thresholds = csv(value).map(Number).filter(Number.isFinite)))}
                />
              </Field>
            </Panel>
          </div>
        </section>

        <section id="people" className="wide-panel">
          <div className="section-heading">
            <Users size={20} />
            <div>
              <h2>People And Time Zones</h2>
              <p>Compact HUD time cards for teammates and regions.</p>
            </div>
          </div>
          <div className="people-list">
            {config.people.people.map((person, index) => (
              <PersonRow
                key={`${person.key}-${index}`}
                person={person}
                timezoneOptions={timezoneOptions}
                dragging={draggingPersonIndex === index}
                onDragStart={() => setDraggingPersonIndex(index)}
                onDragOver={(event) => event.preventDefault()}
                onDrop={() => {
                  if (draggingPersonIndex !== null) {
                    movePerson(draggingPersonIndex, index);
                  }
                  setDraggingPersonIndex(null);
                }}
                onDragEnd={() => setDraggingPersonIndex(null)}
                onChange={(next) => mutate((draft) => void (draft.people.people[index] = next))}
                onRemove={() => mutate((draft) => void draft.people.people.splice(index, 1))}
              />
            ))}
          </div>
          <button className="secondary-button" type="button" onClick={() => mutate((draft) => void draft.people.people.push(emptyPerson(display.timezone_primary)))}>
            Add timezone
          </button>
        </section>

        {hasPokemonPlugin && game && pokemon && aiSelector && config.pokemon_companions ? (
        <section id="pokemon" className="panel-grid">
          <Panel title="Pokemon Scene" icon={Code2} subtitle="World loop and HUD tuning">
            <Field label="Game FPS">
              <NumberInput value={game.fps} onChange={(value) => mutate((draft) => void (draft.game!.game.fps = value))} />
            </Field>
            <Field label="Map switch seconds">
              <NumberInput
                value={game.map_switch_seconds}
                onChange={(value) => mutate((draft) => void (draft.game!.game.map_switch_seconds = value))}
              />
            </Field>
            <Field label="Route speed px">
              <NumberInput value={game.route_speed_px} onChange={(value) => mutate((draft) => void (draft.game!.game.route_speed_px = value))} />
            </Field>
            <Field label="HUD height">
              <NumberInput value={game.hud_height} onChange={(value) => mutate((draft) => void (draft.game!.game.hud_height = value))} />
            </Field>
            <Field label="Static background">
              <Switch
                checked={game.static_background}
                onChange={(value) => mutate((draft) => void (draft.game!.game.static_background = value))}
              />
            </Field>
            <Field label="Mock events">
              <Switch checked={game.events.mock_events} onChange={(value) => mutate((draft) => void (draft.game!.game.events.mock_events = value))} />
            </Field>
          </Panel>

          <Panel title="Pokemon Companions" icon={Users} subtitle="Visual mapping for recent Discord people">
            <div className="field field-wide">
              <span>Discord sprites</span>
              <div className="companion-list">
                {discordPeople.length ? (
                  discordPeople.map(([userId, person]) => (
                    <CompanionSpriteRow
                      key={userId}
                      userId={userId}
                      person={person}
                      visual={config.pokemon_companions!.companions.discord[userId]}
                      onSprite={(sprite_variant) =>
                        mutate((draft) => {
                          const current = draft.pokemon_companions!.companions.discord[userId] ?? { sprite_variant: null, label: "" };
                          draft.pokemon_companions!.companions.discord[userId] = { ...current, sprite_variant };
                        })
                      }
                      onLabel={(label) =>
                        mutate((draft) => {
                          const current = draft.pokemon_companions!.companions.discord[userId] ?? { sprite_variant: null, label: "" };
                          draft.pokemon_companions!.companions.discord[userId] = { ...current, label };
                        })
                      }
                    />
                  ))
                ) : (
                  <span className="empty-note">Discord people will appear here after voice activity.</span>
                )}
              </div>
            </div>
          </Panel>

          <Panel title="Pokemon AI Selector" icon={Bot} subtitle="Throttled Pokemon-specific AI selection">
            <Field label="Selector enabled">
              <Switch checked={aiSelector.enabled} onChange={(value) => mutate((draft) => void (draft.game!.game.events.ai_selector.enabled = value))} />
            </Field>
            <Field label="Async">
              <Switch checked={aiSelector.async} onChange={(value) => mutate((draft) => void (draft.game!.game.events.ai_selector.async = value))} />
            </Field>
            <Field label="Ambient calls">
              <Switch checked={aiSelector.ambient} onChange={(value) => mutate((draft) => void (draft.game!.game.events.ai_selector.ambient = value))} />
            </Field>
            <Field label="Candidate limit">
              <NumberInput
                value={aiSelector.candidate_limit}
                onChange={(value) => mutate((draft) => void (draft.game!.game.events.ai_selector.candidate_limit = value))}
              />
            </Field>
            <Field label="Cooldown seconds">
              <NumberInput
                value={aiSelector.throttle.cooldown_seconds}
                onChange={(value) => mutate((draft) => void (draft.game!.game.events.ai_selector.throttle.cooldown_seconds = value))}
              />
            </Field>
            <Field label="Requests per window">
              <NumberInput
                value={aiSelector.throttle.max_requests_per_window}
                onChange={(value) => mutate((draft) => void (draft.game!.game.events.ai_selector.throttle.max_requests_per_window = value))}
              />
            </Field>
          </Panel>

          <Panel title="Pokemon Data" icon={Cpu} subtitle="PokeAPI, sprite cache and generation bounds">
            <Field label="Generation limit">
              <NumberInput
                value={pokemon.generation_limit}
                onChange={(value) => mutate((draft) => void (draft.pokemon!.pokemon.generation_limit = value))}
              />
            </Field>
            <Field label="Sprite style">
              <Select
                value={pokemon.sprite_style}
                options={["animated", "front_default", "official-artwork"]}
                onChange={(value) => mutate((draft) => void (draft.pokemon!.pokemon.sprite_style = value))}
              />
            </Field>
            <Field label="Lazy download">
              <Switch
                checked={pokemon.lazy_download}
                onChange={(value) => mutate((draft) => void (draft.pokemon!.pokemon.lazy_download = value))}
              />
            </Field>
            <Field label="Offline mode">
              <Switch checked={pokemon.offline} onChange={(value) => mutate((draft) => void (draft.pokemon!.pokemon.offline = value))} />
            </Field>
            <Field label="Network timeout">
              <NumberInput
                value={pokemon.network_timeout_seconds}
                onChange={(value) => mutate((draft) => void (draft.pokemon!.pokemon.network_timeout_seconds = value))}
              />
            </Field>
            <Field label="Cache dir">
              <TextInput value={pokemon.cache_dir} onChange={(value) => mutate((draft) => void (draft.pokemon!.pokemon.cache_dir = value))} />
            </Field>
          </Panel>
        </section>
        ) : null}
      </main>

      <footer className="save-bar">
        <div>
          <strong>{dirty ? "Unsaved changes" : "Config synced"}</strong>
          <span>Writes only the loaded core, integration and selected plugin JSON configs.</span>
        </div>
        <div className="save-actions">
          <button className="secondary-button" type="button" onClick={() => void refreshConfig()}>
            <RefreshCw size={16} />
            Reload
          </button>
          <button className="primary-button" type="button" disabled={!dirty || saveState === "saving"} onClick={() => void persistConfig()}>
            {saveState === "saved" ? <Check size={16} /> : <Save size={16} />}
            {saveState === "saving" ? "Saving" : saveState === "saved" ? "Saved" : "Save JSON"}
          </button>
        </div>
      </footer>
    </div>
  );
}

function LayoutPreview({
  config,
  selected,
  onSelect,
  onChange,
  onEquipment,
}: {
  config: RuntimeConfig;
  selected: LayoutKey;
  onSelect: (key: LayoutKey) => void;
  onChange: (key: LayoutKey, box: LayoutBox) => void;
  onEquipment: (target: string) => void;
}) {
  const display = config.display.display;
  const box = display.layout[selected];
  const frameWidth = display.width;
  const frameHeight = display.height;
  const scale = Math.min(1.7, 520 / Math.max(frameWidth, 1), 560 / Math.max(frameHeight, 1));

  function dragStart(event: MouseEvent<HTMLDivElement>, key: LayoutKey) {
    event.preventDefault();
    onSelect(key);
    const startX = event.clientX;
    const startY = event.clientY;
    const startBox = { ...display.layout[key] };

    const move = (moveEvent: globalThis.MouseEvent) => {
      const next = clampBox(
        {
          ...startBox,
          x: Math.round(startBox.x + (moveEvent.clientX - startX) / scale),
          y: Math.round(startBox.y + (moveEvent.clientY - startY) / scale),
        },
        frameWidth,
        frameHeight,
      );
      onChange(key, next);
    };

    const up = () => {
      window.removeEventListener("mousemove", move);
      window.removeEventListener("mouseup", up);
    };

    window.addEventListener("mousemove", move);
    window.addEventListener("mouseup", up);
  }

  function resizeStart(event: MouseEvent<HTMLDivElement>, key: LayoutKey, direction: ResizeDirection) {
    event.preventDefault();
    event.stopPropagation();
    onSelect(key);
    const startX = event.clientX;
    const startY = event.clientY;
    const startBox = { ...display.layout[key] };

    const move = (moveEvent: globalThis.MouseEvent) => {
      const dx = Math.round((moveEvent.clientX - startX) / scale);
      const dy = Math.round((moveEvent.clientY - startY) / scale);
      const next = { ...startBox };
      if (direction.includes("e")) {
        next.width = startBox.width + dx;
      }
      if (direction.includes("s")) {
        next.height = startBox.height + dy;
      }
      if (direction.includes("w")) {
        next.x = startBox.x + dx;
        next.width = startBox.width - dx;
      }
      if (direction.includes("n")) {
        next.y = startBox.y + dy;
        next.height = startBox.height - dy;
      }
      onChange(key, clampBox(next, frameWidth, frameHeight));
    };

    const up = () => {
      window.removeEventListener("mousemove", move);
      window.removeEventListener("mouseup", up);
    };

    window.addEventListener("mousemove", move);
    window.addEventListener("mouseup", up);
  }

  return (
    <section id="layout" className="layout-editor wide-panel">
      <div className="section-heading">
        <Monitor size={20} />
        <div>
          <h2>Screen Layout</h2>
          <p>Preview the selected equipment frame and arrange the runtime regions written to display.json.</p>
        </div>
      </div>

      <div className="equipment-strip">
        {equipmentOptions.map((option) => (
          <button
            key={option.target}
            className={display.device.target === option.target ? "is-active" : ""}
            type="button"
            onClick={() => onEquipment(option.target)}
          >
            {option.label}
          </button>
        ))}
      </div>

      <div className="layout-workbench">
        <div className="screen-preview-shell">
          <div className="screen-preview" style={{ width: frameWidth * scale, height: frameHeight * scale }}>
            {layoutItems.map((item) => {
              const current = display.layout[item.key];
              return (
                <div
                  key={item.key}
                  role="button"
                  tabIndex={0}
                  className={`layout-region ${selected === item.key ? "is-selected" : ""}`}
                  style={{
                    left: current.x * scale,
                    top: current.y * scale,
                    width: current.width * scale,
                    height: current.height * scale,
                    borderColor: item.tone,
                    backgroundColor: `${item.tone}24`,
                  }}
                  onMouseDown={(event) => dragStart(event, item.key)}
                  onKeyDown={(event) => {
                    if (event.key === "Enter" || event.key === " ") {
                      event.preventDefault();
                      onSelect(item.key);
                    }
                  }}
                >
                  <span className="layout-region-label">{item.label}</span>
                  {selected === item.key
                    ? resizeDirections.map((direction) => (
                        <div
                          key={direction}
                          className={`resize-handle resize-handle-${direction}`}
                          role="presentation"
                          title="Resize"
                          onMouseDown={(event) => resizeStart(event, item.key, direction)}
                        >
                          {direction.length === 2 ? <MoveDiagonal2 size={10} strokeWidth={3} /> : null}
                        </div>
                      ))
                    : null}
                </div>
              );
            })}
          </div>
        </div>

        <div className="layout-controls">
          <Field label="Selected">
            <Select value={selected} options={layoutItems.map((item) => item.key)} onChange={(value) => onSelect(value as LayoutKey)} />
          </Field>
          <Field label="X">
            <NumberInput value={box.x} onChange={(value) => onChange(selected, clampBox({ ...box, x: value }, frameWidth, frameHeight))} />
          </Field>
          <Field label="Y">
            <NumberInput value={box.y} onChange={(value) => onChange(selected, clampBox({ ...box, y: value }, frameWidth, frameHeight))} />
          </Field>
          <Field label="Width">
            <NumberInput value={box.width} onChange={(value) => onChange(selected, clampBox({ ...box, width: value }, frameWidth, frameHeight))} />
          </Field>
          <Field label="Height">
            <NumberInput value={box.height} onChange={(value) => onChange(selected, clampBox({ ...box, height: value }, frameWidth, frameHeight))} />
          </Field>
          <button className="secondary-button" type="button" onClick={() => onChange(selected, defaultLayoutFor(frameWidth, frameHeight)[selected])}>
            Reset selected
          </button>
        </div>
      </div>
    </section>
  );
}

type IconComponent = ComponentType<{ size?: number }>;

function Metric({ icon: Icon, label, value }: { icon: IconComponent; label: string; value: string }) {
  return (
    <div className="metric">
      <Icon size={18} />
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function PluginCard({ plugin, selected, onToggle }: { plugin: DetectedPlugin; selected: boolean; onToggle: () => void }) {
  const Icon = visualPluginIcons[plugin.key] ?? Code2;
  return (
    <button className={`integration-card ${selected ? "is-on" : ""}`} type="button" onClick={onToggle}>
      <Icon size={18} />
      <span>{plugin.label}</span>
      <strong>{selected ? `${plugin.configKeys.length} configs` : "OFF"}</strong>
    </button>
  );
}

function Panel({ title, subtitle, icon: Icon, children }: { title: string; subtitle: string; icon: IconComponent; children: ReactNode }) {
  return (
    <section className="panel">
      <div className="panel-heading">
        <Icon size={19} />
        <div>
          <h2>{title}</h2>
          <p>{subtitle}</p>
        </div>
      </div>
      <div className="form-grid">{children}</div>
    </section>
  );
}

function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <label className="field">
      <span>{label}</span>
      {children}
    </label>
  );
}

function TextInput({ value, onChange }: { value: string; onChange: (value: string) => void }) {
  return <input value={value} onChange={(event) => onChange(event.target.value)} />;
}

function NumberInput({ value, onChange }: { value: number; onChange: (value: number) => void }) {
  return <input type="number" value={value} onChange={(event) => onChange(Number(event.target.value))} />;
}

function TextArea({ value, onChange }: { value: string; onChange: (value: string) => void }) {
  return <textarea value={value} rows={4} onChange={(event) => onChange(event.target.value)} />;
}

function Select({ value, options, onChange }: { value: string; options: string[]; onChange: (value: string) => void }) {
  return (
    <select value={value} onChange={(event) => onChange(event.target.value)}>
      {options.map((option) => (
        <option key={option} value={option}>
          {option}
        </option>
      ))}
    </select>
  );
}

type TimezoneOption = {
  value: string;
  label: string;
};

function TimezoneSelect({ value, options, onChange }: { value: string; options: TimezoneOption[]; onChange: (value: string) => void }) {
  const listId = useId();
  const [draft, setDraft] = useState(value);
  const optionValues = useMemo(() => new Set(options.map((option) => option.value)), [options]);

  useEffect(() => {
    setDraft(value);
  }, [value]);

  function update(next: string) {
    setDraft(next);
    if (optionValues.has(next)) {
      onChange(next);
    }
  }

  return (
    <>
      <input
        className="timezone-input"
        list={listId}
        value={draft}
        onBlur={() => {
          if (!optionValues.has(draft)) {
            setDraft(value);
          }
        }}
        onChange={(event) => update(event.target.value)}
      />
      <datalist id={listId}>
      {options.map((option) => (
          <option key={option.value} value={option.value} label={option.label} />
      ))}
      </datalist>
    </>
  );
}

function Switch({ checked, onChange }: { checked: boolean; onChange: (value: boolean) => void }) {
  return (
    <button className={`switch ${checked ? "is-on" : ""}`} type="button" onClick={() => onChange(!checked)} aria-pressed={checked}>
      <span />
      {checked ? "Enabled" : "Disabled"}
    </button>
  );
}

function PersonRow({
  person,
  timezoneOptions,
  dragging,
  onDragStart,
  onDragOver,
  onDrop,
  onDragEnd,
  onChange,
  onRemove,
}: {
  person: PersonConfig;
  timezoneOptions: TimezoneOption[];
  dragging: boolean;
  onDragStart: () => void;
  onDragOver: (event: DragEvent<HTMLDivElement>) => void;
  onDrop: () => void;
  onDragEnd: () => void;
  onChange: (person: PersonConfig) => void;
  onRemove: () => void;
}) {
  const update = (patch: Partial<PersonConfig>) => onChange({ ...person, ...patch });
  const updateTimezone = (timezone: string) => onChange({ ...person, ...timezonePatch(timezone) });
  return (
    <div className={`person-row ${dragging ? "is-dragging" : ""}`} onDragOver={onDragOver} onDrop={onDrop}>
      <button className="drag-handle" type="button" draggable onDragStart={onDragStart} onDragEnd={onDragEnd} aria-label={`Reorder ${person.name || person.timezone}`}>
        <GripVertical size={16} />
      </button>
      <TextInput value={person.name} onChange={(name) => update({ name })} />
      <TimezoneSelect value={person.timezone} options={timezoneOptions} onChange={updateTimezone} />
      <TextInput value={person.work_start} onChange={(work_start) => update({ work_start })} />
      <TextInput value={person.work_end} onChange={(work_end) => update({ work_end })} />
      <button className="icon-button" type="button" onClick={onRemove} aria-label={`Remove ${person.key}`}>
        Remove
      </button>
    </div>
  );
}

function CompanionSpriteRow({
  userId,
  person,
  visual,
  onSprite,
  onLabel,
}: {
  userId: string;
  person: DiscordPersonConfig;
  visual?: { sprite_variant: number | null; label: string };
  onSprite: (spriteVariant: number | null) => void;
  onLabel: (label: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const nicknames = person.nicknames.length ? person.nicknames.join(", ") : userId;
  const selected = visual?.sprite_variant ?? null;
  const activeVariant = selected ?? Math.abs(hashString(userId)) % discordSpriteVariants.length;
  function choose(spriteVariant: number | null) {
    onSprite(spriteVariant);
    setOpen(false);
  }
  return (
    <div className="companion-row">
      <div className="companion-meta">
        <strong>{person.display_name || userId}</strong>
        <span>{nicknames}</span>
        <input className="companion-label-input" value={visual?.label ?? ""} placeholder="Map label" onChange={(event) => onLabel(event.target.value)} />
      </div>
      <button className="sprite-current" type="button" onClick={() => setOpen(true)}>
        <img src={`/api/npc-sprites/${activeVariant}.gif`} alt="" />
        <span>{selected == null ? `Auto ${activeVariant}` : `Sprite ${selected}`}</span>
      </button>
      {open ? (
        <div className="sprite-modal-backdrop" role="presentation" onMouseDown={() => setOpen(false)}>
          <div className="sprite-modal" role="dialog" aria-modal="true" aria-label={`Choose sprite for ${person.display_name || userId}`} onMouseDown={(event) => event.stopPropagation()}>
            <div className="sprite-modal-heading">
              <div>
                <strong>{person.display_name || userId}</strong>
                <span>{nicknames}</span>
              </div>
              <button className="icon-button" type="button" onClick={() => setOpen(false)}>
                Close
              </button>
            </div>
            <div className="sprite-picker" role="radiogroup">
              <button className={`sprite-option sprite-auto ${selected == null ? "is-selected" : ""}`} type="button" onClick={() => choose(null)}>
                Auto
              </button>
              {discordSpriteVariants.map((variant) => (
                <button
                  className={`sprite-option ${selected === variant ? "is-selected" : ""}`}
                  key={variant}
                  type="button"
                  onClick={() => choose(variant)}
                  title={`Sprite ${variant}`}
                  aria-pressed={selected === variant}
                >
                  <img src={`/api/npc-sprites/${variant}.gif`} alt="" />
                  <span>{variant}</span>
                </button>
              ))}
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}

function hashString(value: string): number {
  let hash = 0;
  for (let index = 0; index < value.length; index += 1) {
    hash = (hash * 31 + value.charCodeAt(index)) | 0;
  }
  return hash;
}

function DiscordPersonRow({ userId, person }: { userId: string; person: DiscordPersonConfig }) {
  const nicknames = person.nicknames.length ? person.nicknames.join(", ") : userId;
  return (
    <div className="companion-row">
      <div className="companion-meta">
        <strong>{person.display_name || userId}</strong>
        <span>{nicknames}</span>
      </div>
      <span className="recent-stamp">{person.last_seen_at ? new Date(person.last_seen_at).toLocaleString() : ""}</span>
    </div>
  );
}

function lines(value: string): string[] {
  return value.split("\n").map((line) => line.trim()).filter(Boolean);
}

function csv(value: string): string[] {
  return value.split(",").map((item) => item.trim()).filter(Boolean);
}

function readSelectedPlugins(): string[] {
  try {
    const raw = window.localStorage.getItem("pixel-ops.config-studio.plugins");
    const parsed = raw ? JSON.parse(raw) : [];
    return Array.isArray(parsed) ? parsed.filter((item): item is string => typeof item === "string") : [];
  } catch {
    return [];
  }
}

function integrationConfig(config: RuntimeConfig, key: string): IntegrationToggle {
  const value = config.integrations.integrations[key];
  return value && typeof value === "object" && "enabled" in value ? (value as IntegrationToggle) : { enabled: false };
}

function discordPersonEntries(people: Record<string, DiscordPersonConfig>): Array<[string, DiscordPersonConfig]> {
  return Object.entries(people).sort(([, first], [, second]) => second.last_seen_at.localeCompare(first.last_seen_at));
}

function emptyPerson(timezone: string): PersonConfig {
  const patch = timezonePatch(timezone);
  return {
    key: patch.key,
    name: "",
    country: patch.country,
    show_flag: patch.show_flag,
    timezone: patch.timezone,
    timezone_label: patch.timezone_label,
    standard_key: patch.standard_key,
    daylight_key: patch.daylight_key,
    work_start: "09:00",
    work_end: "18:00",
  };
}

function buildTimezoneOptions(): TimezoneOption[] {
  const supportedValuesOf = (Intl as typeof Intl & { supportedValuesOf?: (key: "timeZone") => string[] }).supportedValuesOf;
  const zones = supportedValuesOf ? supportedValuesOf("timeZone") : fallbackTimezones;
  return Array.from(new Set([...zones, ...fallbackTimezones]))
    .sort((first, second) => first.localeCompare(second))
    .map((timezone) => ({
      value: timezone,
      label: `${timezoneLabel(timezone)} - ${timezone} (${timezoneKey(timezone, new Date())})`,
    }));
}

function timezonePatch(
  timezone: string,
): Pick<PersonConfig, "key" | "timezone" | "timezone_label" | "standard_key" | "daylight_key" | "country" | "show_flag"> {
  const standardKey = timezoneKey(timezone, new Date(Date.UTC(2026, 0, 1, 12)));
  const daylightKey = timezoneKey(timezone, new Date(Date.UTC(2026, 6, 1, 12)));
  const country = countryForTimezone(timezone);
  return {
    key: timezoneKey(timezone, new Date()),
    timezone,
    timezone_label: timezoneLabel(timezone),
    standard_key: standardKey,
    daylight_key: daylightKey,
    country,
    show_flag: Boolean(country),
  };
}

function countryForTimezone(timezone: string): string {
  const explicit: Record<string, string> = {
    "America/Sao_Paulo": "BR",
    "America/Mexico_City": "MX",
    "America/Phoenix": "US",
    "America/Los_Angeles": "US",
    "America/Denver": "US",
    "America/Chicago": "US",
    "America/New_York": "US",
    "Asia/Kolkata": "IN",
    "Europe/Lisbon": "PT",
  };
  return explicit[timezone] ?? "";
}

function timezoneLabel(timezone: string): string {
  const parts = timezone.split("/");
  return (parts[parts.length - 1] || timezone).replace(/_/g, " ");
}

function timezoneKey(timezone: string, date: Date): string {
  try {
    const formatter = new Intl.DateTimeFormat("en-US", {
      timeZone: timezone,
      timeZoneName: "short",
      hour: "2-digit",
      minute: "2-digit",
    });
    const name = formatter.formatToParts(date).find((part) => part.type === "timeZoneName")?.value;
    return compactTimezoneKey(name || timezone);
  } catch {
    return compactTimezoneKey(timezone);
  }
}

function compactTimezoneKey(value: string): string {
  const clean = value.replace(/^GMT/, "UTC").replace(/\s+/g, "");
  if (/^[A-Z]{2,5}$/.test(clean) || /^UTC[+-]\d{1,2}(:?\d{2})?$/.test(clean)) {
    return clean;
  }
  return clean
    .split(/[/_-]+/)
    .filter(Boolean)
    .map((part) => part[0]?.toUpperCase() ?? "")
    .join("")
    .slice(0, 5);
}

function ensureConfigDefaults(config: RuntimeConfig): RuntimeConfig {
  const next = cloneConfig(config);
  const display = next.display.display;
  display.device = display.device ?? {
    target: "window",
    output: "window",
    window_scale: 2,
    seconds: 20,
    forever: true,
    preview_sequence: false,
    full_frame: false,
  };
  display.layout = { ...defaultLayoutFor(display.width, display.height), ...(display.layout ?? {}) };
  next.integrations.integrations.github.fetch_deployments = next.integrations.integrations.github.fetch_deployments ?? true;
  next.integrations.integrations.github.deployment_workflows = next.integrations.integrations.github.deployment_workflows ?? [];
  next.integrations.integrations.weather.provider = next.integrations.integrations.weather.provider ?? "open_meteo";
  next.integrations.integrations.weather.timeout_seconds = next.integrations.integrations.weather.timeout_seconds ?? 8;
  next.integrations.integrations.weather.api_key_env = next.integrations.integrations.weather.api_key_env ?? "OPENWEATHERMAP_API_KEY";
  next.integrations.integrations.discord.bot_token_env = next.integrations.integrations.discord.bot_token_env ?? "PIXEL_OPS_DISCORD_BOT_TOKEN";
  next.integrations.integrations.discord.guild_id = next.integrations.integrations.discord.guild_id ?? "";
  next.integrations.integrations.discord.focus_user_id = next.integrations.integrations.discord.focus_user_id ?? "";
  next.integrations.integrations.discord.max_companions = next.integrations.integrations.discord.max_companions ?? 5;
  next.integrations.integrations.discord.gateway_reconnect_seconds = next.integrations.integrations.discord.gateway_reconnect_seconds ?? 10;
  next.discord_people = next.discord_people ?? { discord_people: { max_recent: 50, people: {} } };
  next.discord_people.discord_people.max_recent = next.discord_people.discord_people.max_recent ?? 50;
  next.discord_people.discord_people.people = next.discord_people.discord_people.people ?? {};
  for (const [userId, person] of Object.entries(next.discord_people.discord_people.people)) {
    next.discord_people.discord_people.people[userId] = {
      display_name: person.display_name ?? userId,
      nicknames: person.nicknames ?? [],
      last_seen_at: person.last_seen_at ?? "",
    };
  }
  if (next.pokemon) {
    next.pokemon.pokemon.offline = Boolean(next.pokemon.pokemon.offline);
  }
  if (next.pokemon_companions) {
    next.pokemon_companions.companions.discord = next.pokemon_companions.companions.discord ?? {};
    for (const [userId, visual] of Object.entries(next.pokemon_companions.companions.discord)) {
      next.pokemon_companions.companions.discord[userId] = {
        sprite_variant: visual.sprite_variant ?? null,
        label: visual.label ?? "",
      };
    }
  }
  next.people.people = next.people.people.map((person) => ({ ...person, show_flag: Boolean(person.show_flag) }));
  return next;
}

function digits(value: string): string {
  return value.replace(/\D/g, "");
}

function clampNumber(value: number, min: number, max: number): number {
  if (!Number.isFinite(value)) {
    return min;
  }
  return Math.max(min, Math.min(max, Math.round(value)));
}

function applyEquipment(config: RuntimeConfig, target: string) {
  const option = equipmentOptions.find((item) => item.target === target) ?? equipmentOptions[0];
  const display = config.display.display;
  display.device.target = option.target;
  display.device.output = option.output;
  if (target !== "window") {
    display.width = option.width;
    display.height = option.height;
    display.layout = defaultLayoutFor(option.width, option.height);
  }
}

function defaultLayoutFor(width: number, height: number): Record<LayoutKey, LayoutBox> {
  const hudHeight = Math.min(212, Math.max(116, Math.round(height * 0.44)));
  const textHeight = Math.min(96, Math.max(62, Math.round(height * 0.19)));
  const gameY = hudHeight;
  const textY = Math.max(gameY + 1, height - textHeight - 2);
  const contentWidth = Math.max(1, width - 16);
  const lowerHudY = Math.max(66, hudHeight - 48);
  const middleHudY = Math.max(48, lowerHudY - 44);
  return {
    timezones: { x: 8, y: 8, width: contentWidth, height: Math.max(86, middleHudY - 10) },
    route_signal: { x: 8, y: middleHudY, width: Math.max(88, Math.round(width * 0.28)), height: 40 },
    gauges: { x: Math.max(104, Math.round(width * 0.33)), y: middleHudY, width: Math.max(72, Math.round(width * 0.24)), height: 40 },
    weather: { x: Math.max(8, width - 120), y: middleHudY, width: 112, height: 40 },
    activity: { x: 8, y: lowerHudY, width: contentWidth, height: 40 },
    game: { x: 0, y: gameY, width, height: Math.max(1, textY - gameY - 4) },
    text_box: { x: 8, y: textY, width: Math.max(1, width - 16), height: Math.max(1, height - textY - 2) },
  };
}

function clampBox(box: LayoutBox, frameWidth: number, frameHeight: number): LayoutBox {
  const width = Math.max(8, Math.min(frameWidth, Math.round(box.width)));
  const height = Math.max(8, Math.min(frameHeight, Math.round(box.height)));
  return {
    ...box,
    x: Math.max(0, Math.min(frameWidth - width, Math.round(box.x))),
    y: Math.max(0, Math.min(frameHeight - height, Math.round(box.y))),
    width,
    height,
  };
}
