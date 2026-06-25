"""settings.py - 全域路徑與設定"""
import os
from pathlib import Path

# .env 支援（可選，不強制安裝 python-dotenv）
_env_file = Path(__file__).resolve().parent.parent / ".env"
if _env_file.exists():
    for _line in _env_file.read_text().splitlines():
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            _k, _v = _line.split("=", 1)
            os.environ.setdefault(_k.strip(), _v.strip())

# 專案根目錄（自動偵測，跟著 repo 走）
BASE_DIR = Path(__file__).resolve().parent.parent

# 資料路徑
DATA_DIR = BASE_DIR / "data"
STAGING_DIR = DATA_DIR / "00_staging"
UNSORTED_DIR = DATA_DIR / "01_unsorted"
ORIGINAL_DIR = DATA_DIR / "02_original"
PROCESSED_DIR = DATA_DIR / "03_processed"
FULL_DIR = PROCESSED_DIR / "full"
THUMB_DIR = PROCESSED_DIR / "thumb"
MICRO_DIR = PROCESSED_DIR / "micro"

# 資料庫
DB_DIR = BASE_DIR / "db"
SQLITE_PATH = DB_DIR / "jewelry.sqlite"
PRICING_DB_PATH = DB_DIR / "pricing.sqlite"
CHROMA_PATH = DB_DIR / "chroma"

# 設定檔
CONFIG_DIR = BASE_DIR / "config"
CATEGORIES_JSON = CONFIG_DIR / "categories.json"

# Web 與 log
WEB_DIR = BASE_DIR / "web"
LOG_DIR = BASE_DIR / "logs"

# 影像處理參數
FULL_SIZE = (1200, 1200)
THUMB_SIZE = (400, 400)
MICRO_SIZE = (100, 100)
JPEG_QUALITY = 90

# CLIP 模型
CLIP_MODEL = "ViT-B-32"
CLIP_PRETRAINED = "laion2b_s34b_b79k"

# 信心分數門檻（低於此值在 UI 標示為「不確定」）
CONFIDENCE_THRESHOLD = 0.5

# 認證 token（設定後所有頁面需帶 ?token=XXX 或 Authorization: Bearer XXX）
# 留空 = 本機開發模式（無需驗證）
AUTH_TOKEN = os.environ.get("JEWELRY_AUTH_TOKEN", "")

# 允許的 CORS origins（逗號分隔，留空 = 全開）
ALLOWED_ORIGINS = [
    o.strip()
    for o in os.environ.get("JEWELRY_ALLOWED_ORIGINS", "").split(",")
    if o.strip()
] or ["*"]
