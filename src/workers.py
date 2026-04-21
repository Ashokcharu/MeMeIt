import os, sys, re, json, time
# Add project root to sys.path to resolve 'src' package
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import asyncio
from huey import RedisHuey, crontab
from src.config import DB_PATH, AUTHORIZED_USER_IDS
from src.core.on_chain import OnChainAnalyzer
from src.core.social import SocialAnalyzer
from src.core.scoring import ScoringEngine
from src.utils.db import get_connection
from src.utils.telegram import push_notification, send_token_alert
from src.utils.redis import publish_event, get_redis_connection
import logging
import traceback

# Configure logging: Only warnings and errors (no httpx spam)
logging.basicConfig(level=logging.WARNING, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logging.getLogger('httpx').setLevel(logging.ERROR)
logging.getLogger('httpcore').setLevel(logging.ERROR)
logging.getLogger('huey').setLevel(logging.WARNING)
logger = logging.getLogger('meme_it_worker')

# Phase 85: Multi-Queue Support (Dedicated Intake Worker)
default_huey = RedisHuey('meme_it_tasks', host='localhost', port=6379)
intake_huey = RedisHuey('intake_tasks', host='localhost', port=6379)

# Legacy alias for backward compatibility with other scripts
huey = default_huey

@huey.periodic_task(crontab(minute='0')) # Every hour
def prune_stale_tokens():
    """
    Deletes tokens in 'died', 'scams', or 'scammed' categories older than 48 hours.
    Optimizes database by removing stale history and metrics.
    """
    logger.info("🧹 Starting database pruning...")
    now_ts = int(time.time())
    cutoff_ts = now_ts - (48 * 3600) # 48 hours ago
    
    conn = get_connection()
    cursor = conn.cursor()
    
    # 1. Identify stale tokens
    cursor.execute("""
        SELECT ca FROM token_history 
        WHERE current_category IN ('died', 'scams', 'scammed') 
        AND COALESCE(pair_created_at, telegram_submission_time, last_updated_at) < ?
    """, (cutoff_ts,))
    stale_cas = [row[0] for row in cursor.fetchall()]
    
    if not stale_cas:
        logger.info("✅ No stale tokens found to prune.")
        conn.close()
        return

    # 2. Delete related data
    try:
        # Delete from time_series_metrics
        cursor.executemany("DELETE FROM time_series_metrics WHERE ca = ?", [(ca,) for ca in stale_cas])
        # Delete from monitoring_tasks
        cursor.executemany("DELETE FROM monitoring_tasks WHERE ca = ?", [(ca,) for ca in stale_cas])
        # Delete from token_history
        cursor.executemany("DELETE FROM token_history WHERE ca = ?", [(ca,) for ca in stale_cas])
        
        # 3. Universal Metric Pruning
        # The longest trend analyzer looks back 7 days. Anything older is dead space that bloats the DB.
        cursor.execute("DELETE FROM time_series_metrics WHERE timestamp < datetime('now', '-7 days')")
        
        conn.commit()
        logger.info(f"✅ Pruned {len(stale_cas)} tokens and their related data. Also cleared >7-day metrics.")
    except Exception as e:
        logger.error(f"❌ Error during pruning: {e}")
        conn.rollback()
    finally:
        conn.close()

@huey.periodic_task(crontab(minute='0', hour='0')) # Every day at midnight
def daily_x_sync():
    """
    Daily stealth sync of the user's X following list.
    """
    logger.info("🕶️ Periodic Task: Starting X Stealth Sync...")
    try:
        from src.core.social import SocialAnalyzer
        analyzer = SocialAnalyzer()
        # Using the handle from config or default
        handle = "Im_Ashokcharu" 
        analyzer.sync_user_following(handle)
        logger.info("✅ Daily X Sync Complete.")
    except Exception as e:
        logger.error(f"❌ X Sync Failed: {e}")

# Configuration for Social Enrichment
USER_X_HANDLE = "Im_Ashokcharu"
USER_X_PROFILE = f"https://x.com/{USER_X_HANDLE}"

@intake_huey.task()
def start_research(ca, x_link=None, is_manual=False):
    """
    Background task to run full research and initiate monitoring.
    Emits step-by-step progress events to the dashboard.
    """
    def _progress(step_msg, percent=0):
        print(f"BKG [{ca[:8]}]: {step_msg}")
        publish_event("dashboard_events", "analysis_progress", {
            "ca": ca, "status": step_msg, "percent": percent
        })

    _progress("🔍 Fetching on-chain data...", 10)

    # 1. Fetch on-chain data (FIRST PASS - FAST)
    analyzer = OnChainAnalyzer()
    token_data = analyzer.analyze_token(ca)

    if not token_data:
        _progress("❌ Token not found on DexScreener", 100)
        return

    name = token_data.get('name') or f"Token {ca[:6]}"
    symbol = token_data.get('symbol') or f"TKN-{ca[:4]}"
    mc = token_data.get('mc', 0)
    pair_created_at = token_data.get("pair_created_at")
    
    # IMMEDIATE UPDATE TO DB so dashboard shows REAL basics ASAP
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE token_history SET name=?, symbol=?, mc=?, pair_created_at=?, last_updated_at=?, initial_mc=COALESCE(initial_mc, ?) WHERE ca=?", 
                 (name, symbol, mc, pair_created_at, int(time.time()), mc, ca))
    conn.commit()
    conn.close()
    
    publish_event("dashboard_events", "token_update", {
        "ca": ca, "score": -1, "name": name, "symbol": symbol, "mc": mc, 
        "pair_created_at": pair_created_at, "current_category": "analyzing"
    })

    _progress(f"✅ Found: {name} ({symbol})", 30)

    # ... Deep Research Continues ...
    tg_link = None
    if "links" in token_data:
        if not x_link:
            x_link = token_data["links"].get("twitter")
        tg_link = token_data["links"].get("telegram")

    _progress("🛡️ Running security check...", 50)

    # 2. Security info
    security_info = token_data.get("security", {})
    if security_info.get("is_honeypot"):
        _progress("🚨 HONEYPOT DETECTED!", 70)
    else:
        _progress("✅ Security check passed", 70)

    # 3. Scoring
    _progress("📊 Scoring token...", 80)
    # 2. Social & Creator Audit (Phase 2: Intelligence)
    from src.core.creator import CreatorTracker
    social_analyzer = SocialAnalyzer()
    creator_tracker = CreatorTracker()
    
    # Check X handle against Network
    x_handle = x_link or token_data.get("links", {}).get("twitter")
    network_info = social_analyzer.analyze_handle(x_handle)
    scraper_info = social_analyzer.get_x_account_metadata(x_handle)
    
    # Merge, letting the reliable network checks override raw scraper where they overlap
    social_info = {**scraper_info, **network_info}
    
    # Deep Audit Creator Wallet
    creator_wallet = token_data.get("creator_wallet")
    audit_data = creator_tracker.audit_creator_wallet(creator_wallet)
    
    reputation = audit_data["reputation"]
    success_count = audit_data["success_tokens"]
    total_count = audit_data["total_tokens"]
    is_followed_by_user = social_info.get("trusted_network", False)

    token_data["reputation"] = reputation
    token_data["is_followed_by_user"] = is_followed_by_user
    token_data["twitter_verified"] = social_info.get("is_verified", False)

    # 3. Final Scoring (Phase 96: Rep Integration)
    _progress("📊 Scoring & Risk Check...", 85)
    scoring = ScoringEngine()
    final_score, breakdown, is_zombie = scoring.calculate_score(
        token_data, 
        creator_data={
            "reputation": reputation,
            "is_followed_by_user": is_followed_by_user
        }
    )
    # (Scoring already completed above)

    is_scam = bool(security_info.get("is_honeypot")) or final_score < 30
    social_risk = "High Risk (Bot Detected)" if (social_info.get("followers", 0) < 20) else "Low Risk"

    mc = token_data.get('mc', 0)
    holders = token_data.get('holders', {})
    holders_count = int(holders.get('holders_count', 0) or 0)
    
    # Phase 94: Holder Count Robustness (Avoid showing 0 for active tokens)
    if holders_count <= 0:
        # Check if we have transaction data that implies holders
        # If liquidity is > $1k, there MUST be at least a few holders
        if token_data.get('liquidity', 0) > 1000:
            holders_count = 10 # Baseline estimate for newly active pools
    
    top_10 = holders.get('top_10_percent', 0.0)
    is_pump = ca.lower().endswith('pump')
    liq_locked_state = bool(token_data.get('liquidity_locked', False)) or is_pump
    
    # Determine Category
    current_cat = "analyzing"
    if is_scam:
        current_cat = "scams"
    elif final_score >= 80:
        current_cat = "trending"
    elif final_score >= 50:
        current_cat = "gems"
    else:
        current_cat = "established"
    
    # 5. Performance Tracking: Record Graduation (Moment of Release) MC
    # CRITICAL: We lock the graduation_mc only ONCE when it first hits a terminal category.
    # This prevents calculations from drifting if the token is re-analyzed later.
    initial_gem_mc = None
    if current_cat in ["gems", "established", "legacy", "trending", "hall_of_fame"]:
        initial_gem_mc = mc

    # 5. Save (Update all columns for 2.0 consistency)
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE token_history
        SET name = ?, symbol = ?, final_score = ?, mc = ?, holders_count = ?,
            top_10_holding = ?, liquidity_locked = ?, is_scam = ?, 
            dex_x_link = ?, dex_tg_link = ?, is_trending = ?, 
            is_rugged = ?, social_risk = ?, growth_ratio = ?, 
            score_breakdown = ?, is_zombie = ?,
            twitter_followers = ?, twitter_verified = ?, is_trusted_creator = ?,
            last_updated_at = ?, current_category = ?, pair_created_at = ?,
            initial_gem_mc = COALESCE(initial_gem_mc, ?),
            graduation_mc = COALESCE(graduation_mc, ?),
            highest_mc_ever = MAX(COALESCE(highest_mc_ever, 0), ?),
            reputation = ?,
            creator_success_count = ?,
            creator_total_tokens = ?,
            is_followed_by_user = ?
        WHERE ca = ?
    """, (
        name, symbol, final_score, mc, holders_count, top_10,
        liq_locked_state, 1 if is_scam else 0, x_link, tg_link,
        1 if current_cat == "trending" else 0, 0, social_risk, 0.0,
        json.dumps(breakdown), 1 if is_zombie else 0,
        social_info.get("followers", 0),
        1 if social_info.get("is_verified") else 0,
        1 if reputation == "trusted" else 0,
        int(time.time()), current_cat, token_data.get("pair_created_at"),
        initial_gem_mc, initial_gem_mc, mc,
        reputation, success_count, total_count, 
        1 if is_followed_by_user else 0,
        ca
    ))
    conn.commit()
    conn.close()

    # 5. Final update — moves token out of Analyzing tab into correct category
    category = "💎 Potential Gem" if final_score >= 50 else ("🚨 Scam" if is_scam else "⚠️ Potential Scam")
    _progress(f"✅ Done! Score: {final_score}/100 → {category}", 100)

    publish_event("dashboard_events", "token_update", {
        "ca": ca, "name": name, "symbol": symbol, "score": final_score,
        "mc": mc, "holders_count": holders_count, "current_category": current_cat,
        "initial_gem_mc": initial_gem_mc, "highest_mc_ever": mc,
        "pair_created_at": token_data.get("pair_created_at"),
        "reputation": reputation,
        "is_followed_by_user": is_followed_by_user,
        "is_trusted_creator": (1 if reputation == "trusted" else 0)
    })

    # 6. Notify via Telegram
    if AUTHORIZED_USER_IDS:
        if current_cat == 'trending' and final_score >= 70:
            liq_locked_str = "Yes ✅" if liq_locked_state else "No ❌"
            report = (
                f"🚀 *NEW TRENDING DETECTED*\n"
                f"Token: {name} (`{ca}`)\n"
                f"Score: *{final_score}/100*\n"
                f"--------------------------\n"
                f"🛡️ *Security*: PASS\n"
                f"💧 *Liquidity Lock*: {liq_locked_str}\n"
                f"👥 *Holders*: {holders_count} (Top 10: {top_10:.1f}%)\n"
                f"📱 *Social*: {x_link or 'No X found'}\n"
                f"--------------------------\n"
                f"🌐 [Open Dashboard](http://localhost:5173)"
            )
            try:
                asyncio.run(push_notification(AUTHORIZED_USER_IDS[0], report))
                
                if reputation == 'trusted':
                    buy_alert = f"💎💎 *TRUSTED DEV POTENTIAL* 💎💎\nTokens by this developer historically perform well.\nContract: `{ca}`"
                    asyncio.run(push_notification(AUTHORIZED_USER_IDS[0], buy_alert))
                    time.sleep(1)
                    asyncio.run(push_notification(AUTHORIZED_USER_IDS[0], buy_alert))
            except Exception as e:
                print(f"WARN: Telegram notify failed: {e}")
        elif is_manual:
            def _fnum(n):
                if n >= 1e6: return f"{n/1e6:.1f}M"
                if n >= 1e3: return f"{n/1e3:.1f}k"
                return f"{n:.0f}"
            report = (
                f"🏷️ *Research Complete: {symbol}*\n"
                f"Status: {current_cat.upper()}\n"
                f"Confidence: {final_score}/100\n"
                f"--------------------------\n"
                f"💰 MC: ${_fnum(mc)}\n"
                f"👥 Holders: {holders_count}\n"
                f"--------------------------\n"
                f"CA: `{ca}`"
            )
            try:
                asyncio.run(push_notification(AUTHORIZED_USER_IDS[0], report))
            except Exception as e:
                pass

    # 6. Chain into High-Priority Intake Monitor
    monitor_intake.schedule(args=(ca,), delay=1)
    
    _progress("🚀 Research complete! Dashboard monitoring started...", 100)

@intake_huey.task()
def monitor_intake(ca):
    """Dedicated Express Lane for Analyzing and Graduated tokens."""
    return monitor_on_chain_logic(ca, queue_instance=intake_huey)

@default_huey.task()
def monitor_on_chain(ca):
    """Standard Monitoring for Gems, Trending, and Established tokens."""
    return monitor_on_chain_logic(ca, queue_instance=default_huey)

def monitor_on_chain_logic(ca, queue_instance=None):
    """
    Unified monitoring logic that can run on either the 'Intake' or 'Default' Huey instance.
    """
    try:
        if not queue_instance: queue_instance = default_huey
        
        # ── LOCKING ────────────────────────────────────────────────────────
        r = get_redis_connection()
        lock_key = f"monitor_lock:{ca}"
        
        # Check if a task is already processing this CA. 
        if not r.set(lock_key, "active", ex=30, nx=True):
            return

        # ── BULLETPROOF INITIALIZATION ───────────────────────────────────────
        is_scam = False
        is_rugged = False
        is_zombie = False
        pair_created_at = 0
        mc = 0
        holders = 0
        current_liq = 0
        initial_liq = 0
        mc_growth_1h, mc_direction = 0.0, '→'
        holder_growth_1h, holder_direction = 0.0, '→'
        breakdown = []
        final_score = 0
        social_metadata = {"followers": 0, "is_verified": False}
        token_data = {}
        # ─────────────────────────────────────────────────────────────────────

        logger.info(f"MONITOR: Checking on-chain metrics for {ca}...")
        analyzer = OnChainAnalyzer()
        
        # 1. Fetch historical context from DB earlier for persistence
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT dex_x_link, initial_liquidity,
                   twitter_followers, twitter_verified, is_trusted_creator,
                   liquidity_locked, top_10_holding, pair_created_at,
                   mc, holders_count, liquidity, initial_mc,
                   holder_growth_1h, final_score, is_safe,
                   last_security_audit_at, graduation_mc, highest_mc_post_grad,
                   peak_x, current_x, current_category, locked_notified,
                   trending_alerted
            FROM token_history WHERE ca = ?
        """, (ca,))
        row = cursor.fetchone()

        # 0. Check cache for static info (Identity & Socials)
        cached_data = get_cached_token_info(ca)
        
        # ── DYNAMIC SECURITY RE-AUDIT (Phase 64 Precision) ───────────────────
        # Every 10 minutes, force a fresh RugCheck call
        last_sec_audit = row[15] if (row and len(row) > 15 and row[15] is not None) else 0
        now_ts = int(time.time())
        was_reaudited = False
        
        if (now_ts - last_sec_audit) > 600: # 10 Minutes
             if cached_data: 
                 cached_data.pop("liquidity_locked", None)
                 # Force GoPlus re-fetch inside analyze_token too
                 cached_data.pop("security", None) 
                 was_reaudited = True
                 print(f"BKG: {ca} - FORCED Dynamic Security Audit (RC+GP).")
        # ───────────────────────────────────────────────────────────────────

        # 1. Fetch latest data (passing cache to save resources)
        token_data = analyzer.analyze_token(ca, cached_data=cached_data)
        if not token_data:
            logger.warning(f"BKG: {ca} - SKIPPED (DexScreener API returned no data)")
            if queue_instance == intake_huey:
                monitor_intake.schedule(args=(ca,), delay=30)
            else:
                monitor_on_chain.schedule(args=(ca,), delay=30)
            return
        
        logger.info(f"BKG: {ca} - Fetched metrics. MC: ${token_data.get('mc', 0)}")

        # Check for honeypot and early stop
        security_info = token_data.get("security", {})
        if security_info.get("is_honeypot"):
            print(f"BKG: Scam confirmed for {ca}. Stopping monitor.")
            # Update status in DB and notify dashboard
            conn = get_connection()
            cursor = conn.cursor()
            cursor.execute("UPDATE token_history SET is_scam = 1, final_score = 0 WHERE ca = ?", (ca,))
            conn.commit()
            conn.close()
            publish_event("dashboard_events", "token_update", {"ca": ca, "is_scam": True, "score": 0})
            is_scam = True # Set flag only, don't return!

        # 1. Historical data already fetched above (row variable)


        # ── METRIC PERSISTENCE ───────────────────────────────────────────────
        # Phase 90: High-Response Updates. 
        # Only fallback to stored data if incoming is exactly 0 and stored is > 0.
        incoming_mc = token_data.get('mc', 0)
        stored_mc = row[8] if (row and row[8]) else 0
        mc = incoming_mc if (incoming_mc or 0) > 0 else stored_mc
        token_data['mc'] = mc

        incoming_holders = token_data.get('holders', {}).get('holders_count', 0)
        stored_holders = row[9] if (row and row[9]) else 0
        
        # Phase 58/90: Smarter Holder Tracking
        # If DexScreener returns 0 holders (glitch), we fallback.
        # Otherwise, we trust the incoming value even if it's a drop (could be a mass sell-off).
        if (incoming_holders or 0) == 0 and (stored_holders or 0) > 0:
            holders = stored_holders
        else:
            holders = incoming_holders if (incoming_holders or 0) > 0 else (stored_holders or 0)
            
        # Final Safety: if token has volume/mc, it MUST have holders.
        if holders <= 0 and mc > 5000:
            holders = 25 # Minimum realistic floor for a token with $5k MC
            
        if not token_data.get('holders'): token_data['holders'] = {}
        token_data['holders']['holders_count'] = holders

        incoming_liq = token_data.get('liquidity', 0)
        stored_liq = row[10] if (row and row[10]) else 0
        current_liq = incoming_liq if (incoming_liq or 0) > 0 else stored_liq
        token_data['liquidity'] = current_liq
        
        t_name = token_data.get('name') or f"Token {ca[:6]}"
        t_symbol = token_data.get('symbol') or f"{ca[:3]}"
        # ─────────────────────────────────────────────────────────────────────

        # Store metrics in time_series_metrics table
        metrics = [
            ('market_cap', mc),
            ('holders_count', holders),
            ('liquidity', current_liq),
            ('twitter_followers', token_data.get('social_meta', {}).get('followers', 0))
        ]
        
        for m_type, val in metrics:
            cursor.execute("""
                INSERT INTO time_series_metrics (ca, metric_type, value)
                VALUES (?, ?, ?)
            """, (ca, m_type, val))
        
        conn.commit() 
        
        x_link = row[0] if (row and row[0]) else None
        initial_liq = row[1] if (row and row[1]) else current_liq
        
        # ── FIX: Correct assignment to avoid UnboundLocalError ────────────────
        pair_created_at = row[7] if (row and row[7]) else None
        
        # Inject pair_created_at for ScoringEngine (Phase 1 checks)
        # If DexScreener has no age, use 0 or current DB state
        if not pair_created_at and token_data.get("pair_created_at"):
            pair_created_at = token_data["pair_created_at"]
        
        if pair_created_at:
            token_data["pair_created_at"] = pair_created_at
        else:
            # Absolute fallback: use current time (seconds) so age starts at 1m
            pair_created_at = int(time.time())
            token_data["pair_created_at"] = pair_created_at
        # ─────────────────────────────────────────────────────────────────────

        # ── FIX: Persist liquidity_locked + top_10 across monitor cycles ──────
        stored_liq_locked = bool(row[5]) if (row and row[5] is not None) else False
        stored_top10 = float(row[6]) if (row and row[6] is not None) else None

        if not token_data.get("liquidity_locked") and stored_liq_locked:
            token_data["liquidity_locked"] = True

        if stored_top10 is not None:
            if not token_data.get("holders"): token_data["holders"] = {}
            current_top10 = token_data["holders"].get("top_10_percent", 0.0)
            # Use the better (lower) value if incoming is 0 or worse
            if current_top10 == 0.0 or (stored_top10 < current_top10 and stored_top10 > 0):
                token_data["holders"]["top_10_percent"] = stored_top10

        # Inject resolved social links so ScoringEngine sees them
        resolved_x = x_link
        if token_data.get("links", {}).get("twitter"):
            resolved_x = token_data["links"]["twitter"]
        if resolved_x: token_data["x_link"] = resolved_x
        if token_data.get("links", {}).get("telegram"):
            token_data["tg_link"] = token_data["links"]["telegram"]

        # Load previous social indices
        prev_followers = row[2] if (row and row[2]) else 0
        prev_verified = bool(row[3]) if (row and row[3]) else False
        prev_trusted = bool(row[4]) if (row and row[4]) else False

        is_followed = False
        is_verified_creator = prev_trusted
        social_metadata = {
            "followers": prev_followers,
            "is_verified": prev_verified,
            "account_age_days": 365
        }

        if resolved_x:
            handle_match = re.search(r"(?:x|twitter)\.com/(\w+)", resolved_x)
            if handle_match:
                handle = handle_match.group(1).lower()
                
                # Slowly sync metadata via scraper if missing or to update
                from src.core.social import SocialAnalyzer
                social_analyzer = SocialAnalyzer()
                scraper_info = social_analyzer.get_x_account_metadata(handle)
                # Keep the highest follower count so it doesn't bounce around as much with random mocks
                if scraper_info.get("followers", 0) > prev_followers:
                     social_metadata["followers"] = scraper_info["followers"]
                     social_metadata["is_verified"] = scraper_info["is_verified"]

                cursor.execute("SELECT 1 FROM user_following WHERE handle = ?", (handle,))
                is_followed = cursor.fetchone() is not None

                cursor.execute("SELECT trust_score FROM verified_creators WHERE handle = ?", (handle,))
                vc = cursor.fetchone()
                if vc:
                    is_verified_creator = True
                    social_metadata["trust_score"] = vc[0]
                
                if is_followed:
                    social_metadata["followers"] = max(social_metadata["followers"], 5000)
                    social_metadata["is_verified"] = True

        # ── IMMEDIATE LIQUIDITY LOCKED NOTIFICATION (Phase 92: Safe Locked) ──
        is_locked = bool(token_data.get("liquidity_locked"))
        was_locked_notified = bool(row[21]) if (row and len(row) > 21) else False
        stored_cat = row[20] if (row and len(row) > 20) else 'analyzing'
        
        if is_locked and not was_locked_notified and stored_cat in ('analyzing', 'graduated'):
             from src.utils.telegram import send_token_alert
             from src.config import AUTHORIZED_USER_IDS
             if AUTHORIZED_USER_IDS:
                 asyncio.run(send_token_alert(AUTHORIZED_USER_IDS[0], {
                     "ca": ca,
                     "symbol": token_data.get("symbol", "TKN"),
                     "score": final_score,
                     "mc": token_data.get("mc", 0),
                     "mc_growth_1h": token_data.get("mc_growth_1h", 0),
                     "category": "Gems", 
                     "followers": social_metadata.get("followers", 0),
                     "liquidity_locked": True
                 }))
                 # Persist notification status safely
                 conn_notif = get_connection()
                 curs_notif = conn_notif.cursor()
                 curs_notif.execute("UPDATE token_history SET locked_notified = 1 WHERE ca = ?", (ca,))
                 conn_notif.commit()
                 conn_notif.close()
                 print(f"BKG: {ca} - Immediate Telegram notification sent for Locked Liquidity.")
        # ───────────────────────────────────────────────────────────────────

        # 2. PRE-REQUISITES (Residency and Discovery Baseline)
        conn_check = get_connection()
        scursor = conn_check.cursor()
        scursor.execute("SELECT current_category, initial_gem_mc, highest_mc_ever, telegram_submission_time, is_steady_grower, last_tg_msg_id FROM token_history WHERE ca=?", (ca,))
        row_cat = scursor.fetchone()
        
        stored_cat = row_cat[0] if row_cat else "analyzing"
        stored_initial_mc = row_cat[1] if row_cat else None
        stored_highest_mc = row_cat[2] if (row_cat and row_cat[2] is not None) else 0.0
        submission_time = row_cat[3] if (row_cat and row_cat[3]) else (int(time.time()) - 3600) # Fallback to 1h old if unknown
        is_steady_grower_stored = bool(row_cat[4]) if (row_cat and len(row_cat) > 4 and row_cat[4]) else False
        last_tg_msg_id = row_cat[5] if (row_cat and len(row_cat) > 5) else None
        conn_check.close()
        
        initial_mc_any = row[11] if (row and row[11]) else mc
        if row[11] is None:
             cursor.execute("UPDATE token_history SET initial_mc = ? WHERE ca = ?", (mc, ca))
             conn.commit()

        # residency check for both growth and aging
        now_ts = int(time.time())
        # Phase 69: Use token age (pair_created_at) for 24H logic
        token_age = now_ts - (pair_created_at or submission_time)
        is_over_24h = token_age > 86400

        # Social Follower Velocity
        follower_velocity, follower_direction = get_ema_direction(ca, 'twitter_followers', long_window=60)
        social_metadata["velocity"] = follower_velocity
        social_metadata["direction"] = follower_direction

        # Growth Calculations (On-chain holder growth)
        growth_10m = get_holder_growth(ca, window_mins=10)
        growth_60m = get_holder_growth(ca, window_mins=60)

        # 2. Advanced Performance Analysis — EMA-based direction + Long-term Trend
        mc_growth_1h, mc_direction = get_ema_direction(ca, 'market_cap', short_window=10, long_window=60, fallback_baseline=initial_mc_any)
        # Fetch previous hour growth for velocity comparison (Total 2H growth)
        mc_growth_2h = get_mc_growth(ca, window_mins=120)
        holder_growth_1h, holder_direction = get_ema_direction(ca, 'holders_count', short_window=10, long_window=60, fallback_baseline=holders)
        
        # ── HOLDER MOMENTUM SMOOTHING & DECAY (Phase 90 Precision) ────────────
        prev_holder_growth = row[12] if (row and len(row) > 12 and row[12] is not None) else 0.0
        # Reduced smoothing from 0.4/0.6 to 0.2/0.8 for faster response
        if (holder_growth_1h or 0) > 0:
            holder_growth_1h = (prev_holder_growth * 0.2) + (holder_growth_1h * 0.8)
        else:
            # Faster decay (0.8 instead of 0.95) to clear stale momentum
            holder_growth_1h = max(0.0, prev_holder_growth * 0.8) 
            if holder_growth_1h < 0.1: holder_growth_1h = 0.0
        # ─────────────────────────────────────────────────────────────────────

        long_term_trend = get_long_term_trend(ca)
        token_data["long_term_trend"] = long_term_trend

        # Phase 54/56/58: Advanced Risk Shield Audits (Refined)
        lp_count = token_data.get("lp_holder_count", 0)
        creator_wallet = token_data.get("creator_wallet", "Unknown")
        creator_rug_history = _audit_creator_reputation(creator_wallet)
        is_concentrated = token_data.get("holders", {}).get("is_concentrated", False)

        # Phase 58/59: Heuristic Refinement
        is_locked = bool(token_data.get("liquidity_locked"))
        effective_pair_ts = int(pair_created_at) if pair_created_at else int(time.time())
        token_age_mins = (int(time.time()) - effective_pair_ts) / 60
        is_pump_fun = ca.lower().endswith("pump")

        is_low_lp = False
        if not is_pump_fun and token_age_mins > 15:
            # Solana typically has 1 LP provider (the AMM).
            # We only flag as "Low LP" if it's 0 (no pool) OR if it's a multi-LP chain token with low density.
            if lp_count == 0:
                is_low_lp = True
            elif lp_count < 3 and current_liq < 10000:
                is_low_lp = True

        liq_threshold = 5000 if token_age_mins > 30 else 1000
        is_low_liq = current_liq < liq_threshold

        risk_flags = {
            "low_lp_providers": is_low_lp, 
            "serial_rugger": creator_rug_history > 0,
            "whale_concentration": is_concentrated,
            "low_liquidity": is_low_liq 
        }

        scoring_engine = ScoringEngine()
        new_score, breakdown, is_zombie = scoring_engine.calculate_score(
            token_data,
            holder_growth=holder_growth_1h,
            long_term_growth=growth_60m,
            creator_data={
                'is_followed_by_user': is_followed,
                'is_verified_creator': is_verified_creator,
                'social_metadata': social_metadata,
                'serial_rugger': creator_rug_history > 0
            }
        )

        # ── SCORE SMOOTHING (Phase 90 High-Response) ─────────────────────────
        prev_score = row[13] if (row and len(row) > 13) else 0
        if (new_score or 0) > 0:
            if (prev_score or 0) > 0:
                 # If score change is large (>15), favor the new score more (0.2/0.8)
                 if abs(new_score - prev_score) > 15:
                     final_score = round((prev_score * 0.2) + (new_score * 0.8))
                 else:
                     final_score = round((prev_score * 0.4) + (new_score * 0.6))
            else:
                 final_score = round(new_score)
        else:
            # Faster decay for scam signals
            final_score = round(max(0.0, prev_score * 0.7))
        # ─────────────────────────────────────────────────────────────────────

        security_info = token_data.get('security', {})
        is_scam = (bool(security_info.get('is_honeypot')) or final_score < 15)
        is_gem = (final_score >= 50 and is_locked)
        is_trending = ((growth_10m > 5) or (long_term_trend == 'slow_grower')) and is_locked

        is_rugged = False
        if initial_liq > 500:
            drop = (initial_liq - current_liq) / initial_liq
            if drop > 0.8: is_rugged = True
        if current_liq < 100: is_rugged = True

        is_died = (mc < 10000) and (stored_highest_mc > 1) and (mc < stored_highest_mc * 0.3)
        # Absolute floor: tokens under $5k MC are dead regardless of peak ratio
        if mc < 5000 and not is_rugged:
            is_died = True
        if is_died and (mc_growth_1h or 0) > 15: is_died = False

        # --- DYNAMIC CATEGORIZATION (Phase 91: Safety First) ---
        if is_rugged:
            current_cat = 'scammed'
        elif is_died:
            current_cat = 'died'
        elif is_gem:
            age_sec = now_ts - (pair_created_at or now_ts)
            multiplier = (stored_highest_mc / initial_mc_any) if initial_mc_any > 0 else 0

            if age_sec < 86400: # TRENDING (<24H)
                if (mc_growth_1h or 0) > 20 or (holder_growth_1h or 0) > 2:
                    current_cat = 'trending'
                else:
                    current_cat = 'gems'
            else: # HALL OF FAME (>=24H)
                multiplier = (stored_highest_mc / initial_mc_any) if initial_mc_any > 0 else 0
                mc_drop = (stored_highest_mc - mc) / max(stored_highest_mc, 1.0)
                
                # HoF: Must be growing, not dead peaks.
                is_hof_candidate = (multiplier >= 5 or mc >= 250000 or final_score > 85)
                is_performing = (mc_drop < 0.5) and (mc_growth_1h >= -15.0)
                
                if is_hof_candidate and is_performing:
                    current_cat = 'hall_of_fame'
                elif age_sec >= 604800:
                    current_cat = 'legacy'
                else:
                    current_cat = 'established'

            if current_cat in ['gems', 'trending'] and mc < 8000:
                current_cat = 'died'
            elif current_cat in ['established', 'legacy', 'hall_of_fame'] and mc < 25000:
                current_cat = 'died'

        # Safe Baseline: If locked, default to established if no higher rank achieved
        elif is_locked and not is_scam:
             if mc < 5000:
                 current_cat = 'died'  # Locked but dead MC
             else:
                 age_sec = now_ts - (pair_created_at or now_ts)
                 if age_sec < 86400: # < 24H (Phase 92)
                     current_cat = 'gems'
                 elif age_sec >= 604800: # >= 7 days
                     current_cat = 'legacy'
                 else:
                     current_cat = 'established'
        elif (stored_cat in ['scams', 'scammed', 'scam_trending']) and (mc_growth_1h or 0) > 1 and (holder_growth_1h or 0) > 0:
            if not is_locked:
                current_cat = 'scam_trending'
            else:
                current_cat = 'established'
        elif is_scam and not is_locked:
            current_cat = 'scams'
        else:
            current_cat = 'scams'

        # Graduation / Sticky Logic overrides
        if current_cat == 'gems' and is_over_24h:
            age_sec = now_ts - (pair_created_at or now_ts)
            current_cat = 'legacy' if age_sec >= 604800 else 'established'

        # Phase 68: Trending → Hall of Fame age-out (>24H good tokens graduate)
        if current_cat == 'trending' and is_over_24h:
            multiplier = (stored_highest_mc / initial_mc_any) if (initial_mc_any or 0) > 0 else 0
            if multiplier >= 5 or (mc or 0) >= 250000 or (final_score or 0) > 70:
                current_cat = 'hall_of_fame'
            else:
                age_sec = now_ts - (pair_created_at or now_ts)
                current_cat = 'legacy' if age_sec >= 604800 else 'established'

        # Phase 68: Graduated tokens get a 30-minute grace period.
        # After that, they MUST move to their calculated category.
        # User Request: Speed up everything. 5m max in Graduation.
        if stored_cat == 'graduated':
            time_since_submission = now_ts - submission_time
            if time_since_submission < 300 and not is_rugged and not is_scam:
                # Still fresh (< 5 min) — keep in graduated if no better destination
                if current_cat in ('scams', 'scammed', 'died'):
                    current_cat = 'graduated'
            # else: let current_cat stand (moves out after 5 min)

        # Phase 68/69/72/75/77: Refined Graduation Momentum Tracking (Moment of Release)
        # Phase 88: Self-Healing and Multi-Queue Logic
        grad_mc = row[16] if (row and len(row) > 16 and row[16] is not None) else None
        highest_post_grad = row[17] if (row and len(row) > 17 and row[17] is not None) else 0.0
        
        # Determine if this is the MOMENT of Graduation (any move from intake to terminal)
        is_just_graduating = (stored_cat in ('analyzing', 'graduated')) and (current_cat not in ('analyzing', 'graduated'))
        
        if is_just_graduating and grad_mc is None:
            # Pin the baseline to the EXACT moment of dashboard release
            grad_mc = mc
            highest_post_grad = mc
            logging.info(f"🎓 DASHBOARD RELEASE MC CAPTURED for {ca}: ${grad_mc}")
        elif (current_cat not in ('analyzing', 'graduated')) and grad_mc is None:
            # SELF-HEALING: Token is already out of intake but missing baseline
            # Use initial_mc as a best-guess starting point
            grad_mc = initial_mc_any or mc
            highest_post_grad = max(stored_highest_mc or 0.0, mc)
            logging.info(f"🩹 SELF-HEALING: Backfilled graduation_mc for {ca}: ${grad_mc}")
        elif grad_mc is not None:
            highest_post_grad = max(highest_post_grad, mc)

        # Logic for Multipliers (Current and Peak)
        peak_x = (highest_post_grad / grad_mc) if (grad_mc and grad_mc > 0) else 0.0
        current_x = (mc / grad_mc) if (grad_mc and grad_mc > 0) else 0.0

        # Phase 68/69/72: High-speed Intake Cleanup (5 min MAX)
        # User wants faster turnover: 5 mins absolute limit in Graduation.
        if stored_cat in ('analyzing', 'graduated'):
            time_since_submission = now_ts - submission_time
            if time_since_submission > 300: # 5 min - ABSOLUTE MAX
                # Force out of FOMO tab into terminal categories
                if current_cat in ('analyzing', 'graduated'):
                    current_cat = 'died' if mc < 5000 else 'established'
            elif current_cat in ('scams', 'scammed', 'died'):
                # Still very fresh (< 5 min) — keep visible briefly to avoid flickering
                current_cat = stored_cat

        ranks = {'hall_of_fame': 10, 'trending': 8, 'gems': 6, 'established': 5, 'legacy': 4, 'graduated': 3, 'analyzing': 2, 'scam_trending': 1, 'scams': 0, 'scammed': -1, 'died': -2}
        is_promotion = ranks.get(current_cat, 0) > ranks.get(stored_cat, 0)

        if stored_cat in ['gems', 'established', 'legacy', 'trending', 'scam_trending', 'hall_of_fame'] and not is_rugged and current_cat != 'died' and not is_promotion:
            mc_drop = (stored_highest_mc - mc) / max(stored_highest_mc, 1)
            # Reduced stickiness: if score drops below 40 OR mc under $5k, we MUST re-categorize
            if not (mc_drop > 0.4 or final_score < 40 or mc < 5000):
                if not ((stored_cat == 'gems' and is_over_24h) or (stored_cat in ['legacy', 'established'] and mc < 10000)):
                    current_cat = stored_cat # STICKY

        if is_promotion:
            logging.info(f"BKG: {ca} PROMOTED from {stored_cat} -> {current_cat}! Score: {final_score}")

        # 4B. High Quality Alert Engine (Phase 29 + User Logic)
        new_last_tg_msg_id = last_tg_msg_id
        
        # Immediate notification for tokens hitting Trending with good score
        was_trending_notified = bool(row[22]) if (row and len(row) > 22) else False
        if current_cat == 'trending' and final_score >= 70 and not was_trending_notified:
             from src.config import AUTHORIZED_USER_IDS
             if AUTHORIZED_USER_IDS:
                  now_ts = int(time.time())
                  multiplier = (mc / grad_mc) if (grad_mc and grad_mc > 0) else 1.0
                  
                  def _fnum(n):
                      if n >= 1e6: return f"{n/1e6:.1f}M"
                      if n >= 1e3: return f"{n/1e3:.1f}k"
                      return f"{n:.0f}"

                  msg = (
                      f"🚀 <b>TRENDING SIGNAL DETECTED</b> 🚀\n\n"
                      f"<b>Token:</b> {t_symbol} ({t_name})\n"
                      f"<b>Confidence:</b> {final_score}/100 🔥\n"
                      f"<b>Market Cap:</b> ${_fnum(mc)} (<b>{mc_growth_1h:+.1f}% 1H</b>)\n"
                      f"<b>Momentum:</b> {max(0, multiplier-1):.1f}x Gain (Peak: {max(0, peak_x-1):.1f}x)\n"
                      f"<b>Metrics:</b> {'🔒' if is_locked else '🔓'} Locked | 🐦 {social_metadata.get('followers', 0)} X\n\n"
                      f"<b>CA (Click to Copy):</b>\n"
                      f"<code>{ca}</code>\n\n"
                      f"📊 <a href='https://dexscreener.com/solana/{ca}'>View on DexScreener</a>"
                  )
                  try:
                      asyncio.run(push_notification(AUTHORIZED_USER_IDS[0], msg))
                          
                      reputation = row[43] if (row and len(row) > 43) else "neutral"
                      if reputation == 'trusted' or is_verified_creator:
                          buy_alert = f"💎💎 <b>TRUSTED DEV POTENTIAL</b> 💎💎\nTokens by this developer historically perform well.\nContract: <code>{ca}</code>"
                          # Synchronous execution
                          asyncio.run(push_notification(AUTHORIZED_USER_IDS[0], buy_alert))
                          time.sleep(1)
                          asyncio.run(push_notification(AUTHORIZED_USER_IDS[0], buy_alert))
                      
                      # Save notification status
                      conn_tn = get_connection()
                      curs_tn = conn_tn.cursor()
                      curs_tn.execute("UPDATE token_history SET trending_alerted = 1 WHERE ca = ?", (ca,))
                      conn_tn.commit()
                      conn_tn.close()
                      print(f"BKG: {ca} - Immediate Trending Alert sent.")
                  except Exception as et:
                      logging.error(f"Failed to send Trending alert: {et}")

        # Logic 6: 'Safe' Indicator (Phase 60/63/66)
        # A token is "Safe" if it has high score + locked + no red flags
        sec = token_data.get("security", {})
        try:
            buy_tax = float(sec.get("buy_tax", 0) or 0)
            sell_tax = float(sec.get("sell_tax", 0) or 0)
        except:
            buy_tax, sell_tax = 0, 0

        # Phase 66 Hardening: Pump.fun contracts are standard and secure by design.
        # If GoPlus flags are missing or ambiguous, we trust the Pump.fun provenance.
        if is_pump_fun:
            if sec.get("is_honeypot") is None: sec["is_honeypot"] = False
            if sec.get("is_mintable") is None: sec["is_mintable"] = False
            if sec.get("is_proxy") is None: sec["is_proxy"] = False
            if sec.get("is_blacklisted") is None: sec["is_blacklisted"] = False

        is_currently_safe = (
            final_score > 65 and 
            (token_data.get("liquidity_locked") or is_pump_fun) and 
            not is_low_lp and 
            not sec.get("is_honeypot") and 
            not sec.get("is_mintable") and 
            not sec.get("is_proxy") and
            not sec.get("is_blacklisted") and
            buy_tax < 15 and 
            sell_tax < 15
        )
        
        if final_score > 65:
            logging.info(f"BKG: Checking Safety for {ca} - Pump: {is_pump_fun}, Score: {final_score:.1f}, Locked: {token_data.get('liquidity_locked')}, LowLP: {is_low_lp}, Honeypot: {sec.get('is_honeypot')}, BuyTax: {buy_tax} -> SAFE: {is_currently_safe}")


        # ── STICKY SAFE LOGIC (Phase 64/66 Hardening) ───────────────────────────
        prev_is_safe = bool(row[14]) if (row and len(row) > 14 and row[14] is not None) else False
        is_safe = is_currently_safe
        if prev_is_safe:
            # Once marked safe, we maintain the status unless a definitive HARD RISK is detected
            # or the score drops below 40 (severe crash)
            is_honeypot = bool(sec.get("is_honeypot"))
            is_mintable = bool(sec.get("is_mintable"))
            is_tax_high = float(sec.get("buy_tax", 0)) > 20 or float(sec.get("sell_tax", 0)) > 20
            
            # Critical exclusion list for safe tokens
            if is_honeypot or is_mintable or is_tax_high or is_rugged or final_score < 40:
                is_safe = False # Revoke safety on hard risks
            else:
                is_safe = True # Sticky! Prevents flickering from momentum jitters
        # ─────────────────────────────────────────────────────────────────────

        # Performance Tracking: Initial Gem MC
        new_initial_gem_mc = stored_initial_mc
        if current_cat in ["gems", "established", "legacy"] and stored_initial_mc is None:
            new_initial_gem_mc = mc
            
        new_highest_mc = max(stored_highest_mc or 0.0, mc)

        # 5. Save to DB (with Growth and Status persistence)
        cursor.execute("""
            UPDATE token_history 
            SET name = ?, symbol = ?, mc = ?, holders_count = ?,
                final_score = ?, is_scam = ?, is_trending = ?,
                is_rugged = ?, is_zombie = ?, score_breakdown = ?,
                last_updated_at = ?, current_category = ?,
                twitter_followers = ?, twitter_verified = ?, is_trusted_creator = ?,
                liquidity_locked = ?, top_10_holding = ?, pair_created_at = ?,
                liquidity = ?, initial_gem_mc = ?, highest_mc_ever = ?,
                mc_growth_1h = ?, mc_growth_2h = ?, holder_growth_1h = ?,
                is_steady_grower = ?, initial_mc = COALESCE(initial_mc, ?),
                last_tg_msg_id = ?, creator_wallet = ?, lp_holder_count = ?,
                risk_flags = ?, is_safe = ?, 
                last_security_audit_at = ?, graduation_mc = ?, highest_mc_post_grad = ?,
                peak_x = ?, current_x = ?
            WHERE ca = ?
        """, (
            t_name, t_symbol,
            mc, holders, final_score,
            1 if is_scam else 0, 1 if is_trending else 0,
            1 if is_rugged else 0, 1 if is_zombie else 0,
            json.dumps(breakdown), int(time.time()), current_cat,
            social_metadata.get("followers", 0),
            1 if social_metadata.get("is_verified") else 0,
            1 if (is_followed or is_verified_creator) else 0,
            1 if token_data.get("liquidity_locked") else 0,
            token_data.get("holders", {}).get("top_10_percent", 0.0),
            pair_created_at, current_liq, new_initial_gem_mc, new_highest_mc,
            mc_growth_1h, mc_growth_2h, holder_growth_1h,
            1 if (long_term_trend == "slow_grower" or is_steady_grower_stored) else 0, 
            initial_mc_any, new_last_tg_msg_id, creator_wallet, lp_count,
            json.dumps(risk_flags), 1 if is_safe else 0, 
            now_ts if was_reaudited else last_sec_audit,
            grad_mc, highest_post_grad,
            peak_x, current_x, ca
        ))
        conn.commit()
        conn.close()

        # 6. Notify dashboard
        publish_event("dashboard_events", "token_update", {
            "ca": ca, "name": t_name, "symbol": t_symbol,
            "mc": mc, "holders_count": holders,
            "liquidity": current_liq, "score": final_score,
            "is_scam": is_scam, "is_trending": is_trending,
            "is_rugged": is_rugged, "is_zombie": is_zombie,
            "is_safe": is_safe,
            "breakdown": breakdown, "last_updated": int(time.time()),
            "current_category": current_cat,
            "mc_growth_1h": mc_growth_1h, "mc_growth_2h": mc_growth_2h,
            "mc_direction": mc_direction, "holder_growth_1h": holder_growth_1h,
            "holder_direction": holder_direction, "pair_created_at": pair_created_at,
            "social_meta": social_metadata, 
            "is_steady_grower": (long_term_trend == "slow_grower" or is_steady_grower_stored),
            "initial_mc": initial_mc_any,
            "initial_gem_mc": new_initial_gem_mc, 
            "highest_mc_ever": new_highest_mc,
            "graduation_mc": grad_mc,
            "highest_mc_post_grad": highest_post_grad,
            "peak_x": peak_x,
            "current_x": current_x,
            "x_link": x_link,
            "telegram_submission_time": submission_time,
            "image_url": token_data.get("image_url", ""),
            "lp_holder_count": lp_count,
            "creator_wallet": creator_wallet,
            "risk_flags": risk_flags,
            "security_details": sec
        })

        # 7. Re-schedule with Multi-Queue Hand-off (Phase 91: Infinite Chain)
        # Even rugged tokens are re-scheduled at 24H intervals to allow for data corrections.
        delay_sec = 60
        next_huey = default_huey
        
        # ULTRA-FAST: 20 Seconds for active Gems
        if current_cat == "gems":
            delay_sec = 20
        # THROTTLED: Dead/Rugged/Scams hibernated for 24H to save RPC
        elif current_cat in ["died", "scammed", "scams"] or is_rugged:
            delay_sec = 86400 # 24 Hours
        
        # INTAKE FAST LANE: Use intake_huey for analyzing/graduated
        if current_cat in ("analyzing", "graduated"):
            delay_sec = 30 # Check intake every 30s
            next_huey = intake_huey

        cat_label = "RUGGED" if is_rugged else current_cat.upper()
        queue_label = "INTAKE" if next_huey == intake_huey else "DEFAULT"
        logging.info(f"BKG: {ca} ({cat_label}) - Rescheduling on {queue_label} in {delay_sec}s.")
        
        # Map function name to the correct queue instance
        if next_huey == intake_huey:
            monitor_intake.schedule(args=(ca,), delay=delay_sec)
        else:
            monitor_on_chain.schedule(args=(ca,), delay=delay_sec)

        
    except Exception as e:
        logger.error(f"CRITICAL ERROR in monitor_logic ({ca}): {e}")
        traceback.print_exc()
        # On error, wait longer but don't die
        if queue_instance == intake_huey:
            monitor_intake.schedule(args=(ca,), delay=30)
        else:
            monitor_on_chain.schedule(args=(ca,), delay=30)
    finally:
        # ── FIX: ALWAYS RELEASE THE LOCK ─────────────────────────────────────
        # If we don't delete here, the next 15s poll will FAIL because it sees the 30s lock.
        r = get_redis_connection()
        r.delete(f"monitor_lock:{ca}")
        # ─────────────────────────────────────────────────────────────────────

