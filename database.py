import asyncpg
import os
from datetime import datetime, timedelta

DATABASE_URL = os.getenv("DATABASE_URL")

class Database:
    def __init__(self):
        self.pool = None

    async def connect(self):
        if not DATABASE_URL:
            raise ValueError("DATABASE_URL not set!")
        self.pool = await asyncpg.create_pool(DATABASE_URL, min_size=2, max_size=20)

    async def close(self):
        if self.pool: 
            await self.pool.close()

    async def execute(self, query: str, *args):
        async with self.pool.acquire() as conn:
            return await conn.execute(query, *args)

    async def fetch(self, query: str, *args):
        async with self.pool.acquire() as conn:
            return await conn.fetch(query, *args)

    async def fetchrow(self, query: str, *args):
        async with self.pool.acquire() as conn:
            return await conn.fetchrow(query, *args)

    async def fetchval(self, query: str, *args):
        async with self.pool.acquire() as conn:
            return await conn.fetchval(query, *args)

db = Database()

# ========================= TABLE SETUP =========================
async def create_tables():
    # Users table
    await db.execute("""
    CREATE TABLE IF NOT EXISTS users (
        user_id BIGINT PRIMARY KEY,
        plan TEXT DEFAULT 'free',
        premium_days INT DEFAULT 0,
        expiry TIMESTAMP,
        is_banned BOOLEAN DEFAULT FALSE,
        banned_at TIMESTAMP,
        banned_by BIGINT
    );
    """)
    await db.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS plan TEXT DEFAULT 'free';")
    await db.execute("UPDATE users SET plan = 'free' WHERE plan IS NULL;")

    # Proxies table
    await db.execute("""
    CREATE TABLE IF NOT EXISTS proxies (
        id SERIAL PRIMARY KEY,
        user_id BIGINT NOT NULL,
        ip TEXT NOT NULL,
        port TEXT NOT NULL,
        username TEXT,
        password TEXT,
        proxy_url TEXT NOT NULL,
        proxy_type TEXT DEFAULT 'http'
    );
    """)

    # Sites table
    await db.execute("""
    CREATE TABLE IF NOT EXISTS sites (
        id SERIAL PRIMARY KEY,
        user_id BIGINT NOT NULL,
        site TEXT NOT NULL,
        UNIQUE(user_id, site)
    );
    """)

    # Keys table with plan_type support
    await db.execute("""
    CREATE TABLE IF NOT EXISTS keys (
        key TEXT PRIMARY KEY,
        days INT NOT NULL,
        plan_type TEXT DEFAULT 'pro',
        created_at TIMESTAMP DEFAULT NOW(),
        used BOOLEAN DEFAULT FALSE,
        used_by BIGINT,
        used_at TIMESTAMP
    );
    """)
    
    # Add missing columns for existing databases
    await db.execute("ALTER TABLE keys ADD COLUMN IF NOT EXISTS plan_type TEXT DEFAULT 'pro'")
    await db.execute("ALTER TABLE keys ADD COLUMN IF NOT EXISTS used_by BIGINT")
    await db.execute("ALTER TABLE keys ADD COLUMN IF NOT EXISTS used_at TIMESTAMP")
    
    # Update existing keys to have default plan_type
    await db.execute("UPDATE keys SET plan_type = 'pro' WHERE plan_type IS NULL")

    # Approved cards table
    await db.execute("""
    CREATE TABLE IF NOT EXISTS approved_cards (
        id SERIAL PRIMARY KEY,
        card TEXT NOT NULL,
        status TEXT NOT NULL,
        response TEXT,
        gateway TEXT,
        price TEXT,
        created_at TIMESTAMP DEFAULT NOW()
    );
    """)

# ========================= PLAN & USER =========================
async def ensure_user(user_id: int):
    await db.execute("""
        INSERT INTO users (user_id, plan) VALUES ($1, 'free') 
        ON CONFLICT (user_id) DO NOTHING
    """, user_id)

async def get_user_plan(user_id: int) -> str:
    row = await db.fetchrow("SELECT plan FROM users WHERE user_id = $1", user_id)
    return row['plan'] if row else 'free'

async def set_user_plan(user_id: int, new_plan: str, days: int = 0):
    await ensure_user(user_id)
    expiry = datetime.utcnow() + timedelta(days=days) if days > 0 else None
    await db.execute("""
        UPDATE users SET plan = $2, expiry = $3, premium_days = $4 WHERE user_id = $1
    """, user_id, new_plan.lower(), expiry, days)

async def is_premium_user(user_id: int) -> bool:
    row = await db.fetchrow("SELECT plan, expiry FROM users WHERE user_id = $1", user_id)
    if not row or row['plan'] == 'free': 
        return False
    if row.get('expiry') and row['expiry'] < datetime.utcnow():
        await set_user_plan(user_id, 'free')
        return False
    return True

