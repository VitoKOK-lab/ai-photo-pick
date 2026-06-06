"""classify.py - CLIP 分類 + embedding 產生"""
import json
import sys
from pathlib import Path
from typing import Dict, Tuple
import torch
import open_clip
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config.settings import CATEGORIES_JSON, CLIP_MODEL, CLIP_PRETRAINED

# 全域載入模型（lazy load）
_model = None
_preprocess = None
_tokenizer = None
_device = "mps" if torch.backends.mps.is_available() else "cpu"

def load_model():
    global _model, _preprocess, _tokenizer
    if _model is None:
        print(f"[CLIP] Loading model {CLIP_MODEL} on {_device}...")
        _model, _, _preprocess = open_clip.create_model_and_transforms(
            CLIP_MODEL, pretrained=CLIP_PRETRAINED
        )
        _model = _model.to(_device).eval()
        _tokenizer = open_clip.get_tokenizer(CLIP_MODEL)
        print("[CLIP] Model loaded.")
    return _model, _preprocess, _tokenizer

def load_categories() -> Dict[str, list]:
    with open(CATEGORIES_JSON, "r", encoding="utf-8") as f:
        return json.load(f)

def classify_one(image_path: Path) -> Tuple[Dict, list]:
    """
    對一張照片做分類 + 產生 embedding
    回傳：(分類結果 dict, embedding list[float])
    """
    model, preprocess, tokenizer = load_model()
    categories = load_categories()

    image = Image.open(image_path).convert("RGB")
    image_input = preprocess(image).unsqueeze(0).to(_device)

    with torch.no_grad():
        image_features = model.encode_image(image_input)
        image_features /= image_features.norm(dim=-1, keepdim=True)

    embedding = image_features[0].cpu().tolist()

    result = {}
    for dim_name, labels in categories.items():
        prompts = [f"a photo of jewelry with {label}" for label in labels]
        text_input = tokenizer(prompts).to(_device)

        with torch.no_grad():
            text_features = model.encode_text(text_input)
            text_features /= text_features.norm(dim=-1, keepdim=True)
            similarities = (image_features @ text_features.T).softmax(dim=-1)
            scores = similarities[0].cpu().tolist()

        best_idx = scores.index(max(scores))
        result[dim_name] = {
            "label": labels[best_idx],
            "confidence": round(scores[best_idx], 4)
        }

    return result, embedding

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python -m scripts.classify <image_path>")
        sys.exit(1)

    result, emb = classify_one(Path(sys.argv[1]))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    print(f"\nEmbedding length: {len(emb)}")
