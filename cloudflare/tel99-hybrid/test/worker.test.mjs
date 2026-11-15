// Node's built-in test runner: no dependencies, runs in CI for free.
import test from "node:test";
import assert from "node:assert/strict";
import worker from "../src/index.js";

function harness(handler) {
  const calls = [];
  const originalFetch = globalThis.fetch;
  globalThis.fetch = async (url, opts = {}) => {
    calls.push({ url, opts });
    return handler(url, opts);
  };
  return {
    calls,
    restore() { globalThis.fetch = originalFetch; },
    issues: (list) => ({ ok: true, status: 200, json: async () => list }),
    status: (code) => ({ ok: code < 400, status: code, json: async () => ({}) }),
  };
}

const ENV = { TEL99_ENABLED: "true", GITHUB_DISPATCH_TOKEN: "x" };

test("disabled: no network call at all", async () => {
  const h = harness(() => h.issues([]));
  try {
    await worker.scheduled({}, {}, {});
    assert.equal(h.calls.length, 0);
  } finally { h.restore(); }
});

test("enabled without token: no network call", async () => {
  const h = harness(() => h.issues([]));
  try {
    await worker.scheduled({}, { TEL99_ENABLED: "true" }, {});
    assert.equal(h.calls.length, 0);
  } finally { h.restore(); }
});

test("oldest mission first, regardless of API order", async () => {
  const h = harness((url) =>
    url.includes("/issues")
      ? h.issues([
          { number: 999, created_at: "2026-11-14T00:00:00Z" },
          { number: 70, created_at: "2026-11-01T00:00:00Z" },
        ])
      : h.status(204)
  );
  try {
    await worker.scheduled({}, ENV, {});
    const dispatch = h.calls.find((c) => c.url.endsWith("/dispatches"));
    const body = JSON.parse(dispatch.opts.body);
    assert.equal(body.client_payload.issue, 70);
  } finally { h.restore(); }
});

test("pull requests are never dispatched", async () => {
  const h = harness((url) =>
    url.includes("/issues")
      ? h.issues([
          { number: 71, created_at: "2026-11-01T00:00:00Z", pull_request: {} },
          { number: 70, created_at: "2026-11-02T00:00:00Z" },
        ])
      : h.status(204)
  );
  try {
    await worker.scheduled({}, ENV, {});
    const body = JSON.parse(h.calls.find((c) => c.url.endsWith("/dispatches")).opts.body);
    assert.equal(body.client_payload.issue, 70);
  } finally { h.restore(); }
});

test("no labelled issue: lookup only, no dispatch", async () => {
  const h = harness(() => h.issues([]));
  try {
    await worker.scheduled({}, ENV, {});
    assert.equal(h.calls.length, 1);
    assert.ok(!h.calls.some((c) => c.url.endsWith("/dispatches")));
  } finally { h.restore(); }
});

test("lookup failure: no dispatch", async () => {
  const h = harness(() => h.status(500));
  try {
    await worker.scheduled({}, ENV, {});
    assert.ok(!h.calls.some((c) => c.url.endsWith("/dispatches")));
  } finally { h.restore(); }
});

test("dispatch failure is logged, never throws", async () => {
  const h = harness((url) =>
    url.includes("/issues")
      ? h.issues([{ number: 70, created_at: "2026-11-01T00:00:00Z" }])
      : h.status(403)
  );
  try {
    await assert.doesNotReject(() => worker.scheduled({}, ENV, {}));
  } finally { h.restore(); }
});

test("KV dedup: an already dispatched issue is skipped", async () => {
  const kv = {
    store: { "dispatched:70": "1" },
    async get(k) { return this.store[k] ?? null; },
    async put(k, v) { this.store[k] = v; },
  };
  const h = harness((url) =>
    url.includes("/issues")
      ? h.issues([
          { number: 70, created_at: "2026-11-01T00:00:00Z" },
          { number: 72, created_at: "2026-11-05T00:00:00Z" },
        ])
      : h.status(204)
  );
  try {
    await worker.scheduled({}, { ...ENV, TEL99_DEDUP: kv }, {});
    const body = JSON.parse(h.calls.find((c) => c.url.endsWith("/dispatches")).opts.body);
    assert.equal(body.client_payload.issue, 72);
  } finally { h.restore(); }
});

test("KV dedup: a successful dispatch is recorded", async () => {
  const kv = {
    store: {},
    async get(k) { return this.store[k] ?? null; },
    async put(k, v) { this.store[k] = v; },
  };
  const h = harness((url) =>
    url.includes("/issues")
      ? h.issues([{ number: 70, created_at: "2026-11-01T00:00:00Z" }])
      : h.status(204)
  );
  try {
    await worker.scheduled({}, { ...ENV, TEL99_DEDUP: kv }, {});
    assert.equal(kv.store["dispatched:70"], "1");
  } finally { h.restore(); }
});
