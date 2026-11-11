// ai-photo-pick — 審美資料庫：客人公開瀏覽＋收藏款式，老闆後台看收藏統計
// 已經不需要人工審片了，上傳一律直接「已留」；/review.html 是舊的人工審片工具，保留但不再是首頁
// D1: photos 表（+ favorites 收藏表、settings 設定表）；R2: 原圖存放

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

      // ── 審片佇列／客人瀏覽清單：status=pending 給審片用，status=kept 給客人瀏覽用
      //    可選加 category/color/gemstone/stone_shape/photo_type 篩選，after_id 做翻頁 ──
      if (pathname === "/api/photos" && request.method === "GET") {
        const status = url.searchParams.get("status") || "pending";
        const limit = Math.min(parseInt(url.searchParams.get("limit") || "60", 10) || 60, 200);
        const order = url.searchParams.get("order") === "random" ? "RANDOM()" : "id ASC";
        const afterId = parseInt(url.searchParams.get("after_id") || "0", 10) || 0;

        const conds = ["status = ?"];
        const binds = [status];
        for (const col of ["category", "color", "gemstone", "stone_shape", "photo_type"]) {
          const v = url.searchParams.get(col);
          if (v) { conds.push(`${col} = ?`); binds.push(v); }
        }
        if (afterId) { conds.push("id > ?"); binds.push(afterId); }
        binds.push(limit);

        const { results } = await env.DB.prepare(
          `SELECT id, filename, status, category, gemstone, style, photo_type, color, stone_shape, created_at
           FROM photos WHERE ${conds.join(" AND ")} ORDER BY ${order} LIMIT ?`
        ).bind(...binds).all();
        return json({
          photos: results.map((p) => ({ ...p, image_url: `/api/image/${p.id}` })),
        });
      }

      // ── 客人瀏覽頁用：目前「已留」照片裡實際出現過哪些分類/顏色/寶石/形狀可選 ──
      if (pathname === "/api/filters" && request.method === "GET") {
        const status = url.searchParams.get("status") || "kept";
        const out = {};
        for (const col of ["category", "color", "gemstone", "stone_shape"]) {
          const { results } = await env.DB.prepare(
            `SELECT DISTINCT ${col} AS v FROM photos WHERE status = ? AND ${col} IS NOT NULL AND ${col} != '' ORDER BY ${col}`
          ).bind(status).all();
          out[col] = results.map((r) => r.v);
        }
        return json(out);
      }

      // ── 收藏：同一個訪客名字對同一張照片按一次＝收藏，再按一次＝取消 ──
      if (pathname === "/api/favorites" && request.method === "POST") {
        const body = await request.json().catch(() => ({}));
        const photoId = parseInt(body.photo_id, 10);
        const name = String(body.name || "").trim().slice(0, 40);
        if (!photoId || !name) return json({ error: "缺少 photo_id 或 name" }, 400);

        const existing = await env.DB.prepare(
          `SELECT id FROM favorites WHERE photo_id = ? AND visitor_name = ?`
        ).bind(photoId, name).first();

        let favorited;
        if (existing) {
          await env.DB.prepare(`DELETE FROM favorites WHERE id = ?`).bind(existing.id).run();
          favorited = false;
        } else {
          await env.DB.prepare(
            `INSERT INTO favorites (photo_id, visitor_name) VALUES (?, ?)`
          ).bind(photoId, name).run();
          favorited = true;
        }
        const row = await env.DB.prepare(
          `SELECT COUNT(*) AS c FROM favorites WHERE photo_id = ?`
        ).bind(photoId).first();
        return json({ favorited, count: row.c });
      }

      // ── 某個訪客收藏了哪些照片（「我的收藏」分頁用）──
      if (pathname === "/api/favorites" && request.method === "GET") {
        const name = String(url.searchParams.get("name") || "").trim();
        if (!name) return json({ favorites: [] });
        const { results } = await env.DB.prepare(
          `SELECT p.id, p.filename, p.category, p.gemstone, p.style, p.color, p.stone_shape, f.created_at AS favorited_at
           FROM favorites f JOIN photos p ON p.id = f.photo_id
           WHERE f.visitor_name = ? ORDER BY f.created_at DESC`
        ).bind(name).all();
        return json({
          favorites: results.map((p) => ({ ...p, image_url: `/api/image/${p.id}` })),
        });
      }

      // ── 後台密碼是否已經設定過（還沒設定過的話，前台要顯示「設定密碼」而不是「登入」）──
      if (pathname === "/api/admin/has-password" && request.method === "GET") {
        const row = await env.DB.prepare(`SELECT value FROM settings WHERE key = 'admin_password'`).first();
        return json({ hasPassword: !!(row && row.value) });
      }

      // ── 第一次設定後台密碼（還沒設定過才能用這個；已經有密碼了要用下面的「修改密碼」）──
      if (pathname === "/api/admin/set-password" && request.method === "POST") {
        const body = await request.json().catch(() => ({}));
        const newPw = String(body.password || "");
        if (newPw.length < 4) return json({ error: "密碼至少需要 4 碼" }, 400);
        const row = await env.DB.prepare(`SELECT value FROM settings WHERE key = 'admin_password'`).first();
        if (row && row.value) return json({ error: "密碼已經設定過了，請用修改密碼的功能" }, 409);
        await env.DB.prepare(
          `INSERT INTO settings (key, value) VALUES ('admin_password', ?)`
        ).bind(newPw).run();
        return json({ ok: true });
      }

      // ── 修改已存在的後台密碼（要先輸入對目前密碼）──
      if (pathname === "/api/admin/change-password" && request.method === "POST") {
        const body = await request.json().catch(() => ({}));
        const oldPw = String(body.old_password || "");
        const newPw = String(body.new_password || "");
        if (newPw.length < 4) return json({ error: "新密碼至少需要 4 碼" }, 400);
        const row = await env.DB.prepare(`SELECT value FROM settings WHERE key = 'admin_password'`).first();
        if (!row || !row.value || row.value !== oldPw) return json({ error: "目前密碼錯誤" }, 401);
        await env.DB.prepare(
          `UPDATE settings SET value = ? WHERE key = 'admin_password'`
        ).bind(newPw).run();
        return json({ ok: true });
      }

      // ── 老闆後台：客人收藏統計（需要密碼）──
      if (pathname === "/api/admin/stats" && request.method === "GET") {
        const pw = url.searchParams.get("password") || request.headers.get("x-admin-password") || "";
        const row = await env.DB.prepare(`SELECT value FROM settings WHERE key = 'admin_password'`).first();
        if (!row || !row.value || pw !== row.value) {
          return json({ error: "密碼錯誤" }, 401);
        }
        const totals = await env.DB.prepare(
          `SELECT COUNT(*) AS totalFavorites,
                  COUNT(DISTINCT visitor_name) AS totalVisitors,
                  COUNT(DISTINCT photo_id) AS totalPhotos
           FROM favorites`
        ).first();
        const { results: top } = await env.DB.prepare(
          `SELECT p.id, p.filename, p.category, p.gemstone, p.color, p.stone_shape, COUNT(f.id) AS cnt
           FROM favorites f JOIN photos p ON p.id = f.photo_id
           GROUP BY f.photo_id ORDER BY cnt DESC LIMIT 60`
        ).all();
        const byCol = async (col) => {
          const { results } = await env.DB.prepare(
            `SELECT p.${col} AS key, COUNT(*) AS cnt FROM favorites f JOIN photos p ON p.id = f.photo_id
             WHERE p.${col} IS NOT NULL AND p.${col} != '' GROUP BY p.${col} ORDER BY cnt DESC`
          ).all();
          return results;
        };
        const [byCategory, byColor, byGemstone, byShape] = await Promise.all([
          byCol("category"), byCol("color"), byCol("gemstone"), byCol("stone_shape"),
        ]);
        const { results: byVisitor } = await env.DB.prepare(
          `SELECT visitor_name, COUNT(*) AS cnt FROM favorites GROUP BY visitor_name ORDER BY cnt DESC LIMIT 60`
        ).all();
        return json({
          totals,
          top: top.map((p) => ({ ...p, image_url: `/api/image/${p.id}` })),
          byCategory, byColor, byGemstone, byShape, byVisitor,
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
      //    可選帶入既有標籤（category/color/gemstone/style/photo_type/stone_shape），搬遷舊照片時沿用；
      //    已經不做人工審片了，所有上傳一律直接算「已留」，客人馬上就看得到；
      //    可選帶 status=pending 才會丟進審片佇列（保留給 /review.html 這個舊工具用）──
      if (pathname === "/api/photos" && request.method === "POST") {
        const form = await request.formData();
        const files = form.getAll("file").filter((f) => f && typeof f.arrayBuffer === "function");
        if (files.length === 0) return json({ error: "沒有收到檔案" }, 400);
        const category = form.get("category") || null;
        const color = form.get("color") || null;
        const gemstone = form.get("gemstone") || null;
        const style = form.get("style") || null;
        const photoType = form.get("photo_type") || null;
        const stoneShape = form.get("stone_shape") || null;
        const status = form.get("status") === "pending" ? "pending" : "kept";

        const added = [];
        const skipped = [];
        for (const file of files) {
          const buf = await file.arrayBuffer();
          const hashBuf = await crypto.subtle.digest("SHA-256", buf);
          const hash = [...new Uint8Array(hashBuf)].map((b) => b.toString(16).padStart(2, "0")).join("");

          // 內容已存在（不論檔名），跳過不重複上傳，但順便把這次帶來、舊紀錄還缺的欄位補上 ──
          const dup = await env.DB.prepare(`SELECT id FROM photos WHERE file_hash = ?`).bind(hash).first();
          if (dup) {
            await env.DB.prepare(
              `UPDATE photos SET
                 category = COALESCE(category, ?), color = COALESCE(color, ?),
                 gemstone = COALESCE(gemstone, ?), style = COALESCE(style, ?),
                 photo_type = COALESCE(photo_type, ?), stone_shape = COALESCE(stone_shape, ?)
               WHERE id = ?`
            ).bind(category, color, gemstone, style, photoType, stoneShape, dup.id).run();
            skipped.push({ id: dup.id, filename: file.name || "" });
            continue;
          }

          const ext = extOf(file.name);
          const key = `photos/${crypto.randomUUID()}.${ext}`;
          await env.IMAGES.put(key, buf, {
            httpMetadata: { contentType: file.type || contentTypeFor(ext) },
          });
          const ins = await env.DB.prepare(
            `INSERT INTO photos (r2_key, filename, status, content_type, file_size, category, color, gemstone, style, photo_type, stone_shape, file_hash, decided_at)
             VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`
          ).bind(
            key, file.name || key, status, file.type || contentTypeFor(ext), buf.byteLength,
            category, color, gemstone, style, photoType, stoneShape, hash, status === "kept" ? new Date().toISOString() : null
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
