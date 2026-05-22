import {
  Activity,
  Bot,
  CalendarDays,
  Check,
  CloudSun,
  Code2,
  Cpu,
  Github,
  Monitor,
  RefreshCw,
  Save,
  Settings2,
  Users,
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import type { ComponentType, MouseEvent, ReactNode } from "react";
import mascotAlertImg from "./assets/pixelops-mascot-angry.png";
import mascotImg from "./assets/pixelops-mascot.png";
import mascotSleepyImg from "./assets/pixelops-mascot-sleepy.png";
import { PixelMascot } from "./components/PixelMascot";
import { cloneConfig, loadConfig, saveConfig } from "./lib/configApi";
import type { IntegrationToggle, LayoutBox, LayoutKey, PersonConfig, RuntimeConfig } from "./types";

type SaveState = "idle" | "saving" | "saved" | "error";

const integrations = [
  { key: "github", label: "GitHub", icon: Github },
  { key: "google_calendar", label: "Google Calendar", icon: CalendarDays },
  { key: "ics", label: "ICS", icon: CalendarDays },
  { key: "weather", label: "Weather", icon: CloudSun },
  { key: "ai_usage", label: "AI usage", icon: Activity },
  { key: "slack", label: "Slack", icon: Bot },
  { key: "discord", label: "Discord", icon: Bot },
] as const;

const layoutItems: Array<{ key: LayoutKey; label: string; tone: string }> = [
  { key: "timezones", label: "Timezones", tone: "#7fb2e6" },
  { key: "gauges", label: "Gauges", tone: "#7ee0bd" },
  { key: "weather", label: "Weather", tone: "#e8c766" },
  { key: "activity", label: "Activity", tone: "#ef846d" },
  { key: "game", label: "Game", tone: "#8fbf7a" },
  { key: "text_box", label: "Text box", tone: "#d8d0ff" },
];

const equipmentOptions = [
  { target: "window", label: "Window", width: 320, height: 480, output: "window" },
  { target: "turzx_35", label: "TURZX 3.5", width: 320, height: 480, output: "turzx" },
  { target: "turzx_94", label: "TURZX 9.4", width: 480, height: 320, output: "turzx" },
  { target: "preview", label: "Preview PNG", width: 320, height: 480, output: "preview" },
  { target: "gif", label: "GIF", width: 320, height: 480, output: "gif" },
] as const;

export function App() {
  const [config, setConfig] = useState<RuntimeConfig | null>(null);
  const [baseline, setBaseline] = useState<RuntimeConfig | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [saveState, setSaveState] = useState<SaveState>("idle");
  const [selectedLayout, setSelectedLayout] = useState<LayoutKey>("game");

  useEffect(() => {
    void refreshConfig();
  }, []);

  const dirty = useMemo(() => JSON.stringify(config) !== JSON.stringify(baseline), [baseline, config]);

  async function refreshConfig() {
    setError(null);
    const loaded = await loadConfig();
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

  if (!config) {
    return (
      <main className="loading-shell">
        <RefreshCw className="spin" size={24} />
        <span>Loading runtime config</span>
      </main>
    );
  }

  const display = config.display.display;
  const game = config.game.game;
  const pokemon = config.pokemon.pokemon;
  const aiSelector = game.events.ai_selector;
  const enabledCount = integrations.filter(({ key }) => Boolean((config.integrations.integrations[key] as IntegrationToggle).enabled)).length;

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
          <a href="#integrations">Integrations</a>
          <a href="#people">People</a>
          <a href="#pokemon">Pokemon</a>
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
          <Metric icon={Cpu} label="FPS" value={`${display.fps} display / ${game.fps} game`} />
          <Metric icon={Activity} label="Integrations" value={`${enabledCount} enabled`} />
          <Metric icon={Bot} label="AI model" value={display.ai.enabled ? display.ai.model : "off"} />
        </section>

        {error ? <div className="error-banner">{error}</div> : null}

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
              <TextInput
                value={display.timezone_primary}
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
            {integrations.map(({ key, label, icon: Icon }) => {
              const item = config.integrations.integrations[key] as IntegrationToggle;
              return (
                <button
                  className={`integration-card ${item.enabled ? "is-on" : ""}`}
                  key={key}
                  type="button"
                  onClick={() => mutate((draft) => void (((draft.integrations.integrations[key] as IntegrationToggle).enabled = !item.enabled)))}
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
            </Panel>

            <Panel title="Weather" icon={CloudSun} subtitle="Weather-like mood source">
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
                onChange={(next) => mutate((draft) => void (draft.people.people[index] = next))}
                onRemove={() => mutate((draft) => void draft.people.people.splice(index, 1))}
              />
            ))}
          </div>
          <button className="secondary-button" type="button" onClick={() => mutate((draft) => void draft.people.people.push(emptyPerson()))}>
            Add timezone
          </button>
        </section>

        <section id="pokemon" className="panel-grid">
          <Panel title="Pokemon Scene" icon={Code2} subtitle="World loop and HUD tuning">
            <Field label="Game FPS">
              <NumberInput value={game.fps} onChange={(value) => mutate((draft) => void (draft.game.game.fps = value))} />
            </Field>
            <Field label="Map switch seconds">
              <NumberInput
                value={game.map_switch_seconds}
                onChange={(value) => mutate((draft) => void (draft.game.game.map_switch_seconds = value))}
              />
            </Field>
            <Field label="Route speed px">
              <NumberInput value={game.route_speed_px} onChange={(value) => mutate((draft) => void (draft.game.game.route_speed_px = value))} />
            </Field>
            <Field label="HUD height">
              <NumberInput value={game.hud_height} onChange={(value) => mutate((draft) => void (draft.game.game.hud_height = value))} />
            </Field>
            <Field label="Static background">
              <Switch
                checked={game.static_background}
                onChange={(value) => mutate((draft) => void (draft.game.game.static_background = value))}
              />
            </Field>
            <Field label="Mock events">
              <Switch checked={game.events.mock_events} onChange={(value) => mutate((draft) => void (draft.game.game.events.mock_events = value))} />
            </Field>
          </Panel>

          <Panel title="Pokemon AI Selector" icon={Bot} subtitle="Throttled Pokemon-specific AI selection">
            <Field label="Selector enabled">
              <Switch checked={aiSelector.enabled} onChange={(value) => mutate((draft) => void (draft.game.game.events.ai_selector.enabled = value))} />
            </Field>
            <Field label="Async">
              <Switch checked={aiSelector.async} onChange={(value) => mutate((draft) => void (draft.game.game.events.ai_selector.async = value))} />
            </Field>
            <Field label="Ambient calls">
              <Switch checked={aiSelector.ambient} onChange={(value) => mutate((draft) => void (draft.game.game.events.ai_selector.ambient = value))} />
            </Field>
            <Field label="Candidate limit">
              <NumberInput
                value={aiSelector.candidate_limit}
                onChange={(value) => mutate((draft) => void (draft.game.game.events.ai_selector.candidate_limit = value))}
              />
            </Field>
            <Field label="Cooldown seconds">
              <NumberInput
                value={aiSelector.throttle.cooldown_seconds}
                onChange={(value) => mutate((draft) => void (draft.game.game.events.ai_selector.throttle.cooldown_seconds = value))}
              />
            </Field>
            <Field label="Requests per window">
              <NumberInput
                value={aiSelector.throttle.max_requests_per_window}
                onChange={(value) => mutate((draft) => void (draft.game.game.events.ai_selector.throttle.max_requests_per_window = value))}
              />
            </Field>
          </Panel>

          <Panel title="Pokemon Data" icon={Cpu} subtitle="PokeAPI, sprite cache and generation bounds">
            <Field label="Generation limit">
              <NumberInput
                value={pokemon.generation_limit}
                onChange={(value) => mutate((draft) => void (draft.pokemon.pokemon.generation_limit = value))}
              />
            </Field>
            <Field label="Sprite style">
              <Select
                value={pokemon.sprite_style}
                options={["animated", "front_default", "official-artwork"]}
                onChange={(value) => mutate((draft) => void (draft.pokemon.pokemon.sprite_style = value))}
              />
            </Field>
            <Field label="Lazy download">
              <Switch
                checked={pokemon.lazy_download}
                onChange={(value) => mutate((draft) => void (draft.pokemon.pokemon.lazy_download = value))}
              />
            </Field>
            <Field label="Offline mode">
              <Switch checked={pokemon.offline} onChange={(value) => mutate((draft) => void (draft.pokemon.pokemon.offline = value))} />
            </Field>
            <Field label="Network timeout">
              <NumberInput
                value={pokemon.network_timeout_seconds}
                onChange={(value) => mutate((draft) => void (draft.pokemon.pokemon.network_timeout_seconds = value))}
              />
            </Field>
            <Field label="Cache dir">
              <TextInput value={pokemon.cache_dir} onChange={(value) => mutate((draft) => void (draft.pokemon.pokemon.cache_dir = value))} />
            </Field>
          </Panel>
        </section>
      </main>

      <footer className="save-bar">
        <div>
          <strong>{dirty ? "Unsaved changes" : "Config synced"}</strong>
          <span>Writes to pixel_ops/config/*.json and pixel_ops/plugins/pokemon/*.json.</span>
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

  function dragStart(event: MouseEvent<HTMLButtonElement>, key: LayoutKey) {
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
                <button
                  key={item.key}
                  type="button"
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
                >
                  <span>{item.label}</span>
                </button>
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

function Switch({ checked, onChange }: { checked: boolean; onChange: (value: boolean) => void }) {
  return (
    <button className={`switch ${checked ? "is-on" : ""}`} type="button" onClick={() => onChange(!checked)} aria-pressed={checked}>
      <span />
      {checked ? "Enabled" : "Disabled"}
    </button>
  );
}

function PersonRow({ person, onChange, onRemove }: { person: PersonConfig; onChange: (person: PersonConfig) => void; onRemove: () => void }) {
  const update = (patch: Partial<PersonConfig>) => onChange({ ...person, ...patch });
  return (
    <div className="person-row">
      <TextInput value={person.key} onChange={(key) => update({ key })} />
      <TextInput value={person.name} onChange={(name) => update({ name })} />
      <TextInput value={person.country} onChange={(country) => update({ country: country.toUpperCase() })} />
      <label className="inline-switch">
        <span>Flag</span>
        <Switch checked={Boolean(person.show_flag)} onChange={(show_flag) => update({ show_flag })} />
      </label>
      <TextInput value={person.timezone} onChange={(timezone) => update({ timezone })} />
      <TextInput value={person.timezone_label} onChange={(timezone_label) => update({ timezone_label })} />
      <TextInput value={person.work_start} onChange={(work_start) => update({ work_start })} />
      <TextInput value={person.work_end} onChange={(work_end) => update({ work_end })} />
      <button className="icon-button" type="button" onClick={onRemove} aria-label={`Remove ${person.key}`}>
        Remove
      </button>
    </div>
  );
}

function lines(value: string): string[] {
  return value.split("\n").map((line) => line.trim()).filter(Boolean);
}

function csv(value: string): string[] {
  return value.split(",").map((item) => item.trim()).filter(Boolean);
}

function emptyPerson(): PersonConfig {
  return {
    key: "NEW",
    name: "",
    country: "",
    show_flag: false,
    timezone: "America/Sao_Paulo",
    timezone_label: "New timezone",
    work_start: "09:00",
    work_end: "18:00",
  };
}

function ensureConfigDefaults(config: RuntimeConfig): RuntimeConfig {
  const next = cloneConfig(config);
  const display = next.display.display;
  next.pokemon.pokemon.offline = Boolean(next.pokemon.pokemon.offline);
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
  next.people.people = next.people.people.map((person) => ({ ...person, show_flag: Boolean(person.show_flag) }));
  return next;
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
  return {
    timezones: { x: 8, y: 8, width: Math.max(120, width - 16), height: Math.max(86, hudHeight - 58) },
    gauges: { x: 8, y: Math.max(66, hudHeight - 48), width: Math.max(112, Math.round(width * 0.45)), height: 40 },
    weather: { x: Math.round(width * 0.51), y: gameY + 2, width: Math.max(116, width - Math.round(width * 0.51) - 16), height: 42 },
    activity: { x: Math.round(width * 0.51), y: Math.max(66, hudHeight - 48), width: Math.max(116, width - Math.round(width * 0.51) - 8), height: 40 },
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
