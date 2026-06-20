"""pricing.py - 估價資料庫（獨立於照片資料庫）"""
import json
import sqlite3
import sys
from pathlib import Path
from typing import Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

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
    # Spot (Jun 2026): 24K=4781/g, 999Ag=83/g, Pt999=2213/g  ×karat×1.5 retail
    ("925銀",  115),   # 83×0.925×1.5≈115
    ("9K金",  2690),   # 4781×0.375×1.5≈2690
    ("14K金", 4200),   # 4781×0.585×1.5≈4200
    ("18K金", 5400),   # 4781×0.75×1.5≈5390→5400
    ("Pt950", 3150),   # 2213×0.95×1.5≈3154→3150
]

# Market reference for frontend "reset to market" button
METALS_MARKET_REF = {
    "925銀": 115, "9K金": 2690, "14K金": 4200, "18K金": 5400, "Pt950": 3150
}

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
    ("手鍊",   "極簡",  3000,  5000),
    ("手鍊",   "簡單",  5000,  8000),
    ("手鍊",   "中等",  8000, 13000),
    ("手鍊",   "複雜", 13000, 22000),
    ("手鍊",   "精工", 22000, 40000),
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

_SEED_STONES_INVEST = [
    # (key, name, band, price_floor, price_ceil)
    ("RUBY",     "紅寶石",   "B1",  40000,  200000),
    ("RUBY",     "紅寶石",   "B2", 120000,  600000),
    ("RUBY",     "紅寶石",   "B3", 300000, 1500000),
    ("RUBY",     "紅寶石",   "B4", 800000, 4000000),
    ("RUBY",     "紅寶石",   "B5",2000000,10000000),
    ("SAPPHIRE", "藍寶石",   "B1",  30000,  150000),
    ("SAPPHIRE", "藍寶石",   "B2",  80000,  400000),
    ("SAPPHIRE", "藍寶石",   "B3", 200000, 1000000),
    ("SAPPHIRE", "藍寶石",   "B4", 500000, 2500000),
    ("SAPPHIRE", "藍寶石",   "B5",1200000, 6000000),
    ("EMERALD",  "祖母綠",   "B1",  20000,  100000),
    ("EMERALD",  "祖母綠",   "B2",  60000,  300000),
    ("EMERALD",  "祖母綠",   "B3", 150000,  750000),
    ("EMERALD",  "祖母綠",   "B4", 400000, 2000000),
    ("EMERALD",  "祖母綠",   "B5",1000000, 5000000),
    ("DIAMOND",  "鑽石",     "B1",  15000,   80000),
    ("DIAMOND",  "鑽石",     "B2",  50000,  250000),
    ("DIAMOND",  "鑽石",     "B3", 150000,  700000),
    ("DIAMOND",  "鑽石",     "B4", 400000, 1800000),
    ("DIAMOND",  "鑽石",     "B5",1000000, 4500000),
    ("ALEXANDRITE","亞歷山大石","B1",50000, 300000),
    ("ALEXANDRITE","亞歷山大石","B2",150000,800000),
    ("ALEXANDRITE","亞歷山大石","B3",400000,2000000),
    ("ALEXANDRITE","亞歷山大石","B4",1000000,5000000),
    ("ALEXANDRITE","亞歷山大石","B5",2500000,12000000),
    ("TANZANITE", "坦桑石",   "B1",  15000,   80000),
    ("TANZANITE", "坦桑石",   "B2",  40000,  200000),
    ("TANZANITE", "坦桑石",   "B3", 100000,  500000),
    ("TANZANITE", "坦桑石",   "B4", 250000, 1200000),
    ("TANZANITE", "坦桑石",   "B5", 600000, 3000000),
]

# (key, origin, multiplier)
_SEED_STONE_ORIGINS = [
    ("RUBY",      "緬甸",   1.5),
    ("RUBY",      "莫桑比克", 1.0),
    ("RUBY",      "泰國",   0.7),
    ("RUBY",      "其他",   0.8),
    ("SAPPHIRE",  "斯里蘭卡", 1.3),
    ("SAPPHIRE",  "克什米爾", 2.0),
    ("SAPPHIRE",  "緬甸",   1.2),
    ("SAPPHIRE",  "馬達加斯加",0.8),
    ("SAPPHIRE",  "泰國",   0.7),
    ("SAPPHIRE",  "其他",   0.85),
    ("EMERALD",   "哥倫比亞", 1.5),
    ("EMERALD",   "尚比亞",  0.9),
    ("EMERALD",   "巴西",   0.75),
    ("EMERALD",   "其他",   0.7),
    ("ALEXANDRITE","俄羅斯", 2.0),
    ("ALEXANDRITE","斯里蘭卡",1.2),
    ("ALEXANDRITE","巴西",  0.9),
    ("TANZANITE", "坦尚尼亞",1.0),
]

# (key, treatment, multiplier)
_SEED_STONE_TREATMENTS = [
    ("RUBY",     "無燒",  1.5),
    ("RUBY",     "有燒",  1.0),
    ("RUBY",     "鉛玻璃", 0.3),
    ("SAPPHIRE", "無燒",  1.4),
    ("SAPPHIRE", "有燒",  1.0),
    ("EMERALD",  "無注油", 1.4),
    ("EMERALD",  "輕微注油",1.0),
    ("EMERALD",  "中度注油",0.7),
    ("EMERALD",  "重度注油",0.4),
    ("DIAMOND",  "無處理", 1.0),
    ("DIAMOND",  "輻照彩鑽",0.5),
]

