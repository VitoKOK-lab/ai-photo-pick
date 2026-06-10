"""classify.py v2 - CLIP 分類 + embedding
根因修正：softmax 前乘 logit_scale（溫度），避免均勻分布亂分
"""
import json
import sys
from pathlib import Path
from typing import Dict, Tuple
import torch
import open_clip
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config.settings import CLIP_MODEL, CLIP_PRETRAINED

PROMPTS_JSON = Path(__file__).resolve().parent.parent / "config" / "prompts.json"

UNDECIDED = "未定"

# conf = top1 機率門檻；margin = top1−top2 差距門檻
# style / stone_size / price_band 僅供參考，不分流到「未定」
THRESHOLDS = {
    "color":       {"conf": 0.50, "margin": 0.10},
    "category":    {"conf": 0.50, "margin": 0.10},
    "stone_shape": {"conf": 0.50, "margin": 0.08},
    "material":    {"conf": 0.50, "margin": 0.06},
    "gemstone":    {"conf": 0.50, "margin": 0.08},
    "style":       {"conf": 0.00, "margin": 0.00},
    "stone_size":  {"conf": 0.00, "margin": 0.00},
    "price_band":  {"conf": 0.00, "margin": 0.00},
}

ADVISORY_DIMS = {"style", "stone_size", "price_band"}

_model = None
_preprocess = None
_tokenizer = None
_logit_scale = None
_device = "mps" if torch.backends.mps.is_available() else "cpu"
_text_cache: Dict[str, torch.Tensor] = {}


def load_model():
    global _model, _preprocess, _tokenizer, _logit_scale
    if _model is None:
        print(f"[CLIP] Loading model {CLIP_MODEL} on {_device}...")
        _model, _, _preprocess = open_clip.create_model_and_transforms(
            CLIP_MODEL, pretrained=CLIP_PRETRAINED
        )
        _model = _model.to(_device).eval()
        _tokenizer = open_clip.get_tokenizer(CLIP_MODEL)
        _logit_scale = _model.logit_scale.exp().item()
        print(f"[CLIP] Model loaded. logit_scale={_logit_scale:.2f}")
    return _model, _preprocess, _tokenizer, _logit_scale


def load_prompts() -> Dict[str, Dict[str, str]]:
    with open(PROMPTS_JSON, "r", encoding="utf-8") as f:
        return json.load(f)


def _get_text_features(dim_name: str, prompts: list, tokenizer, model) -> torch.Tensor:
    """文字特徵快取，同一個維度只算一次（重跑全量大幅加速）"""
    if dim_name not in _text_cache:
        text_input = tokenizer(prompts).to(_device)
        with torch.no_grad():
            tf = model.encode_text(text_input)
            tf /= tf.norm(dim=-1, keepdim=True)
        _text_cache[dim_name] = tf
    return _text_cache[dim_name]


def classify_one(image_path: Path) -> Tuple[Dict, list]:
    """
    對一張照片做分類 + 產生 embedding
    回傳：(分類結果 dict, embedding list[float])
    """
    model, preprocess, tokenizer, logit_scale = load_model()
    prompts_map = load_prompts()

    image = Image.open(image_path).convert("RGB")
    image_input = preprocess(image).unsqueeze(0).to(_device)

    with torch.no_grad():
        image_features = model.encode_image(image_input)
        image_features /= image_features.norm(dim=-1, keepdim=True)

    embedding = image_features[0].cpu().tolist()

    result = {}
    for dim_name, label_prompt_map in prompts_map.items():
        labels  = list(label_prompt_map.keys())
        prompts = list(label_prompt_map.values())

        text_features = _get_text_features(dim_name, prompts, tokenizer, model)

        with torch.no_grad():
            # ★ 根因修正：乘 logit_scale 再 softmax（避免均勻分布亂分）
            raw    = (image_features @ text_features.T) * logit_scale
            scores = raw.softmax(dim=-1)[0].cpu().tolist()

        sorted_scores = sorted(scores, reverse=True)
        top1   = sorted_scores[0]
        top2   = sorted_scores[1] if len(sorted_scores) > 1 else 0.0
        margin = top1 - top2
        best_idx = scores.index(top1)

        thr        = THRESHOLDS.get(dim_name, {"conf": 0.0, "margin": 0.0})
        is_advisory = dim_name in ADVISORY_DIMS

        if not is_advisory and (top1 < thr["conf"] or margin < thr["margin"]):
            label = UNDECIDED
        else:
            label = labels[best_idx]

        result[dim_name] = {
            "label":      label,
            "confidence": round(top1,   4),
            "margin":     round(margin, 4),
        }

    return result, embedding


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python -m scripts.classify <image_path>")
        sys.exit(1)

    result, emb = classify_one(Path(sys.argv[1]))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    print(f"\nEmbedding length: {len(emb)}")
