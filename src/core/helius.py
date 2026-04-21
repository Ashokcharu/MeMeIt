import requests
import time
from src.config import HELIUS_API_KEYS

class HeliusClient:
    _key_index = 0

    def __init__(self):
        self.session = requests.Session()

    def get_token_data(self, ca):
        """
        Uses Helius DAS API (getAsset) to fetch Token Info (Price & Supply).
        Acts as a high-speed fallback when DexScreener is rate-limited.
        Automatically rotates through available API keys on 429 errors.
        """
        if not HELIUS_API_KEYS:
            return None
            
        payload = {
            "jsonrpc": "2.0",
            "id": "memeit-fallback",
            "method": "getAsset",
            "params": {
                "id": ca,
                "displayOptions": {
                    "showFungible": True
                }
            }
        }

        # Try each key once before giving up
        for _ in range(len(HELIUS_API_KEYS)):
            current_key = HELIUS_API_KEYS[HeliusClient._key_index]
            rpc_url = f"https://mainnet.helius-rpc.com/?api-key={current_key}"
            
            try:
                res = self.session.post(rpc_url, json=payload, timeout=5)
                
                # Rotate key if rate-limited
                if res.status_code == 429:
                    print(f"RATE LIMIT: Helius 429 on key '{current_key[:6]}...'. Switching keys.")
                    HeliusClient._key_index = (HeliusClient._key_index + 1) % len(HELIUS_API_KEYS)
                    continue
                    
                res.raise_for_status()
                data = res.json().get("result", {})
                
                if not data:
                    return None
                    
                token_info = data.get("token_info", {})
                price_info = token_info.get("price_info", {})
                price = price_info.get("price_per_token", 0.0)
                
                supply = token_info.get("supply", 0)
                decimals = token_info.get("decimals", 0)
                
                real_supply = supply / (10 ** decimals) if decimals else supply
                mc = price * real_supply
                
                content = data.get("content", {})
                metadata = content.get("metadata", {})
                
                result = {
                    "name": metadata.get("name", "Unknown"),
                    "symbol": metadata.get("symbol", f"{ca[:4]}"),
                    "price": str(price),
                    "mc": mc,
                    "chain": "solana",
                    "liquidity": 0, # Liquidity is hard to reliably extract from getAsset alone
                    "volume_24h": 0,
                    "pair_age_ms": 0,
                    "dexId": "helius_fallback",
                    "pairAddress": ca,
                    "pair_created_at": 0,
                    "links": {},
                    "is_fallback": True,
                    "image_url": content.get("links", {}).get("image", metadata.get("image", ""))
                }
                return result
                
            except Exception as e:
                # If it's a connection error or server error, we can try next key just in case,
                # but it's usually better to break to avoid thrashing. We print and break.
                print(f"Helius Fallback Error for {ca}: {e}")
                break
                
        return None
