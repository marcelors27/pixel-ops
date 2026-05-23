import type { ConfigManifest, RuntimeConfig } from "../types";

export async function loadConfig(plugins: string[] = []): Promise<RuntimeConfig> {
  const params = new URLSearchParams();
  if (plugins.length) {
    params.set("plugins", plugins.join(","));
  }
  const response = await fetch(`/api/config${params.size ? `?${params.toString()}` : ""}`);
  if (!response.ok) {
    throw new Error(await response.text());
  }
  return response.json() as Promise<RuntimeConfig>;
}

export async function loadConfigManifest(): Promise<ConfigManifest> {
  const response = await fetch("/api/config-manifest");
  if (!response.ok) {
    throw new Error(await response.text());
  }
  return response.json() as Promise<ConfigManifest>;
}

export async function saveConfig(config: RuntimeConfig): Promise<void> {
  const response = await fetch("/api/config", {
    method: "PUT",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(config),
  });

  if (!response.ok) {
    throw new Error(await response.text());
  }
}

export function cloneConfig(config: RuntimeConfig): RuntimeConfig {
  return structuredClone(config);
}
