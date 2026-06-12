"""export_static.py - 產生 GitHub Pages 靜態資產

執行：python3 scripts/export_static.py

產出：
  docs/photos.json   所有照片的標籤資料
  docs/thumbs/       320px 縮圖（有快取，不重複生成）
"""
import json
import sqlite3
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config.settings import BASE_DIR, SQLITE_PATH

OUT_DIR    = BASE_DIR / "docs"
THUMBS_DIR = OUT_DIR / "thumbs"
THUMBS_DIR.mkdir(parents=True, exist_ok=True)

FIELDS = [
    "id","filename","category","style","color","metal_color",
    "gemstone","material","price_band","setting_amount",
    "craft_complexity","stone_size","stone_shape","full_path",
]

def make_thumb(photo_id: int, full_path: Path, size: int = 320) -> bool:
    out = THUMBS_DIR / f"{photo_id}.jpg"
    if out.exists():
        return True
    if not full_path or not full_path.exists():
        return False
    try:
        from PIL import Image
        img = Image.open(full_path).convert("RGB")
        img.thumbnail((size, size), Image.LANCZOS)
        img.save(out, "JPEG", quality=82, optimize=True)
        return True
    except Exception as e:
        print(f"  ⚠ {photo_id}: {e}")
        return False

def main():
    conn = sqlite3.connect(SQLITE_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT * FROM photos ORDER BY id").fetchall()
    conn.close()
    print(f"共 {len(rows)} 張照片")

    photos = []
    t0 = time.time()
    ok = skip = 0

    for i, row in enumerate(rows, 1):
        d = dict(row)
        pid = d["id"]
        full_path = Path(d.get("full_path") or "")

        has_thumb = make_thumb(pid, full_path)
        if has_thumb:
            ok += 1
        else:
            skip += 1

        photos.append({
            "id":               pid,
            "filename":         d.get("filename"),
            "thumb_url":        f"thumbs/{pid}.jpg" if has_thumb else None,
            "category":         d.get("category"),
            "style":            d.get("style"),
            "color":            d.get("color"),
            "metal_color":      d.get("metal_color"),
            "gemstone":         d.get("gemstone"),
            "material":         d.get("material"),
            "price_band":       d.get("price_band"),
            "setting_amount":   d.get("setting_amount"),
            "craft_complexity": d.get("craft_complexity"),
            "stone_size":       d.get("stone_size"),
            "stone_shape":      d.get("stone_shape"),
        })

        if i % 200 == 0:
            elapsed = time.time() - t0
            eta = elapsed / i * (len(rows) - i)
            print(f"  {i}/{len(rows)}  ETA {eta:.0f}s")

    photos_json = OUT_DIR / "photos.json"
    photos_json.write_text(
        json.dumps(photos, ensure_ascii=False, separators=(',', ':')),
        encoding="utf-8"
    )

    elapsed = time.time() - t0
    size_mb = sum(f.stat().st_size for f in THUMBS_DIR.glob("*.jpg")) / 1024 / 1024
    print(f"\n✅ 完成 ({elapsed:.0f}s)")
    print(f"  縮圖：{ok} 張，跳過：{skip} 張")
    print(f"  thumbs/ 目錄大小：{size_mb:.1f} MB")
    print(f"  photos.json：{photos_json.stat().st_size/1024:.0f} KB")
    print(f"\n下一步：")
    print(f"  git add docs/")
    print(f"  git commit -m 'Update static export'")
    print(f"  git push")

if __name__ == "__main__":
    main()
