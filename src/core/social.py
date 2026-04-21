import random
import time
import requests
import logging
from src.config import X_SCRAPE_JITTER_RANGE, X_USER_AGENT
from src.utils.db import get_connection

class SocialAnalyzer:
    def __init__(self):
        self.session = requests.Session()
        self.jitter = X_SCRAPE_JITTER_RANGE
        self.headers = {
            "User-Agent": X_USER_AGENT,
            "Accept": "application/json",
        }

    def sync_user_following(self, user_handle):
        """
        Slowly syncs the list of accounts a user follows on X.
        Mimics human behavior with random delays.
        """
        logging.info(f"🕶️ Starting Stealth Sync for X Following List: @{user_handle}")
        # Note: In a real production environment, this would require a session cookie 
        # or a browser-based scraper to get private follow data. 
        # Here we provide the architectural hook for it.
        
        # Simulating a safe, slow fetch
        mock_follows = ["OceanToStars", "aeyakovenko", "Solana", "phantom"] 
        
        conn = get_connection()
        cursor = conn.cursor()
        
        for handle in mock_follows:
            # Human-like jitter between "requests"
            delay = random.uniform(*self.jitter)
            logging.debug(f"X Stealth: Waiting {delay:.2f}s before next sync...")
            # time.sleep(delay) # Uncomment in production
            
            cursor.execute("""
                INSERT INTO user_following (handle, synced_at)
                VALUES (?, CURRENT_TIMESTAMP)
                ON CONFLICT(handle) DO UPDATE SET synced_at=excluded.synced_at
            """, (handle,))
        
        conn.commit()
        conn.close()
        logging.info("✅ Stealth Sync Complete.")

    def analyze_handle(self, handle):
        """
        Verifies if an X handle is part of the Trusted Network.
        """
        if not handle:
            return {"trusted_network": False, "followers": 0, "verified": False}
        
        # Clean handle
        clean_handle = handle.split('/')[-1].replace('@', '').strip()
        
        conn = get_connection()
        cursor = conn.cursor()
        
        # Check user following list
        cursor.execute("SELECT 1 FROM user_following WHERE handle = ?", (clean_handle,))
        is_followed = cursor.fetchone() is not None
        
        # Check verified creators
        cursor.execute("SELECT reputation FROM verified_creators WHERE handle = ?", (clean_handle,))
        row = cursor.fetchone()
        is_verified = row is not None
        reputation = row[0] if row else "neutral"

        conn.close()

        return {
            "handle": clean_handle,
            "is_followed": is_followed,
            "is_verified": is_verified,
            "reputation": reputation,
            "trusted_network": is_followed or (reputation == "trusted")
        }

    def get_x_account_metadata(self, handle):
        """
        Placeholder metadata retrieval (mimics a human-paced scrape).
        """
        if not handle: return {"followers": 0, "is_verified": False}
        
        # Simulate delay
        # time.sleep(random.uniform(2, 5))
        
        return {
            "followers": random.randint(500, 50000),
            "is_verified": random.choice([True, False]),
            "account_age_days": random.randint(30, 1000)
        }
