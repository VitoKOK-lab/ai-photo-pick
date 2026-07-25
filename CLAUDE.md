# ai-photo-pick — 開發指引

## 環境

- **Mac Mini M4**，系統 Python 3.9（CommandLineTools）
- 指令用 `python3`（不是 `python`）
- 套件裝在 `/Users/vitomini/Library/Python/3.9/lib/python/site-packages/`
- **numpy 必須鎖在 1.x**（`numpy<2`），2.0 與 torchvision 不相容

## 匯入照片（完整流程）

```bash
# 1. 把照片放進 data/01_unsorted/（子資料夾都可以）
# 2. 執行（會自動處理 + 補標籤 + 刪空資料夾）
python3 -m scripts.02_migrate      # 每次 git pull 後先跑（補欄位，可重複執行）
python3 -m scripts.full_ingest     # 一鍵匯入
```

`full_ingest.py` 做三件事：
1. 批次 CLIP 分析 → 寫入 SQLite + ChromaDB（成功後刪來源檔）
2. 刪除 01_unsorted/ 內的空資料夾
3. 補填舊照片缺少的標籤（gemstone / metal_color / setting_amount / craft_complexity）

## 資料庫欄位對照

CLIP 分類的 11 個維度，全部存進 SQLite `photos` 表：

| 欄位 | 說明 | 選項 |
|---|---|---|
| category | 品項 | 戒指/手鏈/墜子/項鍊/耳釘/胸針/其他 |
| color | 寶石色 | 紅/粉/黃/綠/藍/紫/白/彩 |
| gemstone | 寶石種類 | 鑽石/紅寶石/藍寶石… 共18種 |
| stone_shape | 形狀 | 橢圓形/水滴形/圓形… 共13種 |
| stone_size | 大小 | 1克拉以內 → 10克拉以上 |
| material | 材質 | 925銀/18K黃金/18K白金/18K玫瑰金/鉑金/其他 |
| metal_color | 金工色 | 金/銀 |
| style | 鑽石量 | 無鑽/簡約/輕奢/奢華 |
| setting_amount | 配石量 | 少/正常/多 |
| craft_complexity | 複雜度 | 極簡/普通/複雜/極複雜 |
| price_band | 價格區間 | 入門/中階/高階/奢華/頂級 |
| photo_type | 照片類型 | 去背/情境 |

## 已知注意事項

- `diamond_status`：schema 有此欄，但 CLIP 不自動填，需手動標記
- `price_estimate_low/high`：保留欄位，目前不自動填
- `metal_color / setting_amount / craft_complexity / price_band / photo_type` 只存 label，不存 confidence
- `photo_type` 用 CLIP 語意判斷（prompts.json 有定義），新圖匯入自動分類，舊圖補跑 `python3 -m scripts.classify_photo_type`
- UI 預設只顯示「去背」照片，篩選列點「照片類型」可切換為「情境」或全部

## 情境照浮水印/他牌文字偵測（Gemini）

情境照常夾帶別家浮水印/品牌名/文字。用 Gemini 偵測並「標記」（不自動刪），到 App 審查後刪。

```bash
python3 -m scripts.02_migrate           # 先補 watermark_flag 欄位（第一次）
python3 -m scripts.scan_watermarks      # 掃尚未檢查的情境照 → 標記疑似有文字的
python3 -m scripts.scan_watermarks --rescan   # 全部情境照重掃
```

- `full_ingest` 已內建 STEP 5：每次匯入自動掃新情境照並標記（需 GEMINI_API_KEY）
- App 情境模式點「⚠ 疑似浮水印」篩選 → 逐張審查：確認是他牌就刪（刪除同步移除原圖+縮圖+向量），要留的按「保留」清除標記
- `watermark_flag`：NULL=未檢查、0=乾淨/已保留、1=疑似有浮水印文字

## 驗證 DB 是否完整

```bash
python3 -c "
import sqlite3
conn = sqlite3.connect('db/jewelry.sqlite')
total    = conn.execute('SELECT COUNT(*) FROM photos').fetchone()[0]
has_gem  = conn.execute('SELECT COUNT(*) FROM photos WHERE gemstone IS NOT NULL').fetchone()[0]
no_gem   = conn.execute('SELECT COUNT(*) FROM photos WHERE gemstone IS NULL').fetchone()[0]
print(f'總照片數: {total}，有寶石標籤: {has_gem}，缺: {no_gem}')
conn.close()
"
```

## 啟動伺服器

```bash
python3 -m uvicorn api.main:app --host 0.0.0.0 --port 8000
```

## 重要：更新代碼後

```bash
git pull
python3 -m scripts.02_migrate   # 若有新欄位
# 重啟 uvicorn
pkill -f "uvicorn api.main:app"
python3 -m uvicorn api.main:app --host 0.0.0.0 --port 8000 &
```
