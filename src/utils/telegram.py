import asyncio
from telegram import Bot
from src.config import TELEGRAM_BOT_TOKEN

async def push_notification(chat_id, message, mode='HTML', reply_to_message_id=None):
    """
    Sends a push notification with specified parse mode and optional threading.
    """
    try:
        bot = Bot(token=TELEGRAM_BOT_TOKEN)
        sent = await bot.send_message(
            chat_id=chat_id, text=message, parse_mode=mode, 
            disable_web_page_preview=False,
            reply_to_message_id=reply_to_message_id
        )
        return sent.message_id
    except Exception as e:
        print(f"Error sending TG notification: {e}")
        return None

async def send_token_alert(chat_id, token_data, reply_to_message_id=None):
    """
    Sends a high-quality formatted token alert for Phase 29.
    Smartly threads messages if tracking the same token.
    """
    ca = token_data.get('ca', 'Unknown')
    symbol = token_data.get('symbol', 'TKN')
    score = token_data.get('score', 0)
    mc = token_data.get('mc', 0)
    g1h = token_data.get('mc_growth_1h', 0)
    cat = token_data.get('category', 'Gems')
    followers = token_data.get('followers', 0)
    locked = token_data.get('liquidity_locked', False)
    
    # Format MC
    if mc >= 1e6: mc_str = f"${mc/1e6:.1f}M"
    elif mc >= 1e3: mc_str = f"${mc/1e3:.1f}k"
    else: mc_str = f"${mc:.0f}"

    lock_emoji = "🔒" if locked else "🔓"
    
    if reply_to_message_id:
        msg = (
            f"🚀 <b>UPDATE: {symbol} Moving Higher!</b> 🚀\n\n"
            f"<b>Market Cap:</b> {mc_str} (<b>{g1h:+.1f}% 1H</b>)\n"
            f"<b>Category:</b> {cat.upper()}\n"
            f"<b>CA:</b>\n<code>{ca}</code>\n\n"
            f"📊 <a href='https://dexscreener.com/solana/{ca}'>View on DexScreener</a>"
        )
    else:
        msg = (
            f"💎 <b>SMART ALERT: {cat.upper()}</b> 💎\n\n"
            f"<b>Token:</b> {symbol}\n"
            f"<b>Confidence:</b> {score}/100 🔥\n"
            f"<b>Market Cap:</b> {mc_str} (1H: {g1h:+.1f}%)\n"
            f"<b>Metrics:</b> {lock_emoji} Locked | 🐦 {followers} X Followers\n\n"
            f"<b>CA (Click to Copy):</b>\n"
            f"<code>{ca}</code>\n\n"
            f"📊 <a href='https://dexscreener.com/solana/{ca}'>View on DexScreener</a>"
        )
        
    return await push_notification(chat_id, msg, mode='HTML', reply_to_message_id=reply_to_message_id)
