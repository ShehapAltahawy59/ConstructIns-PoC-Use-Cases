// ConstructX AI — Companies → Subcontracts (SOV + EVM) → Progress claims.

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
function badge(level) { return `<span class="badge ${level}">${level}</span>`; }
function recClass(rec) {
  if (rec === "Preferred Vendor" || rec === "No Action") return "good";
  if (rec === "Do Not Assign New Projects" || rec === "Urgent Purchase") return "bad";
  return "warn";
}
const money = (n) => "$" + Math.round(n).toLocaleString();

// ---------- Generic data-entry (companies, materials) ----------
const FIELD_SPECS = {
  companies: {
    label: "Company", endpoint: "/api/subcontractors", pk: "vendor_id",
    reload: () => loadSubcontractors(),
    fields: [
      { n: "vendor_id", l: "Company ID", t: "text", req: true },
      { n: "company_name", l: "Company Name", t: "text", req: true },
      { n: "trade", l: "Trade", t: "text" },
      { n: "capacity_projects", l: "Capacity (max projects)", t: "number" },
    ],
  },
  subcontracts: {  // custom form; used by deleteRecord/reload only
    label: "Subcontract", endpoint: "/api/subcontracts", pk: "subcontract_id",
    reload: () => loadSubcontractors(),
  },
  materials: {
    label: "Material", endpoint: "/api/materials", pk: "material_id",
    reload: () => loadMaterials(),
    compute: (v) => {
      const num = (k) => parseFloat(v[k]) || 0;
      const r1 = (x) => Math.round(x * 10) / 10;
      const out = {};
      const dt = num("deliveries_total");
      if (dt > 0) out.delivery_reliability = r1((num("deliveries_on_time") / dt) * 100);
      const parts = String(v.lead_days || "").replace(/;/g, ",").split(",")
        .map((s) => parseFloat(s.trim())).filter((x) => x > 0);
      if (parts.length) out.lead_time_days = r1(parts.reduce((a, b) => a + b, 0) / parts.length);
      return out;
    },
    fields: [
      { n: "material_id", l: "Material ID", t: "text", req: true },
      { n: "material_name", l: "Material Name", t: "text", req: true },
      { n: "category", l: "Category", t: "text" },
      { n: "current_stock", l: "Current Stock", t: "number" },
      { n: "minimum_stock", l: "Minimum Stock", t: "number" },
      { n: "required_qty", l: "Required Qty", t: "number" },
      { n: "supplier", l: "Supplier", t: "text" },
      { n: "unit_price", l: "Unit Price", t: "number" },
      { k: "heading", l: "🚚 Raw delivery records — scores auto-calculate" },
      { n: "deliveries_total", l: "Deliveries — Total", t: "number", k: "raw" },
      { n: "deliveries_on_time", l: "Deliveries — On Time", t: "number", k: "raw" },
      { n: "lead_days", l: "Past Lead Times (days, comma-sep)", t: "text", k: "raw" },
      { n: "delivery_reliability", l: "Delivery Reliability % ⚙ auto", t: "number", k: "computed" },
      { n: "lead_time_days", l: "Lead Time (days) ⚙ auto", t: "number", k: "computed" },
      { k: "heading", l: "Schedule" },
      { n: "project", l: "Project", t: "text" },
      { n: "expected_delivery", l: "Expected Delivery", t: "date" },
    ],
  },
};

let activeSpec = null;
const RAW = { companies: {}, materials: {} };

