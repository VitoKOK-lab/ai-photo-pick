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

    def test_initial_track_status(self, client):
        _import(client)
        rows = client.get("/api/cs/orders?view=all").json()
        by_no = {o["order_number"]: o for o in rows}
        assert by_no["20260601002"]["track_status"] == "待付款"   # 未付款
        assert by_no["20260601001"]["track_status"] == "製作中"   # 已付款未出貨
        # 只追未完成：一進來就已出貨的單直接封存、不佔看板
        assert by_no["20260601003"]["shipped_at"] is not None
        assert by_no["20260601003"]["archived"] == 1
        active_nos = [o["order_number"] for o in client.get("/api/cs/orders?view=active").json()]
        assert set(active_nos) == {"20260601001", "20260601002"}

    def test_import_missing_order_column(self, client):
        r = _import(client, "姓名,金額\n王小明,100\n")
        assert r.status_code == 400


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
            "next_action": "聯絡客人告知延期", "track_status": "售後處理中",
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
        archived_ids = [o["id"] for o in client.get("/api/cs/orders?view=archived").json()]
        assert oid in archived_ids


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
