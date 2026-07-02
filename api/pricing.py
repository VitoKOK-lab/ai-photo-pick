"""pricing.py - 估價資料庫（獨立於照片資料庫）"""
import json
import sqlite3
import sys
from pathlib import Path
from typing import Optional
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from api.auth import require_admin

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config.settings import PRICING_DB_PATH

router = APIRouter(prefix="/api/pricing", tags=["pricing"])

PRICING_DB_PATH.parent.mkdir(parents=True, exist_ok=True)


def _conn():
    c = sqlite3.connect(PRICING_DB_PATH)
    c.row_factory = sqlite3.Row
    return c


# ─── Schema + Seed ────────────────────────────────────────────
_SEED_METALS = [
    # Spot (Jun 2026): 24K≈4800/g, 999Ag≈85/g, Pt999≈2200/g; ×karat×1.25 Taiwan retail
    ("925銀",    98),   # 85×0.925×1.25≈98
    ("14K金",  3500),   # 4800×0.585×1.25≈3510→3500
    ("18K金",  4500),   # 4800×0.75×1.25≈4500
    ("Pt950",  2600),   # 2200×0.95×1.25≈2613→2600
]

_SEED_WEIGHTS = [
    ("極輕 (0.5–1.5g)", 0.5,  1.5),
    ("輕 (1.5–3g)",     1.5,  3.0),
    ("中 (3–5g)",       3.0,  5.0),
    ("偏重 (5–8g)",     5.0,  8.0),
    ("重 (8–13g)",      8.0, 13.0),
    ("很重 (13–20g)",  13.0, 20.0),
    ("特重 (20–35g)",  20.0, 35.0),
    ("超重 (35–50g)",  35.0, 50.0),
]

_CT_MULTS = [('1ct', 1.0), ('2ct', 2.2), ('3ct', 3.8), ('4ct', 5.5), ('5ct', 8.0)]
_SEED_COMMERCIAL_CARAT = [
    (key, ct, name, round(pmin * mult), round(pmax * mult))
    for key, name, pmin, pmax in [
        ("MORGANITE",  "摩根石",    1500,   8000),
        ("AMETHYST",   "紫水晶",     300,   2000),
        ("CITRINE",    "黃水晶",     300,   2000),
        ("TOPAZ",      "托帕石",     500,   3000),
        ("AQUAMARINE", "海藍寶石",  2000,  15000),
        ("TOURMALINE", "碧璽",      2000,  30000),
        ("MOONSTONE",  "月光石",    1000,   6000),
        ("OPAL",       "歐泊",      2000,  20000),
        ("PERIDOT",    "橄欖石",     500,   3000),
        ("GARNET",     "石榴石",     500,   4000),
        ("SPINEL",     "尖晶石",    3000,  30000),
        ("ZIRCON",     "鋯石",       200,   1500),
        ("LABRADORITE","拉長石",     500,   3000),
        ("KUNZITE",    "紫鋰輝石",  1000,   8000),
        ("SPHENE",     "榍石",      2000,  15000),
    ]
    for ct, mult in _CT_MULTS
]

_SEED_LABOR = [
    ("戒指",   "極簡",  1500,  2500),
    ("戒指",   "簡單",  2500,  4500),
    ("戒指",   "中等",  4500,  7000),
    ("戒指",   "複雜",  7000, 12000),
    ("戒指",   "精工", 12000, 25000),
    ("吊墜",   "極簡",  1000,  2000),
    ("吊墜",   "簡單",  2000,  3500),
    ("吊墜",   "中等",  3500,  6000),
    ("吊墜",   "複雜",  6000, 10000),
    ("吊墜",   "精工", 10000, 20000),
    ("耳釘",   "極簡",  1500,  2500),
    ("耳釘",   "簡單",  2500,  4500),
    ("耳釘",   "中等",  4500,  7000),
    ("耳釘",   "複雜",  7000, 12000),
    ("耳釘",   "精工", 12000, 22000),
    ("手鏈",   "極簡",  3000,  5000),
    ("手鏈",   "簡單",  5000,  8000),
    ("手鏈",   "中等",  8000, 13000),
    ("手鏈",   "複雜", 13000, 22000),
    ("手鏈",   "精工", 22000, 40000),
    ("項鍊",   "極簡",  4000,  7000),
    ("項鍊",   "簡單",  7000, 12000),
    ("項鍊",   "中等", 12000, 20000),
    ("項鍊",   "複雜", 20000, 35000),
    ("項鍊",   "精工", 35000, 60000),
    ("胸針",   "極簡",  1500,  2500),
    ("胸針",   "簡單",  2500,  4000),
    ("胸針",   "中等",  4000,  7000),
    ("胸針",   "複雜",  7000, 12000),
    ("胸針",   "精工", 12000, 22000),
    ("手鐲",   "極簡",  2000,  3500),
    ("手鐲",   "簡單",  3500,  6000),
    ("手鐲",   "中等",  6000, 10000),
    ("手鐲",   "複雜", 10000, 18000),
    ("手鐲",   "精工", 18000, 35000),
]

# ── 投資級寶石 v2：與前端估價工具一致（17 種，含產地/處理/色級乘數）──
# 升版時會清空四張 invest 表重灌一次（使用者自訂值會被重設，之後可再編輯）
INVEST_SEED_VERSION = 2

