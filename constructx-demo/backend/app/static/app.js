// ConstructX AI demo dashboard — vanilla JS, no dependencies.

async function api(path) {
  const res = await fetch(path);
  if (!res.ok) throw new Error(`${path} -> ${res.status}`);
  return res.json();
}

function el(tag, cls, html) {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (html !== undefined) e.innerHTML = html;
  return e;
}

function badge(level) {
  return `<span class="badge ${level}">${level}</span>`;
}

function recClass(rec) {
  if (rec === "Preferred Vendor" || rec === "No Action") return "good";
  if (rec === "Do Not Assign New Projects" || rec === "Urgent Purchase") return "bad";
  return "warn";
}

// ---------- Live data entry (add / upload / reload) ----------
const FIELD_SPECS = {
  subcontractors: {
    label: "Vendor",
    reload: () => loadSubcontractors(),
    fields: [
      { n: "vendor_id", l: "Vendor ID", t: "text", req: true },
      { n: "vendor_name", l: "Vendor Name", t: "text", req: true },
      { n: "trade", l: "Trade", t: "text" },
      { n: "project", l: "Project", t: "text" },
      { n: "contract_value", l: "Contract Value", t: "number" },
      { n: "planned_progress", l: "Planned Progress %", t: "number" },
      { n: "actual_progress", l: "Actual Progress %", t: "number" },
      { k: "heading", l: "📋 Raw QA & Safety records — the scores below auto-calculate" },
      { n: "inspections_total", l: "Inspections — Total", t: "number", k: "raw" },
      { n: "inspections_passed", l: "Inspections — Passed", t: "number", k: "raw" },
      { n: "ncrs_raised", l: "NCRs Raised", t: "number", k: "raw" },
      { n: "ncrs_closed", l: "NCRs Closed", t: "number", k: "raw" },
      { n: "recordable_incidents", l: "Recordable Incidents", t: "number", k: "raw" },
      { n: "man_hours", l: "Man-Hours Worked", t: "number", k: "raw" },
      { n: "quality_score", l: "Quality Score ⚙ auto", t: "number", k: "computed" },
      { n: "inspection_pass", l: "Inspection Pass % ⚙ auto", t: "number", k: "computed" },
      { n: "safety_score", l: "Safety Score ⚙ auto", t: "number", k: "computed" },
      { k: "heading", l: "Progress issues & commercial" },
      { n: "delay_days", l: "Delay Days", t: "number" },
      { n: "open_issues", l: "Open Issues", t: "number" },
      { n: "invoice_amount", l: "Invoice Amount", t: "number" },
      { n: "paid_amount", l: "Paid Amount", t: "number" },
      { n: "engineer_rating", l: "Engineer Rating (0-5)", t: "number" },
      { n: "client_rating", l: "Client Rating (0-5)", t: "number" },
      { n: "active_projects", l: "Active Projects", t: "number" },
      { n: "capacity_projects", l: "Capacity Projects", t: "number" },
    ],
    compute: (v) => {
      const num = (k) => parseFloat(v[k]) || 0;
      const clip = (x) => Math.max(0, Math.min(100, x));
      const r1 = (x) => Math.round(x * 10) / 10;
      const out = {};
      const total = num("inspections_total");
      if (total > 0) {
        const insp = (num("inspections_passed") / total) * 100;
        const raised = num("ncrs_raised");
        const ncr = raised <= 0 ? 100 : (num("ncrs_closed") / raised) * 100;
        out.inspection_pass = r1(insp);
        out.quality_score = r1(clip(0.7 * insp + 0.3 * ncr));
      }
      const hours = num("man_hours");
      if (hours > 0) {
        const trir = (num("recordable_incidents") * 200000) / hours;
        out.safety_score = r1(clip(100 - trir * 10));
      }
      return out;
    },
  },
  materials: {
    label: "Material",
    reload: () => loadMaterials(),
    fields: [
      { n: "material_id", l: "Material ID", t: "text", req: true },
      { n: "material_name", l: "Material Name", t: "text", req: true },
      { n: "category", l: "Category", t: "text" },
      { n: "current_stock", l: "Current Stock", t: "number" },
      { n: "minimum_stock", l: "Minimum Stock", t: "number" },
      { n: "required_qty", l: "Required Qty", t: "number" },
      { n: "supplier", l: "Supplier", t: "text" },
      { n: "unit_price", l: "Unit Price", t: "number" },
      { k: "heading", l: "🚚 Raw delivery records — the scores below auto-calculate" },
      { n: "deliveries_total", l: "Deliveries — Total", t: "number", k: "raw" },
      { n: "deliveries_on_time", l: "Deliveries — On Time", t: "number", k: "raw" },
      { n: "lead_days", l: "Past Lead Times (days, comma-sep)", t: "text", k: "raw" },
      { n: "delivery_reliability", l: "Delivery Reliability % ⚙ auto", t: "number", k: "computed" },
      { n: "lead_time_days", l: "Lead Time (days) ⚙ auto", t: "number", k: "computed" },
      { k: "heading", l: "Schedule" },
      { n: "project", l: "Project", t: "text" },
      { n: "expected_delivery", l: "Expected Delivery", t: "date" },
    ],
    compute: (v) => {
      const num = (k) => parseFloat(v[k]) || 0;
      const r1 = (x) => Math.round(x * 10) / 10;
      const out = {};
      const dt = num("deliveries_total");
      if (dt > 0) out.delivery_reliability = r1((num("deliveries_on_time") / dt) * 100);
      const parts = String(v.lead_days || "").replace(/;/g, ",").split(",")
        .map((s) => parseFloat(s.trim())).filter((x) => x > 0);
      if (parts.length) {
        out.lead_time_days = r1(parts.reduce((a, b) => a + b, 0) / parts.length);
      }
      return out;
    },
  },
};

