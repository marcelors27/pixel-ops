export type ConfigDescriptor = {
  key: keyof RuntimeConfig | string;
  label: string;
  relativePath: string;
  scope: "core" | "integration" | "plugin";
  owner?: string;
};

export type DetectedPlugin = {
  key: string;
  label: string;
  configKeys: string[];
  configs: ConfigDescriptor[];
  layoutWindows?: LayoutWindowOption[];
};

export type ConfigManifest = {
  core: ConfigDescriptor[];
  integrations: DetectedPlugin[];
  visualPlugins: DetectedPlugin[];
};

export type RuntimeConfig = {
  display: {
    display: {
      width: number;
      height: number;
      orientation?: string;
      orientations?: Record<
        string,
        {
          width?: number;
          height?: number;
          layout?: Record<LayoutKey, LayoutBox>;
        }
      >;
      device: {
        target: string;
        output: string;
        window_scale: number;
        seconds: number;
        forever: boolean;
        preview_sequence: boolean;
        full_frame: boolean;
      };
      layout: Record<LayoutKey, LayoutBox>;
      backend: string;
      fps: number;
      preview_output: string;
      gif_output: string;
      scanlines: boolean;
      timezone_primary: string;
      ai: {
        enabled: boolean;
        provider: string;
        model: string;
        reasoning_effort: string;
        api_key_env: string;
        timeout_seconds: number;
        cache_enabled: boolean;
        cache_dir: string;
      };
      splash: {
        enabled: boolean;
        seconds: number;
        logo_path: string;
        background: number[];
      };
    };
  };
  integrations: {
    integrations: Record<string, unknown> & {
      social_bus_limit: number;
      slack: IntegrationToggle & {
        app_token_env: string;
        bot_token_env: string;
        bot_user_id: string;
        socket_reconnect_seconds: number;
      };
      discord: IntegrationToggle & {
        bot_token_env: string;
        guild_id: string;
        focus_user_id: string;
        max_companions: number;
        gateway_reconnect_seconds: number;
      };
      github: IntegrationToggle & {
        token_env: string;
        repos: string[];
        poll_seconds: number;
        max_pull_requests: number;
        fetch_pull_requests: number;
        fetch_deployments: boolean;
        deployment_workflows: string[];
        startup_lookback_seconds: number;
        timeout_seconds: number;
      };
      google_calendar: IntegrationToggle & {
        calendar_id: string;
        credentials_path: string;
        token_path: string;
        ics_urls: string[];
        poll_seconds: number;
      };
      ics: IntegrationToggle & {
        paths: string[];
        poll_seconds: number;
      };
      weather: IntegrationToggle & {
        provider: string;
        city: string;
        country_code: string;
        poll_seconds: number;
        timeout_seconds: number;
        api_key_env: string;
      };
      ai_usage: IntegrationToggle & {
        providers: string[];
        poll_seconds: number;
        codex_home: string;
        claude_projects_path: string;
        openai_admin_key_env: string;
        openai_api_monthly_budget_usd: number;
        thresholds: number[];
        timeout_seconds: number;
      };
      pc_stats: IntegrationToggle & {
        fields: string[];
        poll_seconds: number;
        top_process_count: number;
        disk_path: string;
      };
    };
  };
  discord_people?: {
    discord_people: {
      max_recent: number;
      people: Record<string, DiscordPersonConfig>;
    };
  };
  people: {
    people: PersonConfig[];
  };
  game?: {
    game: {
      fps: number;
      static_background: boolean;
      require_ash_sprite: boolean;
      map_switch_seconds: number;
      route_speed_px: number;
      vertical_wander_px: number;
      movement: MovementConfig;
      hud_height: number;
      text_box_height: number;
      events: {
        mock_events: boolean;
        queue_limit: number;
        knowledge_path: string;
        ai_selector: {
          enabled: boolean;
          async: boolean;
          ambient: boolean;
          candidate_limit: number;
          throttle: {
            enabled: boolean;
            cooldown_seconds: number;
            window_seconds: number;
            max_requests_per_window: number;
            max_pending: number;
            skip_sources: string[];
            skip_categories: string[];
          };
        };
        repo_biomes: Record<string, string[]>;
        event_pokemon_types: Record<string, string[]>;
      };
    };
  };
  pokemon?: {
    pokemon: {
      api_base_url: string;
      sprite_base_url: string;
      cache_dir: string;
      generation_limit: number;
      sprite_style: string;
      network_timeout_seconds: number;
      offline: boolean;
      lazy_download: boolean;
    };
  };
  pokemon_companions?: {
    companions: {
      discord: Record<string, PokemonCompanionConfig>;
    };
  };
};

export type LayoutKey = string;

export type LayoutWindowOption = {
  kind: string;
  label: string;
  tone: string;
};

export type LayoutBox = {
  kind?: string;
  x: number;
  y: number;
  width: number;
  height: number;
};

export type MovementRect = {
  map: string;
  x: number;
  y: number;
  w: number;
  h: number;
};

export type MovementActorConfig = {
  source_rects: MovementRect[];
  avoid_source_rects?: MovementRect[];
};

export type MovementConfig = {
  debug_overlay: boolean;
  walkable: MovementActorConfig;
  blocked: {
    source_rects: MovementRect[];
  };
};

export type IntegrationToggle = {
  enabled: boolean;
};

export type DiscordPersonConfig = {
  display_name: string;
  nicknames: string[];
  last_seen_at: string;
};

export type PokemonCompanionConfig = {
  sprite_variant: number | null;
  label: string;
};

export type PersonConfig = {
  key: string;
  name: string;
  country: string;
  show_flag?: boolean;
  timezone: string;
  timezone_label: string;
  standard_key?: string;
  daylight_key?: string;
  work_start: string;
  work_end: string;
};
