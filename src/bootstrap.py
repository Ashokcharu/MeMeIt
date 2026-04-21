import os, sys
# Add project root to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.workers import monitor_on_chain, monitor_social
from src.utils.db import get_connection

def bootstrap_monitoring():
    """
    Enqueues monitoring tasks for every active token in the database.
    This ensures that when the app restarts, monitoring resumes automatically.
    """
    print("🚀 MeMeIt Bootstrap: Resuming monitoring for all active tokens...")
    try:
        conn = get_connection()
        cursor = conn.cursor()
        # Find all tokens that are not rugged
        cursor.execute("""
            SELECT ca, dex_x_link, is_scam, is_rugged 
            FROM token_history 
            WHERE is_rugged = 0
            ORDER BY created_at DESC
        """)
        rows = cursor.fetchall()
        conn.close()
        
        print(f"   -> Found {len(rows)} active tokens.")
        for ca, x_link, is_scam, is_rugged in rows:
            print(f"   -> Resuming chain for: {ca}")
            # Enqueue the task
            monitor_on_chain(ca)
            if x_link:
                # monitor_social(ca, x_link) # Optional: don't clog Huey initially
                pass 
                
        print("✅ Bootstrap complete. All tokens enqueued.")
    except Exception as e:
        print(f"❌ Bootstrap failed: {e}")

if __name__ == "__main__":
    bootstrap_monitoring()
