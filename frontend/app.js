// Vanilla-JS dashboard for the Secure 3D-Printer Fleet (tier A0).
const state = { token: null, user: null, role: null, tab: "jobs" };

async function api(path, method = "GET", body = null) {
  const headers = { "Content-Type": "application/json" };
  if (state.token) headers.Authorization = "Bearer " + state.token;
  const res = await fetch("/api" + path, {
    method,
    headers,
    body: body ? JSON.stringify(body) : null,
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.detail || res.statusText);
  return data;
}

const $ = (sel) => document.querySelector(sel);
function h(html) {
  const t = document.createElement("template");
  t.innerHTML = html.trim();
  return t.content.firstChild;
}
function esc(s) {
  return String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
}

async function health() {
  try {
    const b = await (await fetch("/health")).json();
    const pill = $("#status-pill");
    pill.textContent = b.status === "ok" ? "online" : "degraded";
    pill.classList.toggle("ok", b.status === "ok");
  } catch (_) {}
}

// ---- login ----
function renderLogin() {
  $("#nav").classList.add("hidden");
  $("#logout").classList.add("hidden");
  $("#whoami").textContent = "";
  const quick = ["admin", "op-1", "client-acme", "auditor-1"];
  $("#view").innerHTML = "";
  const card = h(`<section class="card">
    <h1>Sign in</h1>
    <p class="muted">Enter a user id, or use a demo identity. Sign in as admin first and seed the demo.</p>
    <div class="row"><input id="uid" placeholder="user id" value="admin" /><button id="login" class="btn">Sign in</button></div>
    <div class="chips">${quick.map((u) => `<button class="chip" data-u="${u}">${u}</button>`).join("")}</div>
    <div id="loginmsg" class="muted"></div>
  </section>`);
  $("#view").appendChild(card);
  card.querySelectorAll(".chip").forEach((b) => (b.onclick = () => { $("#uid").value = b.dataset.u; }));
  $("#login").onclick = doLogin;
}

async function doLogin() {
  try {
    const uid = $("#uid").value.trim();
    const r = await api("/auth/login", "POST", { user_id: uid });
    state.token = r.token; state.user = r.user_id; state.role = r.role;
    renderApp();
  } catch (e) {
    $("#loginmsg").textContent = "Login failed: " + e.message;
  }
}

// ---- shell ----
function renderApp() {
  $("#whoami").textContent = `${state.user} (${state.role})`;
  $("#logout").classList.remove("hidden");
  $("#logout").onclick = () => { state.token = null; renderLogin(); };
  const tabs = ["jobs", "fleet", "materials", "audit"];
  if (state.role === "Admin") tabs.push("admin");
  const nav = $("#nav");
  nav.classList.remove("hidden");
  nav.innerHTML = tabs.map((t) => `<button class="tab ${t === state.tab ? "active" : ""}" data-t="${t}">${t}</button>`).join("");
  nav.querySelectorAll(".tab").forEach((b) => (b.onclick = () => { state.tab = b.dataset.t; renderApp(); }));
  ({ jobs: renderJobs, fleet: renderFleet, materials: renderMaterials, audit: renderAudit, admin: renderAdmin }[state.tab])();
}

// ---- jobs ----
async function renderJobs() {
  const view = $("#view");
  view.innerHTML = `<section class="card"><h1>Jobs</h1><div id="joblist" class="muted">loading...</div></section>`;
  if (state.role === "Client") {
    view.insertBefore(h(`<section class="card">
      <h2>Submit a job</h2>
      <div class="grid">
        <label>Design name<input id="dn" value="bracket.3mf" /></label>
        <label>Material lot<input id="ml" value="mat-pla-001" /></label>
        <label>Scenario<select id="sc"><option>legitimate</option><option>lazy-fake</option><option>sabotaged</option></select></label>
        <label>Duration<input id="du" type="number" value="120" /></label>
      </div>
      <button id="submit" class="btn">Submit</button><span id="submsg" class="muted"></span>
    </section>`), view.firstChild);
    $("#submit").onclick = async () => {
      try {
        await api("/jobs", "POST", {
          design_name: $("#dn").value, material_lot_id: $("#ml").value,
          scenario: $("#sc").value, duration: parseInt($("#du").value, 10),
        });
        $("#submsg").textContent = "submitted";
        loadJobs();
      } catch (e) { $("#submsg").textContent = e.message; }
    };
  }
  loadJobs();
}

async function loadJobs() {
  try {
    const jobs = await api("/jobs");
    const rows = jobs.map((j) => {
      const canRun = state.role === "Operator" && ["Submitted"].includes(j.status);
      const pe = j.verification ? j.verification.p_evade : null;
      return `<tr>
        <td class="mono">${esc(j.id.slice(0, 12))}</td>
        <td>${esc(j.design_name)}</td>
        <td><span class="badge ${statusClass(j.status)}">${esc(j.status)}</span></td>
        <td>${esc(j.scenario)}</td>
        <td>${pe === null ? "" : "P(evade)=" + pe.toExponential(1)}</td>
        <td>${canRun ? `<button class="btn small" data-run="${j.id}">Run</button>` : ""}
            <button class="btn small ghost" data-view="${j.id}">Details</button></td>
      </tr>`;
    }).join("");
    $("#joblist").innerHTML = `<table><thead><tr><th>id</th><th>design</th><th>status</th><th>scenario</th><th>verify</th><th></th></tr></thead><tbody>${rows}</tbody></table><div id="detail"></div>`;
    $("#joblist").querySelectorAll("[data-run]").forEach((b) => (b.onclick = async () => {
      b.disabled = true; b.textContent = "running...";
      try { await api(`/jobs/${b.dataset.run}/run`, "POST"); } catch (e) { alert(e.message); }
      loadJobs();
    }));
    $("#joblist").querySelectorAll("[data-view]").forEach((b) => (b.onclick = () => showDetail(b.dataset.view)));
  } catch (e) {
    $("#joblist").innerHTML = `<span class="muted">${esc(e.message)}</span>`;
  }
}

async function showDetail(id) {
  const j = await api("/jobs/" + id);
  const v = j.verification;
  const d = $("#detail");
  d.innerHTML = `<div class="card sub">
    <h3>${esc(j.id)}</h3>
    <p>Status <span class="badge ${statusClass(j.status)}">${esc(j.status)}</span> | printer ${esc(j.printer_id || "-")} | file ${esc((j.file_hash || "").slice(0, 16))}</p>
    ${v ? `<p class="mono">verdict=${esc(v.verdict)} sampled=${v.n} P(evade)=${v.p_evade.toExponential(2)} screening_failures=${v.screening_failures}</p>
    <p class="muted">${esc(v.note)}</p>` : "<p class='muted'>no verification record</p>"}
  </div>`;
}

function statusClass(s) {
  if (s.startsWith("Verified")) return "ok";
  if (s === "Failed") return "bad";
  if (["Cancelled", "Expired"].includes(s)) return "warn";
  return "info";
}

// ---- fleet / materials ----
async function renderFleet() {
  $("#view").innerHTML = `<section class="card"><h1>Fleet monitor</h1><div id="f">loading...</div></section>`;
  const printers = await api("/printers");
  $("#f").innerHTML = `<table><thead><tr><th>id</th><th>model</th><th>status</th><th>materials</th><th>job</th></tr></thead><tbody>${printers.map((p) => `<tr><td class="mono">${esc(p.id)}</td><td>${esc(p.model)}</td><td><span class="badge ${p.status === "idle" ? "ok" : "info"}">${esc(p.status)}</span></td><td>${esc((p.materials || []).join(", "))}</td><td class="mono">${esc(p.current_job || "-")}</td></tr>`).join("")}</tbody></table>`;
}

async function renderMaterials() {
  $("#view").innerHTML = `<section class="card"><h1>Materials</h1><div id="m">loading...</div></section>`;
  const mats = await api("/materials");
  $("#m").innerHTML = `<table><thead><tr><th>id</th><th>type</th><th>available</th></tr></thead><tbody>${mats.map((m) => `<tr><td class="mono">${esc(m.id)}</td><td>${esc(m.type)}</td><td>${m.available}</td></tr>`).join("")}</tbody></table>`;
}

// ---- audit ----
async function renderAudit() {
  $("#view").innerHTML = `<section class="card"><h1>Audit trail</h1>
    <button id="verify" class="btn">Verify chain integrity</button><span id="vres" class="muted"></span>
    <div id="events" class="muted">loading...</div></section>`;
  $("#verify").onclick = async () => {
    const r = await api("/audit/verify");
    $("#vres").innerHTML = r.ok ? `<span class="badge ok">intact (${r.count} events)</span>` : `<span class="badge bad">tampered: ${esc(r.reason)}</span>`;
  };
  const evs = await api("/audit/events");
  $("#events").innerHTML = `<table><thead><tr><th>seq</th><th>actor</th><th>action</th><th>target</th><th>ts</th></tr></thead><tbody>${evs.map((e) => `<tr><td>${e.seq}</td><td>${esc(e.actor)}</td><td>${esc(e.action)}</td><td class="mono">${esc((e.target || "").slice(0, 14))}</td><td class="muted">${esc((e.ts || "").slice(0, 19))}</td></tr>`).join("")}</tbody></table>`;
}

// ---- admin ----
async function renderAdmin() {
  $("#view").innerHTML = `<section class="card"><h1>Admin</h1>
    <p class="muted">Seed demo operators, clients, printers, and materials for the walkthrough.</p>
    <button id="seed" class="btn">Seed demo data</button><span id="seedmsg" class="muted"></span></section>`;
  $("#seed").onclick = async () => {
    try { await api("/demo/seed", "POST"); $("#seedmsg").textContent = "seeded"; }
    catch (e) { $("#seedmsg").textContent = e.message; }
  };
}

health();
renderLogin();
