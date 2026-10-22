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

async function boot(generatedAt, initialNow, payloadOverride) {
  let now = initialNow;
  let fetchCount = 0;
  const timers = [];
  const requests = [];
  const perUrlCounts = new Map();
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
  const payload = payloadOverride || report(generatedAt);
  const context = {
    document: { getElementById: element },
    window: {
      setInterval(callback, delay) { timers.push({ callback, delay, kind: "interval" }); return timers.length; },
      setTimeout(callback, delay) { timers.push({ callback, delay, kind: "timeout" }); callback(); return timers.length; }
    },
    fetch: async (url) => {
      fetchCount += 1;
      const key = String(url || "");
      requests.push({ url: key, at: now });
      let served = payload;
      if (payload && payload.byUrl) {
        for (const fragment of Object.keys(payload.byUrl)) {
          if (key.indexOf(fragment) !== -1) {
            let candidate = payload.byUrl[fragment];
            if (Array.isArray(candidate)) {
              const index = perUrlCounts.get(fragment) || 0;
              perUrlCounts.set(fragment, index + 1);
              candidate = candidate[Math.min(index, candidate.length - 1)];
            }
            served = candidate;
            break;
          }
        }
      }
      if (served === null) {
        return { ok: false, status: 404, json: async () => ({}) };
      }
      return { ok: true, json: async () => served };
    },
    Date: TestDate,
    console
  };
  vm.runInNewContext(script, context);
  async function settle() {
    for (let i = 0; i < 30; i++) {
      await new Promise(resolve => setImmediate(resolve));
      const refresh = elements.get("refresh");
      if (refresh && refresh.disabled === false && elements.get("main-status").innerHTML) return;
    }
  }
  await settle();
  return {
    elements, timers, requests, settle,
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

  const twoPointPayload = report(new Date(start - 10_000).toISOString());
  twoPointPayload.indicators = {
    timeframe: "15m",
    last_closed_candle_at: twoPointPayload.generated_at,
    close_series: [
      { time: new Date(start - 60_000).toISOString(), close: 0.00100 },
      { time: new Date(start).toISOString(), close: 0.00102 },
    ]
  };
  const twoPoint = await boot(new Date(start - 10_000).toISOString(), start, twoPointPayload);
  assert.equal(twoPoint.elements.get("price-chart").hidden, false);
  assert.notEqual(twoPoint.elements.get("price-chart").innerHTML, "");
  assert.notEqual(twoPoint.elements.get("chart-start").textContent, "—");
  assert.notEqual(twoPoint.elements.get("chart-end").textContent, "—");

  // ------------------------------------------------------------------
  // Panneau de detection de retournement (early_reversal)
  // ------------------------------------------------------------------
  const agentPayload = generatedAt => ({
    schema_version: 1,
    symbol: "TELUSDT",
    mode: "READ_ONLY_ANALYSIS",
    generated_at: generatedAt,
    status: "SURVEILLER",
    alignment: "MIXTE",
    orders_sent: 0,
    timeframes: {
      "15m": {
        status: "OK", trend: "MIXTE", close: 0.00152, rsi14: 41.2,
        ema20: 0.0015, ema50: 0.00155, macd_histogram: 0.000001,
        volume_ratio_20: 1.3, candle_count: 300,
        last_closed_at: generatedAt, candle_age_seconds: 42, reason: null
      },
      "1h": { status: "OK", trend: "MIXTE", close: 0.00152, rsi14: 45, ema20: 0.0015, ema50: 0.00155, macd_histogram: 0, volume_ratio_20: 1, candle_count: 300, reason: null },
      "4h": { status: "OK", trend: "BAISSIER", close: 0.0015, rsi14: 27, ema20: 0.00155, ema50: 0.0016, macd_histogram: -0.00001, volume_ratio_20: 0.9, candle_count: 300, reason: null },
      "1d": { status: "OK", trend: "BAISSIER", close: 0.00155, rsi14: 30, ema20: 0.0016, ema50: 0.0017, macd_histogram: -0.00002, volume_ratio_20: 0.8, candle_count: 300, reason: null },
      "1w": { status: "OK", trend: "MIXTE", close: 0.00155, rsi14: 40, ema20: 0.0016, ema50: 0.0017, macd_histogram: 0, volume_ratio_20: 1, candle_count: 100, reason: null },
      "1M": { status: "PARTIEL", trend: "INDETERMINE", close: 0.0023, rsi14: 40, ema20: 0.0023, ema50: null, macd_histogram: null, volume_ratio_20: 1, candle_count: 23, reason: "historique mensuel trop court" }
    },
    flags: [],
    risk_checks: { critical_level: 0.001526, status: "AU_DESSUS_SUR_CLOTURE", closed_timeframes_below_level: [] },
    early_reversal: {
      signal_status: "ALERTE_PRÉCOCE",
      direction: "HAUSSIER",
      reason: "Setup de retournement haussier a l'extreme, 2 famille(s) independante(s), non confirme",
      confidence: 50,
      confidence_note: "score de convergence des familles de preuves (0-100) ; ce n'est pas une probabilite et n'a pas ete calibre",
      families: ["momentum", "structure"],
      evidence: [
        { category: "momentum", type: "macd_histogram_turn" },
        { category: "structure", type: "bullish_engulfing" }
      ],
      contradictions: [{ type: "higher_timeframe_trend_opposite", timeframe: "1d" }],
      missing_data: [],
      contributing_timeframes: ["15m", "4h", "1d"],
      setup: { direction: "HAUSSIER", anchor: 0.001512, age_bars: 1, note: "age_bars : nombre de bougies depuis la creation du setup." },
      regime: { state: "NEUTRE", value: -0.043424, window_bars: 30, band: 0.05, note: "variation relative sur 30 bougies journalieres cloturees" },
      exploitable: false,
      exploitable_reason: "Aucun signal de retournement confirme a ce stade",
      objectives: {
        short_term: { level: 0.00158, distance_pct: 3.9, distance_atr: 1.2, kind: "opposing structural level" },
        swing: { level: 0.00172, distance_pct: 13.1, distance_atr: 4.1, kind: "opposing structural level" },
        note: "Niveaux structurels informatifs : une localisation, pas une prediction."
      }
    }
  });

  const agent = await boot(new Date(start - 10_000).toISOString(), start, {
    byUrl: {
      "agent_analysis.json": agentPayload(new Date(start - 10_000).toISOString()),
      "tel_snapshot.json": null,
      "report.json": report(new Date(start - 10_000).toISOString())
    }
  });
  const revStatus = agent.elements.get("agent-reversal-status");
  const revDetail = agent.elements.get("agent-reversal-detail");
  const revEvidence = agent.elements.get("agent-reversal-evidence");
  assert.match(revStatus.textContent, /ALERTE PRÉCOCE/);
  assert.match(revDetail.innerHTML, /Direction :/);
  assert.match(revDetail.innerHTML, /Ancre structurelle/);
  assert.match(revDetail.innerHTML, /Familles de preuves/);
  assert.match(revDetail.innerHTML, /Objectif court terme/);
  assert.match(revDetail.innerHTML, /pas une probabilite|pas une probabilité/);
  assert.match(revDetail.innerHTML, /ni un signal d.achat/);
  assert.match(revEvidence.innerHTML, /macd_histogram_turn/);
  assert.match(revEvidence.innerHTML, /bullish_engulfing/);
  assert.match(revEvidence.innerHTML, /contradiction/);

  // --- T37 : regime de marche et exploitabilite ---
  const revQuality = agent.elements.get("agent-reversal-quality");
  assert.ok(revQuality, "le bloc qualite doit exister");
  assert.match(revQuality.innerHTML, /R\u00e9gime neutre/);
  assert.match(revQuality.innerHTML, /-4,34 %/);
  assert.match(revQuality.innerHTML, /30 j/);
  assert.match(revQuality.innerHTML, /Signal non exploitable/);
  assert.match(revDetail.innerHTML, /Exploitabilit\u00e9 :/);
  assert.match(revDetail.innerHTML, /n.est pas une entr\u00e9e/);
  // une alerte precoce n'est jamais presentee comme une configuration valide
  assert.doesNotMatch(revStatus.className, /pass/);

  // cas : CONFIRMATION en regime neutre -> signal exploitable, badge vert
  const confirmOk = agentPayload(new Date(start - 10_000).toISOString());
  confirmOk.early_reversal.signal_status = "CONFIRMATION";
  confirmOk.early_reversal.exploitable = true;
  confirmOk.early_reversal.exploitable_reason =
    "Retournement confirme en regime neutre : configuration mesuree la plus favorable";
  const okCase = await boot(new Date(start - 10_000).toISOString(), start, {
    byUrl: {
      "agent_analysis.json": confirmOk,
      "tel_snapshot.json": null,
      "report.json": report(new Date(start - 10_000).toISOString())
    }
  });
  const okQuality = okCase.elements.get("agent-reversal-quality");
  assert.match(okCase.elements.get("agent-reversal-status").textContent, /CONFIRMATION/);
  assert.match(okQuality.innerHTML, /Signal exploitable/);
  assert.match(okQuality.innerHTML, /quality-chip ok/);
  assert.match(okCase.elements.get("agent-reversal-status").className, /pass/);
  assert.match(okCase.elements.get("agent-reversal-detail").innerHTML, /en regime neutre/);

  // cas : CONFIRMATION contre une tendance -> exploitable = false, badge NON vert
  const confirmTrend = agentPayload(new Date(start - 10_000).toISOString());
  confirmTrend.early_reversal.signal_status = "CONFIRMATION";
  confirmTrend.early_reversal.regime = { state: "TENDANCE_BAISSIERE", value: -0.31, window_bars: 30, band: 0.05 };
  confirmTrend.early_reversal.exploitable = false;
  confirmTrend.early_reversal.exploitable_reason =
    "Retournement confirme mais regime en tendance (variation 1j 30 j hors zone neutre) : contre-tendance non exploitable";
  const trendCase = await boot(new Date(start - 10_000).toISOString(), start, {
    byUrl: {
      "agent_analysis.json": confirmTrend,
      "tel_snapshot.json": null,
      "report.json": report(new Date(start - 10_000).toISOString())
    }
  });
  const trendQuality = trendCase.elements.get("agent-reversal-quality");
  assert.match(trendQuality.innerHTML, /Tendance baissi\u00e8re/);
  assert.match(trendQuality.innerHTML, /Signal non exploitable/);
  assert.match(trendQuality.innerHTML, /quality-chip trend/);
  assert.doesNotMatch(trendCase.elements.get("agent-reversal-status").className, /pass/);
  assert.match(trendCase.elements.get("agent-reversal-detail").innerHTML, /contre-tendance non exploitable/);
  // les observations restent visibles malgre l'absence d'exploitabilite
  assert.match(trendCase.elements.get("agent-reversal-evidence").innerHTML, /macd_histogram_turn/);

  // cas : INVALIDATION (le scenario est contredit) -> jamais exploitable, jamais vert
  const invalidated = agentPayload(new Date(start - 10_000).toISOString());
  invalidated.early_reversal.signal_status = "INVALIDATION";
  invalidated.early_reversal.exploitable = false;
  invalidated.early_reversal.exploitable_reason =
    "Scenario invalide : l'ancre structurelle est rompue.";
  invalidated.early_reversal.setup = null;
  const invalidCase = await boot(new Date(start - 10_000).toISOString(), start, {
    byUrl: {
      "agent_analysis.json": invalidated,
      "tel_snapshot.json": null,
      "report.json": report(new Date(start - 10_000).toISOString())
    }
  });
  assert.match(invalidCase.elements.get("agent-reversal-status").textContent, /INVALIDATION/);
  assert.doesNotMatch(invalidCase.elements.get("agent-reversal-status").className, /pass/);
  const invalidQuality = invalidCase.elements.get("agent-reversal-quality");
  assert.match(invalidQuality.innerHTML, /Signal non exploitable/);
  assert.match(invalidCase.elements.get("agent-reversal-detail").innerHTML, /ancre structurelle est rompue/);
  // une invalidation n'affiche ni ancre ni objectif : le scenario est contredit
  assert.doesNotMatch(invalidCase.elements.get("agent-reversal-detail").innerHTML, /Ancre structurelle/);

  // cas : rapport d'une version d'agent anterieure (ni regime ni exploitable)
  const legacy = agentPayload(new Date(start - 10_000).toISOString());
  delete legacy.early_reversal.regime;
  delete legacy.early_reversal.exploitable;
  delete legacy.early_reversal.exploitable_reason;
  const legacyCase = await boot(new Date(start - 10_000).toISOString(), start, {
    byUrl: {
      "agent_analysis.json": legacy,
      "tel_snapshot.json": null,
      "report.json": report(new Date(start - 10_000).toISOString())
    }
  });
  const legacyQuality = legacyCase.elements.get("agent-reversal-quality");
  assert.match(legacyQuality.innerHTML, /non communiqu/);
  assert.match(legacyQuality.innerHTML, /R\u00e9gime : non communiqu/);
  assert.doesNotMatch(legacyCase.elements.get("agent-reversal-status").className, /pass/);

  // cas : le rapport ne publie pas de detection -> statut explicite, pas de valeur inventee
  const withoutReversal = agentPayload(new Date(start - 10_000).toISOString());
  delete withoutReversal.early_reversal;
  const bare = await boot(new Date(start - 10_000).toISOString(), start, {
    byUrl: {
      "agent_analysis.json": withoutReversal,
      "tel_snapshot.json": null,
      "report.json": report(new Date(start - 10_000).toISOString())
    }
  });
  assert.match(bare.elements.get("agent-reversal-status").textContent, /NON PUBLIÉ/);
  assert.match(bare.elements.get("agent-reversal-detail").textContent, /Aucune conclusion/);

  // cas : donnees de l'analyse absentes ou perimees -> le panneau doit le dire
  const broken = await boot(new Date(start - 10_000).toISOString(), start, {
    byUrl: {
      "agent_analysis.json": null,
      "tel_snapshot.json": null,
      "report.json": report(new Date(start - 10_000).toISOString())
    }
  });
  assert.match(broken.elements.get("agent-reversal-status").textContent, /ATTENDRE/);
  assert.match(broken.elements.get("agent-reversal-detail").textContent, /indisponible/);

  // ------------------------------------------------------------------
  // Provenance: one coordinated refresh cycle, transient mismatch retried
  // ------------------------------------------------------------------
  const cidA = "aaaaaaaa-1111-4111-8111-aaaaaaaaaaaa";
  const cidB = "bbbbbbbb-2222-4222-8222-bbbbbbbbbbbb";
  const reportA = report(new Date(start - 10_000).toISOString());
  const reportB = report(new Date(start - 10_000).toISOString());
  reportA.collection_id = cidA;
  reportB.collection_id = cidB;
  const snapshotB = {
    schema_version: 1,
    symbol: "TELUSDT",
    collection_id: cidB,
    generated_at: new Date(start - 10_000).toISOString()
  };
  const agentA = agentPayload(new Date(start - 10_000).toISOString());
  const agentB = agentPayload(new Date(start - 10_000).toISOString());
  agentA.collection_id = cidA;
  agentB.collection_id = cidB;

  const recovery = await boot(new Date(start - 10_000).toISOString(), start, {
    byUrl: {
      "report.json": [reportA, reportB],
      "tel_snapshot.json": [snapshotB, snapshotB],
      "agent_analysis.json": [agentB, agentB]
    }
  });
  assert.match(recovery.elements.get("main-status").innerHTML, /SURVEILLER/);
  assert.notEqual(recovery.elements.get("last-price").textContent, "—");
  assert.match(recovery.elements.get("agent-status").textContent, /SURVEILLER/);
  assert.doesNotMatch(recovery.elements.get("report-error").textContent, /collection_id/);
  assert.equal(
    recovery.elements.get("report-error").textContent.includes("provenance"),
    false,
    "a transient mixed publication must recover, not stay rejected"
  );
  assert.ok(recovery.fetchCount >= 6, "a mixed publication must trigger a coordinated retry");
  assert.equal(
    recovery.timers.filter(timer => timer.kind === "interval" && timer.delay === 60_000).length,
    1,
    "there must be one artifact refresh coordinator, not three independent pollers"
  );
  assert.equal(recovery.requests.length, 6);
  const firstCycleTokens = recovery.requests.slice(0, 3).map(request =>
    new URL(request.url, "https://dashboard.test").searchParams.get("t")
  );
  assert.equal(new Set(firstCycleTokens).size, 1, "one cycle must use one cache-busting token");

  const persistent = await boot(new Date(start - 10_000).toISOString(), start, {
    byUrl: {
      "report.json": [reportA, reportA, reportA],
      "tel_snapshot.json": [snapshotB, snapshotB, snapshotB],
      "agent_analysis.json": [agentA, agentA, agentA]
    }
  });
  assert.match(persistent.elements.get("main-status").innerHTML, /ATTENDRE/);
  assert.match(persistent.elements.get("report-error").textContent, /provenance incohérente|collection_id/);
  assert.equal(persistent.elements.get("last-price").textContent, "—");
  assert.match(persistent.elements.get("report-age").textContent, /NON VALIDÉ/);
  assert.match(persistent.elements.get("agent-status").textContent, /ATTENDRE/);
  assert.match(persistent.elements.get("agent-meta").textContent, /collection_id incohérent/);
  assert.equal(persistent.fetchCount, 9, "three coordinated attempts are made before fail-closed");

  // A page that was already stuck on a mixed collection must be able to
  // recover on the next coordinated refresh: the old code compared the new
  // report against the stale snapshot/agent ids before replacing its own id.
  const recoverAfterReject = await boot(new Date(start - 10_000).toISOString(), start, {
    byUrl: {
      "report.json": [reportA, reportA, reportA, reportB],
      "tel_snapshot.json": [snapshotB, snapshotB, snapshotB, snapshotB],
      "agent_analysis.json": [agentA, agentA, agentA, agentB]
    }
  });
  assert.match(recoverAfterReject.elements.get("main-status").innerHTML, /ATTENDRE/);
  recoverAfterReject.elements.get("refresh").listeners.click();
  await recoverAfterReject.settle();
  assert.match(recoverAfterReject.elements.get("main-status").innerHTML, /SURVEILLER/);
  assert.doesNotMatch(recoverAfterReject.elements.get("report-error").textContent, /collection_id/);
  assert.equal(recoverAfterReject.fetchCount, 12);

  process.stdout.write("Dashboard freshness tests: OK\n");
  process.stdout.write("Dashboard provenance refresh tests: OK\n");
  process.stdout.write("Dashboard early-reversal panel tests: OK\n");
})().catch(error => {
  console.error(error);
  process.exitCode = 1;
});
