from src.config import DB_PATH
from src.utils.db import get_connection

def init_db():
    conn = get_connection()
    cursor = conn.cursor()
    
    # Verified creators table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS verified_creators (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            handle TEXT UNIQUE,
            wallet_address TEXT,
            trust_score REAL DEFAULT 50.0,
            tags TEXT,
            last_updated DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Token history table — full schema including all scoring columns
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS token_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ca TEXT UNIQUE,
            name TEXT,
            symbol TEXT,
            creator_wallet TEXT,
            initial_liquidity REAL,
            mc REAL,
            holders_count INTEGER,
            top_10_holding REAL,
            liquidity_locked BOOLEAN,
            is_scam BOOLEAN DEFAULT FALSE,
            final_score REAL,
            report_path TEXT,
            dex_x_link TEXT,
            dex_tg_link TEXT,
            is_trending BOOLEAN DEFAULT FALSE,
            is_rugged BOOLEAN DEFAULT FALSE,
            last_updated_at REAL,
            liquidity REAL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            pair_created_at REAL,
            score_breakdown TEXT,
            social_risk TEXT DEFAULT "Low Risk",
            growth_ratio REAL DEFAULT 0.0,
            is_zombie BOOLEAN DEFAULT FALSE,
            twitter_followers INTEGER DEFAULT 0,
            twitter_verified BOOLEAN DEFAULT FALSE,
            twitter_symbols TEXT,
            twitter_status TEXT,
            is_trusted_creator BOOLEAN DEFAULT FALSE
        )
    ''')

    # Safe migration: add any missing columns to existing databases without crashing.
    # SQLite does not support IF NOT EXISTS for columns, so we use try/except.
    _migration_columns = [
        ("pair_created_at",    "REAL"),
        ("score_breakdown",    "TEXT"),
        ("social_risk",        "TEXT DEFAULT 'Low Risk'"),
        ("growth_ratio",       "REAL DEFAULT 0.0"),
        ("is_zombie",          "BOOLEAN DEFAULT FALSE"),
        ("twitter_followers",  "INTEGER DEFAULT 0"),
        ("twitter_verified",   "BOOLEAN DEFAULT FALSE"),
        ("twitter_symbols",    "TEXT"),
        ("twitter_status",     "TEXT"),
        ("is_trusted_creator", "BOOLEAN DEFAULT FALSE"),
        ("liquidity",          "REAL"),
        ("telegram_submission_time", "REAL"),
        ("current_category",    "TEXT DEFAULT 'analyzing'"),
        ("initial_gem_mc",      "REAL"),
        ("highest_mc_ever",     "REAL"),
        ("mc_growth_1h",        "REAL DEFAULT 0.0"),
        ("mc_growth_2h",        "REAL DEFAULT 0.0"),
        ("holder_growth_1h",    "REAL DEFAULT 0.0"),
        ("is_steady_grower",    "BOOLEAN DEFAULT FALSE"),
        ("initial_mc",          "REAL"),
        ("is_safe",             "BOOLEAN DEFAULT FALSE"),
        ("last_security_audit_at", "INTEGER DEFAULT 0"),
        ("graduation_mc",       "REAL"),
        ("highest_mc_post_grad", "REAL"),
        ("locked_notified",     "BOOLEAN DEFAULT FALSE"),
        ("trending_alerted",    "BOOLEAN DEFAULT FALSE"),
    ]
    for col_name, col_def in _migration_columns:
        try:
            cursor.execute(f"ALTER TABLE token_history ADD COLUMN {col_name} {col_def}")
        except Exception:
            pass  # Column already exists — safe to ignore

    # Add reputation caching to token_history
    try:
        cursor.execute("ALTER TABLE token_history ADD COLUMN reputation TEXT DEFAULT 'neutral'")
        cursor.execute("ALTER TABLE token_history ADD COLUMN creator_success_count INTEGER DEFAULT 0")
        cursor.execute("ALTER TABLE token_history ADD COLUMN creator_total_tokens INTEGER DEFAULT 0")
        cursor.execute("ALTER TABLE token_history ADD COLUMN is_followed_by_user BOOLEAN DEFAULT 0")
    except:
        pass # Columns already exist

    # Ensure user_follows table exists
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS user_follows (
            followed_handle TEXT PRIMARY KEY,
            followed_id TEXT,
            last_synced_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    conn.commit()
    
    # User following table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS user_following (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            handle TEXT UNIQUE,
            synced_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # Monitoring tasks table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS monitoring_tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ca TEXT UNIQUE,
            status TEXT DEFAULT 'active',
            interval_mins INTEGER DEFAULT 2,
            started_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # Time-series metrics table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS time_series_metrics (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ca TEXT,
            metric_type TEXT, -- 'market_cap', 'holders_count', 'liquidity'
            value REAL,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Historical Mints table - tracks every token ever discovered from a creator
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS historical_mints (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            creator_wallet TEXT,
            mint TEXT UNIQUE,
            symbol TEXT,
            starting_mc REAL,
            peak_mc REAL,
            peak_x REAL,
            is_scam BOOLEAN DEFAULT FALSE,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # Safe migration for creators table
    _creator_migrations = [
        ("total_tokens", "INTEGER DEFAULT 0"),
        ("success_tokens", "INTEGER DEFAULT 0"), # Count of 10x+ tokens
        ("reputation", "TEXT DEFAULT 'neutral'"), # 'trusted', 'scammer', 'neutral'
        ("last_audit_at", "INTEGER DEFAULT 0")
    ]
    for col_name, col_def in _creator_migrations:
        try:
            cursor.execute(f"ALTER TABLE verified_creators ADD COLUMN {col_name} {col_def}")
        except Exception:
            pass

    # Critical Performance Indexes
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_ts_metrics_ca_type ON time_series_metrics(ca, metric_type, timestamp DESC)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_token_history_ca ON token_history(ca)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_monitoring_tasks_ca ON monitoring_tasks(ca)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_historical_mints_wallet ON historical_mints(creator_wallet)')
    
    conn.commit()
    conn.close()

if __name__ == "__main__":
    init_db()
    print(f"Database initialized at {DB_PATH}")