# (key, color_quality, multiplier)
_SEED_STONE_COLORS = [
    ("RUBY",      "頂級紅/鴿血紅", 1.8),
    ("RUBY",      "優質紅",        1.2),
    ("RUBY",      "標準紅",        1.0),
    ("RUBY",      "粉紅/淺紅",     0.6),
    ("SAPPHIRE",  "皇家藍/矢車菊藍",1.6),
    ("SAPPHIRE",  "優質藍",        1.2),
    ("SAPPHIRE",  "標準藍",        1.0),
    ("SAPPHIRE",  "淺藍/灰藍",     0.65),
    ("EMERALD",   "頂級綠",        1.5),
    ("EMERALD",   "優質綠",        1.1),
    ("EMERALD",   "標準綠",        1.0),
    ("EMERALD",   "淺綠/黃綠",     0.6),
    ("TANZANITE", "頂級藍紫",      1.5),
    ("TANZANITE", "優質藍",        1.1),
    ("TANZANITE", "標準",          1.0),
    ("TANZANITE", "淺色",          0.65),
]

_SEED_STONES_COMMERCIAL = [
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
    """)

    # Seed only if tables are empty
    if not c.execute("SELECT 1 FROM pricing_metals LIMIT 1").fetchone():
        c.executemany("INSERT OR IGNORE INTO pricing_metals (material, price_per_g) VALUES (?,?)", _SEED_METALS)

    if not c.execute("SELECT 1 FROM pricing_weights LIMIT 1").fetchone():
        c.executemany("INSERT OR IGNORE INTO pricing_weights (label, weight_min, weight_max) VALUES (?,?,?)", _SEED_WEIGHTS)

    if not c.execute("SELECT 1 FROM pricing_labor LIMIT 1").fetchone():
        c.executemany("INSERT OR IGNORE INTO pricing_labor (category, complexity, price_min, price_max) VALUES (?,?,?,?)", _SEED_LABOR)

    if not c.execute("SELECT 1 FROM pricing_stones_invest LIMIT 1").fetchone():
        c.executemany("INSERT OR IGNORE INTO pricing_stones_invest (stone_key, stone_name, band, price_floor, price_ceil) VALUES (?,?,?,?,?)", _SEED_STONES_INVEST)

    if not c.execute("SELECT 1 FROM pricing_stone_origins LIMIT 1").fetchone():
        c.executemany("INSERT OR IGNORE INTO pricing_stone_origins (stone_key, origin, multiplier) VALUES (?,?,?)", _SEED_STONE_ORIGINS)

    if not c.execute("SELECT 1 FROM pricing_stone_treatments LIMIT 1").fetchone():
        c.executemany("INSERT OR IGNORE INTO pricing_stone_treatments (stone_key, treatment, multiplier) VALUES (?,?,?)", _SEED_STONE_TREATMENTS)

    if not c.execute("SELECT 1 FROM pricing_stone_colors LIMIT 1").fetchone():
        c.executemany("INSERT OR IGNORE INTO pricing_stone_colors (stone_key, color_quality, multiplier) VALUES (?,?,?)", _SEED_STONE_COLORS)

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

    metals_updated = c.execute("SELECT MIN(updated_at) FROM pricing_metals").fetchone()[0]

    conn.close()
    return {
        "metals": metals,
        "metals_market_ref": METALS_MARKET_REF,
        "weights": weights,
        "labor": labor,
        "stones_invest": stones_invest,
        "stones_commercial": stones_commercial,
        "commercial_carat": commercial_carat,
        "sidestones": sidestones,
        "plating": plating,
        "metals_last_updated": metals_updated,
    }


# ─── Admin update endpoints ────────────────────────────────────
@router.put("/metals/{material}")
def update_metal(material: str, body: MetalUpdate):
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
def update_labor(category: str, complexity: str, body: LaborUpdate):
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
def update_stone_band(stone_key: str, band: str, body: StoneBandUpdate):
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
def update_commercial_stone(stone_key: str, body: CommercialStoneUpdate):
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
def update_sidestone(label: str, body: SidestoneUpdate):
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
def update_commercial_carat(stone_key: str, ct_label: str, body: CommercialStoneUpdate):
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
def update_weight(label: str, body: WeightUpdate):
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
def update_plating(label: str, body: PlatingUpdate):
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
def update_stone_origin(stone_key: str, origin: str, body: MultiplierUpdate):
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
def update_stone_treatment(stone_key: str, treatment: str, body: MultiplierUpdate):
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
def update_stone_color(stone_key: str, color_quality: str, body: MultiplierUpdate):
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
        suggested["9K金"]  = round(g * 9  / 24)
        suggested["14K金"] = round(g * 14 / 24)
        suggested["18K金"] = round(g * 18 / 24)
    if "silver" in spot:
        suggested["925銀"] = round(spot["silver"] * 0.925)
    if "platinum" in spot:
        suggested["Pt950"] = round(spot["platinum"] * 0.95)

    return {"spot": spot, "suggested": suggested, "errors": errors}
