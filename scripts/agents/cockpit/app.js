"use strict";
const unknown = "INCONNU";
const labels = {
  IDLE: "En attente", BUSY: "Occupé", ACK: "Reçue", RUNNING: "En cours",
  WORKER_EXITED: "Travail reçu", ACCEPTED: "Acceptée", REJECTED: "Rejetée",
  AWAITING_HUMAN: "Revue requise", BLOCKED: "Bloquée", STOPPED: "Arrêté",
  STOP_REQUESTED: "Arrêt demandé", PLANNED: "Planifié", PASS: "Réussi", FAIL: "Échec",
  open: "Ouverte", closed: "Fermée"
};
const names = {
  development: "Développement", quant: "Analyse", quality: "Vérification",
  coordination: "Coordination", cloud: "Cloud et fiabilité", security: "Sécurité",
  mobile: "Expérience mobile", documentation: "Documentation", evaluation: "Évaluation",
  market_data: "Données de marché", monitoring: "Suivi des incidents", release: "Publication"
};
const byId = id => document.getElementById(id);

function node(tag, text, css) {
  const el = document.createElement(tag);
  if (text !== undefined) el.textContent = text ?? unknown;
  if (css) el.className = css;
  return el;
}
function state(value) { return Object.hasOwn(labels, value) ? labels[value] : unknown; }
function pill(text, variant) { return node("span", text, variant ? "pill " + variant : "pill"); }
function link(url, title) {
  if (typeof url !== "string" || !url.startsWith("https://github.com/")) return node("span", title);
  const el = node("a", title);
  el.href = url;
  el.rel = "noreferrer";
  return el;
}
function list(id, rows, empty, render) {
  const target = byId(id);
  target.replaceChildren();
  if (!Array.isArray(rows) || rows.length === 0) {
    target.append(node("li", Array.isArray(rows) ? empty : unknown, "meta"));
    return;
  }
  for (const row of rows) target.append(render(row));
}
function header(title, badge) {
  const div = node("div", undefined, "record-head");
  div.append(node("strong", title), badge);
  return div;
}
function utc(value) { return value ? value.replace("T", " ").replace(/Z$/, " UTC") : unknown; }

function update(data) {
  byId("repo").textContent = data.repository ?? unknown;
  byId("mode").textContent = data.mode === "demo" ? "Démonstration locale · données simulées" : "Lecture seule · instantanés locaux";
  byId("asof").textContent = "Dernière observation · " + utc(data.observed_at);
  byId("state").textContent = state(data.state);
  const budgets = byId("budgets");
  budgets.replaceChildren();
  for (const [label, key] of [["Quota disponible", "quota"], ["Appels prévus", "calls"],
    ["Durée prévue (s)", "seconds"], ["Contexte estimé (jetons)", "context_tokens"]]) {
    const cell = node("div");
    cell.append(node("dt", label), node("dd", data.budget?.[key] ?? unknown));
    budgets.append(cell);
  }
  byId("mission-count").textContent = Array.isArray(data.missions) ? data.missions.length : "";
  list("mission-list", data.missions, "Aucune mission dans cet instantané.", row => {
    const li = node("li");
    const variant = row.state === "ACCEPTED" ? "good" : ["BLOCKED", "REJECTED"].includes(row.state) ? "warn" : "";
    li.append(header(row.id, pill(state(row.state), variant)),
      node("p", [row.project ?? unknown, utc(row.at)].join(" · "), "meta"));
    const details = node("details");
    details.append(node("summary", "Empreinte de preuve"), node("code", row.proof));
    li.append(details);
    return li;
  });
  byId("role-count").textContent = Array.isArray(data.roles) ? data.roles.length : "";
  list("role-list", data.roles, "Aucun rôle dans cet instantané.", row => {
    const li = node("li");
    li.append(header(names[row.role] ?? row.role, pill(row.configured ? "Configuré" : "Réservé")),
      node("p", "Activité · " + state(row.activity), "meta"));
    return li;
  });
  byId("blocker").textContent = "Dernier blocage · " + (data.error ?? unknown);
  list("event-list", data.events, "Aucun événement dans cet instantané.", row => {
    const li = node("li");
    li.append(header(row.mission, pill(Object.hasOwn(labels, row.phase) ? state(row.phase) : row.phase)),
      row.url ? link(row.url, "Voir le reçu GitHub") : node("p", utc(row.at), "meta"));
    return li;
  });
  list("pull-list", data.pulls, "Aucune PR dans cet instantané.", row => {
    const li = node("li");
    li.append(header("PR #" + row.number, pill(row.draft === true ? "Brouillon" : state(row.state))),
      link(row.url, "Ouvrir sur GitHub"));
    return li;
  });
}

async function refresh() {
  const button = byId("refresh");
  const feedback = byId("feedback");
  button.disabled = true;
  try {
    const response = await fetch("/snapshot.json", {cache: "no-store", signal: AbortSignal.timeout(5000)});
    if (!response.ok) throw new Error("snapshot");
    update(await response.json());
    feedback.textContent = "";
  } catch {
    update({});
    feedback.textContent = "Instantané indisponible. État actuel · INCONNU.";
  } finally {
    button.disabled = false;
  }
}
byId("refresh").addEventListener("click", refresh);
refresh();
