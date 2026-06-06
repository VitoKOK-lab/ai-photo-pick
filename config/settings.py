"""settings.py - 全域路徑與設定"""
from pathlib import Path

# 專案根目錄（自動偵測，跟著 repo 走）
BASE_DIR = Path(__file__).resolve().parent.parent

# 資料路徑
DATA_DIR = BASE_DIR / "data"
UNSORTED_DIR = DATA_DIR / "01_unsorted"
ORIGINAL_DIR = DATA_DIR / "02_original"
PROCESSED_DIR = DATA_DIR / "03_processed"
FULL_DIR = PROCESSED_DIR / "full"
THUMB_DIR = PROCESSED_DIR / "thumb"
MICRO_DIR = PROCESSED_DIR / "micro"

# 資料庫
DB_DIR = BASE_DIR / "db"
SQLITE_PATH = DB_DIR / "jewelry.sqlite"
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
