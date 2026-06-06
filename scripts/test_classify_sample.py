"""test_classify_sample.py - 對 100 張試樣跑分類，輸出 CSV 供 review"""
import csv
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config.settings import BASE_DIR
from scripts.classify import classify_one

SAMPLE_DIR = BASE_DIR / "tests" / "test_sample"
OUTPUT_CSV = BASE_DIR / "tests" / "classification_results.csv"

VALID_EXT = (".jpg", ".jpeg", ".png", ".webp", ".heic")

def main():
    images = sorted([p for p in SAMPLE_DIR.iterdir() if p.suffix.lower() in VALID_EXT])
    print(f"Found {len(images)} images in {SAMPLE_DIR}")

    if len(images) == 0:
        print("[ERROR] 沒有試樣照片。請放 100 張代表性照片進 tests/test_sample/")
        return

    rows = []
    start = time.time()

    for i, img_path in enumerate(images, 1):
        try:
            result, _ = classify_one(img_path)
            row = {
                "filename": img_path.name,
                "color": result["color"]["label"],
                "color_conf": result["color"]["confidence"],
                "category": result["category"]["label"],
                "category_conf": result["category"]["confidence"],
                "material": result["material"]["label"],
                "material_conf": result["material"]["confidence"],
                "diamond_status": result["diamond_status"]["label"],
                "diamond_conf": result["diamond_status"]["confidence"],
                "gemstone": result["gemstone"]["label"],
                "gemstone_conf": result["gemstone"]["confidence"],
            }
            rows.append(row)
            print(f"[{i}/{len(images)}] {img_path.name} -> {row['category']}/{row['color']}/{row['gemstone']}")
        except Exception as e:
            print(f"[ERROR] {img_path.name}: {e}")

    elapsed = time.time() - start
    if rows:
        print(f"\n[DONE] {len(rows)} images classified in {elapsed:.1f}s ({elapsed/len(rows):.2f}s per image)")

        with open(OUTPUT_CSV, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=rows[0].keys())
            writer.writeheader()
            writer.writerows(rows)
        print(f"[OK] Results saved to {OUTPUT_CSV}")

if __name__ == "__main__":
    main()
