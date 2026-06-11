"""reclassify_trained.py - 用 KNN 重新分類所有照片並整理檔名

前置條件：先執行 python3 scripts/teach.py（每類標記 15 張）
執行：python3 scripts/reclassify_trained.py

流程：
  1. 載入訓練標記 (data/training_labels.json)
  2. 用 CLIP 生成所有照片的 embedding（有快取，可中斷續跑）
  3. KNN (k=7) 預測每張照片的品項
  4. 移動檔案到新資料夾，更新 DB
  5. 完成後提示執行 reindex_from_disk.py
"""
import json
import shutil
import sqlite3
import sys
import time
from collections import Counter
from pathlib import Path

import numpy as np
import torch
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config.settings import SQLITE_PATH, BASE_DIR

LABELS_FILE      = BASE_DIR / "data" / "training_labels.json"
EMBED_CACHE_FILE = BASE_DIR / "data" / "embeddings_cache.npz"
CLASSIFIED_DIR   = BASE_DIR / "data" / "02_classified"

CATEGORIES = ['戒指', '手鏈', '手鐲', '墜子', '項鍊', '耳釘', '胸針', '其他']
KNN_K = 7


# ── CLIP helpers ──────────────────────────────────────────────────────────────

def _get_device():
    if torch.backends.mps.is_available():
        return "mps"
    if torch.cuda.is_available():
        return "cuda"
    return "cpu"


_model = _preprocess = None
_device = _get_device()


def _load_clip():
    global _model, _preprocess
    if _model is None:
        import open_clip
        from config.settings import CLIP_MODEL, CLIP_PRETRAINED
        print(f"[CLIP] 載入模型 ({_device})…")
        _model, _, _preprocess = open_clip.create_model_and_transforms(
            CLIP_MODEL, pretrained=CLIP_PRETRAINED
        )
        _model = _model.to(_device).eval()
        print("[CLIP] 模型已載入")
    return _model, _preprocess


def get_embedding(image_path: Path) -> np.ndarray:
    model, preprocess = _load_clip()
    img = Image.open(image_path).convert("RGB")
    tensor = preprocess(img).unsqueeze(0).to(_device)
    with torch.no_grad():
        feat = model.encode_image(tensor)
        feat /= feat.norm(dim=-1, keepdim=True)
    return feat[0].cpu().numpy().astype(np.float32)


# ── KNN ───────────────────────────────────────────────────────────────────────

def knn_predict(train_embs: np.ndarray, train_labels: list,
                test_emb: np.ndarray, k: int = KNN_K) -> str:
    sims = train_embs @ test_emb                # cosine sim (unit vectors)
    top_k = np.argsort(sims)[::-1][:k]
    votes = [train_labels[i] for i in top_k]
    return Counter(votes).most_common(1)[0][0]


# ── main ──────────────────────────────────────────────────────────────────────

