"""reclassify_trained.py - 用 KNN 重新分類所有照片並整理檔名

執行：
  python3 scripts/reclassify_trained.py           ← 重分品項（category）
  python3 scripts/reclassify_trained.py --style   ← 重分鑽石等級（style）

前置條件：
  品項：先執行 python3 scripts/teach.py
  鑽石：先執行 python3 scripts/teach.py --style
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

CAT_LABELS_FILE    = BASE_DIR / "data" / "training_labels.json"
STYLE_LABELS_FILE  = BASE_DIR / "data" / "training_labels_style.json"
CHAIN_LABELS_FILE  = BASE_DIR / "data" / "training_labels_chain.json"
EMBED_CACHE_FILE   = BASE_DIR / "data" / "embeddings_cache.npz"
CLASSIFIED_DIR     = BASE_DIR / "data" / "02_classified"

CATEGORIES    = ['戒指', '手鏈', '墜子', '項鍊', '耳釘', '胸針', '其他']
STYLE_DB_VALS = ['無鑽', '簡約(5顆鑽內)', '輕奢(20顆鑽內)', '豪鑲滿鑲鑽']
CHAIN_DB_VALS = ['無鍊', '細鍊', '中等', '粗鍊']
KNN_K = 7


def _ensure_chain_column():
    """確保 photos 表有 chain_width 欄位"""
    conn = sqlite3.connect(SQLITE_PATH)
    cols = {r[1] for r in conn.execute("PRAGMA table_info(photos)")}
    if 'chain_width' not in cols:
        conn.execute("ALTER TABLE photos ADD COLUMN chain_width TEXT")
        conn.commit()
        print("✓ 已新增 chain_width 欄位")
    conn.close()


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
    mode_style = '--style' in sys.argv
    mode_chain = '--chain' in sys.argv

    if mode_chain:
        _ensure_chain_column()
        labels_file = CHAIN_LABELS_FILE
        dim_name    = '鍊子粗細'
        dim_field   = 'chain_width'
        dim_labels  = CHAIN_DB_VALS
        teach_cmd   = 'python3 scripts/teach.py --chain'
    elif mode_style:
        labels_file = STYLE_LABELS_FILE
        dim_name    = '鑽石等級'
        dim_field   = 'style'
        dim_labels  = STYLE_DB_VALS
        teach_cmd   = 'python3 scripts/teach.py --style'
    else:
        labels_file = CAT_LABELS_FILE
        dim_name    = '品項'
        dim_field   = 'category'
        dim_labels  = CATEGORIES
        teach_cmd   = 'python3 scripts/teach.py'

    # 1. 載入訓練標記
    if not labels_file.exists():
        print(f"❌ 找不到{dim_name}訓練標記！請先執行：{teach_cmd}")
        sys.exit(1)

    with open(labels_file, encoding='utf-8') as f:
        label_dict: dict = json.load(f)

    label_counts = Counter(label_dict.values())
    print(f"✓ {dim_name}訓練標記：{len(label_dict)} 筆  {dict(label_counts)}")

    min_samples = min(label_counts.get(c, 0) for c in dim_labels)
    if min_samples < 5:
        lacking = [c for c in dim_labels if label_counts.get(c, 0) < 5]
        print(f"⚠  標記不足：{lacking}")
        print("建議先補足（每類至少 5 張），或繼續執行（準確率可能較低）")
        ans = input("繼續？(y/n) ").strip().lower()
        if ans != 'y':
            sys.exit(0)

    # 2. 載入所有照片
    conn = sqlite3.connect(SQLITE_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT id, full_path, filename, category, style, chain_width FROM photos ORDER BY id"
        if not mode_chain else
        "SELECT id, full_path, filename, category, style, COALESCE(chain_width,'') as chain_width FROM photos ORDER BY id"
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

    # 5. KNN 分類 + 更新 DB（品項模式同時搬移檔案）
    action = "鑽石等級" if mode_style else "品項 + 搬移檔案"
    print(f"\n開始 KNN 分類（{action}）…")
    conn = sqlite3.connect(SQLITE_PATH)
    conn.row_factory = sqlite3.Row

    changed = errors = skipped = 0

    for row in rows:
        pid = str(row['id'])
        if pid not in cache:
            skipped += 1
            continue

        predicted   = knn_predict(train_embs, train_labs, cache[pid])
        if mode_chain:
            old_val = row['chain_width'] or ''
        elif mode_style:
            old_val = row['style'] or ''
        else:
            old_val = row['category'] or ''

        if predicted == old_val:
            continue  # 沒變，跳過

        if mode_style or mode_chain:
            # 只更新 DB 欄位，不動檔案
            field = 'chain_width' if mode_chain else 'style'
            conn.execute(f"UPDATE photos SET {field}=? WHERE id=?", (predicted, row['id']))
            changed += 1
        else:
            # 品項模式：移動檔案 + 更新 DB
            old_path = Path(row['full_path'])
            if not old_path.exists():
                skipped += 1
                continue

            try:
                rel_parts = old_path.relative_to(CLASSIFIED_DIR).parts
                old_style_dir = rel_parts[1] if len(rel_parts) >= 3 else '未分'
            except ValueError:
                old_style_dir = '未分'

            new_dir = CLASSIFIED_DIR / predicted / old_style_dir
            new_dir.mkdir(parents=True, exist_ok=True)

            stem_parts = old_path.stem.split('_')
            if stem_parts:
                stem_parts[0] = predicted
            new_stem = '_'.join(stem_parts)
            new_path = new_dir / (new_stem + old_path.suffix)

            if new_path.exists():
                base, ext = new_path.stem, new_path.suffix
                n = 1
                while new_path.exists():
                    new_path = new_dir / f"{base}_{n}{ext}"
                    n += 1

            try:
                shutil.move(str(old_path), str(new_path))
                conn.execute(
                    "UPDATE photos SET category=?, full_path=?, thumb_path=?, micro_path=?, original_path=? WHERE id=?",
                    (predicted, str(new_path), str(new_path), str(new_path), str(new_path), row['id'])
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

    label = '鍊子粗細' if mode_chain else ('鑽石等級' if mode_style else '品項')
    print(f"\n✅ 完成！")
    print(f"  更改{label}：{changed} 筆")
    print(f"  錯誤：      {errors} 筆")
    print(f"  跳過：      {skipped} 筆")
    if not mode_style and not mode_chain:
        print(f"\n下一步：python3 scripts/reindex_from_disk.py")
    else:
        print(f"\n完成！{label}已更新到 DB。")


if __name__ == "__main__":
    main()