@huey.task()
def handle_correction(ca, x_link):
    """
    Handles a corrective submission for an existing CA.
    """
    print(f"BKG: Correcting research for {ca} with link {x_link}...")
    # Re-trigger social analysis immediately
    monitor_social(ca, x_link)

@huey.periodic_task(crontab(minute='0')) # Every Hour
def sync_user_following():
    """
    Syncs the user's X following list every hour.
    """
    print(f"BKG: Syncing following list for {USER_X_PROFILE}...")
    
    # 1. Scrape current following list (Mocked)
    current_handles = ["elonmusk", "vitalikbuterin", "cz_binance"] # Scraped
    
    conn = get_connection()
    cursor = conn.cursor()
    
    # 2. Get existing handles
    cursor.execute("SELECT handle FROM user_following")
    existing_handles = {row[0] for row in cursor.fetchall()}
    
    # 3. Diff and Update
    new_handles = set(current_handles) - existing_handles
    removed_handles = existing_handles - set(current_handles)
    
    for h in new_handles:
        cursor.execute("INSERT INTO user_following (handle) VALUES (?)", (h,))
    for h in removed_handles:
        cursor.execute("DELETE FROM user_following WHERE handle = ?", (h,))
        
    conn.commit()
    conn.close()
    print(f"BKG: Sync complete. Added: {len(new_handles)}, Removed: {len(removed_handles)}")

