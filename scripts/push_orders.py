"""push_orders.py — 把下載好的 SHOPLINE 報表自動送進客服系統。

放在「下載報表的那台 Mac」上，跟你現有的整理/上傳流程並排跑：
你的「下載 → 整理 → 出 HTML → 推 GitHub」完全不動，這支只多做一件事——
把最新的原始 SHOPLINE 報表 POST 進客服系統，由系統自動合併、去重、更新看板。

── 安裝（一次）─────────────────────────────────
    python3 -m pip install requests

── 設定 ───────────────────────────────────────
    改下面三個值（部署好系統後填入正式網址與通行碼）。

── 排程（Mac，每天兩次）──────────────────────────
    crontab -e
    0 9,18 * * * /usr/bin/python3 /路徑/push_orders.py >> /路徑/push.log 2>&1
"""
import glob
import os
import sys

import requests

# ===== 改這三行 =====
SYSTEM_URL = "http://你的主機:8000/api/cs/import"        # 部署後填入
TOKEN      = "你的通行碼"                                 # 與系統 JEWELRY_AUTH_TOKEN 相同
WATCH_DIR  = os.path.expanduser("~/Downloads/SHOPLINE")  # SHOPLINE 報表下載資料夾
# ====================

STATE = os.path.expanduser("~/.cs_last_push")   # 記住上次送過的檔名，避免重送


def newest_report(folder):
    files = glob.glob(os.path.join(folder, "*.xls")) + glob.glob(os.path.join(folder, "*.csv"))
    return max(files, key=os.path.getmtime) if files else None


def main():
    latest = newest_report(WATCH_DIR)
    if not latest:
        print("找不到報表檔（.xls/.csv）：", WATCH_DIR)
        return 1

    name = os.path.basename(latest)
    last = open(STATE).read().strip() if os.path.exists(STATE) else ""
    if name == last:
        print("沒有新報表，略過：", name)
        return 0

    print("送出：", name)
    with open(latest, "rb") as f:
        r = requests.post(
            SYSTEM_URL,
            headers={"Authorization": f"Bearer {TOKEN}"},
            params={"source": "auto"},
            files={"file": (name, f)},
            timeout=120,
        )
    print(r.status_code, r.text[:200])
    if r.ok:
        with open(STATE, "w") as s:
            s.write(name)
        return 0
    return 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:           # 連不到/逾時等，記錄但不讓排程崩潰
        print("匯入失敗：", e)
        sys.exit(1)
