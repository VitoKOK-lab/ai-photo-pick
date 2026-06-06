const BASE = "";

async function get(path) {
    const r = await fetch(BASE + path);
    return r.json();
}

// ─── 狀態 ───────────────────────────────────────────────
let currentDays = 7;
let currentSort = "popular";
let currentDim  = "category";

// ─── 總覽 ────────────────────────────────────────────────
async function loadOverview() {
    const d = await get("/api/stats/overview");
    set("card-photos",    fmt(d.total_photos));
    set("card-views",     fmt(d.total_views));
    set("card-favorites", fmt(d.total_favorites));
    set("card-locks",     fmt(d.total_locks));
    set("card-dwell",     d.avg_dwell_sec);
    set("card-sessions",  fmt(d.total_sessions));
}

function set(id, val) {
    document.querySelector(`#${id} .stat-value`).textContent = val;
}

function fmt(n) {
    if (n >= 10000) return (n / 10000).toFixed(1) + "萬";
    return n.toLocaleString();
}

// ─── 每日趨勢（純 canvas，不依賴第三方） ──────────────
async function loadDaily() {
    const d = await get(`/api/stats/daily?days=${currentDays}`);
    const el = document.getElementById("daily-empty");
    const canvas = document.getElementById("daily-chart");

    if (!d.data.length) {
        el.style.display = "block";
        canvas.style.display = "none";
        return;
    }
    el.style.display = "none";
    canvas.style.display = "block";
    drawBarChart(canvas, d.data);
}

function drawBarChart(canvas, data) {
    const dpr = window.devicePixelRatio || 1;
    const W = canvas.parentElement.clientWidth;
    const H = 180;
    canvas.width  = W * dpr;
    canvas.height = H * dpr;
    canvas.style.width  = W + "px";
    canvas.style.height = H + "px";

    const ctx = canvas.getContext("2d");
    ctx.scale(dpr, dpr);

    const PAD = { top: 16, right: 8, bottom: 36, left: 36 };
    const chartW = W - PAD.left - PAD.right;
    const chartH = H - PAD.top - PAD.bottom;

    const views     = data.map(d => d.views);
    const favorites = data.map(d => d.favorites);
    const maxVal    = Math.max(...views, ...favorites, 1);

    const barW   = Math.max(2, chartW / data.length - 2);
    const gap    = chartW / data.length;

    ctx.clearRect(0, 0, W, H);

    // 格線
    ctx.strokeStyle = "#eee";
    ctx.lineWidth = 1;
    for (let i = 0; i <= 4; i++) {
        const y = PAD.top + chartH * (1 - i / 4);
        ctx.beginPath();
        ctx.moveTo(PAD.left, y);
        ctx.lineTo(W - PAD.right, y);
        ctx.stroke();
        ctx.fillStyle = "#aaa";
        ctx.font = "10px sans-serif";
        ctx.textAlign = "right";
        ctx.fillText(Math.round(maxVal * i / 4), PAD.left - 4, y + 3);
    }

    data.forEach((d, i) => {
        const x = PAD.left + i * gap + gap / 2 - barW / 2;

        // views bar
        const vh = (d.views / maxVal) * chartH;
        ctx.fillStyle = "#6ca0dc";
        ctx.fillRect(x, PAD.top + chartH - vh, barW * 0.55, vh);

        // favorites bar（疊在旁邊）
        const fh = (d.favorites / maxVal) * chartH;
        ctx.fillStyle = "#e88";
        ctx.fillRect(x + barW * 0.55, PAD.top + chartH - fh, barW * 0.45, fh);

        // x label（每隔幾格才顯示）
        if (i % Math.ceil(data.length / 8) === 0) {
            ctx.fillStyle = "#888";
            ctx.font = "9px sans-serif";
            ctx.textAlign = "center";
            ctx.fillText(d.day.slice(5), PAD.left + i * gap + gap / 2, H - 6);
        }
    });

    // 圖例
    ctx.fillStyle = "#6ca0dc";
    ctx.fillRect(PAD.left, H - 28, 10, 10);
    ctx.fillStyle = "#555";
    ctx.font = "11px sans-serif";
    ctx.textAlign = "left";
    ctx.fillText("瀏覽", PAD.left + 14, H - 19);

    ctx.fillStyle = "#e88";
    ctx.fillRect(PAD.left + 50, H - 28, 10, 10);
    ctx.fillStyle = "#555";
    ctx.fillText("收藏", PAD.left + 64, H - 19);
}

