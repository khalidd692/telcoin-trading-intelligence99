/* TEL99 Agent Mission Control - renderer (read-only).
 * Loads cockpit/data.json (curated, no secrets) and renders it.
 * It NEVER calls a model, starts a conversation, or writes anything.
 * All text is inserted with textContent, never innerHTML, so data from
 * GitHub can never inject markup. */
'use strict';

const $ = (id) => document.getElementById(id);

function el(tag, cls, text) {
  const n = document.createElement(tag);
  if (cls) n.className = cls;
  if (text != null) n.textContent = text;
  return n;
}

function link(href, text, cls) {
  const a = document.createElement('a');
  a.href = href; a.textContent = text;
  a.target = '_blank'; a.rel = 'noopener';
  if (cls) a.className = cls;
  return a;
}

function fmtTime(iso) {
  if (!iso) return 'horodatage inconnu';
  try {
    const d = new Date(iso);
    return d.toISOString().replace('T', ' ').replace('.000Z', 'Z');
  } catch (e) { return iso; }
}

function shortTime(iso) {
  if (!iso) return '--';
  try { return new Date(iso).toISOString().slice(11, 19) + 'Z'; }
  catch (e) { return iso; }
}

/* ---------- 1. Mission ---------- */
function renderMission(d) {
  const box = $('missionBody');
  box.classList.remove('skeleton');
  box.textContent = '';
  const m = d.mission || {};
  const phase = el('span', 'phase');
  phase.dataset.p = m.phase || 'inconnue';
  phase.appendChild(el('span', 'pdot'));
  phase.appendChild(el('span', null, m.phase_label || 'Inconnue'));
  box.appendChild(phase);

  box.appendChild(el('div', 'm-title', m.title || 'Mission sans titre'));
  if (m.objective) box.appendChild(el('p', 'm-obj', m.objective));

  const meta = el('div', 'meta');
  const addMeta = (k, v) => {
    const s = el('span');
    s.appendChild(el('b', null, k + ' : '));
    s.appendChild(document.createTextNode(v == null ? 'INCONNU' : v));
    meta.appendChild(s);
  };
  addMeta('Projet', 'telcoin-trading-intelligence99');
  addMeta('Horodatage', fmtTime(m.timestamp));
  addMeta('Issue', '#' + (m.number || '?'));
  if (m.source) addMeta('Source', m.source);
  if (m.commit_sha) addMeta('Commit vérifié', m.commit_sha.slice(0, 12));
  box.appendChild(meta);

  const links = el('div', 'links');
  if (m.issue_url) links.appendChild(link(m.issue_url, 'Issue GitHub #' + (m.number || '')));
  if (m.openhands_url) links.appendChild(link(m.openhands_url, 'Conversation OpenHands'));
  if (m.proof_url) links.appendChild(link(m.proof_url, 'Preuve GitHub Actions'));
  box.appendChild(links);
}

/* ---------- 2. Agents ---------- */
const STATE_LABEL = { running: 'EN COURS', done: 'DERNIERE ACTIVITE', blocked: 'BLOQUE', unknown: 'INCONNU' };
const ROLE_SUB = {
  analyst: 'Audit donnees / signaux',
  developer: 'Revue de code',
  verifier: 'Controle independant'
};

