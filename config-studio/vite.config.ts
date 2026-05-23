import react from "@vitejs/plugin-react";
import { execFile } from "node:child_process";
import { promises as fs } from "node:fs";
import path from "node:path";
import type { IncomingMessage, ServerResponse } from "node:http";
import { promisify } from "node:util";
import { defineConfig, type Plugin } from "vite";

const repoRoot = path.resolve(__dirname, "..");
const execFileAsync = promisify(execFile);

type ConfigDescriptor = {
  key: string;
  label: string;
  relativePath: string;
  scope: "core" | "integration" | "plugin";
  owner?: string;
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

async function ensureSpritePreviews() {
  const outputDir = path.join(repoRoot, "pixel_ops/cache/config_studio/npc_sprites");
  const manifestPath = path.join(outputDir, "manifest.json");
  try {
    const raw = await fs.readFile(manifestPath, "utf8");
    const manifest = JSON.parse(raw) as { count?: number };
    if (manifest.count === 55) {
      return outputDir;
    }
  } catch {
    // Regenerate below.
  }
  await fs.mkdir(outputDir, { recursive: true });
  await execFileAsync("python3", ["scripts/generate_npc_sprite_previews.py", outputDir], {
    cwd: repoRoot,
  });
  return outputDir;
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
