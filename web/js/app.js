import * as api from "./api.js";

// ─── 分類選項（同步 categories.json）────────────────────────
const FILTER_OPTIONS = {
    color:    ["紅","粉紅","橙","黃","綠","藍綠","藍","紫","白","無色透明","黑","灰","棕"],
    category: ["戒指","項鍊","墜飾","耳環","手鍊","手鐲","胸針","其他"],
    price_band: ["< 1萬","1-3萬","3-6萬","6-10萬","10-15萬","> 15萬"],
    material: ["925銀","18k黃金","18k白金","18k玫瑰金","鉑金","其他金屬"],
    gemstone: [
        "紅寶石","藍寶石","祖母綠","坦桑石","海藍寶",
        "粉碧璽","綠碧璽","藍碧璽","西瓜碧璽",
        "紫水晶","黃水晶","煙水晶","白水晶",
        "托帕石","月光石","歐泊","橄欖石","石榴石","丹泉石",
        "青金石","珍珠","翡翠","瑪瑙","玉髓",
        "鑽石主石","其他寶石"
    ],
};

const SORT_OPTIONS = [
    { value: "random",  label: "隨機" },
    { value: "newest",  label: "最新" },
    { value: "popular", label: "最熱" },
];

const PRICE_BANDS = ["< 1萬","1-3萬","3-6萬","6-10萬","10-15萬","> 15萬"];

// ─── 狀態 ────────────────────────────────────────────────────
let state = {
    filters: {},
    page: 1,
    sort: "random",
    photos: [],
    favoritedIds: new Set(),
    similarMode: null,       // null 或 anchor photo_id
    priceBandIdx: -1,        // 手勢控制用
    loading: false,
};

// ─── DOM refs ────────────────────────────────────────────────
const grid     = document.getElementById("grid");
const lightbox = document.getElementById("lightbox");
const lightboxImg = document.getElementById("lightbox-img");
const toast    = document.getElementById("toast");

// ─── Toast ───────────────────────────────────────────────────
function showToast(msg, duration = 1500) {
    toast.textContent = msg;
    toast.classList.add("show");
    setTimeout(() => toast.classList.remove("show"), duration);
}

// ─── Skeleton loading ────────────────────────────────────────
function renderSkeleton() {
    grid.innerHTML = Array(9).fill(
        `<div class="tile skeleton"><div class="skeleton-shimmer"></div></div>`
    ).join("");
}

// ─── Empty state ─────────────────────────────────────────────
function renderEmpty(msg = "沒有符合的照片") {
    grid.innerHTML = `
        <div class="empty-state">
            <div class="empty-icon">🔍</div>
            <div class="empty-msg">${msg}</div>
            ${Object.keys(state.filters).length
                ? `<button class="empty-clear" id="empty-clear-btn">清除篩選</button>`
                : ""}
        </div>
    `;
    document.getElementById("empty-clear-btn")?.addEventListener("click", clearFilters);
}

// ─── 讀取照片 ────────────────────────────────────────────────
async function loadPhotos() {
    if (state.loading) return;
    state.loading = true;
    renderSkeleton();

    try {
        let data;
        if (state.similarMode) {
            const result = await api.findSimilar(state.similarMode, 8);
            const photos = [...result.similar];
            if (photos.length >= 4) photos.splice(4, 0, result.anchor);
            else photos.unshift(result.anchor);
            data = { photos: photos.slice(0, 9), total: 9 };
        } else {
            data = await api.listPhotos(state.filters, state.page, state.sort);
        }

        state.photos = data.photos;
        await loadFavoriteStatus();

        if (!data.photos.length) {
            renderEmpty(state.similarMode ? "找不到相似照片" : "沒有符合的照片");
        } else {
            renderGrid();
        }
    } catch (e) {
        grid.innerHTML = `
            <div class="empty-state">
                <div class="empty-icon">⚠️</div>
                <div class="empty-msg">載入失敗，請確認伺服器狀態</div>
            </div>
        `;
    } finally {
        state.loading = false;
    }
}

async function loadFavoriteStatus() {
    try {
        const data = await api.listFavorites(1);
        state.favoritedIds = new Set(data.favorites.map(f => f.photo_id));
        document.getElementById("fav-count").textContent = data.total;
    } catch (_) {}
}

