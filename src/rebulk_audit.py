import sqlite3
import time
from src.core.creator import CreatorTracker
from src.utils.db import get_connection

def bulk_audit():
    conn = get_connection()
    cursor = conn.cursor()
    
    # Fetch all tokens that currently have neutral reputation
    cursor.execute("SELECT ca, creator_wallet FROM token_history WHERE reputation = 'neutral'")
    tokens = cursor.fetchall()
    
    tracker = CreatorTracker(db_conn=conn)
    print(f"🔄 Starting Bulk Audit for {len(tokens)} tokens...")
    
    for ca, wallet in tokens:
        if not wallet: continue
        print(f"  🔍 Auditing {ca[:8]} (Creator: {wallet[:8]})")
        try:
            audit_data = tracker.audit_creator_wallet(wallet)
            reputation = audit_data["reputation"]
            success = audit_data["success_tokens"]
            total = audit_data["total_tokens"]
            
            # Update token_history with the new reputation
            cursor.execute("""
                UPDATE token_history 
                SET reputation = ?, creator_success_count = ?, creator_total_tokens = ?
                WHERE ca = ?
            """, (reputation, success, total, ca))
            conn.commit()
            print(f"    ✅ Result: {reputation} ({success}/{total})")
            
            # Slow down to respect Solscan/Helius rate limits
            time.sleep(2)
        except Exception as e:
            print(f"    ❌ Error auditing {ca}: {e}")
    
    conn.close()
    print("✨ Bulk Audit Complete.")

if __name__ == "__main__":
    bulk_audit()
