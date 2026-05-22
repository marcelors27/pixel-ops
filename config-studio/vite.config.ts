import react from "@vitejs/plugin-react";
import { promises as fs } from "node:fs";
import path from "node:path";
import type { IncomingMessage, ServerResponse } from "node:http";
import { defineConfig, type Plugin } from "vite";

const repoRoot = path.resolve(__dirname, "..");

const configFiles = {
  display: "pixel_ops/config/display.json",
  integrations: "pixel_ops/config/integrations.json",
  people: "pixel_ops/config/people.json",
  game: "pixel_ops/plugins/pokemon/game.json",
  pokemon: "pixel_ops/plugins/pokemon/pokemon.json",
} as const;

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

async function loadRuntimeConfig() {
  const entries = await Promise.all(
    Object.entries(configFiles).map(async ([key, relativePath]) => {
      const raw = await fs.readFile(path.join(repoRoot, relativePath), "utf8");
      return [key, JSON.parse(raw)] as const;
    }),
  );
  return Object.fromEntries(entries);
}

async function saveRuntimeConfig(payload: unknown) {
  if (!payload || typeof payload !== "object" || Array.isArray(payload)) {
    throw new Error("Invalid config payload.");
  }

  const record = payload as Record<string, unknown>;
  await Promise.all(
    Object.entries(configFiles).map(async ([key, relativePath]) => {
      if (!(key in record)) return;
      const target = path.join(repoRoot, relativePath);
      await fs.writeFile(target, `${JSON.stringify(record[key], null, 2)}\n`, "utf8");
    }),
  );
}

function runtimeConfigApi(): Plugin {
  return {
    name: "pixel-ops-runtime-config-api",
    configureServer(server) {
      server.middlewares.use("/api/config", async (req, res) => {
        try {
          if (req.method === "GET") {
            sendJson(res, 200, await loadRuntimeConfig());
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
