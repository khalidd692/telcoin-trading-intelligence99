// Fails if the Worker would ship in an unsafe state.
// Run in CI and before any deploy: `node scripts/check-config.mjs`.
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const here = dirname(fileURLToPath(import.meta.url));
const raw = readFileSync(join(here, "..", "wrangler.jsonc"), "utf8");
// Strip // line comments: the file is JSONC, not strict JSON.
const config = JSON.parse(raw.replace(/^\s*\/\/.*$/gm, ""));

const problems = [];
if (config.vars?.TEL99_ENABLED !== "false") {
  problems.push('TEL99_ENABLED must ship as "false"');
}
if (!Array.isArray(config.triggers?.crons) || config.triggers.crons.length !== 0) {
  problems.push("crons must be empty until the operator approves activation");
}
if (config.workers_dev === true) {
  problems.push("workers_dev must stay false (no accidental public endpoint)");
}

if (problems.length) {
  console.error("UNSAFE wrangler config:");
  for (const p of problems) console.error(" - " + p);
  process.exit(1);
}
console.log("wrangler config safe (disabled, no cron, no workers.dev)");
