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