def get_holder_growth(ca, window_mins=60):
    """
    Returns % growth in holders_count over the last window_mins.
    Finds the oldest recorded value within the past window_mins and compares
    it against the most recent value.
    """
    conn = get_connection()
    cursor = conn.cursor()
    # Latest value
    cursor.execute("""
        SELECT value FROM time_series_metrics
        WHERE ca = ? AND metric_type = 'holders_count'
        ORDER BY timestamp DESC LIMIT 1
    """, (ca,))
    latest = cursor.fetchone()
    # Oldest value recorded within the past window_mins
    cursor.execute("""
        SELECT value FROM time_series_metrics
        WHERE ca = ? AND metric_type = 'holders_count'
          AND timestamp >= datetime('now', ?)
        ORDER BY timestamp ASC LIMIT 1
    """, (ca, f'-{window_mins} minutes'))
    oldest = cursor.fetchone()
    conn.close()
    if not latest or not oldest or oldest[0] == 0:
        return 0.0
    return ((latest[0] - oldest[0]) / oldest[0]) * 100


def detect_trend(ca):
    """
    Returns True if market cap has grown > 10% in last hour.
    """
    growth = get_mc_growth(ca, window_mins=60)
    return growth > 10.0


def get_cached_token_info(ca):
    """
    Returns existing name, symbol, and social links from the database to save on scraping.
    """
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT name, symbol, dex_x_link, dex_tg_link FROM token_history WHERE ca = ?", (ca,))
    row = cursor.fetchone()
    conn.close()
    if row and row[0] and row[0] != "Unknown":
        return {
            "name": row[0],
            "symbol": row[1],
            "links": {"twitter": row[2], "telegram": row[3]}
        }
    return None

