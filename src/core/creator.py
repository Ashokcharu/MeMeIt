from src.utils.solscan import SolscanClient
from src.utils.db import get_connection
import logging

class CreatorTracker:
    def __init__(self, db_conn=None):
        self.conn = db_conn or get_connection()
        self.solscan = SolscanClient()

    def audit_creator_wallet(self, wallet_address):
        """
        Deep audit of creator wallet history using Solscan.
        Identifies past tokens and calculates peak performance.
        """
        if not wallet_address: 
            return {
                "reputation": "neutral",
                "total_tokens": 0,
                "success_tokens": 0
            }
        
        # Check if we already have a recent audit
        cursor = self.conn.cursor()
        cursor.execute("SELECT reputation, last_audit_at FROM verified_creators WHERE wallet_address=?", (wallet_address,))
        row = cursor.fetchone()
        
        # Cache audits for 24 hours
        import time
        now = int(time.time())
        if row and (now - row[1] < 86400):
            # Fetch counts from database to reconstruct full object
            cursor.execute("SELECT total_tokens, success_tokens FROM verified_creators WHERE wallet_address=?", (wallet_address,))
            counts = cursor.fetchone()
            return {
                "reputation": row[0],
                "total_tokens": counts[0] if counts else 0,
                "success_tokens": counts[1] if counts else 0
            }

        logging.info(f"🔍 Starting Deep Audit for Creator Wallet: {wallet_address}")
        mints = self.solscan.get_creator_mints(wallet_address)
        
        total_tokens = len(mints)
        success_tokens = 0
        is_scammer = False

        for mint in mints:
            ca = mint.get("address")
            if not ca: continue
            
            meta = self.solscan.get_token_market_data(ca)
            if not meta: continue
            
            # Simplified "Starting MC" vs "Peak MC" calculation
            # In a real scenario, we'd query price history. 
            # Here we use the token's current/peak data from Solscan if available.
            peak_mc = float(meta.get("marketCap", 0) or 0)
            # Fetch from historical_mints if we already tracked it
            cursor.execute("SELECT peak_mc, starting_mc FROM historical_mints WHERE mint=?", (ca,))
            h_row = cursor.fetchone()
            
            if h_row:
                h_peak = h_row[0]
                h_start = h_row[1]
                if h_start > 0 and (h_peak / h_start >= 10.0):
                    success_tokens += 1
            elif peak_mc > 500000: # Threshold for "Success" if no history
                success_tokens += 1
            
            # Save to historical logs for future fast lookups
            cursor.execute("""
                INSERT OR IGNORE INTO historical_mints (mint, creator_address, peak_mc, starting_mc)
                VALUES (?, ?, ?, ?)
            """, (ca, wallet_address, peak_mc, meta.get("initialMarketCap") or meta.get("marketCap") or 0))

        reputation = "neutral"
        if success_tokens >= 1:
            reputation = "trusted"
        elif total_tokens >= 3 and success_tokens == 0:
            reputation = "scammer"

        # Update or Insert reputation
        cursor.execute("""
            INSERT INTO verified_creators (wallet_address, reputation, total_tokens, success_tokens, last_audit_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(wallet_address) DO UPDATE SET
                reputation=excluded.reputation,
                total_tokens=excluded.total_tokens,
                success_tokens=excluded.success_tokens,
                last_audit_at=excluded.last_audit_at
        """, (wallet_address, reputation, total_tokens, success_tokens, now))
        
        self.conn.commit()
        return {
            "reputation": reputation,
            "total_tokens": total_tokens,
            "success_tokens": success_tokens
        }

    def get_display_reputation(self, reputation):
        if reputation == "trusted":
            return "TRUSTED DEV ✅"
        elif reputation == "scammer":
            return "SCAMMER 🚨"
        return "Data Pending (Scraper Sync)"
