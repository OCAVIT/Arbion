-- =============================================
-- ARBION TEST DATA SEED
-- Run this in DbGate or any SQL client
-- =============================================

-- 1. Create test manager (password: test123)
-- Password hash for "test123" using bcrypt
INSERT INTO users (username, password_hash, role, display_name, is_active, created_at, updated_at)
VALUES (
    'test_manager',
    '$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/X4.VTtYt0CqJYbPfS',
    'manager',
    'Тест Менеджер',
    true,
    NOW(),
    NOW()
)
ON CONFLICT (username) DO NOTHING;

-- 2. Create test monitored chat
INSERT INTO monitored_chats (chat_id, title, member_count, status, source, useful_ratio, orders_found, deals_created, joined_at, created_at, updated_at)
VALUES (
    -1001234567890,
    'Test Trade Group',
    1000,
    'active',
    'seed',
    0.75,
    50,
    10,
    NOW(),
    NOW(),
    NOW()
)
ON CONFLICT (chat_id) DO NOTHING;

-- 3. Create test orders (buy and sell)
-- Your main account ID: 1173103063 (Xcherf) - this will be the BUYER
-- Bot account ID: 8141646325 (@StickerArsen) - this will be the SELLER

-- Buy order 1
INSERT INTO orders (order_type, chat_id, sender_id, message_id, product, price, quantity, region, raw_text, contact_info, is_active, created_at, updated_at)
VALUES (
    'buy',
    -1001234567890,
    1173103063,
    1001,
    'iPhone 15 Pro Max',
    95000.00,
    '1 шт',
    'Москва',
    'Куплю iPhone 15 Pro Max за 95000р, Москва',
    '@Xcherf',
    true,
    NOW(),
    NOW()
);

-- Sell order 1 (from bot account - AI will contact this)
INSERT INTO orders (order_type, chat_id, sender_id, message_id, product, price, quantity, region, raw_text, contact_info, is_active, created_at, updated_at)
VALUES (
    'sell',
    -1001234567890,
    1173103063,
    1002,
    'iPhone 15 Pro Max',
    105000.00,
    '1 шт',
    'Москва',
    'Продам iPhone 15 Pro Max за 105000р, Москва, новый в упаковке',
    '@Xcherf',
    true,
    NOW(),
    NOW()
);

-- Buy order 2
INSERT INTO orders (order_type, chat_id, sender_id, message_id, product, price, quantity, region, raw_text, contact_info, is_active, created_at, updated_at)
VALUES (
    'buy',
    -1001234567890,
    1173103063,
    1003,
    'MacBook Pro M3',
    180000.00,
    '1 шт',
    'СПб',
    'Куплю MacBook Pro M3 за 180000р, СПб',
    '@Xcherf',
    true,
    NOW(),
    NOW()
);

-- Sell order 2
INSERT INTO orders (order_type, chat_id, sender_id, message_id, product, price, quantity, region, raw_text, contact_info, is_active, created_at, updated_at)
VALUES (
    'sell',
    -1001234567890,
    1173103063,
    1004,
    'MacBook Pro M3',
    200000.00,
    '1 шт',
    'СПб',
    'Продам MacBook Pro M3 за 200000р, СПб, идеальное состояние',
    '@Xcherf',
    true,
    NOW(),
    NOW()
);

-- Buy order 3
INSERT INTO orders (order_type, chat_id, sender_id, message_id, product, price, quantity, region, raw_text, contact_info, is_active, created_at, updated_at)
VALUES (
    'buy',
    -1001234567890,
    1173103063,
    1005,
    'PlayStation 5',
    45000.00,
    '1 шт',
    'Казань',
    'Куплю PS5 за 45000р, Казань',
    '@Xcherf',
    true,
    NOW(),
    NOW()
);

-- Sell order 3
INSERT INTO orders (order_type, chat_id, sender_id, message_id, product, price, quantity, region, raw_text, contact_info, is_active, created_at, updated_at)
VALUES (
    'sell',
    -1001234567890,
    1173103063,
    1006,
    'PlayStation 5',
    55000.00,
    '1 шт',
    'Казань',
    'Продам PlayStation 5 за 55000р, Казань, с играми',
    '@Xcherf',
    true,
    NOW(),
    NOW()
);

-- 4. Create detected deals in different statuses
-- Get order IDs (assuming sequential insert)

-- COLD deal (iPhone) - AI hasn't contacted yet
INSERT INTO detected_deals (buy_order_id, sell_order_id, product, region, buy_price, sell_price, margin, status, buyer_chat_id, buyer_sender_id, ai_insight, created_at, updated_at)
SELECT
    b.id as buy_order_id,
    s.id as sell_order_id,
    'iPhone 15 Pro Max',
    'Москва',
    95000.00,
    105000.00,
    10000.00,
    'cold',
    -1001234567890,
    1173103063,
    NULL,
    NOW(),
    NOW()
FROM orders b, orders s
WHERE b.product = 'iPhone 15 Pro Max' AND b.order_type = 'buy'
  AND s.product = 'iPhone 15 Pro Max' AND s.order_type = 'sell'
LIMIT 1;

-- IN_PROGRESS deal (MacBook) - AI is negotiating
INSERT INTO detected_deals (buy_order_id, sell_order_id, product, region, buy_price, sell_price, margin, status, buyer_chat_id, buyer_sender_id, ai_insight, created_at, updated_at)
SELECT
    b.id as buy_order_id,
    s.id as sell_order_id,
    'MacBook Pro M3',
    'СПб',
    180000.00,
    200000.00,
    20000.00,
    'in_progress',
    -1001234567890,
    1173103063,
    'AI начал переговоры. Продавец ответил положительно.',
    NOW(),
    NOW()