function openForm(specKey, values, editing) {
  activeSpec = specKey;
  const spec = FIELD_SPECS[specKey];
  document.getElementById("modal-title").textContent = `${editing ? "Edit" : "Add"} ${spec.label}`;
  const form = document.getElementById("modal-form");
  form.innerHTML = spec.fields.map((f) => {
    if (f.k === "heading") return `<div class="form-heading">${f.l}</div>`;
    const raw = values && values[f.n] != null ? String(values[f.n]) : "";
    const val = raw.replace(/"/g, "&quot;");
    const cls = f.k === "raw" ? "raw-field" : f.k === "computed" ? "computed-field" : "";
    const ro = (editing && f.n === spec.pk) || f.k === "computed" ? "readonly" : "";
    return `<label class="${f.req ? "req " : ""}${cls}">${f.l}
       <input name="${f.n}" type="${f.t}" ${f.req ? "required" : ""}
              ${f.t === "number" ? 'step="any"' : ""} value="${val}" ${ro}></label>`;
  }).join("");
  form.oninput = () => recompute(specKey);
  document.getElementById("modal-overlay").classList.add("open");
}
function recompute(specKey) {
  const spec = FIELD_SPECS[specKey];
  if (!spec.compute) return;
  const form = document.getElementById("modal-form");
  const v = {};
  new FormData(form).forEach((val, k) => { v[k] = val; });
  Object.entries(spec.compute(v)).forEach(([k, val]) => {
    if (form.elements[k]) form.elements[k].value = val;
  });
}
function openAddForm(specKey) { openForm(specKey, null, false); }
function openEditForm(specKey, id) { openForm(specKey, RAW[specKey][id], true); }
function closeModal(e) {
  if (e && e.target !== e.currentTarget) return;
  document.getElementById("modal-overlay").classList.remove("open");
}
async function deleteRecord(specKey, id) {
  const spec = FIELD_SPECS[specKey];
  if (!confirm(`Delete ${id}? This cannot be undone.`)) return;
  try {
    const res = await fetch(`${spec.endpoint}/${encodeURIComponent(id)}`, { method: "DELETE" });
    if (!res.ok) throw new Error((await res.json()).detail || res.status);
    await spec.reload();
    if (isOpen("assign-overlay") && lastCompany) openSubcontracts(lastCompany);
    flash(`Deleted ${id} ✓`, "ok");
  } catch (err) { alert("Delete failed: " + err.message); }
}
async function submitAddForm() {
  if (activeSpec === "subcontracts") return submitSubcontract();
  const spec = FIELD_SPECS[activeSpec];
  const form = document.getElementById("modal-form");
  if (!form.reportValidity()) return;
  const payload = {};
  new FormData(form).forEach((v, k) => { if (v !== "") payload[k] = v; });
  try {
    const res = await fetch(spec.endpoint, {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload),
    });
    if (!res.ok) throw new Error((await res.json()).detail || res.status);
    closeModal();
    await spec.reload();
    flash(`Saved ${payload[spec.pk]} ✓`, "ok");
  } catch (err) { alert("Could not save: " + err.message); }
}
async function uploadFile(module, input) {
  activeSpec = module;
  const file = input.files[0];
  if (!file) return;
  const fd = new FormData(); fd.append("file", file);
  flash("Uploading…");
  try {
    const res = await fetch(`/api/${module}/upload?mode=append`, { method: "POST", body: fd });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || res.status);
    await FIELD_SPECS[module].reload();
    flash(`Imported ${data.inserted} new, updated ${data.updated} ✓`, "ok");
  } catch (err) { flash("Upload failed: " + err.message, "err"); }
  finally { input.value = ""; }
}
async function importWorkbook(module, input) {
  activeSpec = module;
  const file = input.files[0];
  if (!file) return;
  if (!confirm(`Import "${file.name}"? This replaces the current ${module} data.`)) {
    input.value = ""; return;
  }
  const fd = new FormData(); fd.append("file", file);
  flash("Importing…");
  try {
    const res = await fetch(`/api/${module}/import`, { method: "POST", body: fd });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || res.status);
    if (module === "materials") await loadMaterials(); else await loadSubcontractors();
    const n = Object.entries(data.imported).map(([k, v]) => `${v} ${k}`).join(", ");
    flash(`Imported ✓ — ${n}`, "ok");
  } catch (err) { flash("Import failed: " + err.message, "err"); }
  finally { input.value = ""; }
}

function flash(text, cls = "") {
  const e = document.getElementById(activeSpec === "materials" ? "mat-msg" : "sub-msg");
  if (!e) return;
  e.textContent = text; e.className = "toolbar-msg " + cls;
  if (cls === "ok") setTimeout(() => { e.textContent = ""; }, 5000);
}
const isOpen = (id) => document.getElementById(id).classList.contains("open");

// ---------- New / edit Subcontract (plan + Schedule of Values) ----------
function openSubcontractForm(prefill) {
  prefill = prefill || {};
  activeSpec = "subcontracts";
  document.getElementById("modal-title").textContent = "New Subcontract (the plan)";
  const g = (k) => prefill[k] != null ? String(prefill[k]).replace(/"/g, "&quot;") : "";
  const today = new Date().toISOString().slice(0, 10);
  const sovRow = (i) => `<div class="form-heading" style="border:none;margin:.2rem 0 0">SOV line ${i}</div>
    <label>Cost code<input name="sov_code_${i}" type="text"></label>
    <label>Description<input name="sov_desc_${i}" type="text"></label>
    <label>Scheduled value<input name="sov_val_${i}" type="number" step="any"></label>
    <div></div>`;
  document.getElementById("modal-form").innerHTML = `
    <label class="req">Subcontract ID<input name="subcontract_id" required></label>
    <label class="req">Company ID<input name="vendor_id" required value="${g("vendor_id")}"></label>
    <label>Company Name (if new)<input name="company_name" value="${g("company_name")}"></label>
    <label>Trade (if new company)<input name="trade" value="${g("trade")}"></label>
    <label class="req">Project ID<input name="project_id" required></label>
    <label>Project Name (if new)<input name="project_name"></label>
    <label style="grid-column:1/-1">Title<input name="title"></label>
    <label class="req">Start date<input name="start_date" type="date" value="${today}" required></label>
    <label class="req">Planned end date<input name="planned_end_date" type="date" required></label>
    <label>Retainage %<input name="retainage_pct" type="number" step="any" value="10"></label>
    <div class="form-heading">📋 Schedule of Values (contract = sum of lines)</div>
    ${sovRow(1)}${sovRow(2)}${sovRow(3)}`;
  document.getElementById("modal-overlay").classList.add("open");
}
async function submitSubcontract() {
  const form = document.getElementById("modal-form");
  if (!form.reportValidity()) return;
  const v = {};
  new FormData(form).forEach((val, k) => { if (val !== "") v[k] = val; });
  const sov = [];
  for (let i = 1; i <= 3; i++) {
    if (v[`sov_val_${i}`]) sov.push({
      cost_code: v[`sov_code_${i}`] || `L${i}`, description: v[`sov_desc_${i}`] || "",
      scheduled_value: v[`sov_val_${i}`],
    });
  }
  const payload = {
    subcontract_id: v.subcontract_id, vendor_id: v.vendor_id,
    company_name: v.company_name, trade: v.trade, project_id: v.project_id,
    project_name: v.project_name, title: v.title, start_date: v.start_date,
    planned_end_date: v.planned_end_date, retainage_pct: v.retainage_pct, sov,
  };
  try {
    const res = await fetch("/api/subcontracts", {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload),
    });
    if (!res.ok) throw new Error((await res.json()).detail || res.status);
    closeModal();
    await loadSubcontractors();
    if (isOpen("assign-overlay") && lastCompany) openSubcontracts(lastCompany);
    flash(`Saved ${payload.subcontract_id} ✓`, "ok");
  } catch (err) { alert("Could not save: " + err.message); }
}

