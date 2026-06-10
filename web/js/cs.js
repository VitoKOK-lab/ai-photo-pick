// cs.js — 客服訂單追蹤前端邏輯（純 JS，無建置步驟）
const BASE = "";

async function api(path, opts = {}) {
  const r = await fetch(BASE + path, opts);
  if (!r.ok) {
    let msg = `錯誤 ${r.status}`;
    try { msg = (await r.json()).detail || msg; } catch {}
    throw new Error(msg);
  }
  return r.json();
}
const jpost = (p, b) => api(p, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(b) });
const jput  = (p, b) => api(p, { method: "PUT",  headers: { "Content-Type": "application/json" }, body: JSON.stringify(b) });

const $ = (id) => document.getElementById(id);
const esc = (s) => (s == null ? "" : String(s).replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c])));

let META = { track_statuses: [], risk_types: [] };
let currentView = "active";
let searchTerm = "";
let currentOrder = null;

// ─── 看板 ────────────────────────────────────────────────────────────────────
async function loadDashboard() {
  const d = await api("/api/cs/dashboard");
  $("dash").innerHTML = `
    <button class="dash-card ${currentView === "active" ? "active" : ""}" data-view="active">
      <div class="num">${d.active}</div><div class="label">進行中訂單</div></button>
    <button class="dash-card c-risk ${currentView === "risk" ? "active" : ""}" data-view="risk">
      <div class="num">${d.risk}</div><div class="label">🔴 異常待處理</div></button>
    <button class="dash-card c-overdue ${currentView === "overdue" ? "active" : ""}" data-view="overdue">
      <div class="num">${d.overdue}</div><div class="label">🟠 逾期未出貨</div></button>
    <button class="dash-card c-payment ${currentView === "payment" ? "active" : ""}" data-view="payment">
      <div class="num">${d.payment_overdue}</div><div class="label">🟡 付款超時</div></button>`;
  $("dash").querySelectorAll(".dash-card").forEach(c =>
    c.addEventListener("click", () => setView(c.dataset.view)));
  if (d.last_import) $("last-import").textContent = "最後更新：" + d.last_import.replace("T", " ").slice(0, 16);
}

function statusPill(s) { return `<span class="pill pill-status">${esc(s || "—")}</span>`; }

// 組出連回 SHOPLINE 後台的訂單網址
function shoplineUrl(orderNumber) {
  const tpl = META.shopline_order_url;
  if (!tpl || !orderNumber) return "";
  return tpl.replace("{handle}", META.shopline_handle || "")
            .replace("{order_number}", encodeURIComponent(orderNumber));
}
function shoplineLink(orderNumber, label) {
  const url = shoplineUrl(orderNumber);
  if (!url) return "";
  return `<a class="sl-link" href="${esc(url)}" target="_blank" rel="noopener"
    title="到 SHOPLINE 後台叫出這張單" onclick="event.stopPropagation()">${label || "🔗 SHOPLINE"}</a>`;
}

async function loadOrders() {
  const params = new URLSearchParams({ view: currentView });
  if (searchTerm) params.set("q", searchTerm);
  const rows = await api("/api/cs/orders?" + params);
  const tb = $("orders-tbody");
  tb.innerHTML = "";
  $("board-empty").classList.toggle("hidden", rows.length > 0);

  for (const o of rows) {
    const tr = document.createElement("tr");
    tr.className = o.is_risk ? "row-risk" : (o.overdue ? "row-overdue" : "");
    const flags = [];
    if (o.is_risk) flags.push(`<span class="flag flag-risk">🔴 ${esc(o.risk_type || "異常")}</span>`);
    if (o.overdue) flags.push(`<span class="flag flag-overdue">🟠 逾期</span>`);
    tr.innerHTML = `
      <td class="ordno">${esc(o.order_number)}${shoplineLink(o.order_number, "🔗")}</td>
      <td class="cust">${esc(o.customer_name || "—")}</td>
      <td class="hide-sm truncate">${esc(o.item_summary || "—")}</td>
      <td>${statusPill(o.track_status)}</td>
      <td>${esc(o.owner || "—")}</td>
      <td class="hide-sm truncate ${o.next_action ? "" : "muted"}">${esc(o.next_action || "—")}</td>
      <td class="${o.overdue ? "" : "muted"}">${esc(o.due_date || "—")}</td>
      <td>${flags.join(" ") || "—"}</td>`;
    tr.addEventListener("click", () => openOrder(o.id));
    tb.appendChild(tr);
  }
}

