import {
  Activity,
  Bot,
  CalendarDays,
  Cable,
  Check,
  CloudSun,
  Code2,
  Cpu,
  Github,
  GripVertical,
  Maximize2,
  Minimize2,
  Monitor,
  MoveDiagonal2,
  Music2,
  FileImage,
  Play,
  Plus,
  RefreshCw,
  Save,
  Square,
  Terminal,
  Trash2,
  Users,
  ZoomIn,
  ZoomOut,
} from "lucide-react";
import { useEffect, useId, useMemo, useRef, useState } from "react";
import type { ComponentType, DragEvent, MouseEvent, ReactNode } from "react";
import mascotAlertImg from "./assets/pixelops-mascot-angry.png";
import mascotImg from "./assets/pixelops-mascot.png";
import mascotSleepyImg from "./assets/pixelops-mascot-sleepy.png";
import { PixelMascot } from "./components/PixelMascot";
import {
  cloneConfig,
  configureKiteSecrets,
  loadConfig,
  loadConfigManifest,
  loadDiscordProfile,
  loadGithubRepos,
  loadKiteStatus,
  loadNpcSpriteManifest,
  loadRuntimeAutostartStatus,
  loadRuntimeStatus,
  pollDiscordOAuthStatus,
  pollGithubDeviceLogin,
  runKiteAction,
  runRuntimeAutostartAction,
  runRuntimeAction,
  saveConfig,
  saveDiscordBotToken,
  saveGithubToken,
  scanUsbDisplays,
  identifyUsbDisplay,
  startDiscordOAuth,
  startGithubDeviceLogin,
} from "./lib/configApi";
import type {
  ConfigManifest,
  DetectedPlugin,
  DiscordGuildOption,
  DiscordOAuthStartResponse,
  DiscordPersonConfig,
  DisplayOutputConfig,
  GitHubDeviceStartResponse,
  GitHubRepoOption,
  IntegrationToggle,
  KiteActionResult,
  LayoutBox,
  LayoutKey,
  LayoutProfileConfig,
  LayoutWindowOption,
  MovementConfig,
  MovementRect,
  PersonConfig,
  RuntimeAutostartStatus,
  RuntimeConfig,
  RuntimeStatus,
  UsbValidationResult,
} from "./types";

type SaveState = "idle" | "saving" | "saved" | "error";
type MovementLayer = "walkable" | "blocked";
type PokemonMapOption = { key: string; label: string; width: number; height: number; url: string };
type PokemonGameConfig = NonNullable<RuntimeConfig["game"]>["game"];
type PokemonDataConfig = NonNullable<RuntimeConfig["pokemon"]>["pokemon"];
type PokemonAiSelectorConfig = PokemonGameConfig["events"]["ai_selector"];
type PokemonPanelKey = "scene" | "companions" | "ai" | "data";
type UsbDeviceCandidate = NonNullable<UsbValidationResult["devices"]>[number];
type SettingsTabItem = {
  key: string;
  label: string;
  icon: IconComponent;
  tone?: "plugin" | "integration";
};
type LayoutThemeDefinition = {
  label: string;
  palette: string[];
  tones: Record<string, string>;
};

const integrationIcons: Record<string, IconComponent> = {
  github: Github,
  google_calendar: CalendarDays,
  ics: CalendarDays,
  weather: CloudSun,
  ai_usage: Activity,
  pc_stats: Cpu,
  clickup: Check,
  todoist: Check,
  media: Music2,
  kite: Cable,
  slack: Bot,
  discord: Bot,
  zoom: Users,
};

const visualPluginIcons: Record<string, IconComponent> = {
  pokemon: Code2,
};

const layoutWindowCatalog: LayoutWindowOption[] = [
  { kind: "timezones", label: "Timezones timeline", tone: "#7fb2e6" },
  { kind: "timezones_clock", label: "Timezones clock", tone: "#9ad18b" },
  { kind: "activity", label: "Activity", tone: "#ef846d" },
  { kind: "meetings_day", label: "Meetings Day", tone: "#9aa7ff" },
  { kind: "mana", label: "Mana", tone: "#4f9fff" },
  { kind: "gamification", label: "Player HP", tone: "#ef6461" },
];

const layoutThemeCatalog: Record<string, LayoutThemeDefinition> = {
  default: {
    label: "Default",
    palette: ["#7fb2e6", "#9ad18b", "#ef846d", "#9aa7ff", "#f0a35d", "#7ee0bd", "#e8c766", "#d8d0ff"],
    tones: {},
  },
  pokemon: {
    label: "Pokemon",
    palette: ["#ef6461", "#f7c948", "#5fbf7a", "#5da9e9", "#b58cff", "#f0a35d", "#7ee0bd", "#f07f95"],
    tones: {
      game: "#5fbf7a",
      text_box: "#d8d0ff",
      pokemon_captures: "#ef6461",
      route_signal: "#f0a35d",
      weather: "#e8c766",
      meetings_day: "#9aa7ff",
      mana: "#4f9fff",
      gamification: "#ef6461",
    },
  },
  terminal: {
    label: "Terminal",
    palette: ["#65f0a1", "#4fd1c5", "#a7f3d0", "#facc15", "#f472b6", "#93c5fd", "#c4b5fd", "#fb7185"],
    tones: {
      activity: "#65f0a1",
      gauges: "#4fd1c5",
      mana: "#60ccff",
      pc_stats: "#a7f3d0",
      tasks: "#facc15",
      tasks_board: "#f472b6",
      gamification: "#65f0a1",
    },
  },
  ocean: {
    label: "Ocean",
    palette: ["#67e8f9", "#38bdf8", "#818cf8", "#2dd4bf", "#a7f3d0", "#f0abfc", "#f9a8d4", "#fde68a"],
    tones: {
      timezones: "#67e8f9",
      timezones_clock: "#38bdf8",
      weather: "#2dd4bf",
      meetings_day: "#818cf8",
      mana: "#38bdf8",
      gamification: "#67e8f9",
    },
  },
  ember: {
    label: "Ember",
    palette: ["#fb7185", "#f97316", "#facc15", "#fdba74", "#fda4af", "#c084fc", "#60a5fa", "#34d399"],
    tones: {
      activity: "#fb7185",
      route_signal: "#f97316",
      weather: "#facc15",
      media: "#fdba74",
      mana: "#60a5fa",
      gamification: "#fb7185",
    },
  },
};
const layoutThemeKeys = Object.keys(layoutThemeCatalog);

const resizeDirections = ["n", "s", "e", "w", "nw", "ne", "sw", "se"] as const;
type ResizeDirection = (typeof resizeDirections)[number];
const displayArrangementWidth = 760;
const displayArrangementHeight = 260;
const displayArrangementPadding = 24;
const displayArrangementScale = 0.16;
const displayArrangementZoomStep = 0.05;
const displayArrangementMinZoom = 0.08;
const displayArrangementMaxZoom = 0.5;
const layoutPreviewZoomStep = 0.25;
const layoutPreviewMinZoom = 0.25;
const layoutPreviewMaxZoom = 3;

const equipmentOptions = [
  { target: "window", label: "Window", width: 320, height: 480, output: "window" },
  { target: "turzx_35", label: "TURZX 3.5", width: 320, height: 480, output: "turzx" },
  { target: "turzx_94", label: "TURZX 9.4", width: 480, height: 320, output: "turzx" },
  { target: "thermalright", label: "Thermalright LY", width: 1920, height: 462, output: "thermalright" },
  { target: "preview", label: "Preview PNG", width: 320, height: 480, output: "preview" },
  { target: "gif", label: "GIF", width: 320, height: 480, output: "gif" },
] as const;