function renderAgents(d) {
  const box = $('agentsBody');
  box.textContent = '';
  (d.agents || []).forEach((a) => {
    const card = el('div', 'agent');
    card.dataset.s = a.state || 'unknown';
    card.appendChild(el('div', 'spark'));

    const head = el('div', 'a-head');
    const orb = el('div', 'orb', (a.label || '?').slice(0, 1));
    head.appendChild(orb);
    const names = el('div');
    names.appendChild(el('div', 'a-name', a.label));
    names.appendChild(el('div', 'a-role', ROLE_SUB[a.role] || ''));
    head.appendChild(names);
    head.appendChild(el('span', 'a-state', STATE_LABEL[a.state] || 'INCONNU'));
    card.appendChild(head);

    const body = el('div', 'a-body');
    if (a.state === 'running' && a.current_task) {
      const p = el('div');
      p.appendChild(el('span', 'k', 'Tache actuelle (prouvee) : '));
      p.appendChild(el('span', 'v', a.current_task));
      body.appendChild(p);
    } else {
      const p = el('div');
      p.appendChild(el('span', 'k', 'Derniere activite connue : '));
      p.appendChild(el('span', 'v', a.last_activity || 'aucune preuve publiee'));
      body.appendChild(p);
      const t = el('div');
      t.appendChild(el('span', 'k', 'Horodatage : '));
      t.appendChild(el('span', 'v', a.last_activity_at ? fmtTime(a.last_activity_at) : 'INCONNU'));
      body.appendChild(t);
    }
    if (a.duration_s != null) {
      const dur = el('div');
      dur.appendChild(el('span', 'k', 'Duree : '));
      dur.appendChild(el('span', 'v', a.duration_s + ' s'));
      body.appendChild(dur);
    }
    card.appendChild(body);

    if ((a.evidence || []).length) {
      const ev = el('div', 'a-ev');
      a.evidence.slice().reverse().forEach((e) => {
        if (!e.source) return;
        const row = link(e.source, null);
        row.appendChild(el('span', 't', shortTime(e.at)));
        row.appendChild(el('span', null, e.summary || 'preuve'));
        ev.appendChild(row);
      });
      if (ev.childNodes.length) card.appendChild(ev);
    }
    box.appendChild(card);
  });
  const src = $('agentsSrc');
  src.textContent = 'Etats derives uniquement des evenements sources ci-dessous. '
    + 'Aucun flux simule : un agent n\'est "en cours" que si un demarrage reel n\'a pas de fin.';
}

/* ---------- 4. Quota ---------- */
function renderQuota(d) {
  const box = $('quotaBody');
  box.classList.remove('skeleton');
  box.textContent = '';
  const q = d.quota || {};
  const grid = el('div', 'q-grid');
  const cell = (lbl, val) => {
    const c = el('div', 'q-cell');
    c.appendChild(el('div', 'lbl', lbl));
    c.appendChild(el('div', 'val', val == null ? 'INCONNU' : String(val)));
    return c;
  };
  grid.appendChild(cell('Restantes', q.remaining == null ? null : q.remaining));
  grid.appendChild(cell('Plafond / jour', q.daily_limit == null ? null : q.daily_limit));
  grid.appendChild(cell('Utilisees', q.used_today == null ? null : q.used_today));
  box.appendChild(grid);

  if (q.daily_limit && q.remaining != null) {
    const bar = el('div', 'bar');
    const fill = el('i');
    fill.style.width = Math.max(0, Math.min(100, (q.remaining / q.daily_limit) * 100)) + '%';
    bar.appendChild(fill);
    box.appendChild(bar);
  }

  const v = el('div', 'q-verdict', q.message || 'INCONNU');
  v.dataset.v = q.verdict || 'unknown';
  box.appendChild(v);

  const meta = el('div', 'kv');
  const add = (k, val) => {
    const s = el('span');
    s.appendChild(el('b', null, k + ' : '));
    s.appendChild(document.createTextNode(val == null ? 'INCONNU' : val));
    meta.appendChild(s);
  };
  add('Mesure le', q.measured_at ? fmtTime(q.measured_at) : null);
  add('Reset', q.reset_at ? fmtTime(q.reset_at) : null);
  add('Credits', q.credits == null ? 'INCONNU' : q.credits);
  box.appendChild(meta);

  const src = el('div', 'src');
  src.appendChild(document.createTextNode('Source : ' + (q.source || 'INCONNU')));
  box.appendChild(src);
}