_INVEST_V2 = {
    "RUBY": {"name": "紅寶石",
        "floor": {"B1": 40000, "B2": 120000, "B3": 350000, "B4": 1000000, "B5": 3500000},
        "ceil":  {"B1": 200000, "B2": 600000, "B3": 2000000, "B4": 8000000, "B5": 30000000},
        "origins": {"緬甸 Mogok": 3.0, "莫桑比克": 1.0, "泰國": 0.4, "馬達加斯加": 0.6, "其他": 0.5},
        "treatments": {"無燒": 1.0, "有燒": 0.3},
        "colors": {"頂級 (鴿血/牛血)": 2.5, "中等 (深紅)": 1.0, "入門 (淡紅/粉)": 0.5}},
    "SAPPHIRE": {"name": "藍寶石",
        "floor": {"B1": 50000, "B2": 150000, "B3": 400000, "B4": 1000000, "B5": 3000000},
        "ceil":  {"B1": 250000, "B2": 1200000, "B3": 3500000, "B4": 12000000, "B5": 40000000},
        "origins": {"喀什米爾": 4.0, "緬甸": 2.5, "錫蘭/斯里蘭卡": 1.0, "馬達加斯加": 0.5, "泰國": 0.3, "澳洲": 0.3},
        "treatments": {"無燒": 1.0, "有燒": 0.3},
        "colors": {"頂級 (矢車菊/皇家藍)": 2.5, "中等 (中藍)": 1.0, "入門 (淺藍)": 0.5}},
    "PADPARADSCHA": {"name": "帕帕拉恰",
        "floor": {"B1": 100000, "B2": 250000, "B3": 600000, "B4": 1500000, "B5": 5000000},
        "ceil":  {"B1": 300000, "B2": 800000, "B3": 2500000, "B4": 8000000, "B5": 25000000},
        "origins": {"錫蘭/斯里蘭卡": 1.0, "馬達加斯加": 0.5, "越南": 0.6},
        "treatments": {"無燒": 1.0, "有燒": 0.4},
        "colors": {"頂級 (粉橙均衡)": 2.0, "中等 (偏粉或偏橙)": 1.0, "入門 (色淡)": 0.5}},
    "EMERALD": {"name": "祖母綠",
        "floor": {"B1": 30000, "B2": 80000, "B3": 300000, "B4": 800000, "B5": 2500000},
        "ceil":  {"B1": 150000, "B2": 400000, "B3": 1500000, "B4": 5000000, "B5": 15000000},
        "origins": {"哥倫比亞 Muzo": 2.5, "哥倫比亞 Chivor": 1.8, "尚比亞": 1.0, "巴西": 0.6, "衣索比亞": 0.5},
        "treatments": {"None (無油)": 1.4, "Minor (輕油)": 1.0, "Moderate (中油)": 0.6, "Significant (重油)": 0.3},
        "colors": {"頂級 (Vivid Green)": 2.0, "中等 (中綠)": 1.0, "入門 (淺綠)": 0.5}},
    "DIAMOND": {"name": "鑽石",
        "floor": {"B1": 40000, "B2": 100000, "B3": 250000, "B4": 600000, "B5": 1500000},
        "ceil":  {"B1": 160000, "B2": 400000, "B3": 900000, "B4": 2500000, "B5": 6000000},
        "origins": {"一般": 1.0},
        "treatments": {"無處理": 1.0, "HPHT/輻照處理": 0.5, "培育鑽 (Lab-grown)": 0.15},
        "colors": {"D–F 高色": 1.5, "G–H": 1.0, "I–J": 0.7, "K 以下": 0.45}},
    "PARAIBA": {"name": "帕拉依巴",
        "floor": {"B1": 70000, "B2": 150000, "B3": 500000, "B4": 1500000, "B5": 4000000},
        "ceil":  {"B1": 300000, "B2": 700000, "B3": 2500000, "B4": 7000000, "B5": 20000000},
        "origins": {"巴西 Paraiba 州": 3.5, "莫桑比克": 1.0, "奈及利亞": 0.5},
        "treatments": {"無燒": 1.0, "有燒": 0.6},
        "colors": {"頂級 (霓虹藍/電光)": 2.0, "中等 (藍綠)": 1.0, "入門 (淡綠)": 0.4}},
    "SPINEL": {"name": "尖晶石",
        "floor": {"B1": 30000, "B2": 80000, "B3": 200000, "B4": 500000, "B5": 1500000},
        "ceil":  {"B1": 200000, "B2": 800000, "B3": 2500000, "B4": 6000000, "B5": 18000000},
        "origins": {"緬甸 Mogok": 2.5, "坦尚 Mahenge": 2.0, "越南 (鈷藍)": 3.0, "馬達加斯加": 1.0, "塔吉克": 1.2, "其他": 0.7},
        "treatments": {"無燒": 1.0},
        "colors": {"頂級 (鴿血/鈷藍/螢光粉)": 2.5, "中等 (紅/粉/紫)": 1.0, "入門 (淡色/灰色)": 0.4}},
    "ALEXANDRITE": {"name": "變色石",
        "floor": {"B1": 80000, "B2": 200000, "B3": 500000, "B4": 1200000, "B5": 3500000},
        "ceil":  {"B1": 400000, "B2": 1500000, "B3": 4000000, "B4": 10000000, "B5": 30000000},
        "origins": {"俄羅斯 Ural": 2.5, "巴西": 1.0, "斯里蘭卡": 0.8},
        "treatments": {"無處理": 1.0},
        "colors": {"頂級 (變色明顯 80%+)": 2.5, "中等 (50-70%)": 1.0, "入門 (變色弱 <50%)": 0.4}},
    "TANZANITE": {"name": "坦桑石",
        "floor": {"B1": 10000, "B2": 25000, "B3": 50000, "B4": 120000, "B5": 300000},
        "ceil":  {"B1": 40000, "B2": 80000, "B3": 180000, "B4": 400000, "B5": 900000},
        "origins": {"坦尚 Merelani": 1.0},
        "treatments": {"熱處理 (標準)": 1.0, "無燒 (罕見)": 1.4},
        "colors": {"頂級 (D Block 深藍紫)": 2.0, "中等 (藍紫)": 1.0, "入門 (淡藍/淡紫)": 0.4}},
    "TSAVORITE": {"name": "沙弗萊石",
        "floor": {"B1": 40000, "B2": 80000, "B3": 200000, "B4": 600000, "B5": 1500000},
        "ceil":  {"B1": 150000, "B2": 320000, "B3": 800000, "B4": 2000000, "B5": 5000000},
        "origins": {"肯亞": 1.0, "坦尚尼亞": 1.0, "其他": 0.7},
        "treatments": {"無處理": 1.0},
        "colors": {"頂級 (Vivid Green)": 2.0, "中等 (中綠)": 1.0, "入門 (淡綠)": 0.5}},
    "TOURMALINE": {"name": "碧璽",
        "floor": {"B1": 8000, "B2": 20000, "B3": 50000, "B4": 130000, "B5": 300000},
        "ceil":  {"B1": 40000, "B2": 100000, "B3": 300000, "B4": 700000, "B5": 1500000},
        "origins": {"巴西": 1.0, "莫桑比克": 1.2, "奈及利亞": 0.8, "美國 (西瓜)": 1.5, "其他": 0.7},
        "treatments": {"無處理": 1.0, "熱處理": 0.9},
        "colors": {"紅碧璽 Rubellite": 1.5, "藍綠 Indicolite": 1.3, "帕拉依巴色 (含銅)": 4.0, "一般綠/粉": 1.0, "雙色/西瓜": 1.2}},
    "AQUAMARINE": {"name": "海藍寶",
        "floor": {"B1": 10000, "B2": 25000, "B3": 60000, "B4": 130000, "B5": 300000},
        "ceil":  {"B1": 60000, "B2": 250000, "B3": 600000, "B4": 1500000, "B5": 4000000},
        "origins": {"巴西 Santa Maria": 2.0, "巴西其他": 1.0, "莫桑比克": 0.7, "馬達加斯加": 0.6, "巴基斯坦": 1.2},
        "treatments": {"熱處理 (標準)": 1.0, "無燒": 1.3},
        "colors": {"頂級 (Santa Maria 深藍)": 2.5, "中等 (中藍)": 1.0, "入門 (淡藍)": 0.4}},
    "OPAL": {"name": "歐泊",
        "floor": {"B1": 8000, "B2": 20000, "B3": 40000, "B4": 100000, "B5": 250000},
        "ceil":  {"B1": 40000, "B2": 120000, "B3": 300000, "B4": 800000, "B5": 2000000},
        "origins": {"澳洲 Lightning Ridge (黑歐泊)": 5.0, "澳洲 Queensland (Boulder)": 3.0, "澳洲其他": 1.5, "衣索比亞": 1.0, "墨西哥 (Fire)": 0.6},
        "treatments": {"無處理 (Solid)": 1.0, "糖煙處理": 0.6, "雙層複合 Doublet": 0.3, "三層複合 Triplet": 0.15},
        "colors": {"頂級 (Red Fire/Harlequin)": 2.5, "中等 (Multi-color play)": 1.0, "入門 (Blue/Green flash)": 0.5}},
    "SPESSARTITE": {"name": "芬達石榴石",
        "floor": {"B1": 10000, "B2": 25000, "B3": 55000, "B4": 120000, "B5": 280000},
        "ceil":  {"B1": 40000, "B2": 100000, "B3": 250000, "B4": 600000, "B5": 1500000},
        "origins": {"奈及利亞 (Mandarin)": 2.0, "馬達加斯加": 1.5, "納米比亞": 1.3, "巴西": 0.8, "其他": 0.7},
        "treatments": {"無處理": 1.0},
        "colors": {"頂級 (Vivid Mandarin Orange)": 2.0, "中等 (Orange)": 1.0, "入門 (Brownish Orange)": 0.5}},
    "MOONSTONE": {"name": "月光石",
        "floor": {"B1": 4000, "B2": 10000, "B3": 20000, "B4": 45000, "B5": 100000},
        "ceil":  {"B1": 12000, "B2": 30000, "B3": 70000, "B4": 150000, "B5": 300000},
        "origins": {"印度": 0.8, "斯里蘭卡": 1.0, "緬甸": 1.2},
        "treatments": {"無處理": 1.0},
        "colors": {"頂級 (藍光彩虹)": 1.8, "中等 (白光)": 1.0, "入門 (灰白)": 0.5}},
    "YELLOW_SAP": {"name": "黃剛玉",
        "floor": {"B1": 20000, "B2": 60000, "B3": 150000, "B4": 400000, "B5": 1000000},
        "ceil":  {"B1": 100000, "B2": 400000, "B3": 1000000, "B4": 2500000, "B5": 8000000},
        "origins": {"錫蘭": 1.5, "馬達加斯加": 1.0, "緬甸": 1.3, "泰國": 0.5},
        "treatments": {"無燒": 1.0, "有燒": 0.4},
        "colors": {"頂級 (金黃/帕帕色)": 2.0, "中等 (檸檬黃)": 1.0, "入門 (淡黃)": 0.5}},
    "CATEYE": {"name": "貓眼石",
        "floor": {"B1": 20000, "B2": 50000, "B3": 130000, "B4": 300000, "B5": 700000},
        "ceil":  {"B1": 100000, "B2": 250000, "B3": 700000, "B4": 1800000, "B5": 5000000},
        "origins": {"斯里蘭卡": 1.5, "巴西": 1.0, "印度": 0.8},
        "treatments": {"無處理": 1.0},
        "colors": {"頂級 (蜜糖色+清晰光帶)": 2.0, "中等": 1.0, "入門": 0.5}},
}