async def is_banned_user(user_id: int) -> bool:
    row = await db.fetchrow("SELECT is_banned FROM users WHERE user_id = $1", user_id)
    return row and row['is_banned']

async def ban_user(user_id: int, banned_by: int):
    await ensure_user(user_id)
    await db.execute("""
        UPDATE users SET is_banned = TRUE, banned_at = $2, banned_by = $3 
        WHERE user_id = $1
    """, user_id, datetime.utcnow(), banned_by)

async def unban_user(user_id: int) -> bool:
    result = await db.execute("""
        UPDATE users SET is_banned = FALSE, banned_at = NULL, banned_by = NULL 
        WHERE user_id = $1 AND is_banned = TRUE
    """, user_id)
    return result != "UPDATE 0"

async def remove_premium(user_id: int) -> bool:
    """Remove premium access from user"""
    result = await db.execute("""
        UPDATE users SET plan = 'free', expiry = NULL, premium_days = 0 
        WHERE user_id = $1 AND plan != 'free'
    """, user_id)
    return result != "UPDATE 0"

# ========================= KEY SYSTEM =========================
async def create_key(key: str, days: int, plan_type: str = 'pro'):
    """Create a new key with plan type (free/pro/toji)"""
    await db.execute("""
        INSERT INTO keys (key, days, plan_type, created_at) 
        VALUES ($1, $2, $3, $4)
        ON CONFLICT (key) DO NOTHING
    """, key, days, plan_type, datetime.utcnow())

async def get_key_data(key: str):
    """Get key data including plan_type"""
    return await db.fetchrow("SELECT * FROM keys WHERE key = $1", key)

async def use_key(user_id: int, key: str):
    """Use a key and activate the corresponding plan for user"""
    row = await db.fetchrow("SELECT * FROM keys WHERE key = $1", key)
    if not row: 
        return False, "Invalid key!"
    if row["used"]: 
        return False, "This key has already been used!"
    
    # Get plan_type and days from key
    plan_type = row.get("plan_type", "pro")  # Default to 'pro' for old keys
    days = row["days"]
    
    # Mark key as used
    await db.execute("""
        UPDATE keys SET used = TRUE, used_by = $1, used_at = $2 WHERE key = $3
    """, user_id, datetime.utcnow(), key)
    
    # Set user plan with the plan_type from key
    await set_user_plan(user_id, plan_type, days)
    return True, days

async def get_all_keys():
    """Get all keys with plan_type information"""
    return await db.fetch("SELECT * FROM keys ORDER BY created_at DESC")

async def delete_key(key: str) -> bool:
    """Delete a key from database"""
    result = await db.execute("DELETE FROM keys WHERE key = $1", key)
    return result != "DELETE 0"

async def get_keys_by_plan(plan_type: str):
    """Get all keys for a specific plan type"""
    return await db.fetch(
        "SELECT * FROM keys WHERE plan_type = $1 ORDER BY created_at DESC", 
        plan_type
    )

async def get_unused_keys_count():
    """Get count of unused keys"""
    return await db.fetchval("SELECT COUNT(*) FROM keys WHERE used = FALSE") or 0

async def get_used_keys_count():
    """Get count of used keys"""
    return await db.fetchval("SELECT COUNT(*) FROM keys WHERE used = TRUE") or 0

async def get_keys_stats():
    """Get key statistics"""
    total = await db.fetchval("SELECT COUNT(*) FROM keys") or 0
    used = await get_used_keys_count()
    unused = await get_unused_keys_count()
    
    pro_keys = await db.fetchval("SELECT COUNT(*) FROM keys WHERE plan_type = 'pro' AND used = FALSE") or 0
    toji_keys = await db.fetchval("SELECT COUNT(*) FROM keys WHERE plan_type = 'toji' AND used = FALSE") or 0
    free_keys = await db.fetchval("SELECT COUNT(*) FROM keys WHERE plan_type = 'free' AND used = FALSE") or 0
    
    return {
        'total': total,
        'used': used,
        'unused': unused,
        'pro_available': pro_keys,
        'toji_available': toji_keys,
        'free_available': free_keys
    }

# ========================= PROXY SYSTEM =========================
async def add_proxy_db(user_id: int, proxy_data: dict):
    await db.execute("""
        INSERT INTO proxies (user_id, ip, port, username, password, proxy_url, proxy_type)
        VALUES ($1, $2, $3, $4, $5, $6, $7)
    """, user_id, proxy_data['ip'], proxy_data['port'],
        proxy_data.get('username'), proxy_data.get('password'),
        proxy_data['proxy_url'], proxy_data.get('type', 'http'))

async def get_all_user_proxies(user_id: int):
    rows = await db.fetch("SELECT * FROM proxies WHERE user_id = $1 ORDER BY id", user_id)
    return [dict(r) for r in rows]

async def get_proxy_count(user_id: int):
    return await db.fetchval("SELECT COUNT(*) FROM proxies WHERE user_id = $1", user_id) or 0

