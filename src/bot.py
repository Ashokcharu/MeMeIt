import os, sys, re, time, logging
# Add project root to sys.path to resolve 'src' package
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, MessageHandler, filters
from telegram.request import HTTPXRequest
from src.config import TELEGRAM_BOT_TOKEN, AUTHORIZED_USER_IDS
from src.utils.db import get_connection
from src.utils.telegram import push_notification
from src.utils.redis import publish_event

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.WARNING
)
logging.getLogger('httpx').setLevel(logging.ERROR)
logging.getLogger('httpcore').setLevel(logging.ERROR)

# Regex for CA (EVM/SOL)
CA_PATTERN = r"([0-9a-zA-Z]{32,44})"
# Regex for X/Twitter links
LINK_PATTERN = r"(https?://(?:x|twitter)\.com/\w+)"

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("MeMeIt Risk Analysis Bot\nSend me a CA and an optional X link to start research.\nFormat: `CA [X-Link]`")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if AUTHORIZED_USER_IDS and user_id not in AUTHORIZED_USER_IDS:
        print(f"⚠️  UNAUTHORIZED ACCESS ATTEMPT: User ID {user_id}")
        await update.message.reply_text(f"⛔ Unauthorized. This bot is private.\nYour User ID is: `{user_id}`\nPlease provide this ID to the developer.")
        return

    text = update.message.text
    ca_match = re.search(CA_PATTERN, text)
    link_match = re.search(LINK_PATTERN, text)
    
    if not ca_match:
        await update.message.reply_text("❌ Could not find a valid Contract Address (CA) in your message.")
        return

    ca = ca_match.group(1)
    link = link_match.group(1) if link_match else None
    
    from src.workers import start_research, handle_correction
    from src.core.database import get_connection

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT 1 FROM token_history WHERE ca = ?", (ca,))
    exists = cursor.fetchone()
    conn.close()

    if exists:
        # Check if research is already fresh (< 5 mins) or if user provided a new link
        if not link:
            conn = get_connection()
            cursor = conn.cursor()
            cursor.execute("""
                SELECT name, symbol, final_score, mc, current_category, 
                       graduation_mc, highest_mc_post_grad, trending_alerted
                FROM token_history WHERE ca = ?
            """, (ca,))
            token = cursor.fetchone()
            conn.close()
            
            if token and token[2] != -1: # Not in 'Analyzing' state
                name, symbol, score, mc, cat, grad_mc, peak_mc, notified = token
                res_mc = grad_mc or mc
                p_mc = peak_mc or mc
                multiplier = (mc / res_mc) if res_mc > 0 else 1.0
                peak_x = (p_mc / res_mc) if res_mc > 0 else 1.0
                
                def _fnum(n):
                    if n >= 1e6: return f"{n/1e6:.1f}M"
                    if n >= 1e3: return f"{n/1e3:.1f}k"
                    return f"{n:.0f}"

                report = (
                    f"🏷️ <b>Token Found: {symbol}</b>\n"
                    f"Status: {cat.upper()}\n"
                    f"Confidence: {score}/100\n"
                    f"--------------------------\n"
                    f"💰 MC: ${_fnum(mc)}\n"
                    f"🚀 Release MC: ${_fnum(res_mc)}\n"
                    f"📈 Peak: {peak_x:.1f}x (Current: {multiplier:.1f}x)\n"
                    f"--------------------------\n"
                    f"CA: <code>{ca}</code>\n"
                    f"📊 <a href='https://dexscreener.com/solana/{ca}'>DexScreener</a>"
                )
                await update.message.reply_text(report, parse_mode='HTML')
                return

        # Move back to "Analyzing" state for fresh research
        conn = get_connection()
        cursor = conn.cursor()
        now = int(time.time())
        fallback_name = f"Token {ca[:6]}"
        fallback_symbol = f"TKN-{ca[:4]}"
        
        cursor.execute("""
            UPDATE token_history 
            SET name = ?, symbol = ?, final_score = -1, last_updated_at = ?, telegram_submission_time = ?, current_category = 'analyzing',
                is_rugged = 0, is_scam = 0 
            WHERE ca = ?
        """, (fallback_name, fallback_symbol, now, now, ca))
        conn.commit()
        conn.close()
        
        handle_correction(ca, link)
        publish_event("dashboard_events", "token_update", {
            "ca": ca, "score": -1, "name": fallback_name, "symbol": fallback_symbol, 
            "x_link": link, "current_category": "analyzing", "telegram_submission_time": now
        })
        await update.message.reply_text(f"🔄 Refreshing research for existing CA: `{ca}`\nMoved back to Analyzing tab! Social Link: {link or 'None'}")
    else:
        now = int(time.time())
        t_name = f"Incoming ({ca[:4]}...)"
        t_symbol = "---"
        mc = 0
        liquidity = 0
        image_url = ""

        # Fast-Track Intake Data (Phase 30)
        from src.core.on_chain import DexScreenerClient
        client = DexScreenerClient()
        fast_data = client.get_token_data(ca)
        
        if fast_data:
            mc = fast_data.get("mc", 0)
            liquidity = fast_data.get("liquidity", 0)
            image_url = fast_data.get("image_url", "")
            t_name = fast_data.get("name", t_name)
            t_symbol = fast_data.get("symbol", t_symbol)

        # Phase 31: Zero-Index Defense (Helius Fallback)
        if not fast_data or mc == 0 or not image_url:
            from src.core.helius import HeliusClient
            helius_fallback = HeliusClient().get_token_data(ca)
            if helius_fallback:
                mc = helius_fallback.get("mc", mc)
                image_url = helius_fallback.get("image_url", image_url)
                if t_symbol == "---":
                    t_name = helius_fallback.get("name", t_name)
                    t_symbol = helius_fallback.get("symbol", t_symbol)

        # Insert a placeholder row to instantly show "Analyzing" in the dashboard
        conn = get_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT INTO token_history 
            (ca, name, symbol, mc, holders_count, initial_liquidity, liquidity, final_score, 
             is_scam, is_trending, is_rugged, is_zombie, score_breakdown, 
             last_updated_at, telegram_submission_time, current_category, 
             dex_x_link, twitter_followers, twitter_verified, is_trusted_creator, pair_created_at, image_url)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (ca, t_name, t_symbol, mc, 0, liquidity, liquidity, -1, 0, 0, 0, 0, '[]', now, now, 'analyzing', link, 0, 0, 0, now, image_url))
        conn.commit()
        conn.close()

        # Immediate UI Feedback (Phase 29)
        from src.utils.redis import publish_event
        publish_event("dashboard_events", "token_update", {
            "ca": ca,
            "current_category": "analyzing",
            "name": t_name,
            "symbol": t_symbol,
            "mc": mc,
            "score": 0,
            "last_updated": now,
            "pair_created_at": 0,
            "liquidity": liquidity,
            "holders_count": 0,
            "image_url": image_url
        })

        # Enqueue the background task
        start_research(ca, link, is_manual=True)
        await update.message.reply_text(f"🔍 Research started for `{ca}`\nCheck the dashboard! Monitoring for 5 minutes.\nSocial Link: {link or 'None'}")

def main():
    # Increase timeouts for slow network environments (Phase 78)
    request = HTTPXRequest(connect_timeout=30, read_timeout=30)
    application = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).request(request).build()
    
    start_handler = CommandHandler('start', start)
    msg_handler = MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message)
    
    application.add_handler(start_handler)
    application.add_handler(msg_handler)
    
    print("Bot is running...")
    application.run_polling()

if __name__ == '__main__':
    main()
