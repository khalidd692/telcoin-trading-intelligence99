"use strict";

const byId = id => document.getElementById(id);
const statuses = {
  ACTIVE: "ACTIF", WAITING: "EN ATTENTE", BLOCKED: "BLOQUÉ",
  ACCEPTED: "ACCEPTÉ", STOPPED: "ARRÊTÉ", UNAVAILABLE: "INDISPONIBLE",
};
const stages = {
  WAITING: "En attente du superviseur", QUEUED: "Mission prête dans la file",
  DEPENDENCIES: "Prérequis en attente", PREPARING: "Réservation du checkpoint",
  ACK: "Accusé de réception", WORKER: "Analyse et développement",
  VERIFICATION: "Vérification Docker", VERIFICATION_PENDING: "Vérification en attente",
  PUBLICATION: "Publication GitHub", COMPLETE: "Livraison confirmée",
  STOP_REQUESTED: "Arrêt demandé", STOPPED: "Session arrêtée",
  RECONCILIATION: "Vérifier les checkpoints avant toute reprise",
  AWAITING_HUMAN: "Réconciliation requise par l’opérateur",
  REJECTED: "Vérification rejetée", BLOCKED: "Exécution bloquée",
  EVIDENCE_UNAVAILABLE: "Preuve indépendante indisponible",
  RUNNING: "Exécution enregistrée", WORKER_EXITED: "Reçu du worker enregistré",
  ACCEPTED: "Vérification acceptée",
};
const blockers = {
  GITHUB_RATE_LIMIT: "Limite de requêtes GitHub atteinte",
  GITHUB_RECEIPT_OR_APPROVAL_UNCONFIRMED: "Mandat ou reçu GitHub à confirmer",
  SOURCE_UNAVAILABLE_OR_INVALID: "Source GitHub indisponible ou invalide",
};
const testLabels = {
  "bounded-model-receipt": "Reçu du modèle borné",
  "approved-function-diff": "Diff limité à la fonction approuvée",
  "baseline-fails": "Échec attendu sur la version d’origine",
  "candidate-passes": "Réussite du correctif",
};
const receiptNames = {ACK: "Accusé de réception", EVIDENCE: "Preuve GitHub", RESULT: "Résultat GitHub"};
const localTime = new Intl.DateTimeFormat("fr-FR", {dateStyle: "short", timeStyle: "medium"});
let snapshot = null;
let selectedRole = null;
let updating = false;
let lastContent = "";

function make(name, text, className) {
  const element = document.createElement(name);
  if (text !== undefined && text !== null) element.textContent = String(text);
  if (className) element.className = className;
  return element;
}

function text(id, value) {
  const element = byId(id);
  if (element.textContent !== value) element.textContent = value;
}

function statusTag(status) {
  return make("span", statuses[status] || "INDISPONIBLE", "tag " + (status || "").toLowerCase());
}

function timeLabel(iso) {
  return iso ? localTime.format(new Date(iso)) : "Horodatage indisponible";
}

function externalLink(label, url) {
  const link = make("a", label);
  link.href = url;
  link.target = "_blank";
  link.rel = "noopener noreferrer";
  return link;
}

function empty(message) {
  return make("p", message, "muted");
}

function fields(values) {
  const list = make("dl", null, "fields");
  for (const [label, value] of values) {
    if (value === undefined || value === null) continue;
    const detail = make("dd");
    detail.append(value instanceof Node ? value : String(value));
    list.append(make("dt", label), detail);
  }
  return list;
}

