const STATE_TTL_MS = 20 * 60 * 1000;

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    const id = env.KITE_HUB.idFromName("default");
    const hub = env.KITE_HUB.get(id);
    return hub.fetch(request);
  },
};

export class PixelOpsKiteHub {
  constructor(state, env) {
    this.state = state;
    this.env = env;
    this.clients = new Set();
    this.meetings = new Map();
  }

  async fetch(request) {
    const url = new URL(request.url);
    if (url.pathname === "/health") {
      return json({ ok: true, service: "PixelOpsKite" });
    }
    if (url.pathname === "/connect") {
      return this.connect(request);
    }
    if (url.pathname === "/webhooks/zoom") {
      return this.zoomWebhook(request);
    }
    if (url.pathname === "/state") {
      if (!this.authorized(request)) return unauthorized();
      this.prune();
      return json({ meetings: Array.from(this.meetings.values()) });
    }
    return new Response("Not found", { status: 404 });
  }

  connect(request) {
    if (!this.authorized(request)) return unauthorized();
    if (request.headers.get("upgrade") !== "websocket") {
      return new Response("Expected WebSocket", { status: 426 });
    }
    const pair = new WebSocketPair();
    const [client, server] = Object.values(pair);
    server.accept();
    this.clients.add(server);
    server.send(JSON.stringify({ type: "hello", service: "PixelOpsKite", sent_at: new Date().toISOString() }));
    server.addEventListener("close", () => this.clients.delete(server));
    server.addEventListener("error", () => this.clients.delete(server));
    return new Response(null, { status: 101, webSocket: client });
  }

  async zoomWebhook(request) {
    if (request.method !== "POST") {
      return new Response("Method not allowed", { status: 405 });
    }
    const rawBody = await request.text();
    if (!(await this.validZoomRequest(request, rawBody))) return unauthorized();
    const payload = parseJson(rawBody);
    if (!payload || typeof payload !== "object") {
      return new Response("Bad request", { status: 400 });
    }
    if (payload.event === "endpoint.url_validation") {
      return this.zoomValidation(payload);
    }
    const envelope = this.zoomEnvelope(payload);
    if (envelope) {
      this.applyZoomEnvelope(envelope);
      this.broadcast(envelope);
    }
    return json({ ok: true });
  }

  authorized(request) {
    const expected = this.env.PIXEL_OPS_KITE_TOKEN;
    if (!expected) return false;
    const auth = request.headers.get("authorization") || "";
    const token = auth.startsWith("Bearer ") ? auth.slice(7) : "";
    return token === expected;
  }

  async validZoomRequest(request, rawBody) {
    const expected = this.env.ZOOM_WEBHOOK_SECRET_TOKEN;
    if (!expected) return false;
    const signature = request.headers.get("x-zm-signature") || "";
    const timestamp = request.headers.get("x-zm-request-timestamp") || "";
    if (signature && timestamp) {
      const message = `v0:${timestamp}:${rawBody}`;
      const digest = await hmacHex(expected, message);
      return signature === `v0=${digest}`;
    }
    const secretToken = request.headers.get("x-zm-secret-token") || "";
    return secretToken === expected;
  }

  zoomValidation(payload) {
    const crypto = globalThis.crypto;
    const plainToken = String(payload.payload?.plainToken || "");
    if (!plainToken || !this.env.ZOOM_WEBHOOK_SECRET_TOKEN) {
      return new Response("Bad request", { status: 400 });
    }
    return crypto.subtle
      .importKey("raw", utf8(this.env.ZOOM_WEBHOOK_SECRET_TOKEN), { name: "HMAC", hash: "SHA-256" }, false, ["sign"])
      .then((key) => crypto.subtle.sign("HMAC", key, utf8(plainToken)))
      .then((signature) =>
        json({
          plainToken,
          encryptedToken: hex(signature),
        })
      );
  }

  zoomEnvelope(payload) {
    const event = String(payload.event || "");
    if (!event.startsWith("meeting.")) return null;
    const object = payload.payload?.object || {};
    const participant = object.participant || {};
    const meetingId = String(object.uuid || object.id || "");
    if (!meetingId) return null;
    return {
      type: "webhook",
      provider: "zoom",
      event,
      received_at: new Date().toISOString(),
      payload: {
        event,
        event_ts: payload.event_ts,
        payload: {
          account_id: payload.payload?.account_id || "",
          object: {
            uuid: meetingId,
            id: String(object.id || ""),
            topic: String(object.topic || ""),
            start_time: object.start_time || "",
            end_time: object.end_time || "",
            participant: {
              id: String(participant.id || participant.participant_user_id || participant.user_id || participant.email || ""),
              user_id: String(participant.user_id || ""),
              user_name: String(participant.user_name || participant.name || participant.email || ""),
              email: String(participant.email || ""),
            },
          },
        },
      },
    };
  }

  applyZoomEnvelope(envelope) {
    const object = envelope.payload.payload.object;
    const participant = object.participant || {};
    const meetingId = object.uuid;
    const now = Date.now();
    const current = this.meetings.get(meetingId) || {
      provider: "zoom",
      meeting_id: meetingId,
      topic: object.topic || meetingId,
      updated_at: new Date(now).toISOString(),
      expires_at: new Date(now + STATE_TTL_MS).toISOString(),
      participants: {},
    };
    current.topic = object.topic || current.topic || meetingId;
    current.updated_at = new Date(now).toISOString();
    current.expires_at = new Date(now + STATE_TTL_MS).toISOString();
    const participantId = String(participant.email || participant.id || participant.user_id || participant.user_name || "").toLowerCase();
    if (participantId) {
      if (envelope.event.includes("participant_left")) {
        delete current.participants[participantId];
      } else if (envelope.event.includes("participant_joined")) {
        current.participants[participantId] = {
          id: participantId,
          name: participant.user_name || participant.email || participantId,
          email: participant.email || "",
        };
      }
    }
    if (envelope.event.includes("meeting.ended")) {
      this.meetings.delete(meetingId);
      return;
    }
    this.meetings.set(meetingId, current);
    this.prune();
  }

  prune() {
    const now = Date.now();
    for (const [meetingId, meeting] of this.meetings.entries()) {
      if (Date.parse(meeting.expires_at || "") < now) {
        this.meetings.delete(meetingId);
      }
    }
  }

  broadcast(envelope) {
    const message = JSON.stringify(envelope);
    for (const client of this.clients) {
      try {
        client.send(message);
      } catch (_error) {
        this.clients.delete(client);
      }
    }
  }
}

function json(value, init = {}) {
  return new Response(JSON.stringify(value), {
    ...init,
    headers: { "content-type": "application/json", ...(init.headers || {}) },
  });
}

function parseJson(value) {
  try {
    return JSON.parse(value);
  } catch (_error) {
    return null;
  }
}

function unauthorized() {
  return new Response("Unauthorized", { status: 401 });
}

function utf8(value) {
  return new TextEncoder().encode(value);
}

function hex(buffer) {
  return [...new Uint8Array(buffer)].map((byte) => byte.toString(16).padStart(2, "0")).join("");
}

async function hmacHex(secret, message) {
  const key = await crypto.subtle.importKey("raw", utf8(secret), { name: "HMAC", hash: "SHA-256" }, false, ["sign"]);
  const signature = await crypto.subtle.sign("HMAC", key, utf8(message));
  return hex(signature);
}