// ---------- Company → subcontracts drill-down ----------
let lastCompany = null;
function closeAssign(e) { if (!e || e.target === e.currentTarget) document.getElementById("assign-overlay").classList.remove("open"); }

async function openSubcontracts(vendorId) {
  lastCompany = vendorId;
  const body = document.getElementById("assign-body");
  body.innerHTML = "Loading…";
  document.getElementById("assign-overlay").classList.add("open");
  try {
    const d = await api(`/api/subcontractors/${encodeURIComponent(vendorId)}/subcontracts`);
    const rows = d.subcontracts.map((s) => {
      const isNew = s.evaluable === false;
      const score = isNew ? `<span class="badge New">🆕 New</span>` : `<b>${s.ai_score}</b>`;
      const spiCls = s.kpis && s.actual_progress < s.planned_progress ? "bad" : "good";
      return `<tr>
        <td><b>${s.project}</b></td>
        <td>${money(s.contract_value)}</td>
        <td>${s.planned_progress}%</td>
        <td class="rec ${spiCls}">${s.actual_progress}%</td>
        <td>${score}</td>
        <td class="actions">
          <button class="icon-btn" title="Details / SOV / claims" onclick="openSubDetail('${s.subcontract_id}')">📊</button>
          <button class="icon-btn" title="Delete" onclick="deleteRecord('subcontracts','${s.subcontract_id}')">🗑️</button>
        </td></tr>`;
    }).join("");
    body.innerHTML = `
      <h3 style="margin:0 0 .2rem">📂 ${d.company} — Subcontracts</h3>
      <p class="subtitle" style="margin:.1rem 0 1rem">${d.trade} · capacity ${d.capacity_projects} projects</p>
      <div class="table-wrap"><table><thead><tr>
        <th>Project</th><th>Contract</th><th>Planned</th><th>Actual</th><th>AI Score</th><th></th>
      </tr></thead><tbody>${rows || '<tr><td colspan="6">No subcontracts yet.</td></tr>'}</tbody></table></div>
      <button class="btn" style="margin-top:.9rem"
        onclick='openSubcontractForm({vendor_id:"${vendorId}",company_name:"${d.company.replace(/"/g, "")}",trade:"${d.trade}"})'>
        ➕ New subcontract for ${d.company}</button>`;
  } catch (err) { body.innerHTML = `<p class="rec bad">Could not load: ${err.message}</p>`; }
}

// ---------- Subcontract detail (SOV + EVM + progress-claim S-curve) ----------
function closeTrack(e) { if (!e || e.target === e.currentTarget) document.getElementById("track-overlay").classList.remove("open"); }

