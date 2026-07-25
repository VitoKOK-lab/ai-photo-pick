"""detect_watermark.py — 用 Gemini Vision 偵測照片上是否有「文字／浮水印／他牌名稱／logo」

情境照（有背景）常會夾帶別家店的浮水印、品牌名、logo 或促銷文字；
這個模組判斷一張照片上是否出現「任何可讀的文字或浮水印」（珠寶本身金屬上的
細小鋼印刻字不算）。回傳結構化結果，供掃描腳本與匯入流程共用。

需要環境變數 GEMINI_API_KEY（在 .env 設定），與分類用的是同一把金鑰。

單獨測試：
  python3 -m scripts.detect_watermark <image_path>
"""
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import config.settings  # 載入 .env → 設定環境變數

GEMINI_MODEL = "gemini-2.5-flash"

_PROMPT = """你是圖片稽核員。判斷這張珠寶照片上是否出現「任何可讀的文字、浮水印、店名／品牌名或 logo」。

【要抓出來的（算有文字）】
- 半透明或壓在照片上的浮水印
- 別家店名、品牌名、帳號、網址、電話、微信/LINE ID
- 商標 logo、印章、貼紙上的字
- 任何促銷字、標價字、說明字，或背景招牌/包裝/紙卡上清楚可讀的字

【不算文字（要忽略）】
- 珠寶金屬本身上極小的鋼印、純度刻印（如 750、G18K）——這是產品的一部分
- 完全無法辨識、純裝飾花紋

【鐵律】
- 只回傳純 JSON，不得有任何其他文字或 markdown
- 格式：{"has_text": true/false, "kind": "浮水印|品牌名|logo|促銷字|其他文字|無", "sample": "看到的文字內容(沒有就空字串)", "confidence": 0.0~1.0}
"""

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


def _open_image(path: Path):
    from PIL import Image
    img = Image.open(path).convert("RGB")
    img.thumbnail((1024, 1024), Image.LANCZOS)
    return img


def detect_text(image_path) -> dict:
    """回傳 {"has_text": bool, "kind": str, "sample": str, "confidence": float}。

    偵測失敗時回傳 has_text=False + kind='錯誤'（保守：不誤刪）。"""
    image_path = Path(image_path)
    if not image_path.exists():
        return {"has_text": False, "kind": "錯誤", "sample": "", "confidence": 0.0}
    try:
        client = _get_client()
        resp = client.models.generate_content(
            model=GEMINI_MODEL, contents=[_PROMPT, _open_image(image_path)]
        )
        raw = resp.text.strip()
        if "```" in raw:
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        d = json.loads(raw.strip())
        return {
            "has_text":   bool(d.get("has_text")),
            "kind":       str(d.get("kind", "") or "無"),
            "sample":     str(d.get("sample", "") or "")[:120],
            "confidence": round(min(max(float(d.get("confidence", 0)), 0.0), 1.0), 3),
        }
    except Exception as e:
        return {"has_text": False, "kind": "錯誤", "sample": str(e)[:120], "confidence": 0.0}


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 -m scripts.detect_watermark <image_path>")
        sys.exit(1)
    print(json.dumps(detect_text(sys.argv[1]), ensure_ascii=False, indent=2))
