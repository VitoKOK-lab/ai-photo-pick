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
    gemstone TEXT, gemstone_confidence REAL,
    diamond_status TEXT,
    stone_shape TEXT, stone_shape_confidence REAL,
    stone_size TEXT, stone_size_confidence REAL,
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

-- ── 客服訂單追蹤（SHOPLINE 匯入 + 交接班）──────────────────────────────────
CREATE TABLE IF NOT EXISTS cs_orders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_number TEXT NOT NULL UNIQUE,   -- SHOPLINE 訂單號碼（去重鍵）
    customer_name TEXT,
    phone TEXT,
    order_date TEXT,                     -- 訂單成立日期（原文）
    total TEXT,                          -- 訂單金額（原文）
    item_summary TEXT,                   -- 商品名稱
    sl_order_status TEXT,               -- SHOPLINE 訂單狀態（原文）
    sl_payment_status TEXT,             -- SHOPLINE 付款狀態（原文）
    sl_shipping_status TEXT,            -- SHOPLINE 出貨狀態（原文）
    -- 內部追蹤欄位（同仁手動維護，匯入不覆蓋）
    track_status TEXT DEFAULT '待處理',   -- 目前進度（單一下拉，見 config/cs_workflow.json）
    product_type TEXT DEFAULT '規格',     -- 規格 / 訂製（決定出貨期限 14 或 45 天）
    sla_days INTEGER,                    -- 出貨期天數（規格14/訂製45）
    due_ship_date TEXT,                  -- 出貨期限 = 下單日 + sla_days（YYYY-MM-DD）
    owner TEXT,                          -- 目前負責人
    last_handler TEXT,                   -- 最後處理人（誰動過這張單）
    next_action TEXT,                    -- 下一步動作
    due_date TEXT,                       -- 預計出貨/完成日（YYYY-MM-DD）
    is_risk INTEGER DEFAULT 0,           -- 異常旗標
    risk_type TEXT,                      -- 異常類型
    notes TEXT,
    customer_id TEXT,                    -- SHOPLINE 顧客 ID（串客人歷史用）
    -- ── 取自內部追蹤總表的真實欄位 ──
    customer_source TEXT,               -- 客戶來源（官網/LINE/維修）〔SHOPLINE〕
    sales_rep TEXT,                     -- 銷售業務〔SHOPLINE/員工〕
    payment_method TEXT,               -- 付款方式/匯款後五碼〔SHOPLINE〕
    gold_work_date TEXT,               -- 上訂金工日期〔員工〕
    accounting_by TEXT,                -- 會計確認人〔員工〕
    accounting_at TEXT,                -- 會計確認時間〔員工〕
    notify_7d_at TEXT, notify_7d_by TEXT,   -- 客戶追蹤通知 7 天（下單日起算）
    notify_14d_at TEXT, notify_14d_by TEXT, -- 14 天
    notify_21d_at TEXT, notify_21d_by TEXT, -- 21 天
    order_goods_by TEXT,               -- 叫貨登記人
    order_goods_at TEXT,               -- 叫貨日期
    stone_source TEXT,                 -- 裸石出處
    main_stone TEXT,                   -- 主石
    main_stone_photo TEXT,             -- 主石照片（連結）
    custom_style_photo TEXT,           -- 訂製款式照片（連結）
    weight_ct TEXT,                    -- 重量 ct
    dimensions TEXT,                   -- 長*寬*厚
    material TEXT,                     -- 材質
    side_stone TEXT,                   -- 配鑽
    plating TEXT,                      -- 鍍金
    item_kind TEXT,                    -- 品項
    unit TEXT,                         -- 單位
    ring_size TEXT,                    -- 圍數
    chase_by TEXT,                     -- 追單人
    factory TEXT,                      -- 工廠
    model3d_img TEXT,                  -- 3D圖（連結）
    model3d_confirmed TEXT,            -- 3D圖確認完（日期/打勾）
    arrival_date TEXT,                 -- 到貨日期
    arrival_photo TEXT,                -- 到貨照片（連結）
    product_video TEXT,                -- 成品視頻檔案連結
    ship_from TEXT,                    -- 出貨地點
    warranty_card TEXT,                -- 保卡/證書
    ecard_link TEXT,                   -- 電子保卡連結
    ship_to_tw_at TEXT,                -- 寄回台灣時間
    ship_tracking TEXT,                -- 寄件編號/寄送方式
    arrive_tw_at TEXT,                 -- 到台灣時間
    tw_receiver TEXT,                  -- 台灣接貨點檢貨收貨人
    ship_to_customer_at TEXT,          -- 出貨時間（給客人）
    ship_by TEXT,                      -- 出貨/寄件人
    review_ecard TEXT,                 -- 5星好評/電子保卡確定交貨
    order_closed TEXT,                 -- 官網結案
    aftersale TEXT,                    -- 退換貨/維修
    aftersale_notes TEXT,              -- 售後進度備註
    return_status TEXT,                  -- 退貨簽核：待簽核/已核准/已駁回（NULL=無退貨）
    return_reason TEXT,                  -- 退貨原因
    return_signed_by TEXT,               -- 簽核人
    return_signed_at TEXT,               -- 簽核時間
    shipped_at TEXT,                     -- 首次偵測到已出貨的日期（YYYY-MM-DD）
    completed_at TEXT,                   -- 首次偵測到已完成（送達）的日期，退換貨期由此起算
    archived INTEGER DEFAULT 0,          -- 0=在看板上, 1=已封存進資料庫
    raw_json TEXT,                       -- 原始整列備份，不遺失任何欄位
    first_imported_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_cs_orders_status   ON cs_orders(track_status);
