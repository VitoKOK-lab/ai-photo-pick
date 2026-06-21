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
    stone_shape TEXT, stone_shape_confidence REAL,
    stone_size TEXT, stone_size_confidence REAL,
    gemstone TEXT, gemstone_confidence REAL,
    style TEXT, style_confidence REAL,
    setting_amount TEXT,
    craft_complexity TEXT,
    metal_color TEXT,
    diamond_status TEXT,
    photo_type TEXT,
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

CREATE TABLE IF NOT EXISTS staff (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS customers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    line_id TEXT,
    phone TEXT,
    notes TEXT,
    session_count INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_customers_line_id ON customers(line_id);

CREATE TABLE IF NOT EXISTS customer_tags (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    customer_id INTEGER NOT NULL,
    tag TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (customer_id) REFERENCES customers(id) ON DELETE CASCADE,
    UNIQUE(customer_id, tag)
);
CREATE INDEX IF NOT EXISTS idx_customer_tags_cid ON customer_tags(customer_id);

CREATE TABLE IF NOT EXISTS customer_sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    customer_id INTEGER NOT NULL,
    staff_id INTEGER,
    notes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (customer_id) REFERENCES customers(id) ON DELETE CASCADE,
    FOREIGN KEY (staff_id) REFERENCES staff(id)
);

CREATE TABLE IF NOT EXISTS customer_favorites (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    customer_id INTEGER NOT NULL,
    photo_id INTEGER NOT NULL,
    session_id INTEGER,
    note TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (customer_id) REFERENCES customers(id) ON DELETE CASCADE,
    FOREIGN KEY (photo_id) REFERENCES photos(id),
    FOREIGN KEY (session_id) REFERENCES customer_sessions(id)
);
CREATE INDEX IF NOT EXISTS idx_cf_customer  ON customer_favorites(customer_id);
CREATE INDEX IF NOT EXISTS idx_cf_photo     ON customer_favorites(photo_id);

CREATE TABLE IF NOT EXISTS transactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    item_name TEXT NOT NULL,
    category TEXT,
    material TEXT,
    gemstone TEXT,
    stone_spec TEXT,
    metal_weight REAL,
    price INTEGER NOT NULL,
    sale_date DATE,
    notes TEXT,
    client_name TEXT,
    photo_id INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (photo_id) REFERENCES photos(id)
);
CREATE INDEX IF NOT EXISTS idx_tx_material ON transactions(material);
CREATE INDEX IF NOT EXISTS idx_tx_gemstone ON transactions(gemstone);
CREATE INDEX IF NOT EXISTS idx_tx_date     ON transactions(sale_date);
CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    name          TEXT NOT NULL,
    username      TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    role          TEXT NOT NULL DEFAULT 'editor' CHECK(role IN ('admin','editor','viewer')),
    is_active     INTEGER NOT NULL DEFAULT 1,
    created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS guest_links (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    token         TEXT NOT NULL UNIQUE,
    customer_id   INTEGER NOT NULL,
    customer_name TEXT NOT NULL,
    created_by    TEXT,
    expires_at    TIMESTAMP NOT NULL,
    created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    is_active     INTEGER NOT NULL DEFAULT 1,
    FOREIGN KEY (customer_id) REFERENCES customers(id)
);
"""
