"""batch_reclassify.py - 用 CLIP 批次補齊照片標籤

批次模式：直接存 top-1 結果（包含「未定」），不等高信心度。
加 --overwrite 旗標可強制覆蓋已有的值。
跑法：
    python3 scripts/batch_reclassify.py
    python3 scripts/batch_reclassify.py --overwrite
"""
import argparse
import sqlite3
import sys
import time
import torch
import open_clip
from pathlib import Path
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config.settings import SQLITE_PATH
from scripts.classify import load_model, load_prompts, _get_text_features

# classify.py 維度 → DB 欄位
DIM_TO_COL = {
    "color":            "color",
    "stone_shape":      "stone_shape",
    "stone_size":       "stone_size",
    "material":         "material",
    "gemstone":         "gemstone",
    "price_band":       "price_band",
    "setting_amount":   "setting_amount",
    "craft_complexity": "craft_complexity",
    "metal_color":      "metal_color",
    # category / style 從資料夾來，不動
}

# 信心度太低時的門檻（低於此值的結果記為「未定」）
# 批次模式較寬鬆：0.25 就存
CONF_MIN = 0.25


def derive_metal_color(material):
    if material in ("18K黃金", "18K玫瑰金"):
        return "金"
    if material in ("18K白金", "925銀", "鉑金"):
        return "銀"
    return None


def open_rgb(img_path):
    """開啟圖片並轉成 RGB，CMYK / 其他格式用 paste 繞過 numpy 依賴"""
    img = Image.open(img_path)
    if img.mode == "RGB":
        return img
    try:
        return img.convert("RGB")
    except Exception:
        # CMYK 或其他格式：paste 到白底 RGB 畫布（顏色稍有偏差但夠用）
        rgb = Image.new("RGB", img.size, (255, 255, 255))
        rgb.paste(img)
        return rgb


def classify_batch_one(img_path, model, preprocess, tokenizer, logit_scale, prompts_map, device):
    """直接回傳 top-1 結果（不過濾未定），信心度低就標為未定"""
    image = open_rgb(img_path)
    image_input = preprocess(image).unsqueeze(0).to(device)
    with torch.no_grad():
        img_feat = model.encode_image(image_input)
        img_feat /= img_feat.norm(dim=-1, keepdim=True)

    result = {}
    for dim, label_prompt_map in prompts_map.items():
        if dim not in DIM_TO_COL and dim != "metal_color":
            continue
        labels  = list(label_prompt_map.keys())
        prompts = list(label_prompt_map.values())
        text_feat = _get_text_features(dim, prompts, tokenizer, model)
        with torch.no_grad():
            raw    = (img_feat @ text_feat.T) * logit_scale
            scores = raw.softmax(dim=-1)[0].cpu().tolist()
        best_idx = scores.index(max(scores))
        top1 = scores[best_idx]
        result[dim] = {
            "label": labels[best_idx] if top1 >= CONF_MIN else "未定",
            "confidence": round(top1, 4),
        }
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--overwrite", action="store_true",
                        help="強制覆蓋已有的標籤值（含非空白欄位）")
    args = parser.parse_args()

    conn = sqlite3.connect(SQLITE_PATH)
    conn.row_factory = sqlite3.Row

    # 確保欄位存在
    for col in ("setting_amount", "craft_complexity", "metal_color", "stone_shape", "stone_size"):
        try:
            conn.execute(f"ALTER TABLE photos ADD COLUMN {col} TEXT")
            conn.commit()
            print(f"[DB] 新增欄位：{col}")
        except Exception:
            pass

    # 取得 DB 欄位清單
    col_info = conn.execute("PRAGMA table_info(photos)").fetchall()
    existing_cols = {c[1] for c in col_info}

    cur = conn.cursor()
    cur.execute("SELECT id, full_path FROM photos ORDER BY id")
    rows = cur.fetchall()
    total = len(rows)
    print(f"[INFO] 共 {total} 張照片，開始分類…")
    if args.overwrite:
        print("[INFO] --overwrite 模式：覆蓋所有欄位")

    # 載入模型（一次）
    model, preprocess, tokenizer, logit_scale = load_model()
    prompts_map = load_prompts()
    device = next(model.parameters()).device

    done = 0
    errors = 0
    skipped = 0
    t0 = time.time()

    for row in rows:
        photo_id  = row["id"]
        full_path = row["full_path"]

        img_path = Path(full_path)
        if not img_path.exists():
            skipped += 1
            done += 1
            continue

        try:
            classification = classify_batch_one(
                img_path, model, preprocess, tokenizer, logit_scale, prompts_map, device
            )
        except Exception as e:
            print(f"  [ERR] id={photo_id}: {e}")
            errors += 1
            done += 1
            continue

        update_fields = {}
        for dim, col in DIM_TO_COL.items():
            if dim not in classification:
                continue
            label = classification[dim]["label"]
            conf  = classification[dim]["confidence"]

            if not args.overwrite:
                cur2 = conn.cursor()
                cur2.execute(f"SELECT {col} FROM photos WHERE id=?", (photo_id,))
                r = cur2.fetchone()
                existing = r[0] if r else None
                if existing and existing.strip() and existing != "未定":
                    continue  # 已有值，跳過

            if col in existing_cols:
                update_fields[col] = label
            conf_col = col + "_confidence"
            if conf_col in existing_cols:
                update_fields[conf_col] = conf

        # material → metal_color 推導
        if "metal_color" in DIM_TO_COL and "metal_color" in existing_cols:
            mat = update_fields.get("material") or classification.get("material", {}).get("label")
            derived = derive_metal_color(mat)
            if derived and ("metal_color" not in update_fields or update_fields.get("metal_color") == "未定"):
                update_fields["metal_color"] = derived

        if update_fields:
            set_clause = ", ".join(f"{k}=?" for k in update_fields)
            conn.execute(
                f"UPDATE photos SET {set_clause}, updated_at=CURRENT_TIMESTAMP WHERE id=?",
                list(update_fields.values()) + [photo_id],
            )

        done += 1
        if done % 100 == 0:
            conn.commit()
            elapsed = time.time() - t0
            per = elapsed / done
            eta = (total - done) * per
            print(f"  {done}/{total} ({done*100//total}%)  已用 {elapsed:.0f}s  剩約 {eta:.0f}s")

    conn.commit()
    conn.close()

    elapsed = time.time() - t0
    print(f"\n✅ 完成！{done} 張，跳過 {skipped}，錯誤 {errors}，共 {elapsed:.0f} 秒")


if __name__ == "__main__":
    main()
