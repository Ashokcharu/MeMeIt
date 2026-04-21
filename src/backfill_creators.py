import json
import requests
import sqlite3
import time
from src.utils.db import get_connection
from src.config import HELIUS_API_KEY

def backfill():
    conn = get_connection()
    cursor = conn.cursor()
    
    # Get tokens missing creator_wallet
    cursor.execute("SELECT ca FROM token_history WHERE creator_wallet IS NULL OR creator_wallet = '' OR creator_wallet = 'Unknown'")
    tokens = [r[0] for r in cursor.fetchall()]
    
    print(f"🔄 Backfilling Creator Wallets for {len(tokens)} tokens...")
    
    for ca in tokens:
        print(f"  🔍 Finding creator for {ca[:8]}...")
        creator = None
        
        # Try Helius DAS getAsset
        url = f"https://mainnet.helius-rpc.com/?api-key={HELIUS_API_KEY}"
        try:
            resp = requests.post(url, json={
                "jsonrpc": "2.0",
                "id": "my-id",
                "method": "getAsset",
                "params": {"id": ca}
            }, timeout=10)
            if resp.status_code == 200:
                data = resp.json().get("result", {})
                creators = data.get("creators", [])
                if creators:
                    creator = creators[0].get("address")
        except: pass
        
        if creator:
            cursor.execute("UPDATE token_history SET creator_wallet = ? WHERE ca = ?", (creator, ca))
            conn.commit()
            print(f"    ✅ Found: {creator}")
        else:
            print(f"    ⚠️ Not found.")
        
        time.sleep(0.5)

    conn.close()
    print("✨ Backfill Complete.")

if __name__ == "__main__":
    backfill()