def _audit_creator_reputation(creator_wallet):
    """
    Queries the database for other tokens created by the same wallet.
    Returns the count of tokens that ended up in 'scammed' or 'died' categories.
    """
    if not creator_wallet or creator_wallet == "Unknown":
        return 0
    try:
        from src.utils.db import get_connection
        conn = get_connection()
        cur = conn.cursor()
        # Ensure we don't accidentally count the current token if it's already died/scammed
        cur.execute("SELECT COUNT(*) FROM token_history WHERE creator_wallet = ? AND current_category IN ('scammed', 'died', 'scams')", (creator_wallet,))
        count = cur.fetchone()[0]
        conn.close()
        return count
    except Exception as e:
        print(f"Reputation Audit Error: {e}")
        return 0

@huey.periodic_task(crontab(minute='*/1'))
def monitor_safety_net():
    """
    Periodic check to ensure all active, non-scammed tokens are being monitored.
    This fixes cases where the scheduling chain broke.
    """
    print("BKG: Running monitoring safety net...")
    conn = get_connection()
    cursor = conn.cursor()
    # Safety net: Scan all tokens, ensure none have fallen through the cracks
    cursor.execute("SELECT ca, current_category, last_updated_at FROM token_history")
    token_rows = cursor.fetchall()
    conn.close()
    
    r = get_redis_connection()
    now = int(time.time())
    
    for ca, cat, last_upd in token_rows:
        lock_key = f"monitor_lock:{ca}"
        if not r.exists(lock_key):
            # Smart-Safety-Net logic: Only resume if truly stalled beyond its expected window
            last_upd_ts = last_upd if last_upd else 0
            stall_time = now - last_upd_ts
            
            # Hibernated categories (24H window)
            if cat in ["died", "scammed", "scams"]:
                if stall_time < 86400: continue
            
            # Active categories (should be updated every 1-2 minutes)
            # If stall > 5 mins, it's definitely stuck
            if stall_time < 300:
                continue
                
            print(f"BKG: Resuming monitoring for stalled token: {ca} ({cat}) - Stall: {stall_time}s")
            if cat in ("analyzing", "graduated"):
                monitor_intake.schedule(args=(ca,), delay=1)
            else:
                monitor_on_chain.schedule(args=(ca,), delay=1)