// ─── 渲染 Grid ───────────────────────────────────────────────
function renderGrid() {
    grid.innerHTML = "";
    state.photos.forEach(p => {
        const tile = document.createElement("div");
        tile.className = "tile";
        if (state.favoritedIds.has(p.id)) tile.classList.add("favorited");
        tile.dataset.photoId = p.id;

        tile.innerHTML = `
            <img src="${p.micro_url}" data-thumb="${p.thumb_url}"
                 class="loading-micro" alt="" loading="lazy">
            ${p.price_band ? `<div class="price-tag">${p.price_band}</div>` : ""}
        `;

        const img = tile.querySelector("img");
        const thumbLoader = new Image();
        thumbLoader.src = p.thumb_url;
        thumbLoader.onload = () => {
            img.src = p.thumb_url;
            img.classList.replace("loading-micro", "loading-thumb");
        };

        attachGestures(tile, p);
        grid.appendChild(tile);
        api.logEvent(p.id, "view");
    });

    updateFilterPills();
    setTimeout(preloadNextPage, 500);
}

async function preloadNextPage() {
    if (state.similarMode) return;
    try {
        const next = await api.listPhotos(state.filters, state.page + 1, state.sort);
        next.photos.forEach(p => { new Image().src = p.thumb_url; });
    } catch (_) {}
}

// ─── 篩選 Pills ──────────────────────────────────────────────
function updateFilterPills() {
    document.querySelectorAll(".filter-pill[data-dim]").forEach(pill => {
        const dim = pill.dataset.dim;
        const active = !!state.filters[dim];
        pill.classList.toggle("active", active);
        const dimLabel = { color:"顏色", category:"品類", price_band:"價位",
                           material:"材質", gemstone:"寶石" };
        pill.textContent = active
            ? `${dimLabel[dim]}: ${state.filters[dim]} ✕`
            : `${dimLabel[dim]} ▾`;
    });
}

// ─── Dropdown ────────────────────────────────────────────────
let activeDropdown = null;

function openDropdown(pill, dim) {
    closeDropdown();

    const options = FILTER_OPTIONS[dim] || [];
    const current = state.filters[dim] || null;

    const menu = document.createElement("div");
    menu.className = "dropdown-menu";

    options.forEach(opt => {
        const item = document.createElement("div");
        item.className = "dropdown-item" + (opt === current ? " selected" : "");
        item.textContent = opt;
        item.addEventListener("click", e => {
            e.stopPropagation();
            if (opt === current) {
                delete state.filters[dim];
            } else {
                state.filters[dim] = opt;
            }
            state.page = 1;
            state.similarMode = null;
            closeDropdown();
            loadPhotos();
        });
        menu.appendChild(item);
    });

    // 定位在 pill 下方
    const rect = pill.getBoundingClientRect();
    menu.style.top  = (rect.bottom + 4) + "px";
    menu.style.left = Math.min(rect.left, window.innerWidth - 200) + "px";

    document.body.appendChild(menu);
    activeDropdown = menu;
}

function closeDropdown() {
    activeDropdown?.remove();
    activeDropdown = null;
}

document.querySelectorAll(".filter-pill[data-dim]").forEach(pill => {
    pill.addEventListener("click", e => {
        e.stopPropagation();
        if (activeDropdown) { closeDropdown(); return; }
        openDropdown(pill, pill.dataset.dim);
    });
});

document.addEventListener("click", () => closeDropdown());

// ─── 清除篩選 ────────────────────────────────────────────────
function clearFilters() {
    state.filters = {};
    state.page = 1;
    state.priceBandIdx = -1;
    state.similarMode = null;
    closeDropdown();
    loadPhotos();
}

document.getElementById("clear-filter").addEventListener("click", clearFilters);

// ─── Sort 按鈕 ───────────────────────────────────────────────
const sortBtn = document.getElementById("sort-btn");
let sortMenuOpen = false;

sortBtn?.addEventListener("click", e => {
    e.stopPropagation();
    if (sortMenuOpen) { closeSortMenu(); return; }
    openSortMenu();
});

function openSortMenu() {
    closeDropdown();
    const menu = document.createElement("div");
    menu.className = "dropdown-menu sort-menu";
    menu.id = "sort-menu";

    SORT_OPTIONS.forEach(opt => {
        const item = document.createElement("div");
        item.className = "dropdown-item" + (opt.value === state.sort ? " selected" : "");
        item.textContent = opt.label;
        item.addEventListener("click", e => {
            e.stopPropagation();
            state.sort = opt.value;
            state.page = 1;
            state.similarMode = null;
            closeSortMenu();
            updateSortBtn();
            loadPhotos();
        });
        menu.appendChild(item);
    });

    const rect = sortBtn.getBoundingClientRect();
    menu.style.bottom = (window.innerHeight - rect.top + 4) + "px";
    menu.style.left   = (rect.left - 60) + "px";
    document.body.appendChild(menu);
    sortMenuOpen = true;
}

