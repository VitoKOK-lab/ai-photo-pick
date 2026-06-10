"""calibrate_threshold.py - 抽樣統計 confidence 分布，校準門檻

用法：python3 scripts/calibrate_threshold.py [樣本數，預設200]
"""
import random
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config.settings import SQLITE_PATH
from scripts.classify import classify_one

N = int(sys.argv[1]) if len(sys.argv) > 1 else 200

conn = sqlite3.connect(SQLITE_PATH)
conn.row_factory = sqlite3.Row
rows = conn.execute("SELECT id, full_path FROM photos").fetchall()
conn.close()

sample = random.sample(rows, min(N, len(rows)))
print(f"抽樣 {len(sample)} 張，開始分析...\n")

from collections import defaultdict
data: dict = defaultdict(list)

for i, row in enumerate(sample, 1):
    path = Path(row["full_path"])
    if not path.exists():
        continue
    try:
        cls, _ = classify_one(path)
        for dim, v in cls.items():
            data[dim].append((v["confidence"], v.get("margin", 0)))
        print(f"  [{i}/{len(sample)}] ok")
    except Exception as e:
        print(f"  [{i}/{len(sample)}] 錯誤：{e}")

print("\n── confidence / margin 分布（供校準門檻用）──\n")
for dim, vals in data.items():
    confs   = sorted([v[0] for v in vals])
    margins = sorted([v[1] for v in vals])
    n       = len(confs)
    med_c   = confs[n // 2]
    med_m   = margins[n // 2]
    p25_c   = confs[n // 4]
    p25_m   = margins[n // 4]
    undecided_50 = sum(1 for c, m in vals if c < 0.50 or m < 0.08) / n * 100
    print(f"  {dim:15s}  conf 中位={med_c:.3f} p25={p25_c:.3f} | margin 中位={med_m:.3f} p25={p25_m:.3f} | 門檻0.5時未定={undecided_50:.1f}%")
