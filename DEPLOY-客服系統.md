# 客服訂單追蹤系統 — 雲端部署白話指南

這份是給「非工程師」照著做的步驟。目標：把系統架在**一台台灣的雲主機**上，
大陸同仁用現有 VPN（跟連 SHOPLINE 同一條）連進來，8 個人一起用。

全程約 30 分鐘。指令是一行一行複製貼上即可。

---

## 0. 你會得到什麼

- 一個網址，例如：`http://你的主機IP:8000/cs.html?token=你設的通行碼`
- 8 個客服用瀏覽器打開就能用，不用裝任何東西
- 只有知道通行碼的人進得來
- 每天兩次：從 SHOPLINE 匯出報表 → 在頁面上「⬆ 上傳」即可

---

## 1. 開一台台灣雲主機

選一家台灣機房的雲主機（大陸 VPN 連台灣最順）：

- **Google Cloud**：地區選 `asia-east1`（台灣彰化）
- 或 **中華電信 HiCloud**、其他台灣機房供應商

規格：**最小台就夠**（1～2 核心、2GB 記憶體、20GB 硬碟）。
作業系統選 **Ubuntu 22.04 LTS**。

開好後你會拿到：主機的 **公用 IP**、登入用的 **帳號/金鑰**。

---

## 2. 連進主機並安裝基本工具

用 SSH 連進主機後，依序執行：

```bash
sudo apt update
sudo apt install -y python3 python3-pip python3-venv git
```

---

## 3. 取得程式

```bash
cd ~
git clone <你的程式庫網址> ai-photo-pick
cd ai-photo-pick
```

> 大陸連 GitHub 若太慢，可改用 Gitee 鏡像，或請台灣這邊先下載再上傳到主機。
> 客服每天用系統時**完全不需要** GitHub，這步只有「裝/更新程式」時才用到。

---

## 4. 安裝套件（輕量版，免裝影像辨識）

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements-cs.txt
```

只會裝 5 個小套件，1～2 分鐘完成。

---

## 5. 設定通行碼（保護資料）

建立一個 `.env` 檔，放一組只有你們知道的通行碼：

```bash
echo "JEWELRY_AUTH_TOKEN=改成你自己的長密碼" > .env
```

> 建議用 16 碼以上的英數混合，例如 `kx7Qm2Vp9Lz4Rt8`。
> 設了之後，沒有通行碼的人連到網址只會看到登入頁，進不來。

---

## 6. 建立資料庫

```bash
python scripts/init_cs_db.py
```

看到 `[OK] 資料庫已建立` 就成功。資料會存在 `db/jewelry.sqlite` 這個檔。

---

## 7. 先手動啟動測試

```bash
uvicorn api.cs_app:app --host 0.0.0.0 --port 8000
```

在你自己電腦的瀏覽器打開：
`http://你的主機IP:8000/cs.html?token=你設的通行碼`

看到客服看板就成功了。確認沒問題後，按 `Ctrl + C` 停掉，進入下一步做成自動啟動。

---

## 8. 設成開機自動啟動（重開機也不怕）

建立服務設定檔：

```bash
sudo nano /etc/systemd/system/cs.service
```

貼上以下內容（把 `你的使用者名稱` 換成實際登入帳號，路徑若不同也改一下）：

```ini
[Unit]
Description=客服訂單追蹤
After=network.target

[Service]
User=你的使用者名稱
WorkingDirectory=/home/你的使用者名稱/ai-photo-pick
EnvironmentFile=/home/你的使用者名稱/ai-photo-pick/.env
ExecStart=/home/你的使用者名稱/ai-photo-pick/venv/bin/uvicorn api.cs_app:app --host 0.0.0.0 --port 8000
Restart=always

[Install]
WantedBy=multi-user.target
```

存檔（`Ctrl+O`、`Enter`、`Ctrl+X`），然後啟用：

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now cs.service
sudo systemctl status cs.service   # 看到 active (running) 就成功
```

從此主機重開機，系統會自動跑起來，不用人顧。

---

## 9. 連線與安全

雲主機有公用 IP，建議**把連線限制在你們的人**，兩種做法擇一或併用：

1. **通行碼**（第 5 步已設）— 基本防護，先有這個就好。
2. **防火牆只放行特定 IP**（更安全）— 在雲主機後台的防火牆設定，
   只允許「台灣辦公室對外 IP」和「大陸 VPN 的出口 IP」連 8000 埠，其他全擋。
   不確定 IP 的話可先用通行碼，之後再補。

---

## 10. 給客服的使用方式

把這個網址發給 8 位同仁（含通行碼，開一次後瀏覽器會記住）：

```
http://你的主機IP:8000/cs.html?token=你設的通行碼
```

- 右上角「我是」填自己名字（只填一次，記在那台電腦）→ 之後操作會自動記在購物旅程上
- 每天兩次：SHOPLINE 匯出訂單報表 → 點「⬆ 上傳 SHOPLINE 報表」選檔上傳
- 系統自動合併、去重、算出貨期限、排急迫度

---

## 11. 每天備份（很重要）

所有資料就是一個檔 `db/jewelry.sqlite`，定時複製一份就是備份。
設定每天自動備份：

```bash
crontab -e
```

加入這一行（每天凌晨 2 點備份，保留在 backups 資料夾）：

```
0 2 * * * cp /home/你的使用者名稱/ai-photo-pick/db/jewelry.sqlite /home/你的使用者名稱/ai-photo-pick/db/backup-$(date +\%Y\%m\%d).sqlite
```

> 想更保險，可定期把備份檔下載到台灣辦公室電腦，或上傳雲端硬碟。

---

## 12. 之後更新程式

```bash
cd ~/ai-photo-pick
git pull
source venv/bin/activate
pip install -r requirements-cs.txt    # 偶爾有新套件才需要
sudo systemctl restart cs.service
```

資料（`db/jewelry.sqlite`）不會被更新覆蓋，放心。

---

## 常見問題

- **打不開網址？** 確認 systemd 是 `active (running)`，且雲主機防火牆有開 8000 埠。
- **看到登入頁？** 網址要帶 `?token=你的通行碼`。
- **要搬家/換主機？** 把整個資料夾搬過去，重點是 `db/jewelry.sqlite` 這個檔複製過去就保住所有資料。
- **想換埠號（例如 80，免打 :8000）？** 把上面 `--port 8000` 改成 `--port 80`，並開放 80 埠。
