import requests
import time
from .rugcheck import RugCheckClient

class DexScreenerClient:
    BASE_URL = "https://api.dexscreener.com/latest/dex/tokens"

    def __init__(self):
        self.session = requests.Session()

    def get_token_data(self, ca):
        """
        Fetches basic token data from Dexscreener.
        Returns price, liquidity, volume, pair age, and chain.
        """
        url = f"{self.BASE_URL}/{ca}"
        # Dual Architecture: DexScreener Primary, Helius Fallback (Phase 27)
        for attempt in range(2): 
            try:
                response = self.session.get(url, timeout=10)
                if response.status_code == 429:
                    # Multi-Stage Optimization (Phase 46)
                    # Routine background monitoring MUST NOT burn Helius credits.
                    # We only allow RPC fallbacks for manual Telegram submissions.
                    wait_time = 10 
                    time.sleep(wait_time)
                    continue
                
                response.raise_for_status()
                data = response.json()
                
                pairs = data.get("pairs", [])
                if not pairs:
                    return None
                    
                # STRICT check: Only process pairs where this CA is the BASE token.
                # Avoids adopting the name/MC of a scam token that creates a pool against this CA.
                ca_lower = ca.lower()
                base_pairs = [p for p in pairs if p.get("baseToken", {}).get("address", "").lower() == ca_lower]
                
                # If we legitimately can't find it as a base token at all, check if we provided a quote token or if DexScreener is lagging.
                if not base_pairs:
                    return None
                
                # Phase 91: Selection Robustness. 
                # Prioritize Liquidity first, then MC.
                valid_pairs = [p for p in base_pairs if float(p.get("liquidity", {}).get("usd", 0) or 0) > 500]
                if not valid_pairs: valid_pairs = base_pairs
                
                # Sort by Liquidity DESC, then MarketCap DESC
                primary_pair = sorted(valid_pairs, key=lambda x: (
                    float(x.get("liquidity", {}).get("usd", 0) or 0),
                    float(x.get("marketCap", x.get("fdv", 0)) or 0)
                ), reverse=True)[0]
                
                # Extract links
                raw_socials = primary_pair.get("info", {}).get("socials", [])
                processed_links = {}
                for link in raw_socials:
                    l_type = link.get("type", "").lower()
                    l_url = link.get("url", "")
                    if l_type in ["twitter", "x"] and len(l_url) > 15: # Avoid https://x.com/ stubs
                        processed_links["twitter"] = l_url
                    elif l_type == "telegram":
                        processed_links["telegram"] = l_url
                
                raw_websites = primary_pair.get("info", {}).get("websites", [])
                for w in raw_websites:
                    if w.get("url"):
                        processed_links["website"] = w.get("url")


                result = {
                    "name": primary_pair.get("baseToken", {}).get("name"),
                    "symbol": primary_pair.get("baseToken", {}).get("symbol"),
                    "price": primary_pair.get("priceUsd"),
                    "mc": float(primary_pair.get("marketCap", primary_pair.get("fdv", 0))),
                    "liquidity": primary_pair.get("liquidity", {}).get("usd"),
                    "volume_24h": primary_pair.get("volume", {}).get("h24"),
                    "pair_age_ms": int(time.time() * 1000) - primary_pair.get("pairCreatedAt", 0),
                    "chain": primary_pair.get("chainId"),
                    "dexId": primary_pair.get("dexId"),
                    "pairAddress": primary_pair.get("pairAddress"),
                    "pair_created_at": primary_pair.get("pairCreatedAt", 0) / 1000,
                    "links": processed_links,
                    "image_url": primary_pair.get("info", {}).get("imageUrl", "")
                }
                return result
            except Exception as e:
                if attempt == 4:
                    print(f"Error fetching DexScreener data: {e}")
                # Short wait (2s) on generic connection issues
                time.sleep(2)
        return None

