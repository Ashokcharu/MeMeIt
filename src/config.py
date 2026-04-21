import os
from dotenv import load_dotenv

load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "8740016500:AAHUhamJEIDyqCb9sFKblsW1RxA5-vLSZU4")
DEXSCREENER_API_URL = "https://api.dexscreener.com/latest/dex/tokens"
GOPLUS_API_URL = "https://api.gopluslabs.io/api/v1/token_security"

HELIUS_API_KEYS_RAW = [
    os.getenv("HELIUS_API_KEY", "57ae767c-01bb-41e3-912c-978b651e06ca"),
    os.getenv("HELIUS_API_KEY_2", "85935c10-e5ff-4547-8cfb-102358046605"),
    os.getenv("HELIUS_API_KEY_3", "ec7c4caa-11f1-4123-8c2c-44ba985407ae"),
    os.getenv("HELIUS_API_KEY_4", "21e73231-d813-4c8e-b7ee-179cb6532ebd"),
    os.getenv("HELIUS_API_KEY_5", "59da2ec0-aca2-429e-878e-03d740133fa3")
]
HELIUS_API_KEYS = [k for k in HELIUS_API_KEYS_RAW if k]

SOLSCAN_API_KEYS = [
    os.getenv("SOLSCAN_API_KEY_1"),
    os.getenv("SOLSCAN_API_KEY_2"),
    os.getenv("SOLSCAN_API_KEY_3")
]
SOLSCAN_API_KEYS = [k for k in SOLSCAN_API_KEYS if k]

# Stealth X Scraping Settings
X_SCRAPE_INTERVAL_SEC = 86400 # 24 hours
X_SCRAPE_JITTER_RANGE = (60, 300) # Random delay between requests to avoid blocks
X_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36"

SPL_TOKEN_PROGRAM_ID = os.getenv("SPL_TOKEN_PROGRAM_ID", "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA")

# Monitoring settings
MONITORING_DURATION_MINS = 30
BUY_PRESSURE_THRESHOLD = 0.20 # 20% spike
SOCIAL_RESCAN_INTERVAL = 10 # 10 minutes

# Database
DB_PATH = os.path.join(os.path.dirname(__file__), "../data/meme_it.db")

# Telegram Authorization
AUTHORIZED_USER_IDS = [6762835190]

# Redis Settings
REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))
REDIS_DB = int(os.getenv("REDIS_DB", 0))
