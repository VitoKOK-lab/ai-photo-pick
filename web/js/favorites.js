import * as api from "./api.js";

const grid = document.getElementById("grid");
const lightbox = document.getElementById("lightbox");
const lightboxImg = document.getElementById("lightbox-img");
const toast = document.getElementById("toast");

let state = {
    page: 1,
    favorites: [],
};

function showToast(msg) {
    toast.textContent = msg;
    toast.classList.add("show");
    setTimeout(() => toast.classList.remove("show"), 1500);
}

async function load() {
    const data = await api.listFavorites(state.page);
    state.favorites = data.favorites;
    document.getElementById("total-count").textContent = `(${data.total})`;
    render();
}

function render() {
    grid.innerHTML = "";
    state.favorites.forEach(f => {
        const tile = document.createElement("div");
        tile.className = "tile favorited";
        tile.dataset.photoId = f.photo_id;

        // 兩階段載入：micro → thumb
        tile.innerHTML = `
            <img src="${f.micro_url}" class="loading-micro" alt="" loading="lazy">
            <div class="price-tag">${f.price_band || ""}</div>
        `;

        const img = tile.querySelector("img");
        const thumbLoader = new Image();
        thumbLoader.src = f.thumb_url;
        thumbLoader.onload = () => {
            img.src = f.thumb_url;
            img.classList.remove("loading-micro");
            img.classList.add("loading-thumb");
        };

        attachGestures(tile, f);
        grid.appendChild(tile);
    });
}

function attachGestures(tile, fav) {
    const hammer = new Hammer(tile);
    hammer.get("doubletap").set({ taps: 2 });
    hammer.get("press").set({ time: 500 });

    hammer.on("tap", () => {
        lightboxImg.src = fav.thumb_url;
        lightboxImg.classList.add("loading-thumb");
        lightbox.classList.add("show");
        lightbox.dataset.photoId = fav.photo_id;

        const fullLoader = new Image();
        fullLoader.src = fav.full_url;
        fullLoader.onload = () => {
            if (lightbox.dataset.photoId == fav.photo_id) {
                lightboxImg.src = fav.full_url;
                lightboxImg.classList.remove("loading-thumb");
            }
        };
    });

    hammer.on("doubletap", () => {
        // 跳主頁啟動相關性模式
        window.location.href = `/?similar=${fav.photo_id}`;
    });

    hammer.on("press", async () => {
        await api.removeFavorite(fav.photo_id);
        showToast("已移除");
        await load();
    });
}

const lightboxHammer = new Hammer(lightbox);
lightboxHammer.on("tap", () => {
    lightbox.classList.remove("show");
    lightboxImg.classList.remove("loading-thumb");
});

document.getElementById("lock-btn").addEventListener("click", async () => {
    if (state.favorites.length < 1) {
        showToast("喜愛清單為空");
        return;
    }
    const top9 = state.favorites.slice(0, 9);
    const photos = top9.map((f, i) => ({ photo_id: f.photo_id, lock_number: i + 1 }));
    const result = await api.createLock(photos);
    showToast(`已鎖定 ${photos.length} 張`);
    setTimeout(() => window.location.href = "/locks.html", 800);
});

load();
