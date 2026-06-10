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

let META = { track_statuses: [], risk_types: [], product_types: {} };
let currentView = "active";
let searchTerm = "";
let currentOrder = null;
let noteWho = "staff";

// 操作者身分（記在這台瀏覽器，動作會記進購物旅程）
function me() { return ($("whoami").value || "").trim(); }

// ─── SHOPLINE 連結 ────────────────────────────────────────────────────────────
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
    title="到 SHOPLINE 後台搜尋這張單" onclick="event.stopPropagation()">${label || "🔗 SHOPLINE"}</a>`;
}

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
    <button class="dash-card c-payment ${currentView === "duesoon" ? "active" : ""}" data-view="duesoon">
      <div class="num">${d.due_soon}</div><div class="label">🟡 快到期(${META.due_soon_days || 3}天內)</div></button>`;
  $("dash").querySelectorAll(".dash-card").forEach(c =>
    c.addEventListener("click", () => setView(c.dataset.view)));
  if (d.last_import) $("last-import").textContent = "最後更新：" + d.last_import.replace("T", " ").slice(0, 16);
}

function statusPill(s) { return `<span class="pill pill-status">${esc(s || "—")}</span>`; }
function typeBadge(t) {
  const cls = t === "訂製" ? "tb-custom" : "tb-std";
  return `<span class="type-badge ${cls}">${esc(t || "規格")}</span>`;
}
// 出貨期限欄：日期 + 剩餘天數（逾期紅、快到期橙）
function dueCell(o) {
  if (o.track_status === "已完成") return `<span class="muted">已完成</span>`;
  if (!o.due_ship_date) return `<span class="muted">—</span>`;
  const dl = o.days_left;
  let tag = "";
  if (dl != null) {
    if (dl < 0) tag = `<span class="due-tag due-late">逾期${-dl}天</span>`;
    else if (o.due_soon) tag = `<span class="due-tag due-soon">剩${dl}天</span>`;
    else tag = `<span class="due-tag">剩${dl}天</span>`;
  }
  return `<div class="due-wrap"><span class="due-date">${esc(o.due_ship_date)}</span>${tag}</div>`;
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
    tr.className = o.is_risk ? "row-risk" : (o.ship_overdue ? "row-overdue" : "");
    const flags = [];
    if (o.is_risk) flags.push(`<span class="flag flag-risk">🔴 ${esc(o.risk_type || "異常")}</span>`);
    if (o.ship_overdue) flags.push(`<span class="flag flag-overdue">🟠 逾期</span>`);
    else if (o.due_soon) flags.push(`<span class="flag flag-soon">🟡 快到期</span>`);
    tr.innerHTML = `
      <td class="ordno">${esc(o.order_number)}${shoplineLink(o.order_number, "🔗")}</td>
      <td class="cust">${esc(o.customer_name || "—")}</td>
      <td>${typeBadge(o.product_type)}</td>
      <td class="hide-sm truncate">${esc(o.item_summary || "—")}</td>
      <td>${statusPill(o.track_status)}</td>
      <td>${dueCell(o)}</td>
      <td class="hide-sm ${o.last_handler ? "" : "muted"}">${esc(o.last_handler || "—")}</td>
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

// ─── 訂單詳情 / 進度 ──────────────────────────────────────────────────────────
function fillSelect(sel, options, value) {
  sel.innerHTML = options.map(o => `<option value="${esc(o)}"${o === value ? " selected" : ""}>${esc(o)}</option>`).join("");
}

function renderTimeline(events) {
  if (!events || !events.length) {
    $("om-timeline").innerHTML = `<div class="tl-empty">還沒有任何記錄</div>`;
    return;
  }
  $("om-timeline").innerHTML = events.map(e => {
    const cls = e.actor_type === "customer" ? "tl-cust" : (e.actor_type === "system" ? "tl-sys" : "tl-staff");
    const icon = e.actor_type === "customer" ? "🗣" : (e.actor_type === "system" ? "⚙" : (e.kind === "risk" ? "🔴" : "✔"));
    return `<div class="tl-item ${cls}">
      <div class="tl-dot">${icon}</div>
      <div class="tl-body">
        <div class="tl-meta"><span class="tl-time">${esc(e.occurred_at || "")}</span>
          <span class="tl-actor">${esc(e.actor || "")}</span></div>
        <div class="tl-text">${esc(e.content || "")}</div>
      </div></div>`;
  }).join("");
}

async function openOrder(id) {
  const o = await api(`/api/cs/orders/${id}`);
  currentOrder = o;
  $("om-title").innerHTML = `${esc(o.customer_name || "（無收件人）")}
    <span class="om-ordno">${esc(o.order_number)}</span>
    ${shoplineLink(o.order_number, "🔗 到 SHOPLINE 叫單")}`;
  $("om-sub").textContent = [o.phone, o.item_summary, o.total ? "NT$" + o.total : ""].filter(Boolean).join(" · ");

  // 出貨期限提示條
  const bar = $("om-duebar");
  if (o.track_status === "已完成") {
    bar.className = "om-due-bar done";
    bar.textContent = `已完成${o.completed_at ? "（" + o.completed_at + "）" : ""}，退換貨期滿後自動歸檔`;
  } else if (o.due_ship_date) {
    const dl = o.days_left;
    bar.className = "om-due-bar " + (dl < 0 ? "late" : (o.due_soon ? "soon" : "ok"));
    const txt = dl < 0 ? `已逾期 ${-dl} 天` : `還剩 ${dl} 天`;
    bar.textContent = `${o.product_type}・出貨期限 ${o.due_ship_date}（${txt}）`;
  } else { bar.className = "om-due-bar"; bar.textContent = ""; }

  fillSelect($("om-ptype"), Object.keys(META.product_types || { 規格: 14, 訂製: 45 }), o.product_type || "規格");
  fillSelect($("om-status"), META.track_statuses, o.track_status);
  fillSelect($("om-risktype"), ["", ...META.risk_types], o.risk_type || "");
  $("om-owner").value = o.owner || "";
  $("om-next").value = o.next_action || "";
  $("om-due").value = o.due_date || "";
  $("om-risk").checked = !!o.is_risk;
  $("om-notes").value = o.notes || "";

  renderTimeline(o.timeline);
  $("om-noteinput").value = "";

  const raw = o.raw || {};
  $("om-raw").innerHTML = Object.keys(raw).length
    ? Object.entries(raw).filter(([, v]) => v !== "" && v != null)
        .map(([k, v]) => `<div><b>${esc(k)}</b>: ${esc(v)}</div>`).join("")
    : '<span class="muted">（此單非由報表匯入）</span>';
  $("om-rawwrap").classList.toggle("hidden", !Object.keys(raw).length);
  $("order-modal").classList.remove("hidden");
}

async function saveOrder() {
  if (!currentOrder) return;
  const o = await jput(`/api/cs/orders/${currentOrder.id}`, {
    track_status: $("om-status").value,
    product_type: $("om-ptype").value,
    owner: $("om-owner").value.trim(),
    next_action: $("om-next").value.trim(),
    due_date: $("om-due").value || null,
    is_risk: $("om-risk").checked,
    risk_type: $("om-risktype").value || null,
    notes: $("om-notes").value.trim(),
    handler: me() || null,
  });
  currentOrder = o;
  renderTimeline(o.timeline);
  $("order-modal").classList.add("hidden");
  refresh();
}

async function addNote() {
  if (!currentOrder) return;
  const content = $("om-noteinput").value.trim();
  if (!content) return;
  const actor = noteWho === "customer"
    ? (currentOrder.customer_name || "客人")
    : (me() || "員工");
  const r = await jpost(`/api/cs/orders/${currentOrder.id}/events`, {
    content, actor, actor_type: noteWho,
  });
  $("om-noteinput").value = "";
  renderTimeline(r.timeline);
}

async function archiveOrder() {
  if (!currentOrder) return;
  if (!confirm("把這張單移入封存資料庫？（之後可在「已封存」分類查到）")) return;
  await jput(`/api/cs/orders/${currentOrder.id}`, { archived: true, handler: me() || null });
  $("order-modal").classList.add("hidden");
  refresh();
}

// ─── 客人歷史 ────────────────────────────────────────────────────────────────
async function showHistory() {
  if (!currentOrder) return;
  const cid = currentOrder.customer_id;
  const params = new URLSearchParams({ exclude_id: currentOrder.id });
  if (cid) params.set("customer_id", cid);
  else if (currentOrder.phone) params.set("phone", currentOrder.phone);
  else { alert("這張單沒有顧客ID或電話，無法查歷史"); return; }

  const rows = await api("/api/cs/customers/history?" + params);
  $("hist-title").textContent = `${currentOrder.customer_name || "客人"} 的其他訂單（${rows.length}）`;
  $("hist-list").innerHTML = rows.length ? rows.map(o => `
    <div class="hist-item">
      <div class="hist-top">
        <span class="ordno">${esc(o.order_number)}</span>
        ${typeBadge(o.product_type)} ${statusPill(o.track_status)}
        ${o.is_risk ? '<span class="flag flag-risk">🔴異常</span>' : ""}
        ${o.archived ? '<span class="muted">已封存</span>' : ""}
      </div>
      <div class="hist-sub muted">${esc(o.order_date || "")}・${esc(o.item_summary || "")}
        ${o.last_handler ? "・最後處理：" + esc(o.last_handler) : ""}</div>
    </div>`).join("") : '<div class="empty">這位客人沒有其他訂單</div>';
  $("history-modal").classList.remove("hidden");
}

// ─── 匯入 ────────────────────────────────────────────────────────────────────
async function doImport() {
  const f = $("import-file").files[0];
  if (!f) { alert("請先選擇報表檔案（.xls 或 .csv）"); return; }
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
    from_staff: ($("ho-from").value.trim() || me()) || null,
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
  $("om-addnote").addEventListener("click", addNote);
  $("om-history").addEventListener("click", showHistory);
  $("hist-close").addEventListener("click", () => $("history-modal").classList.add("hidden"));
  document.querySelectorAll(".who-toggle .wt").forEach(b =>
    b.addEventListener("click", () => {
      noteWho = b.dataset.who;
      document.querySelectorAll(".who-toggle .wt").forEach(x => x.classList.toggle("active", x === b));
    }));
  $("ho-save").addEventListener("click", saveHandover);

  // 記住操作者
  const saved = localStorage.getItem("cs_whoami");
  if (saved) $("whoami").value = saved;
  $("whoami").addEventListener("change", () => localStorage.setItem("cs_whoami", me()));

  let t;
  $("search").addEventListener("input", e => {
    clearTimeout(t);
    searchTerm = e.target.value.trim();
    t = setTimeout(loadOrders, 250);
  });
  document.querySelectorAll(".overlay").forEach(ov =>
    ov.addEventListener("click", e => { if (e.target === ov) ov.classList.add("hidden"); }));
}

async function init() {
  bind();
  try { META = await api("/api/cs/meta"); } catch {}
  refresh();
}
init();