const fallbackDiscordSpriteVariants = Array.from({ length: 55 }, (_, index) => index);
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
  const [pokemonMaps, setPokemonMaps] = useState<PokemonMapOption[]>([]);
  const [npcSpriteVariants, setNpcSpriteVariants] = useState<number[]>(fallbackDiscordSpriteVariants);
  const [pathName, setPathName] = useState(() => window.location.pathname);
  const [runtimeStatus, setRuntimeStatus] = useState<RuntimeStatus | null>(null);
  const [runtimeAutostart, setRuntimeAutostart] = useState<RuntimeAutostartStatus | null>(null);
  const [runtimeBusy, setRuntimeBusy] = useState<string | null>(null);
  const [usbBusy, setUsbBusy] = useState<string | null>(null);
  const [usbValidation, setUsbValidation] = useState<UsbValidationResult | null>(null);
  const [activeSettingsTab, setActiveSettingsTab] = useState<string>("");
  const timezoneOptions = useMemo(() => buildTimezoneOptions(), []);

  useEffect(() => {
    void refreshManifest();
  }, []);

  useEffect(() => {
    if (!manifest) return;
    void refreshConfig(selectedPluginKeys);
  }, [manifest, selectedPluginKeys]);

  useEffect(() => {
    void fetch("/api/pokemon-maps")
      .then((response) => (response.ok ? response.json() : { maps: [] }))
      .then((payload) => setPokemonMaps(Array.isArray(payload.maps) ? payload.maps : []))
      .catch(() => setPokemonMaps([]));
  }, []);

  useEffect(() => {
    void loadNpcSpriteManifest()
      .then((manifest) => setNpcSpriteVariants(Array.isArray(manifest.variants) && manifest.variants.length ? manifest.variants : fallbackDiscordSpriteVariants))
      .catch(() => setNpcSpriteVariants(fallbackDiscordSpriteVariants));
  }, []);

  useEffect(() => {
    void refreshRuntimeStatus();
    void refreshRuntimeAutostartStatus();
    const interval = window.setInterval(() => void refreshRuntimeStatus(false), 2500);
    return () => window.clearInterval(interval);
  }, []);

  useEffect(() => {
    const updatePath = () => setPathName(window.location.pathname);
    window.addEventListener("popstate", updatePath);
    return () => window.removeEventListener("popstate", updatePath);
  }, []);

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

  async function refreshRuntimeStatus(reportError = true) {
    try {
      setRuntimeStatus(await loadRuntimeStatus());
    } catch (caught) {
      if (reportError) {
        setError(caught instanceof Error ? caught.message : String(caught));
      }
    }
  }

  async function refreshRuntimeAutostartStatus(reportError = true) {
    try {
      setRuntimeAutostart(await loadRuntimeAutostartStatus());
    } catch (caught) {
      if (reportError) {
        setError(caught instanceof Error ? caught.message : String(caught));
      }
    }
  }

  async function triggerRuntimeAction(action: "check" | "preview" | "run/start" | "run/stop" | "window/start" | "window/stop") {
    setRuntimeBusy(action);
    setError(null);
    try {
      setRuntimeStatus(await runRuntimeAction(action));
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : String(caught));
    } finally {
      setRuntimeBusy(null);
    }
  }

  async function triggerRuntimeAutostartAction(action: "install" | "remove") {
    setRuntimeBusy(`autostart/${action}`);
    setError(null);
    try {
      setRuntimeAutostart(await runRuntimeAutostartAction(action));
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : String(caught));
    } finally {
      setRuntimeBusy(null);
    }
  }

  async function triggerUsbScan() {
    setUsbBusy("scan");
    setError(null);
    try {
      setUsbValidation(await scanUsbDisplays());
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : String(caught));
    } finally {
      setUsbBusy(null);
    }
  }

  async function triggerDisplayIdentify(display: DisplayOutputConfig) {
    setUsbBusy(display.id);
    setError(null);
    try {
      setUsbValidation(await identifyUsbDisplay(display));
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : String(caught));
    } finally {
      setUsbBusy(null);
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

  function navigate(path: string) {
    window.history.pushState({}, "", path);
    setPathName(path);
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
  const layoutOptions = layoutWindowOptions(config, manifest, selectedPluginKeys);
  const discordPeopleConfig = config.discord_people?.discord_people ?? { max_recent: 50, people: {} };
  const discordPeople = discordPersonEntries(discordPeopleConfig.people);
  const enabledCount = manifest.integrations.filter(({ key }) => Boolean(integrationConfig(config, key).enabled)).length;
  const activeVisualPlugins = manifest.visualPlugins.filter((plugin) => selectedPluginKeys.includes(plugin.key));
  const activeIntegrations = manifest.integrations.filter(({ key }) => Boolean(integrationConfig(config, key).enabled));
  const settingsTabs: SettingsTabItem[] = [
    ...activeVisualPlugins.map((plugin) => ({
      key: `plugin:${plugin.key}`,
      label: plugin.label,
      icon: visualPluginIcons[plugin.key] ?? Code2,
      tone: "plugin" as const,
    })),
    ...activeIntegrations.map((integration) => ({
      key: `integration:${integration.key}`,
      label: integration.label,
      icon: integrationIcons[integration.key] ?? Bot,
      tone: "integration" as const,
    })),
  ];
  const activeSettingsKey = settingsTabs.some((tab) => tab.key === activeSettingsTab) ? activeSettingsTab : settingsTabs[0]?.key ?? "";
  const activePluginKey = activeSettingsKey.startsWith("plugin:") ? activeSettingsKey.slice("plugin:".length) : "";
  const activeIntegrationKey = activeSettingsKey.startsWith("integration:") ? activeSettingsKey.slice("integration:".length) : "";
  const isPluginMapsRoute = pathName === "/pluginmaps";

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
          <a href="/" onClick={(event) => { event.preventDefault(); navigate("/"); }}>Home</a>
          {!isPluginMapsRoute ? <a href="#layout">Layout</a> : null}
          {!isPluginMapsRoute ? <a href="#display">Display</a> : null}
          {!isPluginMapsRoute ? <a href="#runtime">Runtime</a> : null}
          {!isPluginMapsRoute ? <a href="#plugins">Plugins + Integrations</a> : null}
          {!isPluginMapsRoute ? <a href="#people">People</a> : null}
          {hasPokemonPlugin ? <a href="/pluginmaps" onClick={(event) => { event.preventDefault(); navigate("/pluginmaps"); }}>Plugin maps</a> : null}
        </nav>
      </header>

      {isPluginMapsRoute ? (
      <main className="pluginmaps-main">
        {error ? <div className="error-banner">{error}</div> : null}
        {hasPokemonPlugin && game ? (
          <section className="wide-panel pluginmaps-panel">
            <div className="section-heading">
              <MoveDiagonal2 size={20} />
              <div>
                <h2>Plugin Maps</h2>
                <p>Draw Pokemon movement areas directly on full map images. Rectangles are saved in source-map coordinates.</p>
              </div>
            </div>
            <MovementAreaEditor
              maps={pokemonMaps}
              movement={game.movement}
              onChange={(movement) => mutate((draft) => void (draft.game!.game.movement = movement))}
              expanded
            />
          </section>
        ) : (
          <section className="wide-panel">
            <div className="section-heading">
              <MoveDiagonal2 size={20} />
              <div>
                <h2>Plugin Maps</h2>
                <p>Select the Pokemon visual plugin to load map movement configuration.</p>
              </div>
            </div>
          </section>
        )}
      </main>
      ) : (
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
              <a className="hero-button secondary" href="#plugins">
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

        <RuntimePanel
          status={runtimeStatus}
          autostart={runtimeAutostart}
          busy={runtimeBusy}
          onCheck={() => void triggerRuntimeAction("check")}
          onPreview={() => void triggerRuntimeAction("preview")}
          onStartRun={() => void triggerRuntimeAction("run/start")}
          onStopRun={() => void triggerRuntimeAction("run/stop")}
          onStartWindow={() => void triggerRuntimeAction("window/start")}
          onStopWindow={() => void triggerRuntimeAction("window/stop")}
          onInstallAutostart={() => void triggerRuntimeAutostartAction("install")}
          onRemoveAutostart={() => void triggerRuntimeAutostartAction("remove")}
        />

        <section id="plugins" className="wide-panel">
          <div className="section-heading">
            <Code2 size={20} />
            <div>
              <h2>Plugins And Integrations</h2>
              <p>Visual plugins own interface configs. Runtime integrations feed ambient state into the app.</p>
            </div>
          </div>
          <div className="integration-grid">
            {manifest.visualPlugins.map((plugin) => (
              <PluginCard
                key={plugin.key}
                plugin={plugin}
                selected={selectedPluginKeys.includes(plugin.key)}
                onToggle={() => {
                  if (!selectedPluginKeys.includes(plugin.key)) {
                    setActiveSettingsTab(`plugin:${plugin.key}`);
                  }
                  toggleVisualPlugin(plugin.key);
                }}
              />
            ))}
            {manifest.integrations.map(({ key, label }) => {
              const item = integrationConfig(config, key);
              const Icon = integrationIcons[key] ?? Bot;
              return (
                <button
                  className={`integration-card provider-card ${item.enabled ? "is-on" : ""}`}
                  key={key}
                  type="button"
                  onClick={() => {
                    if (!item.enabled) {
                      setActiveSettingsTab(`integration:${key}`);
                    }
                    mutate((draft) => {
                      const current = integrationConfig(draft, key);
                      draft.integrations.integrations[key] = { ...current, enabled: !current.enabled };
                    });
                  }}
                >
                  <Icon size={18} />
                  <span>{label}</span>
                  <strong>{item.enabled ? "ON" : "OFF"}</strong>
                </button>
              );
            })}
          </div>
          <SettingsTabs tabs={settingsTabs} activeKey={activeSettingsKey} onSelect={setActiveSettingsTab}>
            {activePluginKey === "pokemon" && hasPokemonPlugin && game && pokemon && aiSelector && config.pokemon_companions ? (
              <PokemonPluginPanels
                game={game}
                pokemon={pokemon}
                aiSelector={aiSelector}
                config={config}
                discordPeople={discordPeople}
                spriteVariants={npcSpriteVariants}
                onMutate={mutate}
              />
            ) : activePluginKey ? (
              <div className="empty-plugin-tab">
                <Code2 size={18} />
                <span>No editable panels are registered for this plugin yet.</span>
              </div>
            ) : activeIntegrationKey ? (
              <IntegrationPanel
                activeKey={activeIntegrationKey}
                config={config}
                discordPeople={discordPeople}
                discordPeopleConfig={discordPeopleConfig}
                onMutate={mutate}
              />
            ) : null}
          </SettingsTabs>
        </section>

        <LayoutPreview
          config={config}
          options={layoutOptions}
          selected={selectedLayout}
          onSelect={setSelectedLayout}
          onChange={(key, box) => mutate((draft) => void (draft.display.display.layout[key] = box))}
          onAdd={(kind) =>
            mutate((draft) => {
              const display = draft.display.display;
              const key = nextLayoutWindowKey(display.layout, kind);
              display.layout[key] = layoutBoxForNewWindow(kind, display.width, display.height, display.layout);
              setSelectedLayout(key);
            })
          }
          onRemove={(key) =>
            mutate((draft) => {
              removeLayoutWindow(draft.display.display.layout, key);
              for (const profile of Object.values(draft.display.display.orientations ?? {})) {
                if (profile.layout) {
                  removeLayoutWindow(profile.layout, key, true);
                }
              }
              setSelectedLayout(firstLayoutWindowKey(draft.display.display.layout) ?? "game");
            })
          }
          onFactoryDefault={() =>
            mutate((draft) => {
              const display = draft.display.display;
              display.layout = defaultLayoutFor(display.width, display.height);
              setSelectedLayout("game");
            })
          }
          onEquipment={(target) => mutate((draft) => applyEquipment(draft, target))}
          onThemeChange={(theme) => mutate((draft) => void (draft.display.display.layout_theme = theme))}
          onSaveLayoutProfile={(label) =>
            mutate((draft) => {
              const display = draft.display.display;
              ensureDisplayOutputs(display);
              display.layout_profiles = display.layout_profiles ?? {};
              const key = layoutProfileKey(label);
              display.layout_profiles[key] = snapshotLayoutProfile(display, label);
            })
          }
          onRestoreLayoutProfile={(key) =>
            mutate((draft) => {
              const display = draft.display.display;
              const profile = display.layout_profiles?.[key];
              if (!profile) return;
              restoreLayoutProfile(display, profile);
              setSelectedLayout(firstLayoutWindowKey(display.layout) ?? "game");
            })
          }
          onDeleteLayoutProfile={(key) =>
            mutate((draft) => {
              delete draft.display.display.layout_profiles?.[key];
            })
          }
          usbBusy={usbBusy}
          usbValidation={usbValidation}
          onUsbScan={() => void triggerUsbScan()}
          onIdentifyDisplay={(display) => void triggerDisplayIdentify(display)}
          onDisplayChange={(displayId, next) =>
            mutate((draft) => {
              const displays = ensureDisplayOutputs(draft.display.display);
              const index = displays.findIndex((display) => display.id === displayId);
              if (index >= 0) {
                const current = displays[index];
                const candidate = displayGeometryChanged(current, next) ? attachDisplayToNearest(next, displays, displayId) : next;
                if (displayGeometryChanged(current, candidate) && displayOverlapsAny(candidate, displays, displayId)) {
                  return;
                }
                displays[index] = candidate;
              }
              applyMultiDisplayBounds(draft.display.display);
              applyPrimaryDisplay(draft.display.display, displays[0]);
            })
          }
          onAddDisplay={() =>
            mutate((draft) => {
              const display = draft.display.display;
              const displays = ensureDisplayOutputs(display);
              const next = newDisplayOutput(displays.length + 1, displays);
              displays.push(next);
              applyMultiDisplayBounds(display);
            })
          }
          onAddUsbDisplay={(device) =>
            mutate((draft) => {
              const display = draft.display.display;
              const displays = ensureDisplayOutputs(display);
              const next = newDisplayOutputFromUsbDevice(displays.length + 1, displays, device);
              displays.push(next);
              applyMultiDisplayBounds(display);
            })
          }
          onRemoveDisplay={(displayId) =>
            mutate((draft) => {
              const display = draft.display.display;
              const displays = ensureDisplayOutputs(display);
              if (displays.length <= 1) return;
              const index = displays.findIndex((item) => item.id === displayId);
              if (index >= 0) {
                displays.splice(index, 1);
              }
              displays.forEach((item, itemIndex) => {
                item.identify_number = itemIndex + 1;
                item.label = item.label || `Display ${itemIndex + 1}`;
              });
              applyMultiDisplayBounds(display);
            })
          }
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
                options={["window", "preview", "gif", "turzx", "thermalright"]}
                onChange={(value) =>
                  mutate((draft) => {
                    if (value === "thermalright") {
                      applyEquipment(draft, "thermalright");
                    } else {
                      draft.display.display.device.output = value;
                    }
                  })
                }
              />
            </Field>
            <Field label="Canvas">
              <ReadOnlyValue value={`${display.width}x${display.height}`} />
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

      </main>
      )}

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
  options,
  selected,
  onSelect,
  onChange,
  onAdd,
  onRemove,
  onFactoryDefault,
  onEquipment,
  onThemeChange,
  onSaveLayoutProfile,
  onRestoreLayoutProfile,
  onDeleteLayoutProfile,
  usbBusy,
  usbValidation,
  onUsbScan,
  onIdentifyDisplay,
  onDisplayChange,
  onAddDisplay,
  onAddUsbDisplay,
  onRemoveDisplay,
}: {
  config: RuntimeConfig;
  options: LayoutWindowOption[];
  selected: LayoutKey;
  onSelect: (key: LayoutKey) => void;
  onChange: (key: LayoutKey, box: LayoutBox) => void;
  onAdd: (kind: string) => void;
  onRemove: (key: LayoutKey) => void;
  onFactoryDefault: () => void;
  onEquipment: (target: string) => void;
  onThemeChange: (theme: string) => void;
  onSaveLayoutProfile: (label: string) => void;
  onRestoreLayoutProfile: (key: string) => void;
  onDeleteLayoutProfile: (key: string) => void;
  usbBusy: string | null;
  usbValidation: UsbValidationResult | null;
  onUsbScan: () => void;
  onIdentifyDisplay: (display: DisplayOutputConfig) => void;
  onDisplayChange: (displayId: string, next: DisplayOutputConfig) => void;
  onAddDisplay: () => void;
  onAddUsbDisplay: (device: UsbDeviceCandidate) => void;
  onRemoveDisplay: (displayId: string) => void;
}) {
  const display = config.display.display;
  const displays = display.device.displays?.length ? display.device.displays : [displayOutputFromConfig(display, 1)];
  const bounds = displayBounds(displays);
  const frameWidth = bounds.width;
  const frameHeight = bounds.height;
  const [layoutZoom, setLayoutZoom] = useState(1);
  const scale = layoutZoom;
  const [gridEnabled, setGridEnabled] = useState(true);
  const [gridSize, setGridSize] = useState(8);
  const [layoutExpanded, setLayoutExpanded] = useState(false);
  const [addKind, setAddKind] = useState(options[0]?.kind ?? "activity");
  const [profileName, setProfileName] = useState("My layout");
  const [selectedProfileKey, setSelectedProfileKey] = useState("");
  const activeLayoutTheme = layoutThemeCatalog[display.layout_theme ?? "default"] ? (display.layout_theme ?? "default") : "default";
  const optionByKind = new Map(options.map((option) => [option.kind, option]));
  const layoutProfiles = display.layout_profiles ?? {};
  const profileKeys = Object.keys(layoutProfiles);
  const layoutItems = Object.entries(display.layout)
    .map(([key, box]) => {
      const kind = layoutWindowKind(key, box);
      const baseOption = optionByKind.get(kind) ?? { kind, label: titleize(kind), tone: "#aeb7c8" };
      const option = { ...baseOption, tone: layoutThemeTone(activeLayoutTheme, kind, key, baseOption.tone) };
      return { key, kind, box, option };
    });
  const activeKey = display.layout[selected] ? selected : layoutItems[0]?.key;
  const box = (activeKey ? display.layout[activeKey] : undefined) ?? { x: 0, y: 0, width: frameWidth, height: frameHeight };

  useEffect(() => {
    if (!options.some((option) => option.kind === addKind)) {
      setAddKind(options[0]?.kind ?? "activity");
    }
  }, [addKind, options]);

  useEffect(() => {
    if (activeKey && activeKey !== selected) {
      onSelect(activeKey);
    }
  }, [activeKey, onSelect, selected]);

  useEffect(() => {
    if (selectedProfileKey && !layoutProfiles[selectedProfileKey]) {
      setSelectedProfileKey(profileKeys[0] ?? "");
    } else if (!selectedProfileKey && profileKeys.length) {
      setSelectedProfileKey(profileKeys[0]);
    }
  }, [layoutProfiles, profileKeys, selectedProfileKey]);

  function snap(value: number): number {
    if (!gridEnabled) return Math.round(value);
    const size = Math.max(1, gridSize);
    return Math.round(value / size) * size;
  }

  function snapBox(nextBox: LayoutBox): LayoutBox {
    if (!gridEnabled) return nextBox;
    return {
      ...nextBox,
      x: snap(nextBox.x),
      y: snap(nextBox.y),
      width: Math.max(gridSize, snap(nextBox.width)),
      height: Math.max(gridSize, snap(nextBox.height)),
    };
  }

  function commitBox(key: LayoutKey, nextBox: LayoutBox) {
    onChange(key, clampBox(snapBox(nextBox), frameWidth, frameHeight));
  }

  function dragStart(event: MouseEvent<HTMLDivElement>, key: LayoutKey) {
    event.preventDefault();
    onSelect(key);
    const startX = event.clientX;
    const startY = event.clientY;
    const startBox = { ...display.layout[key] };

    const move = (moveEvent: globalThis.MouseEvent) => {
      const next = clampBox(
        snapBox({
          ...startBox,
          x: Math.round(startBox.x + (moveEvent.clientX - startX) / scale),
          y: Math.round(startBox.y + (moveEvent.clientY - startY) / scale),
        }),
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
      commitBox(key, next);
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

      <div className="layout-profile-tools">
        <Field label="Layout profile">
          <TextInput value={profileName} onChange={setProfileName} />
        </Field>
        <button className="secondary-button" type="button" onClick={() => onSaveLayoutProfile(profileName.trim() || "Layout")}>
          <Save size={16} />
          Save profile
        </button>
        <Field label="Restore">
          <Select value={selectedProfileKey} options={profileKeys} onChange={setSelectedProfileKey} />
        </Field>
        <button className="secondary-button" type="button" disabled={!selectedProfileKey} onClick={() => selectedProfileKey && onRestoreLayoutProfile(selectedProfileKey)}>
          <RefreshCw size={16} />
          Restore
        </button>
        <button className="danger-button" type="button" disabled={!selectedProfileKey} onClick={() => selectedProfileKey && onDeleteLayoutProfile(selectedProfileKey)}>
          <Trash2 size={16} />
        </button>
      </div>

      <div className="display-array">
        <div className="display-array-heading">
          <div>
            <strong>Displays</strong>
            <span>{displays.length} configured output{displays.length === 1 ? "" : "s"}</span>
          </div>
          <div className="display-array-actions">
            <button className="secondary-button" type="button" onClick={onUsbScan} disabled={usbBusy === "scan"}>
              <Cable size={16} />
              {usbBusy === "scan" ? "Scanning" : "Validate USB"}
            </button>
            <button className="secondary-button" type="button" onClick={onAddDisplay}>
              <Plus size={16} />
              Add display
            </button>
          </div>
        </div>
        {usbValidation ? (
          <div className={`usb-validation ${usbValidation.ok ? "is-ok" : "is-error"}`}>
            <span>{usbValidation.message}</span>
            {usbValidation.devices?.length ? (
              <span>{usbValidation.devices.map((device) => `${device.target ?? "usb"} ${device.vid}:${device.pid}${device.product ? ` ${device.product}` : ""}`).join(" | ")}</span>
            ) : null}
          </div>
        ) : null}
        {usbValidation?.devices?.length ? (
          <div className="display-array-actions">
            {usbValidation.devices.map((device, index) => (
              <button className="secondary-button" type="button" key={`${device.target ?? "usb"}-${device.vid}-${device.pid}-${device.bus ?? "b"}-${device.address ?? "a"}-${index}`} onClick={() => onAddUsbDisplay(device)}>
                <Plus size={16} />
                Add {device.target ?? "USB"} {device.bus != null && device.address != null ? `${device.bus}:${device.address}` : device.product || device.pid}
              </button>
            ))}
          </div>
        ) : null}
        <DisplayArrangement
          displays={displays}
          gridEnabled={gridEnabled}
          gridSize={gridSize}
          onDisplayChange={onDisplayChange}
        />
        <div className="display-list">
          {displays.map((item, index) => (
            <DisplayOutputRow
              key={item.id}
              display={item}
              index={index}
              canRemove={displays.length > 1}
              busy={usbBusy === item.id}
              onChange={(next) => onDisplayChange(item.id, next)}
              onIdentify={() => onIdentifyDisplay(item)}
              onRemove={() => onRemoveDisplay(item.id)}
            />
          ))}
        </div>
      </div>

      <div className={`layout-window-editor ${layoutExpanded ? "is-expanded" : ""}`}>
        <div className="layout-toolbar">
          <button className={`switch ${gridEnabled ? "is-on" : ""}`} type="button" onClick={() => setGridEnabled((value) => !value)} aria-pressed={gridEnabled}>
            <span />
            Grid snap
          </button>
          <Field label="Grid px">
            <NumberInput value={gridSize} onChange={(value) => setGridSize(clampNumber(value, 2, 64))} />
          </Field>
          <Field label="HUD">
            <Select value={addKind} options={options.map((item) => item.kind)} onChange={setAddKind} />
          </Field>
          <Field label="Theme">
            <Select value={activeLayoutTheme} options={layoutThemeKeys} onChange={onThemeChange} />
          </Field>
          <div className="layout-theme-swatches" aria-hidden="true">
            {layoutThemeCatalog[activeLayoutTheme].palette.slice(0, 6).map((color) => (
              <span key={color} style={{ backgroundColor: color }} />
            ))}
          </div>
          <ZoomControls
            className="layout-zoom-controls"
            label="Layout zoom"
            value={layoutZoom}
            min={layoutPreviewMinZoom}
            max={layoutPreviewMaxZoom}
            step={layoutPreviewZoomStep}
            onChange={setLayoutZoom}
          />
          <button className="secondary-button" type="button" onClick={() => onAdd(addKind)}>
            <Plus size={16} />
            Add HUD
          </button>
          <button className="secondary-button" type="button" onClick={() => setLayoutExpanded((value) => !value)}>
            {layoutExpanded ? <Minimize2 size={16} /> : <Maximize2 size={16} />}
            {layoutExpanded ? "Collapse" : "Expand"}
          </button>
        </div>

        <div className="layout-workbench">
          <div className="screen-preview-shell">
            <div className="screen-preview" style={{ width: frameWidth * scale, height: frameHeight * scale }}>
            {displays.map((item) => (
              <div
                key={item.id}
                className={`display-frame ${item.enabled ? "" : "is-disabled"}`}
                style={{
                  left: (item.x - bounds.x) * scale,
                  top: (item.y - bounds.y) * scale,
                  width: item.width * scale,
                  height: item.height * scale,
                }}
              >
                <span>{item.identify_number}</span>
              </div>
            ))}
            {gridEnabled ? (
              <div
                className="layout-grid"
                style={{
                  backgroundSize: `${gridSize * scale}px ${gridSize * scale}px`,
                }}
              />
            ) : null}
            {layoutItems.map((item) => {
              const current = item.box;
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
                    borderColor: item.option.tone,
                    backgroundColor: `${item.option.tone}24`,
                  }}
                  onMouseDown={(event) => dragStart(event, item.key)}
                  onKeyDown={(event) => {
                    if (event.key === "Enter" || event.key === " ") {
                      event.preventDefault();
                      onSelect(item.key);
                    }
                  }}
                >
                  <span className="layout-region-label">{item.option.label}</span>
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
              <Select value={activeKey ?? ""} options={layoutItems.map((item) => item.key)} onChange={(value) => onSelect(value as LayoutKey)} />
            </Field>
            <Field label="X">
              <NumberInput value={box.x} onChange={(value) => activeKey && commitBox(activeKey, { ...box, x: value })} />
            </Field>
            <Field label="Y">
              <NumberInput value={box.y} onChange={(value) => activeKey && commitBox(activeKey, { ...box, y: value })} />
            </Field>
            <Field label="Width">
              <NumberInput value={box.width} onChange={(value) => activeKey && commitBox(activeKey, { ...box, width: value })} />
            </Field>
            <Field label="Height">
              <NumberInput value={box.height} onChange={(value) => activeKey && commitBox(activeKey, { ...box, height: value })} />
            </Field>
            <button className="secondary-button" type="button" disabled={!activeKey} onClick={() => activeKey && onChange(activeKey, layoutBoxForNewWindow(layoutWindowKind(activeKey, box), frameWidth, frameHeight, display.layout))}>
              Reset selected
            </button>
            <button className="danger-button" type="button" disabled={!activeKey} onClick={() => activeKey && onRemove(activeKey)}>
              Remove selected
            </button>
            <button className="danger-button" type="button" onClick={onFactoryDefault}>
              Factory default
            </button>
          </div>
        </div>
      </div>
    </section>
  );
}

function DisplayArrangement({
  displays,
  gridEnabled,
  gridSize,
  onDisplayChange,
}: {
  displays: DisplayOutputConfig[];
  gridEnabled: boolean;
  gridSize: number;
  onDisplayChange: (displayId: string, next: DisplayOutputConfig) => void;
}) {
  const bounds = displayBounds(displays);
  const [zoom, setZoom] = useState(displayArrangementScale);
  const scale = zoom;
  const canvasWidth = Math.max(displayArrangementWidth, Math.round(bounds.width * scale + displayArrangementPadding * 2));
  const canvasHeight = Math.max(displayArrangementHeight, Math.round(bounds.height * scale + displayArrangementPadding * 2));

  function snapDisplay(value: number): number {
    if (!gridEnabled) return Math.round(value);
    const size = Math.max(1, gridSize);
    return Math.round(value / size) * size;
  }

  function dragDisplayStart(event: MouseEvent<HTMLDivElement>, display: DisplayOutputConfig) {
    event.preventDefault();
    const startX = event.clientX;
    const startY = event.clientY;
    const startDisplay = { ...display };

    const move = (moveEvent: globalThis.MouseEvent) => {
      onDisplayChange(display.id, {
        ...startDisplay,
        x: snapDisplay(startDisplay.x + (moveEvent.clientX - startX) / scale),
        y: snapDisplay(startDisplay.y + (moveEvent.clientY - startY) / scale),
      });
    };

    const up = () => {
      window.removeEventListener("mousemove", move);
      window.removeEventListener("mouseup", up);
    };

    window.addEventListener("mousemove", move);
    window.addEventListener("mouseup", up);
  }

  return (
    <div className="display-arrangement">
      <div className="display-arrangement-heading">
        <div>
          <strong>Display arrangement</strong>
          <span>Drag displays to set their relative position</span>
        </div>
        <ZoomControls
          label="Arrangement zoom"
          value={zoom}
          min={displayArrangementMinZoom}
          max={displayArrangementMaxZoom}
          step={displayArrangementZoomStep}
          onChange={setZoom}
        />
      </div>
      <div className="display-arrangement-shell">
        <div className="display-arrangement-canvas" style={{ width: canvasWidth, height: canvasHeight }}>
          {displays.map((display) => (
            <div
              key={display.id}
              className={`display-arrangement-item ${display.enabled ? "" : "is-disabled"}`}
              style={{
                left: Math.round((display.x - bounds.x) * scale + displayArrangementPadding),
                top: Math.round((display.y - bounds.y) * scale + displayArrangementPadding),
                width: Math.max(40, Math.round(display.width * scale)),
                height: Math.max(28, Math.round(display.height * scale)),
              }}
              onMouseDown={(event) => dragDisplayStart(event, display)}
              role="button"
              tabIndex={0}
              title={`${display.label}: ${display.x}, ${display.y}`}
            >
              <strong>{display.identify_number}</strong>
              <span>{display.label}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

function ZoomControls({
  label,
  value,
  min,
  max,
  step,
  className = "",
  onChange,
}: {
  label: string;
  value: number;
  min: number;
  max: number;
  step: number;
  className?: string;
  onChange: (value: number) => void;
}) {
  const percent = Math.round(value * 100);
  const decrease = () => onChange(clampZoom(value - step, min, max));
  const increase = () => onChange(clampZoom(value + step, min, max));

  return (
    <div className={`zoom-controls ${className}`} aria-label={label}>
      <button type="button" className="icon-button" onClick={decrease} disabled={value <= min} title="Zoom out" aria-label={`${label} out`}>
        <ZoomOut size={16} />
      </button>
      <span>{percent}%</span>
      <button type="button" className="icon-button" onClick={increase} disabled={value >= max} title="Zoom in" aria-label={`${label} in`}>
        <ZoomIn size={16} />
      </button>
    </div>
  );
}

function DisplayOutputRow({
  display,
  index,
  canRemove,
  busy,
  onChange,
  onIdentify,
  onRemove,
}: {
  display: DisplayOutputConfig;
  index: number;
  canRemove: boolean;
  busy: boolean;
  onChange: (next: DisplayOutputConfig) => void;
  onIdentify: () => void;
  onRemove: () => void;
}) {
  const usbTarget = normalizeUsbTarget(display.output);
  const usbConfig = usbTarget === "turzx" ? display.turzx ?? defaultTurzxDeviceConfig() : display.thermalright ?? defaultThermalrightDeviceConfig();
  const isWindowOutput = normalizeOutputTarget(display.output) === "window";
  const isKnownUsbDisplay = !isWindowOutput && knownUsbDisplay(usbConfig);
  const updateUsbConfig = (patch: Record<string, unknown>) => {
    if (usbTarget === "turzx") {
      onChange({ ...display, turzx: { ...(display.turzx ?? defaultTurzxDeviceConfig()), ...patch } });
      return;
    }
    onChange({ ...display, thermalright: { ...(display.thermalright ?? defaultThermalrightDeviceConfig()), ...patch } });
  };
  const changeOutput = (value: string) => {
    const target = normalizeOutputTarget(value);
    onChange(lockDisplayResolution({ ...display, output: target, target }));
  };
  return (
    <div className="display-output-row">
      <div className="display-badge">{display.identify_number || index + 1}</div>
      <Field label="Label">
        <TextInput value={display.label} onChange={(value) => onChange({ ...display, label: value })} />
      </Field>
      <Field label="Output">
        <Select value={display.output} options={["thermalright", "turzx", "window", "preview", "gif"]} onChange={changeOutput} />
      </Field>
      <Field label="X">
        <NumberInput value={display.x} onChange={(value) => onChange({ ...display, x: value })} />
      </Field>
      <Field label="Y">
        <NumberInput value={display.y} onChange={(value) => onChange({ ...display, y: value })} />
      </Field>
      {isWindowOutput ? (
        <>
          <Field label="Width">
            <NumberInput value={display.width} onChange={(value) => onChange({ ...display, width: Math.max(1, value), thermalright: syncThermalrightSize(display.thermalright, Math.max(1, value), display.height) })} />
          </Field>
          <Field label="Height">
            <NumberInput value={display.height} onChange={(value) => onChange({ ...display, height: Math.max(1, value), thermalright: syncThermalrightSize(display.thermalright, display.width, Math.max(1, value)) })} />
          </Field>
        </>
      ) : (
        <Field label="Resolution">
          <ReadOnlyValue value={`${display.width}x${display.height}`} />
        </Field>
      )}
      {!isWindowOutput ? (
        <Field label="Rotation">
          <Select value={String(display.rotation ?? 0)} options={["0", "90", "180", "270"]} onChange={(value) => onChange(lockDisplayResolution({ ...display, rotation: normalizeDisplayRotation(value) }))} />
        </Field>
      ) : null}
      {!isWindowOutput ? (
        <>
          <Field label="USB VID">
            <TextInput disabled={isKnownUsbDisplay} value={usbConfig.vid ?? (usbTarget === "turzx" ? "0x1a86" : "0x0416")} onChange={(value) => updateUsbConfig({ vid: value })} />
          </Field>
          <Field label="USB PID">
            <TextInput disabled={isKnownUsbDisplay} value={usbConfig.pid ?? (usbTarget === "turzx" ? "0x5722" : "0x5408")} onChange={(value) => updateUsbConfig({ pid: value })} />
          </Field>
          <Field label="Bus">
            <NumberInput disabled={isKnownUsbDisplay} value={Number(usbConfig.bus ?? 0)} onChange={(value) => updateUsbConfig({ bus: value || null })} />
          </Field>
          <Field label="Address">
            <NumberInput disabled={isKnownUsbDisplay} value={Number(usbConfig.address ?? 0)} onChange={(value) => updateUsbConfig({ address: value || null })} />
          </Field>
          <Field label="Serial">
            <TextInput disabled={isKnownUsbDisplay} value={usbConfig.serial_number ?? ""} onChange={(value) => updateUsbConfig({ serial_number: value })} />
          </Field>
        </>
      ) : null}
      <Field label="Enabled">
        <Switch checked={display.enabled} onChange={(value) => onChange({ ...display, enabled: value })} />
      </Field>
      <div className="display-row-actions">
        <button className="secondary-button" type="button" onClick={onIdentify} disabled={busy}>
          <Monitor size={16} />
          {busy ? "Sending" : "Identify"}
        </button>
        <button className="danger-button" type="button" disabled={!canRemove} onClick={onRemove}>
          <Trash2 size={16} />
        </button>
      </div>
    </div>
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

function RuntimePanel({
  status,
  autostart,
  busy,
  onCheck,
  onPreview,
  onStartRun,
  onStopRun,
  onStartWindow,
  onStopWindow,
  onInstallAutostart,
  onRemoveAutostart,
}: {
  status: RuntimeStatus | null;
  autostart: RuntimeAutostartStatus | null;
  busy: string | null;
  onCheck: () => void;
  onPreview: () => void;
  onStartRun: () => void;
  onStopRun: () => void;
  onStartWindow: () => void;
  onStopWindow: () => void;
  onInstallAutostart: () => void;
  onRemoveAutostart: () => void;
}) {
  const logs = status?.logs ?? [];
  return (
    <section id="runtime" className="wide-panel runtime-panel">
      <div className="section-heading">
        <Terminal size={20} />
        <div>
          <h2>Runtime</h2>
          <p>{status?.running ? `Runtime running · pid ${status.pid ?? "-"}` : "Runtime stopped"}</p>
        </div>
      </div>
      <div className="runtime-actions">
        <button className="primary-button" type="button" disabled={busy !== null} onClick={onCheck}>
          <Terminal size={16} />
          Check
        </button>
        <button className="primary-button" type="button" disabled={busy !== null} onClick={onPreview}>
          <FileImage size={16} />
          Preview
        </button>
        <button className="secondary-button" type="button" disabled={busy !== null || Boolean(status?.running)} onClick={onStartRun}>
          <Play size={16} />
          Start run
        </button>
        <button className="secondary-button" type="button" disabled={busy !== null || !status?.running} onClick={onStopRun}>
          <Square size={16} />
          Stop run
        </button>
        <button className="secondary-button" type="button" disabled={busy !== null || Boolean(status?.running)} onClick={onStartWindow}>
          <Play size={16} />
          Start window
        </button>
        <button className="secondary-button" type="button" disabled={busy !== null || !status?.running} onClick={onStopWindow}>
          <Square size={16} />
          Stop window
        </button>
      </div>
      <div className="runtime-autostart">
        <div>
          <strong>Autostart</strong>
          <span>
            {autostart?.supported
              ? autostart.installed
                ? `Installed${autostart.loaded === false ? " · not loaded" : autostart.state ? ` · ${autostart.state}` : ""} · ${autostart.path}`
                : "Not installed"
              : `Unsupported on ${autostart?.platform ?? "this OS"}`}
          </span>
          {autostart?.last_exit_code ? <span>Last exit: {autostart.last_exit_code}</span> : null}
          {autostart?.message ? <span>{autostart.message}</span> : null}
        </div>
        <div className="runtime-actions">
          <button className="secondary-button" type="button" disabled={busy !== null || !autostart?.supported || autostart?.installed} onClick={onInstallAutostart}>
            <Save size={16} />
            Install autostart
          </button>
          <button className="danger-button" type="button" disabled={busy !== null || !autostart?.installed} onClick={onRemoveAutostart}>
            <Trash2 size={16} />
            Remove autostart
          </button>
        </div>
      </div>
      <pre className="runtime-log">{logs.length ? logs.join("\n") : "No runtime logs yet."}</pre>
    </section>
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

function SettingsTabs({
  tabs,
  activeKey,
  onSelect,
  children,
}: {
  tabs: SettingsTabItem[];
  activeKey: string;
  onSelect: (key: string) => void;
  children: ReactNode;
}) {
  if (!tabs.length) {
    return <div className="empty-plugin-tab">Enable a plugin or integration to edit settings.</div>;
  }
  const activeTab = tabs.find((tab) => tab.key === activeKey);
  return (
    <div className="plugin-tabs">
      <div className="plugin-tab-list" role="tablist" aria-label="Plugin and integration settings">
        {tabs.map((tab) => {
          const Icon = tab.icon;
          const selected = tab.key === activeKey;
          return (
            <button
              key={tab.key}
              role="tab"
              aria-selected={selected}
              className={`${selected ? "is-active" : ""} ${tab.tone === "integration" ? "is-integration" : ""}`}
              type="button"
              onClick={() => onSelect(tab.key)}
            >
              <Icon size={16} />
              <span>{tab.label}</span>
            </button>
          );
        })}
      </div>
      <div className={`plugin-tab-panel ${activeTab?.tone === "integration" ? "is-integration-panel" : ""}`} role="tabpanel">
        {children}
      </div>
    </div>
  );
}

function IntegrationPanel({
  activeKey,
  config,
  discordPeople,
  discordPeopleConfig,
  onMutate,
}: {
  activeKey: string;
  config: RuntimeConfig;
  discordPeople: Array<[string, DiscordPersonConfig]>;
  discordPeopleConfig: { max_recent: number; people: Record<string, DiscordPersonConfig> };
  onMutate: (mutator: (draft: RuntimeConfig) => void) => void;
}) {
  const [kiteBusy, setKiteBusy] = useState<string | null>(null);
  const [kiteResult, setKiteResult] = useState<KiteActionResult | null>(null);
  const [kiteTokenDraft, setKiteTokenDraft] = useState("");
  const [kiteZoomSecretDraft, setKiteZoomSecretDraft] = useState("");

  async function triggerKiteAction(action: "status" | "install" | "secrets" | "deploy") {
    setKiteBusy(action);
    try {
      const result =
        action === "status"
          ? await loadKiteStatus()
          : action === "secrets"
            ? await configureKiteSecrets(kiteTokenDraft, kiteZoomSecretDraft)
            : await runKiteAction(action);
      setKiteResult(result);
      if (action === "secrets" && result.ok) {
        setKiteTokenDraft("");
        setKiteZoomSecretDraft("");
      }
      if (action === "deploy" && result.ws_url) {
        onMutate((draft) => void (draft.integrations.integrations.kite.ws_url = result.ws_url || ""));
      }
    } catch (error) {
      setKiteResult({
        ok: false,
        message: error instanceof Error ? error.message : String(error),
      });
    } finally {
      setKiteBusy(null);
    }
  }

  if (activeKey === "github") {
    return (
      <GithubIntegrationPanel config={config} onMutate={onMutate} />
    );
  }

  if (activeKey === "weather") {
    return (
      <Panel title="Weather" icon={CloudSun} subtitle="Weather-like mood source">
        <Field label="Provider">
          <Select
            value={config.integrations.integrations.weather.provider}
            options={["open_meteo", "wttr_in", "openweathermap"]}
            onChange={(value) => onMutate((draft) => void (draft.integrations.integrations.weather.provider = value))}
          />
        </Field>
        <Field label="City">
          <TextInput
            value={config.integrations.integrations.weather.city}
            onChange={(value) => onMutate((draft) => void (draft.integrations.integrations.weather.city = value))}
          />
        </Field>
        <Field label="Country code">
          <TextInput
            value={config.integrations.integrations.weather.country_code}
            onChange={(value) => onMutate((draft) => void (draft.integrations.integrations.weather.country_code = value.toUpperCase()))}
          />
        </Field>
        <Field label="Poll seconds">
          <NumberInput
            value={config.integrations.integrations.weather.poll_seconds}
            onChange={(value) => onMutate((draft) => void (draft.integrations.integrations.weather.poll_seconds = value))}
          />
        </Field>
        <Field label="Timeout seconds">
          <NumberInput
            value={config.integrations.integrations.weather.timeout_seconds}
            onChange={(value) => onMutate((draft) => void (draft.integrations.integrations.weather.timeout_seconds = value))}
          />
        </Field>
        <Field label="API key env">
          <TextInput
            value={config.integrations.integrations.weather.api_key_env}
            onChange={(value) => onMutate((draft) => void (draft.integrations.integrations.weather.api_key_env = value))}
          />
        </Field>
      </Panel>
    );
  }

  if (activeKey === "pc_stats") {
    return (
      <Panel title="PC Stats" icon={Cpu} subtitle="Local machine metrics for layout windows">
        <Field label="Fields">
          <TextInput
            value={config.integrations.integrations.pc_stats.fields.join(", ")}
            onChange={(value) => onMutate((draft) => void (draft.integrations.integrations.pc_stats.fields = csv(value)))}
          />
        </Field>
        <Field label="Poll seconds">
          <NumberInput
            value={config.integrations.integrations.pc_stats.poll_seconds}
            onChange={(value) => onMutate((draft) => void (draft.integrations.integrations.pc_stats.poll_seconds = clampNumber(value, 1, 300)))}
          />
        </Field>
        <Field label="Disk path">
          <TextInput
            value={config.integrations.integrations.pc_stats.disk_path}
            onChange={(value) => onMutate((draft) => void (draft.integrations.integrations.pc_stats.disk_path = value || "/"))}
          />
        </Field>
        <Field label="Top processes">
          <NumberInput
            value={config.integrations.integrations.pc_stats.top_process_count}
            onChange={(value) => onMutate((draft) => void (draft.integrations.integrations.pc_stats.top_process_count = clampNumber(value, 1, 5)))}
          />
        </Field>
        <div className="field field-wide">
          <span>Available fields</span>
          <span className="empty-note">cpu, ram, top_ram_app, temperature, gpu, disk, uptime, battery, load</span>
        </div>
      </Panel>
    );
  }

  if (activeKey === "clickup") {
    return (
      <Panel title="ClickUp" icon={Check} subtitle="Assigned dated tasks for the task HUD">
        <Field label="Token env">
          <TextInput
            value={config.integrations.integrations.clickup.token_env}
            onChange={(value) => onMutate((draft) => void (draft.integrations.integrations.clickup.token_env = value))}
          />
        </Field>
        <Field label="Workspace ID">
          <TextInput
            value={config.integrations.integrations.clickup.team_id}
            onChange={(value) => onMutate((draft) => void (draft.integrations.integrations.clickup.team_id = digits(value)))}
          />
        </Field>
        <Field label="Workspace IDs">
          <TextInput
            value={(config.integrations.integrations.clickup.team_ids ?? []).join(", ")}
            onChange={(value) => onMutate((draft) => void (draft.integrations.integrations.clickup.team_ids = commaList(value).map(digits)))}
          />
        </Field>
        <Field label="Assignee ID">
          <TextInput
            value={config.integrations.integrations.clickup.assignee_id}
            onChange={(value) => onMutate((draft) => void (draft.integrations.integrations.clickup.assignee_id = digits(value)))}
          />
        </Field>
        <Field label="Assignee IDs">
          <TextInput
            value={(config.integrations.integrations.clickup.assignee_ids ?? []).join(", ")}
            onChange={(value) => onMutate((draft) => void (draft.integrations.integrations.clickup.assignee_ids = commaList(value).map(digits)))}
          />
        </Field>
        <Field label="Poll seconds">
          <NumberInput
            value={config.integrations.integrations.clickup.poll_seconds}
            onChange={(value) => onMutate((draft) => void (draft.integrations.integrations.clickup.poll_seconds = clampNumber(value, 30, 3600)))}
          />
        </Field>
        <Field label="Max tasks">
          <NumberInput
            value={config.integrations.integrations.clickup.max_tasks}
            onChange={(value) => onMutate((draft) => void (draft.integrations.integrations.clickup.max_tasks = clampNumber(value, 1, 12)))}
          />
        </Field>
        <Field label="Due within days">
          <NumberInput
            value={config.integrations.integrations.clickup.due_within_days}
            onChange={(value) => onMutate((draft) => void (draft.integrations.integrations.clickup.due_within_days = clampNumber(value, 1, 90)))}
          />
        </Field>
        <Field label="Overdue">
          <Switch
            checked={config.integrations.integrations.clickup.include_overdue}
            onChange={(value) => onMutate((draft) => void (draft.integrations.integrations.clickup.include_overdue = value))}
          />
        </Field>
        <Field label="No due date">
          <Switch
            checked={config.integrations.integrations.clickup.include_undated}
            onChange={(value) => onMutate((draft) => void (draft.integrations.integrations.clickup.include_undated = value))}
          />
        </Field>
        <Field label="Subtasks">
          <Switch
            checked={config.integrations.integrations.clickup.include_subtasks}
            onChange={(value) => onMutate((draft) => void (draft.integrations.integrations.clickup.include_subtasks = value))}
          />
        </Field>
        <Field label="Closed">
          <Switch
            checked={config.integrations.integrations.clickup.include_closed}
            onChange={(value) => onMutate((draft) => void (draft.integrations.integrations.clickup.include_closed = value))}
          />
        </Field>
      </Panel>
    );
  }

  if (activeKey === "todoist") {
    return (
      <Panel title="Todoist" icon={Check} subtitle="Active personal tasks for the shared task HUDs">
        <Field label="Token env">
          <TextInput
            value={config.integrations.integrations.todoist.token_env}
            onChange={(value) => onMutate((draft) => void (draft.integrations.integrations.todoist.token_env = value))}
          />
        </Field>
        <Field label="Project IDs">
          <TextInput
            value={config.integrations.integrations.todoist.project_ids.join(", ")}
            onChange={(value) => onMutate((draft) => void (draft.integrations.integrations.todoist.project_ids = commaList(value).map(digits)))}
          />
        </Field>
        <Field label="Section IDs">
          <TextInput
            value={config.integrations.integrations.todoist.section_ids.join(", ")}
            onChange={(value) => onMutate((draft) => void (draft.integrations.integrations.todoist.section_ids = commaList(value).map(digits)))}
          />
        </Field>
        <Field label="Filter">
          <TextInput
            value={config.integrations.integrations.todoist.filter}
            onChange={(value) => onMutate((draft) => void (draft.integrations.integrations.todoist.filter = value))}
          />
        </Field>
        <Field label="Poll seconds">
          <NumberInput
            value={config.integrations.integrations.todoist.poll_seconds}
            onChange={(value) => onMutate((draft) => void (draft.integrations.integrations.todoist.poll_seconds = clampNumber(value, 30, 3600)))}
          />
        </Field>
        <Field label="Max tasks">
          <NumberInput
            value={config.integrations.integrations.todoist.max_tasks}
            onChange={(value) => onMutate((draft) => void (draft.integrations.integrations.todoist.max_tasks = clampNumber(value, 1, 24)))}
          />
        </Field>
        <Field label="Due within days">
          <NumberInput
            value={config.integrations.integrations.todoist.due_within_days}
            onChange={(value) => onMutate((draft) => void (draft.integrations.integrations.todoist.due_within_days = clampNumber(value, 1, 90)))}
          />
        </Field>
        <Field label="Overdue">
          <Switch
            checked={config.integrations.integrations.todoist.include_overdue}
            onChange={(value) => onMutate((draft) => void (draft.integrations.integrations.todoist.include_overdue = value))}
          />
        </Field>
        <Field label="No due date">
          <Switch
            checked={config.integrations.integrations.todoist.include_undated}
            onChange={(value) => onMutate((draft) => void (draft.integrations.integrations.todoist.include_undated = value))}
          />
        </Field>
      </Panel>
    );
  }

  if (activeKey === "media") {
    return (
      <Panel title="Media" icon={Music2} subtitle="Local now-playing state for Spotify and YouTube">
        <Field label="Providers">
          <TextInput
            value={config.integrations.integrations.media.providers.join(", ")}
            onChange={(value) => onMutate((draft) => void (draft.integrations.integrations.media.providers = commaList(value)))}
          />
        </Field>
        <Field label="Poll seconds">
          <NumberInput
            value={config.integrations.integrations.media.poll_seconds}
            onChange={(value) => onMutate((draft) => void (draft.integrations.integrations.media.poll_seconds = clampNumber(value, 2, 300)))}
          />
        </Field>
        <Field label="Timeout seconds">
          <NumberInput
            value={config.integrations.integrations.media.timeout_seconds}
            onChange={(value) => onMutate((draft) => void (draft.integrations.integrations.media.timeout_seconds = clampNumber(value, 1, 10)))}
          />
        </Field>
        <div className="field field-wide">
          <span>Available providers</span>
          <span className="empty-note">spotify, youtube_browser</span>
        </div>
      </Panel>
    );
  }

  if (activeKey === "google_calendar") {
    return (
      <Panel title="Google Calendar" icon={CalendarDays} subtitle="Meeting encounters from shared ICS URLs">
        <Field label="Google ICS URLs">
          <TextArea
            value={config.integrations.integrations.google_calendar.ics_urls.join("\n")}
            onChange={(value) => onMutate((draft) => void (draft.integrations.integrations.google_calendar.ics_urls = lines(value)))}
          />
        </Field>
      </Panel>
    );
  }

  if (activeKey === "ics") {
    return (
      <Panel title="ICS" icon={CalendarDays} subtitle="Meeting encounters from local calendar files">
        <Field label="Local ICS paths">
          <TextArea
            value={config.integrations.integrations.ics.paths.join("\n")}
            onChange={(value) => onMutate((draft) => void (draft.integrations.integrations.ics.paths = lines(value)))}
          />
        </Field>
      </Panel>
    );
  }

  if (activeKey === "discord") {
    return (
      <DiscordIntegrationPanel
        config={config}
        discordPeople={discordPeople}
        discordPeopleConfig={discordPeopleConfig}
        onMutate={onMutate}
      />
    );
  }

  if (activeKey === "kite") {
    return (
      <Panel title="PixelOpsKite" icon={Cable} subtitle="Webhook relay stream for local Pixel Ops">
        <Field label="WebSocket URL">
          <TextInput
            value={config.integrations.integrations.kite.ws_url}
            onChange={(value) => onMutate((draft) => void (draft.integrations.integrations.kite.ws_url = value))}
          />
        </Field>
        <Field label="Token env">
          <TextInput
            value={config.integrations.integrations.kite.token_env}
            onChange={(value) => onMutate((draft) => void (draft.integrations.integrations.kite.token_env = value))}
          />
        </Field>
        <Field label="Reconnect seconds">
          <NumberInput
            value={config.integrations.integrations.kite.reconnect_seconds}
            onChange={(value) => onMutate((draft) => void (draft.integrations.integrations.kite.reconnect_seconds = clampNumber(value, 1, 120)))}
          />
        </Field>
        <Field label="Max companions">
          <NumberInput
            value={config.integrations.integrations.kite.max_companions}
            onChange={(value) => onMutate((draft) => void (draft.integrations.integrations.kite.max_companions = clampNumber(value, 0, 30)))}
          />
        </Field>
        <Field label="Zoom focus user">
          <TextInput
            value={config.integrations.integrations.kite.zoom.focus_user_id}
            onChange={(value) => onMutate((draft) => void (draft.integrations.integrations.kite.zoom.focus_user_id = value))}
          />
        </Field>
        <Field label="Zoom companions">
          <NumberInput
            value={config.integrations.integrations.kite.zoom.max_companions}
            onChange={(value) => onMutate((draft) => void (draft.integrations.integrations.kite.zoom.max_companions = clampNumber(value, 0, 30)))}
          />
        </Field>
        <Field label="Kite token">
          <PasswordInput value={kiteTokenDraft} onChange={setKiteTokenDraft} />
        </Field>
        <Field label="Zoom webhook token">
          <PasswordInput value={kiteZoomSecretDraft} onChange={setKiteZoomSecretDraft} />
        </Field>
        <div className="field field-wide">
          <span>IaC actions</span>
          <div className="runtime-actions">
            <button className="secondary-button" type="button" disabled={kiteBusy !== null} onClick={() => void triggerKiteAction("status")}>
              <Terminal size={15} />
              Check
            </button>
            <button className="secondary-button" type="button" disabled={kiteBusy !== null} onClick={() => void triggerKiteAction("install")}>
              <RefreshCw size={15} />
              Install deps
            </button>
            <button
              className="secondary-button"
              type="button"
              disabled={kiteBusy !== null || (!kiteTokenDraft.trim() && !kiteZoomSecretDraft.trim())}
              onClick={() => void triggerKiteAction("secrets")}
            >
              <Save size={15} />
              Push secrets
            </button>
            <button className="primary-button" type="button" disabled={kiteBusy !== null} onClick={() => void triggerKiteAction("deploy")}>
              <Play size={15} />
              Deploy Kite
            </button>
          </div>
        </div>
        {kiteResult ? (
          <div className="field field-wide">
            <span>{kiteResult.ok ? "Kite ready" : "Kite issue"}</span>
            <pre className="runtime-log">
              {[
                kiteResult.message,
                kiteResult.worker_url ? `Worker URL: ${kiteResult.worker_url}` : "",
                kiteResult.ws_url ? `WebSocket URL: ${kiteResult.ws_url}` : "",
                kiteResult.files ? `Files: ${JSON.stringify(kiteResult.files, null, 2)}` : "",
                kiteResult.local_token_set !== undefined ? `Local token: ${kiteResult.local_token_set ? "set" : "missing"}` : "",
                kiteResult.stdout || "",
                kiteResult.stderr || "",
              ]
                .filter(Boolean)
                .join("\n")}
            </pre>
          </div>
        ) : null}
      </Panel>
    );
  }

  if (activeKey === "zoom") {
    return (
      <Panel title="Zoom" icon={Users} subtitle="Poll live meeting participants as ambient companions">
        <Field label="Account ID env">
          <TextInput
            value={config.integrations.integrations.zoom.account_id_env}
            onChange={(value) => onMutate((draft) => void (draft.integrations.integrations.zoom.account_id_env = value))}
          />
        </Field>
        <Field label="Client ID env">
          <TextInput
            value={config.integrations.integrations.zoom.client_id_env}
            onChange={(value) => onMutate((draft) => void (draft.integrations.integrations.zoom.client_id_env = value))}
          />
        </Field>
        <Field label="Client secret env">
          <TextInput
            value={config.integrations.integrations.zoom.client_secret_env}
            onChange={(value) => onMutate((draft) => void (draft.integrations.integrations.zoom.client_secret_env = value))}
          />
        </Field>
        <Field label="Focus user ID">
          <TextInput
            value={config.integrations.integrations.zoom.focus_user_id}
            onChange={(value) => onMutate((draft) => void (draft.integrations.integrations.zoom.focus_user_id = value))}
          />
        </Field>
        <Field label="Max companions">
          <NumberInput
            value={config.integrations.integrations.zoom.max_companions}
            onChange={(value) => onMutate((draft) => void (draft.integrations.integrations.zoom.max_companions = clampNumber(value, 0, 30)))}
          />
        </Field>
        <Field label="Poll seconds">
          <NumberInput
            value={config.integrations.integrations.zoom.poll_seconds}
            onChange={(value) => onMutate((draft) => void (draft.integrations.integrations.zoom.poll_seconds = clampNumber(value, 10, 300)))}
          />
        </Field>
        <Field label="Page size">
          <NumberInput
            value={config.integrations.integrations.zoom.page_size}
            onChange={(value) => onMutate((draft) => void (draft.integrations.integrations.zoom.page_size = clampNumber(value, 1, 300)))}
          />
        </Field>
        <Field label="Timeout seconds">
          <NumberInput
            value={config.integrations.integrations.zoom.timeout_seconds}
            onChange={(value) => onMutate((draft) => void (draft.integrations.integrations.zoom.timeout_seconds = clampNumber(value, 1, 30)))}
          />
        </Field>
      </Panel>
    );
  }

  if (activeKey === "ai_usage") {
    return (
      <Panel title="AI Usage" icon={Activity} subtitle="Ambient provider gauges">
        <Field label="Providers">
          <TextInput
            value={config.integrations.integrations.ai_usage.providers.join(", ")}
            onChange={(value) => onMutate((draft) => void (draft.integrations.integrations.ai_usage.providers = csv(value)))}
          />
        </Field>
        <Field label="Monthly budget USD">
          <NumberInput
            value={config.integrations.integrations.ai_usage.openai_api_monthly_budget_usd}
            onChange={(value) => onMutate((draft) => void (draft.integrations.integrations.ai_usage.openai_api_monthly_budget_usd = value))}
          />
        </Field>
        <Field label="Thresholds">
          <TextInput
            value={config.integrations.integrations.ai_usage.thresholds.join(", ")}
            onChange={(value) => onMutate((draft) => void (draft.integrations.integrations.ai_usage.thresholds = csv(value).map(Number).filter(Number.isFinite)))}
          />
        </Field>
      </Panel>
    );
  }

  if (activeKey === "slack") {
    const channelCount = Object.keys(config.integrations.integrations.slack.channels ?? {}).length;
    return (
      <Panel title="Slack" icon={Bot} subtitle="Socket Mode signals normalized into ambient activity">
        <Field label="App token env">
          <TextInput
            value={config.integrations.integrations.slack.app_token_env}
            onChange={(value) => onMutate((draft) => void (draft.integrations.integrations.slack.app_token_env = value))}
          />
        </Field>
        <Field label="Bot token env">
          <TextInput
            value={config.integrations.integrations.slack.bot_token_env}
            onChange={(value) => onMutate((draft) => void (draft.integrations.integrations.slack.bot_token_env = value))}
          />
        </Field>
        <Field label="Bot user ID">
          <TextInput
            value={config.integrations.integrations.slack.bot_user_id}
            onChange={(value) => onMutate((draft) => void (draft.integrations.integrations.slack.bot_user_id = value))}
          />
        </Field>
        <Field label="Reconnect seconds">
          <NumberInput
            value={config.integrations.integrations.slack.socket_reconnect_seconds}
            onChange={(value) => onMutate((draft) => void (draft.integrations.integrations.slack.socket_reconnect_seconds = clampNumber(value, 1, 120)))}
          />
        </Field>
        <Field label="Activity window">
          <NumberInput
            value={config.integrations.integrations.slack.activity_window_seconds}
            onChange={(value) => onMutate((draft) => void (draft.integrations.integrations.slack.activity_window_seconds = clampNumber(value, 10, 3600)))}
          />
        </Field>
        <Field label="Activity threshold">
          <NumberInput
            value={config.integrations.integrations.slack.activity_threshold}
            onChange={(value) => onMutate((draft) => void (draft.integrations.integrations.slack.activity_threshold = clampNumber(value, 1, 200)))}
          />
        </Field>
        <Field label="Cooldown seconds">
          <NumberInput
            value={config.integrations.integrations.slack.activity_cooldown_seconds}
            onChange={(value) => onMutate((draft) => void (draft.integrations.integrations.slack.activity_cooldown_seconds = clampNumber(value, 0, 7200)))}
          />
        </Field>
        <Field label="Summary window">
          <NumberInput
            value={config.integrations.integrations.slack.summary_window_seconds}
            onChange={(value) => onMutate((draft) => void (draft.integrations.integrations.slack.summary_window_seconds = clampNumber(value, 60, 7200)))}
          />
        </Field>
        <div className="field field-wide">
          <span>Channel rules</span>
          <span className="empty-note">{channelCount} configured channel rules. JSON editing can stay in integrations config for now.</span>
        </div>
      </Panel>
    );
  }

  return (
    <div className="empty-plugin-tab empty-provider-tab">
      <Code2 size={18} />
      <span>No editable runtime settings are registered for this integration yet.</span>
    </div>
  );
}

function DiscordIntegrationPanel({
  config,
  discordPeople,
  discordPeopleConfig,
  onMutate,
}: {
  config: RuntimeConfig;
  discordPeople: Array<[string, DiscordPersonConfig]>;
  discordPeopleConfig: { max_recent: number; people: Record<string, DiscordPersonConfig> };
  onMutate: (mutator: (draft: RuntimeConfig) => void) => void;
}) {
  const discord = config.integrations.integrations.discord;
  const [botTokenDraft, setBotTokenDraft] = useState("");
  const [oauthLogin, setOauthLogin] = useState<DiscordOAuthStartResponse | null>(null);
  const [guilds, setGuilds] = useState<DiscordGuildOption[]>([]);
  const [viewer, setViewer] = useState("");
  const [busy, setBusy] = useState(false);
  const [polling, setPolling] = useState(false);
  const [message, setMessage] = useState("");

  async function refreshProfile(nextMessage?: string) {
    const result = await loadDiscordProfile(discord.user_token_env);
    setViewer(result.user.global_name || result.user.username || result.user.id);
    setGuilds(result.guilds);
    onMutate((draft) => void (draft.integrations.integrations.discord.focus_user_id = result.user.id));
    setMessage(nextMessage ?? `${result.guilds.length} servers available for ${result.user.username}.`);
  }

  async function loadServers() {
    setBusy(true);
    setMessage("");
    try {
      await refreshProfile();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : String(error));
    } finally {
      setBusy(false);
    }
  }

  async function connectWithBotToken() {
    setBusy(true);
    setMessage("");
    try {
      if (botTokenDraft.trim()) {
        await saveDiscordBotToken(discord.bot_token_env, botTokenDraft.trim());
        setBotTokenDraft("");
      }
      setMessage(`Bot token saved to ${discord.bot_token_env}.`);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : String(error));
    } finally {
      setBusy(false);
    }
  }

  async function startLogin() {
    setBusy(true);
    setMessage("");
    try {
      const result = await startDiscordOAuth(discord.client_id, discord.client_secret_env, discord.user_token_env);
      setOauthLogin(result);
      window.open(result.authorize_url, "pixelops-discord-oauth", "width=720,height=820");
      setMessage("Waiting for Discord authorization.");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : String(error));
    } finally {
      setBusy(false);
    }
  }

  useEffect(() => {
    if (!oauthLogin) return;
    const login = oauthLogin;
    let stopped = false;
    let timeoutId: number | undefined;

    async function poll() {
      setPolling(true);
      try {
        const result = await pollDiscordOAuthStatus(login.state);
        if (stopped) return;
        if (result.status === "authorized") {
          setOauthLogin(null);
          const user = result.user;
          setViewer(user?.global_name || user?.username || user?.id || "");
          setGuilds(result.guilds ?? []);
          if (user?.id) {
            onMutate((draft) => void (draft.integrations.integrations.discord.focus_user_id = user.id));
          }
          setMessage(`Discord authorized${user?.username ? ` as ${user.username}` : ""}.`);
          return;
        }
        if (result.status === "error") {
          setOauthLogin(null);
          setMessage(result.message ?? "Discord authorization failed.");
          return;
        }
        timeoutId = window.setTimeout(() => void poll(), 1500);
      } catch (error) {
        if (!stopped) setMessage(error instanceof Error ? error.message : String(error));
      } finally {
        if (!stopped) setPolling(false);
      }
    }

    timeoutId = window.setTimeout(() => void poll(), 1500);
    return () => {
      stopped = true;
      if (timeoutId !== undefined) window.clearTimeout(timeoutId);
    };
  }, [oauthLogin, onMutate]);

  function selectGuild(guildId: string) {
    onMutate((draft) => void (draft.integrations.integrations.discord.guild_id = guildId));
  }

  return (
    <Panel title="Discord" icon={Bot} subtitle="Gateway voice companions and local account link">
      <Field label="Client ID">
        <TextInput
          value={discord.client_id}
          onChange={(value) => onMutate((draft) => void (draft.integrations.integrations.discord.client_id = digits(value)))}
        />
      </Field>
      <Field label="Client secret env">
        <TextInput
          value={discord.client_secret_env}
          onChange={(value) => onMutate((draft) => void (draft.integrations.integrations.discord.client_secret_env = value || "PIXEL_OPS_DISCORD_CLIENT_SECRET"))}
        />
      </Field>
      <Field label="User token env">
        <TextInput
          value={discord.user_token_env}
          onChange={(value) => onMutate((draft) => void (draft.integrations.integrations.discord.user_token_env = value || "PIXEL_OPS_DISCORD_USER_TOKEN"))}
        />
      </Field>
      <div className="field field-wide github-connect-row">
        <span>Discord login</span>
        <button className="primary-button" type="button" disabled={busy || polling || !discord.client_id} onClick={() => void startLogin()}>
          <Bot size={15} />
          {busy ? "Starting" : "Login by Discord"}
        </button>
        {oauthLogin ? (
          <div className="github-device-card">
            <a className="secondary-button" href={oauthLogin.authorize_url} target="_blank" rel="noreferrer">
              Open Discord
            </a>
            <span className="empty-note">{polling ? "Waiting for authorization..." : "Authorization started."}</span>
          </div>
        ) : null}
        {viewer ? <span className="empty-note">Signed in as {viewer}</span> : null}
        {message ? <span className="empty-note">{message}</span> : null}
      </div>
      <Field label="Bot token env">
        <TextInput
          value={discord.bot_token_env}
          onChange={(value) => onMutate((draft) => void (draft.integrations.integrations.discord.bot_token_env = value || "PIXEL_OPS_DISCORD_BOT_TOKEN"))}
        />
      </Field>
      <Field label="Bot token">
        <PasswordInput value={botTokenDraft} onChange={setBotTokenDraft} />
      </Field>
      <div className="field field-wide github-connect-row">
        <span>Manual fallback</span>
        <button className="secondary-button" type="button" disabled={busy || polling} onClick={() => void connectWithBotToken()}>
          <Bot size={15} />
          Save bot token
        </button>
        <button className="secondary-button" type="button" disabled={busy || polling} onClick={() => void loadServers()}>
          <RefreshCw size={15} />
          Load servers
        </button>
      </div>
      {guilds.length ? (
        <div className="field field-wide github-repo-list">
          <span>Available servers</span>
          <div>
            {guilds.map((guild) => (
              <label key={guild.id} className="github-repo-option">
                <input type="radio" checked={discord.guild_id === guild.id} onChange={() => selectGuild(guild.id)} />
                <span>{guild.name}</span>
                {guild.owner ? <small>owner</small> : null}
              </label>
            ))}
          </div>
        </div>
      ) : null}
      <Field label="Server ID">
        <TextInput
          value={discord.guild_id}
          onChange={(value) => onMutate((draft) => void (draft.integrations.integrations.discord.guild_id = digits(value)))}
        />
      </Field>
      <Field label="My user ID">
        <TextInput
          value={discord.focus_user_id}
          onChange={(value) => onMutate((draft) => void (draft.integrations.integrations.discord.focus_user_id = digits(value)))}
        />
      </Field>
      <Field label="Companions">
        <NumberInput
          value={discord.max_companions}
          onChange={(value) => onMutate((draft) => void (draft.integrations.integrations.discord.max_companions = clampNumber(value, 0, 30)))}
        />
      </Field>
      <Field label="Reconnect seconds">
        <NumberInput
          value={discord.gateway_reconnect_seconds}
          onChange={(value) => onMutate((draft) => void (draft.integrations.integrations.discord.gateway_reconnect_seconds = clampNumber(value, 1, 120)))}
        />
      </Field>
      <Field label="Remember nicks">
        <NumberInput
          value={discordPeopleConfig.max_recent}
          onChange={(value) =>
            onMutate((draft) => {
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
  );
}

function GithubIntegrationPanel({ config, onMutate }: { config: RuntimeConfig; onMutate: (mutator: (draft: RuntimeConfig) => void) => void }) {
  const github = config.integrations.integrations.github;
  const [tokenDraft, setTokenDraft] = useState("");
  const [deviceLogin, setDeviceLogin] = useState<GitHubDeviceStartResponse | null>(null);
  const [repos, setRepos] = useState<GitHubRepoOption[]>([]);
  const [viewer, setViewer] = useState("");
  const [busy, setBusy] = useState(false);
  const [polling, setPolling] = useState(false);
  const [message, setMessage] = useState("");

  async function refreshRepos(nextMessage?: string) {
    const result = await loadGithubRepos(github.token_env);
    setViewer(result.viewer);
    setRepos(result.repos);
    setMessage(nextMessage ?? `${result.repos.length} repositories available for ${result.viewer}.`);
  }

  async function connectWithToken() {
    setBusy(true);
    setMessage("");
    try {
      if (tokenDraft.trim()) {
        await saveGithubToken(github.token_env, tokenDraft.trim());
        setTokenDraft("");
      }
      await refreshRepos();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : String(error));
    } finally {
      setBusy(false);
    }
  }

  async function startDeviceLogin() {
    setBusy(true);
    setMessage("");
    try {
      const result = await startGithubDeviceLogin(github.client_id);
      setDeviceLogin(result);
      setMessage(`Enter ${result.user_code} on GitHub to authorize Pixel OPs.`);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : String(error));
    } finally {
      setBusy(false);
    }
  }

  useEffect(() => {
    if (!deviceLogin) return;
    const login = deviceLogin;
    let stopped = false;
    let timeoutId: number | undefined;

    async function poll() {
      setPolling(true);
      try {
        const result = await pollGithubDeviceLogin(github.client_id, login.device_code, github.token_env);
        if (stopped) return;
        if (result.status === "authorized") {
          setDeviceLogin(null);
          await refreshRepos("GitHub authorized. Repository list refreshed.");
          return;
        }
        const interval = Math.max(result.interval ?? login.interval, login.interval, 5);
        setMessage(result.message ?? "Waiting for GitHub authorization.");
        timeoutId = window.setTimeout(() => void poll(), interval * 1000);
      } catch (error) {
        if (!stopped) setMessage(error instanceof Error ? error.message : String(error));
      } finally {
        if (!stopped) setPolling(false);
      }
    }

    timeoutId = window.setTimeout(() => void poll(), login.interval * 1000);
    return () => {
      stopped = true;
      if (timeoutId !== undefined) window.clearTimeout(timeoutId);
    };
  }, [deviceLogin, github.client_id, github.token_env]);

  function toggleRepo(repo: string, checked: boolean) {
    onMutate((draft) => {
      const current = new Set(draft.integrations.integrations.github.repos);
      if (checked) {
        current.add(repo);
      } else {
        current.delete(repo);
      }
      draft.integrations.integrations.github.repos = [...current].sort();
    });
  }

  const selected = new Set(github.repos);

  return (
    <Panel title="GitHub" icon={Github} subtitle="Pull requests in the compact HUD">
      <Field label="Client ID">
        <TextInput
          value={github.client_id}
          onChange={(value) => onMutate((draft) => void (draft.integrations.integrations.github.client_id = value))}
        />
      </Field>
      <Field label="Token env">
        <TextInput
          value={github.token_env}
          onChange={(value) => onMutate((draft) => void (draft.integrations.integrations.github.token_env = value || "PIXEL_OPS_GITHUB_TOKEN"))}
        />
      </Field>
      <div className="field field-wide github-connect-row">
        <span>GitHub login</span>
        <button className="primary-button" type="button" disabled={busy || polling || !github.client_id} onClick={() => void startDeviceLogin()}>
          <Github size={15} />
          {busy ? "Starting" : "Login by GitHub"}
        </button>
        {deviceLogin ? (
          <div className="github-device-card">
            <strong>{deviceLogin.user_code}</strong>
            <a className="secondary-button" href={deviceLogin.verification_uri} target="_blank" rel="noreferrer">
              Open GitHub
            </a>
            <span className="empty-note">{polling ? "Waiting for authorization..." : "Authorization started."}</span>
          </div>
        ) : null}
        {viewer ? <span className="empty-note">Signed in as {viewer}</span> : null}
        {message ? <span className="empty-note">{message}</span> : null}
      </div>
      <Field label="Manual token">
        <PasswordInput value={tokenDraft} onChange={setTokenDraft} />
      </Field>
      <div className="field field-wide github-connect-row">
        <span>Manual fallback</span>
        <button className="secondary-button" type="button" disabled={busy || polling} onClick={() => void connectWithToken()}>
          <Github size={15} />
          Load repos
        </button>
      </div>
      {repos.length ? (
        <div className="field field-wide github-repo-list">
          <span>Available repos</span>
          <div>
            {repos.map((repo) => (
              <label key={repo.full_name} className="github-repo-option">
                <input type="checkbox" checked={selected.has(repo.full_name)} onChange={(event) => toggleRepo(repo.full_name, event.target.checked)} />
                <span>{repo.full_name}</span>
                {repo.private ? <small>private</small> : null}
              </label>
            ))}
          </div>
        </div>
      ) : null}
      <Field label="Repos">
        <TextArea
          value={github.repos.join("\n")}
          onChange={(value) => onMutate((draft) => void (draft.integrations.integrations.github.repos = lines(value)))}
        />
      </Field>
      <Field label="Poll seconds">
        <NumberInput
          value={github.poll_seconds}
          onChange={(value) => onMutate((draft) => void (draft.integrations.integrations.github.poll_seconds = value))}
        />
      </Field>
      <Field label="Max pull requests">
        <NumberInput
          value={github.max_pull_requests}
          onChange={(value) => onMutate((draft) => void (draft.integrations.integrations.github.max_pull_requests = value))}
        />
      </Field>
      <Field label="Deploy signals">
        <Switch
          checked={github.fetch_deployments}
          onChange={(value) => onMutate((draft) => void (draft.integrations.integrations.github.fetch_deployments = value))}
        />
      </Field>
      <Field label="Deploy workflows">
        <TextArea
          value={github.deployment_workflows.join("\n")}
          onChange={(value) => onMutate((draft) => void (draft.integrations.integrations.github.deployment_workflows = lines(value)))}
        />
      </Field>
    </Panel>
  );
}

function PokemonPluginPanels({
  game,
  pokemon,
  aiSelector,
  config,
  discordPeople,
  spriteVariants,
  onMutate,
}: {
  game: PokemonGameConfig;
  pokemon: PokemonDataConfig;
  aiSelector: PokemonAiSelectorConfig;
  config: RuntimeConfig;
  discordPeople: Array<[string, DiscordPersonConfig]>;
  spriteVariants: number[];
  onMutate: (mutator: (draft: RuntimeConfig) => void) => void;
}) {
  const [activePanel, setActivePanel] = useState<PokemonPanelKey>("scene");
  const tabs: Array<{ key: PokemonPanelKey; label: string; icon: IconComponent }> = [
    { key: "scene", label: "Scene", icon: Code2 },
    { key: "companions", label: "Companions", icon: Users },
    { key: "ai", label: "AI Selector", icon: Bot },
    { key: "data", label: "Data", icon: Cpu },
  ];

  return (
    <div className="plugin-subtabs">
      <div className="plugin-tab-list plugin-subtab-list" role="tablist" aria-label="Pokemon settings">
        {tabs.map((tab) => {
          const Icon = tab.icon;
          const selected = tab.key === activePanel;
          return (
            <button
              key={tab.key}
              role="tab"
              aria-selected={selected}
              className={selected ? "is-active" : ""}
              type="button"
              onClick={() => setActivePanel(tab.key)}
            >
              <Icon size={16} />
              <span>{tab.label}</span>
            </button>
          );
        })}
      </div>
      <div className="plugin-subtab-panel" role="tabpanel">
        {activePanel === "scene" ? (
          <Panel title="Pokemon Scene" icon={Code2} subtitle="World loop and HUD tuning">
            <Field label="Game FPS">
              <NumberInput value={game.fps} onChange={(value) => onMutate((draft) => void (draft.game!.game.fps = value))} />
            </Field>
            <Field label="Map switch seconds">
              <NumberInput
                value={game.map_switch_seconds}
                onChange={(value) => onMutate((draft) => void (draft.game!.game.map_switch_seconds = value))}
              />
            </Field>
            <Field label="Route speed px">
              <NumberInput value={game.route_speed_px} onChange={(value) => onMutate((draft) => void (draft.game!.game.route_speed_px = value))} />
            </Field>
            <Field label="HUD height">
              <NumberInput value={game.hud_height} onChange={(value) => onMutate((draft) => void (draft.game!.game.hud_height = value))} />
            </Field>
            <Field label="Static background">
              <Switch checked={game.static_background} onChange={(value) => onMutate((draft) => void (draft.game!.game.static_background = value))} />
            </Field>
            <Field label="Mock events">
              <Switch checked={game.events.mock_events} onChange={(value) => onMutate((draft) => void (draft.game!.game.events.mock_events = value))} />
            </Field>
          </Panel>
        ) : null}

        {activePanel === "companions" ? (
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
                      spriteVariants={spriteVariants}
                      onSprite={(sprite_variant) =>
                        onMutate((draft) => {
                          const current = draft.pokemon_companions!.companions.discord[userId] ?? { sprite_variant: null, label: "" };
                          draft.pokemon_companions!.companions.discord[userId] = { ...current, sprite_variant };
                        })
                      }
                      onLabel={(label) =>
                        onMutate((draft) => {
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
        ) : null}

        {activePanel === "ai" ? (
          <Panel title="Pokemon AI Selector" icon={Bot} subtitle="Throttled Pokemon-specific AI selection">
            <Field label="Selector enabled">
              <Switch checked={aiSelector.enabled} onChange={(value) => onMutate((draft) => void (draft.game!.game.events.ai_selector.enabled = value))} />
            </Field>
            <Field label="Async">
              <Switch checked={aiSelector.async} onChange={(value) => onMutate((draft) => void (draft.game!.game.events.ai_selector.async = value))} />
            </Field>
            <Field label="Ambient calls">
              <Switch checked={aiSelector.ambient} onChange={(value) => onMutate((draft) => void (draft.game!.game.events.ai_selector.ambient = value))} />
            </Field>
            <Field label="Candidate limit">
              <NumberInput
                value={aiSelector.candidate_limit}
                onChange={(value) => onMutate((draft) => void (draft.game!.game.events.ai_selector.candidate_limit = value))}
              />
            </Field>
            <Field label="Cooldown seconds">
              <NumberInput
                value={aiSelector.throttle.cooldown_seconds}
                onChange={(value) => onMutate((draft) => void (draft.game!.game.events.ai_selector.throttle.cooldown_seconds = value))}
              />
            </Field>
            <Field label="Requests per window">
              <NumberInput
                value={aiSelector.throttle.max_requests_per_window}
                onChange={(value) => onMutate((draft) => void (draft.game!.game.events.ai_selector.throttle.max_requests_per_window = value))}
              />
            </Field>
          </Panel>
        ) : null}

        {activePanel === "data" ? (
          <Panel title="Pokemon Data" icon={Cpu} subtitle="PokeAPI, sprite cache and generation bounds">
            <Field label="Generation limit">
              <NumberInput value={pokemon.generation_limit} onChange={(value) => onMutate((draft) => void (draft.pokemon!.pokemon.generation_limit = value))} />
            </Field>
            <Field label="Sprite style">
              <Select
                value={pokemon.sprite_style}
                options={["animated", "front_default", "official-artwork"]}
                onChange={(value) => onMutate((draft) => void (draft.pokemon!.pokemon.sprite_style = value))}
              />
            </Field>
            <Field label="Lazy download">
              <Switch checked={pokemon.lazy_download} onChange={(value) => onMutate((draft) => void (draft.pokemon!.pokemon.lazy_download = value))} />
            </Field>
            <Field label="Offline mode">
              <Switch checked={pokemon.offline} onChange={(value) => onMutate((draft) => void (draft.pokemon!.pokemon.offline = value))} />
            </Field>
            <Field label="Network timeout">
              <NumberInput
                value={pokemon.network_timeout_seconds}
                onChange={(value) => onMutate((draft) => void (draft.pokemon!.pokemon.network_timeout_seconds = value))}
              />
            </Field>
            <Field label="Cache dir">
              <TextInput value={pokemon.cache_dir} onChange={(value) => onMutate((draft) => void (draft.pokemon!.pokemon.cache_dir = value))} />
            </Field>
          </Panel>
        ) : null}
      </div>
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

function TextInput({ value, onChange, disabled = false }: { value: string; onChange: (value: string) => void; disabled?: boolean }) {
  return <input value={value} disabled={disabled} onChange={(event) => onChange(event.target.value)} />;
}

function PasswordInput({ value, onChange }: { value: string; onChange: (value: string) => void }) {
  return <input type="password" value={value} autoComplete="off" onChange={(event) => onChange(event.target.value)} />;
}

function NumberInput({ value, onChange, disabled = false }: { value: number; onChange: (value: number) => void; disabled?: boolean }) {
  return <input type="number" value={value} disabled={disabled} onChange={(event) => onChange(Number(event.target.value))} />;
}

function ReadOnlyValue({ value }: { value: string }) {
  return <div className="readonly-value">{value}</div>;
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

function MovementAreaEditor({
  maps,
  movement,
  onChange,
  expanded = false,
}: {
  maps: PokemonMapOption[];
  movement: MovementConfig;
  onChange: (movement: MovementConfig) => void;
  expanded?: boolean;
}) {
  const [layer, setLayer] = useState<MovementLayer>("walkable");
  const [selectedMapKey, setSelectedMapKey] = useState("");
  const [selectedIndex, setSelectedIndex] = useState<number | null>(null);
  const [gridEnabled, setGridEnabled] = useState(false);
  const [gridSize, setGridSize] = useState(16);
  const [zoomPercent, setZoomPercent] = useState(expanded ? 300 : 100);
  const imageRef = useRef<HTMLImageElement | null>(null);
  const activeMap = maps.find((item) => item.key === selectedMapKey) ?? maps[0];
  const mapKey = activeMap?.key ?? "";
  const rects = movementRectsForLayer(movement, layer).filter((rect) => rect.map === mapKey);

  useEffect(() => {
    if (!selectedMapKey && maps[0]) {
      setSelectedMapKey(maps[0].key);
    }
  }, [maps, selectedMapKey]);

  function commit(nextRects: MovementRect[]) {
    const next = JSON.parse(JSON.stringify(movement)) as MovementConfig;
    const existing = movementRectsForLayer(next, layer).filter((rect) => rect.map !== mapKey);
    setMovementRectsForLayer(next, layer, [...existing, ...nextRects]);
    onChange(next);
  }

  function snap(value: number): number {
    if (!gridEnabled) return Math.round(value);
    const size = Math.max(1, gridSize);
    return Math.round(value / size) * size;
  }

  function snapRect(rect: MovementRect): MovementRect {
    if (!gridEnabled) return rect;
    return {
      ...rect,
      x: snap(rect.x),
      y: snap(rect.y),
      w: Math.max(gridSize, snap(rect.w)),
      h: Math.max(gridSize, snap(rect.h)),
    };
  }

  function imagePoint(event: MouseEvent<HTMLElement>) {
    const image = imageRef.current;
    if (!image || !activeMap) return null;
    const bounds = image.getBoundingClientRect();
    const scaleX = activeMap.width / bounds.width;
    const scaleY = activeMap.height / bounds.height;
    return {
      x: Math.round((event.clientX - bounds.left) * scaleX),
      y: Math.round((event.clientY - bounds.top) * scaleY),
      scaleX,
      scaleY,
    };
  }

  function addRect(event: MouseEvent<HTMLDivElement>) {
    if ((event.target as HTMLElement).closest(".movement-rect")) return;
    const point = imagePoint(event);
    if (!point || !activeMap) return;
    const nextRect = clampMovementRect(
      snapRect({ map: activeMap.key, x: point.x - 30, y: point.y - 18, w: 60, h: 36 }),
      activeMap.width,
      activeMap.height,
    );
    commit([...rects, nextRect]);
    setSelectedIndex(rects.length);
  }

  function dragRect(event: MouseEvent<HTMLDivElement>, index: number) {
    event.preventDefault();
    event.stopPropagation();
    if (!activeMap) return;
    setSelectedIndex(index);
    const point = imagePoint(event);
    if (!point) return;
    const start = rects[index];
    const startPoint = point;
    const move = (moveEvent: globalThis.MouseEvent) => {
      const image = imageRef.current;
      if (!image) return;
      const bounds = image.getBoundingClientRect();
      const x = Math.round((moveEvent.clientX - bounds.left) * (activeMap.width / bounds.width));
      const y = Math.round((moveEvent.clientY - bounds.top) * (activeMap.height / bounds.height));
      const next = rects.map((rect, rectIndex) =>
        rectIndex === index
          ? clampMovementRect(snapRect({ ...rect, x: start.x + x - startPoint.x, y: start.y + y - startPoint.y }), activeMap.width, activeMap.height)
          : rect,
      );
      commit(next);
    };
    const up = () => {
      window.removeEventListener("mousemove", move);
      window.removeEventListener("mouseup", up);
    };
    window.addEventListener("mousemove", move);
    window.addEventListener("mouseup", up);
  }

  function resizeRect(event: MouseEvent<HTMLDivElement>, index: number, direction: ResizeDirection) {
    event.preventDefault();
    event.stopPropagation();
    if (!activeMap) return;
    setSelectedIndex(index);
    const point = imagePoint(event);
    if (!point) return;
    const start = rects[index];
    const startPoint = point;
    const move = (moveEvent: globalThis.MouseEvent) => {
      const image = imageRef.current;
      if (!image) return;
      const bounds = image.getBoundingClientRect();
      const x = Math.round((moveEvent.clientX - bounds.left) * (activeMap.width / bounds.width));
      const y = Math.round((moveEvent.clientY - bounds.top) * (activeMap.height / bounds.height));
      const dx = x - startPoint.x;
      const dy = y - startPoint.y;
      const nextRect = { ...start };
      if (direction.includes("e")) nextRect.w = start.w + dx;
      if (direction.includes("s")) nextRect.h = start.h + dy;
      if (direction.includes("w")) {
        nextRect.x = start.x + dx;
        nextRect.w = start.w - dx;
      }
      if (direction.includes("n")) {
        nextRect.y = start.y + dy;
        nextRect.h = start.h - dy;
      }
      commit(
        rects.map((rect, rectIndex) =>
          rectIndex === index ? clampMovementRect(snapRect(nextRect), activeMap.width, activeMap.height) : rect,
        ),
      );
    };
    const up = () => {
      window.removeEventListener("mousemove", move);
      window.removeEventListener("mouseup", up);
    };
    window.addEventListener("mousemove", move);
    window.addEventListener("mouseup", up);
  }

  function selectedRect(): MovementRect | null {
    return selectedIndex == null ? null : rects[selectedIndex] ?? null;
  }

  if (!activeMap) {
    return <span className="empty-note">No Pokemon maps found.</span>;
  }

  const selected = selectedRect();
  const scale = Math.max(25, Math.min(500, zoomPercent)) / 100;

  return (
    <div className={`movement-editor ${expanded ? "movement-editor-expanded" : ""}`}>
      <div className="movement-toolbar">
        <Select value={mapKey} options={maps.map((item) => item.key)} onChange={(value) => { setSelectedMapKey(value); setSelectedIndex(null); }} />
        <Select value={layer} options={["walkable", "blocked"]} onChange={(value) => { setLayer(value as MovementLayer); setSelectedIndex(null); }} />
        <button className={`switch ${gridEnabled ? "is-on" : ""}`} type="button" onClick={() => setGridEnabled((value) => !value)} aria-pressed={gridEnabled}>
          <span />
          Grid
        </button>
        <Field label="Grid px">
          <NumberInput value={gridSize} onChange={(value) => setGridSize(clampNumber(value, 2, 128))} />
        </Field>
        <Field label="Zoom %">
          <NumberInput value={zoomPercent} onChange={(value) => setZoomPercent(clampNumber(value, 25, 500))} />
        </Field>
        <button className="secondary-button" type="button" onClick={() => onChange({ ...movement, debug_overlay: !movement.debug_overlay })}>
          {movement.debug_overlay ? "Hide overlay" : "Show overlay"}
        </button>
      </div>
      <div className="movement-map-shell">
        <div className="movement-map" style={{ width: activeMap.width * scale }} onMouseDown={addRect}>
          <img ref={imageRef} src={activeMap.url} alt="" style={{ width: activeMap.width * scale }} />
          {gridEnabled ? (
            <div
              className="movement-grid"
              style={{
                backgroundSize: `${gridSize * scale}px ${gridSize * scale}px`,
              }}
            />
          ) : null}
          {rects.map((rect, index) => (
            <div
              key={`${rect.map}-${index}`}
              className={`movement-rect movement-rect-${layer} ${selectedIndex === index ? "is-selected" : ""}`}
              style={{ left: rect.x * scale, top: rect.y * scale, width: rect.w * scale, height: rect.h * scale }}
              onMouseDown={(event) => dragRect(event, index)}
            >
              <span>{layer}</span>
              {selectedIndex === index
                ? resizeDirections.map((direction) => (
                    <div
                      key={direction}
                      className={`resize-handle resize-handle-${direction}`}
                      role="presentation"
                      title="Resize"
                      onMouseDown={(event) => resizeRect(event, index, direction)}
                    >
                      {direction.length === 2 ? <MoveDiagonal2 size={10} strokeWidth={3} /> : null}
                    </div>
                  ))
                : null}
            </div>
          ))}
        </div>
      </div>
      {selected ? (
        <div className="movement-fields">
          {(["x", "y", "w", "h"] as const).map((key) => (
            <Field key={key} label={key.toUpperCase()}>
              <NumberInput
                value={selected[key]}
                onChange={(value) => {
                  const next = rects.map((rect, index) =>
                    index === selectedIndex ? clampMovementRect(snapRect({ ...rect, [key]: value }), activeMap.width, activeMap.height) : rect,
                  );
                  commit(next);
                }}
              />
            </Field>
          ))}
          <button
            className="secondary-button"
            type="button"
            onClick={() => {
              commit(rects.filter((_, index) => index !== selectedIndex));
              setSelectedIndex(null);
            }}
          >
            Delete selected
          </button>
        </div>
      ) : (
        <span className="empty-note">Click the map to add a rectangle. Drag rectangles to move them.</span>
      )}
    </div>
  );
}

function CompanionSpriteRow({
  userId,
  person,
  visual,
  spriteVariants,
  onSprite,
  onLabel,
}: {
  userId: string;
  person: DiscordPersonConfig;
  visual?: { sprite_variant: number | null; label: string };
  spriteVariants: number[];
  onSprite: (spriteVariant: number | null) => void;
  onLabel: (label: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const nicknames = person.nicknames.length ? person.nicknames.join(", ") : userId;
  const selected = visual?.sprite_variant ?? null;
  const variants = spriteVariants.length ? spriteVariants : fallbackDiscordSpriteVariants;
  const activeVariant = selected ?? variants[Math.abs(hashString(userId)) % variants.length];
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
              {variants.map((variant) => (
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

function movementRectsForLayer(movement: MovementConfig, layer: MovementLayer): MovementRect[] {
  if (layer === "blocked") {
    return movement.blocked.source_rects;
  }
  return movement.walkable.source_rects;
}

function setMovementRectsForLayer(movement: MovementConfig, layer: MovementLayer, rects: MovementRect[]) {
  if (layer === "blocked") {
    movement.blocked.source_rects = rects;
  } else {
    movement.walkable.source_rects = rects;
  }
}

function clampMovementRect(rect: MovementRect, width: number, height: number): MovementRect {
  const w = Math.max(4, Math.min(width, Math.round(rect.w)));
  const h = Math.max(4, Math.min(height, Math.round(rect.h)));
  return {
    ...rect,
    x: Math.max(0, Math.min(width - w, Math.round(rect.x))),
    y: Math.max(0, Math.min(height - h, Math.round(rect.y))),
    w,
    h,
  };
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
  display.device.thermalright = display.device.thermalright ?? defaultThermalrightDeviceConfig();
  ensureDisplayOutputs(display);
  display.layout_theme = layoutThemeCatalog[display.layout_theme ?? "default"] ? (display.layout_theme ?? "default") : "default";
  if (!display.layout || typeof display.layout !== "object") {
    display.layout = defaultLayoutFor(display.width, display.height);
  }
  display.gamification = display.gamification ?? {
    max_hp: 100,
    meeting_cost: 8,
    task_delivered_cost: 5,
    base_recovery_per_hour: 0,
    companion_recovery_per_hour: 4,
    max_companion_bonus: 5,
  };
  next.integrations.integrations.github.client_id = next.integrations.integrations.github.client_id ?? "Iv23litC8XR0gzcGAiaG";
  next.integrations.integrations.github.token_env = next.integrations.integrations.github.token_env ?? "PIXEL_OPS_GITHUB_TOKEN";
  next.integrations.integrations.github.repos = next.integrations.integrations.github.repos ?? [];
  next.integrations.integrations.github.poll_seconds = next.integrations.integrations.github.poll_seconds ?? 300;
  next.integrations.integrations.github.max_pull_requests = next.integrations.integrations.github.max_pull_requests ?? 4;
  next.integrations.integrations.github.fetch_pull_requests = next.integrations.integrations.github.fetch_pull_requests ?? 20;
  next.integrations.integrations.github.fetch_deployments = next.integrations.integrations.github.fetch_deployments ?? true;
  next.integrations.integrations.github.deployment_workflows = next.integrations.integrations.github.deployment_workflows ?? [];
  next.integrations.integrations.github.startup_lookback_seconds = next.integrations.integrations.github.startup_lookback_seconds ?? 3600;
  next.integrations.integrations.github.timeout_seconds = next.integrations.integrations.github.timeout_seconds ?? 20;
  next.integrations.integrations.kite = next.integrations.integrations.kite ?? {
    enabled: false,
    ws_url: "",
    token_env: "PIXEL_OPS_KITE_TOKEN",
    reconnect_seconds: 10,
    max_companions: 8,
    zoom: {
      focus_user_id: "",
      max_companions: 8,
    },
  };
  next.integrations.integrations.kite.ws_url = next.integrations.integrations.kite.ws_url ?? "";
  next.integrations.integrations.kite.token_env = next.integrations.integrations.kite.token_env ?? "PIXEL_OPS_KITE_TOKEN";
  next.integrations.integrations.kite.reconnect_seconds = next.integrations.integrations.kite.reconnect_seconds ?? 10;
  next.integrations.integrations.kite.max_companions = next.integrations.integrations.kite.max_companions ?? 8;
  next.integrations.integrations.kite.zoom = next.integrations.integrations.kite.zoom ?? { focus_user_id: "", max_companions: 8 };
  next.integrations.integrations.kite.zoom.focus_user_id = next.integrations.integrations.kite.zoom.focus_user_id ?? "";
  next.integrations.integrations.kite.zoom.max_companions = next.integrations.integrations.kite.zoom.max_companions ?? 8;
  next.integrations.integrations.slack.app_token_env = next.integrations.integrations.slack.app_token_env ?? "PIXEL_OPS_SLACK_APP_TOKEN";
  next.integrations.integrations.slack.bot_token_env = next.integrations.integrations.slack.bot_token_env ?? "PIXEL_OPS_SLACK_BOT_TOKEN";
  next.integrations.integrations.slack.bot_user_id = next.integrations.integrations.slack.bot_user_id ?? "";
  next.integrations.integrations.slack.socket_reconnect_seconds = next.integrations.integrations.slack.socket_reconnect_seconds ?? 10;
  next.integrations.integrations.slack.activity_window_seconds = next.integrations.integrations.slack.activity_window_seconds ?? 120;
  next.integrations.integrations.slack.activity_threshold = next.integrations.integrations.slack.activity_threshold ?? 5;
  next.integrations.integrations.slack.activity_cooldown_seconds = next.integrations.integrations.slack.activity_cooldown_seconds ?? 300;
  next.integrations.integrations.slack.summary_window_seconds = next.integrations.integrations.slack.summary_window_seconds ?? 900;
  next.integrations.integrations.slack.channels = next.integrations.integrations.slack.channels ?? {};
  next.integrations.integrations.weather.provider = next.integrations.integrations.weather.provider ?? "open_meteo";
  next.integrations.integrations.weather.timeout_seconds = next.integrations.integrations.weather.timeout_seconds ?? 8;
  next.integrations.integrations.weather.api_key_env = next.integrations.integrations.weather.api_key_env ?? "OPENWEATHERMAP_API_KEY";
  next.integrations.integrations.pc_stats = next.integrations.integrations.pc_stats ?? {
    enabled: false,
    fields: ["cpu", "ram", "top_ram_app", "temperature", "gpu", "disk", "uptime"],
    poll_seconds: 5,
    top_process_count: 1,
    disk_path: "/",
  };
  next.integrations.integrations.pc_stats.fields = next.integrations.integrations.pc_stats.fields ?? ["cpu", "ram", "top_ram_app", "temperature", "gpu", "disk", "uptime"];
  next.integrations.integrations.pc_stats.poll_seconds = next.integrations.integrations.pc_stats.poll_seconds ?? 5;
  next.integrations.integrations.pc_stats.top_process_count = next.integrations.integrations.pc_stats.top_process_count ?? 1;
  next.integrations.integrations.pc_stats.disk_path = next.integrations.integrations.pc_stats.disk_path ?? "/";
  next.integrations.integrations.clickup = next.integrations.integrations.clickup ?? {
    enabled: false,
    token_env: "PIXEL_OPS_CLICKUP_TOKEN",
    team_id: "",
    team_ids: [],
    assignee_id: "",
    assignee_ids: [],
    poll_seconds: 120,
    max_tasks: 5,
    due_within_days: 14,
    include_overdue: true,
    include_undated: true,
    include_subtasks: true,
    include_closed: false,
    timeout_seconds: 10,
  };
  next.integrations.integrations.clickup.token_env = next.integrations.integrations.clickup.token_env ?? "PIXEL_OPS_CLICKUP_TOKEN";
  next.integrations.integrations.clickup.team_id = next.integrations.integrations.clickup.team_id ?? "";
  next.integrations.integrations.clickup.team_ids = next.integrations.integrations.clickup.team_ids ?? [];
  next.integrations.integrations.clickup.assignee_id = next.integrations.integrations.clickup.assignee_id ?? "";
  next.integrations.integrations.clickup.assignee_ids = next.integrations.integrations.clickup.assignee_ids ?? [];
  next.integrations.integrations.clickup.poll_seconds = next.integrations.integrations.clickup.poll_seconds ?? 120;
  next.integrations.integrations.clickup.max_tasks = next.integrations.integrations.clickup.max_tasks ?? 5;
  next.integrations.integrations.clickup.due_within_days = next.integrations.integrations.clickup.due_within_days ?? 14;
  next.integrations.integrations.clickup.include_overdue = next.integrations.integrations.clickup.include_overdue ?? true;
  next.integrations.integrations.clickup.include_undated = next.integrations.integrations.clickup.include_undated ?? true;
  next.integrations.integrations.clickup.include_subtasks = next.integrations.integrations.clickup.include_subtasks ?? true;
  next.integrations.integrations.clickup.include_closed = next.integrations.integrations.clickup.include_closed ?? false;
  next.integrations.integrations.clickup.timeout_seconds = next.integrations.integrations.clickup.timeout_seconds ?? 10;
  next.integrations.integrations.todoist = next.integrations.integrations.todoist ?? {
    enabled: false,
    token_env: "PIXEL_OPS_TODOIST_TOKEN",
    project_ids: [],
    section_ids: [],
    filter: "",
    poll_seconds: 120,
    max_tasks: 12,
    due_within_days: 14,
    include_overdue: true,
    include_undated: true,
    timeout_seconds: 10,
  };
  next.integrations.integrations.todoist.token_env = next.integrations.integrations.todoist.token_env ?? "PIXEL_OPS_TODOIST_TOKEN";
  next.integrations.integrations.todoist.project_ids = next.integrations.integrations.todoist.project_ids ?? [];
  next.integrations.integrations.todoist.section_ids = next.integrations.integrations.todoist.section_ids ?? [];
  next.integrations.integrations.todoist.filter = next.integrations.integrations.todoist.filter ?? "";
  next.integrations.integrations.todoist.poll_seconds = next.integrations.integrations.todoist.poll_seconds ?? 120;
  next.integrations.integrations.todoist.max_tasks = next.integrations.integrations.todoist.max_tasks ?? 12;
  next.integrations.integrations.todoist.due_within_days = next.integrations.integrations.todoist.due_within_days ?? 14;
  next.integrations.integrations.todoist.include_overdue = next.integrations.integrations.todoist.include_overdue ?? true;
  next.integrations.integrations.todoist.include_undated = next.integrations.integrations.todoist.include_undated ?? true;
  next.integrations.integrations.todoist.timeout_seconds = next.integrations.integrations.todoist.timeout_seconds ?? 10;
  next.integrations.integrations.media = next.integrations.integrations.media ?? {
    enabled: false,
    providers: ["spotify"],
    poll_seconds: 10,
    timeout_seconds: 2,
  };
  next.integrations.integrations.media.providers = next.integrations.integrations.media.providers ?? ["spotify"];
  next.integrations.integrations.media.poll_seconds = next.integrations.integrations.media.poll_seconds ?? 10;
  next.integrations.integrations.media.timeout_seconds = next.integrations.integrations.media.timeout_seconds ?? 2;
  next.integrations.integrations.discord = next.integrations.integrations.discord ?? {
    enabled: false,
    bot_token_env: "PIXEL_OPS_DISCORD_BOT_TOKEN",
    client_id: "",
    client_secret_env: "PIXEL_OPS_DISCORD_CLIENT_SECRET",
    user_token_env: "PIXEL_OPS_DISCORD_USER_TOKEN",
    guild_id: "",
    focus_user_id: "",
    max_companions: 5,
    gateway_reconnect_seconds: 10,
  };
  next.integrations.integrations.discord.bot_token_env = next.integrations.integrations.discord.bot_token_env ?? "PIXEL_OPS_DISCORD_BOT_TOKEN";
  next.integrations.integrations.discord.client_id = next.integrations.integrations.discord.client_id ?? "";
  next.integrations.integrations.discord.client_secret_env = next.integrations.integrations.discord.client_secret_env ?? "PIXEL_OPS_DISCORD_CLIENT_SECRET";
  next.integrations.integrations.discord.user_token_env = next.integrations.integrations.discord.user_token_env ?? "PIXEL_OPS_DISCORD_USER_TOKEN";
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
  if (next.game) {
    const legacyMovement = next.game.game.movement as MovementConfig & {
      ash?: { source_rects?: MovementRect[]; avoid_source_rects?: MovementRect[] };
      companions?: { source_rects?: MovementRect[]; avoid_source_rects?: MovementRect[] };
    };
    next.game.game.movement = {
      debug_overlay: Boolean(next.game.game.movement?.debug_overlay),
      walkable: {
        source_rects: [
          ...(legacyMovement.walkable?.source_rects ?? []),
          ...(legacyMovement.ash?.source_rects ?? []),
          ...(legacyMovement.companions?.source_rects ?? []),
        ],
        avoid_source_rects: [
          ...(legacyMovement.walkable?.avoid_source_rects ?? []),
          ...(legacyMovement.ash?.avoid_source_rects ?? []),
          ...(legacyMovement.companions?.avoid_source_rects ?? []),
        ],
      },
      blocked: {
        source_rects: next.game.game.movement?.blocked?.source_rects ?? [],
      },
    };
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

function commaList(value: string): string[] {
  return value
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
}

function titleize(value: string): string {
  return value
    .split(/[_-]+/)
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

function clampNumber(value: number, min: number, max: number): number {
  if (!Number.isFinite(value)) {
    return min;
  }
  return Math.max(min, Math.min(max, Math.round(value)));
}

function clampZoom(value: number, min: number, max: number): number {
  if (!Number.isFinite(value)) {
    return min;
  }
  return Number(Math.max(min, Math.min(max, value)).toFixed(2));
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
  if (target === "thermalright") {
    display.orientation = "vertical";
    display.fps = Math.max(display.fps || 10, 10);
    display.device.thermalright = display.device.thermalright ?? defaultThermalrightDeviceConfig();
  }
}

function defaultThermalrightDeviceConfig(): NonNullable<DisplayOutputConfig["thermalright"]> {
  return {
    vid: "0x0416",
    pid: "0x5408",
    timeout_ms: 5000,
    jpeg_quality: 85,
    image_width: 1920,
    image_height: 462,
    min_frame_interval_ms: 100,
    packet_delay_ms: 0,
    packet_size: 4096,
    hard_reset_on_start: true,
    hard_reset_wait_ms: 1500,
    handshake_on_first_frame: false,
    require_handshake: true,
    send_start_init: true,
    read_start_ack: true,
    read_frame_ack: true,
    start_retries: 0,
    frame_retries: 1,
    debug: false,
  };
}

function defaultTurzxDeviceConfig(): NonNullable<DisplayOutputConfig["turzx"]> {
  return {
    vid: "0x1a86",
    pid: "0x5722",
    serial_number: "",
    bus: null,
    address: null,
    timeout_ms: 5000,
  };
}

function displayOutputFromConfig(display: RuntimeConfig["display"]["display"], index = 1): DisplayOutputConfig {
  const output = normalizeOutputTarget(display.device.output || display.device.target || "window");
  const resolution = lockedDisplayResolution(output);
  return {
    id: `display-${index}`,
    label: `Display ${index}`,
    enabled: true,
    target: output,
    output,
    x: 0,
    y: 0,
    width: resolution.width,
    height: resolution.height,
    rotation: 0,
    identify_number: index,
    thermalright: {
      ...defaultThermalrightDeviceConfig(),
      ...(display.device.thermalright ?? {}),
      image_width: resolution.width,
      image_height: resolution.height,
    },
    turzx: display.device.turzx ? { ...defaultTurzxDeviceConfig(), ...display.device.turzx } : defaultTurzxDeviceConfig(),
  };
}

function ensureDisplayOutputs(display: RuntimeConfig["display"]["display"]): DisplayOutputConfig[] {
  const existing = Array.isArray(display.device.displays) ? display.device.displays : [];
  const normalized = existing.length ? existing : [displayOutputFromConfig(display, 1)];
  display.device.displays = normalized.map((item, index) => normalizeDisplayOutput(item, index + 1));
  applyMultiDisplayBounds(display);
  return display.device.displays;
}

function normalizeDisplayOutput(raw: Partial<DisplayOutputConfig>, index: number): DisplayOutputConfig {
  const output = normalizeOutputTarget(raw.output || raw.target || "window");
  const rotation = normalizeDisplayRotation(raw.rotation);
  const resolution = lockedDisplayResolution(output, rotation, raw.width, raw.height);
  return {
    id: raw.id || `display-${index}`,
    label: raw.label || `Display ${index}`,
    enabled: raw.enabled ?? true,
    target: output,
    output,
    x: Number(raw.x ?? 0),
    y: Number(raw.y ?? 0),
    width: resolution.width,
    height: resolution.height,
    rotation,
    identify_number: Number(raw.identify_number ?? index),
    thermalright: syncThermalrightSize({ ...defaultThermalrightDeviceConfig(), ...(raw.thermalright ?? {}) }, resolution.width, resolution.height),
    turzx: { ...defaultTurzxDeviceConfig(), ...(raw.turzx ?? {}) },
  };
}

function newDisplayOutput(index: number, displays: DisplayOutputConfig[]): DisplayOutputConfig {
  const previous = displays[displays.length - 1];
  const output = normalizeOutputTarget(previous?.output || previous?.target || "thermalright");
  const rotation = previous?.rotation ?? 0;
  const resolution = lockedDisplayResolution(output, rotation, previous?.width, previous?.height);
  return {
    id: `display-${Date.now().toString(36)}-${index}`,
    label: `Display ${index}`,
    enabled: true,
    target: output,
    output,
    x: previous ? previous.x + previous.width : 0,
    y: previous?.y ?? 0,
    width: resolution.width,
    height: resolution.height,
    rotation,
    identify_number: index,
    thermalright: syncThermalrightSize(previous?.thermalright ?? defaultThermalrightDeviceConfig(), resolution.width, resolution.height),
    turzx: { ...defaultTurzxDeviceConfig(), ...(previous?.turzx ?? {}) },
  };
}

function newDisplayOutputFromUsbDevice(index: number, displays: DisplayOutputConfig[], device: UsbDeviceCandidate): DisplayOutputConfig {
  const target = normalizeUsbTarget(device.target);
  const resolution = lockedDisplayResolution(target, 0);
  const base: DisplayOutputConfig = {
    id: `display-${Date.now().toString(36)}-${index}`,
    label: `${target === "thermalright" ? "Thermalright" : "TURZX"} ${index}`,
    enabled: true,
    target,
    output: target,
    x: displays.length ? Math.max(...displays.map((item) => item.x + item.width)) : 0,
    y: 0,
    width: resolution.width,
    height: resolution.height,
    rotation: 0,
    identify_number: index,
    thermalright: syncThermalrightSize(defaultThermalrightDeviceConfig(), resolution.width, resolution.height),
    turzx: defaultTurzxDeviceConfig(),
  };
  const usbFields = {
    vid: device.vid,
    pid: device.pid,
    serial_number: device.serial_number || "",
    bus: device.bus ?? null,
    address: device.address ?? null,
  };
  if (target === "thermalright") {
    base.thermalright = syncThermalrightSize({ ...defaultThermalrightDeviceConfig(), ...usbFields }, resolution.width, resolution.height);
  } else {
    base.turzx = { ...defaultTurzxDeviceConfig(), ...usbFields };
  }
  return base;
}

function normalizeUsbTarget(value: string | undefined): "thermalright" | "turzx" {
  return value === "turzx" ? "turzx" : "thermalright";
}

function normalizeOutputTarget(value: string): "thermalright" | "turzx" | "window" | "preview" | "gif" {
  if (value === "display") return "turzx";
  if (value === "turzx" || value === "window" || value === "preview" || value === "gif") return value;
  return "thermalright";
}

function lockedDisplayResolution(output: string, rotation: unknown = 0, fallbackWidth?: unknown, fallbackHeight?: unknown): { width: number; height: number } {
  const target = normalizeOutputTarget(output);
  if (target === "window") {
    return {
      width: Math.max(1, Number(fallbackWidth ?? 320)),
      height: Math.max(1, Number(fallbackHeight ?? 480)),
    };
  }
  const native = target === "thermalright" ? { width: 1920, height: 462 } : { width: 320, height: 480 };
  const displayRotation = normalizeDisplayRotation(rotation);
  if (displayRotation === 90 || displayRotation === 270) {
    return { width: native.height, height: native.width };
  }
  return native;
}

function lockDisplayResolution(display: DisplayOutputConfig): DisplayOutputConfig {
  const resolution = lockedDisplayResolution(display.output || display.target, display.rotation, display.width, display.height);
  return {
    ...display,
    width: resolution.width,
    height: resolution.height,
    thermalright: syncThermalrightSize(display.thermalright, resolution.width, resolution.height),
  };
}

function normalizeDisplayRotation(value: unknown): 0 | 90 | 180 | 270 {
  const rotation = Number(value);
  return rotation === 90 || rotation === 180 || rotation === 270 ? rotation : 0;
}

function knownUsbDisplay(config: { serial_number?: string; bus?: number | null; address?: number | null } | undefined): boolean {
  if (!config) return false;
  return Boolean(config.serial_number) || (config.bus != null && config.address != null);
}

function syncThermalrightSize(thermalright: DisplayOutputConfig["thermalright"] | undefined, width: number, height: number) {
  return {
    ...defaultThermalrightDeviceConfig(),
    ...(thermalright ?? {}),
    image_width: width,
    image_height: height,
  };
}

function displayBounds(displays: DisplayOutputConfig[]) {
  if (!displays.length) return { x: 0, y: 0, width: 320, height: 480 };
  const enabled = displays;
  const minX = Math.min(...enabled.map((item) => item.x));
  const minY = Math.min(...enabled.map((item) => item.y));
  const maxX = Math.max(...enabled.map((item) => item.x + item.width));
  const maxY = Math.max(...enabled.map((item) => item.y + item.height));
  return { x: minX, y: minY, width: Math.max(1, maxX - minX), height: Math.max(1, maxY - minY) };
}

function layoutThemeTone(themeKey: string, kind: string, key: string, fallback: string) {
  const theme = layoutThemeCatalog[themeKey] ?? layoutThemeCatalog.default;
  if (themeKey === "default") return fallback;
  return theme.tones[kind] ?? theme.palette[stableIndex(`${kind}:${key}`, theme.palette.length)] ?? fallback;
}

function stableIndex(value: string, modulo: number) {
  if (modulo <= 1) return 0;
  let hash = 0;
  for (const char of value) {
    hash = (hash * 31 + char.charCodeAt(0)) >>> 0;
  }
  return hash % modulo;
}

function layoutProfileKey(label: string) {
  return slugify(label) || "layout";
}

function snapshotLayoutProfile(display: RuntimeConfig["display"]["display"], label: string): LayoutProfileConfig {
  const displays = ensureDisplayOutputs(display);
  return {
    label,
    saved_at: new Date().toISOString(),
    width: display.width,
    height: display.height,
    layout_theme: display.layout_theme ?? "default",
    device: {
      target: display.device.target,
      output: display.device.output,
      displays: cloneJson(displays),
    },
    layout: cloneJson(display.layout),
  };
}

function restoreLayoutProfile(display: RuntimeConfig["display"]["display"], profile: LayoutProfileConfig) {
  display.layout = cloneJson(profile.layout);
  display.device.displays = cloneJson(profile.device.displays).map((item, index) => normalizeDisplayOutput(item, index + 1));
  display.device.target = profile.device.target;
  display.device.output = profile.device.output;
  display.layout_theme = layoutThemeCatalog[profile.layout_theme ?? "default"] ? (profile.layout_theme ?? "default") : "default";
  applyMultiDisplayBounds(display);
  display.width = profile.width;
  display.height = profile.height;
}

function cloneJson<T>(value: T): T {
  return JSON.parse(JSON.stringify(value)) as T;
}

function slugify(value: string) {
  return value
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");
}

function displayGeometryChanged(current: DisplayOutputConfig, next: DisplayOutputConfig) {
  return current.x !== next.x || current.y !== next.y || current.width !== next.width || current.height !== next.height;
}

function attachDisplayToNearest(candidate: DisplayOutputConfig, displays: DisplayOutputConfig[], candidateId: string): DisplayOutputConfig {
  const anchors = displays.filter((display) => display.id !== candidateId);
  if (!anchors.length) return candidate;

  const placements = anchors.flatMap((anchor) => {
    const right = { ...candidate, x: anchor.x + anchor.width, y: clampOverlapAxis(candidate.y, candidate.height, anchor.y, anchor.height) };
    const left = { ...candidate, x: anchor.x - candidate.width, y: clampOverlapAxis(candidate.y, candidate.height, anchor.y, anchor.height) };
    const below = { ...candidate, x: clampOverlapAxis(candidate.x, candidate.width, anchor.x, anchor.width), y: anchor.y + anchor.height };
    const above = { ...candidate, x: clampOverlapAxis(candidate.x, candidate.width, anchor.x, anchor.width), y: anchor.y - candidate.height };
    return [right, left, below, above];
  });

  return placements
    .filter((placement) => !displayOverlapsAny(placement, displays, candidateId))
    .sort((first, second) => displayDistance(first, candidate) - displayDistance(second, candidate))[0] ?? candidate;
}

function clampOverlapAxis(value: number, size: number, anchorStart: number, anchorSize: number) {
  const min = anchorStart - size + 1;
  const max = anchorStart + anchorSize - 1;
  return Math.round(Math.max(min, Math.min(max, value)));
}

function displayDistance(first: DisplayOutputConfig, second: DisplayOutputConfig) {
  const dx = first.x - second.x;
  const dy = first.y - second.y;
  return dx * dx + dy * dy;
}

function displayOverlapsAny(candidate: DisplayOutputConfig, displays: DisplayOutputConfig[], candidateId: string) {
  return displays.some((display) => display.id !== candidateId && rectanglesOverlap(candidate, display));
}

function rectanglesOverlap(first: DisplayOutputConfig, second: DisplayOutputConfig) {
  return first.x < second.x + second.width && first.x + first.width > second.x && first.y < second.y + second.height && first.y + first.height > second.y;
}

function applyMultiDisplayBounds(display: RuntimeConfig["display"]["display"]) {
  const displays = display.device.displays ?? [];
  if (!displays.length) return;
  const bounds = displayBounds(displays);
  display.width = bounds.width;
  display.height = bounds.height;
  applyPrimaryDisplay(display, displays[0]);
}

function applyPrimaryDisplay(display: RuntimeConfig["display"]["display"], primary: DisplayOutputConfig | undefined) {
  if (!primary) return;
  display.device.target = primary.target;
  display.device.output = primary.output;
  display.device.thermalright = primary.thermalright ?? display.device.thermalright ?? defaultThermalrightDeviceConfig();
}

function defaultLayoutFor(width: number, height: number): Record<LayoutKey, LayoutBox> {
  if (width >= 1600 && height <= 600) {
    return defaultWideLayoutFor(width, height);
  }
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
    pc_stats: { x: Math.max(8, width - 132), y: 8, width: 124, height: Math.max(54, middleHudY - 12) },
    activity: { x: 8, y: lowerHudY, width: contentWidth, height: 40 },
    game: { x: 0, y: gameY, width, height: Math.max(1, textY - gameY - 4) },
    text_box: { x: 8, y: textY, width: Math.max(1, width - 16), height: Math.max(1, height - textY - 2) },
  };
}

function defaultWideLayoutFor(width: number, height: number): Record<LayoutKey, LayoutBox> {
  const margin = 24;
  const topHeight = 74;
  const bottomHeight = 72;
  const gameY = topHeight + margin;
  const gameHeight = Math.max(1, height - topHeight - bottomHeight - margin * 2);
  const sideWidth = Math.round(width * 0.16);
  const middleWidth = Math.max(1, width - sideWidth * 2 - margin * 4);
  return {
    timezones: { x: margin, y: 16, width: Math.round(width * 0.32), height: topHeight - 20 },
    meetings_day: { x: margin, y: gameY, width: sideWidth, height: Math.min(170, gameHeight), kind: "meetings_day" },
    pokemon_captures: { x: Math.max(margin, width - Math.round(width * 0.32) - margin), y: gameY, width: Math.round(width * 0.18), height: Math.min(144, gameHeight), kind: "pokemon_captures" },
    route_signal: { x: Math.round(width * 0.35), y: 16, width: Math.round(width * 0.16), height: topHeight - 20 },
    gauges: { x: Math.round(width * 0.53), y: 16, width: Math.round(width * 0.16), height: topHeight - 20 },
    weather: { x: Math.round(width * 0.71), y: 16, width: Math.round(width * 0.12), height: topHeight - 20 },
    pc_stats: { x: Math.max(margin, width - Math.round(width * 0.14) - margin), y: 16, width: Math.round(width * 0.14), height: topHeight - 20 },
    gamification: { x: Math.round(width * 0.84), y: height - bottomHeight + 8, width: Math.max(1, Math.round(width * 0.14)), height: bottomHeight - 18, kind: "gamification" },
    activity: { x: margin, y: height - bottomHeight + 8, width: Math.round(width * 0.44), height: bottomHeight - 18 },
    game: { x: sideWidth + margin * 2, y: gameY, width: middleWidth, height: gameHeight },
    text_box: { x: Math.round(width * 0.47), y: height - bottomHeight + 8, width: Math.max(1, Math.round(width * 0.53) - margin), height: bottomHeight - 18 },
  };
}

function layoutWindowOptions(config: RuntimeConfig, manifest: ConfigManifest, selectedPluginKeys: string[]): LayoutWindowOption[] {
  const options = [...layoutWindowCatalog];
  for (const integration of manifest.integrations) {
    if (integrationConfig(config, integration.key).enabled) {
      options.push(...(integration.layoutWindows ?? []));
    }
  }
  for (const plugin of manifest.visualPlugins) {
    if (selectedPluginKeys.includes(plugin.key)) {
      options.push(...(plugin.layoutWindows ?? []));
    }
  }
  const seen = new Set<string>();
  return options.filter((option) => {
    if (seen.has(option.kind)) return false;
    seen.add(option.kind);
    return true;
  });
}

function layoutWindowKind(key: string, box: LayoutBox): string {
  return box.kind || key;
}

function firstLayoutWindowKey(layout: Record<LayoutKey, LayoutBox>): string | null {
  return Object.keys(layout)[0] ?? null;
}

function removeLayoutWindow(layout: Record<LayoutKey, LayoutBox>, key: string, removeSameKind = false) {
  const removed = layout[key];
  const removedKind = removed ? layoutWindowKind(key, removed) : key;
  for (const [candidateKey, box] of Object.entries(layout)) {
    if (candidateKey === key || (removeSameKind && layoutWindowKind(candidateKey, box) === removedKind)) {
      delete layout[candidateKey];
    }
  }
}

function nextLayoutWindowKey(layout: Record<LayoutKey, LayoutBox>, kind: string): string {
  if (!(kind in layout)) {
    return kind;
  }
  let index = 2;
  while (`${kind}_${index}` in layout) {
    index += 1;
  }
  return `${kind}_${index}`;
}

function layoutBoxForNewWindow(
  kind: string,
  frameWidth: number,
  frameHeight: number,
  layout: Record<LayoutKey, LayoutBox>,
): LayoutBox {
  const defaults = defaultLayoutFor(frameWidth, frameHeight);
  const base = defaults[kind] ?? {
    x: 8,
    y: 8,
    width: Math.max(40, Math.round(frameWidth * 0.35)),
    height: Math.max(32, Math.round(frameHeight * 0.16)),
  };
  const sameKindCount = Object.entries(layout).filter(([key, box]) => layoutWindowKind(key, box) === kind).length;
  return clampBox(
    {
      ...base,
      kind,
      x: base.x + sameKindCount * 12,
      y: base.y + sameKindCount * 12,
    },
    frameWidth,
    frameHeight,
  );
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
