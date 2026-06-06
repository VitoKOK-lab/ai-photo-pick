# Jewelry DB - AI 珠寶照片資料庫

本機 AI 珠寶照片資料庫，自動分類兩萬張珠寶照片並支援向量相關性搜尋。

## 技術架構

- **後端**：FastAPI（Python 3.11）
- **資料庫**：SQLite（metadata）+ chromadb（向量庫）
- **AI 模型**：open_clip ViT-B-32
- **影像處理**：Pillow
- **前端**：純 HTML/JS + Hammer.js（手勢）
- **部署**：Mac mini（本機）+ Cloudflare Tunnel（對外）

## Phase 進度

- [x] **Phase 0**：環境準備 + 100 張試跑（計畫見 `docs/phase0-1-plan.md`）
- [x] **Phase 1**：核心 Ingestion 管道 + 全量首跑
- [x] **Phase 2**：本機 9 宮格 UI（計畫見 `docs/phase2-plan.md`）
- [ ] **Phase 3**：互動追蹤統計 dashboard（計畫見 `docs/phase3-plan.md`）
- [ ] **Phase 4**：React 升級 + Cloudflare Tunnel + GitHub Pages + 認證（計畫見 `docs/phase4-plan.md`）
- [ ] **Phase 5**：價格引擎（舊報價匯入 + AI 推估，計畫見 `docs/phase5-plan.md`）
- [ ] **Phase 6**：客戶分享連結 + 備份系統（計畫見 `docs/phase6-plan.md`）

## 重要文件

| 文件 | 用途 |
|---|---|
| `docs/MASTER_PLAN.md` | 整體規劃總覽，先讀這份 |
| `docs/CLAUDE_CODE_GUIDE.md` | 給 Claude Code 看的工作指引 + Vito 偏好 |
| `docs/phase0-1-plan.md` | Phase 0-1 詳細執行步驟 |
| `docs/phase2-plan.md` | Phase 2 UI 規格 + 程式碼 |
| `docs/phase3-plan.md` | Phase 3 統計 dashboard |
| `docs/phase4-plan.md` | Phase 4 對外部署 |
| `docs/phase5-plan.md` | Phase 5 價格引擎 |
| `docs/phase6-plan.md` | Phase 6 客戶分享 + 備份 |

## 在 Mac mini 上首次部署

### 1. 環境準備

```bash
# 安裝 Homebrew（若沒有）
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

# 安裝 Python 3.11
brew install python@3.11

# Clone repo
cd ~ && git clone <your-repo-url> jewelry-db
cd jewelry-db

# 建立虛擬環境
python3.11 -m venv venv
source venv/bin/activate

# 安裝套件
pip install -r requirements.txt
```

### 2. 初始化資料庫

```bash
python scripts/01_init_db.py
```

預期輸出：
```
[OK] SQLite initialized at /Users/<you>/jewelry-db/db/jewelry.sqlite
[OK] chromadb collection ready: jewelry_embeddings
```

### 3. 試跑 100 張

把 100 張代表性照片放進 `tests/test_sample/`，然後：

```bash
python -m scripts.test_classify_sample
```

開 `tests/classification_results.csv` 評估分類精度（目標 ≥ 80%）。

### 4. 全量批次處理

把所有照片放進 `data/01_unsorted/`，然後：

```bash
nohup python -m scripts.batch_run > logs/batch_$(date +%Y%m%d_%H%M).log 2>&1 &
tail -f logs/batch_*.log  # 監看進度
```

兩萬張預估 3-6 小時，可背景跑。

### 5. 啟動 server

```bash
uvicorn api.main:app --host 0.0.0.0 --port 8000
```

瀏覽器開 `http://localhost:8000/`（本機）或 `http://<Mac IP>:8000/`（同 WiFi 手機）。

### 6. 啟動 watch folder（背景監聽新照片）

另一個終端機：

```bash
python -m scripts.watch_folder
```

之後丟新照片進 `data/01_unsorted/` 會自動處理。

### 7. 設為開機自動啟動（macOS launchd）

參考 `docs/phase0-1-plan.md` Task 1.6 Step 3 的 launchd plist 設定。

## 資料夾結構

```
jewelry-db/
├── api/              ← FastAPI 後端路由
├── config/           ← 設定檔（categories.json, settings.py）
├── data/             ← 照片資料（不進 repo）
│   ├── 01_unsorted/  ← 丟新照片進這
│   ├── 02_original/  ← 原始檔備份
│   └── 03_processed/ ← 處理後三種尺寸
├── db/               ← SQLite + chromadb（不進 repo）
├── docs/             ← Phase 計畫文件
├── logs/             ← 執行 log
├── scripts/          ← 處理 script
├── tests/            ← 試樣
└── web/              ← 前端 HTML/JS/CSS
```

## 開發注意事項

- **照片不進 repo**：原始檔留本機，定期 rclone 同步 Google Drive
- **DB 不進 repo**：每台機器自己初始化
- **設定改 categories.json 後**：重跑 `python -m scripts.batch_run` 才會套用
- **新增照片**：丟進 `data/01_unsorted/`，watch_folder 服務會自動處理

## 備份策略（Phase 6）

- **Time Machine**：外接硬碟，每小時自動
- **rclone + Google Drive**：每日同步 `data/02_original/`
- **GitHub**：程式碼版控（本 repo）
