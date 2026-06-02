import react from "@vitejs/plugin-react";
import { execFile, execFileSync, spawn, type ChildProcessWithoutNullStreams } from "node:child_process";
import { promises as fs } from "node:fs";
import path from "node:path";
import type { IncomingMessage, ServerResponse } from "node:http";
import { promisify } from "node:util";
import { defineConfig, type Plugin } from "vite";

const repoRoot = path.resolve(__dirname, "..");
const execFileAsync = promisify(execFile);
const pythonCmd = resolvePythonCommand();
let runtimeProcess: ChildProcessWithoutNullStreams | null = null;
const runtimeLogs: string[] = [];
const npcSpritePreviewFormatVersion = 2;

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
  ai_usage: [{ kind: "gauges", label: "AI Gauges", tone: "#7ee0bd" }],
  pc_stats: [{ kind: "pc_stats", label: "PC Stats", tone: "#9bd0ff" }],
  weather: [{ kind: "weather", label: "Weather", tone: "#e8c766" }],
  clickup: [
    { kind: "tasks", label: "Tasks", tone: "#b58cff" },
    { kind: "tasks_board", label: "Tasks Board", tone: "#f0a35d" },
  ],
  todoist: [
    { kind: "tasks", label: "Tasks", tone: "#b58cff" },
    { kind: "tasks_board", label: "Tasks Board", tone: "#f0a35d" },
  ],
  media: [{ kind: "media", label: "Now Playing", tone: "#6ee7b7" }],
};

const visualPluginLayoutWindows: Record<string, LayoutWindowDescriptor[]> = {
  pokemon: [
    { kind: "route_signal", label: "Route", tone: "#f0a35d" },
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
      execFileSync(candidate, ["-c", "import PIL, yaml, requests"], {
        cwd: repoRoot,
        stdio: "ignore",
      });
      return candidate;
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

function pushRuntimeLog(value: string) {
  const clean = value.replace(/\r\n/g, "\n").trimEnd();
  if (!clean) return;
  runtimeLogs.push(...clean.split("\n"));
  while (runtimeLogs.length > 240) {
    runtimeLogs.shift();
  }
}

function runtimeStatus() {
  return {
    running: runtimeProcess !== null,
    pid: runtimeProcess?.pid ?? null,
    logs: runtimeLogs.slice(-80),
  };
}

async function runRuntimeCommand(args: string[]) {
  try {
    const { stdout, stderr } = await execFileAsync(pythonCmd, args, {
      cwd: repoRoot,
      maxBuffer: 1024 * 1024 * 4,
    });
    pushRuntimeLog(stdout);
    pushRuntimeLog(stderr);
    return { ok: true, stdout, stderr, ...runtimeStatus() };
  } catch (error) {
    const err = error as Error & { stdout?: string; stderr?: string };
    pushRuntimeLog(err.stdout || "");
    pushRuntimeLog(err.stderr || err.message);
    return { ok: false, stdout: err.stdout || "", stderr: err.stderr || err.message, ...runtimeStatus() };
  }
}

function startRuntimeWindow() {
  if (runtimeProcess) {
    return runtimeStatus();
  }
  runtimeProcess = spawn(
    pythonCmd,
    ["pixel_ops/main.py", "--plugin", "pokemon", "--output", "window", "--forever", "--offline"],
    {
      cwd: repoRoot,
      env: { ...process.env, PYTHONUNBUFFERED: "1" },
    },
  );
  pushRuntimeLog(`Started window runtime pid=${runtimeProcess.pid ?? "unknown"}`);
  runtimeProcess.stdout.on("data", (chunk) => pushRuntimeLog(String(chunk)));
  runtimeProcess.stderr.on("data", (chunk) => pushRuntimeLog(String(chunk)));
  runtimeProcess.on("exit", (code, signal) => {
    pushRuntimeLog(`Window runtime exited code=${code ?? "-"} signal=${signal ?? "-"}`);
    runtimeProcess = null;
  });
  return runtimeStatus();
}

function stopRuntimeWindow() {
  if (!runtimeProcess) {
    return runtimeStatus();
  }
  pushRuntimeLog(`Stopping window runtime pid=${runtimeProcess.pid ?? "unknown"}`);
  runtimeProcess.kill();
  runtimeProcess = null;
  return runtimeStatus();
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
      server.middlewares.use("/api/runtime", async (req, res) => {
        try {
          const url = new URL(req.url || "/", "http://localhost");
          if (req.method === "GET" && url.pathname === "/status") {
            sendJson(res, 200, runtimeStatus());
            return;
          }
          if (req.method === "POST" && url.pathname === "/check") {
            const script = process.platform === "win32" ? "scripts/windows_check.py" : "scripts/linux_check.py";
            sendJson(res, 200, await runRuntimeCommand([script]));
            return;
          }
          if (req.method === "POST" && url.pathname === "/preview") {
            sendJson(res, 200, await runRuntimeCommand(["pixel_ops/main.py", "--plugin", "pokemon", "--output", "preview", "--offline"]));
            return;
          }
          if (req.method === "POST" && url.pathname === "/window/start") {
            sendJson(res, 200, startRuntimeWindow());
            return;
          }
          if (req.method === "POST" && url.pathname === "/window/stop") {
            sendJson(res, 200, stopRuntimeWindow());
            return;
          }
          sendJson(res, 404, { error: "Runtime endpoint not found." });
        } catch (error) {
          sendJson(res, 500, { error: error instanceof Error ? error.message : String(error), ...runtimeStatus() });
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