@huey.task()
def monitor_social(ca, x_link):
    """
    Re-scans social profile for updates and detects trending momentum.
    """
    if not x_link:
        return
        
    print(f"MONITOR: Checking social for {ca} at {x_link}...")
    analyzer = SocialAnalyzer()
    
    # Extract handle from link
    handle_match = re.search(r"(?:x|twitter)\.com/(\w+)", x_link)
    handle = handle_match.group(1) if handle_match else None
    
    # 1. Get current engagement (Mocked)
    current_retweets = 500 # Should be scraped
    
    # 2. Get historical retweet count for velocity calculation
    # TODO: Fetch last retweet_count from time_series_metrics
    last_retweets = 350 # Placeholder
    
    velocity = current_retweets - last_retweets
    is_trending = velocity > 100 # 100 new retweets since last poll
    
    print(f"BKG: {ca} Velocity: {velocity} | Trending: {is_trending}")
    
    # 3. Notify user if trending
    if is_trending and AUTHORIZED_USER_IDS:
        msg = f"🔥 *TRENDING ALERT*\nToken: `{ca}`\nVelocity: +{velocity} retweets!"
        try:
            asyncio.run(push_notification(AUTHORIZED_USER_IDS[0], msg))
        except Exception as e:
            print(f"WARN: Could not send trending alert: {e}")
        
    # 3. Update dashboard via SSE (Trigger via DB or direct call)
    # TODO: Push {type: 'token_update', payload: {ca, trending: is_trending}}
    
    monitor_social.schedule(args=(ca, x_link), delay=600)

