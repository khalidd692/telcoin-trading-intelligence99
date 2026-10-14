const ALLOWED_ORIGIN = "https://khalidd692.github.io";
const MEXC_URL = "wss://wbs-api.mexc.com/ws";
const KUCOIN_TOKEN_URL = "https://api.kucoin.com/api/v1/bullet-public";

function json(body, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json; charset=utf-8", "cache-control": "no-store" },
  });
}

async function upstreamUrl(venue) {
  if (venue === "mexc") return MEXC_URL;
  if (venue !== "kucoin") throw new Error("Unsupported venue");
  const response = await fetch(KUCOIN_TOKEN_URL, {
    method: "POST",
    headers: { "accept": "application/json" },
  });
  if (!response.ok) throw new Error("KuCoin public token HTTP " + response.status);
  const payload = await response.json();
  if (payload.code !== "200000" || !payload.data?.token || !Array.isArray(payload.data.instanceServers)) {
    throw new Error("Invalid KuCoin public token response");
  }
  const server = payload.data.instanceServers.find((item) =>
    item && typeof item.endpoint === "string" && item.endpoint.startsWith("wss://")
  );
  if (!server) throw new Error("KuCoin WSS endpoint unavailable");
  const target = new URL(server.endpoint);
  target.searchParams.set("token", payload.data.token);
  target.searchParams.set("connectId", "telcoin-relay-" + crypto.randomUUID());
  return target.toString();
}

export default {
  async fetch(request) {
    const url = new URL(request.url);
    if (request.method === "GET" && url.pathname === "/health") {
      return json({ service: "telcoin-public-ws-relay", status: "ok", venues: ["mexc", "kucoin"] });
    }
    if (request.headers.get("Origin") !== ALLOWED_ORIGIN) {
      return json({ error: "Origin not allowed" }, 403);
    }
    if (request.headers.get("Upgrade")?.toLowerCase() !== "websocket") {
      return json({ error: "WebSocket upgrade required" }, 426);
    }
    const venue = url.searchParams.get("venue");
    if (venue !== "mexc" && venue !== "kucoin") return json({ error: "venue must be mexc or kucoin" }, 400);

    let target;
    try {
      target = await upstreamUrl(venue);
    } catch (error) {
      return json({ error: error instanceof Error ? error.message : "Upstream setup failed" }, 502);
    }

    const pair = new WebSocketPair();
    const client = pair[0];
    const server = pair[1];
    server.accept();

    let upstream;
    try {
      upstream = new WebSocket(target);
    } catch {
      server.close(1011, "Upstream connection failed");
      return new Response(null, { status: 101, webSocket: client });
    }

    let upstreamOpen = false;
    const closeBoth = (code, reason) => {
      try { if (server.readyState < 2) server.close(code, reason); } catch {}
      try { if (upstream && upstream.readyState < 2) upstream.close(code, reason); } catch {}
    };
    upstream.addEventListener("open", () => { upstreamOpen = true; });
    upstream.addEventListener("message", (event) => {
      try { if (server.readyState === 1) server.send(event.data); } catch { closeBoth(1011, "Relay send failed"); }
    });
    upstream.addEventListener("close", () => closeBoth(1012, "Exchange disconnected"));
    upstream.addEventListener("error", () => closeBoth(1011, "Exchange transport error"));
    server.addEventListener("message", (event) => {
      if (!upstreamOpen || upstream.readyState !== 1) return;
      try { upstream.send(event.data); } catch { closeBoth(1011, "Relay send failed"); }
    });
    server.addEventListener("close", () => closeBoth(1000, "Client disconnected"));
    server.addEventListener("error", () => closeBoth(1011, "Client transport error"));

    return new Response(null, { status: 101, webSocket: client });
  },
};