_SEED_STONES_COMMERCIAL = [
    # 台灣市場 2025 行情（TWD/ct，商業品質批發零售區間）
    ("MORGANITE",  "摩根石",    1500,  15000),   # 頂級深粉紅
    ("AMETHYST",   "紫水晶",     300,   3500),   # 深色烏拉圭精品
    ("CITRINE",    "黃水晶",     300,   3000),   # Madeira 精品
    ("TOPAZ",      "托帕石",     500,  15000),   # 藍托帕低，Imperial 高
    ("AQUAMARINE", "海藍寶石",  2500,  25000),   # 精品海藍寶
    ("TOURMALINE", "碧璽",      2500,  60000),   # Rubellite/Indicolite 精品
    ("MOONSTONE",  "月光石",    1200,  12000),   # 頂級藍月光石
    ("OPAL",       "歐泊",      2500,  40000),   # 黑歐泊
    ("PERIDOT",    "橄欖石",     500,   8000),   # 巴基斯坦/緬甸精品
    ("GARNET",     "石榴石",     800,  20000),   # Tsavorite / Mandarin
    ("SPINEL",     "尖晶石",    4000,  50000),   # 緬甸紅尖晶石
    ("ZIRCON",     "鋯石",       500,   8000),   # 天然柬埔寨藍鋯石
    ("LABRADORITE","拉長石",     500,  10000),   # 頂級 Spectrolite
    ("KUNZITE",    "紫鋰輝石",  1000,  12000),   # 阿富汗精品
    ("SPHENE",     "榍石",      3000,  25000),   # 色散優異的精品
]

