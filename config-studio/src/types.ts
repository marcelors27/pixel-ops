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

export type RuntimeStatus = {
  running: boolean;
  pid: number | null;
  logs: string[];
  ok?: boolean;
  stdout?: string;
  stderr?: string;
};

export type RuntimeAutostartStatus = {
  platform: string;
  supported: boolean;
  installed: boolean;
  path: string;
  loaded?: boolean;
  state?: string;
  last_exit_code?: string;
  ok?: boolean;
  message?: string;
};

export type KiteActionResult = {
  ok: boolean;
  message: string;
  stdout?: string;
  stderr?: string;
  worker_url?: string;
  ws_url?: string;
  files?: Record<string, boolean>;
  local_token_set?: boolean;
};

export type UsbValidationResult = {
  ok: boolean;
  message: string;
  devices?: Array<{
    target?: string;
    vid: string;
    pid: string;
    manufacturer: string;
    product: string;
    serial_number: string;
    bus: number | null;
    address: number | null;
    has_default_endpoints: boolean;
  }>;
  stdout?: string;
  stderr?: string;
};

export type DisplayOutputConfig = {
  id: string;
  label: string;
  enabled: boolean;
  target: string;
  output: string;
  x: number;
  y: number;
  width: number;
  height: number;
  rotation?: 0 | 90 | 180 | 270;
  identify_number: number;
  thermalright?: {
    vid: string;
    pid: string;
    serial_number?: string;
    bus?: number | null;
    address?: number | null;
    timeout_ms: number;
    jpeg_quality: number;
    image_width: number;
    image_height: number;
    min_frame_interval_ms?: number;
    packet_delay_ms?: number;
    packet_size?: number;
    hard_reset_on_start?: boolean;
    hard_reset_wait_ms?: number;
    handshake_on_first_frame?: boolean;
    require_handshake?: boolean;
    send_start_init?: boolean;
    read_start_ack?: boolean;
    read_frame_ack?: boolean;
    start_retries?: number;
    frame_retries?: number;
    debug: boolean;
  };
  turzx?: {
    vid?: string;
    pid?: string;
    serial_number?: string;
    bus?: number | null;
    address?: number | null;
    timeout_ms?: number;
  };
};

export type LayoutProfileConfig = {
  label: string;
  saved_at: string;
  width: number;
  height: number;
  layout_theme?: string;
  device: {
    target: string;
    output: string;
    displays: DisplayOutputConfig[];
  };
  layout: Record<LayoutKey, LayoutBox>;
};

export type GitHubRepoOption = {
  full_name: string;
  private: boolean;
  permissions: Record<string, boolean>;
};

export type GitHubReposResponse = {
  viewer: string;
  repos: GitHubRepoOption[];
};

export type GitHubDeviceStartResponse = {
  device_code: string;
  user_code: string;
  verification_uri: string;
  expires_in: number;
  interval: number;
};

export type GitHubDevicePollResponse = {
  status: "authorized" | "authorization_pending" | "slow_down";
  token_env?: string;
  scope?: string;
  interval?: number;
  message?: string;
};

export type DiscordGuildOption = {
  id: string;
  name: string;
  owner: boolean;
  permissions: string;
};

export type DiscordOAuthStartResponse = {
  state: string;
  authorize_url: string;
  redirect_uri: string;
};

export type DiscordOAuthStatusResponse = {
  status: "pending" | "authorized" | "error";
  message?: string;
  token_env?: string;
  user?: {
    id: string;
    username: string;
    global_name?: string;
  };
  guilds?: DiscordGuildOption[];
};

export type DiscordProfileResponse = {
  user: {
    id: string;
    username: string;
    global_name?: string;
  };
  guilds: DiscordGuildOption[];
};

export type NpcSpriteManifest = {
  count: number;
  variants: number[];
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
        thermalright?: {
          vid: string;
          pid: string;
          serial_number?: string;
          bus?: number | null;
          address?: number | null;
          timeout_ms: number;
          jpeg_quality: number;
          image_width: number;
          image_height: number;
          min_frame_interval_ms?: number;
          packet_delay_ms?: number;
          packet_size?: number;
          hard_reset_on_start?: boolean;
          hard_reset_wait_ms?: number;
          handshake_on_first_frame?: boolean;
          require_handshake?: boolean;
          send_start_init?: boolean;
          read_start_ack?: boolean;
          read_frame_ack?: boolean;
          start_retries?: number;
          frame_retries?: number;
          debug: boolean;
        };
        turzx?: {
          vid?: string;
          pid?: string;
          serial_number?: string;
          bus?: number | null;
          address?: number | null;
          timeout_ms?: number;
        };
        displays?: DisplayOutputConfig[];
      };
      layout: Record<LayoutKey, LayoutBox>;
      layout_theme?: string;
      layout_profiles?: Record<string, LayoutProfileConfig>;
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
      gamification?: {
        max_hp: number;
        meeting_cost: number;
        task_delivered_cost: number;
        base_recovery_per_hour: number;
        companion_recovery_per_hour: number;
        max_companion_bonus: number;
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
      kite: IntegrationToggle & {
        ws_url: string;
        token_env: string;
        reconnect_seconds: number;
        max_companions: number;
        zoom: {
          focus_user_id: string;
          max_companions: number;
        };
      };
      slack: IntegrationToggle & {
        app_token_env: string;
        bot_token_env: string;
        bot_user_id: string;
        socket_reconnect_seconds: number;
        activity_window_seconds: number;
        activity_threshold: number;
        activity_cooldown_seconds: number;
        summary_window_seconds: number;
        channels: Record<
          string,
          {
            label: string;
            tone: string;
            weight: number;
            activity_threshold: number;
            dominant_types: string[];
          }
        >;
      };
      discord: IntegrationToggle & {
        bot_token_env: string;
        client_id: string;
        client_secret_env: string;
        user_token_env: string;
        guild_id: string;
        focus_user_id: string;
        max_companions: number;
        gateway_reconnect_seconds: number;
      };
      zoom: IntegrationToggle & {
        account_id_env: string;
        client_id_env: string;
        client_secret_env: string;
        focus_user_id: string;
        max_companions: number;
        poll_seconds: number;
        page_size: number;
        timeout_seconds: number;
      };
      github: IntegrationToggle & {
        client_id: string;
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
      clickup: IntegrationToggle & {
        token_env: string;
        team_id: string;
        team_ids: string[];
        assignee_id: string;
        assignee_ids: string[];
        poll_seconds: number;
        max_tasks: number;
        due_within_days: number;
        include_overdue: boolean;
        include_undated: boolean;
        include_subtasks: boolean;
        include_closed: boolean;
        timeout_seconds: number;
      };
      todoist: IntegrationToggle & {
        token_env: string;
        project_ids: string[];
        section_ids: string[];
        filter: string;
        poll_seconds: number;
        max_tasks: number;
        due_within_days: number;
        include_overdue: boolean;
        include_undated: boolean;
        timeout_seconds: number;
      };
      media: IntegrationToggle & {
        providers: string[];
        poll_seconds: number;
        timeout_seconds: number;
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