function trendChart(points, planned) {
  const W = 540, H = 190, pad = 34;
  if (!points.length) return "<p>No progress claims yet.</p>";
  const n = points.length;
  const x = (i) => pad + (W - 2 * pad) * (n === 1 ? 0.5 : i / (n - 1));
  const y = (val) => H - pad - (H - 2 * pad) * (Math.max(0, Math.min(100, val)) / 100);
  const path = points.map((p, i) => `${i ? "L" : "M"}${x(i).toFixed(1)},${y(p.pct).toFixed(1)}`).join(" ");
  const dots = points.map((p, i) => `<circle cx="${x(i).toFixed(1)}" cy="${y(p.pct).toFixed(1)}" r="3.5" fill="#1a2ce0"/>`).join("");
  const pl = planned != null ? `<line x1="${pad}" y1="${y(planned).toFixed(1)}" x2="${W - pad}" y2="${y(planned).toFixed(1)}" stroke="#e0930a" stroke-dasharray="5"/>
    <text x="${W - pad}" y="${(y(planned) - 5).toFixed(1)}" font-size="10" fill="#e0930a" text-anchor="end">planned ${planned}%</text>` : "";
  const labels = points.map((p, i) => `<text x="${x(i).toFixed(1)}" y="${H - pad + 14}" font-size="9" fill="#888" text-anchor="middle">${(p.label || "").slice(5)}</text>`).join("");
  return `<svg viewBox="0 0 ${W} ${H}" class="trendchart" width="100%">
    <line x1="${pad}" y1="${pad}" x2="${pad}" y2="${H - pad}" stroke="#ddd"/>
    <line x1="${pad}" y1="${H - pad}" x2="${W - pad}" y2="${H - pad}" stroke="#ddd"/>
    ${pl}<path d="${path}" fill="none" stroke="#1a2ce0" stroke-width="2.5"/>${dots}${labels}</svg>`;
}

async function openSubDetail(sid) {
  const body = document.getElementById("track-body");
  body.innerHTML = "Loading…";
  document.getElementById("track-overlay").classList.add("open");
  try {
    const d = await api(`/api/subcontracts/${encodeURIComponent(sid)}`);
    const m = d.evm;
    const behind = m.schedule_variance_pct < 0;
    const sovRows = d.sov.map((l) => `<tr><td>${l.cost_code}</td><td>${l.description}</td>
      <td>${money(l.scheduled_value)}</td><td>${l.percent_complete}%</td></tr>`).join("");
    const claimInputs = d.sov.map((l) =>
      `<label>${l.cost_code} ${l.description}<input name="claim_${l.line_id}" type="number" step="any" value="${l.percent_complete}"></label>`).join("");
    const points = d.claims.map((c) => ({ label: c.period_end, pct: c.percent_complete }));
    const today = new Date().toISOString().slice(0, 10);
    const coRows = (d.change_orders || []).map((c) => `<tr>
      <td>${c.description}</td>
      <td class="rec ${c.amount < 0 ? "bad" : ""}">${money(c.amount)}</td>
      <td>${c.status === "Approved" ? badge("Low") : badge("Medium")} ${c.status}</td>
      <td class="actions">
        ${c.status === "Pending" ? `<button class="icon-btn" title="Approve" onclick="approveCO('${sid}','${c.co_id}')">✅</button>` : ""}
        <button class="icon-btn" title="Delete" onclick="deleteCO('${sid}','${c.co_id}')">🗑️</button>
      </td></tr>`).join("");
    const contractLine = d.approved_co_total
      ? `Contract <b>${money(m.contract_value)}</b> <small>(orig ${money(d.original_value)} + CO ${money(d.approved_co_total)})</small>`
      : `Contract <b>${money(m.contract_value)}</b>`;
    body.innerHTML = `
      <h3 style="margin:0 0 .2rem">📊 ${d.company} — ${d.project}</h3>
      <p class="subtitle" style="margin:.1rem 0 1rem">${d.title} · ${d.start_date} → ${d.planned_end_date}</p>
      <div class="track-summary">
        ${contractLine} ·
        Planned <b>${m.planned_progress}%</b> · Actual
        <span class="rec ${behind ? "bad" : "good"}">${m.actual_progress}%</span> ·
        SPI <b>${m.spi ?? "—"}</b> <span class="rec ${behind ? "bad" : "good"}">(${m.schedule_variance_pct}%)</span>
        <div style="margin-top:.3rem;color:var(--muted);font-size:.85rem">
          Billed <b>${money(m.billed_to_date)}</b> · retainage ${m.retainage_pct}%:
          held <b>${money(m.retained)}</b>, released <b>${money(m.retainage_released)}</b> ·
          net paid <b>${money(m.net_paid)}</b>
          ${m.retained > 0 ? `<button class="btn ghost" style="margin-left:.5rem;padding:.2rem .6rem" onclick="releaseRetainage('${sid}')">Release retainage</button>` : ""}
        </div>
      </div>
      <h4 style="margin:.6rem 0 .3rem">Progress S-curve (planned vs actual)</h4>
      ${trendChart(points, m.planned_progress)}
      <h4 style="margin:1rem 0 .3rem">Schedule of Values</h4>
      <div class="table-wrap"><table><thead><tr>
        <th>Cost code</th><th>Description</th><th>Scheduled value</th><th>% complete</th>
      </tr></thead><tbody>${sovRows}</tbody></table></div>
      <h4 style="margin:1.1rem 0 .3rem">Log a progress claim (update % complete per line)</h4>
      <form id="claim-form" onsubmit="submitClaim('${sid}');return false;" class="modal-form">
        <label class="req">Period end<input name="period_end" type="date" value="${today}" required></label>
        <div></div>${claimInputs}
      </form>
      <button class="btn" style="margin-top:.7rem" onclick="submitClaim('${sid}')">＋ Submit claim</button>
      <h4 style="margin:1.2rem 0 .3rem">Change Orders</h4>
      <div class="table-wrap"><table><thead><tr>
        <th>Description</th><th>Amount</th><th>Status</th><th></th>
      </tr></thead><tbody>${coRows || '<tr><td colspan="4">None.</td></tr>'}</tbody></table></div>
      <form id="co-form" onsubmit="addChangeOrder('${sid}');return false;" class="modal-form" style="margin-top:.5rem">
        <label class="req">Description<input name="description" required></label>
        <label class="req">Amount (+/-)<input name="amount" type="number" step="any" required></label>
      </form>
      <button class="btn ghost" style="margin-top:.5rem" onclick="addChangeOrder('${sid}')">＋ Raise change order</button>
      <h4 style="margin:1.2rem 0 .3rem">Log inspection / safety <span class="hint">(updates Quality &amp; Safety scores)</span></h4>
      <form id="insp-form" onsubmit="logInspection('${sid}');return false;" class="modal-form">
        <label>Inspections — Total<input name="inspections_total" type="number"></label>
        <label>Inspections — Passed<input name="inspections_passed" type="number"></label>
        <label>NCRs Raised<input name="ncrs_raised" type="number"></label>
        <label>NCRs Closed<input name="ncrs_closed" type="number"></label>
        <label>Recordable Incidents<input name="recordable_incidents" type="number"></label>
        <label>Man-Hours Worked<input name="man_hours" type="number"></label>
        <label>Delay Days<input name="delay_days" type="number"></label>
        <label>Open Issues<input name="open_issues" type="number"></label>
      </form>
      <button class="btn ghost" style="margin-top:.5rem" onclick="logInspection('${sid}')">＋ Log inspection</button>`;
  } catch (err) { body.innerHTML = `<p class="rec bad">Could not load: ${err.message}</p>`; }
}

