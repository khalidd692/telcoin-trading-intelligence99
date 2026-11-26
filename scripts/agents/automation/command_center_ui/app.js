"use strict";

(() => {
  const state = {
    csrfToken: null,
    controlsEnabled: false,
    snapshot: null,
    cc: null,
    activeView: "conversations",
    activeConvId: null,
    activeConv: null,
    activeJobId: null,
    retryableJobId: null,
    previewData: null,
    selectedFile: null,
  };

  const $ = (id) => document.getElementById(id);

  function mk(tag, cls, text) {
    const node = document.createElement(tag);
    if (cls) node.className = cls;
    if (text !== undefined && text !== null) node.textContent = String(text);
    return node;
  }

  function statusClass(s) {
    const v = String(s || "").toUpperCase();
    if (["DELIVERED", "ACCEPTED", "DONE", "READY", "PROVEN", "VERIFIED", "LIVE_APP"].includes(v)) return "status-ok";
    if (["RUNNING", "QUEUED", "DELEGATING", "WAITING_OLLAMA", "PARTIAL", "PAUSED", "PENDING", "IN_PROGRESS"].includes(v)) return "status-warn";
    return "status-err";
  }

  async function apiGet(url) {
    const r = await fetch(url, { cache: "no-store" });
    const data = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(data.error || `HTTP ${r.status}`);
    return data;
  }

  async function apiMutate(method, url, body) {
    if (!state.controlsEnabled || !state.csrfToken) {
      throw new Error("Interface en lecture seule : relancez avec --allow-controls.");
    }
    const r = await fetch(url, {
      method,
      headers: {
        "Content-Type": "application/json",
        "X-TEL99-Token": state.csrfToken,
      },
      body: body !== undefined ? JSON.stringify(body) : undefined,
    });
    const data = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(data.error || `HTTP ${r.status}`);
    return data;
  }

  function switchView(viewId) {
    state.activeView = viewId;
    document.querySelectorAll(".nav-btn").forEach((btn) => {
      btn.classList.toggle("active", btn.dataset.view === viewId);
    });
    document.querySelectorAll(".view-panel").forEach((panel) => {
      panel.classList.toggle("active", panel.id === `view-${viewId}`);
    });
  }

  function setChatBanner(text, cls, showCancel, retryJobId) {
    const bar = $("chatStatusText");
    bar.textContent = text;
    bar.className = cls || "muted";
    $("btnCancelJob").classList.toggle("hidden", !showCancel);
    state.retryableJobId = retryJobId || null;
    $("btnRetryJob").classList.toggle("hidden", !state.retryableJobId);
  }

  function renderTopbar() {
    const snap = state.snapshot;
    const cc = state.cc;
    const pills = $("topPills");
    const items = [];
    if (snap && snap.resources) {
      const ram = snap.resources.available_memory_mib;
      items.push(mk("span", `pill ${ram && ram < 1200 ? "warn" : "ok"}`, `RAM libre: ${ram ?? "?"} MiB`));
    }
    if (cc && cc.docker_sandbox) {
      items.push(mk("span", `pill ${cc.docker_sandbox.ready ? "ok" : "err"}`, cc.docker_sandbox.ready ? "Sandbox Docker: OK" : "Sandbox Docker: Indisponible"));
    }
    if (cc && cc.certification && cc.certification.phase2_chain && cc.certification.phase2_chain.status) {
      const p2 = cc.certification.phase2_chain;
      items.push(mk("span", `pill ${p2.status === "RUNNING" ? "warn" : "ok"}`, `Phase 2: ${p2.status}`));
    }
    if (cc && cc.ai_radar) {
      items.push(mk("span", `pill ${cc.ai_radar.online ? "ok" : "warn"}`, cc.ai_radar.online ? "AI Radar: En ligne" : "AI Radar: Hors ligne"));
    }
    items.push(mk("span", `pill ${state.controlsEnabled ? "ok" : "warn"}`, state.controlsEnabled ? "Contrôles actifs" : "Lecture seule"));
    pills.replaceChildren(...items);
  }

  function renderTeamSelectorAndView() {
    const agents = (state.cc && state.cc.team) || [];
    $("badgeTeam").textContent = String(agents.length);
    const sel = $("chatRoleSelect");
    const prev = sel.value || (state.activeConv ? state.activeConv.role : "coordination");
    if (sel.options.length !== agents.length) {
      sel.replaceChildren(
        ...agents.map((a) => {
          const opt = document.createElement("option");
          opt.value = a.role;
          opt.textContent = `${a.label_fr} (${a.name})`;
          return opt;
        })
      );
    }
    if (prev && Array.from(sel.options).some((o) => o.value === prev)) {
      sel.value = prev;
    }

    const cards = agents.map((a) => {
      const card = mk("div", "agent-card");
      const head = mk("div", "agent-head");
      head.append(mk("div", "avatar", a.avatar || "AGT"));
      const meta = mk("div");
      meta.append(mk("div", "", a.label_fr), mk("div", "muted", `${a.name} · ${a.role}`));
      head.append(meta);
      card.append(head);
      card.append(mk("div", "muted", a.tagline || a.description || ""));
      const v3l = a.v3_local ? `V3 loc: ${a.v3_local.passed}/${a.v3_local.total}` : "V3 loc: n/a";
      const v3h = a.v3_hybrid ? `V3 hyb: ${a.v3_hybrid.passed}/${a.v3_hybrid.total}` : "";
      const lvl = `${a.proven_level_label || "Niveau 0"} · ${a.skill_ready ? "Skill actif" : "Sans skill"}`;
      card.append(mk("div", "muted", `${lvl} · ${v3l} ${v3h}`.trim()));
      const actions = mk("div", "row-inline");
      const talkBtn = mk("button", "btn primary sm", a.is_commander ? "Ouvrir Mode Commandant" : "Discuter");
      talkBtn.addEventListener("click", () => startConversationWithAgent(a.role, a.is_commander));
      actions.append(talkBtn);
      card.append(actions);
      return card;
    });
    $("teamGrid").replaceChildren(...(cards.length ? cards : [mk("div", "muted", "Aucun agent chargé.")]));
  }

  async function startConversationWithAgent(role, teamMode) {
    try {
      const agent = ((state.cc && state.cc.team) || []).find((x) => x.role === role);
      const title = agent ? `Discussion · ${agent.label_fr}` : "Nouvelle conversation";
      const conv = await apiMutate("POST", "/api/cc/conversations", {
        title,
        role,
        team_mode: Boolean(teamMode),
        confidential: true,
        hybrid: false,
      });
      state.activeConvId = conv.id;
      state.activeConv = conv;
      await refreshAll();
      renderActiveConversation();
      switchView("conversations");
      $("chatInput").focus();
    } catch (err) {
      setChatBanner(`Erreur création session : ${err.message}`, "status-err", false);
    }
  }

  function renderConversationsList() {
    const convs = (state.cc && state.cc.conversations) || [];
    $("badgeConvs").textContent = String(convs.length);
    if (!convs.length) {
      $("convList").replaceChildren(mk("div", "muted", "Aucune conversation. Cliquez sur « Nouvelle » pour démarrer."));
      return;
    }
    const items = convs.map((c) => {
      const box = mk("div", `conv-item ${c.id === state.activeConvId ? "active" : ""}`);
      box.append(mk("div", "conv-item-title", c.title || "Conversation"));
      const meta = mk("div", "conv-item-meta");
      meta.append(
        mk("span", "", `${c.team_mode ? "Commandant" : c.role} · ${c.message_count} msg`),
        mk("span", "", c.confidential ? "Local" : "Hybride")
      );
      box.append(meta);
      box.addEventListener("click", () => selectConversation(c.id));
      return box;
    });
    $("convList").replaceChildren(...items);
  }

  async function selectConversation(convId) {
    try {
      const conv = await apiGet(`/api/cc/conversations/${encodeURIComponent(convId)}`);
      state.activeConvId = conv.id;
      state.activeConv = conv;
      renderConversationsList();
      renderActiveConversation();
      // Surface any retryable failed/interrupted job for this conversation so user can resume without duplicating!
      if (!state.activeJobId && state.cc && Array.isArray(state.cc.chat_jobs)) {
        const failed = state.cc.chat_jobs.find(
          (j) => j.conversation_id === conv.id && (j.status === "ERROR" || j.status === "CANCELLED")
        );
        if (failed) {
          setChatBanner(
            `Dernière requête interrompue (${failed.error_category || failed.status}) : ${failed.error || failed.phase}`,
            "status-err",
            false,
            failed.job_id
          );
        } else {
          setChatBanner("Prêt — mode local confidentiel par défaut (aucun appel modèle automatique).", "muted", false, null);
        }
      }
    } catch (err) {
      setChatBanner(`Erreur chargement conversation : ${err.message}`, "status-err", false);
    }
  }

  function renderActiveConversation() {
    const conv = state.activeConv;
    if (!conv) {
      $("chatMessages").replaceChildren(
        mk("div", "muted", "Sélectionnez une conversation ou créez-en une nouvelle pour parler à l'un des 12 agents ou au Mode Commandant.")
      );
      return;
    }
    $("chatRoleSelect").value = conv.role || "coordination";
    $("chatTeamToggle").checked = Boolean(conv.team_mode);
    $("chatConfidentialToggle").checked = Boolean(conv.confidential !== false);
    $("chatHybridToggle").checked = Boolean(conv.hybrid && !conv.confidential);
    $("chatHybridToggle").disabled = Boolean(conv.confidential !== false);

    const msgs = conv.messages || [];
    if (!msgs.length) {
      $("chatMessages").replaceChildren(
        mk("div", "muted", "Conversation prête. Mode local confidentiel actif par défaut (aucun appel modèle automatique avant votre message).")
      );
      return;
    }

    const nodes = msgs.map((m) => {
      const wrap = mk("div", `msg ${m.role === "user" ? "user" : "assistant"}`);
      const hdr = mk("div", "msg-header");
      if (m.role === "user") {
        hdr.append(mk("span", "", "Vous"), mk("span", "", m.created_at || ""));
      } else {
        const who = `${m.label_fr || m.agent_name || "Agent"} (${m.agent_name || m.agent_role || ""})`;
        const modeLabel = ({fast:"Rapide", auto:"Intelligent", deep:"Approfondi"})[m.response_mode] || "Ancien mode";
        const info = `${modeLabel} · ${m.provider_used || "?"} / ${m.model_used || "?"} · ${m.duration_seconds ?? "?"}s · ${m.confidential ? "Local" : "Hybride"}`;
        hdr.append(mk("span", "", who));
        const right = mk("div", "row-inline");
        right.append(mk("span", "", info));
        const copyBtn = mk("button", "btn sm", "Copier");
        copyBtn.addEventListener("click", () => {
          navigator.clipboard.writeText(String(m.content || "")).then(() => {
            copyBtn.textContent = "Copié";
            setTimeout(() => { copyBtn.textContent = "Copier"; }, 1200);
          }).catch(() => {});
        });
        right.append(copyBtn);
        hdr.append(right);
      }
      wrap.append(hdr);
      wrap.append(mk("div", "msg-body", m.content || ""));

      if (Array.isArray(m.delegated_specialists) && m.delegated_specialists.length) {
        const dbox = mk("div", "delegation-box");
        dbox.append(mk("strong", "", `Spécialistes réellement mobilisés (${m.delegated_specialists.length}) :`));
        m.delegated_specialists.forEach((ds) => {
          const det = document.createElement("details");
          det.style.marginTop = "6px";
          const sum = document.createElement("summary");
          sum.textContent = `${ds.label_fr || ds.role} (${ds.agent_name}) · ${ds.provider_used}/${ds.model_used} · ${ds.duration_seconds ?? "?"}s`;
          det.append(sum);
          det.append(mk("div", "msg-body", ds.response || ""));
          dbox.append(det);
        });
        wrap.append(dbox);
      }
      return wrap;
    });
    const container = $("chatMessages");
    container.replaceChildren(...nodes);
    container.scrollTop = container.scrollHeight;
  }

  async function sendChatMessage() {
    const text = $("chatInput").value.trim();
    if (!text) return;
    try {
      if (!state.activeConvId) {
        const role = $("chatRoleSelect").value || "coordination";
        const conv = await apiMutate("POST", "/api/cc/conversations", {
          title: text.slice(0, 56),
          role,
          team_mode: $("chatTeamToggle").checked,
          confidential: $("chatConfidentialToggle").checked,
          hybrid: $("chatHybridToggle").checked,
        });
        state.activeConvId = conv.id;
        state.activeConv = conv;
      }
      $("chatInput").value = "";
      $("btnSendChat").disabled = true;
      setChatBanner("Envoi en file sécurisée…", "status-warn", true);
      const job = await apiMutate("POST", `/api/cc/conversations/${encodeURIComponent(state.activeConvId)}/messages`, {
        message: text,
        response_mode: $("chatResponseMode").value,
        role: $("chatRoleSelect").value,
        team_mode: $("chatTeamToggle").checked,
        confidential: $("chatConfidentialToggle").checked,
        hybrid: $("chatHybridToggle").checked,
      });
      state.activeJobId = job.job_id;
      await selectConversation(state.activeConvId);
      pollActiveJob();
    } catch (err) {
      $("btnSendChat").disabled = false;
      setChatBanner(`Erreur : ${err.message}`, "status-err", false);
    }
  }

  async function pollActiveJob() {
    if (!state.activeJobId) return;
    try {
      const job = await apiGet(`/api/cc/jobs/${encodeURIComponent(state.activeJobId)}`);
      if (["QUEUED", "WAITING_OLLAMA", "RUNNING", "DELEGATING"].includes(job.status)) {
        const delInfo = (job.delegated_specialists || []).length
          ? ` · ${job.delegated_specialists.length} spécialiste(s) consulté(s)`
          : "";
        setChatBanner(`[${job.status}] ${job.phase || "Traitement en cours…"}${delInfo}`, "status-warn", true);
        setTimeout(pollActiveJob, 1200);
      } else {
        const finishedId = state.activeJobId;
        state.activeJobId = null;
        $("btnSendChat").disabled = false;
        if (job.status === "DONE") {
          setChatBanner(`Réponse reçue (${job.provider_used}/${job.model_used} en ${job.duration_seconds}s).`, "status-ok", false, null);
        } else if (job.status === "CANCELLED") {
          setChatBanner("Demande annulée proprement (reprise sans doublon disponible).", "muted", false, finishedId);
        } else {
          setChatBanner(
            `Erreur [${job.error_category || "ERREUR"}] : ${job.error || job.phase || "échec"}`,
            "status-err",
            false,
            finishedId
          );
        }
        if (state.activeConvId) {
          await selectConversation(state.activeConvId);
        }
        await refreshAll();
      }
    } catch (err) {
      state.activeJobId = null;
      $("btnSendChat").disabled = false;
      setChatBanner(`Suivi interrompu : ${err.message}`, "status-err", false);
    }
  }

  function renderProjectsAndDeliveries() {
    const projects = (state.cc && state.cc.projects) || [];
    $("badgeProjects").textContent = String(projects.length);

    const projectCards = projects.map((p) => {
      const card = mk("div", "card");
      const top = mk("div", "section-header");
      const left = mk("div");
      left.append(
        mk("h3", "", `${p.name} (${p.project})`),
        mk("div", "muted", p.path)
      );
      const badge = mk("span", `pill ${statusClass(p.status).replace("status-", "")}`, `${p.status}${p.runner_active ? " · ACTIF" : ""}`);
      top.append(left, badge);
      card.append(top);

      if (p.goal) card.append(mk("div", "muted", `Objectif : ${p.goal.slice(0, 260)}`));
      const acc = p.missions_total ? `${p.missions_accepted ?? 0}/${p.missions_total} missions acceptées` : "Application / dossier suivi";
      const reqSum = p.requirements_summary
        ? ` · Exigences vérifiées: ${p.requirements_summary.verified}/${p.requirements_summary.total}`
        : "";
      card.append(mk("div", "", `${acc}${reqSum} · Révision plan #${p.plan_revision || 1}`));

      if (p.agents_called && p.agents_called.length) {
        card.append(mk("div", "muted", `Agents réellement appelés : ${p.agents_called.join(", ")}`));
      }
      if (p.deterministic_verifiers_run && p.deterministic_verifiers_run.length) {
        card.append(mk("div", "muted", `Vérificateurs déterministes : ${p.deterministic_verifiers_run.join(", ")}`));
      }

      const controls = mk("div", "row-inline");
      controls.style.marginTop = "10px";
      if (p.initialized) {
        const bPause = mk("button", "btn sm", "Pause");
        bPause.addEventListener("click", () => projectControl(p.path, "pause", false));
        const bRes = mk("button", "btn sm", "Reprendre");
        bRes.addEventListener("click", () => projectControl(p.path, "resume", false));
        const bResFail = mk("button", "btn sm", "Reprendre échecs");
        bResFail.addEventListener("click", () => projectControl(p.path, "resume", true));
        const bStop = mk("button", "btn danger sm", "Arrêt sûr (projet)");
        bStop.addEventListener("click", () => {
          if (window.confirm(`Confirmer l'arrêt sécurisé du projet « ${p.name} » uniquement ?`)) {
            projectControl(p.path, "stop", false);
          }
        });
        controls.append(bPause, bRes, bResFail, bStop);
      }
      if (p.loopback_url) {
        const a = document.createElement("a");
        a.href = p.loopback_url;
        a.target = "_blank";
        a.rel = "noopener noreferrer";
        a.className = "btn primary sm";
        a.textContent = `Ouvrir ${p.loopback_url}`;
        controls.append(a);
      }
      card.append(controls);

      if (p.files_on_disk && p.files_on_disk.length) {
        const fbox = mk("div", "row-inline");
        fbox.style.marginTop = "10px";
        fbox.append(mk("span", "muted", "Fichiers livrés (lecture seule) :"));
        p.files_on_disk.slice(0, 14).forEach((rel) => {
          const fb = mk("button", "btn sm", rel);
          fb.addEventListener("click", () => openReadOnlyFile(p.path, rel));
          fbox.append(fb);
        });
        card.append(fbox);
      }

      if (p.requirements && p.requirements.length) {
        const det = document.createElement("details");
        det.style.marginTop = "8px";
        const sum = document.createElement("summary");
        sum.textContent = `Matrice des exigences (${p.requirements.length})`;
        det.append(sum);
        const tbl = document.createElement("table");
        const tb = document.createElement("tbody");
        p.requirements.forEach((r) => {
          const tr = document.createElement("tr");
          tr.append(
            mk("td", "", r.id),
            mk("td", "", r.source_text || ""),
            mk("td", statusClass(r.status), r.status || "PENDING"),
            mk("td", "muted", (r.evidence || []).join(" | "))
          );
          tb.append(tr);
        });
        tbl.append(tb);
        det.append(tbl);
        card.append(det);
      }

      if (p.log_tail) {
        const detL = document.createElement("details");
        detL.style.marginTop = "8px";
        const sumL = document.createElement("summary");
        sumL.textContent = "Journal récent du runner";
        detL.append(sumL);
        detL.append(mk("div", "code-viewer", p.log_tail));
        card.append(detL);
      }
      return card;
    });
    $("projectsList").replaceChildren(...(projectCards.length ? projectCards : [mk("div", "muted", "Aucun projet enregistré.")]));

    // Deliveries tab
    const delivRows = projects.map((p) => {
      const tr = document.createElement("tr");
      tr.append(
        mk("td", "", p.name),
        mk("td", statusClass(p.status), p.status),
        mk("td", "", String((p.files_on_disk || []).length)),
        mk("td", "muted", p.startup_command || p.loopback_url || "—")
      );
      const tdAct = document.createElement("td");
      if (p.loopback_url) {
        const a = document.createElement("a");
        a.href = p.loopback_url;
        a.target = "_blank";
        a.rel = "noopener noreferrer";
        a.className = "btn primary sm";
        a.textContent = "Ouvrir";
        tdAct.append(a);
      } else if ((p.files_on_disk || []).length) {
        const btn = mk("button", "btn sm", "Voir README / 1er fichier");
        const first = p.files_on_disk.find((f) => f.toLowerCase().endsWith("readme.md")) || p.files_on_disk[0];
        btn.addEventListener("click", () => {
          switchView("projects");
          openReadOnlyFile(p.path, first);
        });
        tdAct.append(btn);
      }
      tr.append(tdAct);
      return tr;
    });
    $("deliveriesTable").replaceChildren(...delivRows);
  }

  async function projectControl(projectPath, action, resumeRejected) {
    try {
      const res = await apiMutate("POST", "/api/cc/projects/control", {
        project_dir: projectPath,
        action,
        resume_rejected: Boolean(resumeRejected),
        confidential: $("projConfidentialToggle").checked,
        hybrid: $("projHybridToggle").checked,
      });
      $("projFeedback").textContent = `Action '${action}' appliquée sur ${projectPath}${res.restarted_pid ? ` (PID ${res.restarted_pid})` : ""}.`;
      $("projFeedback").className = "status-ok";
      await refreshAll();
    } catch (err) {
      $("projFeedback").textContent = `Erreur contrôle projet : ${err.message}`;
      $("projFeedback").className = "status-err";
    }
  }

  async function openReadOnlyFile(projectPath, relPath) {
    try {
      const res = await apiGet(
        `/api/cc/projects/file?project=${encodeURIComponent(projectPath)}&path=${encodeURIComponent(relPath)}`
      );
      $("fileViewerTitle").textContent = `${relPath} (${res.size_bytes} octets · lecture seule)`;
      $("fileViewerContent").textContent = res.content;
      $("fileViewerCard").classList.remove("hidden");
    } catch (err) {
      $("projFeedback").textContent = `Lecture fichier bloquée : ${err.message}`;
      $("projFeedback").className = "status-err";
    }
  }

  async function previewProject() {
    try {
      const res = await apiMutate("POST", "/api/cc/projects/preview", {
        goal_text: $("projGoalInput").value.trim(),
        project_dir: $("projDirInput").value.trim(),
        confidential: $("projConfidentialToggle").checked,
        hybrid: $("projHybridToggle").checked,
      });
      state.previewData = res;
      const box = $("projPreviewBox");
      box.classList.remove("hidden");
      const lines = [
        `Dossier isolé : ${res.workspace_root}`,
        `Mode : ${res.confidential ? "Local confidentiel (Ollama seul)" : "Hybride gratuit opt-in (Groq $0.00 + Ollama)"}`,
        `Sandbox Docker OS : ${res.docker_sandbox_ready ? "PRÊTE" : "INDISPONIBLE (" + res.docker_sandbox_reason + ")"}`,
        `Exigences extraites : ${res.requirements_count}`,
      ];
      if (res.goal_mismatch_requires_revision) {
        lines.push("ATTENTION : un plan scellé existe déjà pour un autre objectif — cochez « Réviser le plan » ou changez de dossier.");
      }
      const ul = document.createElement("ul");
      res.requirements.forEach((r) => {
        ul.append(mk("li", "muted", `[${r.id}] ${r.source_text}`));
      });
      box.replaceChildren(
        mk("h3", "", "Aperçu du périmètre avant confirmation"),
        ...lines.map((l) => mk("div", "", l)),
        ul
      );
      $("btnLaunchProject").disabled = false;
      $("projFeedback").textContent = "Périmètre vérifié. Cliquez sur « Confirmer et lancer le projet » pour démarrer.";
      $("projFeedback").className = "status-ok";
    } catch (err) {
      $("btnLaunchProject").disabled = true;
      $("projFeedback").textContent = `Refus prévisualisation : ${err.message}`;
      $("projFeedback").className = "status-err";
    }
  }

  async function launchProject() {
    if (!state.previewData) return;
    try {
      const res = await apiMutate("POST", "/api/cc/projects/launch", {
        goal_text: $("projGoalInput").value.trim(),
        project_dir: $("projDirInput").value.trim(),
        confidential: $("projConfidentialToggle").checked,
        hybrid: $("projHybridToggle").checked,
        revise_plan: $("projReviseToggle").checked,
        confirmed: true,
      });
      if (!res.ok) {
        $("projFeedback").textContent = `Lancement refusé (${res.status}) : ${res.error}`;
        $("projFeedback").className = "status-err";
        return;
      }
      $("projFeedback").textContent = `Projet lancé en arrière-plan (PID ${res.pid}) dans ${res.workspace_root}. La fermeture du navigateur n'interrompt pas l'exécution.`;
      $("projFeedback").className = "status-ok";
      $("btnLaunchProject").disabled = true;
      await refreshAll();
    } catch (err) {
      $("projFeedback").textContent = `Erreur lancement : ${err.message}`;
      $("projFeedback").className = "status-err";
    }
  }

  function renderActivitySkillsMemoryResources() {
    const cc = state.cc;
    const snap = state.snapshot;
    if (!cc) return;

    // Activity tab
    const jobs = cc.chat_jobs || [];
    const jobRows = jobs.map((j) => {
      const tr = document.createElement("tr");
      tr.append(
        mk("td", "", j.job_id),
        mk("td", "", j.team_mode ? "Commandant" : j.role),
        mk("td", statusClass(j.status), j.status),
        mk("td", "", j.phase || ""),
        mk("td", "muted", `${j.provider_used || "—"} / ${j.model_used || "—"}`)
      );
      return tr;
    });
    $("jobsTable").replaceChildren(...(jobRows.length ? jobRows : [(() => {
      const tr = document.createElement("tr");
      const td = mk("td", "muted", "Aucune requête conversationnelle récente.");
      td.colSpan = 5;
      tr.append(td);
      return tr;
    })()]));

    const leases = (cc.leases && cc.leases.active) || [];
    $("leasesList").replaceChildren(
      ...(leases.length
        ? leases.map((l) => mk("div", "muted", `Bail actif : ${l.actor} -> ${l.resource_id}`))
        : [mk("div", "muted", "Aucun bail CAS bloquant en cours.")])
    );

    // Skills & Learning tab
    const cert = cc.certification || {};
    const v3l = cert.v3_local_after || {};
    const v3h = cert.v3_hybrid_after || {};
    const v4l = cert.v4_local || {};
    const mat = cert.matrix_global || {};
    const end = cert.endurance_run3 || {};
    const certKpis = [
      ["V3 Local (après)", v3l.total ? `${v3l.passed}/${v3l.total} (${Math.round((v3l.success_rate || 0) * 10000) / 100}%)` : "—"],
      ["V3 Hybride", v3h.total ? `${v3h.passed}/${v3h.total} (${Math.round((v3h.success_rate || 0) * 10000) / 100}%)` : "—"],
      ["V4 Inédit (gelé)", v4l.total ? `${v4l.passed}/${v4l.total}` : "En cours (Phase 2)"],
      ["Matrice 12×12", `${mat.cells_evaluated ?? 0}/${mat.cells_total ?? 144} cellules`],
      ["Endurance RUN3", end.duration_minutes ? `${end.duration_minutes} min (${end.missions_accepted}/${end.missions_total})` : "Non validée"],
      ["Skills vérifiés", String((cc.skills || []).length)],
    ];
    $("certKpis").replaceChildren(
      ...certKpis.map(([k, v]) => {
        const c = mk("div", "card");
        c.append(mk("div", "kpi-num", v), mk("div", "muted", k));
        return c;
      })
    );
    $("skillsList").replaceChildren(...(cc.skills || []).map((s) => mk("span", "pill ok", s)));

    // Memory tab
    const mem = cc.memory_entries || [];
    const q = ($("memFilterInput").value || "").trim().toLowerCase();
    const filtered = q ? mem.filter((m) => `${m.title} ${m.body} ${m.kind} ${m.author}`.toLowerCase().includes(q)) : mem;
    const memRows = filtered.slice(-40).reverse().map((m) => {
      const tr = document.createElement("tr");
      tr.append(
        mk("td", "", m.kind || ""),
        mk("td", "", m.title || ""),
        mk("td", m.verified ? "status-ok" : "status-warn", m.verified ? "Vérifiée" : "Non vérifiée"),
        mk("td", "muted", m.author || ""),
        mk("td", "muted", (m.body || "").slice(0, 140))
      );
      return tr;
    });
    $("memoryTable").replaceChildren(...(memRows.length ? memRows : [(() => {
      const tr = document.createElement("tr");
      const td = mk("td", "muted", "Aucune entrée mémoire correspondante.");
      td.colSpan = 5;
      tr.append(td);
      return tr;
    })()]));

    // Resources & Models tab
    const eng = cc.engines || {};
    const ol = eng.ollama || {};
    const resLines = [
      `RAM libre système : ${eng.available_memory_mib ?? (snap && snap.resources ? snap.resources.available_memory_mib : "?")} MiB`,
      `Ollama local : ${ol.reachable ? "Joignable" : "Indisponible"} · Modèles résidents : ${(ol.loaded_models || []).join(", ") || "aucun"}`,
      `Sandbox Docker OS : ${cc.docker_sandbox.ready ? "OK" : "Indisponible"} (${cc.docker_sandbox.image})`,
      `Politique par défaut : Local confidentiel (concurrence=1, 0 $ dépensé, 0 appel Gemini automatique)`,
    ];
    Object.entries(cc.cloud_budgets || {}).forEach(([prov, b]) => {
      resLines.push(
        `Quota cloud gratuit ${prov} : ${b.requests_today}/${b.max_requests_per_day} req · ${b.tokens_today}/${b.max_tokens_per_day} tok · corrompu=${Boolean(b.corrupted)}`
      );
    });
    $("resourcesList").replaceChildren(...resLines.map((l) => mk("div", "", l)));

    // AI Radar tab
    const r = cc.ai_radar || {};
    $("radarStatusText").textContent = r.online
      ? `AI Radar est en ligne et vérifié (HTTP ${r.http_status}) sur ${r.url}.`
      : `AI Radar ne répond pas sur ${r.url}. Lancez-le via launch-tel99.ps1 -Mode Radar.`;
    $("radarStatusText").className = r.online ? "status-ok" : "status-warn";

    renderMorningBrief();
  }

  function renderMorningBrief() {
    const cc = state.cc || {};
    const g8 = cc.proactive_g8 || {};
    const cl = cc.continuous_learning || {};
    const history = Array.isArray(g8.briefs_history) ? g8.briefs_history : [];
    const latest = g8.latest_brief || null;
    if ($("badgeBrief")) $("badgeBrief").textContent = String(history.length);

    if ($("btnToggleLearningPause")) {
      $("btnToggleLearningPause").textContent = cl.paused ? "Reprendre apprentissage" : "Pause apprentissage";
    }
    if ($("btnToggleProactive")) {
      $("btnToggleProactive").textContent = g8.enabled === false ? "Activer G8" : "Désactiver G8";
    }

    const actionRow = $("briefActionRow");
    if (actionRow) {
      if (latest && latest.brief_id) {
        actionRow.classList.remove("hidden");
        $("briefLatestTitle").textContent = `${latest.title || "Brief proactif"} [${latest.status || "PROPOSAL"}]`;
        $("briefLatestMeta").textContent =
          `Déclencheur : ${latest.trigger || "?"} · Date : ${latest.generated_at || "?"} · ` +
          `Durée : ${latest.duration_seconds ?? "?"}s · Feedback : ${latest.owner_feedback || "en attente"}`;
      } else {
        actionRow.classList.add("hidden");
      }
    }

    const grid = $("briefSectionsGrid");
    if (grid) {
      const memVerified = (cc.memory_entries || []).filter((m) => m.verified).slice(0, 4);
      const pendingProjs = (cc.projects || []).filter((p) => !["COMPLETED", "DELIVERED", "ACCEPTED"].includes(String(p.status || "").toUpperCase()));
      const sections = [
        {
          title: "1. Opportunités détectées",
          lines: latest
            ? [latest.title, `Utilité : ${latest.why_useful || "N/A"}`]
            : ["Aucune nouvelle opportunité non couverte pour le moment (zéro travail artificiel)."],
        },
        {
          title: "2. Travail réellement accompli",
          lines: latest && latest.deliverable_rel_path
            ? [`Livrable vérifié : ${latest.deliverable_rel_path} (${latest.deliverable_bytes ?? "?"} octets)`, ...(latest.evidence || [])]
            : ["Aucun livrable proactif additionnel généré sur ce cycle."],
        },
        {
          title: "3. Problèmes anticipés",
          lines: (latest && latest.risks && latest.risks.length)
            ? latest.risks
            : ["Aucun nouveau risque bloquant détecté dans les sources autorisées."],
        },
        {
          title: "4. Nouvelles connaissances",
          lines: memVerified.length
            ? memVerified.map((m) => `[${m.kind}] ${m.title}`)
            : ["Aucune nouvelle entrée vérifiée récente."],
        },
        {
          title: "5. Améliorations de leurs compétences",
          lines: [
            `Apprentissage continu : ${cl.status || "IDLE"} · Exercices : ${cl.exercises_run ?? 0} · Leçons promues : ${cl.verified_lessons_promoted ?? 0}`,
            `Chaîne G6 vérifiée : ${Boolean(cl.g6_chain_proven || cl.transfer_verified)} · Entraînement LoRA 16 Go : désactivé (Skills/Mémoire/Harness).`,
          ],
        },
        {
          title: "6. Propositions pour mes futurs projets",
          lines: pendingProjs.length
            ? pendingProjs.map((p) => `${p.name} (${p.status}, ${p.missions_accepted}/${p.missions_total} missions)`)
            : ["Tous les projets suivis sont livrés ou prêts pour une nouvelle mission."],
        },
        {
          title: "7. Décisions nécessitant mon accord",
          lines: latest && latest.requires_human_approval
            ? [`Validation propriétaire requise pour : ${latest.title} (aucune approbation auto-générée).`]
            : ["Aucune décision sensible en attente."],
        },
        {
          title: "8. Programme de travail recommandé",
          lines: [
            latest && latest.next_action ? latest.next_action : "Utiliser le Command Center ou laisser le créneau nuit (03h00, sans réveil forcé) préparer le prochain brief.",
            "Limites : pas d'exécution PC éteint/veille, pas de dépense, pas de fusion main.",
          ],
        },
      ];
      grid.replaceChildren(
        ...sections.map((sec) => {
          const card = mk("div", "card");
          card.appendChild(mk("h3", "", sec.title));
          const ul = document.createElement("ul");
          sec.lines.forEach((line) => ul.appendChild(mk("li", "", line)));
          card.appendChild(ul);
          return card;
        })
      );
    }

    const tbody = $("briefHistoryTable");
    if (tbody) {
      const rows = history.slice().reverse().map((b) => {
        const tr = document.createElement("tr");
        tr.appendChild(mk("td", "", b.generated_at || ""));
        tr.appendChild(mk("td", "", b.trigger || ""));
        tr.appendChild(mk("td", statusClass(b.status), b.status || ""));
        tr.appendChild(mk("td", "", b.title || ""));
        tr.appendChild(mk("td", "", b.owner_feedback || "—"));
        return tr;
      });
      tbody.replaceChildren(...rows);
    }
  }

  async function sendLearningControl(payload, okMsg) {
    try {
      await apiMutate("POST", "/api/cc/learning/control", payload);
      if ($("briefFeedbackBanner")) {
        $("briefFeedbackBanner").textContent = okMsg;
        $("briefFeedbackBanner").className = "status-ok";
      }
      await refreshAll();
    } catch (err) {
      if ($("briefFeedbackBanner")) {
        $("briefFeedbackBanner").textContent = `Erreur contrôle : ${err.message}`;
        $("briefFeedbackBanner").className = "status-err";
      }
    }
  }

  async function refreshAll() {
    try {
      const [snap, cc] = await Promise.all([
        apiGet("/api/snapshot.json"),
        apiGet("/api/cc/state"),
      ]);
      state.snapshot = snap;
      state.cc = cc;
      state.controlsEnabled = Boolean(snap.controls_enabled);
      state.csrfToken = snap.controls_token || null;

      renderTopbar();
      renderTeamSelectorAndView();
      renderConversationsList();
      renderProjectsAndDeliveries();
      renderActivitySkillsMemoryResources();
    } catch (err) {
      setChatBanner(`Erreur actualisation : ${err.message}`, "status-err", false);
    }
  }

  function wireEvents() {
    document.querySelectorAll(".nav-btn").forEach((btn) => {
      btn.addEventListener("click", () => switchView(btn.dataset.view));
    });
    $("btnNewConv").addEventListener("click", () => {
      startConversationWithAgent($("chatRoleSelect").value || "coordination", $("chatTeamToggle").checked);
    });
    $("btnRenameConv").addEventListener("click", async () => {
      if (!state.activeConvId || !state.activeConv) return;
      const next = window.prompt("Nouveau titre de la conversation :", state.activeConv.title || "");
      if (!next || !next.trim()) return;
      try {
        state.activeConv = await apiMutate("PATCH", `/api/cc/conversations/${encodeURIComponent(state.activeConvId)}`, {
          title: next.trim(),
        });
        await refreshAll();
        renderActiveConversation();
      } catch (err) {
        setChatBanner(`Erreur renommage : ${err.message}`, "status-err", false);
      }
    });
    $("btnDeleteConv").addEventListener("click", async () => {
      if (!state.activeConvId) return;
      if (!window.confirm("Supprimer définitivement cette conversation ?")) return;
      try {
        await apiMutate("DELETE", `/api/cc/conversations/${encodeURIComponent(state.activeConvId)}`);
        state.activeConvId = null;
        state.activeConv = null;
        await refreshAll();
        renderActiveConversation();
      } catch (err) {
        setChatBanner(`Erreur suppression : ${err.message}`, "status-err", false);
      }
    });
    $("chatConfidentialToggle").addEventListener("change", () => {
      const conf = $("chatConfidentialToggle").checked;
      $("chatHybridToggle").disabled = conf;
      if (conf) $("chatHybridToggle").checked = false;
    });
    $("projConfidentialToggle").addEventListener("change", () => {
      const conf = $("projConfidentialToggle").checked;
      $("projHybridToggle").disabled = conf;
      if (conf) $("projHybridToggle").checked = false;
    });
    $("chatRoleSelect").addEventListener("change", () => {
      if ($("chatRoleSelect").value === "coordination") {
        $("chatTeamToggle").checked = true;
      }
    });
    $("btnSendChat").addEventListener("click", sendChatMessage);
    $("chatInput").addEventListener("keydown", (ev) => {
      if (ev.key === "Enter" && !ev.shiftKey) {
        ev.preventDefault();
        sendChatMessage();
      }
    });
    $("btnCancelJob").addEventListener("click", async () => {
      if (!state.activeJobId) return;
      try {
        await apiMutate("POST", `/api/cc/jobs/${encodeURIComponent(state.activeJobId)}/cancel`, {});
        setChatBanner("Annulation envoyée…", "muted", false, null);
      } catch (err) {
        setChatBanner(`Erreur annulation : ${err.message}`, "status-err", false, null);
      }
    });
    $("btnRetryJob").addEventListener("click", async () => {
      if (!state.retryableJobId) return;
      try {
        const jid = state.retryableJobId;
        $("btnSendChat").disabled = true;
        setChatBanner("Reprise de la requête sans doublon…", "status-warn", true, null);
        const job = await apiMutate("POST", `/api/cc/jobs/${encodeURIComponent(jid)}/retry`, {});
        state.activeJobId = job.job_id;
        pollActiveJob();
      } catch (err) {
        $("btnSendChat").disabled = false;
        setChatBanner(`Erreur reprise : ${err.message}`, "status-err", false, state.retryableJobId);
      }
    });
    $("btnPreviewProject").addEventListener("click", previewProject);
    $("btnLaunchProject").addEventListener("click", launchProject);
    $("btnCloseFileViewer").addEventListener("click", () => $("fileViewerCard").classList.add("hidden"));
    $("memFilterInput").addEventListener("input", renderActivitySkillsMemoryResources);
    if ($("btnToggleLearningPause")) {
      $("btnToggleLearningPause").addEventListener("click", () => {
        const paused = Boolean(state.cc && state.cc.continuous_learning && state.cc.continuous_learning.paused);
        sendLearningControl({ action: paused ? "resume" : "pause" }, paused ? "Apprentissage repris." : "Apprentissage mis en pause.");
      });
    }
    if ($("btnToggleProactive")) {
      $("btnToggleProactive").addEventListener("click", () => {
        const enabled = !(state.cc && state.cc.proactive_g8 && state.cc.proactive_g8.enabled === false);
        sendLearningControl(
          { action: enabled ? "proactive_disable" : "proactive_enable" },
          enabled ? "Proactivité G8 désactivée." : "Proactivité G8 activée."
        );
      });
    }
    [["btnBriefAccept", "accept"], ["btnBriefUseful", "useful"], ["btnBriefReject", "reject"]].forEach(([id, fb]) => {
      const btn = $(id);
      if (btn) {
        btn.addEventListener("click", () => {
          const latest = state.cc && state.cc.proactive_g8 && state.cc.proactive_g8.latest_brief;
          if (!latest || !latest.brief_id) return;
          sendLearningControl({ action: "feedback", brief_id: latest.brief_id, feedback: fb }, `Feedback '${fb}' enregistré et mémorisé.`);
        });
      }
    });
  }

  document.addEventListener("DOMContentLoaded", async () => {
    wireEvents();
    await refreshAll();
    const convs = (state.cc && state.cc.conversations) || [];
    if (convs.length) {
      await selectConversation(convs[0].id);
    } else {
      renderActiveConversation();
    }
    setInterval(refreshAll, 6000);
  });
})();
