import react from "@vitejs/plugin-react";
import { execFile, execFileSync, spawn, type ChildProcessWithoutNullStreams } from "node:child_process";
import { randomBytes } from "node:crypto";
import { promises as fs } from "node:fs";
import os from "node:os";
import path from "node:path";
import type { IncomingMessage, ServerResponse } from "node:http";
import { promisify } from "node:util";
import { defineConfig, type Plugin } from "vite";

const repoRoot = path.resolve(process.env.PIXEL_OPS_REPO_ROOT || path.resolve(__dirname, ".."));
const pixelOpsKiteRoot = path.join(repoRoot, "infra/cloudflare/pixelops-kite");
const execFileAsync = promisify(execFile);
const pythonCmd = resolvePythonCommand();
let runtimeProcess: ChildProcessWithoutNullStreams | null = null;
const runtimeLogs: string[] = [];
let firmwareProcess: ChildProcessWithoutNullStreams | null = null;
const firmwareLogs: string[] = [];
let firmwareOperation: "build" | "upload" | null = null;
let firmwareResult: { ok: boolean; message: string } | null = null;
let firmwareStartedAt: string | null = null;
let firmwareFinishedAt: string | null = null;
let platformioCommand: { command: string; prefix: string[]; label: string } | null | undefined;
const npcSpritePreviewFormatVersion = 2;

type RuntimeProcessSource = "managed" | "external";

type RuntimeProcessInfo = {
  pid: number;
  source: RuntimeProcessSource;
  command?: string;
};

type ConfigDescriptor = {
  key: string;
  label: string;
  relativePath: string;
  scope: "core" | "integration" | "plugin";
  owner?: string;
};

type LayoutWindowDescriptor = {
  kind: string;
  label: string;
  tone: string;
};

type GitHubRepoDescriptor = {
  full_name: string;
  private: boolean;
  archived: boolean;
  permissions?: Record<string, boolean>;
};

type GitHubDeviceCodeResponse = {
  device_code: string;
  user_code: string;
  verification_uri: string;
  expires_in: number;
  interval: number;
};

type GitHubDeviceTokenResponse = {
  access_token?: string;
  token_type?: string;
  scope?: string;
  error?: string;
  error_description?: string;
  interval?: number;
};

type DiscordOAuthSession = {
  status: "pending" | "authorized" | "error";
  client_id: string;
  client_secret_env: string;
  token_env: string;
  redirect_uri: string;
  message?: string;
  user?: DiscordUserDescriptor;
  guilds?: DiscordGuildDescriptor[];
};

type DiscordTokenResponse = {
  access_token?: string;
  token_type?: string;
  scope?: string;
  error?: string;
  error_description?: string;
};

type DiscordUserDescriptor = {
  id: string;
  username: string;
  global_name?: string;
};

type DiscordGuildDescriptor = {
  id: string;
  name: string;
  owner: boolean;
  permissions: string;
};

type KiteCommandResult = {
  ok: boolean;
  message: string;
  stdout?: string;
  stderr?: string;
  worker_url?: string;
  ws_url?: string;
};

const discordOAuthSessions = new Map<string, DiscordOAuthSession>();

const coreConfigFiles: ConfigDescriptor[] = [
  { key: "display", label: "Display", relativePath: "pixel_ops/config/display.json", scope: "core" },
  { key: "integrations", label: "Integrations", relativePath: "pixel_ops/config/integrations.json", scope: "core" },
  { key: "people", label: "People", relativePath: "pixel_ops/config/people.json", scope: "core" },
];

const integrationSidecars: Record<string, ConfigDescriptor[]> = {
  discord: [
    {
      key: "discord_people",
      label: "Recent Discord people",
      relativePath: "pixel_ops/config/discord_people.json",
      scope: "integration",
      owner: "discord",
    },
  ],
};

const integrationLayoutWindows: Record<string, LayoutWindowDescriptor[]> = {
  gamification: [{ kind: "gamification", label: "Player HP", tone: "#ef6461" }],
  ai_usage: [
    { kind: "gauges", label: "AI Gauges", tone: "#7ee0bd" },
    { kind: "mana", label: "Mana", tone: "#4f9fff" },
  ],
  pc_stats: [{ kind: "pc_stats", label: "PC Stats", tone: "#9bd0ff" }],
  weather: [
    { kind: "weather", label: "Weather Now", tone: "#e8c766" },
    { kind: "weather_forecast", label: "Weather Forecast", tone: "#9bd0ff" },
  ],
  google_calendar: [{ kind: "meetings_day", label: "Meetings Day", tone: "#9aa7ff" }],
  ics: [{ kind: "meetings_day", label: "Meetings Day", tone: "#9aa7ff" }],
  zoom: [{ kind: "activity", label: "Meeting Activity", tone: "#9aa7ff" }],
  clickup: [
    { kind: "tasks", label: "Tasks", tone: "#b58cff" },
    { kind: "tasks_board", label: "Tasks Board", tone: "#f0a35d" },
  ],
  todoist: [
    { kind: "tasks", label: "Tasks", tone: "#b58cff" },
    { kind: "tasks_board", label: "Tasks Board", tone: "#f0a35d" },
  ],
  capacities: [{ kind: "project_radar", label: "Project Radar", tone: "#b58cff" }],
  media: [{ kind: "media", label: "Now Playing", tone: "#6ee7b7" }],
  crosshero: [
    { kind: "crosshero_wod", label: "CrossHero WOD", tone: "#f58236" },
    { kind: "crosshero_classes", label: "CrossHero Classes", tone: "#4ac29a" },
  ],
};

const visualPluginLayoutWindows: Record<string, LayoutWindowDescriptor[]> = {
  pokemon: [
    { kind: "route_signal", label: "Route", tone: "#f0a35d" },
    { kind: "pokemon_captures", label: "Pokemon Captures", tone: "#ef6461" },
    { kind: "game", label: "Game", tone: "#8fbf7a" },
    { kind: "text_box", label: "Text box", tone: "#d8d0ff" },
  ],
};

const pluginConfigKeyAliases: Record<string, Record<string, string>> = {
  pokemon: {
    companions: "pokemon_companions",
  },
};

function sendJson(res: ServerResponse, status: number, body: unknown) {
  res.statusCode = status;
  res.setHeader("content-type", "application/json; charset=utf-8");
  res.end(JSON.stringify(body, null, 2));
}

function sendOAuthCallbackHtml(res: ServerResponse, message: string) {
  res.statusCode = 200;
  res.setHeader("content-type", "text/html; charset=utf-8");
  res.end(`<!doctype html>
<html>
  <head><meta charset="utf-8"><title>Pixel OPs Discord</title></head>
  <body style="font-family: system-ui, sans-serif; background: #10131a; color: #f4f7fb; padding: 24px;">
    <strong>${escapeHtml(message)}</strong>
    <script>
      if (window.opener) window.opener.postMessage({ type: "pixel-ops-discord-oauth" }, window.location.origin);
      window.setTimeout(() => window.close(), 1200);
    </script>
  </body>
</html>`);
}

