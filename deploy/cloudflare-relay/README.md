# Public WebSocket relay (Cloudflare Workers)

GitHub Pages is static hosting: it cannot make the KuCoin public-token request server-side, and browsers may block that cross-origin request. This optional relay moves the token request to a small server-side Worker and relays the two **public, read-only** WebSocket feeds. It does not use API keys and cannot place orders.

## Deploy

1. In Cloudflare, create a Worker named `telcoin-public-ws-relay`.
2. Paste the contents of `worker.js` from this folder and deploy.
3. Open `https://YOUR-WORKER.YOUR-SUBDOMAIN.workers.dev/health`. It should return JSON with `"status":"ok"`.
4. In `site/index.html`, set `window.TELCOIN_REALTIME_RELAY_URL` to your Worker base URL (for example `https://telcoin-public-ws-relay.YOUR-SUBDOMAIN.workers.dev/`) immediately before `<script src="./realtime.js"></script>`.
5. Commit that URL change to `main`, wait for the GitHub Pages deployment, then reload the dashboard in Brave.

The Worker accepts WebSocket upgrades only from `https://khalidd692.github.io`; do not use a wildcard origin. If you use a different Pages hostname, update `ALLOWED_ORIGIN` in `worker.js` to that exact origin and redeploy.

## Validation and safety

- The relay preserves binary exchange frames, including Blob-to-ArrayBuffer normalization. MEXC protobuf decoding and KuCoin ticker validation remain in the browser.
- A relay health response only proves the Worker is deployed, **not** that exchange feeds are healthy. Verify both cards receive fresh ticks before treating the live check as passed.
- If either feed is unavailable, stale, malformed, or inconsistent, the dashboard must remain `ATTENDRE`.
- No private credentials, API keys, trading permissions, or orders are involved.
- Cloudflare Worker deployment is an external prerequisite; adding these files to GitHub does not deploy the Worker automatically.
