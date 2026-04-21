import asyncio
import websockets
import json
import requests
import threading

from src.config import HELIUS_API_KEY

def fetch_and_process(signature: str):
    """
    Takes a raw blockchain signature from WSS, queries the Helius REST framework to construct an Enhanced Transaction (mimicking exactly what the Webhook does), and extracts the inner mint.
    """
    # Phase 90: Ultra-high speed discovery. 
    # Reduced from 30s to 10s for near-instant dashboard appearance.
    import time
    time.sleep(10) 
    
    try:
        url = f"https://api.helius.xyz/v0/transactions/?api-key={HELIUS_API_KEY}"
        resp = requests.post(url, json={"transactions": [signature]})
        if resp.status_code == 200:
            txs = resp.json()
            if not txs: return
            tx = txs[0]
            
            # Secure token_mint extraction from native Transfers array
            transfers = tx.get("tokenTransfers", [])
            for t in transfers:
                mint = t.get("mint")
                if mint and mint != "So11111111111111111111111111111111111111112":
                    from src.graduation_ai import process_graduation
                    process_graduation(mint, "", signature)
                    break
    except Exception as e:
        print(f"WSS Parser Sub-Thread Error: {e}")

async def listen():
    print("📡 Initializing zero-friction Helius WebSocket streaming engine...")
    uri = f"wss://mainnet.helius-rpc.com/?api-key={HELIUS_API_KEY}"
    while True:
        try:
            async with websockets.connect(uri) as websocket:
                req = {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "logsSubscribe",
                    "params": [
                        {"mentions": ["675kPX9MHTjS2tz1jyGZeqZAp8LrcfNpbhB1g9ybgRpq"]},
                        {"commitment": "processed"}
                    ]
                }
                await websocket.send(json.dumps(req))
                print("✅ Secure WebSocket Bridge to Raydium AMM Active! Awaiting Liquidity Pools...")
                
                while True:
                    msg = await websocket.recv()
                    data = json.loads(msg)
                    
                    params = data.get("params", {})
                    if not params: continue
                    
                    result = params.get("result", {}).get("value", {})
                    logs = result.get("logs")
                    signature = result.get("signature")
                    
                    if not logs or not signature: continue
                    
                    # Log scanning for Raydium primitive instructions
                    is_creation = False
                    for log in logs:
                        if "Instruction: InitializeInstruction2" in log or "Instruction: Initialize2" in log:
                            is_creation = True
                            break
                            
                    if is_creation:
                        print(f"🌊 RAW POOL DETECTED (Signature: {signature[:12]}...). Passing to parser...")
                        threading.Thread(target=fetch_and_process, args=(signature,)).start()
        except Exception as e:
            print(f"WSS Disconnected: {e}. Re-establishing tunnel in 3s...")
            await asyncio.sleep(3)

if __name__ == "__main__":
    asyncio.run(listen())
