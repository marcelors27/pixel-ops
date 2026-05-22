import type { RuntimeConfig } from "../types";

export async function loadConfig(): Promise<RuntimeConfig> {
  const response = await fetch("/api/config");
  if (!response.ok) {
    throw new Error(await response.text());
  }
  return response.json() as Promise<RuntimeConfig>;
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
