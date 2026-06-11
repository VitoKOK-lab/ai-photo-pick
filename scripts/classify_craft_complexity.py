"""classify_craft_complexity.py - 用 CLIP 零樣本分析「做工複雜度」並存入 DB

分四級：極簡 / 普通 / 複雜 / 極複雜
使用 config/prompts.json 的 craft_complexity 描述。
共用 embeddings_cache.npz（不需重算圖片 embedding）。

執行：python3 scripts/classify_craft_complexity.py
"""
import json
import sqlite3
import sys
import time
from pathlib import Path

import numpy as np
import torch
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config.settings import SQLITE_PATH, BASE_DIR

EMBED_CACHE_FILE = BASE_DIR / "data" / "embeddings_cache.npz"
PROMPTS_FILE     = BASE_DIR / "config" / "prompts.json"

LABELS = ['極簡', '普通', '複雜', '極複雜']


def _get_device():
    if torch.backends.mps.is_available(): return "mps"
    if torch.cuda.is_available():         return "cuda"
    return "cpu"


_device = _get_device()
_model = _preprocess = _tokenizer = _logit_scale = None


def _load_clip():
    global _model, _preprocess, _tokenizer, _logit_scale
    if _model is None:
        import open_clip
        from config.settings import CLIP_MODEL, CLIP_PRETRAINED
        print(f"[CLIP] 載入模型 ({_device})…")
        _model, _, _preprocess = open_clip.create_model_and_transforms(
            CLIP_MODEL, pretrained=CLIP_PRETRAINED
        )
        _model = _model.to(_device).eval()
        _tokenizer = open_clip.get_tokenizer(CLIP_MODEL)
        _logit_scale = _model.logit_scale.exp().item()
        print(f"[CLIP] 完成  logit_scale={_logit_scale:.2f}")
    return _model, _preprocess, _tokenizer, _logit_scale


def get_text_features(prompts: list) -> torch.Tensor:
    model, _, tokenizer, _ = _load_clip()
    tokens = tokenizer(prompts).to(_device)
    with torch.no_grad():
        tf = model.encode_text(tokens)
        tf /= tf.norm(dim=-1, keepdim=True)
    return tf


def get_image_embedding(image_path: Path) -> np.ndarray:
    model, preprocess, _, _ = _load_clip()
    img = Image.open(image_path).convert("RGB")
    tensor = preprocess(img).unsqueeze(0).to(_device)
    with torch.no_grad():
        feat = model.encode_image(tensor)
        feat /= feat.norm(dim=-1, keepdim=True)
    return feat[0].cpu().numpy().astype(np.float32)


def main():
    # 確保欄位存在
    conn = sqlite3.connect(SQLITE_PATH)
    cols = {r[1] for r in conn.execute("PRAGMA table_info(photos)")}
    if 'craft_complexity' not in cols:
        conn.execute("ALTER TABLE photos ADD COLUMN craft_complexity TEXT")
        conn.commit()
        print("✓ 已新增 craft_complexity 欄位")

    rows = conn.execute(
        "SELECT id, full_path, filename FROM photos WHERE full_path IS NOT NULL ORDER BY id"
    ).fetchall()
    conn.close()
    print(f"共 {len(rows)} 張照片")

    # 載入 prompts
    with open(PROMPTS_FILE, encoding='utf-8') as f:
        all_prompts = json.load(f)
    craft_prompts  = all_prompts.get('craft_complexity', {})
    labels_ordered = list(craft_prompts.keys())   # ['極簡','普通','複雜','極複雜']
    prompt_texts   = list(craft_prompts.values())

    if not prompt_texts:
        print("❌ prompts.json 中找不到 craft_complexity，請確認設定檔")
        return

    # 載入 embedding 快取
    cache: dict = {}
    if EMBED_CACHE_FILE.exists():
        data = np.load(EMBED_CACHE_FILE, allow_pickle=True)
        for pid, emb in zip(data['ids'], data['embeddings']):
            cache[str(pid)] = emb
        print(f"✓ 快取 {len(cache)} 筆 embedding")

    # 需要生成 embedding 的照片（快取中沒有的）
    need_embed = [r for r in rows
                  if str(r[0]) not in cache and Path(r[1]).exists()]

    if need_embed:
        print(f"\n生成 {len(need_embed)} 筆 embedding…")
        _load_clip()
        t0 = time.time()
        for i, row in enumerate(need_embed, 1):
            try:
                emb = get_image_embedding(Path(row[1]))
                cache[str(row[0])] = emb
            except Exception as e:
                print(f"  ⚠ {row[2]}: {e}")
            if i % 300 == 0 or i == len(need_embed):
                elapsed = time.time() - t0
                eta = elapsed / i * (len(need_embed) - i)
                print(f"  {i}/{len(need_embed)}  ETA {eta:.0f}s")

        all_ids  = list(cache.keys())
        all_embs = np.array([cache[k] for k in all_ids], dtype=np.float32)
        EMBED_CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        np.savez(EMBED_CACHE_FILE, ids=all_ids, embeddings=all_embs)
        print("✓ 快取已更新")

    # 計算 text features
    print("\n計算文字特徵…")
    _, _, _, logit_scale = _load_clip()
    text_feats = get_text_features(prompt_texts)  # (4, dim)

    # 分類所有照片
    print("分類中…")
    conn = sqlite3.connect(SQLITE_PATH)
    updated = skipped = 0
    dist = {l: 0 for l in labels_ordered}

    for row in rows:
        pid = str(row[0])
        if pid not in cache:
            skipped += 1
            continue

        emb = torch.tensor(cache[pid], device=_device).unsqueeze(0)
        with torch.no_grad():
            scores = (emb @ text_feats.T * logit_scale).softmax(dim=-1)[0].cpu().tolist()

        best = labels_ordered[scores.index(max(scores))]
        conn.execute("UPDATE photos SET craft_complexity=? WHERE id=?", (best, row[0]))
        dist[best] += 1
        updated += 1

        if updated % 500 == 0:
            conn.commit()
            print(f"  已處理 {updated} 筆…")

    conn.commit()
    conn.close()

    print(f"\n✅ 完成！")
    print(f"  分類：{updated} 筆  跳過：{skipped} 筆")
    print(f"  結果分佈：")
    for lbl, cnt in dist.items():
        pct = 100 * cnt / max(updated, 1)
        bar = '█' * int(pct / 2)
        print(f"    {lbl:6s}  {bar}  {cnt} ({pct:.1f}%)")

    print("\n如果分佈合理即完成。")
    print("若要用人工標記修正，執行：python3 scripts/teach.py --craft")
    print("                         python3 scripts/reclassify_trained.py --craft")


if __name__ == "__main__":
    main()
