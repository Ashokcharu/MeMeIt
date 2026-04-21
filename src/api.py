import os, sys
# Add project root to sys.path to resolve 'src' package
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse
from src.config import DB_PATH
from fastapi.middleware.cors import CORSMiddleware
import asyncio
import json
import time
from src.utils.db import get_connection
from src.utils.redis import get_redis_connection
from src.core.database import init_db

init_db() # 🚀 Ensure schema is up to date on every startup

app = FastAPI(title="MeMeIt Dashboard API")

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # Simplified for reliability
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.post("/api/webhook/helius")
async def helius_webhook(request: Request):
    try:
        payload = await request.json()
        from src.graduation_ai import process_graduation
        
        # Helius Enhanced Webhook Payload is an array of transactions
        if isinstance(payload, list):
            for tx in payload:
                # We are looking for LP pool creation or initial swaps
                if tx.get("type") in ["SWAP", "UNKNOWN", "POOL_CREATE"]:
                    transfers = tx.get("tokenTransfers", [])
                    for t in transfers:
                        mint = t.get("mint")
                        if mint and mint != "So11111111111111111111111111111111111111112":
                            # Fast non-blocking handoff to Graduation Engine
                            import threading
                            threading.Thread(target=process_graduation, args=(mint, "")).start()
                            break # Limit to primary mint
    except Exception as e:
        print(f"Webhook Error: {e}")
    return {"status": "ok"}

@app.get("/api/tokens")
async def get_tokens():
    """
    Returns a list of all analyzed tokens.
    """
    from fastapi.responses import Response
    from src.utils.redis import get_redis_connection
    r = get_redis_connection()
    try:
        cached = r.get("api_tokens_cache")
        if cached:
            return Response(content=cached, media_type="application/json")
    except:
        pass # Fallback if redis fails

    from src.utils.db import get_connection
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT ca, name, symbol, final_score, initial_liquidity, is_scam, dex_x_link, dex_tg_link, mc, holders_count, top_10_holding, liquidity_locked, is_trending, is_rugged, social_risk, growth_ratio, score_breakdown, last_updated_at, is_zombie,
               twitter_followers, twitter_symbols, twitter_status, is_trusted_creator, twitter_verified, pair_created_at,
               liquidity, telegram_submission_time, current_category,
               mc_growth_1h, mc_growth_2h, holder_growth_1h, is_steady_grower, initial_mc, highest_mc_ever,
               creator_wallet, lp_holder_count, risk_flags, is_safe, image_url,
               graduation_mc, highest_mc_post_grad, peak_x, current_x,
               reputation, creator_success_count, creator_total_tokens, is_followed_by_user
        FROM token_history 
        ORDER BY telegram_submission_time DESC, last_updated_at DESC 
    """)
    rows = cursor.fetchall()
    conn.close()
    
    tokens = []
    for r in rows:
        breakdown = []
        if r[16]:
            try:
                breakdown = json.loads(r[16])
            except: pass

        tokens.append({
            "ca": r[0],
            "name": r[1] or "Unknown",
            "symbol": r[2],
            "score": r[3],
            "liquidity": r[25] if (r[25] is not None and r[25] > 0) else (r[4] or 0.0),
            "is_scam": bool(r[5]),
            "x_link": r[6],
            "tg_link": r[7],
            "mc": r[8] or 0.0,
            "holders_count": r[9] or 0,
            "top_10_holding": r[10] or 0.0,
            "liquidity_locked": bool(r[11]),
            "is_trending": bool(r[12]),
            "is_rugged": bool(r[13]),
            "social_risk": r[14] or "Low Risk",
            "growth_ratio": r[15] or 0.0,
            "last_updated": int(r[17]) if isinstance(r[17], (int, float)) or (isinstance(r[17], str) and r[17].isdigit()) else int(time.time()),
            "breakdown": breakdown,
            "is_zombie": bool(r[18]),
            "is_trusted_creator": bool(r[22]),
            "social_meta": {"followers": r[19] or 0, "is_verified": bool(r[23])},
            "pair_created_at": r[24],
            "telegram_submission_time": r[26],
            "current_category": r[27],
            "mc_growth_1h": r[28] or 0.0,
            "mc_growth_2h": r[29] or 0.0,
            "holder_growth_1h": r[30] or 0.0,
            "is_steady_grower": bool(r[31]),
            "initial_mc": r[32],
            "highest_mc_ever": r[33],
            "creator_wallet": r[34],
            "lp_holder_count": r[35] or 0,
            "risk_flags": json.loads(r[36]) if r[36] else {},
            "is_safe": bool(r[37]),
            "image_url": r[38] or "",
            "graduation_mc": r[39],
            "highest_mc_post_grad": r[40],
            "peak_x": r[41],
            "current_x": r[42],
            "reputation": r[43] or "neutral",
            "creator_success_count": r[44] or 0,
            "creator_total_tokens": r[45] or 0,
            "is_followed_by_user": bool(r[46])
        })
    try:
        result_json = json.dumps(tokens)
        r.setex("api_tokens_cache", 10, result_json)
        from fastapi.responses import Response
        return Response(content=result_json, media_type="application/json")
    except Exception as e:
        print(f"Redis cache set failed: {e}")
        return tokens

@app.get("/api/tokens/{ca}")
async def get_token_report(ca: str):
    """
    Returns the latest risk report for a specific token.
    """
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT ca, name, symbol, final_score, score_breakdown, initial_liquidity, mc, holders_count, liquidity_locked, is_scam, is_rugged, is_zombie,
               twitter_followers, is_trusted_creator, twitter_verified, pair_created_at,
               liquidity, telegram_submission_time, current_category,
               mc_growth_1h, mc_growth_2h, holder_growth_1h, is_steady_grower, initial_mc, highest_mc_ever,
               creator_wallet, lp_holder_count, risk_flags, is_safe, image_url,
               graduation_mc, highest_mc_post_grad, peak_x, current_x
        FROM token_history WHERE ca = ? ORDER BY created_at DESC LIMIT 1
    """, (ca,))
    r = cursor.fetchone()
    conn.close()
    
    if not r:
        return {"error": "Token not found"}
        
    breakdown = []
    if r[4]:
        try: breakdown = json.loads(r[4])
        except: pass
        
    return {
        "ca": r[0], "name": r[1], "symbol": r[2], "score": r[3],
        "breakdown": breakdown, 
        "liquidity": r[16] if (r[16] is not None and r[16] > 0) else (r[5] or 0.0), 
        "mc": r[6], "holders_count": r[7], "liquidity_locked": bool(r[8]),
        "is_scam": bool(r[9]), "is_rugged": bool(r[10]), "is_zombie": bool(r[11]),
        "social_meta": {"followers": r[12] or 0, "is_verified": bool(r[14])},
        "is_trusted_creator": bool(r[13]),
        "pair_created_at": r[15],
        "telegram_submission_time": r[17],
        "current_category": r[18],
        "mc_growth_1h": r[19] or 0.0,
        "mc_growth_2h": r[20] or 0.0,
        "holder_growth_1h": r[21] or 0.0,
        "is_steady_grower": bool(r[22]),
        "initial_mc": r[23],
        "highest_mc_ever": r[24],
        "creator_wallet": r[25],
        "lp_holder_count": r[26] or 0,
        "risk_flags": json.loads(r[27]) if r[27] else {},
        "is_safe": bool(r[28]),
        "image_url": r[29] or "",
        "graduation_mc": r[30],
        "highest_mc_post_grad": r[31],
        "peak_x": r[32],
        "current_x": r[33]
    }