function escapeHtml(value: string): string {
  return value.replace(/[&<>"']/g, (char) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[char] || char));
}

function resolvePythonCommand() {
  const candidates = [
    process.env.PIXEL_OPS_PYTHON,
    process.platform === "win32" ? path.join(repoRoot, ".venv", "Scripts", "python.exe") : path.join(repoRoot, ".venv", "bin", "python"),
    process.platform === "win32" ? "python" : "python3",
    "python",
    "py",
  ].filter(Boolean) as string[];
  for (const candidate of candidates) {
    try {
      const executable = execFileSync(candidate, ["-c", "import sys; import PIL, yaml, requests; print(sys.executable)"], {
        cwd: repoRoot,
        encoding: "utf8",
        stdio: ["ignore", "pipe", "ignore"],
      }).trim();
      return executable || candidate;
    } catch {
      continue;
    }
  }
  return candidates[0] || "python";
}

async function readBody(req: IncomingMessage): Promise<string> {
  const chunks: Buffer[] = [];
  for await (const chunk of req) {
    chunks.push(Buffer.isBuffer(chunk) ? chunk : Buffer.from(chunk));
  }
  return Buffer.concat(chunks).toString("utf8");
}

async function pathExists(relativePath: string): Promise<boolean> {
  try {
    await fs.access(path.join(repoRoot, relativePath));
    return true;
  } catch {
    return false;
  }
}

async function listDirectories(relativePath: string): Promise<string[]> {
  const root = path.join(repoRoot, relativePath);
  try {
    const entries = await fs.readdir(root, { withFileTypes: true });
    return entries.filter((entry) => entry.isDirectory() && !entry.name.startsWith("__")).map((entry) => entry.name).sort();
  } catch {
    return [];
  }
}

function titleize(value: string): string {
  return value
    .split(/[_-]+/)
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

function pluginConfigKey(pluginName: string, stem: string): string {
  return pluginConfigKeyAliases[pluginName]?.[stem] ?? stem;
}

async function detectVisualPlugins() {
  const pluginNames = await listDirectories("pixel_ops/plugins");
  const plugins = [];
  for (const name of pluginNames) {
    const pluginPy = `pixel_ops/plugins/${name}/plugin.py`;
    if (!(await pathExists(pluginPy))) continue;

    const pluginRoot = path.join(repoRoot, "pixel_ops/plugins", name);
    const files = await fs.readdir(pluginRoot, { withFileTypes: true });
    const configs = files
      .filter((entry) => entry.isFile() && entry.name.endsWith(".json"))
      .map((entry) => {
        const stem = entry.name.replace(/\.json$/, "");
        return {
          key: pluginConfigKey(name, stem),
          label: titleize(stem),
          relativePath: `pixel_ops/plugins/${name}/${entry.name}`,
          scope: "plugin" as const,
          owner: name,
        };
      })
      .sort((first, second) => first.key.localeCompare(second.key));
    if (!configs.length) continue;

    plugins.push({
      key: name,
      label: titleize(name),
      configKeys: configs.map((config) => config.key),
      configs,
      layoutWindows: visualPluginLayoutWindows[name] ?? [],
    });
  }
  return plugins;
}

async function detectIntegrationPlugins() {
  const integrationNames = await listDirectories("pixel_ops/integrations");
  const integrations = [];
  for (const name of integrationNames) {
    const pluginPy = `pixel_ops/integrations/${name}/plugin.py`;
    if (!(await pathExists(pluginPy))) continue;
    integrations.push({
      key: name,
      label: titleize(name),
      configKeys: integrationSidecars[name]?.map((config) => config.key) ?? [],
      configs: integrationSidecars[name] ?? [],
      layoutWindows: integrationLayoutWindows[name] ?? [],
    });
  }
  return integrations;
}

async function buildConfigManifest() {
  const visualPlugins = await detectVisualPlugins();
  const integrations = await detectIntegrationPlugins();
  return {
    core: coreConfigFiles,
    integrations,
    visualPlugins,
  };
}

async function configDescriptorsFor(selectedPlugins: string[]) {
  const manifest = await buildConfigManifest();
  const selectedPluginSet = new Set(selectedPlugins);
  const descriptors = [...coreConfigFiles];
  for (const plugin of manifest.visualPlugins) {
    if (selectedPluginSet.has(plugin.key)) {
      descriptors.push(...plugin.configs);
    }
  }

  const integrationsPath = coreConfigFiles.find((item) => item.key === "integrations")?.relativePath;
  if (integrationsPath) {
    const raw = await fs.readFile(path.join(repoRoot, integrationsPath), "utf8");
    const integrationsConfig = JSON.parse(raw) as { integrations?: Record<string, { enabled?: boolean }> };
    for (const integration of manifest.integrations) {
      if (integrationsConfig.integrations?.[integration.key]?.enabled) {
        descriptors.push(...integration.configs);
      }
    }
  }

  return descriptors;
}

async function loadRuntimeConfig(selectedPlugins: string[]) {
  const descriptors = await configDescriptorsFor(selectedPlugins);
  const entries = await Promise.all(
    descriptors.map(async (descriptor) => {
      const raw = await fs.readFile(path.join(repoRoot, descriptor.relativePath), "utf8");
      return [descriptor.key, JSON.parse(raw)] as const;
    }),
  );
  return Object.fromEntries(entries);
}

async function saveRuntimeConfig(payload: unknown) {
  if (!payload || typeof payload !== "object" || Array.isArray(payload)) {
    throw new Error("Invalid config payload.");
  }

  const record = payload as Record<string, unknown>;
  const manifest = await buildConfigManifest();
  const configFiles = [
    ...coreConfigFiles,
    ...manifest.integrations.flatMap((plugin) => plugin.configs),
    ...manifest.visualPlugins.flatMap((plugin) => plugin.configs),
  ];
  await Promise.all(
    configFiles.map(async (descriptor) => {
      if (!(descriptor.key in record)) return;
      const target = path.join(repoRoot, descriptor.relativePath);
      await fs.writeFile(target, `${JSON.stringify(record[descriptor.key], null, 2)}\n`, "utf8");
    }),
  );
}

async function readDotEnv(): Promise<Record<string, string>> {
  const envPath = path.join(repoRoot, ".env");
  try {
    const raw = await fs.readFile(envPath, "utf8");
    const values: Record<string, string> = {};
    for (const line of raw.split(/\r?\n/)) {
      const trimmed = line.trim();
      if (!trimmed || trimmed.startsWith("#")) continue;
      const match = trimmed.match(/^(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)=(.*)$/);
      if (!match) continue;
      values[match[1]] = unquoteEnvValue(match[2]);
    }
    return values;
  } catch {
    return {};
  }
}

function unquoteEnvValue(value: string): string {
  const trimmed = value.trim();
  if ((trimmed.startsWith('"') && trimmed.endsWith('"')) || (trimmed.startsWith("'") && trimmed.endsWith("'"))) {
    return trimmed.slice(1, -1);
  }
  return trimmed;
}

function quoteEnvValue(value: string): string {
  if (/^[A-Za-z0-9_./:@-]+$/.test(value)) {
    return value;
  }
  return JSON.stringify(value);
}

async function writeDotEnvValue(name: string, value: string): Promise<void> {
  if (!/^[A-Za-z_][A-Za-z0-9_]*$/.test(name)) {
    throw new Error("Invalid env var name.");
  }
  const envPath = path.join(repoRoot, ".env");
  let raw = "";
  try {
    raw = await fs.readFile(envPath, "utf8");
  } catch {
    raw = "";
  }
  const nextLine = `${name}=${quoteEnvValue(value)}`;
  const lines = raw ? raw.split(/\r?\n/) : [];
  let replaced = false;
  const next = lines.map((line) => {
    if (line.match(new RegExp(`^(?:export\\s+)?${name}=`))) {
      replaced = true;
      return nextLine;
    }
    return line;
  });
  if (!replaced) {
    if (next.length && next[next.length - 1] !== "") next.push("");
    next.push(nextLine);
  }
  await fs.writeFile(envPath, `${next.join("\n").replace(/\n+$/, "")}\n`, "utf8");
}

async function githubToken(tokenEnv: string): Promise<string> {
  const name = tokenEnv || "PIXEL_OPS_GITHUB_TOKEN";
  return process.env[name] || (await readDotEnv())[name] || "";
}

async function githubJson<T>(url: string, token: string): Promise<T> {
  const response = await fetch(url, {
    headers: {
      Accept: "application/vnd.github+json",
      Authorization: `Bearer ${token}`,
      "User-Agent": "pixel-ops-config-studio",
      "X-GitHub-Api-Version": "2022-11-28",
    },
  });
  if (!response.ok) {
    throw new Error(`GitHub returned ${response.status}: ${await response.text()}`);
  }
  return response.json() as Promise<T>;
}

async function githubForm<T>(url: string, fields: Record<string, string>): Promise<T> {
  const response = await fetch(url, {
    method: "POST",
    headers: {
      Accept: "application/json",
      "content-type": "application/x-www-form-urlencoded",
      "User-Agent": "pixel-ops-config-studio",
    },
    body: new URLSearchParams(fields),
  });
  if (!response.ok) {
    throw new Error(`GitHub returned ${response.status}: ${await response.text()}`);
  }
  return response.json() as Promise<T>;
}

async function startGithubDeviceLogin(clientId: string): Promise<GitHubDeviceCodeResponse> {
  if (!clientId.trim()) {
    throw new Error("GitHub client_id is required.");
  }
  return githubForm<GitHubDeviceCodeResponse>("https://github.com/login/device/code", {
    client_id: clientId.trim(),
  });
}

async function pollGithubDeviceLogin(clientId: string, deviceCode: string, tokenEnv: string) {
  if (!clientId.trim() || !deviceCode.trim()) {
    throw new Error("GitHub client_id and device_code are required.");
  }
  const result = await githubForm<GitHubDeviceTokenResponse>("https://github.com/login/oauth/access_token", {
    client_id: clientId.trim(),
    device_code: deviceCode.trim(),
    grant_type: "urn:ietf:params:oauth:grant-type:device_code",
  });
  if (result.access_token) {
    const name = tokenEnv || "PIXEL_OPS_GITHUB_TOKEN";
    await writeDotEnvValue(name, result.access_token);
    return { status: "authorized", token_env: name, scope: result.scope ?? "" };
  }
  if (result.error === "authorization_pending" || result.error === "slow_down") {
    return {
      status: result.error,
      interval: result.interval,
      message: result.error_description ?? result.error,
    };
  }
  throw new Error(result.error_description || result.error || "GitHub device authorization failed.");
}

async function listGithubRepos(tokenEnv: string) {
  const token = await githubToken(tokenEnv);
  if (!token) {
    throw new Error(`${tokenEnv || "PIXEL_OPS_GITHUB_TOKEN"} is not set in .env.`);
  }
  const viewer = await githubJson<{ login: string }>("https://api.github.com/user", token);
  const repos: GitHubRepoDescriptor[] = [];
  for (let page = 1; page <= 10; page += 1) {
    const items = await githubJson<GitHubRepoDescriptor[]>(
      `https://api.github.com/user/repos?per_page=100&page=${page}&sort=updated&affiliation=owner,collaborator,organization_member`,
      token,
    );
    repos.push(...items);
    if (items.length < 100) break;
  }
  return {
    viewer: viewer.login,
    repos: repos
      .filter((repo) => !repo.archived)
      .map((repo) => ({
        full_name: repo.full_name,
        private: repo.private,
        permissions: repo.permissions ?? {},
      }))
      .sort((first, second) => first.full_name.localeCompare(second.full_name)),
  };
}

async function envValue(name: string): Promise<string> {
  return process.env[name] || (await readDotEnv())[name] || "";
}

function configStudioOrigin(): string {
  return process.env.PIXEL_OPS_CONFIG_STUDIO_ORIGIN || "http://localhost:5174";
}

function discordRedirectUri(): string {
  return `${configStudioOrigin()}/api/discord/oauth/callback`;
}

async function discordToken(tokenEnv: string): Promise<string> {
  const name = tokenEnv || "PIXEL_OPS_DISCORD_USER_TOKEN";
  return envValue(name);
}

async function discordJson<T>(url: string, token: string): Promise<T> {
  const response = await fetch(url, {
    headers: {
      Accept: "application/json",
      Authorization: `Bearer ${token}`,
      "User-Agent": "pixel-ops-config-studio",
    },
  });
  if (!response.ok) {
    throw new Error(`Discord returned ${response.status}: ${await response.text()}`);
  }
  return response.json() as Promise<T>;
}

async function discordForm<T>(url: string, fields: Record<string, string>): Promise<T> {
  const response = await fetch(url, {
    method: "POST",
    headers: {
      Accept: "application/json",
      "content-type": "application/x-www-form-urlencoded",
      "User-Agent": "pixel-ops-config-studio",
    },
    body: new URLSearchParams(fields),
  });
  if (!response.ok) {
    throw new Error(`Discord returned ${response.status}: ${await response.text()}`);
  }
  return response.json() as Promise<T>;
}

function startDiscordOAuth(clientId: string, clientSecretEnv: string, tokenEnv: string) {
  if (!clientId.trim()) {
    throw new Error("Discord client_id is required.");
  }
  const state = randomBytes(18).toString("hex");
  const redirect_uri = discordRedirectUri();
  const session: DiscordOAuthSession = {
    status: "pending",
    client_id: clientId.trim(),
    client_secret_env: clientSecretEnv || "PIXEL_OPS_DISCORD_CLIENT_SECRET",
    token_env: tokenEnv || "PIXEL_OPS_DISCORD_USER_TOKEN",
    redirect_uri,
  };
  discordOAuthSessions.set(state, session);
  const params = new URLSearchParams({
    client_id: session.client_id,
    redirect_uri,
    response_type: "code",
    scope: "identify guilds",
    state,
  });
  return {
    state,
    redirect_uri,
    authorize_url: `https://discord.com/oauth2/authorize?${params.toString()}`,
  };
}

async function completeDiscordOAuth(code: string, state: string) {
  const session = discordOAuthSessions.get(state);
  if (!session) {
    throw new Error("Unknown Discord OAuth state.");
  }
  const clientSecret = await envValue(session.client_secret_env);
  if (!clientSecret) {
    throw new Error(`${session.client_secret_env} is not set in .env.`);
  }
  const token = await discordForm<DiscordTokenResponse>("https://discord.com/api/oauth2/token", {
    client_id: session.client_id,
    client_secret: clientSecret,
    grant_type: "authorization_code",
    code,
    redirect_uri: session.redirect_uri,
  });
  if (!token.access_token) {
    throw new Error(token.error_description || token.error || "Discord authorization failed.");
  }
  await writeDotEnvValue(session.token_env, token.access_token);
  const profile = await discordProfileFromToken(token.access_token);
  session.status = "authorized";
  session.user = profile.user;
  session.guilds = profile.guilds;
  session.message = "Discord authorized.";
  return session;
}

async function discordProfileFromToken(token: string) {
  const user = await discordJson<DiscordUserDescriptor>("https://discord.com/api/users/@me", token);
  const guilds = await discordJson<DiscordGuildDescriptor[]>("https://discord.com/api/users/@me/guilds", token);
  return {
    user,
    guilds: guilds.sort((first, second) => first.name.localeCompare(second.name)),
  };
}

async function loadDiscordProfile(tokenEnv: string) {
  const token = await discordToken(tokenEnv);
  if (!token) {
    throw new Error(`${tokenEnv || "PIXEL_OPS_DISCORD_USER_TOKEN"} is not set in .env.`);
  }
  return discordProfileFromToken(token);
}

function pushRuntimeLog(value: string) {
  const clean = value.replace(/\r\n/g, "\n").trimEnd();
  if (!clean) return;
  runtimeLogs.push(...clean.split("\n"));
  while (runtimeLogs.length > 240) {
    runtimeLogs.shift();
  }
}

function pushFirmwareLog(value: string) {
  const clean = value.replace(/\r\n/g, "\n").trimEnd();
  if (!clean) return;
  firmwareLogs.push(...clean.split("\n"));
  while (firmwareLogs.length > 300) firmwareLogs.shift();
}

function resolvePlatformioCommand(): { command: string; prefix: string[]; label: string } {
  if (platformioCommand) return platformioCommand;
  if (platformioCommand === null) throw new Error("PlatformIO não encontrado. Instale 'pio' ou o gerenciador 'uv'.");
  for (const command of ["pio", "platformio"]) {
    try {
      execFileSync(command, ["--version"], { stdio: "ignore" });
      platformioCommand = { command, prefix: [], label: command };
      return platformioCommand;
    } catch {
      // Try the next locally installed command.
    }
  }
  try {
    execFileSync("uvx", ["platformio", "--version"], { stdio: "ignore" });
    platformioCommand = { command: "uvx", prefix: ["platformio"], label: "uvx platformio" };
    return platformioCommand;
  } catch {
    platformioCommand = null;
    throw new Error("PlatformIO não encontrado. Instale 'pio' ou o gerenciador 'uv'.");
  }
}

async function discoverFirmwarePorts(): Promise<string[]> {
  const patterns = process.platform === "darwin"
    ? [/^cu\.usbmodem/i, /^cu\.usbserial/i, /^cu\.SLAB_USBtoUART/i, /^cu\.wchusbserial/i]
    : [/^ttyACM\d+$/i, /^ttyUSB\d+$/i];
  if (process.platform === "win32") return [];
  try {
    const entries = await fs.readdir("/dev");
    return entries.filter((entry) => patterns.some((pattern) => pattern.test(entry))).map((entry) => `/dev/${entry}`).sort();
  } catch {
    return [];
  }
}

async function firmwareStatus() {
  let tool: string | null = null;
  let toolError: string | null = null;
  try {
    tool = resolvePlatformioCommand().label;
  } catch (error) {
    toolError = error instanceof Error ? error.message : String(error);
  }
  return {
    busy: firmwareProcess !== null,
    operation: firmwareOperation,
    result: firmwareResult,
    started_at: firmwareStartedAt,
    finished_at: firmwareFinishedAt,
    ports: await discoverFirmwarePorts(),
    environment: "e213",
    firmware_path: "firmware/heltec-e213",
    tool,
    tool_error: toolError,
    logs: firmwareLogs.slice(-120),
  };
}

async function startFirmwareOperation(operation: "build" | "upload", port?: string) {
  if (firmwareProcess) throw new Error("Já existe uma operação de firmware em andamento.");
  const ports = await discoverFirmwarePorts();
  if (operation === "upload" && (!port || !ports.includes(port))) {
    throw new Error("Selecione uma porta USB detectada antes de instalar o firmware.");
  }
  const platformio = resolvePlatformioCommand();
  const args = [...platformio.prefix, "run", "--environment", "e213"];
  if (operation === "upload") args.push("--target", "upload", "--upload-port", port as string);
  firmwareLogs.length = 0;
  firmwareOperation = operation;
  firmwareResult = null;
  firmwareStartedAt = new Date().toISOString();
  firmwareFinishedAt = null;
  pushFirmwareLog(`${platformio.label} ${args.slice(platformio.prefix.length).join(" ")}`);
  firmwareProcess = spawn(platformio.command, args, {
    cwd: path.join(repoRoot, "firmware/heltec-e213"),
    env: process.env,
  });
  firmwareProcess.stdout.on("data", (chunk) => pushFirmwareLog(String(chunk)));
  firmwareProcess.stderr.on("data", (chunk) => pushFirmwareLog(String(chunk)));
  firmwareProcess.on("error", (error) => {
    pushFirmwareLog(error.message);
    firmwareResult = { ok: false, message: `Falha ao iniciar: ${error.message}` };
  });
  firmwareProcess.on("exit", (code, signal) => {
    const ok = code === 0;
    firmwareResult = {
      ok,
      message: ok
        ? operation === "upload" ? "Firmware instalado. O painel está reiniciando." : "Firmware compilado com sucesso."
        : `Operação falhou (código ${code ?? "-"}, sinal ${signal ?? "-"}).`,
    };
    firmwareFinishedAt = new Date().toISOString();
    firmwareProcess = null;
  });
  return firmwareStatus();
}

function runtimePidPath() {
  return path.join(repoRoot, "pixel_ops/output/runtime.pid");
}

async function runtimeStatus() {
  const discovered = await discoverRuntimeProcess();
  return {
    running: discovered !== null,
    pid: discovered?.pid ?? null,
    source: discovered?.source ?? null,
    command: discovered?.command ?? null,
    logs: runtimeLogs.slice(-80),
  };
}

function runtimeCommandArgs(mode: "configured" | "window" = "configured"): string[] {
  const args = ["pixel_ops/main.py", "--forever"];
  if (mode === "window") {
    args.push("--output", "window", "--offline");
  }
  return args;
}

async function runRuntimeCommand(args: string[]) {
  try {
    const { stdout, stderr } = await execFileAsync(pythonCmd, args, {
      cwd: repoRoot,
      maxBuffer: 1024 * 1024 * 4,
    });
    pushRuntimeLog(stdout);
    pushRuntimeLog(stderr);
    return { ok: true, stdout, stderr, ...(await runtimeStatus()) };
  } catch (error) {
    const err = error as Error & { stdout?: string; stderr?: string };
    pushRuntimeLog(err.stdout || "");
    pushRuntimeLog(err.stderr || err.message);
    return { ok: false, stdout: err.stdout || "", stderr: err.stderr || err.message, ...(await runtimeStatus()) };
  }
}

async function startRuntime(mode: "configured" | "window" = "configured") {
  if (await discoverRuntimeProcess()) {
    return runtimeStatus();
  }
  const args = runtimeCommandArgs(mode);
  runtimeProcess = spawn(pythonCmd, args, {
    cwd: repoRoot,
    env: { ...process.env, PYTHONUNBUFFERED: "1" },
  });
  pushRuntimeLog(`Started ${mode === "window" ? "window" : "configured"} runtime pid=${runtimeProcess.pid ?? "unknown"}`);
  pushRuntimeLog(`${pythonCmd} ${args.join(" ")}`);
  writeRuntimePid(runtimeProcess.pid).catch(() => undefined);
  runtimeProcess.stdout.on("data", (chunk) => pushRuntimeLog(String(chunk)));
  runtimeProcess.stderr.on("data", (chunk) => pushRuntimeLog(String(chunk)));
  runtimeProcess.on("exit", (code, signal) => {
    pushRuntimeLog(`Runtime exited code=${code ?? "-"} signal=${signal ?? "-"}`);
    runtimeProcess = null;
    removeRuntimePid().catch(() => undefined);
  });
  return runtimeStatus();
}

async function writeRuntimePid(pid: number | undefined) {
  if (!pid) return;
  await fs.mkdir(path.dirname(runtimePidPath()), { recursive: true });
  await fs.writeFile(runtimePidPath(), String(pid), "utf8");
}

async function removeRuntimePid() {
  try {
    await fs.unlink(runtimePidPath());
  } catch {
    // The pid file is best-effort and may not exist for older launchers.
  }
}

async function discoverRuntimeProcess(): Promise<RuntimeProcessInfo | null> {
  if (runtimeProcess?.pid && isProcessAlive(runtimeProcess.pid)) {
    return { pid: runtimeProcess.pid, source: "managed" };
  }
  runtimeProcess = null;
  const pidFileProcess = await runtimeProcessFromPidFile();
  if (pidFileProcess) {
    return pidFileProcess;
  }
  return scanRuntimeProcesses();
}

async function runtimeProcessFromPidFile(): Promise<RuntimeProcessInfo | null> {
  try {
    const raw = await fs.readFile(runtimePidPath(), "utf8");
    const pid = Number(raw.trim());
    if (!Number.isInteger(pid) || pid <= 0 || !isProcessAlive(pid)) {
      await removeRuntimePid();
      return null;
    }
    const command = await processCommand(pid);
    if (!isPixelOpsRuntimeCommand(command)) {
      await removeRuntimePid();
      return null;
    }
    return { pid, source: "external", command };
  } catch {
    return null;
  }
}

function isProcessAlive(pid: number) {
  try {
    process.kill(pid, 0);
    return true;
  } catch {
    return false;
  }
}

async function processCommand(pid: number): Promise<string> {
  try {
    if (process.platform === "win32") {
      const { stdout } = await execFileAsync("powershell.exe", ["-NoProfile", "-Command", `Get-CimInstance Win32_Process -Filter "ProcessId = ${pid}" | ForEach-Object { $_.CommandLine }`]);
      return stdout.trim();
    }
    const { stdout } = await execFileAsync("ps", ["-p", String(pid), "-o", "command="]);
    return stdout.trim();
  } catch {
    return "";
  }
}

async function scanRuntimeProcesses(): Promise<RuntimeProcessInfo | null> {
  try {
    if (process.platform === "win32") {
      const { stdout } = await execFileAsync("powershell.exe", [
        "-NoProfile",
        "-Command",
        "Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -match 'pixel_ops[\\\\\\\\/]main\\.py' -and $_.CommandLine -match '--forever' } | Select-Object ProcessId,CommandLine | ConvertTo-Json -Compress",
      ]);
      const parsed = stdout.trim() ? JSON.parse(stdout) : null;
      const rows = Array.isArray(parsed) ? parsed : parsed ? [parsed] : [];
      const match = rows.find((row) => Number.isInteger(Number(row.ProcessId)) && isPixelOpsRuntimeCommand(String(row.CommandLine || "")));
      return match ? { pid: Number(match.ProcessId), source: "external", command: String(match.CommandLine || "") } : null;
    }
    const { stdout } = await execFileAsync("ps", ["-axo", "pid=,command="], { maxBuffer: 1024 * 1024 * 4 });
    for (const line of stdout.split("\n")) {
      const match = line.match(/^\s*(\d+)\s+(.+)$/);
      if (!match) continue;
      const pid = Number(match[1]);
      const command = match[2];
      if (pid !== process.pid && isPixelOpsRuntimeCommand(command)) {
        return { pid, source: "external", command };
      }
    }
  } catch {
    return null;
  }
  return null;
}

function isPixelOpsRuntimeCommand(command: string) {
  return /pixel_ops[\\/]+main\.py/.test(command) && command.includes("--forever");
}

async function runKiteCommand(command: string, args: string[] = [], input = ""): Promise<KiteCommandResult> {
  return new Promise((resolve) => {
    const child = spawn(command, args, {
      cwd: pixelOpsKiteRoot,
      env: { ...process.env },
      shell: process.platform === "win32",
    });
    let stdout = "";
    let stderr = "";
    child.stdout.on("data", (chunk) => {
      stdout += String(chunk);
    });
    child.stderr.on("data", (chunk) => {
      stderr += String(chunk);
    });
    child.on("error", (error) => {
      resolve({ ok: false, message: error.message, stdout, stderr });
    });
    child.on("close", (code) => {
      const ok = code === 0;
      resolve({
        ok,
        message: ok ? "Command completed." : `Command failed with exit code ${code ?? "unknown"}.`,
        stdout,
        stderr,
        ...kiteUrlsFromOutput(`${stdout}\n${stderr}`),
      });
    });
    if (input) {
      child.stdin.write(input.endsWith("\n") ? input : `${input}\n`);
    }
    child.stdin.end();
  });
}

async function kiteStatus(): Promise<KiteCommandResult & { files: Record<string, boolean>; local_token_set: boolean }> {
  const env = await readDotEnv();
  const files = {
    package_json: await fileExists(path.join(pixelOpsKiteRoot, "package.json")),
    wrangler_toml: await fileExists(path.join(pixelOpsKiteRoot, "wrangler.toml")),
    worker: await fileExists(path.join(pixelOpsKiteRoot, "src/worker.js")),
    node_modules: await fileExists(path.join(pixelOpsKiteRoot, "node_modules")),
  };
  return {
    ok: files.package_json && files.wrangler_toml && files.worker,
    message: files.node_modules ? "PixelOpsKite IaC is ready." : "PixelOpsKite IaC exists; install dependencies before deploy.",
    files,
    local_token_set: Boolean(process.env.PIXEL_OPS_KITE_TOKEN || env.PIXEL_OPS_KITE_TOKEN),
  };
}

async function kiteInstall(): Promise<KiteCommandResult> {
  return runKiteCommand(npmCommand(), ["install"]);
}

async function kiteDeploy(): Promise<KiteCommandResult> {
  const result = await runKiteCommand(npxCommand(), ["wrangler", "deploy"]);
  if (result.worker_url && !result.ws_url) {
    result.ws_url = workerWsUrl(result.worker_url);
  }
  return result;
}

async function kitePutSecret(name: string, value: string): Promise<KiteCommandResult> {
  if (!/^[A-Z_][A-Z0-9_]*$/.test(name)) {
    throw new Error("Invalid Kite secret name.");
  }
  if (!value.trim()) {
    throw new Error(`${name} is required.`);
  }
  return runKiteCommand(npxCommand(), ["wrangler", "secret", "put", name], value);
}

async function configureKiteSecrets(body: { kite_token?: string; zoom_webhook_secret_token?: string }): Promise<KiteCommandResult> {
  const results: KiteCommandResult[] = [];
  const kiteToken = (body.kite_token || "").trim();
  const zoomToken = (body.zoom_webhook_secret_token || "").trim();
  if (kiteToken) {
    await writeDotEnvValue("PIXEL_OPS_KITE_TOKEN", kiteToken);
    results.push(await kitePutSecret("PIXEL_OPS_KITE_TOKEN", kiteToken));
  }
  if (zoomToken) {
    results.push(await kitePutSecret("ZOOM_WEBHOOK_SECRET_TOKEN", zoomToken));
  }
  if (!results.length) {
    return { ok: false, message: "Provide at least one secret value." };
  }
  return {
    ok: results.every((result) => result.ok),
    message: results.every((result) => result.ok) ? "Kite secrets configured." : "One or more Kite secrets failed.",
    stdout: results.map((result) => result.stdout || "").join("\n"),
    stderr: results.map((result) => result.stderr || result.message).join("\n"),
  };
}

async function fileExists(fullPath: string): Promise<boolean> {
  try {
    await fs.access(fullPath);
    return true;
  } catch {
    return false;
  }
}

function npmCommand(): string {
  return process.platform === "win32" ? "npm.cmd" : "npm";
}

function npxCommand(): string {
  return process.platform === "win32" ? "npx.cmd" : "npx";
}

function kiteUrlsFromOutput(output: string): { worker_url?: string; ws_url?: string } {
  const match = output.match(/https:\/\/[^\s'"<>]+\.workers\.dev/);
  if (!match) return {};
  return { worker_url: match[0], ws_url: workerWsUrl(match[0]) };
}

function workerWsUrl(workerUrl: string): string {
  return workerUrl.replace(/^https:/, "wss:").replace(/\/$/, "") + "/connect";
}

async function scanThermalrightUsbDisplays() {
  const script = `
import json
from pixel_ops.hardware.thermalright_usb import scan_thermalright_devices
from pixel_ops.hardware.usb_bulk import scan_turzx_devices

thermalright_devices = scan_thermalright_devices(log=lambda *_args, **_kwargs: None)
turzx_devices = scan_turzx_devices()
devices = [
    {
        "target": "thermalright",
        "vid": f"0x{device.vid:04x}",
        "pid": f"0x{device.pid:04x}",
        "manufacturer": device.manufacturer,
        "product": device.product,
        "serial_number": device.serial_number,
        "bus": device.bus,
        "address": device.address,
        "has_default_endpoints": device.has_default_endpoints,
    }
    for device in thermalright_devices
] + [
    {
        "target": "turzx",
        "vid": f"0x{device.vid:04x}",
        "pid": f"0x{device.pid:04x}",
        "manufacturer": device.manufacturer,
        "product": device.product,
        "serial_number": device.serial_number,
        "bus": device.bus,
        "address": device.address,
        "has_default_endpoints": False,
    }
    for device in turzx_devices
]
print(json.dumps({
    "ok": True,
    "message": f"{len(devices)} USB display candidate(s) found ({len(thermalright_devices)} Thermalright, {len(turzx_devices)} TURZX).",
    "devices": devices,
}))
`;
  try {
    const { stdout, stderr } = await execFileAsync(pythonCmd, ["-c", script], { cwd: repoRoot, maxBuffer: 1024 * 1024 });
    return JSON.parse(stdout || "{}");
  } catch (error) {
    const err = error as Error & { stdout?: string; stderr?: string };
    return { ok: false, message: err.stderr || err.stdout || err.message, stdout: err.stdout || "", stderr: err.stderr || "" };
  }
}

async function identifyThermalrightDisplay(display: Record<string, unknown>) {
  if (await discoverRuntimeProcess()) {
    return {
      ok: false,
      message: "Stop the running window/runtime before identifying USB displays. Thermalright USB can only be claimed by one process at a time.",
    };
  }
  const script = `
import json
import sys
from PIL import Image, ImageDraw
from pixel_ops.outputs.turzx_usb import TURZXOutput
from pixel_ops.outputs.thermalright import ThermalrightOutput

display = json.loads(sys.argv[1])
thermalright = display.get("thermalright") or {}
turzx = display.get("turzx") or {}
target = str(display.get("output") or display.get("target") or "thermalright").lower()
number = int(display.get("identify_number") or 1)
rotation = int(display.get("rotation") or 0)
if rotation not in (0, 90, 180, 270):
    rotation = 0
native_width, native_height = (1920, 462) if target == "thermalright" else (320, 480)
width, height = (native_height, native_width) if rotation in (90, 270) else (native_width, native_height)
image = Image.new("RGB", (width, height), (10, 14, 24))
draw = ImageDraw.Draw(image)
draw.rectangle((0, 0, width - 1, height - 1), outline=(255, 255, 255), width=max(4, width // 180))
label = str(number)
subtitle = str(display.get("label") or f"Display {number}")
font_size = max(24, min(height - 24, width // 5))
try:
    from PIL import ImageFont
    number_font = ImageFont.truetype("Arial.ttf", font_size)
    subtitle_font = ImageFont.truetype("Arial.ttf", max(16, font_size // 5))
except Exception:
    number_font = None
    subtitle_font = None
bbox = draw.textbbox((0, 0), label, font=number_font)
draw.text(((width - (bbox[2] - bbox[0])) // 2, max(8, (height - (bbox[3] - bbox[1])) // 2 - height // 12)), label, font=number_font, fill=(255, 230, 90))
subbox = draw.textbbox((0, 0), subtitle, font=subtitle_font)
draw.text(((width - (subbox[2] - subbox[0])) // 2, min(height - 40, height // 2 + font_size // 3)), subtitle, font=subtitle_font, fill=(180, 220, 255))
if rotation:
    image = image.rotate(-rotation, expand=True)
if target == "turzx":
    output = TURZXOutput.from_config(native_width, native_height, turzx)
else:
    output = ThermalrightOutput(
        vid=int(str(thermalright.get("vid", "0x0416")), 0),
        pid=int(str(thermalright.get("pid", "0x5408")), 0),
        serial_number=str(thermalright.get("serial_number") or ""),
        bus=int(thermalright["bus"]) if thermalright.get("bus") not in (None, "") else None,
        address=int(thermalright["address"]) if thermalright.get("address") not in (None, "") else None,
        timeout_ms=int(thermalright.get("timeout_ms", 5000)),
        jpeg_quality=int(thermalright.get("jpeg_quality", 85)),
        image_width=native_width,
        image_height=native_height,
        min_frame_interval_ms=int(thermalright.get("min_frame_interval_ms", 100)),
        packet_delay_ms=int(thermalright.get("packet_delay_ms", 0)),
        packet_size=int(thermalright.get("packet_size", 4096)),
        hard_reset_on_start=bool(thermalright.get("hard_reset_on_start", True)),
        hard_reset_wait_ms=int(thermalright.get("hard_reset_wait_ms", 1500)),
        handshake_on_first_frame=bool(thermalright.get("handshake_on_first_frame", False)),
        require_handshake=bool(thermalright.get("require_handshake", True)),
        send_start_init=bool(thermalright.get("send_start_init", True)),
        read_start_ack=bool(thermalright.get("read_start_ack", True)),
        read_frame_ack=bool(thermalright.get("read_frame_ack", True)),
        start_retries=int(thermalright.get("start_retries", 0)),
        frame_retries=int(thermalright.get("frame_retries", 1)),
        debug=bool(thermalright.get("debug", False)),
    )
try:
    output.start()
    output.send(image)
finally:
    output.stop()
print(json.dumps({"ok": True, "message": f"Sent identifier {number} to {subtitle}."}))
`;
  try {
    const { stdout, stderr } = await execFileAsync(pythonCmd, ["-c", script, JSON.stringify(display)], {
      cwd: repoRoot,
      maxBuffer: 1024 * 1024 * 4,
    });
    return { ...JSON.parse(stdout || "{}"), stdout, stderr };
  } catch (error) {
    const err = error as Error & { stdout?: string; stderr?: string };
    const rawMessage = err.stderr || err.stdout || err.message;
    const friendly = friendlyUsbError(rawMessage);
    return { ok: false, message: friendly, stdout: err.stdout || "", stderr: err.stderr || "" };
  }
}

function friendlyUsbError(value: string) {
  if (value.includes("Access denied") || value.includes("insufficient permissions")) {
    return "Could not claim the USB display. Stop any running Pixel OPs/Thermalright process, then try Identify again. USB bulk devices can only be owned by one process at a time.";
  }
  if (value.includes("USB device") && value.includes("not found")) {
    return "USB display not found. Check the VID/PID, cable, power, and whether the display is visible to the OS.";
  }
  return value.split("\n").filter(Boolean).slice(-1)[0] || value;
}

async function startRuntimeWindow() {
  return startRuntime("window");
}

async function stopRuntimeWindow() {
  const discovered = await discoverRuntimeProcess();
  if (!discovered) {
    return runtimeStatus();
  }
  pushRuntimeLog(`Stopping ${discovered.source} runtime pid=${discovered.pid}`);
  try {
    if (runtimeProcess && discovered.source === "managed") {
      runtimeProcess.kill();
      runtimeProcess = null;
    } else {
      process.kill(discovered.pid);
    }
  } catch (error) {
    pushRuntimeLog(error instanceof Error ? error.message : String(error));
  }
  await waitForRuntimeStop(discovered.pid);
  await removeRuntimePid();
  return runtimeStatus();
}

async function waitForRuntimeStop(pid: number) {
  for (let attempt = 0; attempt < 10; attempt += 1) {
    if (!isProcessAlive(pid)) {
      return;
    }
    await new Promise((resolve) => setTimeout(resolve, 120));
  }
}

function shellQuote(value: string): string {
  return `'${value.replaceAll("'", "'\\''")}'`;
}

function xmlEscape(value: string): string {
  return value.replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;").replaceAll('"', "&quot;").replaceAll("'", "&apos;");
}

function macAutostartSupportDir() {
  return path.join(os.homedir(), "Library/Application Support/Pixel OPs");
}

function macAutostartLogDir() {
  return path.join(os.homedir(), "Library/Logs/Pixel OPs");
}

async function ensureRuntimeLaunchers() {
  const runtimeDir = path.join(repoRoot, "tools/runtime");
  await fs.mkdir(runtimeDir, { recursive: true });
  const unixLauncher = path.join(runtimeDir, "start-pixel-ops-runtime.sh");
  const windowsLauncher = path.join(runtimeDir, "start-pixel-ops-runtime.cmd");
  const unixContent = `#!/usr/bin/env bash
set -euo pipefail
cd ${shellQuote(repoRoot)}
mkdir -p pixel_ops/output
echo $$ > pixel_ops/output/runtime.pid
exec "\${PIXEL_OPS_PYTHON:-${pythonCmd}}" pixel_ops/main.py --forever >> pixel_ops/output/runtime.log 2>&1
`;
  const windowsContent = `@echo off
cd /d "${repoRoot}"
if not exist pixel_ops\\output mkdir pixel_ops\\output
set PYTHON_CMD=%PIXEL_OPS_PYTHON%
if "%PYTHON_CMD%"=="" set PYTHON_CMD=${pythonCmd}
"%PYTHON_CMD%" pixel_ops/main.py --forever >> pixel_ops\\output\\runtime.log 2>&1
`;
  await fs.writeFile(unixLauncher, unixContent, "utf8");
  await fs.chmod(unixLauncher, 0o755);
  await fs.writeFile(windowsLauncher, windowsContent, "utf8");
  let macLauncher = unixLauncher;
  if (process.platform === "darwin") {
    const supportDir = macAutostartSupportDir();
    const logDir = macAutostartLogDir();
    await fs.mkdir(supportDir, { recursive: true });
    await fs.mkdir(logDir, { recursive: true });
    macLauncher = path.join(supportDir, "start-pixel-ops-runtime.sh");
    const macContent = `#!/usr/bin/env bash
set -euo pipefail
cd ${shellQuote(repoRoot)}
mkdir -p pixel_ops/output
echo $$ > pixel_ops/output/runtime.pid
exec "\${PIXEL_OPS_PYTHON:-${pythonCmd}}" pixel_ops/main.py --forever >> ${shellQuote(path.join(logDir, "runtime.log"))} 2>&1
`;
    await fs.writeFile(macLauncher, macContent, "utf8");
    await fs.chmod(macLauncher, 0o755);
  }
  return { unixLauncher, windowsLauncher, macLauncher };
}

async function autostartPaths() {
  const home = os.homedir();
  if (process.platform === "darwin") {
    return {
      supported: true,
      path: path.join(home, "Library/LaunchAgents/com.pixelops.runtime.plist"),
    };
  }
  if (process.platform === "win32") {
    const appData = process.env.APPDATA || path.join(home, "AppData/Roaming");
    return {
      supported: true,
      path: path.join(appData, "Microsoft/Windows/Start Menu/Programs/Startup/Pixel OPs Runtime.cmd"),
    };
  }
  if (process.platform === "linux") {
    return {
      supported: true,
      path: path.join(home, ".config/autostart/pixel-ops-runtime.desktop"),
    };
  }
  return { supported: false, path: "" };
}

async function runtimeAutostartStatus() {
  const target = await autostartPaths();
  const launchd = process.platform === "darwin" ? await macLaunchAgentStatus() : {};
  return {
    platform: process.platform,
    supported: target.supported,
    installed: target.path ? await fileExists(target.path) : false,
    path: target.path,
    ...launchd,
  };
}

async function installRuntimeAutostart() {
  const target = await autostartPaths();
  if (!target.supported || !target.path) {
    return { ok: false, message: `Autostart is not supported on ${process.platform}.`, ...(await runtimeAutostartStatus()) };
  }
  const launchers = await ensureRuntimeLaunchers();
  await fs.mkdir(path.dirname(target.path), { recursive: true });
  if (process.platform === "darwin") {
    const logDir = macAutostartLogDir();
    await fs.mkdir(logDir, { recursive: true });
    const plist = `<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>com.pixelops.runtime</string>
  <key>ProgramArguments</key>
  <array>
    <string>${xmlEscape(launchers.macLauncher)}</string>
  </array>
  <key>RunAtLoad</key>
  <true/>
  <key>WorkingDirectory</key>
  <string>${xmlEscape(macAutostartSupportDir())}</string>
  <key>StandardOutPath</key>
  <string>${xmlEscape(path.join(logDir, "runtime.launchd.log"))}</string>
  <key>StandardErrorPath</key>
  <string>${xmlEscape(path.join(logDir, "runtime.launchd.err.log"))}</string>
</dict>
</plist>
`;
    await fs.writeFile(target.path, plist, "utf8");
    await reloadMacLaunchAgent(target.path);
  } else if (process.platform === "win32") {
    await fs.writeFile(target.path, `@echo off\r\ncall "${launchers.windowsLauncher}"\r\n`, "utf8");
  } else {
    const desktop = `[Desktop Entry]
Type=Application
Name=Pixel OPs Runtime
Exec=${launchers.unixLauncher}
Path=${repoRoot}
Terminal=false
X-GNOME-Autostart-enabled=true
`;
    await fs.writeFile(target.path, desktop, "utf8");
  }
  return { ok: true, message: "Runtime autostart installed.", ...(await runtimeAutostartStatus()) };
}

async function removeRuntimeAutostart() {
  const target = await autostartPaths();
  if (process.platform === "darwin") {
    await unloadMacLaunchAgent(target.path);
  }
  if (target.path && (await fileExists(target.path))) {
    await fs.unlink(target.path);
  }
  return { ok: true, message: "Runtime autostart removed.", ...(await runtimeAutostartStatus()) };
}

function macLaunchAgentDomain() {
  return `gui/${typeof process.getuid === "function" ? process.getuid() : os.userInfo().uid}`;
}

async function macLaunchAgentStatus() {
  try {
    const { stdout } = await execFileAsync("launchctl", ["print", `${macLaunchAgentDomain()}/com.pixelops.runtime`], { maxBuffer: 1024 * 1024 });
    const lastExit = stdout.match(/last exit code = ([^\n]+)/)?.[1]?.trim();
    const state = stdout.match(/state = ([^\n]+)/)?.[1]?.trim();
    const failed = Boolean(lastExit && !lastExit.startsWith("0") && !lastExit.includes("never exited"));
    return {
      loaded: true,
      state,
      last_exit_code: lastExit,
      message: failed ? `launchd loaded, last exit ${lastExit}. Check ${path.join(macAutostartLogDir(), "runtime.launchd.err.log")}` : undefined,
    };
  } catch {
    return { loaded: false };
  }
}

async function reloadMacLaunchAgent(plistPath: string) {
  await unloadMacLaunchAgent(plistPath);
  await execFileAsync("launchctl", ["bootstrap", macLaunchAgentDomain(), plistPath]);
  await execFileAsync("launchctl", ["kickstart", "-k", `${macLaunchAgentDomain()}/com.pixelops.runtime`]);
}

async function unloadMacLaunchAgent(plistPath: string) {
  if (!plistPath) {
    return;
  }
  try {
    await execFileAsync("launchctl", ["bootout", macLaunchAgentDomain(), plistPath]);
  } catch {
    // Not loaded yet.
  }
}

async function ensureSpritePreviews() {
  const outputDir = path.join(repoRoot, "pixel_ops/cache/config_studio/npc_sprites");
  const manifestPath = path.join(outputDir, "manifest.json");
  const sourceMtimeMs = await npcSpriteSourceMtimeMs();
  try {
    const raw = await fs.readFile(manifestPath, "utf8");
    const manifest = JSON.parse(raw) as { count?: number; format_version?: number; source_mtime_ms?: number };
    if (
      typeof manifest.count === "number" &&
      manifest.format_version === npcSpritePreviewFormatVersion &&
      manifest.source_mtime_ms === sourceMtimeMs
    ) {
      return outputDir;
    }
  } catch {
    // Regenerate below.
  }
  await fs.mkdir(outputDir, { recursive: true });
  await execFileAsync(pythonCmd, ["scripts/generate_npc_sprite_previews.py", outputDir], {
    cwd: repoRoot,
  });
  return outputDir;
}

async function npcSpriteSourceMtimeMs(): Promise<number> {
  const files = [
    path.join(
      repoRoot,
      "pixel_ops/plugins/pokemon/assets/sprites/ash/Game Boy Advance - Pokemon FireRed _ LeafGreen - Trainers & Non-Playable Characters - Overworld NPCs.png",
    ),
  ];
  const newSpritesDir = path.join(repoRoot, "pixel_ops/plugins/pokemon/assets/sprites/new_sprites");
  try {
    const entries = await fs.readdir(newSpritesDir, { withFileTypes: true });
    files.push(...entries.filter((entry) => entry.isFile() && entry.name.endsWith(".png")).map((entry) => path.join(newSpritesDir, entry.name)));
  } catch {
    // Optional sprite directory.
  }
  const stats = await Promise.all(
    files.map(async (file) => {
      try {
        return await fs.stat(file);
      } catch {
        return null;
      }
    }),
  );
  return Math.max(0, ...stats.filter(Boolean).map((stat) => Math.floor(stat!.mtimeMs)));
}

async function listPokemonMaps() {
  const mapsRoot = path.join(repoRoot, "pixel_ops/plugins/pokemon/assets/maps/firered_leafgreen_clean");
  const entries: Array<{ key: string; label: string; width: number; height: number; url: string }> = [];
  async function walk(dir: string) {
    const dirEntries = await fs.readdir(dir, { withFileTypes: true });
    for (const entry of dirEntries) {
      const fullPath = path.join(dir, entry.name);
      if (entry.isDirectory()) {
        await walk(fullPath);
      } else if (entry.isFile() && entry.name.endsWith(".png")) {
        const relative = path.relative(mapsRoot, fullPath).replaceAll(path.sep, "/");
        const key = path.basename(entry.name, ".png");
        const dimensions = await pngDimensions(fullPath);
        entries.push({
          key,
          label: relative.replace(".png", ""),
          width: dimensions.width,
          height: dimensions.height,
          url: `/api/pokemon-maps/${encodeURIComponent(relative)}`,
        });
      }
    }
  }
  await walk(mapsRoot);
  return entries.sort((a, b) => a.label.localeCompare(b.label));
}

async function pngDimensions(filePath: string): Promise<{ width: number; height: number }> {
  const handle = await fs.open(filePath, "r");
  try {
    const buffer = Buffer.alloc(24);
    await handle.read(buffer, 0, 24, 0);
    return { width: buffer.readUInt32BE(16), height: buffer.readUInt32BE(20) };
  } finally {
    await handle.close();
  }
}

async function sendFile(res: ServerResponse, filePath: string, contentType: string) {
  const data = await fs.readFile(filePath);
  res.statusCode = 200;
  res.setHeader("content-type", contentType);
  res.end(data);
}

function runtimeConfigApi(): Plugin {
  return {
    name: "pixel-ops-runtime-config-api",
    configureServer(server) {
      server.middlewares.use("/api/config", async (req, res) => {
        try {
          if (req.method === "GET") {
            const url = new URL(req.url || "/", "http://localhost");
            const selectedPlugins = (url.searchParams.get("plugins") || "")
              .split(",")
              .map((item) => item.trim())
              .filter(Boolean);
            sendJson(res, 200, await loadRuntimeConfig(selectedPlugins));
            return;
          }

          if (req.method === "PUT") {
            const body = await readBody(req);
            await saveRuntimeConfig(JSON.parse(body));
            sendJson(res, 200, { ok: true });
            return;
          }

          sendJson(res, 405, { error: "Method not allowed." });
        } catch (error) {
          sendJson(res, 500, { error: error instanceof Error ? error.message : String(error) });
        }
      });
      server.middlewares.use("/api/config-manifest", async (_req, res) => {
        try {
          sendJson(res, 200, await buildConfigManifest());
        } catch (error) {
          sendJson(res, 500, { error: error instanceof Error ? error.message : String(error) });
        }
      });
      server.middlewares.use("/api/discord", async (req, res) => {
        try {
          const url = new URL(req.url || "/", "http://localhost");
          if (req.method === "POST" && url.pathname === "/oauth/start") {
            const body = JSON.parse(await readBody(req)) as { client_id?: string; client_secret_env?: string; token_env?: string };
            sendJson(res, 200, startDiscordOAuth(body.client_id || "", body.client_secret_env || "PIXEL_OPS_DISCORD_CLIENT_SECRET", body.token_env || "PIXEL_OPS_DISCORD_USER_TOKEN"));
            return;
          }
          if (req.method === "GET" && url.pathname === "/oauth/status") {
            const state = url.searchParams.get("state") || "";
            const session = discordOAuthSessions.get(state);
            if (!session) {
              sendJson(res, 404, { status: "error", message: "Discord OAuth session not found." });
              return;
            }
            sendJson(res, 200, {
              status: session.status,
              message: session.message,
              token_env: session.token_env,
              user: session.user,
              guilds: session.guilds ?? [],
            });
            return;
          }
          if (req.method === "GET" && url.pathname === "/oauth/callback") {
            const state = url.searchParams.get("state") || "";
            const code = url.searchParams.get("code") || "";
            const error = url.searchParams.get("error") || "";
            const session = discordOAuthSessions.get(state);
            if (error) {
              if (session) {
                session.status = "error";
                session.message = error;
              }
              sendOAuthCallbackHtml(res, "Discord authorization failed.");
              return;
            }
            if (!code || !state) {
              if (session) {
                session.status = "error";
                session.message = "Missing Discord OAuth code or state.";
              }
              sendOAuthCallbackHtml(res, "Missing Discord OAuth code or state.");
              return;
            }
            try {
              await completeDiscordOAuth(code, state);
              sendOAuthCallbackHtml(res, "Discord authorized. You can close this window.");
            } catch (callbackError) {
              if (session) {
                session.status = "error";
                session.message = callbackError instanceof Error ? callbackError.message : String(callbackError);
              }
              sendOAuthCallbackHtml(res, callbackError instanceof Error ? callbackError.message : String(callbackError));
            }
            return;
          }
          if (req.method === "POST" && url.pathname === "/token") {
            const body = JSON.parse(await readBody(req)) as { token_env?: string; token?: string };
            const tokenEnv = body.token_env || "PIXEL_OPS_DISCORD_BOT_TOKEN";
            const token = (body.token || "").trim();
            if (!token) {
              sendJson(res, 400, { error: "Token is required." });
              return;
            }
            await writeDotEnvValue(tokenEnv, token);
            sendJson(res, 200, { ok: true, token_env: tokenEnv });
            return;
          }
          if (req.method === "GET" && url.pathname === "/profile") {
            const tokenEnv = url.searchParams.get("token_env") || "PIXEL_OPS_DISCORD_USER_TOKEN";
            sendJson(res, 200, await loadDiscordProfile(tokenEnv));
            return;
          }
          sendJson(res, 404, { error: "Discord endpoint not found." });
        } catch (error) {
          sendJson(res, 500, { error: error instanceof Error ? error.message : String(error) });
        }
      });
      server.middlewares.use("/api/github", async (req, res) => {
        try {
          const url = new URL(req.url || "/", "http://localhost");
          if (req.method === "POST" && url.pathname === "/device/start") {
            const body = JSON.parse(await readBody(req)) as { client_id?: string };
            sendJson(res, 200, await startGithubDeviceLogin(body.client_id || ""));
            return;
          }
          if (req.method === "POST" && url.pathname === "/device/poll") {
            const body = JSON.parse(await readBody(req)) as { client_id?: string; device_code?: string; token_env?: string };
            sendJson(res, 200, await pollGithubDeviceLogin(body.client_id || "", body.device_code || "", body.token_env || "PIXEL_OPS_GITHUB_TOKEN"));
            return;
          }
          if (req.method === "POST" && url.pathname === "/token") {
            const body = JSON.parse(await readBody(req)) as { token_env?: string; token?: string };
            const tokenEnv = body.token_env || "PIXEL_OPS_GITHUB_TOKEN";
            const token = (body.token || "").trim();
            if (!token) {
              sendJson(res, 400, { error: "Token is required." });
              return;
            }
            await writeDotEnvValue(tokenEnv, token);
            sendJson(res, 200, { ok: true, token_env: tokenEnv });
            return;
          }
          if (req.method === "GET" && url.pathname === "/repos") {
            const tokenEnv = url.searchParams.get("token_env") || "PIXEL_OPS_GITHUB_TOKEN";
            sendJson(res, 200, await listGithubRepos(tokenEnv));
            return;
          }
          sendJson(res, 404, { error: "GitHub endpoint not found." });
        } catch (error) {
          sendJson(res, 500, { error: error instanceof Error ? error.message : String(error) });
        }
      });
      server.middlewares.use("/api/crosshero", async (req, res) => {
        try {
          const url = new URL(req.url || "/", "http://localhost");
          if (req.method === "GET" && url.pathname === "/session-status") {
            const env = await readDotEnv();
            const configured = Boolean(process.env.PIXEL_OPS_CROSSHERO_SESSION_COOKIE || env.PIXEL_OPS_CROSSHERO_SESSION_COOKIE);
            sendJson(res, 200, {
              ok: true,
              configured,
              message: configured ? "Sessão do CrossHero configurada." : "Sessão do CrossHero ainda não importada.",
            });
            return;
          }
          if (req.method === "POST" && url.pathname === "/browser-session") {
            const body = JSON.parse(await readBody(req)) as { cookie?: string };
            const cookie = String(body.cookie || "").trim();
            if (!cookie || cookie.length > 16384 || !cookie.includes("=")) {
              sendJson(res, 400, { error: "Cookie do CrossHero inválido." });
              return;
            }
            await writeDotEnvValue("PIXEL_OPS_CROSSHERO_SESSION_COOKIE", cookie);
            sendJson(res, 200, {
              ok: true,
              configured: true,
              message: "Sessão do CrossHero importada com segurança para o .env.",
            });
            return;
          }
          sendJson(res, 404, { error: "CrossHero endpoint not found." });
        } catch (error) {
          sendJson(res, 500, { error: error instanceof Error ? error.message : String(error) });
        }
      });
      server.middlewares.use("/api/kite", async (req, res) => {
        try {
          const url = new URL(req.url || "/", "http://localhost");
          if (req.method === "GET" && url.pathname === "/status") {
            sendJson(res, 200, await kiteStatus());
            return;
          }
          if (req.method === "POST" && url.pathname === "/install") {
            sendJson(res, 200, await kiteInstall());
            return;
          }
          if (req.method === "POST" && url.pathname === "/secrets") {
            const body = JSON.parse(await readBody(req)) as { kite_token?: string; zoom_webhook_secret_token?: string };
            sendJson(res, 200, await configureKiteSecrets(body));
            return;
          }
          if (req.method === "POST" && url.pathname === "/deploy") {
            sendJson(res, 200, await kiteDeploy());
            return;
          }
          sendJson(res, 404, { error: "PixelOpsKite endpoint not found." });
        } catch (error) {
          sendJson(res, 500, { error: error instanceof Error ? error.message : String(error) });
        }
      });
      server.middlewares.use("/api/runtime", async (req, res) => {
        try {
          const url = new URL(req.url || "/", "http://localhost");
          if (req.method === "GET" && url.pathname === "/status") {
            sendJson(res, 200, await runtimeStatus());
            return;
          }
          if (req.method === "POST" && url.pathname === "/check") {
            const script = process.platform === "win32" ? "scripts/windows_check.py" : "scripts/linux_check.py";
            sendJson(res, 200, await runRuntimeCommand([script]));
            return;
          }
          if (req.method === "POST" && url.pathname === "/preview") {
            sendJson(res, 200, await runRuntimeCommand(["pixel_ops/main.py", "--output", "preview", "--offline"]));
            return;
          }
          if (req.method === "POST" && url.pathname === "/run/start") {
            sendJson(res, 200, await startRuntime("configured"));
            return;
          }
          if (req.method === "POST" && url.pathname === "/run/stop") {
            sendJson(res, 200, await stopRuntimeWindow());
            return;
          }
          if (req.method === "POST" && url.pathname === "/window/start") {
            sendJson(res, 200, await startRuntimeWindow());
            return;
          }
          if (req.method === "POST" && url.pathname === "/window/stop") {
            sendJson(res, 200, await stopRuntimeWindow());
            return;
          }
          if (req.method === "GET" && url.pathname === "/autostart/status") {
            sendJson(res, 200, await runtimeAutostartStatus());
            return;
          }
          if (req.method === "POST" && url.pathname === "/autostart/install") {
            sendJson(res, 200, await installRuntimeAutostart());
            return;
          }
          if (req.method === "POST" && url.pathname === "/autostart/remove") {
            sendJson(res, 200, await removeRuntimeAutostart());
            return;
          }
          sendJson(res, 404, { error: "Runtime endpoint not found." });
        } catch (error) {
          sendJson(res, 500, { error: error instanceof Error ? error.message : String(error), ...(await runtimeStatus()) });
        }
      });
      server.middlewares.use("/api/firmware", async (req, res) => {
        try {
          const url = new URL(req.url || "/", "http://localhost");
          if (req.method === "GET" && url.pathname === "/status") {
            sendJson(res, 200, await firmwareStatus());
            return;
          }
          if (req.method === "POST" && url.pathname === "/build") {
            sendJson(res, 202, await startFirmwareOperation("build"));
            return;
          }
          if (req.method === "POST" && url.pathname === "/upload") {
            const body = JSON.parse(await readBody(req)) as { port?: string };
            sendJson(res, 202, await startFirmwareOperation("upload", body.port));
            return;
          }
          sendJson(res, 404, { error: "Firmware endpoint not found." });
        } catch (error) {
          sendJson(res, 400, { error: error instanceof Error ? error.message : String(error), ...(await firmwareStatus()) });
        }
      });
      server.middlewares.use("/api/usb", async (req, res) => {
        try {
          const url = new URL(req.url || "/", "http://localhost");
          if (req.method === "POST" && url.pathname === "/thermalright/scan") {
            sendJson(res, 200, await scanThermalrightUsbDisplays());
            return;
          }
          if (req.method === "POST" && url.pathname === "/thermalright/identify") {
            const body = JSON.parse(await readBody(req)) as Record<string, unknown>;
            sendJson(res, 200, await identifyThermalrightDisplay(body));
            return;
          }
          sendJson(res, 404, { error: "USB endpoint not found." });
        } catch (error) {
          sendJson(res, 500, { error: error instanceof Error ? error.message : String(error) });
        }
      });
      server.middlewares.use("/api/npc-sprites", async (req, res) => {
        try {
          const outputDir = await ensureSpritePreviews();
          const url = req.url || "/";
          if (url === "/" || url === "") {
            const raw = await fs.readFile(path.join(outputDir, "manifest.json"), "utf8");
            sendJson(res, 200, JSON.parse(raw));
            return;
          }
          const match = url.match(/^\/(\d+)\.gif$/);
          if (!match) {
            sendJson(res, 404, { error: "Sprite preview not found." });
            return;
          }
          await sendFile(res, path.join(outputDir, `${match[1]}.gif`), "image/gif");
        } catch (error) {
          sendJson(res, 500, { error: error instanceof Error ? error.message : String(error) });
        }
      });
      server.middlewares.use("/api/pokemon-maps", async (req, res) => {
        try {
          const mapsRoot = path.join(repoRoot, "pixel_ops/plugins/pokemon/assets/maps/firered_leafgreen_clean");
          const url = req.url || "/";
          if (url === "/" || url === "") {
            sendJson(res, 200, { maps: await listPokemonMaps() });
            return;
          }
          const relative = decodeURIComponent(url.replace(/^\//, ""));
          const target = path.normalize(path.join(mapsRoot, relative));
          if (!target.startsWith(mapsRoot) || !target.endsWith(".png")) {
            sendJson(res, 404, { error: "Map not found." });
            return;
          }
          await sendFile(res, target, "image/png");
        } catch (error) {
          sendJson(res, 500, { error: error instanceof Error ? error.message : String(error) });
        }
      });
    },
  };
}

export default defineConfig({
  plugins: [react(), runtimeConfigApi()],
  server: {
    port: 5174,
    strictPort: false,
  },
});