_SEED_SIDESTONES = [
    ("無配石",              0,      0),
    ("配石/鋯石 1–5顆",   400,   1200),
    ("配石/鋯石 6–20顆",  1200,  2800),
    ("配石/鋯石 21–50顆", 2800,  5500),
    ("碎鑽/莫桑 1–5顆",   500,  1000),
    ("碎鑽/莫桑 6–20顆",  2000,  5000),
    ("碎鑽/莫桑 21–50顆", 8000, 20000),
    ("碎鑽/莫桑 50+顆",  20000, 60000),
]

_SEED_PLATING = [
    ("無",    0,     0),
    ("金色",  500,  1500),
    ("玫瑰金", 500, 1500),
    ("黑金",  800,  2000),
]

# 師傅工錢：日薪 × 天數 (台灣金工師傅行情 ~NT$3500/天)
_SEED_LABOR_CONFIG = [
    ('daily_rate', 3500.0),
    ('極簡', 0.5),
    ('簡單', 1.0),
    ('中等', 2.0),
    ('複雜', 4.0),
    ('精工', 8.0),
]

# 配石費：種類 × 數量帶
_SEED_SIDESTONES_V2 = [
    ('天然碎鑽', '1–5顆',      500,   1500),
    ('天然碎鑽', '6–15顆',    2000,   5000),
    ('天然碎鑽', '16–30顆',   5000,  12000),
    ('天然碎鑽', '31–50顆',  12000,  25000),
    ('天然碎鑽', '50顆以上',  25000,  80000),
    ('莫桑鑽',   '1–5顆',      300,    800),
    ('莫桑鑽',   '6–15顆',    1000,   3000),
    ('莫桑鑽',   '16–30顆',   2500,   7000),
    ('莫桑鑽',   '31–50顆',   7000,  18000),
    ('莫桑鑽',   '50顆以上',  18000,  50000),
    ('彩色配石', '1–5顆',       200,    600),
    ('彩色配石', '6–15顆',      600,   2000),
    ('彩色配石', '16–30顆',    2000,   5000),
    ('彩色配石', '31–50顆',    5000,  12000),
    ('彩色配石', '50顆以上',  12000,  35000),
    ('合成培育鑽', '1–5顆',     400,   1000),
    ('合成培育鑽', '6–15顆',   1500,   4000),
    ('合成培育鑽', '16–30顆',  4000,   9000),
    ('合成培育鑽', '31–50顆',  9000,  20000),
    ('合成培育鑽', '50顆以上', 20000,  60000),
]