let activeModule = null;
const RAW = { subcontractors: {}, materials: {} };  // id -> raw record, for editing

function openForm(module, values, editing) {
  activeModule = module;
  const spec = FIELD_SPECS[module];
  const pk = spec.fields[0].n;
  document.getElementById("modal-title").textContent =
    `${editing ? "Edit" : "Add"} ${spec.label}`;
  const form = document.getElementById("modal-form");
  form.innerHTML = spec.fields.map((f) => {
    if (f.k === "heading") return `<div class="form-heading">${f.l}</div>`;
    const raw = values && values[f.n] != null ? String(values[f.n]) : "";
    const val = raw.replace(/"/g, "&quot;");
    const cls = f.k === "raw" ? "raw-field"
      : f.k === "computed" ? "computed-field" : "";
    const ro = editing && f.n === pk ? "readonly" : "";
    return `<label class="${f.req ? "req " : ""}${cls}">${f.l}
       <input name="${f.n}" type="${f.t}" ${f.req ? "required" : ""}
              ${f.t === "number" ? 'step="any"' : ""} value="${val}" ${ro}>
     </label>`;
  }).join("");
  form.oninput = () => recompute(module);
  document.getElementById("modal-overlay").classList.add("open");
}

// Auto-calculate the derived scores from the raw records as the user types.
function recompute(module) {
  const form = document.getElementById("modal-form");
  const v = {};
  new FormData(form).forEach((val, k) => { v[k] = val; });
  const out = FIELD_SPECS[module].compute(v);
  Object.entries(out).forEach(([k, val]) => {
    if (form.elements[k]) form.elements[k].value = val;
  });
}

function openAddForm(module) { openForm(module, null, false); }

function openEditForm(module, id) { openForm(module, RAW[module][id], true); }

async function deleteRecord(module, id) {
  if (!confirm(`Delete ${id}? This cannot be undone.`)) return;
  try {
    const res = await fetch(`/api/${module}/${encodeURIComponent(id)}`,
      { method: "DELETE" });
    if (!res.ok) throw new Error((await res.json()).detail || res.status);
    await FIELD_SPECS[module].reload();
    flash(module, `Deleted ${id} ✓`, "ok");
  } catch (err) {
    alert("Delete failed: " + err.message);
  }
}

function closeModal(e) {
  if (e && e.target !== e.currentTarget) return;
  document.getElementById("modal-overlay").classList.remove("open");
}

// ---------- Live project tracking ----------
function closeTrack(e) {
  if (e && e.target !== e.currentTarget) return;
  document.getElementById("track-overlay").classList.remove("open");
}

function trendChart(history, planned) {
  const W = 540, H = 200, pad = 34;
  if (!history.length) return "<p>No progress history yet.</p>";
  const n = history.length;
  const x = (i) => pad + (W - 2 * pad) * (n === 1 ? 0.5 : i / (n - 1));
  const y = (v) => H - pad - (H - 2 * pad) * (Math.max(0, Math.min(100, v)) / 100);
  const path = history.map((p, i) =>
    `${i ? "L" : "M"}${x(i).toFixed(1)},${y(p.progress_pct).toFixed(1)}`).join(" ");
  const dots = history.map((p, i) =>
    `<circle cx="${x(i).toFixed(1)}" cy="${y(p.progress_pct).toFixed(1)}" r="3.5" fill="#1a2ce0"/>`).join("");
  const plannedLine = planned != null
    ? `<line x1="${pad}" y1="${y(planned).toFixed(1)}" x2="${W - pad}" y2="${y(planned).toFixed(1)}"
         stroke="#e0930a" stroke-width="1.5" stroke-dasharray="5"/>
       <text x="${W - pad}" y="${(y(planned) - 5).toFixed(1)}" font-size="10"
         fill="#e0930a" text-anchor="end">planned ${planned}%</text>` : "";
  const labels = history.map((p, i) =>
    `<text x="${x(i).toFixed(1)}" y="${H - pad + 14}" font-size="9" fill="#888"
       text-anchor="middle">${(p.week_date || "").slice(5)}</text>`).join("");
  return `<svg viewBox="0 0 ${W} ${H}" class="trendchart" width="100%">
    <line x1="${pad}" y1="${pad}" x2="${pad}" y2="${H - pad}" stroke="#ddd"/>
    <line x1="${pad}" y1="${H - pad}" x2="${W - pad}" y2="${H - pad}" stroke="#ddd"/>
    <text x="${pad - 6}" y="${pad + 4}" font-size="9" fill="#aaa" text-anchor="end">100</text>
    <text x="${pad - 6}" y="${H - pad}" font-size="9" fill="#aaa" text-anchor="end">0</text>
    ${plannedLine}
    <path d="${path}" fill="none" stroke="#1a2ce0" stroke-width="2.5"/>
    ${dots}${labels}
  </svg>`;
}

async function openTrack(vendorId) {
  const body = document.getElementById("track-body");
  body.innerHTML = "Loading…";
  document.getElementById("track-overlay").classList.add("open");
  try {
    const d = await api(`/api/subcontractors/${encodeURIComponent(vendorId)}/progress`);
    const f = d.forecast;
    const statusCls = { "On track": "good", "Complete": "good",
      "In progress": "warn", "Behind schedule": "bad", "Stalled": "bad" }[f.status] || "warn";
    const proj = f.projected_completion
      ? `Projected completion: <b>${f.projected_completion}</b>` : "";
    const behind = f.behind_by > 0
      ? ` · <span class="rec bad">${f.behind_by}% behind plan</span>` : "";
    const today = new Date().toISOString().slice(0, 10);
    const rows = d.history.slice().reverse().map((h) =>
      `<tr><td>${h.week_date}</td><td>${h.progress_pct}%</td>
        <td>${h.delay_days ?? "—"}</td><td>${h.open_issues ?? "—"}</td></tr>`).join("");
    body.innerHTML = `
      <h3 style="margin:0 0 .2rem">📈 ${d.vendor} — Live Progress Tracking</h3>
      <p class="subtitle" style="margin:.1rem 0 1rem">${d.trade || ""} · ${d.project || ""}</p>
      <div class="track-summary">
        <span class="rec ${statusCls}" style="font-size:1rem;font-weight:700">${f.status}</span>
        &nbsp;·&nbsp; Latest: <b>${f.latest_progress ?? "—"}%</b> ${behind}
        <div style="margin-top:.3rem;color:var(--muted);font-size:.85rem">
          Velocity: <b>${f.velocity_per_week ?? "—"}%/week</b> ·
          ${f.weeks_to_finish != null ? `~<b>${f.weeks_to_finish} weeks</b> to finish · ` : ""}${proj}
        </div>
      </div>
      ${trendChart(d.history, d.planned_progress)}
      <h4 style="margin:1rem 0 .4rem">Add this week's update</h4>
      <form id="track-form" onsubmit="submitProgress('${vendorId}');return false;" class="modal-form">
        <label class="req">Week date<input name="week_date" type="date" value="${today}" required></label>
        <label class="req">Progress %<input name="progress_pct" type="number" step="any" required></label>
        <label>Delay Days<input name="delay_days" type="number"></label>
        <label>Open Issues<input name="open_issues" type="number"></label>
        <label style="grid-column:1/-1">Note<input name="note" type="text" placeholder="optional"></label>
      </form>
      <button class="btn" style="margin-top:.7rem" onclick="submitProgress('${vendorId}')">＋ Save update</button>
      <h4 style="margin:1.2rem 0 .4rem">History</h4>
      <div class="table-wrap"><table><thead><tr>
        <th>Week</th><th>Progress</th><th>Delay days</th><th>Open issues</th>
      </tr></thead><tbody>${rows}</tbody></table></div>`;
  } catch (err) {
    body.innerHTML = `<p class="rec bad">Could not load: ${err.message}</p>`;
  }
}

async function submitProgress(vendorId) {
  const form = document.getElementById("track-form");
  if (!form.reportValidity()) return;
  const payload = {};
  new FormData(form).forEach((v, k) => { if (v !== "") payload[k] = v; });
  try {
    const res = await fetch(`/api/subcontractors/${encodeURIComponent(vendorId)}/progress`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (!res.ok) throw new Error((await res.json()).detail || res.status);
    await openTrack(vendorId);        // refresh the tracking view
    await loadSubcontractors();       // refresh the main dashboard (AI recomputes)
  } catch (err) {
    alert("Could not save update: " + err.message);
  }
}

async function submitAddForm() {
  const spec = FIELD_SPECS[activeModule];
  const form = document.getElementById("modal-form");
  if (!form.reportValidity()) return;
  const payload = {};
  new FormData(form).forEach((v, k) => { if (v !== "") payload[k] = v; });
  try {
    const res = await fetch(`/api/${activeModule}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (!res.ok) throw new Error((await res.json()).detail || res.status);
    closeModal();
    await spec.reload();
    flash(activeModule, `Saved ${payload[spec.fields[0].n]} ✓`, "ok");
  } catch (err) {
    alert("Could not save: " + err.message);
  }
}

async function uploadFile(module, input) {
  const file = input.files[0];
  if (!file) return;
  const fd = new FormData();
  fd.append("file", file);
  flash(module, "Uploading…");
  try {
    const res = await fetch(`/api/${module}/upload?mode=append`, {
      method: "POST", body: fd,
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || res.status);
    await FIELD_SPECS[module].reload();
    flash(module,
      `Imported ${data.inserted} new, updated ${data.updated} ✓`, "ok");
  } catch (err) {
    flash(module, "Upload failed: " + err.message, "err");
  } finally {
    input.value = "";
  }
}

function flash(module, text, cls = "") {
  const el = document.getElementById(module === "materials" ? "mat-msg" : "sub-msg");
  el.textContent = text;
  el.className = "toolbar-msg " + cls;
  if (cls === "ok") setTimeout(() => { el.textContent = ""; }, 5000);
}

// ---------- Tabs ----------
document.querySelectorAll(".tab").forEach((btn) => {
  btn.addEventListener("click", () => {
    document.querySelectorAll(".tab").forEach((b) => b.classList.remove("active"));
    document.querySelectorAll(".module").forEach((m) => m.classList.remove("active"));
    btn.classList.add("active");
    document.getElementById(btn.dataset.tab).classList.add("active");
  });
});

// ---------- Module 1: Subcontractors ----------
async function loadSubcontractors() {
  const [summary, rows, alerts, concentration, capacity, raw] =
    await Promise.all([
      api("/api/subcontractors/summary"),
      api("/api/subcontractors/evaluate"),
      api("/api/subcontractors/alerts"),
      api("/api/subcontractors/concentration"),
      api("/api/subcontractors/capacity"),
      api("/api/subcontractors/raw"),
    ]);
  RAW.subcontractors = {};
  raw.forEach((r) => { RAW.subcontractors[r.vendor_id] = r; });

  const cards = document.getElementById("sub-cards");
  cards.innerHTML = "";
  const cardData = [
    { v: summary.total_vendors, l: "Subcontractors", c: "" },
    { v: summary.avg_ai_score, l: "Avg AI Score", c: "" },
    { v: summary.preferred_vendors, l: "Preferred Vendors", c: "green" },
    { v: summary.high_delay_risk, l: "High Delay Risk", c: "amber" },
    { v: summary.high_breach_risk, l: "High Breach Risk", c: "red" },
    { v: summary.high_concentration_trades, l: "Concentration Risks", c: "amber" },
    { v: summary.overloaded_vendors, l: "Overloaded Vendors", c: "red" },
  ];
  cardData.forEach((d) => {
    cards.append(el("div", `card ${d.c}`,
      `<div class="value">${d.v}</div><div class="label">${d.l}</div>`));
  });

  const tb = document.querySelector("#sub-table tbody");
  tb.innerHTML = "";
  rows.forEach((r) => {
    tb.append(el("tr", "", `
      <td>${r.rank}</td>
      <td><b>${r.vendor}</b></td>
      <td>${r.trade}</td>
      <td>${r.project}</td>
      <td class="score">${r.ai_score}</td>
      <td>${badge(r.delay_risk)}</td>
      <td>${badge(r.contract_breach_risk)}</td>
      <td>${badge(r.capacity_status)} <small>${r.utilization}%</small></td>
      <td class="rec ${recClass(r.recommendation)}">${r.recommendation}</td>
      <td class="actions">
        <button class="icon-btn" title="Track progress"
          onclick="openTrack('${r.vendor_id}')">📈</button>
        <button class="icon-btn" title="Edit"
          onclick="openEditForm('subcontractors','${r.vendor_id}')">✏️</button>
        <button class="icon-btn" title="Delete"
          onclick="deleteRecord('subcontractors','${r.vendor_id}')">🗑️</button>
      </td>
    `));
  });

  // Vendor concentration (monopoly) risk per trade.
  const ct = document.querySelector("#conc-table tbody");
  ct.innerHTML = "";
  concentration.by_trade.forEach((t) => {
    ct.append(el("tr", "", `
      <td><b>${t.trade}</b></td>
      <td>${t.vendor_count}</td>
      <td>${t.top_vendor}</td>
      <td>${t.top_vendor_share}%</td>
      <td>${t.hhi}</td>
      <td>${badge(t.concentration_risk)}</td>
    `));
  });

  // Workforce capacity / overload (most loaded first, top 12).
  const cp = document.querySelector("#cap-table tbody");
  cp.innerHTML = "";
  capacity.vendors.slice(0, 12).forEach((v) => {
    cp.append(el("tr", "", `
      <td><b>${v.vendor}</b></td>
      <td>${v.active_projects}/${v.capacity_projects}</td>
      <td>${v.utilization}%</td>
      <td>${badge(v.capacity_status)}</td>
    `));
  });

  const box = document.getElementById("sub-alerts");
  box.innerHTML = "";
  alerts.breach_alerts.forEach((a) => {
    box.append(el("div", `alert ${a.contract_breach_risk === "High" ? "high" : ""}`,
      `<b>${a.vendor}</b><small>${a.project} · breach risk: ${a.contract_breach_risk}</small>`));
  });
  alerts.delay_alerts.filter(a => a.delay_risk === "High").forEach((a) => {
    box.append(el("div", "alert high",
      `<b>${a.vendor}</b><small>${a.project} · delay risk: High</small>`));
  });
  if (!box.children.length) box.append(el("div", "alert", "No active alerts 🎉"));
}

// ---------- Module 2: Materials ----------
async function loadMaterials() {
  const [summary, rows, suppliers, alerts, raw] = await Promise.all([
    api("/api/materials/summary"),
    api("/api/materials/evaluate"),
    api("/api/materials/suppliers"),
    api("/api/materials/alerts"),
    api("/api/materials/raw"),
  ]);
  RAW.materials = {};
  raw.forEach((r) => { RAW.materials[r.material_id] = r; });

  const cards = document.getElementById("mat-cards");
  cards.innerHTML = "";
  const cardData = [
    { v: summary.total_materials, l: "Materials Tracked", c: "" },
    { v: summary.critical_items, l: "Critical Stock", c: "red" },
    { v: summary.items_needing_action, l: "Need Purchase Action", c: "amber" },
    { v: summary.status_counts.Healthy || 0, l: "Healthy Stock", c: "green" },
    { v: summary.high_delay_risk, l: "High Delay Risk", c: "amber" },
  ];
  cardData.forEach((d) => {
    cards.append(el("div", `card ${d.c}`,
      `<div class="value">${d.v}</div><div class="label">${d.l}</div>`));
  });

  const tb = document.querySelector("#mat-table tbody");
  tb.innerHTML = "";
  rows.forEach((r) => {
    const switchSup = r.best_supplier !== r.current_supplier
      ? ` <small style="color:var(--blue)">↔ from ${r.current_supplier}</small>` : "";
    tb.append(el("tr", "", `
      <td><b>${r.material}</b></td>
      <td>${r.category}</td>
      <td>${r.current_stock} / ${r.minimum_stock}</td>
      <td>${r.demand_forecast}</td>
      <td>${badge(r.stock_status)}</td>
      <td class="rec ${recClass(r.recommended_action)}">${r.recommended_action}</td>
      <td>${r.reorder_qty || "—"}</td>
      <td>${r.best_supplier}${switchSup}</td>
      <td>${badge(r.delay_risk)}</td>
      <td class="actions">
        <button class="icon-btn" title="Edit"
          onclick="openEditForm('materials','${r.material_id}')">✏️</button>
        <button class="icon-btn" title="Delete"
          onclick="deleteRecord('materials','${r.material_id}')">🗑️</button>
      </td>
    `));
  });

  const st = document.querySelector("#sup-table tbody");
  st.innerHTML = "";
  suppliers.slice(0, 12).forEach((s) => {
    st.append(el("tr", "", `
      <td>${s.rank}</td>
      <td><b>${s.supplier}</b></td>
      <td class="score">${s.score}</td>
      <td>${s.avg_reliability}%</td>
      <td>${s.avg_lead_time}d</td>
    `));
  });

  const box = document.getElementById("mat-alerts");
  box.innerHTML = "";
  alerts.low_stock_alerts.forEach((a) => {
    box.append(el("div", `alert ${a.stock_status === "Critical" ? "high" : ""}`,
      `<b>${a.material}</b><small>${a.project} · ${a.stock_status} · ${a.recommended_action} (${a.reorder_qty})</small>`));
  });
  if (!box.children.length) box.append(el("div", "alert", "No stock alerts 🎉"));
}

// ---------- Boot + live auto-refresh ----------
async function refreshAll() {
  const status = document.getElementById("status");
  try {
    await Promise.all([loadSubcontractors(), loadMaterials()]);
    status.textContent = "live";
    status.className = "ok";
  } catch (e) {
    console.error(e);
    status.textContent = "error: " + e.message;
    status.className = "err";
  }
}

refreshAll();

// Auto-refresh every 30s so edits/uploads/other users reflect on their own.
// Skips while a modal is open so it doesn't interrupt data entry.
setInterval(() => {
  const editing = document.getElementById("modal-overlay").classList.contains("open");
  if (!editing && !document.hidden) refreshAll();
}, 30000);
