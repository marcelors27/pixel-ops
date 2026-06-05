import type {
  ConfigManifest,
  DiscordOAuthStartResponse,
  DiscordOAuthStatusResponse,
  DiscordProfileResponse,
  GitHubDevicePollResponse,
  GitHubDeviceStartResponse,
  GitHubReposResponse,
  KiteActionResult,
  NpcSpriteManifest,
  RuntimeConfig,
  RuntimeStatus,
  UsbValidationResult,
} from "../types";

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

export async function loadKiteStatus(): Promise<KiteActionResult> {
  const response = await fetch("/api/kite/status");
  if (!response.ok) {
    throw new Error(await response.text());
  }
  return response.json() as Promise<KiteActionResult>;
}

export async function runKiteAction(action: "install" | "deploy"): Promise<KiteActionResult> {
  const response = await fetch(`/api/kite/${action}`, { method: "POST" });
  if (!response.ok) {
    throw new Error(await response.text());
  }
  return response.json() as Promise<KiteActionResult>;
}

export async function configureKiteSecrets(kiteToken: string, zoomWebhookSecretToken: string): Promise<KiteActionResult> {
  const response = await fetch("/api/kite/secrets", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ kite_token: kiteToken, zoom_webhook_secret_token: zoomWebhookSecretToken }),
  });
  if (!response.ok) {
    throw new Error(await response.text());
  }
  return response.json() as Promise<KiteActionResult>;
}

export async function scanUsbDisplays(): Promise<UsbValidationResult> {
  const response = await fetch("/api/usb/thermalright/scan", { method: "POST" });
  if (!response.ok) {
    throw new Error(await response.text());
  }
  return response.json() as Promise<UsbValidationResult>;
}

export async function identifyUsbDisplay(display: unknown): Promise<UsbValidationResult> {
  const response = await fetch("/api/usb/thermalright/identify", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(display),
  });
  if (!response.ok) {
    throw new Error(await response.text());
  }
  return response.json() as Promise<UsbValidationResult>;
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

export async function saveDiscordBotToken(tokenEnv: string, token: string): Promise<void> {
  const response = await fetch("/api/discord/token", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ token_env: tokenEnv, token }),
  });
  if (!response.ok) {
    throw new Error(await response.text());
  }
}

export async function loadDiscordProfile(tokenEnv: string): Promise<DiscordProfileResponse> {
  const params = new URLSearchParams({ token_env: tokenEnv });
  const response = await fetch(`/api/discord/profile?${params.toString()}`);
  if (!response.ok) {
    throw new Error(await response.text());
  }
  return response.json() as Promise<DiscordProfileResponse>;
}

export async function startDiscordOAuth(clientId: string, clientSecretEnv: string, tokenEnv: string): Promise<DiscordOAuthStartResponse> {
  const response = await fetch("/api/discord/oauth/start", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ client_id: clientId, client_secret_env: clientSecretEnv, token_env: tokenEnv }),
  });
  if (!response.ok) {
    throw new Error(await response.text());
  }
  return response.json() as Promise<DiscordOAuthStartResponse>;
}

export async function pollDiscordOAuthStatus(state: string): Promise<DiscordOAuthStatusResponse> {
  const params = new URLSearchParams({ state });
  const response = await fetch(`/api/discord/oauth/status?${params.toString()}`);
  if (!response.ok) {
    throw new Error(await response.text());
  }
  return response.json() as Promise<DiscordOAuthStatusResponse>;
}
