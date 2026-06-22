"""fix_brooch_category.py
對所有 category='胸針' 的照片做重新分類：
  1. 像素分析：去背白底照片頂部有細長突起（吊環）→ 判為墜子（項鍊）
  2. 像素分析：圖中有兩個相似且對稱的物件 → 判為耳釘
  3. 無法判斷時才用 CLIP

執行：
    python3 scripts/fix_brooch_category.py
"""
import sqlite3
import sys
import numpy as np
import torch
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config.settings import SQLITE_PATH, PROCESSED_DIR, BASE_DIR
from scripts.classify import load_model, load_prompts, _get_text_features, THRESHOLDS, UNDECIDED
from PIL import Image

FULL_DIR = PROCESSED_DIR / "full"
CLASSIFIED_DIR = BASE_DIR / "data" / "02_classified"
_device = "mps" if torch.backends.mps.is_available() else "cpu"


def get_image_path(row) -> Optional[Path]:
    full_path = Path(row["full_path"]) if row["full_path"] else None
    if full_path and full_path.exists():
        return full_path
    fn = row["filename"]
    if fn:
        for d in [FULL_DIR, CLASSIFIED_DIR]:
            p = d / fn
            if p.exists():
                return p
    return None


def _fg_mask(img_rgb: np.ndarray, threshold: int = 240) -> np.ndarray:
    """回傳非白底的 foreground mask（True = 有物件）"""
    return np.any(img_rgb < threshold, axis=2)


def has_pendant_bail(img_path: Path) -> bool:
    """
    偵測墜子吊環：去背白底照片頂部中央有細長突起。
    原理：物件頂部 10% 的橫向寬度遠小於物件中段寬度。
    """
    try:
        img = Image.open(img_path).convert("RGB")
        arr = np.array(img)
        mask = _fg_mask(arr)
        rows_any = np.where(mask.any(axis=1))[0]
        if len(rows_any) == 0:
            return False
        top_row, bot_row = rows_any[0], rows_any[-1]
        obj_h = bot_row - top_row
        if obj_h < 20:
            return False

        # 物件中段寬度（高度 30%~70% 處）
        mid_top = top_row + int(obj_h * 0.30)
        mid_bot = top_row + int(obj_h * 0.70)
        mid_widths = [mask[r].sum() for r in range(mid_top, mid_bot)]
        mid_w = np.median(mid_widths) if mid_widths else 0

        # 頂部 10% 最大寬度
        bail_bot = top_row + max(int(obj_h * 0.10), 5)
        bail_widths = [mask[r].sum() for r in range(top_row, bail_bot)]
        bail_w = max(bail_widths) if bail_widths else 0

        # 吊環特徵：頂部寬度 < 中段寬度的 40%，且頂部有前景
        return (bail_w > 0) and (bail_w < mid_w * 0.40)
    except Exception:
        return False


def has_earring_pair(img_path: Path) -> bool:
    """
    偵測耳環成對：前景分成左右兩塊，各自的寬度相近，且中間有明顯空白。
    """
    try:
        img = Image.open(img_path).convert("RGB")
        arr = np.array(img)
        mask = _fg_mask(arr)
        W = mask.shape[1]

        # 各欄的前景像素數
        col_sum = mask.sum(axis=0)
        # 左半 / 右半各自的最大密度欄
        left_max  = col_sum[:W//2].max()
        right_max = col_sum[W//2:].max()
        # 中間 20% 區段的前景密度
        mid_l, mid_r = int(W*0.40), int(W*0.60)
        mid_density = col_sum[mid_l:mid_r].mean()

        if left_max == 0 or right_max == 0:
            return False

        # 兩半都有物件，且中間相對稀疏
        ratio = min(left_max, right_max) / max(left_max, right_max)
        return ratio > 0.35 and mid_density < min(left_max, right_max) * 0.50
    except Exception:
        return False


def classify_category_clip(image_path: Path) -> str:
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


def detect_category(img_path: Path) -> tuple:
    """回傳 (新品項, 方法)"""
    if has_pendant_bail(img_path):
        return "項鍊", "bail"
    if has_earring_pair(img_path):
        return "耳釘", "pair"
    clip_result = classify_category_clip(img_path)
    return clip_result, "clip"


def main():
    conn = sqlite3.connect(SQLITE_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT id, filename, full_path FROM photos WHERE category='胸針'"
    ).fetchall()
    total = len(rows)
    print(f"共 {total} 張 category='胸針' 照片，開始分析…\n")

    changed = []
    skipped = []
    method_counts = {"bail": 0, "pair": 0, "clip": 0}

    for i, row in enumerate(rows, 1):
        img_path = get_image_path(row)
        if img_path is None:
            skipped.append(row["id"])
            print(f"[{i}/{total}] id={row['id']} 找不到圖片，跳過")
            continue

        try:
            new_cat, method = detect_category(img_path)
        except Exception as e:
            skipped.append(row["id"])
            print(f"[{i}/{total}] id={row['id']} 失敗：{e}")
            continue

        method_counts[method] += 1
        if new_cat != "胸針":
            status = f"→ {new_cat} [{method}]"
            changed.append((new_cat, row["id"]))
        else:
            status = f"  (仍是胸針) [{method}]"
        print(f"[{i}/{total}] id={row['id']}  {status}")

    print(f"\n分析完畢。")
    print(f"  需要更新：{len(changed)} 張")
    print(f"  保留胸針：{total - len(changed) - len(skipped)} 張")
    print(f"  找不到圖：{len(skipped)} 張")
    print(f"  偵測方法：吊環={method_counts['bail']}  成對={method_counts['pair']}  CLIP={method_counts['clip']}")

    if not changed:
        print("沒有需要更新的項目。")
        conn.close()
        return

    from collections import Counter
    counter = Counter(cat for cat, _ in changed)
    print("\n各新品項分佈：")
    for cat, cnt in sorted(counter.items(), key=lambda x: -x[1]):
        print(f"  {cat}: {cnt} 張")

    ans = input(f"\n確認更新以上 {len(changed)} 張照片的 category？(y/N) ")
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