@app.get("/api/stream")
async def sse_events(request: Request):
    """
    SSE endpoint to push live updates to the frontend using Redis Pub/Sub.
    """
    async def event_generator():
        from src.utils.redis import get_async_redis_connection
        r = get_async_redis_connection()
        pubsub = r.pubsub()
        await pubsub.subscribe("dashboard_events")
        last_ping = asyncio.get_event_loop().time()
        
        try:
            while True:
                if await request.is_disconnected():
                    break
                
                # Fetch message with timeout so we can yield pings
                message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
                
                if message and message['type'] == 'message':
                    data = message['data']
                    try:
                        msg_body = json.loads(data)
                        print(f"OUT: SSE Event type={msg_body.get('type')} ca={msg_body.get('payload', {}).get('ca', 'N/A')}")
                    except: pass
                    
                    yield f"event: update\ndata: {data}\n\n"
                
                # Keepalive ping every 15s
                now = asyncio.get_event_loop().time()
                if now - last_ping > 15:
                    yield ": ping\n\n"
                    last_ping = now
                
                # Short sleep to prevent CPU spinning if get_message was instant
                await asyncio.sleep(0.1)

        finally:
            await pubsub.unsubscribe("dashboard_events")
            await pubsub.aclose()
            await r.aclose()

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        }
    )

if __name__ == "__main__":
    import uvicorn
    # Use 4 workers to handle concurrent SSE and API calls robustly
    uvicorn.run("src.api:app", host="0.0.0.0", port=8000, workers=4)
