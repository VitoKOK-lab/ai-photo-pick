"""batch_reclassify.py - 用 CLIP 批次補齊照片標籤（PIL-free 版）

完全不使用 PIL 讀圖，改用 torchvision.io.decode_jpeg + tensor 正規化，
避免 CMYK / ICC-profile JPEG 需要 numpy 才能解碼的問題。

跑法：
    python3 scripts/batch_reclassify.py
    python3 scripts/batch_reclassify.py --overwrite
"""
import argparse
import sqlite3
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import torch
import torchvision.io as tvio
import torchvision.transforms.functional as TF
import open_clip

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config.settings import SQLITE_PATH
from scripts.classify import load_model, load_prompts, _get_text_features

# CLIP ViT-B/32 正規化常數
_CLIP_MEAN = [0.48145466, 0.4578275,  0.40821073]
_CLIP_STD  = [0.26862954, 0.26130258, 0.27577711]

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
}

CONF_MIN = 0.25   # 低於此信心度存「未定」


def load_as_tensor(img_path: Path, n_px: int = 224) -> torch.Tensor:
    """
    PIL-free 圖片載入 + CLIP 前處理，回傳 (1, C, H, W) float32 tensor。
    先試 tvio.decode_jpeg（最快），失敗再用 sips 轉 PNG 後 tvio.decode_png。
    """
    def _preprocess(t: torch.Tensor) -> torch.Tensor:
        """CHW uint8 → (1,C,n_px,n_px) float32 normalized"""
        if t.shape[0] == 1:           # 灰階 → RGB
            t = t.repeat(3, 1, 1)
        elif t.shape[0] == 4:         # RGBA → RGB
            t = t[:3]
        # Resize shortest side to n_px, then center-crop
        h, w = t.shape[1], t.shape[2]
        scale = n_px / min(h, w)
        nh, nw = max(n_px, int(h * scale)), max(n_px, int(w * scale))
        t = TF.resize(t, [nh, nw], antialias=True)
        top  = (t.shape[1] - n_px) // 2
        left = (t.shape[2] - n_px) // 2
        t = t[:, top:top+n_px, left:left+n_px]
        t = t.float() / 255.0
        t = TF.normalize(t, _CLIP_MEAN, _CLIP_STD)
        return t.unsqueeze(0)

    # --- 方法 1: torchvision JPEG decoder (no PIL, no numpy) ---
    try:
        raw = torch.frombuffer(bytearray(img_path.read_bytes()), dtype=torch.uint8)
        t   = tvio.decode_jpeg(raw, tvio.ImageReadMode.RGB)
        return _preprocess(t)
    except Exception:
        pass

    # --- 方法 2: torchvision PNG decoder via sips conversion ---
    tmp = Path(tempfile.mktemp(suffix=".png"))
    try:
        r = subprocess.run(
            ["/usr/bin/sips", "-s", "format", "png", str(img_path), "--out", str(tmp)],
            capture_output=True, timeout=20,
        )
        if r.returncode == 0 and tmp.exists():
            raw = torch.frombuffer(bytearray(tmp.read_bytes()), dtype=torch.uint8)
            t   = tvio.decode_png(raw, tvio.ImageReadMode.RGB)
            return _preprocess(t)
    finally:
        tmp.unlink(missing_ok=True)

    raise OSError(f"無法讀取圖片: {img_path.name}")


def derive_metal_color(material):
    if material in ("18K黃金", "18K玫瑰金"):
        return "金"
    if material in ("18K白金", "925銀", "鉑金"):
        return "銀"
    return None


def needs_any_update(conn, photo_id, overwrite):
    """回傳 True 代表至少有一個欄位需要補。"""
    if overwrite:
        return True
    for col in DIM_TO_COL.values():
        r = conn.execute(f"SELECT {col} FROM photos WHERE id=?", (photo_id,)).fetchone()
        val = r[0] if r else None
        if not val or not str(val).strip() or val == "未定":
            return True
    return False


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()

    conn = sqlite3.connect(SQLITE_PATH)
    conn.row_factory = sqlite3.Row

    for col in ("setting_amount", "craft_complexity", "metal_color", "stone_shape", "stone_size"):
        try:
            conn.execute(f"ALTER TABLE photos ADD COLUMN {col} TEXT")
            conn.commit()
            print(f"[DB] 新增欄位：{col}")
        except Exception:
            pass

    col_info      = conn.execute("PRAGMA table_info(photos)").fetchall()
    existing_cols = {c[1] for c in col_info}

    rows  = conn.execute("SELECT id, full_path FROM photos ORDER BY id").fetchall()
    total = len(rows)
    print(f"[INFO] 共 {total} 張，開始分類…")

    model, preprocess_unused, tokenizer, logit_scale = load_model()
    prompts_map = load_prompts()
    device = next(model.parameters()).device

    done = skipped = errors = 0
    t0 = time.time()

    for row in rows:
        photo_id  = row["id"]
        img_path  = Path(row["full_path"])

        if not img_path.exists():
            skipped += 1; done += 1; continue

        # 若所有欄位都已有值，跳過不跑 CLIP
        if not needs_any_update(conn, photo_id, args.overwrite):
            skipped += 1; done += 1; continue

        # --- 載入圖片 & 跑 CLIP ---
        try:
            image_input = load_as_tensor(img_path).to(device)
        except Exception as e:
            print(f"  [ERR] id={photo_id} 讀圖失敗: {e}")
            errors += 1; done += 1; continue

        try:
            with torch.no_grad():
                img_feat = model.encode_image(image_input)
                img_feat /= img_feat.norm(dim=-1, keepdim=True)
        except Exception as e:
            print(f"  [ERR] id={photo_id} CLIP失敗: {e}")
            errors += 1; done += 1; continue

        # --- 計算各維度分數 ---
        classification = {}
        for dim, label_prompt_map in prompts_map.items():
            if dim not in DIM_TO_COL:
                continue
            labels  = list(label_prompt_map.keys())
            prompts = list(label_prompt_map.values())
            tf      = _get_text_features(dim, prompts, tokenizer, model)
            with torch.no_grad():
                scores = ((img_feat @ tf.T) * logit_scale).softmax(dim=-1)[0].cpu().tolist()
            best_idx = scores.index(max(scores))
            top1     = scores[best_idx]
            classification[dim] = {
                "label":      labels[best_idx] if top1 >= CONF_MIN else "未定",
                "confidence": round(top1, 4),
            }

        # --- 更新 DB ---
        update_fields = {}
        for dim, col in DIM_TO_COL.items():
            if dim not in classification or col not in existing_cols:
                continue
            label = classification[dim]["label"]
            conf  = classification[dim]["confidence"]

            if not args.overwrite:
                r = conn.execute(f"SELECT {col} FROM photos WHERE id=?", (photo_id,)).fetchone()
                existing = r[0] if r else None
                if existing and str(existing).strip() and existing != "未定":
                    continue

            update_fields[col] = label
            conf_col = col + "_confidence"
            if conf_col in existing_cols:
                update_fields[conf_col] = conf

        # material → metal_color 推導
        if "metal_color" in existing_cols:
            mat     = update_fields.get("material") or (classification.get("material") or {}).get("label")
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
            eta     = (total - done) * elapsed / done
            print(f"  {done}/{total} ({done*100//total}%)  已用{elapsed:.0f}s  剩約{eta:.0f}s")

    conn.commit()
    conn.close()

    elapsed = time.time() - t0
    print(f"\n✅ 完成！{done} 張，跳過 {skipped}，錯誤 {errors}，共 {elapsed:.0f} 秒")


if __name__ == "__main__":
    main()