async function submitClaim(sid) {
  const form = document.getElementById("claim-form");
  if (!form.reportValidity()) return;
  const lines = [];
  let period = null;
  new FormData(form).forEach((val, k) => {
    if (k === "period_end") period = val;
    else if (k.startsWith("claim_") && val !== "")
      lines.push({ line_id: k.slice(6), percent_complete: val });
  });
  try {
    const res = await fetch(`/api/subcontracts/${encodeURIComponent(sid)}/claim`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ period_end: period, lines }),
    });
    if (!res.ok) throw new Error((await res.json()).detail || res.status);
    await openSubDetail(sid);
    await loadSubcontractors();
    if (isOpen("assign-overlay") && lastCompany) openSubcontracts(lastCompany);
  } catch (err) { alert("Could not save claim: " + err.message); }
}

async function _post(url, body, sid) {
  const res = await fetch(url, {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body || {}),
  });
  if (!res.ok) throw new Error((await res.json()).detail || res.status);
  await openSubDetail(sid);
  await loadSubcontractors();
}

async function addChangeOrder(sid) {
  const form = document.getElementById("co-form");
  if (!form.reportValidity()) return;
  const v = {};
  new FormData(form).forEach((val, k) => { v[k] = val; });
  try { await _post(`/api/subcontracts/${sid}/change-order`, v, sid); }
  catch (e) { alert("Change order failed: " + e.message); }
}
async function approveCO(sid, coId) {
  try { await _post(`/api/subcontracts/${sid}/change-order/${coId}/approve`, {}, sid); }
  catch (e) { alert("Approve failed: " + e.message); }
}
async function deleteCO(sid, coId) {
  if (!confirm("Delete this change order?")) return;
  try {
    const res = await fetch(`/api/subcontracts/${sid}/change-order/${coId}`, { method: "DELETE" });
    if (!res.ok) throw new Error(res.status);
    await openSubDetail(sid); await loadSubcontractors();
  } catch (e) { alert("Delete failed: " + e.message); }
}
async function releaseRetainage(sid) {
  if (!confirm("Release the retainage held to date?")) return;
  try { await _post(`/api/subcontracts/${sid}/release-retainage`, {}, sid); }
  catch (e) { alert("Release failed: " + e.message); }
}
async function logInspection(sid) {
  const form = document.getElementById("insp-form");
  const v = {};
  new FormData(form).forEach((val, k) => { if (val !== "") v[k] = val; });
  try {
    await _post(`/api/subcontracts/${sid}/inspection`, v, sid);
    if (isOpen("assign-overlay") && lastCompany) openSubcontracts(lastCompany);
  } catch (e) { alert("Log failed: " + e.message); }
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

// ---------- Module 1: Companies ----------
async function loadSubcontractors() {
  const [summary, rows, alerts, concentration, capacity, raw] = await Promise.all([
    api("/api/subcontractors/summary"),
    api("/api/subcontractors/companies"),
    api("/api/subcontractors/alerts"),
    api("/api/subcontractors/concentration"),
    api("/api/subcontractors/capacity"),
    api("/api/subcontractors/raw"),
  ]);
  RAW.companies = {};
  raw.forEach((c) => { RAW.companies[c.vendor_id] = c; });

  const cards = document.getElementById("sub-cards");
  cards.innerHTML = "";
  [
    { v: summary.total_vendors, l: "Companies", c: "" },
    { v: summary.total_assignments, l: "Subcontracts", c: "" },
    { v: summary.avg_ai_score ?? "—", l: "Avg Score (rated)", c: "" },
    { v: summary.preferred_vendors, l: "Preferred", c: "green" },
    { v: summary.new_vendors, l: "New / Unrated", c: "" },
    { v: summary.high_delay_risk, l: "High Delay Risk", c: "amber" },
    { v: summary.high_concentration_trades, l: "Concentration Risks", c: "amber" },
    { v: summary.overloaded_vendors, l: "Overloaded", c: "red" },
  ].forEach((d) => cards.append(el("div", `card ${d.c}`,
    `<div class="value">${d.v}</div><div class="label">${d.l}</div>`)));

  const tb = document.querySelector("#sub-table tbody");
  tb.innerHTML = "";
  rows.forEach((r) => {
    const isNew = r.evaluable === false;
    const scoreCell = isNew ? `<td><span class="badge New">🆕 New</span></td>` : `<td class="score">${r.avg_score}</td>`;
    const riskCell = (v) => isNew ? "<td>—</td>" : `<td>${badge(v)}</td>`;
    const recCell = isNew ? `<td class="rec">New — collecting data</td>`
      : `<td class="rec ${recClass(r.recommendation)}">${r.recommendation}</td>`;
    tb.append(el("tr", isNew ? "new-row" : "", `
      <td>${r.rank ?? "—"}</td>
      <td><b>${r.company}</b></td>
      <td>${r.trade}</td>
      ${scoreCell}
      <td>${r.projects}</td>
      <td>${badge(r.capacity_status)} <small>${r.utilization}%</small></td>
      ${riskCell(r.delay_risk)}
      ${riskCell(r.contract_breach_risk)}
      ${recCell}
      <td class="actions">
        <button class="icon-btn" title="Subcontracts" onclick="openSubcontracts('${r.vendor_id}')">📂</button>
        <button class="icon-btn" title="Edit" onclick="openEditForm('companies','${r.vendor_id}')">✏️</button>
        <button class="icon-btn" title="Delete" onclick="deleteRecord('companies','${r.vendor_id}')">🗑️</button>
      </td>`));
  });

  const ct = document.querySelector("#conc-table tbody");
  ct.innerHTML = "";
  concentration.by_trade.forEach((t) => ct.append(el("tr", "", `
    <td><b>${t.trade}</b></td><td>${t.vendor_count}</td><td>${t.top_vendor}</td>
    <td>${t.top_vendor_share}%</td><td>${t.hhi}</td><td>${badge(t.concentration_risk)}</td>`)));

  const cp = document.querySelector("#cap-table tbody");
  cp.innerHTML = "";
  capacity.vendors.slice(0, 12).forEach((v) => cp.append(el("tr", "", `
    <td><b>${v.vendor}</b></td><td>${v.active_projects}/${v.capacity_projects}</td>
    <td>${v.utilization}%</td><td>${badge(v.capacity_status)}</td>`)));

  const box = document.getElementById("sub-alerts");
  box.innerHTML = "";
  alerts.breach_alerts.forEach((a) => box.append(el("div",
    `alert ${a.contract_breach_risk === "High" ? "high" : ""}`,
    `<b>${a.vendor}</b><small>breach risk: ${a.contract_breach_risk}</small>`)));
  alerts.delay_alerts.filter((a) => a.delay_risk === "High").forEach((a) => box.append(el("div",
    "alert high", `<b>${a.vendor}</b><small>delay risk: High</small>`)));
  if (!box.children.length) box.append(el("div", "alert", "No active alerts 🎉"));
}

// ---------- Module 2: Material procurement ----------
async function loadMaterials() {
  const [summary, rows, suppliers, alerts] = await Promise.all([
    api("/api/materials/summary"), api("/api/materials/inventory"),
    api("/api/materials/suppliers"), api("/api/materials/alerts"),
  ]);
  const cards = document.getElementById("mat-cards");
  cards.innerHTML = "";
  [
    { v: summary.total_materials, l: "Requirements", c: "" },
    { v: summary.critical_items, l: "Critical Stock", c: "red" },
    { v: summary.items_needing_action, l: "Need Purchase", c: "amber" },
    { v: summary.on_order_items, l: "On Order", c: "" },
    { v: (summary.status_counts.Healthy || 0), l: "Healthy Stock", c: "green" },
    { v: summary.invoice_exceptions, l: "Invoice Exceptions", c: "red" },
    { v: summary.suppliers, l: "Suppliers", c: "" },
  ].forEach((d) => cards.append(el("div", `card ${d.c}`,
    `<div class="value">${d.v}</div><div class="label">${d.l}</div>`)));

  const tb = document.querySelector("#mat-table tbody");
  tb.innerHTML = "";
  rows.forEach((r) => {
    const sw = r.best_supplier !== r.supplier
      ? ` <small style="color:var(--blue)">↔ ${r.supplier}</small>` : "";
    tb.append(el("tr", "", `
      <td>${r.project}</td><td><b>${r.material}</b> <small>${r.unit}</small></td>
      <td>${r.current_stock} / ${r.minimum_stock}</td>
      <td>${r.on_order ? r.on_order : "—"}</td>
      <td>${badge(r.stock_status)}</td><td>${r.demand_forecast}</td>
      <td class="rec ${recClass(r.recommended_action)}">${r.recommended_action}</td>
      <td>${r.reorder_qty || "—"}</td><td>${r.best_supplier}${sw}</td>
      <td>${badge(r.delay_risk)}</td>
      <td class="actions">
        <button class="icon-btn" title="POs & deliveries" onclick="openMatDetail('${r.req_id}')">📊</button>
      </td>`));
  });

  const st = document.querySelector("#sup-table tbody");
  st.innerHTML = "";
  suppliers.slice(0, 12).forEach((s) => st.append(el("tr", "", `
    <td>${s.rank}</td><td><b>${s.name}</b></td><td class="score">${s.score}</td>
    <td>${s.reliability}%</td><td>${s.avg_lead_time ?? "—"}d</td>
    <td class="${s.defect_rate > 0 ? "rec bad" : ""}">${s.defect_rate}%</td><td>${s.deliveries}</td>`)));

  const box = document.getElementById("mat-alerts");
  box.innerHTML = "";
  alerts.low_stock_alerts.forEach((a) => box.append(el("div",
    `alert ${a.stock_status === "Critical" ? "high" : ""}`,
    `<b>${a.material}</b><small>${a.project} · ${a.stock_status} · ${a.recommended_action} (${a.reorder_qty})</small>`)));
  if (!box.children.length) box.append(el("div", "alert", "No stock alerts 🎉"));
}

async function openMatDetail(reqId) {
  activeSpec = "materials";
  const body = document.getElementById("track-body");
  body.innerHTML = "Loading…";
  document.getElementById("track-overlay").classList.add("open");
  try {
    const d = await api(`/api/materials/${encodeURIComponent(reqId)}`);
    lastReq = reqId;
    const matchBadge = (ms) => ms === "Matched" ? badge("Low")
      : ms === "No invoice" ? '<span class="badge">—</span>' : badge("High");
    const poRows = d.purchase_orders.map((p) => `<tr>
      <td>${p.po_id}</td><td>${p.supplier}</td><td>${p.qty_ordered}</td>
      <td>${p.status === "Received" ? badge("Low") : badge("Medium")} ${p.status}</td>
      <td>ord ${p.match.ordered_qty} / recv ${p.match.received_qty} / bill ${p.match.billed_qty}</td>
      <td>${matchBadge(p.match.match_status)} <small>${p.match.match_status}</small></td></tr>`).join("");
    const allPOs = d.purchase_orders.map((p) => `<option value="${p.po_id}">${p.po_id} (${p.supplier})</option>`).join("");
    const delRows = d.deliveries.map((x) => `<tr>
      <td>${x.qty_received}</td><td>${x.order_date || "—"}</td><td>${x.expected_date || "—"}</td>
      <td>${x.received_date || "—"}</td><td>${x.on_time ? badge("Low") + " on-time" : badge("High") + " late"}</td></tr>`).join("");
    const openPOs = d.purchase_orders.filter((p) => p.status !== "Received");
    const poOptions = openPOs.map((p) => `<option value="${p.po_id}">${p.po_id} (${p.supplier}, ${p.qty_ordered})</option>`).join("");
    const supOptions = d.suppliers.map((s) => `<option value="${s.supplier_id}">${s.name}</option>`).join("");
    const today = new Date().toISOString().slice(0, 10);
    body.innerHTML = `
      <h3 style="margin:0 0 .2rem">📊 ${d.material} — ${d.project}</h3>
      <p class="subtitle" style="margin:.1rem 0 1rem">${d.category} · unit ${d.unit}</p>
      <div class="track-summary">
        Stock <b>${d.current_stock} ${d.unit}</b> · min ${d.minimum_stock} · required ${d.required_qty} ·
        consumed ${d.consumed_qty} · on order <b>${d.on_order}</b>
        <div style="margin-top:.3rem;color:var(--muted);font-size:.82rem">stock = delivered − consumed</div>
      </div>
      <h4 style="margin:.6rem 0 .3rem">Purchase Orders &amp; 3-way match</h4>
      <div class="table-wrap"><table><thead><tr>
        <th>PO</th><th>Supplier</th><th>Qty</th><th>Status</th><th>Ordered/Received/Billed</th><th>Match</th>
      </tr></thead><tbody>${poRows || '<tr><td colspan="6">None.</td></tr>'}</tbody></table></div>
      <h4 style="margin:1rem 0 .3rem">Deliveries (GRN)</h4>
      <div class="table-wrap"><table><thead><tr>
        <th>Qty received</th><th>Ordered</th><th>Expected</th><th>Received</th><th>On time</th>
      </tr></thead><tbody>${delRows || '<tr><td colspan="5">None yet.</td></tr>'}</tbody></table></div>
      ${openPOs.length ? `
      <h4 style="margin:1.1rem 0 .3rem">Record a delivery (GRN)</h4>
      <form id="grn-form" onsubmit="submitDelivery('${reqId}','${d.material_id}');return false;" class="modal-form">
        <label class="req">Against PO<select name="po_id" required>${poOptions}</select></label>
        <label class="req">Qty received<input name="qty_received" type="number" step="any" required></label>
        <label>Qty rejected (defective)<input name="qty_rejected" type="number" step="any"></label>
        <label class="req">Received date<input name="received_date" type="date" value="${today}" required></label>
      </form>
      <button class="btn" style="margin-top:.6rem" onclick="submitDelivery('${reqId}','${d.material_id}')">＋ Record delivery</button>` : ""}
      <h4 style="margin:1.2rem 0 .3rem">Submit invoice (3-way match)</h4>
      <form id="inv-form" onsubmit="submitInvoice('${reqId}');return false;" class="modal-form">
        <label class="req">Against PO<select name="po_id" required>${allPOs}</select></label>
        <label class="req">Billed qty<input name="billed_qty" type="number" step="any" required></label>
        <label class="req">Amount<input name="amount" type="number" step="any" required></label>
      </form>
      <button class="btn ghost" style="margin-top:.6rem" onclick="submitInvoice('${reqId}')">＋ Submit invoice</button>
      <h4 style="margin:1.2rem 0 .3rem">Raise a purchase order</h4>
      <form id="po-form" onsubmit="submitPO('${reqId}','${d.project_id}','${d.material_id}');return false;" class="modal-form">
        <label class="req">Supplier<select name="supplier_id" required>${supOptions}</select></label>
        <label class="req">Qty ordered<input name="qty_ordered" type="number" step="any" required></label>
        <label>Unit price<input name="unit_price" type="number" step="any"></label>
        <label>Expected delivery<input name="expected_delivery" type="date"></label>
      </form>
      <button class="btn ghost" style="margin-top:.6rem" onclick="submitPO('${reqId}','${d.project_id}','${d.material_id}')">＋ Raise PO</button>`;
  } catch (err) { body.innerHTML = `<p class="rec bad">Could not load: ${err.message}</p>`; }
}
let lastReq = null;
async function submitDelivery(reqId, materialId) {
  const form = document.getElementById("grn-form");
  if (!form.reportValidity()) return;
  const v = { material_id: materialId };
  new FormData(form).forEach((val, k) => { if (val !== "") v[k] = val; });
  try {
    const res = await fetch("/api/materials/delivery", {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(v),
    });
    if (!res.ok) throw new Error((await res.json()).detail || res.status);
    await openMatDetail(reqId); await loadMaterials();
  } catch (e) { alert("Could not record delivery: " + e.message); }
}
async function submitPO(reqId, projectId, materialId) {
  const form = document.getElementById("po-form");
  if (!form.reportValidity()) return;
  const v = { project_id: projectId, material_id: materialId };
  new FormData(form).forEach((val, k) => { if (val !== "") v[k] = val; });
  try {
    const res = await fetch("/api/materials/po", {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(v),
    });
    if (!res.ok) throw new Error((await res.json()).detail || res.status);
    await openMatDetail(reqId); await loadMaterials();
  } catch (e) { alert("Could not raise PO: " + e.message); }
}
async function submitInvoice(reqId) {
  const form = document.getElementById("inv-form");
  if (!form.reportValidity()) return;
  const v = {};
  new FormData(form).forEach((val, k) => { if (val !== "") v[k] = val; });
  try {
    const res = await fetch("/api/materials/invoice", {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(v),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || res.status);
    alert("Invoice " + data.invoice_id + " — 3-way match: " + data.match.match_status);
    await openMatDetail(reqId); await loadMaterials();
  } catch (e) { alert("Could not submit invoice: " + e.message); }
}

// ---------- Boot + auto-refresh ----------
async function refreshAll() {
  const status = document.getElementById("status");
  try {
    await Promise.all([loadSubcontractors(), loadMaterials()]);
    status.textContent = "live"; status.className = "ok";
  } catch (e) {
    console.error(e); status.textContent = "error: " + e.message; status.className = "err";
  }
}
refreshAll();
setInterval(() => {
  if (["modal-overlay", "track-overlay", "assign-overlay"].some(isOpen) || document.hidden) return;
  const active = document.querySelector(".module.active");
  if (active && active.id === "materials") loadMaterials(); else loadSubcontractors();
}, 30000);