CREATE INDEX IF NOT EXISTS idx_cs_orders_archived ON cs_orders(archived);
CREATE INDEX IF NOT EXISTS idx_cs_orders_risk     ON cs_orders(is_risk);
CREATE INDEX IF NOT EXISTS idx_cs_orders_customer ON cs_orders(customer_id);

-- 購物旅程：每張單的時間軸（系統自動 + 員工 + 客人，誰在何時做了/說了什麼）
CREATE TABLE IF NOT EXISTS cs_order_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id INTEGER NOT NULL,
    occurred_at TEXT,                    -- 事件發生時間（YYYY-MM-DD HH:MM）
    actor TEXT,                          -- 誰：員工名 / 客人 / 系統
    actor_type TEXT DEFAULT 'staff',     -- staff / customer / system
    kind TEXT DEFAULT 'note',            -- system / stage / note / risk
    content TEXT,                        -- 做了什麼 / 說了什麼
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (order_id) REFERENCES cs_orders(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_cs_events_order ON cs_order_events(order_id);

-- 匯入記錄：每次匯入（自動或手動）的結果，供「自動匯入」頁顯示狀態與歷史
CREATE TABLE IF NOT EXISTS cs_import_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    imported_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    source TEXT DEFAULT 'manual',        -- auto（定時自動）/ manual（手動補匯）
    filename TEXT,
    rows_read INTEGER DEFAULT 0,
    orders_in_file INTEGER DEFAULT 0,
    new_count INTEGER DEFAULT 0,
    updated_count INTEGER DEFAULT 0,
    archived_count INTEGER DEFAULT 0,
    status TEXT DEFAULT 'ok',            -- ok / error
    message TEXT
);

CREATE TABLE IF NOT EXISTS cs_handovers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    shift_date TEXT,                     -- 交班日期
    from_staff TEXT,                     -- 交班人
    to_staff TEXT,                       -- 接班人
    watch_orders TEXT,                   -- 要特別盯的單號
    note TEXT,                           -- 叮嚀
    acked INTEGER DEFAULT 0,             -- 接班人已確認
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_cs_handovers_date ON cs_handovers(shift_date);
"""