function setView(v) {
  currentView = v;
  document.querySelectorAll(".chip").forEach(c => c.classList.toggle("active", c.dataset.view === v));
  loadDashboard();
  loadOrders();
}

async function refresh() { await Promise.all([loadDashboard(), loadOrders()]); }

// ─── 訂單編輯 ─────────────────────────────────────────────────────────────────
function fillSelect(sel, options, value) {
  sel.innerHTML = options.map(o => `<option value="${esc(o)}"${o === value ? " selected" : ""}>${esc(o)}</option>`).join("");
}

async function openOrder(id) {
  const o = await api(`/api/cs/orders/${id}`);
  currentOrder = o;
  // 真實姓名擺第一眼，後面接訂單號與一鍵跳回 SHOPLINE
  $("om-title").innerHTML = `${esc(o.customer_name || "（無收件人）")}
    <span class="om-ordno">${esc(o.order_number)}</span>
    ${shoplineLink(o.order_number, "🔗 到 SHOPLINE 叫單")}`;
  $("om-sub").textContent = [o.phone, o.item_summary, o.total].filter(Boolean).join(" · ");
  fillSelect($("om-status"), META.track_statuses, o.track_status);
  fillSelect($("om-risktype"), ["", ...META.risk_types], o.risk_type || "");
  $("om-owner").value = o.owner || "";
  $("om-next").value = o.next_action || "";
  $("om-due").value = o.due_date || "";
  $("om-risk").checked = !!o.is_risk;
  $("om-notes").value = o.notes || "";
  const raw = o.raw || {};
  $("om-raw").innerHTML = Object.keys(raw).length
    ? Object.entries(raw).map(([k, v]) => `<div><b>${esc(k)}</b>: ${esc(v)}</div>`).join("")
    : '<span class="muted">（此單非由報表匯入）</span>';
  $("om-rawwrap").classList.toggle("hidden", !Object.keys(raw).length);
  $("order-modal").classList.remove("hidden");
}

async function saveOrder() {
  if (!currentOrder) return;
  await jput(`/api/cs/orders/${currentOrder.id}`, {
    track_status: $("om-status").value,
    owner: $("om-owner").value.trim(),
    next_action: $("om-next").value.trim(),
    due_date: $("om-due").value || null,
    is_risk: $("om-risk").checked,
    risk_type: $("om-risktype").value || null,
    notes: $("om-notes").value.trim(),
  });
  $("order-modal").classList.add("hidden");
  refresh();
}

async function archiveOrder() {
  if (!currentOrder) return;
  if (!confirm("把這張單移入封存資料庫？（之後可在「已封存」分類查到）")) return;
  await jput(`/api/cs/orders/${currentOrder.id}`, { archived: true });
  $("order-modal").classList.add("hidden");
  refresh();
}

// ─── 匯入 ────────────────────────────────────────────────────────────────────
async function doImport() {
  const f = $("import-file").files[0];
  if (!f) { alert("請先選擇 CSV 檔案"); return; }
  $("import-result").innerHTML = "匯入中…";
  const fd = new FormData();
  fd.append("file", f);
  try {
    const r = await api("/api/cs/import", { method: "POST", body: fd });
    const orders = (r.orders_in_file != null) ? `（合併為 ${r.orders_in_file} 張訂單）` : "";
    let html = `<div class="import-result">
      讀取 ${r.rows_read} 列${orders}　→
      新增 <b>${r.new}</b> 筆新單，更新 ${r.updated} 筆，封存 ${r.archived} 筆。`;
    const matched = Object.keys(r.columns_matched || {});
    if (!matched.includes("customer_name") || !matched.includes("sl_payment_status")) {
      html += `<div class="import-warn">⚠ 部分欄位沒對應到（已對應：${matched.join("、") || "無"}）。
        若客戶/狀態是空的，請把實際欄名加進 config/shopline_mapping.json。</div>`;
    }
    html += `</div>`;
    $("import-result").innerHTML = html;
    refresh();
  } catch (e) {
    $("import-result").innerHTML = `<div class="import-warn">匯入失敗：${esc(e.message)}</div>`;
  }
}