function missionProgress(mission) {
  const ack = mission.receipts.ACK;
  const verified = mission.handoffs.some(proof => proof.role === "tel99-verifier" && proof.ok);
  const progress = [
    ["Admission", true, false],
    ["Réception", ack.state === "CONFIRMED", mission.stage === "ACK"],
    ["Travail", mission.handoffs.some(proof => proof.role === "tel99-dev"), mission.stage === "WORKER"],
    ["Tests", verified, ["VERIFICATION", "VERIFICATION_PENDING"].includes(mission.stage)],
    ["Livraison", mission.stage === "COMPLETE", mission.stage === "PUBLICATION"],
  ];
  const output = make("ol", null, "steps");
  output.setAttribute("aria-label", "Étapes de la mission");
  for (const [label, done, working] of progress) {
    const step = make("li", label, done ? "done" : working ? "current" : "");
    step.setAttribute("aria-label", label + (done ? ", attestée" : working ? ", en cours ou à réconcilier" : ", en attente"));
    if (working && !done) step.setAttribute("aria-current", "step");
    output.append(step);
  }
  return output;
}

function missionCard(mission, wasOpen) {
  const article = make("article", null, "mission");
  const heading = make("div", null, "heading");
  const title = make("h3");
  title.append(externalLink("#" + mission.issue + " · " + mission.function, mission.issue_url));
  heading.append(title, statusTag(mission.status));
  const description = make("p", null, "metadata");
  description.append(make("strong", stages[mission.stage] || mission.stage), " · ",
    make("code", mission.id), " · ", make("code", mission.model));
  article.append(heading, description, missionProgress(mission));
  if (mission.dependencies.length) {
    article.append(make("p", "Dépend de " + mission.dependencies.join(", "), "muted metadata"));
  }
  if (mission.publication_pending) {
    article.append(make("p", "Publication incertaine. Consulter le reçu avant de relancer.", "warning metadata"));
  }

  const links = make("div", null, "inline links");
  links.append(externalLink("Approbation", mission.approval_url));
  for (const [phase, receipt] of Object.entries(mission.receipts)) {
    if (receipt.url) links.append(externalLink(receiptNames[phase], receipt.url));
  }
  if (mission.pull_request) links.append(externalLink("Ouvrir la PR brouillon", mission.pull_request));
  article.append(links);

  const details = make("details");
  details.dataset.mission = mission.id;
  details.open = wasOpen;
  const attempt = mission.attempt ? mission.attempt + " / " + mission.max_attempts : null;
  const counters = mission.measurements;
  details.append(make("summary", "Checkpoint, tests et transmissions"), fields([
    ["Fichier approuvé", make("code", mission.path)],
    ["Contrat SHA-256", make("code", mission.contract_sha256)],
    ["Commit de base", make("code", mission.base_sha)],
    ["Checkpoint", mission.checkpoint],
    ["Date du checkpoint", mission.at && timeLabel(mission.at)],
    ["Tentative", attempt],
    ["Génération", counters.generation_seconds === undefined ? null : counters.generation_seconds + " s"],
    ["Vérification", counters.verification_seconds === undefined ? null : counters.verification_seconds + " s"],
    ["RAM du PC avant/après génération", counters.host_memory_before_mib === undefined ? null :
      counters.host_memory_before_mib + " / " + (counters.host_memory_after_mib ?? "—") + " Mio"],
  ]));
  for (const [phase, receipt] of Object.entries(mission.receipts)) {
    if (receipt.state === "PENDING_RECONCILIATION" || receipt.state === "NOT_SENT") {
      details.append(make("p", receiptNames[phase] + " · " +
        (receipt.state === "NOT_SENT" ? "envoi non effectué" : "réconciliation en attente"), "warning metadata"));
    }
  }

  details.append(make("h3", "Contrôles indépendants"));
  if (mission.checks.length) {
    const checks = make("ul", null, "events");
    for (const check of mission.checks) {
      const code = check.exit_code === null ? "" : " · sortie " + check.exit_code;
      checks.append(make("li", (testLabels[check.name] || check.name) + " · " +
        (check.ok ? "conforme" : "échec") + code, check.ok ? "" : "warning"));
    }
    details.append(checks);
  } else {
    details.append(empty("Aucun résultat indépendant enregistré."));
  }

  details.append(make("h3", "Transmissions attestées"));
  if (mission.handoffs.length) {
    const transfers = make("ol", null, "events");
    for (const handoff of mission.handoffs) {
      transfers.append(make("li", handoff.role + (handoff.model ? " · " + handoff.model : "") +
        " · " + (handoff.ok ? "reçu vérifié" : "contrôle en échec")));
    }
    details.append(transfers);
  } else {
    details.append(empty("Aucun reçu de rôle enregistré."));
  }
  article.append(details);
  return article;
}

