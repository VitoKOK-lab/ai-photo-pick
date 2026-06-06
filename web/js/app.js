import * as api from "./api.js";

let state = {
    filters: {},
    page: 1,
    photos: [],
    favoritedIds: new Set(),
    priceBands: ["< 1萬", "1-3萬", "3-6萬", "6-10萬", "10-15萬", "> 15萬"],
    currentPriceBandIdx: -1,  // -1 表示無篩選
    similarMode: null,  // null 或 anchor photo_id
};

const grid = document.getElementById("grid");
const lightbox = document.getElementById("lightbox");
const lightboxImg = document.getElementById("lightbox-img");
const toast = document.getElementById("toast");

function showToast(msg) {
    toast.textContent = msg;
    toast.classList.add("show");
    setTimeout(() => toast.classList.remove("show"), 1500);
}

async function loadPhotos() {
    let data;
    if (state.similarMode) {
        const result = await api.findSimilar(state.similarMode, 8);
        // anchor 放中間（index 4）
        const photos = [...result.similar];
        if (photos.length >= 4) {
            photos.splice(4, 0, result.anchor);
        } else {
            photos.unshift(result.anchor);
        }
        data = { photos: photos.slice(0, 9), total: 9 };
    } else {
        data = await api.listPhotos(state.filters, state.page);
    }
    state.photos = data.photos;
    await loadFavoriteStatus();
    renderGrid();
}

async function loadFavoriteStatus() {
    const data = await api.listFavorites(1);
    state.favoritedIds = new Set(data.favorites.map(f => f.photo_id));
    document.getElementById("fav-count").textContent = data.total;
}

function renderGrid() {
    grid.innerHTML = "";
    state.photos.forEach(p => {
        const tile = document.createElement("div");
        tile.className = "tile";
        if (state.favoritedIds.has(p.id)) tile.classList.add("favorited");
        tile.dataset.photoId = p.id;

        // 兩階段載入：micro（10KB 模糊）→ thumb（清晰）
        tile.innerHTML = `
            <img src="${p.micro_url}" data-thumb="${p.thumb_url}"
                 class="loading-micro" alt="" loading="lazy">
            <div class="price-tag">${p.price_band || ""}</div>
        `;

        const img = tile.querySelector("img");
        const thumbLoader = new Image();
        thumbLoader.src = p.thumb_url;
        thumbLoader.onload = () => {
            img.src = p.thumb_url;
            img.classList.remove("loading-micro");
            img.classList.add("loading-thumb");
        };

        attachGestures(tile, p);
        grid.appendChild(tile);

        api.logEvent(p.id, "view");
    });

    // 渲染完成後 500ms，背景預載下一頁
    setTimeout(preloadNextPage, 500);
}

async function preloadNextPage() {
    if (state.similarMode) return;  // 相關性模式不預載
    try {
        const nextData = await api.listPhotos(state.filters, state.page + 1);
        nextData.photos.forEach(p => {
            const preload = new Image();
            preload.src = p.thumb_url;
        });
    } catch (e) {
        // 靜默 fallback
    }
}

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
            showToast("已移除喜愛");
            api.logEvent(photo.id, "unfavorite");
        } else {
            await api.addFavorite(photo.id);
            state.favoritedIds.add(photo.id);
            showToast("已加入喜愛 ❤");
            api.logEvent(photo.id, "favorite");
        }
        tile.classList.toggle("favorited");
        loadFavoriteStatus();
    });
}

let lightboxPhotoId = null;
let lightboxOpenedAt = null;

function showLightbox(photo) {
    // thumb 多半已快取，瞬間顯示帶輕微模糊
    lightboxImg.src = photo.thumb_url;
    lightboxImg.classList.add("loading-thumb");
    lightbox.classList.add("show");
    lightboxPhotoId = photo.id;
    lightboxOpenedAt = Date.now();

    // 背景載 full，載完去模糊
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
        const dwell = Date.now() - lightboxOpenedAt;
        api.logEvent(lightboxPhotoId, "dwell", dwell);
    }
    lightbox.classList.remove("show");
    lightboxImg.classList.remove("loading-thumb");
    lightboxPhotoId = null;
}

// Lightbox 手勢
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

// Grid 手勢
const gridHammer = new Hammer(grid);
gridHammer.get("swipe").set({ direction: Hammer.DIRECTION_ALL, threshold: 50 });

gridHammer.on("swipeleft", () => {
    state.similarMode = null;
    state.page += 1;
    loadPhotos();
});

gridHammer.on("swiperight", () => {
    state.similarMode = null;
    if (state.page > 1) {
        state.page -= 1;
        loadPhotos();
    }
});

gridHammer.on("swipeup", () => {
    state.similarMode = null;
    if (state.currentPriceBandIdx < state.priceBands.length - 1) {
        state.currentPriceBandIdx += 1;
        state.filters.price_band = state.priceBands[state.currentPriceBandIdx];
        state.page = 1;
        showToast(`價位：${state.filters.price_band}`);
        loadPhotos();
    }
});

gridHammer.on("swipedown", () => {
    state.similarMode = null;
    if (state.currentPriceBandIdx > 0) {
        state.currentPriceBandIdx -= 1;
        state.filters.price_band = state.priceBands[state.currentPriceBandIdx];
        state.page = 1;
        showToast(`價位：${state.filters.price_band}`);
        loadPhotos();
    } else if (state.currentPriceBandIdx === 0) {
        state.currentPriceBandIdx = -1;
        delete state.filters.price_band;
        state.page = 1;
        showToast("價位：全部");
        loadPhotos();
    }
});

document.getElementById("clear-filter").addEventListener("click", () => {
    state.filters = {};
    state.currentPriceBandIdx = -1;
    state.page = 1;
    state.similarMode = null;
    loadPhotos();
});

// 啟動
loadPhotos();
