export type RuntimeConfig = {
  display: {
    display: {
      width: number;
      height: number;
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
      discord: IntegrationToggle;
      github: IntegrationToggle & {
        token_env: string;
        repos: string[];
        poll_seconds: number;
        max_pull_requests: number;
        fetch_pull_requests: number;
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
        city: string;
        country_code: string;
        poll_seconds: number;
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
    };
  };
  people: {
    people: PersonConfig[];
  };
  game: {
    game: {
      fps: number;
      static_background: boolean;
      require_ash_sprite: boolean;
      map_switch_seconds: number;
      route_speed_px: number;
      vertical_wander_px: number;
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
  pokemon: {
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
};

export type LayoutKey = "timezones" | "gauges" | "weather" | "activity" | "game" | "text_box";

export type LayoutBox = {
  x: number;
  y: number;
  width: number;
  height: number;
};

export type IntegrationToggle = {
  enabled: boolean;
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
