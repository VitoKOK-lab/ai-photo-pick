"""test_api.py - API 端點測試"""
import sqlite3
import pytest


# ─── Health ─────────────────────────────────────────────────
def test_health(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


# ─── Photos ─────────────────────────────────────────────────
class TestPhotos:
    def test_list_empty(self, client):
        r = client.get("/api/photos")
        assert r.status_code == 200
        d = r.json()
        assert d["total"] == 0
        assert d["photos"] == []

    def test_list_with_photo(self, client, photo_id):
        r = client.get("/api/photos")
        assert r.status_code == 200
        assert r.json()["total"] == 1
        assert r.json()["photos"][0]["id"] == photo_id

    def test_get_photo(self, client, photo_id):
        r = client.get(f"/api/photos/{photo_id}")
        assert r.status_code == 200
        assert r.json()["id"] == photo_id
        assert r.json()["category"] == "戒指"

    def test_get_photo_not_found(self, client):
        r = client.get("/api/photos/9999")
        assert r.status_code == 404

    def test_filter_by_category(self, client, photo_id, photo_id2):
        r = client.get("/api/photos?category=戒指")
        assert r.status_code == 200
        assert r.json()["total"] == 1
        assert r.json()["photos"][0]["category"] == "戒指"

    def test_filter_by_color(self, client, photo_id, photo_id2):
        r = client.get("/api/photos?color=藍")
        assert r.json()["total"] == 1
        assert r.json()["photos"][0]["color"] == "藍"

    def test_sort_newest(self, client, photo_id):
        r = client.get("/api/photos?sort=newest")
        assert r.status_code == 200

    def test_sort_popular(self, client, photo_id):
        r = client.get("/api/photos?sort=popular")
        assert r.status_code == 200

    def test_invalid_sort(self, client):
        r = client.get("/api/photos?sort=invalid")
        assert r.status_code == 422


# ─── Events ─────────────────────────────────────────────────
class TestEvents:
    def test_log_view(self, client, photo_id):
        r = client.post("/api/events", json={
            "photo_id": photo_id,
            "event_type": "view",
            "session_id": "sess_test",
        })
        assert r.status_code == 200
        assert "id" in r.json()

    def test_log_invalid_type(self, client, photo_id):
        r = client.post("/api/events", json={
            "photo_id": photo_id,
            "event_type": "INVALID",
            "session_id": "sess_test",
        })
        assert r.status_code == 200
        assert "error" in r.json()

    def test_view_increments_count(self, client, photo_id, tmp_db):
        client.post("/api/events", json={
            "photo_id": photo_id, "event_type": "view", "session_id": "s1"
        })
        client.post("/api/events", json={
            "photo_id": photo_id, "event_type": "view", "session_id": "s1"
        })
        conn = sqlite3.connect(tmp_db)
        row = conn.execute("SELECT view_count FROM photos WHERE id=?", (photo_id,)).fetchone()
        conn.close()
        assert row[0] == 2

    def test_dwell_accumulates(self, client, photo_id, tmp_db):
        client.post("/api/events", json={
            "photo_id": photo_id, "event_type": "dwell",
            "session_id": "s1", "dwell_ms": 3000
        })
        conn = sqlite3.connect(tmp_db)
        row = conn.execute("SELECT total_dwell_ms FROM photos WHERE id=?", (photo_id,)).fetchone()
        conn.close()
        assert row[0] == 3000


# ─── Favorites ───────────────────────────────────────────────
class TestFavorites:
    def test_add_and_list(self, client, photo_id):
        r = client.post("/api/favorites", json={
            "photo_id": photo_id, "session_id": "sess_a"
        })
        assert r.status_code == 200
        assert r.json()["photo_id"] == photo_id

        r = client.get("/api/favorites?session_id=sess_a")
        assert r.json()["total"] == 1

    def test_add_duplicate(self, client, photo_id):
        client.post("/api/favorites", json={"photo_id": photo_id, "session_id": "s"})
        r = client.post("/api/favorites", json={"photo_id": photo_id, "session_id": "s"})
        assert r.json().get("already_exists") is True

    def test_remove(self, client, photo_id):
        client.post("/api/favorites", json={"photo_id": photo_id, "session_id": "s"})
        r = client.delete(f"/api/favorites/{photo_id}?session_id=s")
        assert r.json()["deleted"] is True

        r = client.get("/api/favorites?session_id=s")
        assert r.json()["total"] == 0

    def test_sessions_isolated(self, client, photo_id):
        client.post("/api/favorites", json={"photo_id": photo_id, "session_id": "s1"})
        r = client.get("/api/favorites?session_id=s2")
        assert r.json()["total"] == 0


# ─── Stats ───────────────────────────────────────────────────
class TestStats:
    def test_overview_empty(self, client):
        r = client.get("/api/stats/overview")
        assert r.status_code == 200
        d = r.json()
        assert d["total_photos"] == 0

    def test_overview_with_photo(self, client, photo_id):
        r = client.get("/api/stats/overview")
        assert r.json()["total_photos"] == 1

    def test_by_dimension(self, client, photo_id):
        r = client.get("/api/stats/by-dimension?dim=category")
        assert r.status_code == 200
        items = r.json()["items"]
        assert any(i["label"] == "戒指" for i in items)

    def test_by_dimension_invalid(self, client):
        r = client.get("/api/stats/by-dimension?dim=INVALID")
        assert r.status_code == 422

    def test_daily(self, client):
        r = client.get("/api/stats/daily?days=7")
        assert r.status_code == 200
        assert "data" in r.json()

    def test_top_photos(self, client, photo_id):
        r = client.get("/api/stats/top-photos?sort_by=views&limit=5")
        assert r.status_code == 200
        assert len(r.json()["photos"]) <= 5


# ─── Quotes ──────────────────────────────────────────────────
class TestQuotes:
    def test_create_and_list(self, client):
        r = client.post("/api/quotes", json={
            "description": "緬甸紅寶石", "final_price": 85000,
            "material": "18k黃金", "gemstone": "紅寶石"
        })
        assert r.status_code == 200
        assert "id" in r.json()

        r = client.get("/api/quotes")
        assert r.json()["total"] == 1

    def test_invalid_price(self, client):
        r = client.post("/api/quotes", json={"description": "X", "final_price": -1})
        assert r.status_code == 400

    def test_estimate_no_data(self, client):
        r = client.post("/api/quotes/estimate?material=18k黃金")
        assert r.json()["estimated"] is False

    def test_estimate_with_data(self, client):
        client.post("/api/quotes", json={
            "description": "A", "final_price": 80000,
            "material": "18k黃金", "gemstone": "紅寶石"
        })
        client.post("/api/quotes", json={
            "description": "B", "final_price": 90000,
            "material": "18k黃金", "gemstone": "紅寶石"
        })
        r = client.post("/api/quotes/estimate?material=18k黃金&gemstone=紅寶石")
        d = r.json()
        assert d["estimated"] is True
        assert d["price_estimate_low"] <= d["price_estimate_high"]
        assert d["sample_count"] == 2

    def test_delete(self, client):
        r = client.post("/api/quotes", json={"description": "X", "final_price": 10000})
        qid = r.json()["id"]
        r = client.delete(f"/api/quotes/{qid}")
        assert r.json()["deleted"] is True
        assert client.get("/api/quotes").json()["total"] == 0

    def test_batch_estimate(self, client, photo_id):
        # 加報價
        client.post("/api/quotes", json={
            "description": "A", "final_price": 80000,
            "material": "18k黃金", "gemstone": "紅寶石"
        })
        client.post("/api/quotes", json={
            "description": "B", "final_price": 90000,
            "material": "18k黃金", "gemstone": "紅寶石"
        })
        r = client.post("/api/quotes/batch-estimate?min_samples=1")
        assert r.status_code == 200
        assert r.json()["updated"] >= 1


# ─── Backup ──────────────────────────────────────────────────
class TestBackup:
    def test_status(self, client):
        r = client.get("/api/backup/status")
        assert r.status_code == 200
        assert r.json()["running"] is False
        assert r.json()["last_backup"] is None

    def test_trigger(self, client):
        r = client.post("/api/backup/trigger?db_only=true")
        assert r.status_code == 200
        assert "背景" in r.json()["message"]

    def test_trigger_conflict(self, client):
        import api.backup
        api.backup._backup_running = True
        r = client.post("/api/backup/trigger")
        assert r.status_code == 409
        api.backup._backup_running = False


# ─── Customer Service: 訂單追蹤 + 匯入 + 交接班 ───────────────
SHOPLINE_CSV = (
    "訂單號碼,收件人姓名,收件人電話,訂單成立日期,商品名稱,訂單總額,付款狀態,出貨狀態\n"
    "20260601001,王小明,0912345678,2026-06-01,黑歐泊戒指,NT$22569,已付款,處理中\n"
    "20260601002,李小華,0922333444,2026-06-01,紅寶石墜子,NT$58000,未付款,未出貨\n"
    "20260601003,陳大文,0933555777,2026-06-01,證書套組,NT$12000,已付款,已出貨\n"
)


def _import(client, csv_text=SHOPLINE_CSV):
    return client.post(
        "/api/cs/import",
        files={"file": ("shopline.csv", csv_text, "text/csv")},
    )


class TestCSImport:
    def test_import_new_orders(self, client):
        r = _import(client)
        assert r.status_code == 200
        d = r.json()
        assert d["new"] == 3
        assert d["updated"] == 0
        assert "order_number" in d["columns_matched"]

    def test_import_dedup(self, client):
        _import(client)
        r = _import(client)          # 同一份再匯入一次
        d = r.json()
        assert d["new"] == 0         # 不重複建單
        assert d["updated"] == 3     # 只更新既有

    def test_import_log_recorded(self, client):
        # 自動匯入帶 source=auto，會寫一筆成功記錄
        client.post("/api/cs/import?source=auto",
                    files={"file": ("shopline.csv", SHOPLINE_CSV, "text/csv")})
        log = client.get("/api/cs/import-log").json()
        assert len(log) == 1
        assert log[0]["source"] == "auto"
        assert log[0]["status"] == "ok"
        assert log[0]["new_count"] == 3
        # 儀表板帶出最後一次匯入狀態
        d = client.get("/api/cs/dashboard").json()
        assert d["last_import_log"]["status"] == "ok"

    def test_import_log_records_failure(self, client):
        # 找不到訂單號欄位 → 記一筆 error
        r = _import(client, "姓名,金額\n王小明,100\n")
        assert r.status_code == 400
        log = client.get("/api/cs/import-log").json()
        assert log[0]["status"] == "error"

    def test_initial_track_status(self, client):
        _import(client)
        rows = client.get("/api/cs/orders?view=all").json()
        by_no = {o["order_number"]: o for o in rows}
        # 新單一律從流程第一關「下單待入帳」起（台灣會計確認入帳）
        assert by_no["20260601002"]["track_status"] == "下單待入帳"
        assert by_no["20260601001"]["track_status"] == "下單待入帳"
        # 只追未完成：一進來就已出貨的單落到後段、且直接封存、不佔看板
        assert by_no["20260601003"]["track_status"] == "出貨回台灣(在途)"
        assert by_no["20260601003"]["shipped_at"] is not None
        assert by_no["20260601003"]["archived"] == 1
        active_nos = [o["order_number"] for o in client.get("/api/cs/orders?view=active").json()]
        assert set(active_nos) == {"20260601001", "20260601002"}

    def test_import_missing_order_column(self, client):
        r = _import(client, "姓名,金額\n王小明,100\n")
        assert r.status_code == 400


# 真實 SHOPLINE 報表：一張訂單橫跨多列、訂單號帶 '#'、欄名為「收件人/訂單合計/送貨狀態」
MULTI_ROW_CSV = (
    "訂單號碼,收件人,收件人電話號碼,訂單日期,商品名稱,數量,訂單合計,付款狀態,送貨狀態,訂單狀態\n"
    "#A100,林小姐,0911000111,2026-06-01,藍寶戒,1,30000,已付款,備貨中,處理中\n"
    "#A100,林小姐,0911000111,2026-06-01,珍珠耳環,2,30000,已付款,備貨中,處理中\n"
    "#A200,陳先生,0922000222,2026-06-02,紅寶墜,1,50000,已付款,已到達,已完成\n"
)


class TestCSImportGrouping:
    def test_multi_row_grouped_into_one_order(self, client):
        d = _import(client, MULTI_ROW_CSV).json()
        assert d["rows_read"] == 3
        assert d["orders_in_file"] == 2          # 兩張單，非三列
        assert d["new"] == 2
        # 真實欄名都對得上
        m = d["columns_matched"]
        assert m["customer_name"] == "收件人"
        assert m["total"] == "訂單合計"
        assert m["sl_shipping_status"] == "送貨狀態"

    def test_order_number_hash_stripped_and_items_aggregated(self, client):
        _import(client, MULTI_ROW_CSV)
        by_no = {o["order_number"]: o for o in client.get("/api/cs/orders?view=all").json()}
        assert "A100" in by_no and "#A100" not in by_no   # '#' 去前綴
        a100 = by_no["A100"]
        assert a100["customer_name"] == "林小姐"
        assert a100["item_summary"] == "藍寶戒、珍珠耳環×2"  # 跨列彙整＋數量
        assert a100["order_date"] == "2026-06-01"

    def test_only_unfinished_on_board(self, client):
        _import(client, MULTI_ROW_CSV)
        active = [o["order_number"] for o in client.get("/api/cs/orders?view=active").json()]
        archived = [o["order_number"] for o in client.get("/api/cs/orders?view=archived").json()]
        assert active == ["A100"]        # 備貨中／處理中 → 看板
        assert archived == ["A200"]      # 已到達／已完成 → 直接封存

    def test_excel_serial_date_conversion(self):
        """xls 的訂單日期是 Excel 序號，需轉成 ISO 日期。"""
        from api.cs import _cell
        # 46143 = 2026-05-01（1900 datemode）
        assert _cell(46143.0, datemode=0, is_date=True) == "2026-05-01"
        assert _cell(1360.0) == "1360"   # 金額去掉 .0


class TestCSBoard:
    def test_dashboard_counts(self, client):
        _import(client)
        d = client.get("/api/cs/dashboard").json()
        assert d["active"] == 2          # 已出貨的 003 直接封存，不算進行中
        assert d["risk"] == 0

    def test_update_and_risk_flag(self, client):
        _import(client)
        oid = client.get("/api/cs/orders?view=active").json()[0]["id"]
        r = client.put(f"/api/cs/orders/{oid}", json={
            "is_risk": True, "risk_type": "欠石", "owner": "深圳-阿明",
            "next_action": "聯絡客人告知延期", "track_status": "台灣已收待出貨",
        })
        assert r.status_code == 200
        assert r.json()["is_risk"] == 1
        # 異常檢視應抓到它
        risk = client.get("/api/cs/orders?view=risk").json()
        assert any(o["id"] == oid for o in risk)
        assert client.get("/api/cs/dashboard").json()["risk"] == 1

    def test_overdue_flag(self, client):
        _import(client)
        oid = client.get("/api/cs/orders?view=active").json()[0]["id"]
        client.put(f"/api/cs/orders/{oid}", json={"due_date": "2020-01-01"})
        o = client.get(f"/api/cs/orders/{oid}").json()
        assert o["overdue"] is True
        assert any(x["id"] == oid for x in client.get("/api/cs/orders?view=overdue").json())

    def test_search(self, client):
        _import(client)
        rows = client.get("/api/cs/orders?view=all&q=紅寶石").json()
        assert len(rows) == 1
        assert rows[0]["order_number"] == "20260601002"

    def test_manual_archive_removes_from_board(self, client):
        _import(client)
        oid = client.get("/api/cs/orders?view=active").json()[0]["id"]
        client.put(f"/api/cs/orders/{oid}", json={"archived": True})
        active_ids = [o["id"] for o in client.get("/api/cs/orders?view=active").json()]
        assert oid not in active_ids


# 進度流程 + 出貨期限急迫度 + 購物旅程時間軸 + 客人歷史
WORKFLOW_CSV = (
    "訂單號碼,收件人,收件人電話號碼,顧客 ID,訂單日期,商品名稱,訂單合計,付款狀態,送貨狀態,訂單狀態\n"
    "S1,王小明,0911,C001,2026-06-08,藍寶石戒指,30000,已付款,備貨中,處理中\n"
    "S2,王小明,0911,C001,2026-05-01,訂製-綠碧璽吊墜,52000,已付款,備貨中,處理中\n"
)


class TestCSWorkflow:
    def test_product_type_and_sla(self, client):
        _import(client, WORKFLOW_CSV)
        by_no = {o["order_number"]: o for o in client.get("/api/cs/orders?view=all").json()}
        s1 = by_no["S1"]
        assert s1["product_type"] == "規格"
        assert s1["sla_days"] == 14
        assert s1["due_ship_date"] == "2026-06-22"   # 6/08 + 14
        s2 = by_no["S2"]
        assert s2["product_type"] == "訂製"           # 商品名含「訂製」
        assert s2["sla_days"] == 45
        assert s2["due_ship_date"] == "2026-06-15"   # 5/01 + 45

    def test_timeline_seeded_and_stage_logged(self, client):
        _import(client, WORKFLOW_CSV)
        oid = client.get("/api/cs/orders?view=all&q=S1").json()[0]["id"]
        # 匯入時已種下「客人下單」系統事件
        o = client.get(f"/api/cs/orders/{oid}").json()
        kinds = [(e["kind"], e["content"]) for e in o["timeline"]]
        assert any(k == "system" and "下單" in c for k, c in kinds)
        # 推進進度 → 自動記錄誰、做了什麼
        client.put(f"/api/cs/orders/{oid}", json={
            "track_status": "已叫貨追單中", "handler": "深圳-阿明"})
        o = client.get(f"/api/cs/orders/{oid}").json()
        assert o["last_handler"] == "深圳-阿明"
        assert any(e["kind"] == "stage" and "已叫貨追單中" in e["content"]
                   and e["actor"] == "深圳-阿明" for e in o["timeline"])

    def test_add_customer_message(self, client):
        _import(client, WORKFLOW_CSV)
        oid = client.get("/api/cs/orders?view=all&q=S1").json()[0]["id"]
        r = client.post(f"/api/cs/orders/{oid}/events", json={
            "actor": "王小明", "actor_type": "customer", "content": "想改成18號圈口"})
        assert r.status_code == 201
        o = client.get(f"/api/cs/orders/{oid}").json()
        assert any(e["actor_type"] == "customer" and "18號" in e["content"]
                   for e in o["timeline"])

    def test_customer_history(self, client):
        _import(client, WORKFLOW_CSV)
        rows = client.get("/api/cs/customers/history?customer_id=C001").json()
        assert len(rows) == 2                         # 同一顧客兩張單
        assert {r["order_number"] for r in rows} == {"S1", "S2"}

    def test_urgency_sort_most_urgent_first(self, client):
        _import(client, WORKFLOW_CSV)
        active = client.get("/api/cs/orders?view=active").json()
        # 出貨期限較近的排前面（S2 訂製到期 6/15 早於 S1 規格 6/22）
        nums = [o["order_number"] for o in active]
        assert nums.index("S2") < nums.index("S1")

    def test_stages_single_flow_from_real_sheet(self, client):
        meta = client.get("/api/cs/meta").json()
        stages = meta["stages"]
        # 規格與訂製共用同一套流程（依內部追蹤總表）
        assert "stages_by_type" not in meta
        assert stages[0] == "下單待入帳"
        assert stages[-1] == "已完成結案"
        for s in ("待叫貨", "已叫貨追單中", "出貨回台灣(在途)", "已出貨給客人"):
            assert s in stages
        # 客戶追蹤通知天數（從下單日起算）
        assert meta["customer_notify_days"] == [7, 14, 21]

    def test_return_signoff_flow(self, client):
        _import(client, WORKFLOW_CSV)
        oid = client.get("/api/cs/orders?view=all&q=S1").json()[0]["id"]
        # 申請 → 待簽核
        r = client.post(f"/api/cs/orders/{oid}/return",
                        json={"action": "request", "by": "客服-小芳", "reason": "尺寸不合"})
        assert r.json()["return_status"] == "待簽核"
        # 主管核准 → 記錄簽核人/時間 + 旅程
        r = client.post(f"/api/cs/orders/{oid}/return",
                        json={"action": "approve", "by": "店長-阿德"})
        o = r.json()
        assert o["return_status"] == "已核准"
        assert o["return_signed_by"] == "店長-阿德"
        assert o["return_signed_at"]
        assert any(e["kind"] == "return" and "核准" in e["content"] for e in o["timeline"])

    def test_worklist_prioritises_and_suggests_action(self, client):
        _import(client, WORKFLOW_CSV)
        wl = client.get("/api/cs/worklist").json()
        # S2（下單 5/01）早已過 7/14/21 → 該主動通知客人 → 排進「急」
        assert any(i["order_number"] == "S2" and i["notify_due"] == 21 for i in wl["urgent"])
        assert any("通知客人" in (i["reason"] or "") for i in wl["urgent"])
        # 每筆待辦都帶「該做什麼」一句話（目標②：員工知道做什麼）
        allitems = wl["urgent"] + wl["today"]
        assert all("action" in i for i in allitems)
        s1 = next(i for i in allitems if i["order_number"] == "S1")
        assert s1["action"] == "台灣會計確認入帳"

    def test_notify_done_clears_from_urgent(self, client):
        _import(client, WORKFLOW_CSV)
        oid = client.get("/api/cs/orders?view=all&q=S2").json()[0]["id"]
        r = client.post(f"/api/cs/orders/{oid}/notify", json={"day": 21, "by": "台灣-阿May"})
        assert r.status_code == 200
        o = client.get(f"/api/cs/orders/{oid}").json()
        assert any("通知客人" in e["content"] for e in o["timeline"])
        # 通知後不再因「該通知」而列入急件
        wl = client.get("/api/cs/worklist").json()
        assert not any(i["order_number"] == "S2" and i["notify_due"] for i in wl["urgent"])


class TestCSHandover:
    def test_create_and_ack(self, client):
        r = client.post("/api/cs/handover", json={
            "from_staff": "台灣-小美", "to_staff": "深圳-阿明",
            "watch_orders": "20260601002", "note": "這張欠石，已通知客人延一週",
        })
        assert r.status_code == 201
        hid = r.json()["id"]
        assert r.json()["acked"] == 0
        client.post(f"/api/cs/handover/{hid}/ack")
        rows = client.get("/api/cs/handover").json()
        assert rows[0]["acked"] == 1