def _init_db():
    conn = sqlite3.connect(PRICING_DB_PATH)
    c = conn.cursor()

    c.executescript("""
        CREATE TABLE IF NOT EXISTS pricing_metals (
            id INTEGER PRIMARY KEY,
            material TEXT UNIQUE NOT NULL,
            price_per_g INTEGER NOT NULL,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS pricing_weights (
            id INTEGER PRIMARY KEY,
            label TEXT UNIQUE NOT NULL,
            weight_min REAL NOT NULL,
            weight_max REAL NOT NULL
        );
        CREATE TABLE IF NOT EXISTS pricing_labor (
            id INTEGER PRIMARY KEY,
            category TEXT NOT NULL,
            complexity TEXT NOT NULL,
            price_min INTEGER NOT NULL,
            price_max INTEGER NOT NULL,
            UNIQUE(category, complexity)
        );
        CREATE TABLE IF NOT EXISTS pricing_stones_invest (
            id INTEGER PRIMARY KEY,
            stone_key TEXT NOT NULL,
            stone_name TEXT NOT NULL,
            band TEXT NOT NULL,
            price_floor INTEGER NOT NULL,
            price_ceil INTEGER NOT NULL,
            UNIQUE(stone_key, band)
        );
        CREATE TABLE IF NOT EXISTS pricing_stone_origins (
            id INTEGER PRIMARY KEY,
            stone_key TEXT NOT NULL,
            origin TEXT NOT NULL,
            multiplier REAL NOT NULL,
            UNIQUE(stone_key, origin)
        );
        CREATE TABLE IF NOT EXISTS pricing_stone_treatments (
            id INTEGER PRIMARY KEY,
            stone_key TEXT NOT NULL,
            treatment TEXT NOT NULL,
            multiplier REAL NOT NULL,
            UNIQUE(stone_key, treatment)
        );
        CREATE TABLE IF NOT EXISTS pricing_stone_colors (
            id INTEGER PRIMARY KEY,
            stone_key TEXT NOT NULL,
            color_quality TEXT NOT NULL,
            multiplier REAL NOT NULL,
            UNIQUE(stone_key, color_quality)
        );
        CREATE TABLE IF NOT EXISTS pricing_stones_commercial (
            id INTEGER PRIMARY KEY,
            stone_key TEXT UNIQUE NOT NULL,
            stone_name TEXT NOT NULL,
            price_min INTEGER NOT NULL,
            price_max INTEGER NOT NULL
        );
        CREATE TABLE IF NOT EXISTS pricing_sidestones (
            id INTEGER PRIMARY KEY,
            label TEXT UNIQUE NOT NULL,
            price_min INTEGER NOT NULL,
            price_max INTEGER NOT NULL
        );
        CREATE TABLE IF NOT EXISTS pricing_plating (
            id INTEGER PRIMARY KEY,
            label TEXT UNIQUE NOT NULL,
            price_min INTEGER NOT NULL,
            price_max INTEGER NOT NULL
        );
        CREATE TABLE IF NOT EXISTS pricing_commercial_carat (
            id INTEGER PRIMARY KEY,
            stone_key TEXT NOT NULL,
            ct_label TEXT NOT NULL,
            stone_name TEXT NOT NULL,
            price_min INTEGER NOT NULL,
            price_max INTEGER NOT NULL,
            UNIQUE(stone_key, ct_label)
        );
        CREATE TABLE IF NOT EXISTS pricing_labor_config (
            key TEXT PRIMARY KEY,
            value REAL NOT NULL
        );
        CREATE TABLE IF NOT EXISTS pricing_sidestones_v2 (
            id INTEGER PRIMARY KEY,
            stone_type TEXT NOT NULL,
            qty_band TEXT NOT NULL,
            price_min INTEGER NOT NULL,
            price_max INTEGER NOT NULL,
            UNIQUE(stone_type, qty_band)
        );
    """)

    # Seed only if tables are empty
    if not c.execute("SELECT 1 FROM pricing_metals LIMIT 1").fetchone():
        c.executemany("INSERT OR IGNORE INTO pricing_metals (material, price_per_g) VALUES (?,?)", _SEED_METALS)

    if not c.execute("SELECT 1 FROM pricing_weights LIMIT 1").fetchone():
        c.executemany("INSERT OR IGNORE INTO pricing_weights (label, weight_min, weight_max) VALUES (?,?,?)", _SEED_WEIGHTS)

    if not c.execute("SELECT 1 FROM pricing_labor LIMIT 1").fetchone():
        c.executemany("INSERT OR IGNORE INTO pricing_labor (category, complexity, price_min, price_max) VALUES (?,?,?,?)", _SEED_LABOR)

    # ── 品項用字統一：手鍊 → 手鏈（與 CLIP/Gemini 分類器一致）──
    c.execute("UPDATE OR IGNORE pricing_labor SET category='手鏈' WHERE category='手鍊'")
    c.execute("DELETE FROM pricing_labor WHERE category='手鍊'")

    # ── 投資級寶石：版本化 seed（升版時清空重灌，與前端估價工具一致）──
    c.execute("CREATE TABLE IF NOT EXISTS pricing_meta (key TEXT PRIMARY KEY, value TEXT)")
    row = c.execute("SELECT value FROM pricing_meta WHERE key='invest_seed_version'").fetchone()
    cur_ver = int(row[0]) if row else 0
    if cur_ver < INVEST_SEED_VERSION:
        c.execute("DELETE FROM pricing_stones_invest")
        c.execute("DELETE FROM pricing_stone_origins")
        c.execute("DELETE FROM pricing_stone_treatments")
        c.execute("DELETE FROM pricing_stone_colors")
        for key, s in _INVEST_V2.items():
            for band in ("B1", "B2", "B3", "B4", "B5"):
                c.execute(
                    "INSERT INTO pricing_stones_invest (stone_key, stone_name, band, price_floor, price_ceil) VALUES (?,?,?,?,?)",
                    (key, s["name"], band, s["floor"][band], s["ceil"][band]))
            for o, m in s["origins"].items():
                c.execute("INSERT INTO pricing_stone_origins (stone_key, origin, multiplier) VALUES (?,?,?)", (key, o, m))
            for t, m in s["treatments"].items():
                c.execute("INSERT INTO pricing_stone_treatments (stone_key, treatment, multiplier) VALUES (?,?,?)", (key, t, m))
            for cq, m in s["colors"].items():
                c.execute("INSERT INTO pricing_stone_colors (stone_key, color_quality, multiplier) VALUES (?,?,?)", (key, cq, m))
        c.execute("INSERT OR REPLACE INTO pricing_meta (key, value) VALUES ('invest_seed_version', ?)", (str(INVEST_SEED_VERSION),))

    if not c.execute("SELECT 1 FROM pricing_stones_commercial LIMIT 1").fetchone():
        c.executemany("INSERT OR IGNORE INTO pricing_stones_commercial (stone_key, stone_name, price_min, price_max) VALUES (?,?,?,?)", _SEED_STONES_COMMERCIAL)

    if not c.execute("SELECT 1 FROM pricing_sidestones LIMIT 1").fetchone():
        c.executemany("INSERT OR IGNORE INTO pricing_sidestones (label, price_min, price_max) VALUES (?,?,?)", _SEED_SIDESTONES)

    if not c.execute("SELECT 1 FROM pricing_plating LIMIT 1").fetchone():
        c.executemany("INSERT OR IGNORE INTO pricing_plating (label, price_min, price_max) VALUES (?,?,?)", _SEED_PLATING)

    if not c.execute("SELECT 1 FROM pricing_commercial_carat LIMIT 1").fetchone():
        c.executemany(
            "INSERT OR IGNORE INTO pricing_commercial_carat (stone_key, ct_label, stone_name, price_min, price_max) VALUES (?,?,?,?,?)",
            _SEED_COMMERCIAL_CARAT
        )

    if not c.execute("SELECT 1 FROM pricing_labor_config LIMIT 1").fetchone():
        c.executemany("INSERT OR IGNORE INTO pricing_labor_config (key, value) VALUES (?,?)", _SEED_LABOR_CONFIG)

    if not c.execute("SELECT 1 FROM pricing_sidestones_v2 LIMIT 1").fetchone():
        c.executemany(
            "INSERT OR IGNORE INTO pricing_sidestones_v2 (stone_type, qty_band, price_min, price_max) VALUES (?,?,?,?)",
            _SEED_SIDESTONES_V2
        )

    # Always ensure extended weight rows exist (safe to run every restart)
    for lbl, wmin, wmax in [("特重 (20–35g)", 20.0, 35.0), ("超重 (35–50g)", 35.0, 50.0)]:
        c.execute("INSERT OR IGNORE INTO pricing_weights (label, weight_min, weight_max) VALUES (?,?,?)", (lbl, wmin, wmax))

    conn.commit()
    conn.close()