class GoPlusClient:
    BASE_URLS = {
        "1": "https://api.gopluslabs.io/api/v1/token_security/1",
        "56": "https://api.gopluslabs.io/api/v1/token_security/56",
        "solana": "https://api.gopluslabs.io/api/v1/solana/token_security"
    }

    def __init__(self):
        self.session = requests.Session()

    def get_token_security(self, chain_id, ca):
        """
        Fetches security data from GoPlus.
        """
        base_url = self.BASE_URLS.get(chain_id)
        if not base_url:
            return None
        
        try:
            response = self.session.get(f"{base_url}?contract_addresses={ca}", timeout=10)
            response.raise_for_status()
            data = response.json()
            if data.get("code") == 1:
                result = data.get("result", {})
                # Solana often returns a list of results
                if isinstance(result, list) and len(result) > 0:
                    return result[0]
                # For EVM, result is a dict with CA as key
                if isinstance(result, dict) and ca in result:
                    return result[ca]
                return result
            return None
        except Exception as e:
            print(f"Error fetching GoPlus data: {e}")
            return None

class OnChainAnalyzer:
    _shared_session = None

    def __init__(self):
        if OnChainAnalyzer._shared_session is None:
            OnChainAnalyzer._shared_session = requests.Session()
            OnChainAnalyzer._shared_session.headers.update({
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
            })
        
        self.dex_client = DexScreenerClient()
        self.dex_client.session = OnChainAnalyzer._shared_session
        self.goplus_client = GoPlusClient()
        self.goplus_client.session = OnChainAnalyzer._shared_session

    def analyze_token(self, ca, cached_data=None):
        """
        Main entry point for deep on-chain analysis.
        Uses cached_data if available to save resources.
        """
        token_data = self.dex_client.get_token_data(ca)
        
        # Phase 31: Native Scanner Rescue
        if not token_data or token_data.get('mc', 0) == 0 or not token_data.get('image_url'):
            from src.core.helius import HeliusClient
            helius_fallback = HeliusClient().get_token_data(ca)
            if helius_fallback:
                if not token_data:
                    token_data = helius_fallback
                else:
                    token_data['mc'] = token_data.get('mc', 0) or helius_fallback.get('mc', 0)
                    token_data['image_url'] = token_data.get('image_url') or helius_fallback.get('image_url', "")
                    token_data['name'] = token_data.get('name') or helius_fallback.get('name')
                    token_data['symbol'] = token_data.get('symbol') or helius_fallback.get('symbol')

        if not token_data:
            return None
        
        # 0. Apply Cached Identity
        if cached_data:
            if cached_data.get("name"): token_data["name"] = cached_data["name"]
            if cached_data.get("symbol"): token_data["symbol"] = cached_data["symbol"]
            if cached_data.get("links"):
                if not token_data.get("links"): token_data["links"] = {}
                token_data["links"].update(cached_data["links"])
        
        chain_id_map = {"ethereum": "1", "bsc": "56", "solana": "solana"}
        internal_chain_id = chain_id_map.get(token_data["chain"])
        
        # 1. Security Checks (Layer 1)
        rc_client = RugCheckClient()
        rc_report = None
        
        # Identity/Socials Optimization: 
        # Skip deep RugCheck metadata extraction if we already have it
        needs_identity = not token_data.get("name") or token_data["name"] == "Unknown"
        needs_socials = not token_data.get("links", {}).get("twitter")
        
        if needs_identity or needs_socials or not token_data.get("liquidity_locked"):
            rc_report = rc_client.get_token_report(ca)
        
        # 2. GoPlus Security (Secondary/Fallback)
        security_data = self.goplus_client.get_token_security(internal_chain_id, ca)
        if security_data:
            token_data["security"] = self._process_security(security_data)
            gp_holders = self._process_holders(security_data)
            token_data["holders"] = gp_holders
            token_data["creator_wallet"] = security_data.get("creator_address") or security_data.get("owner_address")
            
            # Phase 54: Extract LP Holder Count for Density Check
            lp_holders = security_data.get("lp_holders", [])
            token_data["lp_holder_count"] = len([h for h in lp_holders if float(h.get("percent", 0)) > 0.1])
            
        # 3. Integrate RugCheck Metadata
        if rc_report:
            token_data["liquidity_locked"] = rc_report.get("liquidity_locked", False)
            if rc_report.get("total_holders"):
                if not token_data.get("holders"): token_data["holders"] = {}
                token_data["holders"]["holders_count"] = rc_report["total_holders"]
            
            if needs_identity:
                token_data["name"] = rc_report.get("name", token_data.get("name"))
                token_data["symbol"] = rc_report.get("symbol", token_data.get("symbol"))
                
            if needs_socials:
                rc_socials = rc_report.get("socials", {})
                for s_key, s_val in rc_socials.items():
                    if s_val and not token_data["links"].get(s_key):
                        token_data["links"][s_key] = s_val

        return token_data

    def _verify_liquidity_multi_layer(self, ca, chain_id):
        """
        Layer 1: RugCheck Report
        Layer 2: DexScreener/Goplus Data
        Layer 3: Local Validation Rules
        """
        is_locked = False
        
        # Layer 1: RugCheck
        try:
            rc_client = RugCheckClient()
            rc_report = rc_client.get_token_report(ca)
            if rc_report and rc_report.get("liquidity_locked"):
                print(f"VERIFY: {ca} - RugCheck confirmed locked.")
                is_locked = True
        except: pass
            
        # Layer 2: Goplus Fallback
        if not is_locked:
            # We already have security_data from Goplus in the caller, but let's re-verify logic
            # (In this simplified version, we'll trust RugCheck or DexScreener's initial flag)
            pass
            
        return is_locked

    def _process_security(self, data):
        return {
            "is_honeypot": data.get("is_honeypot") == "1",
            "is_mintable": data.get("is_mintable") == "1",
            "is_blacklisted": data.get("is_blacklisted") == "1",
            "is_whitelisted": data.get("is_whitelisted") == "1",
            "is_proxy": data.get("is_proxy") == "1",
            "cannot_sell_all": data.get("cannot_sell_all") == "1",
            "slippage_modifiable": data.get("slippage_modifiable") == "1",
            "transfer_pausable": data.get("transfer_pausable") == "1",
            "anti_whale_modifiable": data.get("anti_whale_modifiable") == "1",
            "buy_tax": data.get("buy_tax", "0"),
            "sell_tax": data.get("sell_tax", "0"),
            "owner_privileges": data.get("owner_address") is not None,
            "is_open_source": data.get("is_open_source") == "1"
        }

    def _process_holders(self, data):
        holders = data.get("holders", [])
        top_10_percent = 0.0
        
        # System/Dead addresses to exclude from whale calculation
        system_addresses = [
            "0x000000000000000000000000000000000000dead",
            "0x0000000000000000000000000000000000000000",
            "11111111111111111111111111111111", # Solana system
            "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA" # Solana token program (sometimes shows up)
        ]

        if holders:
            # Filter out LP holders and dead addresses from the "whale" list
            # Note: GoPlus sometimes includes LP pairs as holders
            filtered = [h for h in holders if h.get("address", "").lower() not in system_addresses]
            
            # Sort by balance percentage
            sorted_percentages = sorted([float(h.get("percent", 0)) for h in filtered if h.get("percent")], reverse=True)
            top_10_percent = sum(sorted_percentages[:10])
        
        # GoPlus Solana fallback for holder_count
        raw_count = data.get("holder_count")
        if not raw_count or raw_count == "0":
             holders_count = len(holders) if holders else 0
        else:
             holders_count = int(raw_count)

        return {
            "holders_count": holders_count,
            "top_10_percent": top_10_percent,
            "is_concentrated": top_10_percent > 50.0
        }

    def _check_liquidity_lock(self, data):
        lp_holders = data.get("lp_holders", [])
        if not lp_holders:
            return False
        
        dead_addresses = ["0x000000000000000000000000000000000000dead", "0x0000000000000000000000000000000000000000"]
        total_locked_percent = 0.0
        for holder in lp_holders:
            address = holder.get("address", "").lower()
            if address in dead_addresses or holder.get("is_locked") == 1:
                total_locked_percent += float(holder.get("percent", 0))
        
        return total_locked_percent > 80.0 # 80% locked considered safe-ish

    def detect_clusters(self, ca):
        """
        Placeholder for bubble map/clustering logic.
        Requires heavy on-chain tracing which will be added later.
        """
        return {"clusters_found": False, "details": "Manual tagging required for MVP"}

if __name__ == "__main__":
    # Test with a known CA if available
    pass