/* ---------- 3. Timeline ---------- */
function renderTimeline(d) {
  const events = d.timeline || [];
  const box = $('tlBody');
  const filters = $('filters');
  filters.textContent = '';
  box.textContent = '';

  const agents = ['all', 'coordinator', 'analyst', 'developer', 'verifier'];
  const labels = { all: 'Tout', coordinator: 'Coord.', analyst: 'Analyste', developer: 'Dev', verifier: 'Verif.' };
  let active = 'all';
  const chips = {};
  agents.forEach((a) => {
    const c = el('span', 'chip', labels[a]);
    c.setAttribute('role', 'button');
    c.setAttribute('aria-pressed', a === 'all' ? 'true' : 'false');
    c.addEventListener('click', () => { active = a; paint(); });
    chips[a] = c; filters.appendChild(c);
  });

  function paint() {
    Object.keys(chips).forEach((k) =>
      chips[k].setAttribute('aria-pressed', k === active ? 'true' : 'false'));
    box.textContent = '';
    const shown = events.filter((e) => active === 'all' || e.agent === active);
    if (!shown.length) {
      box.appendChild(el('div', 'empty', 'Aucun evenement pour ce filtre.'));
      return;
    }
    shown.forEach((e) => {
      const row = el('div', 'ev');
      row.dataset.a = e.agent || 'coordinator';
      const head = el('div', 'eh');
      head.appendChild(el('span', 'tag', e.kind || 'event'));
      head.appendChild(el('span', 'ts', fmtTime(e.at)));
      row.appendChild(head);
      row.appendChild(el('div', 'tt', e.summary || ''));
      if (e.source) {
        const l = el('div');
        l.appendChild(link(e.source, 'source : ' + (e.issue ? '#' + e.issue : 'lien')));
        row.appendChild(l);
      }
      box.appendChild(row);
    });
  }
  paint();

  const src = $('tlSrc');
  src.textContent = 'Source : ' + ((d.provenance && d.provenance.events) || 'INCONNU')
    + ' (' + events.length + ' evenements)';
}

/* ---------- Graph ---------- */
function renderGraph(d) {
  const box = $('graphBody');
  box.textContent = '';
  const g = d.delegation_graph || { nodes: [], edges: [] };
  const coord = (g.nodes || []).find((n) => n.kind === 'coordinator');
  if (coord) box.appendChild(node(coord));
  (g.edges || []).forEach((e) => {
    box.appendChild(el('div', 'gedge', '\u2193 delegation'));
    const n = (g.nodes || []).find((x) => x.id === e.to);
    if (n) box.appendChild(node(n));
  });
  if (!(g.edges || []).length) {
    box.appendChild(el('div', 'empty', 'Aucune delegation prouvee par les evenements.'));
  }
}
function node(n) {
  const eln = el('div', 'gnode', n.label);
  if (n.state) eln.dataset.s = n.state;
  return eln;
}

/* ---------- 5. Memory ---------- */
function renderMemory(d) {
  const box = $('memBody');
  box.classList.remove('skeleton');
  box.textContent = '';
  const mem = d.memory || {};
  const latest = mem.latest;
  if (!latest) {
    box.appendChild(el('div', 'empty', 'Aucune entree memoire lisible (INCONNU).'));
  } else {
    const top = el('div', 'mem-top');
    const b = el('span', 'badge ' + (latest.verified ? 'ok' : 'no'),
      latest.verified ? 'VERIFIEE' : 'NON VERIFIEE');
    top.appendChild(b);
    top.appendChild(el('span', 'kv', 'v' + (latest.version == null ? '?' : latest.version)));
    box.appendChild(top);
    box.appendChild(el('div', 'mem-title', latest.title || latest.id));
    const kv = el('div', 'kv');
    const add = (k, val) => {
      const s = el('span');
      s.appendChild(el('b', null, k + ' : '));
      s.appendChild(document.createTextNode(val == null ? 'INCONNU' : val));
      kv.appendChild(s);
    };
    add('Projet', latest.project);
    add('Type', latest.kind);
    add('Verifie par', latest.verified_by || 'INCONNU');
    add('Commit', latest.commit || 'INCONNU');
    add('Date', latest.created_at ? fmtTime(latest.created_at) : null);
    box.appendChild(kv);
  }
  const src = el('div', 'src');
  src.appendChild(document.createTextNode('Source : ' + (mem.source || 'INCONNU')
    + ' (' + ((mem.entries || []).length) + ' entrees)'));
  box.appendChild(src);
}