function roleDetail() {
  if (!selectedRole) return;
  const detail = byId("role-detail");
  const role = snapshot?.roles.find(item => item.id === selectedRole);
  if (!role) {
    detail.replaceChildren(empty("Registre indisponible."));
    return;
  }
  text("role-title", role.label);
  detail.replaceChildren(fields([
    ["Profil", make("code", role.id)],
    ["Disponibilité", statusTag(role.status)],
    ["Moteur", role.engine === "LLM" ? "Modèle local" : role.engine === "DETERMINISTIC" ? "Déterministe" : "Indisponible"],
    ["Tâche actuelle", role.active_mission],
    ["Périmètre", role.scope],
    ["Outils du rôle", role.tools.length ? role.tools.join(", ") : "Aucun outil attesté"],
    ["Contrôles conformes", role.history.filter(item => item.ok).length + " / " + role.history.length],
  ]), make("h3", "Historique des preuves"));
  if (!role.history.length) {
    detail.append(empty("Aucun reçu dans ce registre."));
    return;
  }
  for (const proof of role.history) {
    detail.append(fields([
      ["Mission", externalLink(proof.mission, proof.issue_url)],
      ["Modèle", proof.model],
      ["Empreinte", proof.sha256 && make("code", proof.sha256)],
      ["Checkpoint", timeLabel(proof.at)],
      ["Résultat", proof.ok ? "Conforme" : "Échec"],
    ]));
  }
}

function render(data) {
  snapshot = data;
  const progress = data.missions.filter(mission => mission.stage === "COMPLETE").length;
  const rolesActive = data.roles.filter(role => role.status === "ACTIVE").length;
  text("delivered", progress + " / " + data.missions.length);
  text("active-roles", String(rolesActive));
  const ram = data.resources.memory_available_mib;
  text("memory", ram === null ? "Indisponible" : new Intl.NumberFormat("fr-FR").format(ram) + " Mio");
  text("cpu", data.resources.logical_cpus === null ? "Indisponible" : String(data.resources.logical_cpus));
  const sv = data.supervisor;
  const tag = byId("supervisor-status");
  tag.replaceWith(Object.assign(statusTag(sv.status), {id: tag.id}));
  const freshness = sv.freshness === "fresh" ? "Heartbeat récent"
    : sv.freshness === "stale" ? "Heartbeat périmé" : "Heartbeat indisponible";
  text("freshness", freshness + " · Dernière lecture " + timeLabel(data.read_at));
  text("supervisor-stage", stages[sv.stage] || sv.stage);
  text("heartbeat", sv.heartbeat ? "Signal reçu " + timeLabel(sv.heartbeat) : "");
  text("blocker", blockers[sv.blocker] || "");
  byId("blocker").hidden = !sv.blocker;
  byId("role-observation").hidden = sv.stage !== "WORKER" || rolesActive !== 0;
  byId("open-stop").hidden = !data.stop_enabled;
  text("control-state", sv.stop_requested ? "Arrêt demandé. Suivre la confirmation du superviseur." :
    data.stop_enabled ? "Contrôle d’arrêt autorisé pour cette session." : "Lecture seule");
  const mandate = byId("mandate");
  mandate.hidden = !data.campaign;
  if (data.campaign) mandate.href = data.campaign.url;
  else mandate.removeAttribute("href");

  const digest = JSON.stringify([data.missions, data.roles]);
  if (digest === lastContent) return;
  lastContent = digest;
  const openIds = new Set([...byId("mission-list").querySelectorAll("details[open]")].map(item => item.dataset.mission));
  byId("mission-list").replaceChildren(...(data.missions.length
    ? data.missions.map(item => missionCard(item, openIds.has(item.id)))
    : [empty("Aucune mission admise dans ce registre.")]));
  const events = data.missions.filter(mission => mission.at).sort((a, b) => b.at.localeCompare(a.at));
  byId("events").replaceChildren(...(events.length ? events.map(item => make("li",
    timeLabel(item.at) + " · #" + item.issue + " · " + (stages[item.checkpoint] || item.checkpoint)))
    : [make("li", "Aucun checkpoint disponible.", "muted")]));
  const focusedRole = document.activeElement?.dataset.role;
  byId("roles").replaceChildren(...data.roles.map(role => {
    const button = make("button", null, "role");
    button.type = "button";
    button.dataset.role = role.id;
    button.setAttribute("aria-haspopup", "dialog");
    button.append(make("strong", role.label), statusTag(role.status), make("small", role.id));
    return button;
  }));
  if (focusedRole) byId("roles").querySelector('[data-role="' + focusedRole + '"]')?.focus();
  roleDetail();
}

