import time
import requests
import threading
import sys

def process_mint_thread(token_mint):
    from src.graduation_ai import process_graduation
    process_graduation(token_mint, "", "api_scraper")

def scrape_fomo_dexscreener():
    print("📡 Initializing Deep FOMO API Scraper (DexScreener Indexing)...", flush=True)
    
    seen_mints = set()
    
    while True:
        try:
            # Poll the globally synced "Latest Tokens" indexing array
            resp = requests.get("https://api.dexscreener.com/token-profiles/latest/v1", timeout=10)
            if resp.status_code == 200:
                profiles = resp.json()
                
                new_count = 0
                for p in profiles:
                    if p.get("chainId") == "solana":
                        token_mint = p.get("tokenAddress")
                        if token_mint and token_mint not in seen_mints:
                            seen_mints.add(token_mint)
                            new_count += 1
                            # Instantly pass cleanly indexed CAs directly to the FOMO Filter AI
                            threading.Thread(target=process_mint_thread, args=(token_mint,)).start()
                
                print(f"[{time.strftime('%H:%M:%S')}] 🎓 Extraction Sweep: Fetched {len(profiles)} global profiles, {new_count} new Solana mints piped to Graduation Filters.", flush=True)
                
                # Keep memory tight
                if len(seen_mints) > 10000:
                    seen_mints.clear()
                    
        except Exception as e:
            print(f"Scraper Disconnected: {e}", flush=True)
            
        time.sleep(45) # Hyper-safe 45s polling interval avoids any IP bans while mirroring exact FOMO speeds

if __name__ == "__main__":
    scrape_fomo_dexscreener()
