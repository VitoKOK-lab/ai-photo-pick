"""classify_photo_type.py - 去背 vs 情境 雙重偵測

PIL 看像素（邊緣是否白色）+ CLIP 看語意（是否商品棚拍風格）
兩個都同意是去背 → '去背'，否則 → '情境'

使用方式：
  python3 -m scripts.classify_photo_type          # 全部重新分類
  python3 -m scripts.classify_photo_type --missing  # 只補 NULL 的
"""
import sqlite3
import sys
import time
import logging
from pathlib import Path
from PIL import Image
import torch
import open_clip

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config.settings import SQLITE_PATH, THUMB_DIR, FULL_DIR, CLIP_MODEL, CLIP_PRETRAINED

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s",
                    handlers=[logging.StreamHandler()])
log = logging.getLogger(__name__)

# ── PIL 參數 ───────────────────────────────────────────────
WHITE_THRESHOLD = 235   # channel 值 > 這個才算白（純白底）
PIL_WHITE_RATIO = 0.85  # 珠寶框外背景 85%+ 是白 → PIL 認定去背

# ── CLIP 文字描述 ──────────────────────────────────────────
CLIP_PROMPTS = {
    '去背': (
        "a jewelry product photo shot on a pure white background with nothing else visible — "
        "no display stand, no ring holder, no ring cone, no jewelry box, no props, no shadows of props, "
        "no hands, no body, no fabric, no table surface — "
        "just the single jewelry piece floating isolated on a completely plain white background, "
        "e-commerce catalog style with white all around the jewelry"
    ),
    '情境': (
        "a jewelry photo with any real-world context — worn on a hand, wrist, neck or ear, "
        "placed on a ring display cone or stand, inside a jewelry box, "
        "on marble, wood, fabric or any textured surface, "
        "photographed outdoors or in a room, or any photo where you can see "
        "a background other than plain white behind the jewelry"
    ),
}

_model = _preprocess = _tokenizer = _device = None

def _load_clip():
    global _model, _preprocess, _tokenizer, _device
    if _model is not None:
        return
    _device = "mps" if torch.backends.mps.is_available() else "cpu"
    log.info(f"[CLIP] 載入模型 {CLIP_MODEL} on {_device}…")
    _model, _, _preprocess = open_clip.create_model_and_transforms(
        CLIP_MODEL, pretrained=CLIP_PRETRAINED
    )
    _model = _model.to(_device).eval()
    _tokenizer = open_clip.get_tokenizer(CLIP_MODEL)
    log.info("[CLIP] 模型載入完成")


def pil_check(img_path: Path) -> bool:
    """
    偵測珠寶邊界框，再檢查框外背景是否為純白。
    不被放大圖的人工白邊或四角騙到。
    """
    img = Image.open(img_path).convert('RGB')
    w, h = img.size

    gray = img.convert('L')
    mask = gray.point(lambda x: 255 if x < WHITE_THRESHOLD else 0)
    bbox = mask.getbbox()   # 非白色（珠寶）的邊界框

    if bbox is None:
        return True   # 整張都白

    left, top, right, bottom = bbox
    pad = max(4, min(w, h) // 30)
    t = max(0, top - pad)
    b_edge = min(h, bottom + pad)
    l = max(0, left - pad)
    r = min(w, right + pad)

    bg = []
    if t > 0:       bg += list(img.crop((0, 0, w, t       )).getdata())
    if b_edge < h:  bg += list(img.crop((0, b_edge, w, h  )).getdata())
    if l > 0:       bg += list(img.crop((0, t, l, b_edge  )).getdata())
    if r < w:       bg += list(img.crop((r, t, w, b_edge  )).getdata())

    if not bg:
        return False

    white = sum(1 for rv, gv, bv in bg
                if rv > WHITE_THRESHOLD and gv > WHITE_THRESHOLD and bv > WHITE_THRESHOLD)
    return (white / len(bg)) >= PIL_WHITE_RATIO


# 預先算好文字 embedding（只算一次）
_text_feats = None

def clip_check(full_path: Path) -> bool:
    """CLIP 語意判斷：去背 → True"""
    global _text_feats
    _load_clip()
    if _text_feats is None:
        labels  = list(CLIP_PROMPTS.keys())
        prompts = list(CLIP_PROMPTS.values())
        tokens  = _tokenizer(prompts).to(_device)
        with torch.no_grad():
            tf = _model.encode_text(tokens)
            tf /= tf.norm(dim=-1, keepdim=True)
        _text_feats = (labels, tf)

    image = Image.open(full_path).convert('RGB')
    inp   = _preprocess(image).unsqueeze(0).to(_device)
    with torch.no_grad():
        imf = _model.encode_image(inp)
        imf /= imf.norm(dim=-1, keepdim=True)
        logit_scale = _model.logit_scale.exp().item()
        scores = (imf @ _text_feats[1].T * logit_scale).softmax(dim=-1)[0].cpu().tolist()
    best_label = _text_feats[0][scores.index(max(scores))]
    return best_label == '去背'


def detect_type(thumb_path: Path, full_path: Path) -> str:
    """PIL 白底確認（用 full 圖，更準確）AND CLIP 語意確認"""
    pil_result = pil_check(full_path)   # full 圖 1200px，邊緣更乾淨
    if not pil_result:
        return '情境'
    clip_result = clip_check(full_path)
    return '去背' if clip_result else '情境'


def main(missing_only: bool = False):
    conn = sqlite3.connect(SQLITE_PATH)
    conn.row_factory = sqlite3.Row

    query = ("SELECT id, filename FROM photos WHERE photo_type IS NULL ORDER BY id"
             if missing_only else
             "SELECT id, filename FROM photos ORDER BY id")
    rows  = conn.execute(query).fetchall()
    total = len(rows)
    log.info(f"共 {total} 張，PIL + CLIP 雙重偵測")
    if total == 0:
        conn.close()
        return

    counts = {'去背': 0, '情境': 0, 'miss': 0}
    start  = time.time()
    for i, row in enumerate(rows, 1):
        thumb_path = THUMB_DIR / row['filename']
        full_path  = FULL_DIR  / row['filename']
        if not thumb_path.exists() or not full_path.exists():
            counts['miss'] += 1
            continue
        try:
            ptype = detect_type(thumb_path, full_path)
            conn.execute("UPDATE photos SET photo_type = ? WHERE id = ?", (ptype, row['id']))
            if i % 200 == 0:
                conn.commit()
            counts[ptype] += 1
            if i % 500 == 0:
                elapsed = time.time() - start
                eta = (total - i) / (i / elapsed) if elapsed > 0 else 0
                log.info(f"[{i}/{total}] ETA {eta:.0f}s 去背={counts['去背']} 情境={counts['情境']}")
        except Exception as e:
            counts['miss'] += 1
            log.error(f"  [{i}] {row['filename']}: {e}")

    conn.commit()
    conn.close()
    log.info(f"\n完成 {time.time()-start:.1f}s — 去背:{counts['去背']} 情境:{counts['情境']} 跳過:{counts['miss']}")


if __name__ == '__main__':
    main(missing_only='--missing' in sys.argv)
