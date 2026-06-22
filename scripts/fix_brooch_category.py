"""fix_brooch_category.py
對所有 category='胸針' 的照片重跑 CLIP 品項分類。
只改 category 欄位，其他標籤不動。

執行：
    python3 -m scripts.fix_brooch_category
"""
import sqlite3
import sys
import torch
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config.settings import SQLITE_PATH, PROCESSED_DIR, BASE_DIR
from scripts.classify import load_model, load_prompts, _get_text_features, THRESHOLDS, UNDECIDED
from PIL import Image

FULL_DIR = PROCESSED_DIR / "full"
CLASSIFIED_DIR = BASE_DIR / "data" / "02_classified"
_device = "mps" if torch.backends.mps.is_available() else "cpu"


def get_image_path(row) -> Path | None:
    full_path = Path(row["full_path"]) if row["full_path"] else None
    if full_path and full_path.exists():
        return full_path
    fn = row["filename"]
    if fn:
        p = FULL_DIR / fn
        if p.exists():
            return p
        p = CLASSIFIED_DIR / fn
        if p.exists():
            return p
    return None


def classify_category(image_path: Path) -> str:
    model, preprocess, tokenizer, logit_scale = load_model()
    prompts_map = load_prompts()
    cat_prompts = prompts_map.get("category", {})
    labels  = list(cat_prompts.keys())
    prompts = list(cat_prompts.values())

    image = Image.open(image_path).convert("RGB")
    image_input = preprocess(image).unsqueeze(0).to(_device)

    with torch.no_grad():
        img_feat = model.encode_image(image_input)
        img_feat /= img_feat.norm(dim=-1, keepdim=True)
        text_feat = _get_text_features("category", prompts, tokenizer, model)
        scores = (img_feat @ text_feat.T * logit_scale).softmax(dim=-1)[0].cpu().tolist()

    sorted_s = sorted(scores, reverse=True)
    top1, top2 = sorted_s[0], (sorted_s[1] if len(sorted_s) > 1 else 0.0)
    best_label = labels[scores.index(top1)]
    thr = THRESHOLDS.get("category", {"conf": 0.5, "margin": 0.10})
    if top1 < thr["conf"] or (top1 - top2) < thr["margin"]:
        return UNDECIDED
    return best_label


def main():
    conn = sqlite3.connect(SQLITE_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT id, filename, full_path FROM photos WHERE category='胸針'"
    ).fetchall()
    total = len(rows)
    print(f"共 {total} 張 category='胸針' 照片，開始重跑 CLIP 品項分類…\n")

    changed = []
    skipped = []

    for i, row in enumerate(rows, 1):
        img_path = get_image_path(row)
        if img_path is None:
            skipped.append(row["id"])
            print(f"[{i}/{total}] id={row['id']} 找不到圖片，跳過")
            continue

        try:
            new_cat = classify_category(img_path)
        except Exception as e:
            skipped.append(row["id"])
            print(f"[{i}/{total}] id={row['id']} 分類失敗：{e}")
            continue

        status = "→ " + new_cat if new_cat != "胸針" else "  (仍是胸針)"
        print(f"[{i}/{total}] id={row['id']}  {status}")

        if new_cat != "胸針":
            changed.append((new_cat, row["id"]))

    print(f"\n分析完畢。")
    print(f"  需要更新：{len(changed)} 張")
    print(f"  保留胸針：{total - len(changed) - len(skipped)} 張")
    print(f"  找不到圖：{len(skipped)} 張")

    if not changed:
        print("沒有需要更新的項目。")
        conn.close()
        return

    # 統計各新類別
    from collections import Counter
    counter = Counter(cat for cat, _ in changed)
    print("\n各新品項分佈：")
    for cat, cnt in sorted(counter.items(), key=lambda x: -x[1]):
        print(f"  {cat}: {cnt} 張")

    ans = input("\n確認更新以上 {} 張照片的 category？(y/N) ".format(len(changed)))
    if ans.strip().lower() != "y":
        print("取消，未做任何修改。")
        conn.close()
        return

    conn.executemany("UPDATE photos SET category=? WHERE id=?", changed)
    conn.commit()
    print(f"✅ 已更新 {len(changed)} 張照片的品項標籤。")
    conn.close()


if __name__ == "__main__":
    main()
