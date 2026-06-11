"""classify_color.py - 用 CLIP 零樣本分析「寶石顏色」並存入 DB

8種顏色：紅 / 粉 / 黃 / 綠 / 藍 / 紫 / 白 / 彩
共用 embeddings_cache.npz，不需重新讀圖。

執行：python3 scripts/classify_color.py
"""
import json
import sqlite3
import sys
from pathlib import Path

import numpy as np
import torch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config.settings import SQLITE_PATH, BASE_DIR

EMBED_CACHE_FILE = BASE_DIR / "data" / "embeddings_cache.npz"
PROMPTS_FILE     = BASE_DIR / "config" / "prompts.json"


def _get_device():
    if torch.backends.mps.is_available(): return "mps"
    if torch.cuda.is_available():         return "cuda"
    return "cpu"

_device = _get_device()
_model = _tokenizer = _logit_scale = None


def _load_clip():
    global _model, _tokenizer, _logit_scale
    if _model is None:
        import open_clip
        from config.settings import CLIP_MODEL, CLIP_PRETRAINED
        print(f"[CLIP] 載入模型 ({_device})…")
        _model, _, _ = open_clip.create_model_and_transforms(CLIP_MODEL, pretrained=CLIP_PRETRAINED)
        _model = _model.to(_device).eval()
        _tokenizer = open_clip.get_tokenizer(CLIP_MODEL)
        _logit_scale = _model.logit_scale.exp().item()
        print(f"[CLIP] 完成  logit_scale={_logit_scale:.2f}")
    return _model, _tokenizer, _logit_scale


def main():
    with open(PROMPTS_FILE, encoding='utf-8') as f:
        all_prompts = json.load(f)
    color_prompts  = all_prompts.get('color', {})
    labels_ordered = list(color_prompts.keys())
    prompt_texts   = list(color_prompts.values())

    if not EMBED_CACHE_FILE.exists():
        print("❌ 找不到 embeddings_cache.npz，請先執行 classify_setting_amount.py")
        return
    data = np.load(EMBED_CACHE_FILE, allow_pickle=True)
    cache = {str(pid): emb for pid, emb in zip(data['ids'], data['embeddings'])}
    print(f"✓ 快取 {len(cache)} 筆 embedding")

    conn = sqlite3.connect(SQLITE_PATH)
    rows = conn.execute("SELECT id FROM photos WHERE full_path IS NOT NULL ORDER BY id").fetchall()
    print(f"共 {len(rows)} 張照片")

    print("計算文字特徵…")
    model, tokenizer, logit_scale = _load_clip()
    tokens = tokenizer(prompt_texts).to(_device)
    with torch.no_grad():
        text_feats = model.encode_text(tokens)
        text_feats /= text_feats.norm(dim=-1, keepdim=True)

    print("分類中…")
    updated = skipped = 0
    dist = {l: 0 for l in labels_ordered}

    for (pid,) in rows:
        key = str(pid)
        if key not in cache:
            skipped += 1
            continue
        emb = torch.tensor(cache[key], device=_device).unsqueeze(0)
        with torch.no_grad():
            scores = (emb @ text_feats.T * logit_scale).softmax(dim=-1)[0].cpu().tolist()
        best = labels_ordered[scores.index(max(scores))]
        conn.execute("UPDATE photos SET color=? WHERE id=?", (best, pid))
        dist[best] += 1
        updated += 1
        if updated % 500 == 0:
            conn.commit()
            print(f"  已處理 {updated} 筆…")

    conn.commit()
    conn.close()

    print(f"\n✅ 完成！分類 {updated} 筆，跳過 {skipped} 筆")
    print("結果分佈：")
    for lbl, cnt in dist.items():
        pct = 100 * cnt / max(updated, 1)
        bar = '█' * int(pct / 2)
        print(f"  {lbl}  {bar}  {cnt} ({pct:.1f}%)")


if __name__ == "__main__":
    main()
