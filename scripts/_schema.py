"""_schema.py - SQLite schema 定義（供 init 和 test 共用）"""

SCHEMA = """
CREATE TABLE IF NOT EXISTS photos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    filename TEXT NOT NULL UNIQUE,
    original_filename TEXT NOT NULL,
    original_path TEXT NOT NULL,
    full_path TEXT NOT NULL,
    thumb_path TEXT NOT NULL,
    micro_path TEXT NOT NULL,
    color TEXT, color_confidence REAL,
    category TEXT, category_confidence REAL,
    material TEXT, material_confidence REAL,
    diamond_status TEXT, diamond_confidence REAL,
    gemstone TEXT, gemstone_confidence REAL,
    style TEXT, style_confidence REAL,
    price_estimate_low INTEGER, price_estimate_high INTEGER,
    price_source TEXT, price_band TEXT,
    view_count INTEGER DEFAULT 0,
    click_count INTEGER DEFAULT 0,
    favorite_count INTEGER DEFAULT 0,
    lock_count INTEGER DEFAULT 0,
    total_dwell_ms INTEGER DEFAULT 0,
    file_hash TEXT NOT NULL UNIQUE,
    file_size INTEGER NOT NULL,
    width INTEGER, height INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_photos_color    ON photos(color);
CREATE INDEX IF NOT EXISTS idx_photos_category ON photos(category);
CREATE INDEX IF NOT EXISTS idx_photos_material ON photos(material);
CREATE INDEX IF NOT EXISTS idx_photos_gemstone ON photos(gemstone);
CREATE INDEX IF NOT EXISTS idx_photos_price_band ON photos(price_band);
CREATE INDEX IF NOT EXISTS idx_photos_hash     ON photos(file_hash);

CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    photo_id INTEGER NOT NULL,
    event_type TEXT NOT NULL,
    dwell_ms INTEGER,
    session_id TEXT,
    metadata_json TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (photo_id) REFERENCES photos(id)
);
CREATE INDEX IF NOT EXISTS idx_events_photo_id ON events(photo_id);
CREATE INDEX IF NOT EXISTS idx_events_type     ON events(event_type);
CREATE INDEX IF NOT EXISTS idx_events_session  ON events(session_id);

CREATE TABLE IF NOT EXISTS favorites (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    photo_id INTEGER NOT NULL,
    session_id TEXT NOT NULL,
    note TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (photo_id) REFERENCES photos(id),
    UNIQUE(photo_id, session_id)
);

CREATE TABLE IF NOT EXISTS locks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    photo_id INTEGER NOT NULL,
    lock_number INTEGER NOT NULL,
    customer_share_token TEXT,
    expires_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (photo_id) REFERENCES photos(id),
    UNIQUE(session_id, lock_number)
);

CREATE TABLE IF NOT EXISTS quotes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    photo_id INTEGER,
    description TEXT NOT NULL,
    final_price INTEGER NOT NULL,
    material TEXT,
    gemstone TEXT,
    gemstone_origin TEXT,
    quote_date DATE,
    notes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (photo_id) REFERENCES photos(id)
);
CREATE INDEX IF NOT EXISTS idx_quotes_gemstone ON quotes(gemstone);
CREATE INDEX IF NOT EXISTS idx_quotes_material ON quotes(material);
"""
