import * as api from "./api.js";

const grid = document.getElementById("grid");
const toast = document.getElementById("toast");

function showToast(msg) {
    toast.textContent = msg;
    toast.classList.add("show");
    setTimeout(() => toast.classList.remove("show"), 1500);
}

async function load() {
    const data = await api.getCurrentLock();
    if (!data.locks || data.locks.length === 0) {
        grid.innerHTML = "<p style='padding:20px; text-align:center; color:#999;'>尚未鎖定任何照片</p>";
        return;
    }
    grid.innerHTML = "";
    data.locks.forEach(l => {
        const tile = document.createElement("div");
        tile.className = "tile lock-tile";

        // 兩階段載入：micro → thumb
        tile.innerHTML = `
            <img src="${l.micro_url}" class="loading-micro" alt="" loading="lazy">
            <div class="lock-number">${l.lock_number}</div>
        `;

        const img = tile.querySelector("img");
        const thumbLoader = new Image();
        thumbLoader.src = l.thumb_url;
        thumbLoader.onload = () => {
            img.src = l.thumb_url;
            img.classList.remove("loading-micro");
            img.classList.add("loading-thumb");
        };

        grid.appendChild(tile);
    });

    document.getElementById("share-info").textContent =
        `Token: ${data.customer_share_token} ｜ 過期：${new Date(data.expires_at).toLocaleString()}`;
}

document.getElementById("unlock-btn").addEventListener("click", async () => {
    await api.deleteLock();
    showToast("已解鎖");
    setTimeout(() => window.location.href = "/favorites.html", 600);
});

document.getElementById("share-btn").addEventListener("click", () => {
    showToast("Phase 4 才上線");
});

load();