function closeSortMenu() {
    document.getElementById("sort-menu")?.remove();
    sortMenuOpen = false;
}

function updateSortBtn() {
    if (!sortBtn) return;
    const label = SORT_OPTIONS.find(o => o.value === state.sort)?.label || "排序";
    sortBtn.textContent = `⚙️ ${label}`;
}

document.addEventListener("click", () => closeSortMenu());

// ─── 手勢（Lightbox）────────────────────────────────────────
function attachGestures(tile, photo) {
    const hammer = new Hammer(tile);
    hammer.get("doubletap").set({ taps: 2 });
    hammer.get("press").set({ time: 500 });

    hammer.on("tap", () => {
        showLightbox(photo);
        api.logEvent(photo.id, "click");
    });

    hammer.on("press", async () => {
        if (state.favoritedIds.has(photo.id)) {
            await api.removeFavorite(photo.id);
            state.favoritedIds.delete(photo.id);
            tile.classList.remove("favorited");
            showToast("已移除喜愛");
            api.logEvent(photo.id, "unfavorite");
        } else {
            await api.addFavorite(photo.id);
            state.favoritedIds.add(photo.id);
            tile.classList.add("favorited");
            showToast("已加入喜愛 ❤");
            api.logEvent(photo.id, "favorite");
        }
        loadFavoriteStatus();
    });
}

// ─── Lightbox ────────────────────────────────────────────────
let lightboxPhotoId  = null;
let lightboxOpenedAt = null;

function showLightbox(photo) {
    lightboxImg.src = photo.thumb_url;
    lightboxImg.classList.add("loading-thumb");
    lightbox.classList.add("show");
    lightboxPhotoId  = photo.id;
    lightboxOpenedAt = Date.now();

    const fullLoader = new Image();
    fullLoader.src = photo.full_url;
    fullLoader.onload = () => {
        if (lightboxPhotoId === photo.id) {
            lightboxImg.src = photo.full_url;
            lightboxImg.classList.remove("loading-thumb");
        }
    };
}

function hideLightbox() {
    if (lightboxPhotoId && lightboxOpenedAt) {
        api.logEvent(lightboxPhotoId, "dwell", Date.now() - lightboxOpenedAt);
    }
    lightbox.classList.remove("show");
    lightboxImg.classList.remove("loading-thumb");
    lightboxPhotoId = null;
}

const lightboxHammer = new Hammer(lightbox);
lightboxHammer.get("doubletap").set({ taps: 2 });
lightboxHammer.on("tap", () => hideLightbox());
lightboxHammer.on("doubletap", async () => {
    if (!lightboxPhotoId) return;
    if (!state.favoritedIds.has(lightboxPhotoId)) {
        await api.addFavorite(lightboxPhotoId);
        state.favoritedIds.add(lightboxPhotoId);
        api.logEvent(lightboxPhotoId, "favorite");
    }
    showToast("找相似中...");
    state.similarMode = lightboxPhotoId;
    hideLightbox();
    await loadPhotos();
    showToast("已切換到相似圖");
});

// ─── Grid 手勢（翻頁 + 價位）────────────────────────────────
const gridHammer = new Hammer(grid);
gridHammer.get("swipe").set({ direction: Hammer.DIRECTION_ALL, threshold: 50 });

gridHammer.on("swipeleft", () => {
    state.similarMode = null;
    state.page += 1;
    loadPhotos();
});
gridHammer.on("swiperight", () => {
    state.similarMode = null;
    if (state.page > 1) { state.page -= 1; loadPhotos(); }
});
gridHammer.on("swipeup", () => {
    state.similarMode = null;
    if (state.priceBandIdx < PRICE_BANDS.length - 1) {
        state.priceBandIdx++;
        state.filters.price_band = PRICE_BANDS[state.priceBandIdx];
        state.page = 1;
        showToast(`價位：${state.filters.price_band}`);
        loadPhotos();
    }
});
gridHammer.on("swipedown", () => {
    state.similarMode = null;
    if (state.priceBandIdx > 0) {
        state.priceBandIdx--;
        state.filters.price_band = PRICE_BANDS[state.priceBandIdx];
        state.page = 1;
        showToast(`價位：${state.filters.price_band}`);
        loadPhotos();
    } else if (state.priceBandIdx === 0) {
        state.priceBandIdx = -1;
        delete state.filters.price_band;
        state.page = 1;
        showToast("價位：全部");
        loadPhotos();
    }
});

// ─── 初始化 ──────────────────────────────────────────────────
updateSortBtn();
loadPhotos();
