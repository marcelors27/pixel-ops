import type { ConfigManifest, GitHubDevicePollResponse, GitHubDeviceStartResponse, GitHubReposResponse, NpcSpriteManifest, RuntimeConfig, RuntimeStatus } from "../types";

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

export async function loadRuntimeStatus(): Promise<RuntimeStatus> {
  const response = await fetch("/api/runtime/status");
  if (!response.ok) {
    throw new Error(await response.text());
  }
  return response.json() as Promise<RuntimeStatus>;
}

export async function loadNpcSpriteManifest(): Promise<NpcSpriteManifest> {
  const response = await fetch("/api/npc-sprites");
  if (!response.ok) {
    throw new Error(await response.text());
  }
  return response.json() as Promise<NpcSpriteManifest>;
}

export async function runRuntimeAction(action: "check" | "preview" | "window/start" | "window/stop"): Promise<RuntimeStatus> {
  const response = await fetch(`/api/runtime/${action}`, { method: "POST" });
  if (!response.ok) {
    throw new Error(await response.text());
  }
  return response.json() as Promise<RuntimeStatus>;
}

export async function saveGithubToken(tokenEnv: string, token: string): Promise<void> {
  const response = await fetch("/api/github/token", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ token_env: tokenEnv, token }),
  });
  if (!response.ok) {
    throw new Error(await response.text());
  }
}

export async function loadGithubRepos(tokenEnv: string): Promise<GitHubReposResponse> {
  const params = new URLSearchParams({ token_env: tokenEnv });
  const response = await fetch(`/api/github/repos?${params.toString()}`);
  if (!response.ok) {
    throw new Error(await response.text());
  }
  return response.json() as Promise<GitHubReposResponse>;
}

export async function startGithubDeviceLogin(clientId: string): Promise<GitHubDeviceStartResponse> {
  const response = await fetch("/api/github/device/start", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ client_id: clientId }),
  });
  if (!response.ok) {
    throw new Error(await response.text());
  }
  return response.json() as Promise<GitHubDeviceStartResponse>;
}

export async function pollGithubDeviceLogin(clientId: string, deviceCode: string, tokenEnv: string): Promise<GitHubDevicePollResponse> {
  const response = await fetch("/api/github/device/poll", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ client_id: clientId, device_code: deviceCode, token_env: tokenEnv }),
  });
  if (!response.ok) {
    throw new Error(await response.text());
  }
  return response.json() as Promise<GitHubDevicePollResponse>;
}