_init_db()


# ─── API Models ────────────────────────────────────────────────
class MetalUpdate(BaseModel):
    price_per_g: int

class LaborUpdate(BaseModel):
    price_min: int
    price_max: int

class StoneBandUpdate(BaseModel):
    price_floor: int
    price_ceil: int

class CommercialStoneUpdate(BaseModel):
    price_min: int
    price_max: int

class SidestoneUpdate(BaseModel):
    price_min: int
    price_max: int


# ─── GET all (used by frontend to build estimator) ────────────
@router.get("/all")
def get_all_pricing():
    """返回完整估價資料，供前端快取使用。"""
    conn = _conn()
    c = conn.cursor()

    metals = {r["material"]: r["price_per_g"]
              for r in c.execute("SELECT material, price_per_g FROM pricing_metals").fetchall()}

    weights_rows = c.execute("SELECT label, weight_min, weight_max FROM pricing_weights ORDER BY weight_min").fetchall()
    weights = {r["label"]: [r["weight_min"], r["weight_max"]] for r in weights_rows}

    labor_rows = c.execute("SELECT category, complexity, price_min, price_max FROM pricing_labor").fetchall()
    labor: dict = {}
    for r in labor_rows:
        labor.setdefault(r["category"], {})[r["complexity"]] = [r["price_min"], r["price_max"]]

    invest_rows = c.execute(
        "SELECT stone_key, stone_name, band, price_floor, price_ceil FROM pricing_stones_invest ORDER BY stone_key, band"
    ).fetchall()
    origins_rows  = c.execute("SELECT stone_key, origin, multiplier FROM pricing_stone_origins").fetchall()
    treat_rows    = c.execute("SELECT stone_key, treatment, multiplier FROM pricing_stone_treatments").fetchall()
    color_rows    = c.execute("SELECT stone_key, color_quality, multiplier FROM pricing_stone_colors").fetchall()

    stones_invest: dict = {}
    for r in invest_rows:
        k = r["stone_key"]
        if k not in stones_invest:
            stones_invest[k] = {"name": r["stone_name"], "floor": {}, "ceil": {}, "origins": {}, "treatments": {}, "colors": {}}
        stones_invest[k]["floor"][r["band"]] = r["price_floor"]
        stones_invest[k]["ceil"][r["band"]]  = r["price_ceil"]
    for r in origins_rows:
        k = r["stone_key"]
        if k in stones_invest:
            stones_invest[k]["origins"][r["origin"]] = r["multiplier"]
    for r in treat_rows:
        k = r["stone_key"]
        if k in stones_invest:
            stones_invest[k]["treatments"][r["treatment"]] = r["multiplier"]
    for r in color_rows:
        k = r["stone_key"]
        if k in stones_invest:
            stones_invest[k]["colors"][r["color_quality"]] = r["multiplier"]

    commercial_rows = c.execute("SELECT stone_key, stone_name, price_min, price_max FROM pricing_stones_commercial").fetchall()
    stones_commercial = {r["stone_key"]: {"name": r["stone_name"], "range": [r["price_min"], r["price_max"]]}
                         for r in commercial_rows}

    sidestone_rows = c.execute("SELECT label, price_min, price_max FROM pricing_sidestones ORDER BY price_min").fetchall()
    sidestones = {r["label"]: [r["price_min"], r["price_max"]] for r in sidestone_rows}

    carat_rows = c.execute(
        "SELECT stone_key, ct_label, stone_name, price_min, price_max FROM pricing_commercial_carat ORDER BY stone_key, ct_label"
    ).fetchall()
    commercial_carat: dict = {}
    for r in carat_rows:
        k = r["stone_key"]
        if k not in commercial_carat:
            commercial_carat[k] = {"name": r["stone_name"]}
        commercial_carat[k][r["ct_label"]] = [r["price_min"], r["price_max"]]

    plating_rows = c.execute("SELECT label, price_min, price_max FROM pricing_plating ORDER BY price_min").fetchall()
    plating = {r["label"]: [r["price_min"], r["price_max"]] for r in plating_rows}

    lc_rows = c.execute("SELECT key, value FROM pricing_labor_config").fetchall()
    labor_config = {r["key"]: r["value"] for r in lc_rows}

    sv2_rows = c.execute(
        "SELECT stone_type, qty_band, price_min, price_max FROM pricing_sidestones_v2"
    ).fetchall()
    sidestones_v2: dict = {}
    for r in sv2_rows:
        sidestones_v2.setdefault(r["stone_type"], {})[r["qty_band"]] = [r["price_min"], r["price_max"]]

    metals_updated = c.execute("SELECT MIN(updated_at) FROM pricing_metals").fetchone()[0]

    conn.close()
    return {
        "metals": metals,
        "weights": weights,
        "labor": labor,
        "labor_config": labor_config,
        "stones_invest": stones_invest,
        "stones_commercial": stones_commercial,
        "commercial_carat": commercial_carat,
        "sidestones": sidestones,
        "sidestones_v2": sidestones_v2,
        "plating": plating,
        "metals_last_updated": metals_updated,
    }


