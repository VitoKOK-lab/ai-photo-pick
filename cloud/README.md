# ai-photo-pick（雲端版 — 線上選品平台）

獨立於本機 Mac 系統之外，跑在 Cloudflare 上的簡化版：**公開無登入**，審片佇列（留/刪，決定後不再出現）。

- 正式網址：https://ai-photo-pick.vitokok.workers.dev
- Worker 名稱：`ai-photo-pick`
- D1 資料庫：`ai-photo-pick-db`
- R2 儲存桶：`ai-photo-pick-images`

## 跟本機系統的關係

這是**完全獨立的新系統**，不讀本機的 SQLite/CLIP/ChromaDB，也沒有估價、貴金屬設定等功能——只單純做「大量瀏覽 → 留下 / 刪除」。

- 把本機照片庫（含既有的品項/寶石/風格標籤）搬上來：在**本機 Mac**跑
  ```bash
  python3 -m scripts.push_to_cloud
  ```
  （腳本只呼叫雲端公開 API，不需要任何 Cloudflare 金鑰；可重複執行、會自動跳過已搬過的）
- 雲端上按「刪除」是**真的刪除**（R2 物件 + D1 資料列都清掉），沒有登入、沒有角色限制，任何打開網址的人都能操作

## 開發 / 部署

```bash
cd cloud
npx wrangler dev        # 本地測試
npx wrangler deploy     # 部署到 Cloudflare
```

`wrangler.toml` 裡的 D1/R2 綁定 ID 已經指向正式資源，直接部署就會更新正式站。

## API

全部公開，無需驗證：

| | |
|---|---|
| `GET /api/stats` | 待審/已留/總數 |
| `GET /api/photos?status=pending&limit=40&order=random` | 審片佇列 |
| `POST /api/photos/:id/keep` | 留下 |
| `DELETE /api/photos/:id` | 真刪除（R2 + D1） |
| `POST /api/photos` | 上傳新照片（multipart，field `file`，可選 `category`/`gemstone`/`style`/`photo_type`） |
| `GET /api/image/:id` | 串流圖片本體 |