// ─── 熱門照片 ─────────────────────────────────────────────
async function loadTopPhotos() {
    const d = await get(`/api/stats/top-photos?sort_by=${currentSort}&limit=20`);
    const grid  = document.getElementById("top-photos-grid");
    const empty = document.getElementById("top-empty");

    if (!d.photos.length) {
        empty.style.display = "block";
        grid.innerHTML = "";
        return;
    }
    empty.style.display = "none";

    const metricLabel = { popular: "綜合分", views: "瀏覽", favorites: "收藏", locks: "Lock", dwell: "停留秒" };
    const metricFn = {
        popular:   p => p.view_count + p.favorite_count * 3 + p.lock_count * 5,
        views:     p => p.view_count,
        favorites: p => p.favorite_count,
        locks:     p => p.lock_count,
        dwell:     p => p.avg_dwell_sec + "s",
    };

    grid.innerHTML = d.photos.map((p, i) => `
        <div class="top-photo-row">
            <span class="rank">${i + 1}</span>
            <img src="${p.micro_url}" alt="" onerror="this.style.display='none'">
            <div class="top-photo-info">
                <div class="top-photo-tags">
                    ${p.category || ""}
                    ${p.color ? "· " + p.color : ""}
                    ${p.price_band ? "· " + p.price_band : ""}
                </div>
                <div class="top-photo-metrics">
                    👁 ${p.view_count} &nbsp;
                    ❤ ${p.favorite_count} &nbsp;
                    📌 ${p.lock_count} &nbsp;
                    ⏱ ${p.avg_dwell_sec}s
                </div>
            </div>
            <div class="top-photo-score">${metricFn[currentSort](p)}</div>
        </div>
    `).join("");
}

// ─── 維度分布 ─────────────────────────────────────────────
async function loadDimension() {
    const d = await get(`/api/stats/by-dimension?dim=${currentDim}`);
    const bars  = document.getElementById("dim-bars");
    const empty = document.getElementById("dim-empty");

    if (!d.items.length) {
        empty.style.display = "block";
        bars.innerHTML = "";
        return;
    }
    empty.style.display = "none";

    const maxViews = Math.max(...d.items.map(i => i.views), 1);

    bars.innerHTML = d.items.map(item => `
        <div class="dim-row">
            <div class="dim-label">${item.label}</div>
            <div class="dim-bar-wrap">
                <div class="dim-bar" style="width:${Math.max(2, item.views / maxViews * 100)}%"></div>
            </div>
            <div class="dim-nums">
                <span title="照片">${item.photo_count}</span>
                <span title="瀏覽" class="muted">👁${item.views}</span>
                <span title="收藏" class="muted">❤${item.favorites}</span>
            </div>
        </div>
    `).join("");
}

// ─── 備份狀態 ────────────────────────────────────────────────
async function loadBackupStatus() {
    const d = await get("/api/backup/status");
    const info = document.getElementById("backup-info");
    const snaps = document.getElementById("backup-snapshots");

    if (d.running) {
        info.innerHTML = `<span class="backup-running">⏳ 備份進行中...</span>`;
    } else if (d.last_backup) {
        const dt = new Date(d.last_backup).toLocaleString("zh-TW");
        const ok = d.last_results && Object.values(d.last_results).every(v => v !== false);
        info.innerHTML = `<span class="${ok ? "backup-ok" : "backup-warn"}">
            ${ok ? "✓" : "⚠"} 上次備份：${dt}
        </span>`;
    } else {
        info.innerHTML = `<span class="backup-warn">尚未執行過備份</span>`;
    }

    if (d.local_snapshots?.length) {
        snaps.innerHTML = `<div class="snap-label">本地快照：</div>` +
            d.local_snapshots.map(s =>
                `<span class="snap-item">${s.filename.replace("jewelry_","").replace(".sqlite","")} (${s.size_mb}MB)</span>`
            ).join(" ");
    }
}

async function triggerBackup(dbOnly) {
    const btn = dbOnly ? document.getElementById("backup-db-btn") : document.getElementById("backup-full-btn");
    btn.disabled = true;
    btn.textContent = "⏳ 啟動中...";
    try {
        await fetch(`/api/backup/trigger?db_only=${dbOnly}`, { method: "POST" });
        setTimeout(loadBackupStatus, 1500);
    } finally {
        btn.disabled = false;
        btn.textContent = dbOnly ? "💾 僅備份 DB" : "☁ 完整備份";
    }
}

document.getElementById("backup-full-btn")?.addEventListener("click", () => triggerBackup(false));
document.getElementById("backup-db-btn")?.addEventListener("click",   () => triggerBackup(true));

// ─── 初始化 ───────────────────────────────────────────────
function bindTabs(selector, onChange) {
    document.querySelectorAll(selector).forEach(btn => {
        btn.addEventListener("click", () => {
            document.querySelectorAll(selector).forEach(b => b.classList.remove("active"));
            btn.classList.add("active");
            onChange(btn.dataset);
        });
    });
}

async function loadAll() {
    await Promise.all([loadOverview(), loadDaily(), loadTopPhotos(), loadDimension(), loadBackupStatus()]);
}

bindTabs(".period-btn", ({ days }) => {
    currentDays = +days;
    loadDaily();
});

bindTabs(".sort-btn", ({ sort }) => {
    currentSort = sort;
    loadTopPhotos();
});

bindTabs(".dim-btn", ({ dim }) => {
    currentDim = dim;
    loadDimension();
});

loadAll();