# ─── Admin update endpoints ────────────────────────────────────
@router.put("/metals/{material}")
def update_metal(material: str, body: MetalUpdate, _user=Depends(require_admin)):
    conn = _conn()
    r = conn.execute("SELECT id FROM pricing_metals WHERE material=?", (material,)).fetchone()
    if not r:
        conn.close()
        raise HTTPException(404, "Material not found")
    conn.execute("UPDATE pricing_metals SET price_per_g=?, updated_at=CURRENT_TIMESTAMP WHERE material=?",
                 (body.price_per_g, material))
    conn.commit()
    conn.close()
    return {"ok": True}


@router.put("/labor/{category}/{complexity}")
def update_labor(category: str, complexity: str, body: LaborUpdate, _user=Depends(require_admin)):
    conn = _conn()
    r = conn.execute("SELECT id FROM pricing_labor WHERE category=? AND complexity=?", (category, complexity)).fetchone()
    if not r:
        conn.close()
        raise HTTPException(404, "Labor entry not found")
    conn.execute("UPDATE pricing_labor SET price_min=?, price_max=? WHERE category=? AND complexity=?",
                 (body.price_min, body.price_max, category, complexity))
    conn.commit()
    conn.close()
    return {"ok": True}


@router.put("/stones-invest/{stone_key}/{band}")
def update_stone_band(stone_key: str, band: str, body: StoneBandUpdate, _user=Depends(require_admin)):
    conn = _conn()
    r = conn.execute("SELECT id FROM pricing_stones_invest WHERE stone_key=? AND band=?", (stone_key, band)).fetchone()
    if not r:
        conn.close()
        raise HTTPException(404, "Stone band not found")
    conn.execute("UPDATE pricing_stones_invest SET price_floor=?, price_ceil=? WHERE stone_key=? AND band=?",
                 (body.price_floor, body.price_ceil, stone_key, band))
    conn.commit()
    conn.close()
    return {"ok": True}


@router.put("/stones-commercial/{stone_key}")
def update_commercial_stone(stone_key: str, body: CommercialStoneUpdate, _user=Depends(require_admin)):
    conn = _conn()
    r = conn.execute("SELECT id FROM pricing_stones_commercial WHERE stone_key=?", (stone_key,)).fetchone()
    if not r:
        conn.close()
        raise HTTPException(404, "Commercial stone not found")
    conn.execute("UPDATE pricing_stones_commercial SET price_min=?, price_max=? WHERE stone_key=?",
                 (body.price_min, body.price_max, stone_key))
    conn.commit()
    conn.close()
    return {"ok": True}


@router.put("/sidestones/{label}")
def update_sidestone(label: str, body: SidestoneUpdate, _user=Depends(require_admin)):
    conn = _conn()
    r = conn.execute("SELECT id FROM pricing_sidestones WHERE label=?", (label,)).fetchone()
    if not r:
        conn.close()
        raise HTTPException(404, "Sidestone entry not found")
    conn.execute("UPDATE pricing_sidestones SET price_min=?, price_max=? WHERE label=?",
                 (body.price_min, body.price_max, label))
    conn.commit()
    conn.close()
    return {"ok": True}


@router.put("/stones-commercial-carat/{stone_key}/{ct_label}")
def update_commercial_carat(stone_key: str, ct_label: str, body: CommercialStoneUpdate, _user=Depends(require_admin)):
    conn = _conn()
    r = conn.execute("SELECT id FROM pricing_commercial_carat WHERE stone_key=? AND ct_label=?", (stone_key, ct_label)).fetchone()
    if not r:
        conn.close()
        raise HTTPException(404, "Commercial carat entry not found")
    conn.execute("UPDATE pricing_commercial_carat SET price_min=?, price_max=? WHERE stone_key=? AND ct_label=?",
                 (body.price_min, body.price_max, stone_key, ct_label))
    conn.commit()
    conn.close()
    return {"ok": True}


class WeightUpdate(BaseModel):
    weight_min: float
    weight_max: float