FROM orders b, orders s
WHERE b.product = 'MacBook Pro M3' AND b.order_type = 'buy'
  AND s.product = 'MacBook Pro M3' AND s.order_type = 'sell'
LIMIT 1;

-- WARM deal (PS5) - Ready for manager
INSERT INTO detected_deals (buy_order_id, sell_order_id, product, region, buy_price, sell_price, margin, status, buyer_chat_id, buyer_sender_id, ai_insight, manager_id, assigned_at, created_at, updated_at)
SELECT
    b.id as buy_order_id,
    s.id as sell_order_id,
    'PlayStation 5',
    'Казань',
    45000.00,
    55000.00,
    10000.00,
    'warm',
    -1001234567890,
    1173103063,
    'Продавец заинтересован, готов к сделке. Рекомендую связаться.',
    u.id,
    NOW(),
    NOW(),
    NOW()
FROM orders b, orders s, users u
WHERE b.product = 'PlayStation 5' AND b.order_type = 'buy'
  AND s.product = 'PlayStation 5' AND s.order_type = 'sell'
  AND u.username = 'test_manager'
LIMIT 1;

-- 5. Create negotiations with messages

-- Negotiation for IN_PROGRESS deal (MacBook)
INSERT INTO negotiations (deal_id, seller_chat_id, seller_sender_id, stage, created_at, updated_at)
SELECT
    d.id,
    -1001234567890,
    1173103063,
    'price_discussion',
    NOW(),
    NOW()
FROM detected_deals d
WHERE d.product = 'MacBook Pro M3'
LIMIT 1;

-- Messages for MacBook negotiation
INSERT INTO negotiation_messages (negotiation_id, role, content, created_at)
SELECT n.id, 'ai', 'Здравствуйте! Заинтересовал ваш MacBook Pro M3. Актуально?', NOW() - INTERVAL '10 minutes'
FROM negotiations n
JOIN detected_deals d ON n.deal_id = d.id
WHERE d.product = 'MacBook Pro M3';

INSERT INTO negotiation_messages (negotiation_id, role, content, created_at)
SELECT n.id, 'seller', 'Да, актуально! В наличии, идеальное состояние.', NOW() - INTERVAL '8 minutes'
FROM negotiations n
JOIN detected_deals d ON n.deal_id = d.id
WHERE d.product = 'MacBook Pro M3';

INSERT INTO negotiation_messages (negotiation_id, role, content, created_at)
SELECT n.id, 'ai', 'Отлично! По цене возможен торг? Готов забрать сегодня.', NOW() - INTERVAL '5 minutes'
FROM negotiations n
JOIN detected_deals d ON n.deal_id = d.id
WHERE d.product = 'MacBook Pro M3';

-- Negotiation for WARM deal (PS5)
INSERT INTO negotiations (deal_id, seller_chat_id, seller_sender_id, stage, created_at, updated_at)
SELECT
    d.id,
    -1001234567890,
    1173103063,
    'warm',
    NOW(),
    NOW()
FROM detected_deals d
WHERE d.product = 'PlayStation 5'
LIMIT 1;

-- Messages for PS5 negotiation
INSERT INTO negotiation_messages (negotiation_id, role, content, created_at)
SELECT n.id, 'ai', 'Здравствуйте! Заинтересовала ваша PlayStation 5. Актуально?', NOW() - INTERVAL '30 minutes'
FROM negotiations n
JOIN detected_deals d ON n.deal_id = d.id
WHERE d.product = 'PlayStation 5';

INSERT INTO negotiation_messages (negotiation_id, role, content, created_at)
SELECT n.id, 'seller', 'Да! С играми отдаю, полный комплект.', NOW() - INTERVAL '25 minutes'
FROM negotiations n
JOIN detected_deals d ON n.deal_id = d.id
WHERE d.product = 'PlayStation 5';

INSERT INTO negotiation_messages (negotiation_id, role, content, created_at)
SELECT n.id, 'ai', 'Какие игры в комплекте? По цене торг возможен?', NOW() - INTERVAL '20 minutes'
FROM negotiations n
JOIN detected_deals d ON n.deal_id = d.id
WHERE d.product = 'PlayStation 5';

INSERT INTO negotiation_messages (negotiation_id, role, content, created_at)
SELECT n.id, 'seller', 'FIFA 24, Spider-Man 2, God of War. При быстрой сделке скину 3000р.', NOW() - INTERVAL '15 minutes'
FROM negotiations n
JOIN detected_deals d ON n.deal_id = d.id
WHERE d.product = 'PlayStation 5';

INSERT INTO negotiation_messages (negotiation_id, role, content, created_at)
SELECT n.id, 'ai', 'Отлично, готов встретиться! Где удобно?', NOW() - INTERVAL '10 minutes'
FROM negotiations n
JOIN detected_deals d ON n.deal_id = d.id
WHERE d.product = 'PlayStation 5';

-- =============================================
-- VERIFICATION QUERIES
-- =============================================

-- Check what was created
SELECT 'Users' as entity, COUNT(*) as count FROM users
UNION ALL
SELECT 'Orders', COUNT(*) FROM orders
UNION ALL
SELECT 'Deals', COUNT(*) FROM detected_deals
UNION ALL
SELECT 'Negotiations', COUNT(*) FROM negotiations
UNION ALL
SELECT 'Messages', COUNT(*) FROM negotiation_messages;

-- Show deals with status
SELECT id, product, status, margin, ai_insight
FROM detected_deals
ORDER BY id;
