"""diag_embedding.py - 印出 softmax 前後的 raw cosine，確認 logit_scale 修正效果

用法：python3 scripts/diag_embedding.py <image_path>
"""
import json
import sys
from pathlib import Path
import torch
import open_clip
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config.settings import CLIP_MODEL, CLIP_PRETRAINED

PROMPTS_JSON = Path(__file__).resolve().parent.parent / "config" / "prompts.json"

if len(sys.argv) < 2:
    print("Usage: python3 scripts/diag_embedding.py <image_path>")
    sys.exit(1)

image_path = Path(sys.argv[1])
device = "mps" if torch.backends.mps.is_available() else "cpu"

model, _, preprocess = open_clip.create_model_and_transforms(CLIP_MODEL, pretrained=CLIP_PRETRAINED)
model = model.to(device).eval()
tokenizer = open_clip.get_tokenizer(CLIP_MODEL)
logit_scale = model.logit_scale.exp().item()
print(f"logit_scale = {logit_scale:.2f}\n")

with open(PROMPTS_JSON, encoding="utf-8") as f:
    prompts_map = json.load(f)

image = Image.open(image_path).convert("RGB")
image_input = preprocess(image).unsqueeze(0).to(device)
with torch.no_grad():
    img_feat = model.encode_image(image_input)
    img_feat /= img_feat.norm(dim=-1, keepdim=True)

for dim_name, label_prompt_map in prompts_map.items():
    labels  = list(label_prompt_map.keys())
    prompts = list(label_prompt_map.values())
    text_input = tokenizer(prompts).to(device)
    with torch.no_grad():
        txt_feat = model.encode_text(text_input)
        txt_feat /= txt_feat.norm(dim=-1, keepdim=True)
        raw    = (img_feat @ txt_feat.T)[0].cpu().tolist()
        scaled = [(img_feat @ txt_feat.T * logit_scale).softmax(dim=-1)[0].cpu().tolist()[i] for i in range(len(labels))]

    pairs = sorted(zip(labels, raw, scaled), key=lambda x: -x[1])
    print(f"── {dim_name} ──")
    print(f"  {'label':20s} {'raw cosine':>12} {'softmax×scale':>14}")
    for label, r, s in pairs[:5]:
        print(f"  {label:20s} {r:12.4f} {s:14.4f}")
    print()