function unavailable() {
  snapshot = null;
  lastContent = "";
  text("supervisor-status", "INDISPONIBLE");
  byId("supervisor-status").className = "tag unavailable";
  text("supervisor-stage", "Registre local indisponible");
  text("freshness", "Dernière lecture impossible");
  text("heartbeat", "");
  byId("blocker").hidden = true;
  byId("role-observation").hidden = true;
  for (const id of ["delivered", "active-roles", "memory", "cpu"]) text(id, "—");
  byId("mandate").hidden = true;
  byId("open-stop").hidden = true;
  text("control-state", "Lecture seule");
  byId("mission-list").replaceChildren(empty("État local indisponible."));
  byId("roles").replaceChildren(empty("État de l’équipe indisponible."));
  byId("events").replaceChildren();
  roleDetail();
}

async function refresh() {
  if (updating) return;
  updating = true;
  try {
    const response = await fetch("/status.json", {cache: "no-store", signal: AbortSignal.timeout(5500)});
    if (!response.ok) throw new Error("Registre indisponible");
    render(await response.json());
  } catch {
    unavailable();
  } finally {
    updating = false;
  }
}

byId("refresh").addEventListener("click", refresh);
byId("roles").addEventListener("click", event => {
  const button = event.target.closest("button[data-role]");
  if (!button) return;
  selectedRole = button.dataset.role;
  roleDetail();
  byId("role-dialog").showModal();
});
byId("close-role").addEventListener("click", () => byId("role-dialog").close());
byId("role-dialog").addEventListener("close", () => { selectedRole = null; });
byId("open-stop").addEventListener("click", () => byId("stop-dialog").showModal());
byId("close-stop").addEventListener("click", () => byId("stop-dialog").close());
byId("stop-dialog").addEventListener("close", () => {
  byId("stop-code").value = "";
  byId("stop-confirm").checked = false;
  text("stop-result", "");
});
byId("send-stop").addEventListener("click", async () => {
  const code = byId("stop-code").value;
  const confirm = byId("stop-confirm").checked;
  if (!code || !confirm) {
    text("stop-result", "Saisir le code et cocher la confirmation.");
    return;
  }
  const button = byId("send-stop");
  button.disabled = true;
  try {
    const response = await fetch("/actions/stop", {
      method: "POST", headers: {"Content-Type": "application/json"},
      body: JSON.stringify({code, confirm}), signal: AbortSignal.timeout(5500),
    });
    if (!response.ok) {
      text("stop-result", response.status === 409 ? "Campagne inactive ou arrêt déjà demandé." : "Arrêt refusé.");
      return;
    }
    byId("stop-dialog").close();
    await refresh();
  } catch {
    text("stop-result", "Demande non confirmée. Actualiser l’état du superviseur.");
  } finally {
    button.disabled = false;
  }
});
refresh();
setInterval(refresh, 4000);
