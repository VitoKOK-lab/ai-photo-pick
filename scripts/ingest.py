"""ingest.py - 完整 ingestion pipeline：process + classify + db_write"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scripts.process_image import process_one, file_hash
from scripts.classify import classify_one
from scripts.db_writer import insert_photo, hash_exists

def ingest_one(source_path: Path) -> dict:
    """
    完整處理單張照片
    回傳：{ "status": "ok"|"skip_duplicate"|"error", "photo_id": int, "filename": str, ... }
    """
    h = file_hash(source_path)
    if hash_exists(h):
        return {"status": "skip_duplicate", "source": str(source_path)}

    try:
        metadata = process_one(source_path)
        full_path = Path(metadata["full_path"])
        classification, embedding = classify_one(full_path)
        photo_id = insert_photo(metadata, classification, embedding)
        return {
            "status": "ok",
            "photo_id": photo_id,
            "filename": metadata["filename"],
            "classification": classification,
        }
    except Exception as e:
        return {"status": "error", "source": str(source_path), "error": str(e)}

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python -m scripts.ingest <image_path>")
        sys.exit(1)
    import json
    result = ingest_one(Path(sys.argv[1]))
    print(json.dumps(result, ensure_ascii=False, indent=2))
