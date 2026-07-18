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
      ["vendor_id", "Vendor ID", "text", true],
      ["vendor_name", "Vendor Name", "text", true],
      ["trade", "Trade", "text"],
      ["project", "Project", "text"],
      ["contract_value", "Contract Value", "number"],
      ["planned_progress", "Planned Progress %", "number"],
      ["actual_progress", "Actual Progress %", "number"],
      ["quality_score", "Quality Score (0-100)", "number"],
      ["safety_score", "Safety Score (0-100)", "number"],
      ["inspection_pass", "Inspection Pass %", "number"],
      ["delay_days", "Delay Days", "number"],
      ["open_issues", "Open Issues", "number"],
      ["invoice_amount", "Invoice Amount", "number"],
      ["paid_amount", "Paid Amount", "number"],
      ["engineer_rating", "Engineer Rating (0-5)", "number"],
      ["client_rating", "Client Rating (0-5)", "number"],
      ["active_projects", "Active Projects", "number"],
      ["capacity_projects", "Capacity Projects", "number"],
    ],
  },
  materials: {
    label: "Material",
    reload: () => loadMaterials(),
    fields: [
      ["material_id", "Material ID", "text", true],
      ["material_name", "Material Name", "text", true],
      ["category", "Category", "text"],
      ["current_stock", "Current Stock", "number"],
      ["minimum_stock", "Minimum Stock", "number"],
      ["required_qty", "Required Qty", "number"],
      ["supplier", "Supplier", "text"],
      ["lead_time_days", "Lead Time (days)", "number"],
      ["unit_price", "Unit Price", "number"],
      ["delivery_reliability", "Delivery Reliability %", "number"],
      ["project", "Project", "text"],
      ["expected_delivery", "Expected Delivery", "date"],
    ],
  },
};

let activeModule = null;
const RAW = { subcontractors: {}, materials: {} };  // id -> raw record, for editing

function openForm(module, values) {
  activeModule = module;
  const spec = FIELD_SPECS[module];
  const editing = !!values;
  document.getElementById("modal-title").textContent =
    `${editing ? "Edit" : "Add"} ${spec.label}`;
  const form = document.getElementById("modal-form");
  form.innerHTML = spec.fields.map(([name, label, type, req], i) => {
    const raw = values && values[name] != null ? String(values[name]) : "";
    const val = raw.replace(/"/g, "&quot;");
    const isPk = i === 0;
    return `<label class="${req ? "req" : ""}">${label}
       <input name="${name}" type="${type}" ${req ? "required" : ""}
              ${type === "number" ? 'step="any"' : ""}
              value="${val}" ${editing && isPk ? "readonly" : ""}>
     </label>`;
  }).join("");
  document.getElementById("modal-overlay").classList.add("open");
}

function openAddForm(module) { openForm(module, null); }

function openEditForm(module, id) { openForm(module, RAW[module][id]); }

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
    flash(activeModule, `Saved ${payload[spec.fields[0][0]]} ✓`, "ok");
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