async def get_random_proxy(user_id: int):
    row = await db.fetchrow("SELECT * FROM proxies WHERE user_id = $1 ORDER BY RANDOM() LIMIT 1", user_id)
    return dict(row) if row else None

async def remove_proxy_by_index(user_id: int, index: int):
    rows = await db.fetch("SELECT id, ip, port FROM proxies WHERE user_id = $1 ORDER BY id", user_id)
    if index < 0 or index >= len(rows): 
        return None
    row = rows[index]
    await db.execute("DELETE FROM proxies WHERE id = $1", row['id'])
    return dict(row)

async def remove_proxy_by_url(user_id: int, proxy_url: str):
    await db.execute("DELETE FROM proxies WHERE user_id = $1 AND proxy_url = $2", user_id, proxy_url)

async def clear_all_proxies(user_id: int):
    count = await get_proxy_count(user_id)
    await db.execute("DELETE FROM proxies WHERE user_id = $1", user_id)
    return count

# ========================= SITE SYSTEM =========================
async def add_site_db(user_id: int, site: str) -> bool:
    try:
        await db.execute("INSERT INTO sites (user_id, site) VALUES ($1, $2)", user_id, site)
        return True
    except:
        return False

async def get_user_sites(user_id: int):
    rows = await db.fetch("SELECT site FROM sites WHERE user_id = $1 ORDER BY id", user_id)
    return [r["site"] for r in rows]

async def remove_site_db(user_id: int, site: str) -> bool:
    result = await db.execute("DELETE FROM sites WHERE user_id = $1 AND site = $2", user_id, site)
    return result != "DELETE 0"

async def clear_user_sites(user_id: int):
    await db.execute("DELETE FROM sites WHERE user_id = $1", user_id)

async def set_user_sites(user_id: int, sites: list):
    await clear_user_sites(user_id)
    for site in sites:
        await add_site_db(user_id, site)

# ========================= CARDS & STATS =========================
async def save_card_to_db(card: str, status: str, response: str, gateway: str, price: str):
    await db.execute("""
        INSERT INTO approved_cards (card, status, response, gateway, price, created_at)
        VALUES ($1, $2, $3, $4, $5, $6)
    """, card, status, response or '', gateway or '', price or '', datetime.utcnow())

async def get_total_cards_count():
    return await db.fetchval("SELECT COUNT(*) FROM approved_cards") or 0

async def get_charged_count():
    return await db.fetchval("SELECT COUNT(*) FROM approved_cards WHERE status = 'CHARGED'") or 0

async def get_approved_count():
    return await db.fetchval("SELECT COUNT(*) FROM approved_cards WHERE status = 'APPROVED'") or 0

async def get_total_users():
    return await db.fetchval("SELECT COUNT(*) FROM users") or 0

async def get_premium_count():
    return await db.fetchval("SELECT COUNT(*) FROM users WHERE plan != 'free'") or 0

async def get_total_sites_count():
    return await db.fetchval("SELECT COUNT(*) FROM sites") or 0

async def get_users_with_sites():
    return await db.fetchval("SELECT COUNT(DISTINCT user_id) FROM sites") or 0

async def get_all_premium_users():
    rows = await db.fetch(
        "SELECT user_id, plan, premium_days, expiry FROM users WHERE plan != 'free' ORDER BY user_id"
    )
    return [dict(r) for r in rows]

async def get_sites_per_user():
    return await db.fetch("SELECT user_id, COUNT(*) as cnt FROM sites GROUP BY user_id ORDER BY cnt DESC")

async def get_all_sites_detail():
    return await db.fetch("SELECT user_id, site FROM sites ORDER BY user_id, id")

# ========================= MIGRATION =========================
async def migrate_keys_table():
    """Add new columns to keys table if they don't exist"""
    try:
        # Check if columns exist by trying to select them
        await db.fetchrow("SELECT plan_type, used_by, used_at FROM keys LIMIT 1")
        print("✅ Keys table already has required columns")
    except Exception:
        # Columns don't exist, add them
        print("🔄 Migrating keys table...")
        try:
            await db.execute("ALTER TABLE keys ADD COLUMN IF NOT EXISTS plan_type TEXT DEFAULT 'pro'")
            await db.execute("ALTER TABLE keys ADD COLUMN IF NOT EXISTS used_by BIGINT")
            await db.execute("ALTER TABLE keys ADD COLUMN IF NOT EXISTS used_at TIMESTAMP")
            # Update existing keys to have default plan_type
            await db.execute("UPDATE keys SET plan_type = 'pro' WHERE plan_type IS NULL")
            print("✅ Keys table migration completed")
        except Exception as e:
            print(f"⚠️ Migration error: {e}")

# ========================= INIT =========================
async def init_db():
    await db.connect()
    await create_tables()
    await migrate_keys_table()
    print("✅ Database ready with Free / Pro / Toji plan system!")
