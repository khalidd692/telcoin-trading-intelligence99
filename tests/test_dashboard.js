"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const html = fs.readFileSync(path.join(__dirname, "..", "site", "index.html"), "utf8");
const match = html.match(/<script>\s*([\s\S]*?)\s*<\/script>/i);
assert.ok(match, "dashboard script exists");
const script = match[1];
assert.ok(html.includes(".empty[hidden]{display:none}"), "hidden chart placeholder must not cover a real chart");

function report(generatedAt) {
  return {
    schema_version: 1,
    generated_at: generatedAt,
    symbol: "TELUSDT",
    mode: "READ_ONLY_ALERTS",
    status: "SURVEILLER",
    sources: {
      mexc_ticker: { status: "OK", last: 0.001, bid: 0.000999, ask: 0.001001, spread_pct: 0.2, observed_at: generatedAt, source: "test fixture" },
      mexc_candles: { status: "OK", timeframe: "15m", closed_candles_used: 1 },
      kucoin_level1: { status: "OK", last: 0.001, bid: 0.000999, ask: 0.001001, observed_at: generatedAt }
    },
    checks: [{ name: "test quality check", status: "PASS" }],
    indicators: { timeframe: "15m", last_closed_candle_at: generatedAt, close_series: [] }
  };
}

async function boot(generatedAt, initialNow) {
  let now = initialNow;
  let fetchCount = 0;
  const timers = [];
  const elements = new Map();
  function element(id) {
    if (!elements.has(id)) {
      elements.set(id, {
        id, textContent: "", innerHTML: "", className: "", hidden: false,
        style: {}, attributes: {}, listeners: {},
        addEventListener(name, handler) { this.listeners[name] = handler; },
        setAttribute(name, value) { this.attributes[name] = value; }
      });
    }
    return elements.get(id);
  }
  element("chart-start").textContent = "old chart date";
  element("chart-end").textContent = "old chart date";
  element("price-chart").innerHTML = "old chart";
  element("price-chart").hidden = false;

  class TestDate extends Date {
    static now() { return now; }
  }
  const payload = report(generatedAt);
  const context = {
    document: { getElementById: element },
    window: { setInterval(callback, delay) { timers.push({ callback, delay }); return timers.length; } },
    fetch: async () => {
      fetchCount += 1;
      return { ok: true, json: async () => payload };
    },
    Date: TestDate,
    console
  };
  vm.runInNewContext(script, context);
  await new Promise(resolve => setImmediate(resolve));
  return {
    elements, timers,
    get fetchCount() { return fetchCount; },
    advance(ms) { now += ms; },
    tickAge() { timers.find(timer => timer.delay === 1000).callback(); }
  };
}

(async () => {
  const start = Date.parse("2026-10-14T21:00:00Z");

  const fresh = await boot(new Date(start - 10_000).toISOString(), start);
  assert.match(fresh.elements.get("main-status").innerHTML, /SURVEILLER/);
  assert.notEqual(fresh.elements.get("last-price").textContent, "—");
  const callsBeforeTick = fresh.fetchCount;
  fresh.advance(1_000);
  fresh.tickAge();
  assert.match(fresh.elements.get("report-age").textContent, /11 s/);
  assert.equal(fresh.fetchCount, callsBeforeTick, "the age clock must not fetch or invent prices");

  fresh.advance(31 * 60 * 1000);
  fresh.tickAge();
  assert.match(fresh.elements.get("main-status").innerHTML, /ATTENDRE/);
  assert.equal(fresh.elements.get("last-price").textContent, "—");
  assert.equal(fresh.elements.get("price-chart").innerHTML, "");
  assert.equal(fresh.elements.get("price-chart").hidden, true);
  assert.equal(fresh.elements.get("chart-start").textContent, "—");
  assert.equal(fresh.elements.get("chart-end").textContent, "—");
  assert.match(fresh.elements.get("report-age").textContent, /PÉRIMÉ/);
  assert.equal(fresh.fetchCount, callsBeforeTick, "staleness must fail closed without a market request");

  const stale = await boot(new Date(start - 31 * 60 * 1000).toISOString(), start);
  assert.match(stale.elements.get("main-status").innerHTML, /ATTENDRE/);
  assert.equal(stale.elements.get("last-price").textContent, "—");
  assert.equal(stale.elements.get("chart-start").textContent, "—");
  assert.match(stale.elements.get("report-age").textContent, /PÉRIMÉ/);

  process.stdout.write("Dashboard freshness tests: OK\n");
})().catch(error => {
  console.error(error);
  process.exitCode = 1;
});
