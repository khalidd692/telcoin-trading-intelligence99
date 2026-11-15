// TEL99 hybrid scheduler.
//
// Role: a FREE, reliable clock. Cloudflare Workers cannot host Python or an
// LLM (10 ms CPU on the free plan), so this Worker only decides WHETHER there
// is work and asks GitHub to run a read-only, deterministic job. It never
// starts an OpenHands conversation, trades, pushes, merges or deploys.
//
// Safety:
//  * Disabled unless TEL99_ENABLED === "true" AND a dispatch token is set.
//  * Deterministic selection: oldest labelled mission first (matches the
//    orchestrator's policy.select_mission), so retries target the same mission
//    instead of thrashing between issues.
//  * Optional dedup: if a KV namespace is bound, an issue already dispatched is
//    skipped until it is closed or unlabelled. Without KV it still works.
//  * Every GitHub call checks response.ok; failures are logged and swallowed so
//    a transient error never produces a half-dispatch.

const REPO = "khalidd692/telcoin-trading-intelligence99";
const EVENT_TYPE = "tel99_hybrid_audit_v1";
const MISSION_LABEL = "tel99-mission";
const DEDUP_TTL_SECONDS = 60 * 60 * 6;

const GH = {
  "Accept": "application/vnd.github+json",
  "User-Agent": "tel99-hybrid-scheduler",
  "X-GitHub-Api-Version": "2022-11-28",
};

function oldestFirst(a, b) {
  const ca = a.created_at || "";
  const cb = b.created_at || "";
  if (ca !== cb) return ca < cb ? -1 : 1;
  return (a.number || 0) - (b.number || 0);
}

async function listMissions(token) {
  const url =
    `https://api.github.com/repos/${REPO}/issues` +
    `?state=open&labels=${MISSION_LABEL}&per_page=30`;
  const headers = token ? { ...GH, Authorization: `Bearer ${token}` } : GH;
  const res = await fetch(url, { headers });
  if (!res.ok) {
    console.error("GitHub issue lookup failed", res.status);
    return null;
  }
  const body = await res.json();
  if (!Array.isArray(body)) {
    console.error("GitHub issue lookup returned a non-list");
    return null;
  }
  return body.filter((issue) => !issue.pull_request && typeof issue.number === "number");
}

async function alreadyDispatched(env, issueNumber) {
  if (!env.TEL99_DEDUP) return false;
  const seen = await env.TEL99_DEDUP.get(`dispatched:${issueNumber}`);
  return Boolean(seen);
}

async function markDispatched(env, issueNumber) {
  if (!env.TEL99_DEDUP) return;
  await env.TEL99_DEDUP.put(`dispatched:${issueNumber}`, "1", {
    expirationTtl: DEDUP_TTL_SECONDS,
  });
}

export default {
  async scheduled(_event, env, _ctx) {
    if (env.TEL99_ENABLED !== "true") {
      console.log("TEL99 disabled: no dispatch");
      return;
    }
    if (!env.GITHUB_DISPATCH_TOKEN) {
      console.error("TEL99 disabled: missing dispatch token");
      return;
    }

    const missions = await listMissions(env.GITHUB_DISPATCH_TOKEN);
    if (!missions || missions.length === 0) {
      console.log("No labelled issue: idle");
      return;
    }

    const ordered = [...missions].sort(oldestFirst);
    let chosen = null;
    for (const mission of ordered) {
      if (!(await alreadyDispatched(env, mission.number))) {
        chosen = mission;
        break;
      }
    }
    if (!chosen) {
      console.log("All labelled issues already dispatched: idle");
      return;
    }

    const res = await fetch(`https://api.github.com/repos/${REPO}/dispatches`, {
      method: "POST",
      headers: {
        ...GH,
        "Content-Type": "application/json",
        Authorization: `Bearer ${env.GITHUB_DISPATCH_TOKEN}`,
      },
      body: JSON.stringify({
        event_type: EVENT_TYPE,
        client_payload: { source: "cloudflare", issue: chosen.number },
      }),
    });
    if (res.status !== 204) {
      console.error("GitHub dispatch failed", res.status);
      return;
    }
    await markDispatched(env, chosen.number);
    console.log("Read-only audit dispatched for issue", chosen.number);
  },
};