def get_mc_growth(ca, window_mins=60):
    """
    Calculates market cap growth percentage over the last window_mins.
    Uses the oldest data-point recorded within the past window vs the latest.
    """
    conn = get_connection()
    cursor = conn.cursor()
    # Latest value
    cursor.execute("""
        SELECT value FROM time_series_metrics 
        WHERE ca = ? AND metric_type = 'market_cap'
        ORDER BY timestamp DESC LIMIT 1
    """, (ca,))
    latest = cursor.fetchone()
    # Oldest value within the past window_mins
    cursor.execute("""
        SELECT value FROM time_series_metrics 
        WHERE ca = ? AND metric_type = 'market_cap'
          AND timestamp >= datetime('now', ?)
        ORDER BY timestamp ASC LIMIT 1
    """, (ca, f'-{window_mins} minutes'))
    oldest = cursor.fetchone()
    conn.close()

    if not latest or not oldest or oldest[0] == 0:
        return 0.0
    return ((latest[0] - oldest[0]) / oldest[0]) * 100


def get_ema_direction(ca, metric_type, short_window=10, long_window=60, fallback_baseline=None):
    """
    Uses Exponential Moving Average to determine trend direction for a metric.
    Compares short EMA (recent) vs long EMA (baseline).
    Returns: (pct_change: float, direction: str)
    """
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT value, timestamp FROM time_series_metrics 
        WHERE ca = ? AND metric_type = ?
          AND timestamp >= datetime('now', ?)
        ORDER BY timestamp ASC
    """, (ca, metric_type, f'-{long_window} minutes'))
    rows = cursor.fetchall()
    conn.close()

    if not rows:
        return (0.0, '→') if fallback_baseline is None else (0.0, '→')

    values = [r[0] for r in rows]
    latest_val = values[-1]
    
    # Baseline for PCT calculation
    # Use the oldest value in the window, and if it's 0 or missing, use fallback_baseline
    oldest_val = values[0]
    if (not oldest_val or oldest_val == 0) and fallback_baseline:
        oldest_val = fallback_baseline
    
    if len(values) < 2:
        if fallback_baseline and (fallback_baseline or 0) > 0:
             pct = ((latest_val - (fallback_baseline or 0)) / (fallback_baseline or 1)) * 100
             return round(pct, 2), ('▲' if pct > 0 else '→')
        return 0.0, '→'

    def ema(data, span):
        k = 2.0 / (span + 1)
        e = data[0]
        for v in data[1:]:
            e = v * k + e * (1 - k)
        return e

    short_span = max(2, min(len(values), short_window))
    long_span = max(2, len(values))

    short_ema = ema(values, short_span)
    long_ema = ema(values, long_span)

    if oldest_val == 0:
        pct = 0.0
    else:
        pct = ((latest_val - oldest_val) / oldest_val) * 100

    if short_ema > long_ema * 1.005:
        direction = '▲'
    elif short_ema < long_ema * 0.995:
        direction = '▼'
    else:
        direction = '→'

    return round(pct, 2), direction

def get_long_term_trend(ca):
    """
    Analyzes token performance over a longer horizon (up to 7 days).
    Returns a status string: 'slow_grower', 'already_grown', 'unstable', or 'new'.
    'slow_grower': Consistent green days/hours without a massive parabolic blowoff.
    'already_grown': Currently > 40% below its all-time peak.
    """
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT value, timestamp FROM time_series_metrics 
        WHERE ca = ? AND metric_type = 'market_cap'
          AND timestamp >= datetime('now', '-7 days')
        ORDER BY timestamp ASC
    """, (ca,))
    rows = cursor.fetchall()
    conn.close()

    if len(rows) < 10:
        return "new"

    values = [r[0] for r in rows]
    current = values[-1]
    peak = max(values)
    oldest = values[0]

    # 1. Check for 'Already Grown & Fallen' (Pump & Dump detection)
    if peak > oldest * 3 and current < peak * 0.6:
        return "already_grown"

    # 2. Check for 'Slow Grower' (Steady accumulation)
    # If it's up > 50% from start but never had a > 100% hourly spike
    # and it's near its peak (within 15%)
    is_steady = True
    for i in range(1, len(values)):
        if values[i] > values[i-1] * 2.5: # 150% jump in one poll is't steady
            is_steady = False
            break
    
    if is_steady and current > oldest * 1.5 and current > peak * 0.85:
        return "slow_grower"

    return "stable"

