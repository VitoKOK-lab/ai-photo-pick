const BASE = "";
let currentPage = 1;
let currentFilters = {};

// ─── 工具 ──────────────────────────────────────────────────
async function api(path, opts = {}) {
    const r = await fetch(BASE + path, opts);
    return r.json();
}

function fmtPrice(n) {
    if (!n) return "—";
    return n.toLocaleString() + " 元";
}

function fmtPriceShort(n) {
    if (!n) return "—";
    if (n >= 10000) return (n / 10000).toFixed(1) + "萬";
    return n.toLocaleString();
}

// ─── 總覽統計 ────────────────────────────────────────────
async function loadStats() {
    const d = await api("/api/quotes/stats");
    document.getElementById("s-total").textContent = d.total_quotes ?? "0";
    document.getElementById("s-min").textContent = fmtPriceShort(d.overall_min);
    document.getElementById("s-max").textContent = fmtPriceShort(d.overall_max);
    document.getElementById("s-avg").textContent = fmtPriceShort(d.overall_avg);
}

// ─── 報價列表 ────────────────────────────────────────────
async function loadQuotes(reset = true) {
    if (reset) currentPage = 1;
    const params = new URLSearchParams({ page: currentPage });
    if (currentFilters.material) params.set("material", currentFilters.material);
    if (currentFilters.gemstone) params.set("gemstone", currentFilters.gemstone);

    const d = await api(`/api/quotes?${params}`);
    const tbody = document.getElementById("quotes-tbody");
    const empty = document.getElementById("quotes-empty");
    const loadMore = document.getElementById("load-more");

    if (reset) tbody.innerHTML = "";

    if (!d.quotes.length && reset) {
        empty.style.display = "block";
        loadMore.style.display = "none";
        return;
    }
    empty.style.display = "none";

    d.quotes.forEach(q => {
        const tr = document.createElement("tr");
        tr.innerHTML = `
            <td class="desc-cell" title="${q.description}">${q.description}</td>
            <td>${q.material || "—"}</td>
            <td>${q.gemstone || "—"}</td>
            <td>${q.gemstone_origin || "—"}</td>
            <td class="price-cell">${fmtPrice(q.final_price)}</td>
            <td>${q.quote_date || "—"}</td>
            <td><button class="del-btn" data-id="${q.id}">✕</button></td>
        `;
        tbody.appendChild(tr);
    });

    loadMore.style.display = d.has_more ? "block" : "none";
}

document.getElementById("quotes-tbody").addEventListener("click", async e => {
    const btn = e.target.closest(".del-btn");
    if (!btn) return;
    if (!confirm("確定刪除這筆報價？")) return;
    await api(`/api/quotes/${btn.dataset.id}`, { method: "DELETE" });
    await Promise.all([loadStats(), loadQuotes()]);
});

document.getElementById("load-more").addEventListener("click", () => {
    currentPage++;
    loadQuotes(false);
});

document.getElementById("filter-apply").addEventListener("click", () => {
    currentFilters.material = document.getElementById("f-material").value;
    currentFilters.gemstone = document.getElementById("f-gemstone").value;
    loadQuotes();
});

// ─── 推估工具 ────────────────────────────────────────────
document.getElementById("est-btn").addEventListener("click", async () => {
    const material = document.getElementById("est-material").value;
    const gemstone = document.getElementById("est-gemstone").value;
    if (!material && !gemstone) {
        alert("請至少選一個材質或寶石");
        return;
    }
    const params = new URLSearchParams();
    if (material) params.set("material", material);
    if (gemstone) params.set("gemstone", gemstone);

    const d = await api(`/api/quotes/estimate?${params}`, { method: "POST" });
    const el = document.getElementById("est-result");
    el.style.display = "block";

    if (!d.estimated) {
        el.className = "estimate-result warn";
        el.innerHTML = `⚠ ${d.message}`;
    } else {
        el.className = "estimate-result ok";
        el.innerHTML = `
            <strong>推估區間：</strong>
            ${fmtPrice(d.price_estimate_low)} ～ ${fmtPrice(d.price_estimate_high)}
            &nbsp;（${d.price_band}）<br>
            <small>依據：${d.price_source}，樣本數 ${d.sample_count} 筆</small>
        `;
    }
});

// ─── 批次推估 ────────────────────────────────────────────
document.getElementById("batch-btn").addEventListener("click", async () => {
    const min = document.getElementById("min-samples").value;
    if (!confirm(`確定對所有未定價照片執行批次推估（最少樣本 ${min} 筆）？`)) return;

    document.getElementById("batch-btn").disabled = true;
    const d = await api(`/api/quotes/batch-estimate?min_samples=${min}`, { method: "POST" });
    document.getElementById("batch-btn").disabled = false;

    const el = document.getElementById("batch-result");
    el.style.display = "block";
    el.className = "batch-result ok";
    el.innerHTML = `✓ 更新 ${d.updated} 張，跳過 ${d.skipped} 張（樣本不足或已定價），共 ${d.total} 張待處理`;
});

// ─── 新增 Modal ──────────────────────────────────────────
const modal = document.getElementById("modal");

document.getElementById("add-btn").addEventListener("click", () => {
    modal.style.display = "flex";
});

document.getElementById("modal-cancel").addEventListener("click", () => {
    modal.style.display = "none";
});

modal.addEventListener("click", e => {
    if (e.target === modal) modal.style.display = "none";
});

document.getElementById("modal-save").addEventListener("click", async () => {
    const desc  = document.getElementById("f-desc").value.trim();
    const price = parseInt(document.getElementById("f-price").value);
    if (!desc || !price || price <= 0) {
        alert("描述和金額為必填");
        return;
    }

    await api("/api/quotes", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
            description:     desc,
            final_price:     price,
            material:        document.getElementById("f-mat").value || null,
            gemstone:        document.getElementById("f-gem").value || null,
            gemstone_origin: document.getElementById("f-origin").value.trim() || null,
            quote_date:      document.getElementById("f-date").value || null,
            notes:           document.getElementById("f-notes").value.trim() || null,
        }),
    });

    modal.style.display = "none";
    // 清空表單
    ["f-desc","f-price","f-origin","f-date","f-notes"].forEach(id => {
        document.getElementById(id).value = "";
    });
    ["f-mat","f-gem"].forEach(id => {
        document.getElementById(id).selectedIndex = 0;
    });

    await Promise.all([loadStats(), loadQuotes()]);
});

// ─── 初始化 ──────────────────────────────────────────────
Promise.all([loadStats(), loadQuotes()]);
