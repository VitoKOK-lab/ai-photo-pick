// api.js - API 呼叫封裝
import { getSessionId } from "./session.js";

const BASE = "";

export async function listPhotos(filters = {}, page = 1) {
    const params = new URLSearchParams();
    Object.entries(filters).forEach(([k, v]) => {
        if (v) params.set(k, v);
    });
    params.set("page", page);
    params.set("session_id", getSessionId());
    params.set("exclude_seen", "false");

    const res = await fetch(`${BASE}/api/photos?${params}`);
    return res.json();
}

export async function getPhoto(id) {
    const res = await fetch(`${BASE}/api/photos/${id}`);
    return res.json();
}

export async function findSimilar(photoId, limit = 8) {
    const params = new URLSearchParams({
        limit,
        session_id: getSessionId(),
        exclude_seen: "true",
    });
    const res = await fetch(`${BASE}/api/photos/${photoId}/similar?${params}`);
    return res.json();
}

export async function addFavorite(photoId) {
    const res = await fetch(`${BASE}/api/favorites`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ photo_id: photoId, session_id: getSessionId() }),
    });
    return res.json();
}

export async function removeFavorite(photoId) {
    const params = new URLSearchParams({ session_id: getSessionId() });
    const res = await fetch(`${BASE}/api/favorites/${photoId}?${params}`, {
        method: "DELETE",
    });
    return res.json();
}

export async function listFavorites(page = 1) {
    const params = new URLSearchParams({ session_id: getSessionId(), page });
    const res = await fetch(`${BASE}/api/favorites?${params}`);
    return res.json();
}

export async function logEvent(photoId, eventType, dwellMs = null, metadata = null) {
    const res = await fetch(`${BASE}/api/events`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
            photo_id: photoId,
            event_type: eventType,
            session_id: getSessionId(),
            dwell_ms: dwellMs,
            metadata,
        }),
    });
    return res.json();
}

export async function createLock(photos, expiresDays = 30) {
    const res = await fetch(`${BASE}/api/locks`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
            session_id: getSessionId(),
            photos,
            expires_days: expiresDays,
        }),
    });
    return res.json();
}

export async function deleteLock() {
    const params = new URLSearchParams({ session_id: getSessionId() });
    const res = await fetch(`${BASE}/api/locks?${params}`, { method: "DELETE" });
    return res.json();
}

export async function getCurrentLock() {
    const params = new URLSearchParams({ session_id: getSessionId() });
    const res = await fetch(`${BASE}/api/locks/current?${params}`);
    return res.json();
}
