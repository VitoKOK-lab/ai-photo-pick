"""classify_gemini.py - Gemini Flash 視覺分類引擎（取代 CLIP）"""
import io
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import config.settings  # 載入 .env → 設定環境變數

FIELDS = {
    "category":         ["戒指","手鏈","墜子","項鍊","耳釘","胸針","其他"],
    "color":            ["紅","粉","黃","綠","藍","紫","白","彩"],
    "gemstone":         ["鑽石","紅寶石","藍寶石","祖母綠","坦桑石","海藍寶","碧璽","紫水晶","黃水晶","月光石","歐泊","橄欖石","石榴石","珍珠","翡翠","托帕石","其他彩寶","無寶石"],
    "stone_shape":      ["橢圓形","圓形","水滴形","心形","方形","長方形","馬眼形","枕形","梨形","三角形","花形","不規則","無主石"],
    "stone_size":       ["1克拉以內","1克拉","2克拉","3克拉","5克拉","10克拉","10克拉以上"],
    "material":         ["925銀","18K黃金","18K白金","18K玫瑰金","鉑金","其他"],
    "metal_color":      ["金","銀"],
    "style":            ["無鑽","簡約","輕奢","奢華"],
    "setting_amount":   ["少","正常","多"],
    "craft_complexity": ["極簡","普通","複雜","極複雜"],
    "photo_type":       ["去背","情境"],
    "price_band":       ["入門","中階","高階","奢華","頂級"],
}

# 低於此值 → 標紅需人工確認
CONFIDENCE_THRESHOLDS = {
    "category":         0.90,
    "material":         0.85,
    "craft_complexity": 0.70,
    "color":            0.75,
    "stone_shape":      0.75,
    "metal_color":      0.75,
    "style":            0.75,
    "setting_amount":   0.75,
    "photo_type":       0.75,
    "stone_size":       0.70,
    "gemstone":         0.70,
    "price_band":       0.70,
}

PROMPT = """你是一位珠寶分類專家。仔細分析這張珠寶照片，嚴格按照下方 JSON schema 分類。

【鐵律】
1. 只回傳純 JSON，不得有任何其他文字、markdown 標記、說明
2. 每個欄位只能從「可選值」中選一個，不可自創新值
3. confidence 是對該答案的把握度（0.0–1.0）
4. category（品項）是最關鍵欄位，看圖必須判斷正確
5. craft_complexity 根據可見配鑽/配石數量判斷：
   - 極簡：無配石
   - 普通：少量配石（約 1–10 顆）
   - 複雜：大量配石（10–30 顆）
   - 極複雜：滿鑽鋪鑲/整圈密鑲/大面積pavé

【可選值】
category: 戒指, 手鏈, 墜子, 項鍊, 耳釘, 胸針, 其他
color: 紅, 粉, 黃, 綠, 藍, 紫, 白, 彩
gemstone: 鑽石, 紅寶石, 藍寶石, 祖母綠, 坦桑石, 海藍寶, 碧璽, 紫水晶, 黃水晶, 月光石, 歐泊, 橄欖石, 石榴石, 珍珠, 翡翠, 托帕石, 其他彩寶, 無寶石
stone_shape: 橢圓形, 圓形, 水滴形, 心形, 方形, 長方形, 馬眼形, 枕形, 梨形, 三角形, 花形, 不規則, 無主石
stone_size: 1克拉以內, 1克拉, 2克拉, 3克拉, 5克拉, 10克拉, 10克拉以上
material: 925銀, 18K黃金, 18K白金, 18K玫瑰金, 鉑金, 其他
metal_color: 金, 銀
style: 無鑽, 簡約, 輕奢, 奢華
setting_amount: 少, 正常, 多
craft_complexity: 極簡, 普通, 複雜, 極複雜
photo_type: 去背, 情境
price_band: 入門, 中階, 高階, 奢華, 頂級

【回傳格式】
{"category":"戒指","category_confidence":0.98,"color":"藍","color_confidence":0.92,"gemstone":"藍寶石","gemstone_confidence":0.85,"stone_shape":"橢圓形","stone_shape_confidence":0.88,"stone_size":"3克拉","stone_size_confidence":0.62,"material":"18K白金","material_confidence":0.91,"metal_color":"銀","metal_color_confidence":0.97,"style":"輕奢","style_confidence":0.79,"setting_amount":"正常","setting_amount_confidence":0.81,"craft_complexity":"普通","craft_complexity_confidence":0.74,"photo_type":"去背","photo_type_confidence":0.99,"price_band":"高階","price_band_confidence":0.65}"""

_client = None


def _get_client():
    global _client
    if _client is None:
        from google import genai
        api_key = os.environ.get("GEMINI_API_KEY", "")
        if not api_key:
            raise RuntimeError("GEMINI_API_KEY 未設定，請在 .env 加入 GEMINI_API_KEY=...")
        _client = genai.Client(api_key=api_key)
    return _client

GEMINI_MODEL = "gemini-2.5-flash"


def _open_image(path: Path):
    """壓縮到 1024px 後回傳 PIL Image。"""
    from PIL import Image
    img = Image.open(path).convert("RGB")
    img.thumbnail((1024, 1024), Image.LANCZOS)
    return img


def classify_image(image_path: Path, extra_images: list = None) -> dict:
    """
    用 Gemini Flash 分類一張（或同件多角度）珠寶照片。

    extra_images: 同一件的其他角度路徑列表（客製訂單用）
    回傳: 各欄位 label + confidence，以及 needs_review / low_confidence_fields
    """
    client = _get_client()

    contents = [PROMPT]
    for p in [image_path] + (extra_images or []):
        p = Path(p)
        if p.exists():
            contents.append(_open_image(p))

    response = client.models.generate_content(
        model=GEMINI_MODEL, contents=contents
    )
    raw = response.text.strip()

    # 去掉可能的 markdown code block
    if "```" in raw:
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    raw = raw.strip()

    result = json.loads(raw)

    # 驗證選項 + 夾緊 confidence
    for field, options in FIELDS.items():
        if result.get(field) not in options:
            result[field] = options[0]
            result[f"{field}_confidence"] = 0.0
        else:
            result[f"{field}_confidence"] = round(
                min(max(float(result.get(f"{field}_confidence", 0)), 0.0), 1.0), 3
            )

    # 標記需人工複核的欄位
    low = [f for f, thr in CONFIDENCE_THRESHOLDS.items()
           if result.get(f"{f}_confidence", 0) < thr]
    result["low_confidence_fields"] = low
    result["needs_review"] = bool(low)

    return result


def confidence_color(field: str, confidence: float) -> str:
    """回傳 'green' / 'yellow' / 'red'，供前端上色用。"""
    thr = CONFIDENCE_THRESHOLDS.get(field, 0.75)
    if confidence >= thr:
        return "green"
    elif confidence >= thr - 0.15:
        return "yellow"
    return "red"


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法: python3 -m scripts.classify_gemini <圖片路徑>")
        sys.exit(1)
    r = classify_image(Path(sys.argv[1]))
    print(json.dumps(r, ensure_ascii=False, indent=2))
    if r["needs_review"]:
        print("\n⚠ 需人工確認:", r["low_confidence_fields"])
    else:
        print("\n✓ 全部高信心，可直接匯入")