def main():
    # 1. 載入訓練標記
    if not LABELS_FILE.exists():
        print("❌ 找不到訓練標記！請先執行：python3 scripts/teach.py")
        sys.exit(1)

    with open(LABELS_FILE, encoding='utf-8') as f:
        label_dict: dict = json.load(f)   # {str(photo_id): category}

    cat_counts = Counter(label_dict.values())
    print(f"✓ 訓練標記：{len(label_dict)} 筆  {dict(cat_counts)}")

    min_samples = min(cat_counts.get(c, 0) for c in CATEGORIES)
    if min_samples < 5:
        lacking = [c for c in CATEGORIES if cat_counts.get(c, 0) < 5]
        print(f"⚠  標記不足的品項：{lacking}")
        print("建議先補足（每類至少 5 張），或繼續執行（準確率可能較低）")
        ans = input("繼續？(y/n) ").strip().lower()
        if ans != 'y':
            sys.exit(0)

    # 2. 載入所有照片
    conn = sqlite3.connect(SQLITE_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT id, full_path, filename, category FROM photos ORDER BY id"
    ).fetchall()
    conn.close()
    print(f"共 {len(rows)} 張照片")

    # 3. Embeddings 快取
    cache: dict[str, np.ndarray] = {}   # photo_id (str) → embedding

    if EMBED_CACHE_FILE.exists():
        data = np.load(EMBED_CACHE_FILE, allow_pickle=True)
        ids_arr = data['ids']
        emb_arr = data['embeddings']
        for pid, emb in zip(ids_arr, emb_arr):
            cache[str(pid)] = emb
        print(f"✓ 快取：{len(cache)} 筆 embedding 已載入")

    need_embed = [r for r in rows
                  if str(r['id']) not in cache
                  and Path(r['full_path']).exists()]

    if need_embed:
        print(f"\n需要生成 {len(need_embed)} 筆 embedding（可能需要幾分鐘）…")
        _load_clip()
        t0 = time.time()
        new_ids, new_embs = [], []

        for i, row in enumerate(need_embed, 1):
            try:
                emb = get_embedding(Path(row['full_path']))
                cache[str(row['id'])] = emb
                new_ids.append(str(row['id']))
                new_embs.append(emb)
            except Exception as e:
                print(f"  ⚠ {row['filename']}: {e}")

            if i % 200 == 0 or i == len(need_embed):
                elapsed = time.time() - t0
                eta = elapsed / i * (len(need_embed) - i)
                print(f"  {i}/{len(need_embed)}  ETA {eta:.0f}s")

        # 儲存快取
        all_ids  = list(cache.keys())
        all_embs = np.array([cache[pid] for pid in all_ids], dtype=np.float32)
        EMBED_CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        np.savez(EMBED_CACHE_FILE, ids=all_ids, embeddings=all_embs)
        print(f"✓ 快取已更新（{len(all_ids)} 筆）")

    # 4. 建立訓練集
    train_ids  = [pid for pid in label_dict if pid in cache]
    train_embs = np.array([cache[pid] for pid in train_ids], dtype=np.float32)
    train_labs = [label_dict[pid] for pid in train_ids]
    print(f"\n訓練集：{len(train_ids)} 筆")

    # 5. KNN 分類 + 移動檔案
    print("\n開始 KNN 分類 + 搬移檔案…")
    conn = sqlite3.connect(SQLITE_PATH)
    conn.row_factory = sqlite3.Row

    changed = errors = skipped = 0

    for row in rows:
        pid = str(row['id'])
        if pid not in cache:
            skipped += 1
            continue

        predicted = knn_predict(train_embs, train_labs, cache[pid])
        old_cat   = row['category'] or ''

        if predicted == old_cat:
            continue   # 分類沒變，不動

        old_path = Path(row['full_path'])
        if not old_path.exists():
            skipped += 1
            continue

        # 決定新路徑：{classified_dir}/{新品項}/{原款式}/新檔名
        try:
            rel_parts = old_path.relative_to(CLASSIFIED_DIR).parts
            old_style = rel_parts[1] if len(rel_parts) >= 3 else '未分'
        except ValueError:
            old_style = '未分'

        new_dir = CLASSIFIED_DIR / predicted / old_style
        new_dir.mkdir(parents=True, exist_ok=True)

        # 重新命名：把第 0 段（品項）改成新品項
        stem_parts = old_path.stem.split('_')
        if stem_parts:
            stem_parts[0] = predicted
        new_stem = '_'.join(stem_parts)
        new_path = new_dir / (new_stem + old_path.suffix)

        # 衝突處理
        if new_path.exists():
            base, ext = new_path.stem, new_path.suffix
            n = 1
            while new_path.exists():
                new_path = new_dir / f"{base}_{n}{ext}"
                n += 1

        try:
            shutil.move(str(old_path), str(new_path))
            conn.execute(
                """UPDATE photos
                   SET category=?, full_path=?, thumb_path=?, micro_path=?, original_path=?
                   WHERE id=?""",
                (predicted, str(new_path), str(new_path),
                 str(new_path), str(new_path), row['id'])
            )
            changed += 1
        except Exception as e:
            print(f"  ⚠ 移動失敗 {old_path.name}: {e}")
            errors += 1

        if (changed + errors) % 500 == 0 and (changed + errors) > 0:
            conn.commit()
            print(f"  已處理 {changed + errors} 筆…")

    conn.commit()
    conn.close()

    print(f"\n✅ 完成！")
    print(f"  更改品項：{changed} 筆")
    print(f"  錯誤：    {errors} 筆")
    print(f"  跳過：    {skipped} 筆")
    print(f"\n下一步：python3 scripts/reindex_from_disk.py")


if __name__ == "__main__":
    main()