// ─── 交接班 ──────────────────────────────────────────────────────────────────
async function loadHandovers() {
  const rows = await api("/api/cs/handover");
  $("ho-list").innerHTML = rows.length ? "" : '<div class="empty">尚無交班記錄</div>';
  for (const h of rows) {
    const div = document.createElement("div");
    div.className = "ho-item" + (h.acked ? " acked" : "");
    div.innerHTML = `
      <div class="ho-head">
        <span class="date">${esc(h.shift_date || "")}</span>
        <span class="muted">${esc(h.from_staff || "?")} → ${esc(h.to_staff || "?")}</span>
        ${h.acked ? '<span class="ack-badge">✓ 已接收</span>'
                  : `<button class="btn btn-sm" data-ack="${h.id}" style="margin-left:auto">我已接收</button>`}
      </div>
      ${h.watch_orders ? `<div class="ho-watch">盯：${esc(h.watch_orders)}</div>` : ""}
      ${h.note ? `<div class="ho-note">${esc(h.note)}</div>` : ""}`;
    $("ho-list").appendChild(div);
  }
  $("ho-list").querySelectorAll("[data-ack]").forEach(b =>
    b.addEventListener("click", async () => { await jpost(`/api/cs/handover/${b.dataset.ack}/ack`, {}); loadHandovers(); }));
}

async function saveHandover() {
  const note = $("ho-note").value.trim();
  const watch = $("ho-watch").value.trim();
  if (!note && !watch) { alert("至少填「要盯的單號」或「叮嚀」"); return; }
  await jpost("/api/cs/handover", {
    from_staff: $("ho-from").value.trim() || null,
    to_staff: $("ho-to").value.trim() || null,
    watch_orders: watch || null,
    note: note || null,
  });
  $("ho-note").value = ""; $("ho-watch").value = "";
  loadHandovers();
}

// ─── 分頁切換與事件綁定 ───────────────────────────────────────────────────────
function switchTab(name) {
  document.querySelectorAll(".tab").forEach(t => t.classList.toggle("active", t.dataset.tab === name));
  $("tab-board").classList.toggle("hidden", name !== "board");
  $("tab-handover").classList.toggle("hidden", name !== "handover");
  if (name === "handover") loadHandovers();
}

function bind() {
  document.querySelectorAll(".tab").forEach(t => t.addEventListener("click", () => switchTab(t.dataset.tab)));
  document.querySelectorAll(".chip").forEach(c => c.addEventListener("click", () => setView(c.dataset.view)));
  $("refresh-btn").addEventListener("click", refresh);
  $("open-import-btn").addEventListener("click", () => { $("import-result").innerHTML = ""; $("import-modal").classList.remove("hidden"); });
  $("import-close").addEventListener("click", () => $("import-modal").classList.add("hidden"));
  $("import-do").addEventListener("click", doImport);
  $("om-save").addEventListener("click", saveOrder);
  $("om-close").addEventListener("click", () => $("order-modal").classList.add("hidden"));
  $("om-archive").addEventListener("click", archiveOrder);
  $("ho-save").addEventListener("click", saveHandover);

  let t;
  $("search").addEventListener("input", e => {
    clearTimeout(t);
    searchTerm = e.target.value.trim();
    t = setTimeout(loadOrders, 250);
  });
  // 點遮罩關閉
  document.querySelectorAll(".overlay").forEach(ov =>
    ov.addEventListener("click", e => { if (e.target === ov) ov.classList.add("hidden"); }));
}

async function init() {
  bind();
  try { META = await api("/api/cs/meta"); } catch {}
  refresh();
}
init();
