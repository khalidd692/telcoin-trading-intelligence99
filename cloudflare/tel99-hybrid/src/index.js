// TEL99 hybrid scheduler: Cloudflare only dispatches a read-only GitHub audit.
// It never creates OpenHands conversations, trades, pushes or deploys.
const REPO = "khalidd692/telcoin-trading-intelligence99";
const EVENT_TYPE = "tel99_hybrid_audit_v1";

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
    // Public issue queue is used only to determine whether work is pending.
    const issues = await fetch(
      `https://api.github.com/repos/${REPO}/issues?state=open&labels=tel99-mission&per_page=30`,
      { headers: { "Accept": "application/vnd.github+json", "User-Agent": "tel99-hybrid-scheduler" } }
    );
    if (!issues.ok) {
      console.error("GitHub issue lookup failed", issues.status);
      return;
    }
    const candidates = (await issues.json()).filter(issue => !issue.pull_request);
    if (!candidates.length) {
      console.log("No labelled issue: idle");
      return;
    }
    // GitHub repository_dispatch runs a read-only workflow on the default branch.
    const dispatched = await fetch(`https://api.github.com/repos/${REPO}/dispatches`, {
      method: "POST",
      headers: {
        "Accept": "application/vnd.github+json",
        "Content-Type": "application/json",
        "Authorization": `Bearer ${env.GITHUB_DISPATCH_TOKEN}`,
        "User-Agent": "tel99-hybrid-scheduler",
        "X-GitHub-Api-Version": "2022-11-28"
      },
      body: JSON.stringify({ event_type: EVENT_TYPE, client_payload: { source: "cloudflare", issue: candidates[0].number } })
    });
    if (dispatched.status !== 204) {
      console.error("GitHub dispatch failed", dispatched.status);
      return;
    }
    console.log("Read-only audit dispatched for issue", candidates[0].number);
  }
};