@router.put("/weights/{label}")
def update_weight(label: str, body: WeightUpdate, _user=Depends(require_admin)):
    conn = _conn()
    r = conn.execute("SELECT id FROM pricing_weights WHERE label=?", (label,)).fetchone()
    if not r:
        conn.close()
        raise HTTPException(404, "Weight entry not found")
    conn.execute("UPDATE pricing_weights SET weight_min=?, weight_max=? WHERE label=?",
                 (body.weight_min, body.weight_max, label))
    conn.commit()
    conn.close()
    return {"ok": True}


class PlatingUpdate(BaseModel):
    price_min: int
    price_max: int

@router.put("/plating/{label}")
def update_plating(label: str, body: PlatingUpdate, _user=Depends(require_admin)):
    conn = _conn()
    r = conn.execute("SELECT id FROM pricing_plating WHERE label=?", (label,)).fetchone()
    if not r:
        conn.close()
        raise HTTPException(404, "Plating entry not found")
    conn.execute("UPDATE pricing_plating SET price_min=?, price_max=? WHERE label=?",
                 (body.price_min, body.price_max, label))
    conn.commit()
    conn.close()
    return {"ok": True}


class MultiplierUpdate(BaseModel):
    multiplier: float

@router.put("/stone-origins/{stone_key}/{origin}")
def update_stone_origin(stone_key: str, origin: str, body: MultiplierUpdate, _user=Depends(require_admin)):
    conn = _conn()
    r = conn.execute("SELECT id FROM pricing_stone_origins WHERE stone_key=? AND origin=?", (stone_key, origin)).fetchone()
    if not r:
        conn.close()
        raise HTTPException(404, "Origin not found")
    conn.execute("UPDATE pricing_stone_origins SET multiplier=? WHERE stone_key=? AND origin=?",
                 (body.multiplier, stone_key, origin))
    conn.commit()
    conn.close()
    return {"ok": True}


@router.put("/stone-treatments/{stone_key}/{treatment}")
def update_stone_treatment(stone_key: str, treatment: str, body: MultiplierUpdate, _user=Depends(require_admin)):
    conn = _conn()
    r = conn.execute("SELECT id FROM pricing_stone_treatments WHERE stone_key=? AND treatment=?", (stone_key, treatment)).fetchone()
    if not r:
        conn.close()
        raise HTTPException(404, "Treatment not found")
    conn.execute("UPDATE pricing_stone_treatments SET multiplier=? WHERE stone_key=? AND treatment=?",
                 (body.multiplier, stone_key, treatment))
    conn.commit()
    conn.close()
    return {"ok": True}


@router.put("/stone-colors/{stone_key}/{color_quality}")
def update_stone_color(stone_key: str, color_quality: str, body: MultiplierUpdate, _user=Depends(require_admin)):
    conn = _conn()
    r = conn.execute("SELECT id FROM pricing_stone_colors WHERE stone_key=? AND color_quality=?", (stone_key, color_quality)).fetchone()
    if not r:
        conn.close()
        raise HTTPException(404, "Color quality not found")
    conn.execute("UPDATE pricing_stone_colors SET multiplier=? WHERE stone_key=? AND color_quality=?",
                 (body.multiplier, stone_key, color_quality))
    conn.commit()
    conn.close()
    return {"ok": True}


class LaborConfigUpdate(BaseModel):
    value: float

class SidestonesV2Update(BaseModel):
    price_min: int
    price_max: int

@router.put("/labor-config/{key}")
def update_labor_config(key: str, body: LaborConfigUpdate, _user=Depends(require_admin)):
    conn = _conn()
    conn.execute("INSERT OR REPLACE INTO pricing_labor_config (key, value) VALUES (?,?)", (key, body.value))
    conn.commit()
    conn.close()
    return {"ok": True}

@router.put("/sidestones-v2/{stone_type}/{qty_band}")
def update_sidestone_v2(stone_type: str, qty_band: str, body: SidestonesV2Update, _user=Depends(require_admin)):
    conn = _conn()
    conn.execute(
        "INSERT OR REPLACE INTO pricing_sidestones_v2 (stone_type, qty_band, price_min, price_max) VALUES (?,?,?,?)",
        (stone_type, qty_band, body.price_min, body.price_max)
    )
    conn.commit()
    conn.close()
    return {"ok": True}


@router.get("/metals-spot")
def get_metals_spot():
    """從 Yahoo Finance 取得金、銀、鉑現貨價（TWD/g）。"""
    import urllib.request

    TROY_OZ_TO_G = 31.1035
    SYMBOLS = {"gold": "XAUTWD%3DX", "silver": "XAGTWD%3DX", "platinum": "XPTTWD%3DX"}
    spot: dict = {}
    errors: list = []

    for metal, symbol in SYMBOLS.items():
        try:
            url = f"https://query2.finance.yahoo.com/v8/finance/chart/{symbol}?interval=1d&range=1d"
            req = urllib.request.Request(url, headers={
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
                "Accept": "application/json",
            })
            with urllib.request.urlopen(req, timeout=10) as resp:
                import json as _json
                data = _json.loads(resp.read())
            price_toz = data["chart"]["result"][0]["meta"]["regularMarketPrice"]
            spot[metal] = round(price_toz / TROY_OZ_TO_G, 1)
        except Exception as e:
            errors.append(f"{metal}: {e}")

    suggested: dict = {}
    if "gold" in spot:
        g = spot["gold"]

        suggested["14K金"] = round(g * 14 / 24)
        suggested["18K金"] = round(g * 18 / 24)
    if "silver" in spot:
        suggested["925銀"] = round(spot["silver"] * 0.925)
    if "platinum" in spot:
        suggested["Pt950"] = round(spot["platinum"] * 0.95)

    return {"spot": spot, "suggested": suggested, "errors": errors}
