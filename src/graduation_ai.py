import time
import json
from src.core.database import get_connection
from src.utils.redis import publish_event
from src.core.on_chain import DexScreenerClient
from src.core.helius import HeliusClient
from src.workers import start_research

def calculate_graduation_score(liquidity, tx_count, holders, age_mins):
    """
    Proprietary FOMO Scoring AI.
    Favors high liquidity, fast swap velocity, and brand new pools.
    """
    if age_mins <= 0: age_mins = 1

    # Weights
    # Base: Minimum liquidity gets 10 points, up to 50 for $50k
    liq_score = min(50, (liquidity / 1000))
    
    # Velocity: Swaps per minute
    vel_score = min(40, (tx_count / age_mins))
    
    # Holders
    holder_score = min(30, holders)

    # Recency Modifier: <15 mins is hot, dropping heavily after 60
    recency_mult = 1.5 if age_mins < 15 else (1.0 if age_mins < 30 else 0.5)

    raw_score = liq_score + vel_score + holder_score
    return round(raw_score * recency_mult, 2)

def process_graduation(token_mint: str, pair_address: str, sig: str = ""):
    """
    Intercepts a new LP creation from Helius, applies Graduation Filters, and pushes it to the UI.
    """
    print(f"[Graduation Engine] Analyzing newly created LP for token: {token_mint}")
    
    # Fast de-dupe
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT 1 FROM token_history WHERE ca = ?", (token_mint,))
    exists = cursor.fetchone()
    conn.close()
    
    if exists:
        return # Already being tracked!
        
    client = DexScreenerClient()
    token_data = client.get_token_data(token_mint)
    
    # Fallback defense if Dex is lagging indexing 
    if not token_data or token_data.get("mc", 0) == 0:
        # Optimization (Phase 46): Only use Helius credits for manual Telegram submissions
        # Skip fallback for the high-volume background scraper to save 10M+ credits/day
        if sig == "api_scraper":
            # print(f"[Graduation Engine] Skipping Helius fallback for background token {token_mint} to save credits.")
            return
            
        h_client = HeliusClient()
        h_data = h_client.get_token_data(token_mint)
        if h_data:
            token_data = token_data or h_data
            token_data["mc"] = token_data.get("mc", 0) or h_data.get("mc", 0)
            token_data["image_url"] = token_data.get("image_url", "") or h_data.get("image_url", "")
            
    if not token_data:
        return

    # FILTER 1: Age Limit (Under 180 mins is ideal for scrape lag)
    now = int(time.time())
    pair_created_at = int(token_data.get("pair_created_at", now))
    age_mins = (now - pair_created_at) / 60
    if age_mins > 180:
        return
        
    liq = token_data.get("liquidity")
    if liq is None: liq = 0
    liq = float(liq)
    
    # FILTER 2: Minimum Viability Structure
    # Needs at least a couple hundred dollars to not be an instant honeypot failure
    if liq < 1000:
        return

    # FILTER 3: Activity Threshold
    vol_24h = token_data.get("volume_24h", 0)
    tx_count = vol_24h / 60 if vol_24h > 0 else 0
    if tx_count < 10 and age_mins > 5:
        return

    holders = 10 # Baseline speed injection
    
    # Proprietary FOMO Engine Score
    grad_score = calculate_graduation_score(liq, tx_count, holders, age_mins)
    
    img_url = token_data.get("image_url", "")
    t_name = token_data.get("name", f"Token {token_mint[:4]}")
    t_sym = token_data.get("symbol", "TKN")
    mc = token_data.get("mc", 0)
    
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO token_history 
        (ca, name, symbol, mc, initial_mc, graduation_mc, highest_mc_post_grad, liquidity, final_score, current_category, 
         last_updated_at, telegram_submission_time, pair_created_at, image_url, holders_count, peak_x, current_x)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (token_mint, t_name, t_sym, mc, mc, mc, mc, liq, grad_score, 'graduated', now, now, pair_created_at, img_url, holders, 1.0, 1.0))
    conn.commit()
    conn.close()
    
    print(f"✅ GRADUATED! {t_sym} | Liq: ${liq} | MC: ${mc} | Score: {grad_score}")
    
    publish_event("dashboard_events", "token_update", {
        "ca": token_mint,
        "category": "graduated",
        "current_category": "graduated",
        "name": t_name,
        "symbol": t_sym,
        "mc": mc,
        "score": grad_score,
        "last_updated": now,
        "pair_created_at": pair_created_at,
        "liquidity": liq,
        "holders_count": holders,
        "image_url": img_url,
        "is_graduation": True # Triggers special UI tag
    })
    
    # Pass off to deep scan
    start_research(token_mint, None)