/* ---------- 6. Controls ---------- */
function renderControls(d) {
  const box = $('ctlBody');
  box.classList.remove('skeleton');
  box.textContent = '';
  const c = d.controls || {};
  const row = (lbl, state) => {
    const r = el('div', 'ctrl-row');
    r.appendChild(el('span', 'lbl', lbl));
    r.appendChild(el('span', 'st', state == null ? 'INCONNU' : state));
    return r;
  };
  box.appendChild(row('Verrou de mission', (c.lock || {}).state));
  box.appendChild(row('Arret d\'urgence', (c.emergency_stop || {}).state));
  box.appendChild(row('Automation', (c.automation || {}).state));
  box.appendChild(row('Duree maximale',
    c.max_duration_s == null ? null : (c.max_duration_s + ' s')));

  (c.actions || []).forEach((a) => {
    const btn = el('button', 'btn');
    btn.type = 'button';
    btn.disabled = !a.enabled;
    btn.appendChild(el('span', null, a.label));
    btn.appendChild(el('span', 'lock', a.enabled ? 'actif' : '\uD83D\uDD12 lecture seule'));
    btn.title = a.reason || '';
    if (a.enabled && a.url) {
      btn.addEventListener('click', () => window.open(a.url, '_blank', 'noopener'));
    }
    const wrap = el('div');
    wrap.style.marginTop = '10px';
    wrap.appendChild(btn);
    box.appendChild(wrap);
  });

  if (c.read_only) {
    box.appendChild(el('div', 'ro-note',
      'Lecture seule : aucun bouton Lancer/Stop n\'est raccorde a une API autorisee. '
      + 'Les commandes ci-dessus sont montrees, jamais simulees.'));
  }
}

/* ---------- stars (discrete, reduced-motion aware) ---------- */
function drawStars() {
  const cv = $('stars');
  if (!cv) return;
  const reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  const dpr = Math.min(window.devicePixelRatio || 1, 2);
  const w = window.innerWidth, h = window.innerHeight;
  cv.width = w * dpr; cv.height = h * dpr;
  const ctx = cv.getContext('2d');
  ctx.scale(dpr, dpr);
  const n = Math.min(70, Math.round(w / 10));
  const pts = Array.from({ length: n }, () => ({
    x: Math.random() * w, y: Math.random() * h,
    r: Math.random() * 1.4 + 0.3, a: Math.random() * 0.5 + 0.2,
    v: Math.random() * 0.12 + 0.02
  }));
  function frame() {
    ctx.clearRect(0, 0, w, h);
    pts.forEach((p) => {
      ctx.beginPath();
      ctx.arc(p.x, p.y, p.r, 0, Math.PI * 2);
      ctx.fillStyle = 'rgba(180,205,255,' + p.a + ')';
      ctx.fill();
      if (!reduce) { p.y += p.v; if (p.y > h) p.y = 0; }
    });
    if (!reduce) requestAnimationFrame(frame);
  }
  frame();
}

/* ---------- boot ---------- */
async function boot() {
  try {
    const res = await fetch('data.json', { cache: 'no-store' });
    if (!res.ok) throw new Error('HTTP ' + res.status);
    const d = await res.json();
    renderMission(d);
    renderAgents(d);
    renderQuota(d);
    renderTimeline(d);
    renderGraph(d);
    renderMemory(d);
    renderControls(d);
    $('genLine').textContent = 'Genere le ' + fmtTime(d.generated_at)
      + ' - donnees sourcees, lecture seule';
    if (d.live) {
      const pill = $('roPill');
      pill.textContent = 'MISSION EN COURS';
      pill.classList.remove('ro');
    }
  } catch (e) {
    const box = $('errorBox');
    box.hidden = false;
    box.textContent = 'Erreur de chargement des donnees : ' + e.message
      + '. Aucune donnee inventee ne sera affichee.';
  }
  drawStars();
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', boot);
} else { boot(); }
