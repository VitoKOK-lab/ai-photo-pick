// ai-photo-pick — 線上選品平台（公開無登入，審片佇列：留/刪，決定後不再出現）
// D1: photos 表；R2: 原圖存放

const CORS = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Methods": "GET,POST,DELETE,OPTIONS",
  "Access-Control-Allow-Headers": "Content-Type",
};

function json(data, status = 200) {
  return new Response(JSON.stringify(data), {
    status,
    headers: { "Content-Type": "application/json; charset=utf-8", ...CORS },
  });
}

function extOf(name, fallback = "jpg") {
  const m = /\.([a-zA-Z0-9]+)$/.exec(name || "");
  return (m ? m[1] : fallback).toLowerCase();
}

function contentTypeFor(ext) {
  const map = { jpg: "image/jpeg", jpeg: "image/jpeg", png: "image/png", webp: "image/webp", heic: "image/heic" };
  return map[ext] || "application/octet-stream";
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    const { pathname } = url;

    if (request.method === "OPTIONS") {
      return new Response(null, { headers: CORS });
    }

    try {
      // ── 統計：待審 / 已留 / 已刪總數（刪除是硬刪，不留紀錄，所以只有 pending/kept 計數有意義）──
      if (pathname === "/api/stats" && request.method === "GET") {
        const row = await env.DB.prepare(
          `SELECT
             SUM(CASE WHEN status='pending' THEN 1 ELSE 0 END) AS pending,
             SUM(CASE WHEN status='kept'    THEN 1 ELSE 0 END) AS kept,
             COUNT(*) AS total
           FROM photos`
        ).first();
        return json({
          pending: row.pending || 0,
          kept: row.kept || 0,
          total: row.total || 0,
        });
      }

      // ── 審片佇列：只回傳還沒決定的照片 ──
      if (pathname === "/api/photos" && request.method === "GET") {
        const status = url.searchParams.get("status") || "pending";
        const limit = Math.min(parseInt(url.searchParams.get("limit") || "60", 10) || 60, 200);
        const order = url.searchParams.get("order") === "random" ? "RANDOM()" : "id ASC";
        const { results } = await env.DB.prepare(
          `SELECT id, filename, status, category, gemstone, style, photo_type, created_at
           FROM photos WHERE status = ? ORDER BY ${order} LIMIT ?`
        ).bind(status, limit).all();
        return json({
          photos: results.map((p) => ({ ...p, image_url: `/api/image/${p.id}` })),
        });
      }

      // ── 留下這張：移出審片佇列 ──
      const keepMatch = pathname.match(/^\/api\/photos\/(\d+)\/keep$/);
      if (keepMatch && request.method === "POST") {
        const id = keepMatch[1];
        const r = await env.DB.prepare(
          `UPDATE photos SET status='kept', decided_at=CURRENT_TIMESTAMP WHERE id=?`
        ).bind(id).run();
        if (!r.meta.changes) return json({ error: "Photo not found" }, 404);
        return json({ kept: Number(id) });
      }

      // ── 真刪除：R2 物件 + D1 資料列都刪掉 ──
      const delMatch = pathname.match(/^\/api\/photos\/(\d+)$/);
      if (delMatch && request.method === "DELETE") {
        const id = delMatch[1];
        const row = await env.DB.prepare(`SELECT r2_key FROM photos WHERE id=?`).bind(id).first();
        if (!row) return json({ error: "Photo not found" }, 404);
        await env.IMAGES.delete(row.r2_key);
        await env.DB.prepare(`DELETE FROM photos WHERE id=?`).bind(id).run();
        return json({ deleted: Number(id) });
      }

      // ── 上傳新照片（可一次多檔，multipart/form-data，field name: file）
      //    可選帶入既有標籤（category/gemstone/style/photo_type），搬遷舊照片時沿用 ──
      if (pathname === "/api/photos" && request.method === "POST") {
        const form = await request.formData();
        const files = form.getAll("file").filter((f) => f && typeof f.arrayBuffer === "function");
        if (files.length === 0) return json({ error: "沒有收到檔案" }, 400);
        const category = form.get("category") || null;
        const gemstone = form.get("gemstone") || null;
        const style = form.get("style") || null;
        const photoType = form.get("photo_type") || null;

        const added = [];
        const skipped = [];
        for (const file of files) {
          const buf = await file.arrayBuffer();
          const hashBuf = await crypto.subtle.digest("SHA-256", buf);
          const hash = [...new Uint8Array(hashBuf)].map((b) => b.toString(16).padStart(2, "0")).join("");

          // 內容已存在（不論檔名），跳過，不重複上傳 ──
          const dup = await env.DB.prepare(`SELECT id FROM photos WHERE file_hash = ?`).bind(hash).first();
          if (dup) {
            skipped.push({ id: dup.id, filename: file.name || "" });
            continue;
          }

          const ext = extOf(file.name);
          const key = `photos/${crypto.randomUUID()}.${ext}`;
          await env.IMAGES.put(key, buf, {
            httpMetadata: { contentType: file.type || contentTypeFor(ext) },
          });
          const ins = await env.DB.prepare(
            `INSERT INTO photos (r2_key, filename, status, content_type, file_size, category, gemstone, style, photo_type, file_hash)
             VALUES (?, ?, 'pending', ?, ?, ?, ?, ?, ?, ?)`
          ).bind(
            key, file.name || key, file.type || contentTypeFor(ext), buf.byteLength,
            category, gemstone, style, photoType, hash
          ).run();
          added.push({ id: ins.meta.last_row_id, filename: file.name || key });
        }
        return json({ added, skipped }, 201);
      }

      // ── 串流圖片本體（從 R2）──
      const imgMatch = pathname.match(/^\/api\/image\/(\d+)$/);
      if (imgMatch && request.method === "GET") {
        const id = imgMatch[1];
        const row = await env.DB.prepare(`SELECT r2_key, content_type FROM photos WHERE id=?`).bind(id).first();
        if (!row) return new Response("Not found", { status: 404 });
        const obj = await env.IMAGES.get(row.r2_key);
        if (!obj) return new Response("Not found", { status: 404 });
        return new Response(obj.body, {
          headers: {
            "Content-Type": row.content_type || obj.httpMetadata?.contentType || "image/jpeg",
            "Cache-Control": "public, max-age=31536000, immutable",
            ...CORS,
          },
        });
      }

      // ── 其餘：交給靜態前端 ──
      return env.ASSETS.fetch(request);
    } catch (err) {
      return json({ error: String(err && err.message ? err.message : err) }, 500);
    }
  },
};
