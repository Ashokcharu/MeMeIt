import requests
import time
import logging
from src.config import SOLSCAN_API_KEYS

class SolscanClient:
    def __init__(self):
        self.api_keys = SOLSCAN_API_KEYS
        self.current_key_index = 0
        self.session = requests.Session()

    def _get_next_key(self):
        if not self.api_keys:
            return None
        key = self.api_keys[self.current_key_index]
        self.current_key_index = (self.current_key_index + 1) % len(self.api_keys)
        return key

    def get_creator_mints(self, wallet_address):
        """
        Retrieves all tokens created by the given wallet.
        Primary: Solscan Pro V2 /v2/account/token/mine
        Fallback: Helius Transaction Tracing
        """
        key = self._get_next_key()
        if not key:
            return self._get_creator_mints_helius_fallback(wallet_address)

        # Note: We use v2.0 endpoint which sometimes requires specific plan perms
        url = f"https://pro-api.solscan.io/v2.0/account/token/mine?address={wallet_address}"
        headers = {"token": key}

        try:
            response = self.session.get(url, headers=headers, timeout=10)
            if response.status_code == 200:
                data = response.json()
                if data.get("success"):
                    return data.get("data", [])
            
            # If 404, 401, or 403, proceed to fallback
            logging.warning(f"Solscan Mine restricted or not found ({response.status_code}). Using Helius fallback.")
            return self._get_creator_mints_helius_fallback(wallet_address)
        except Exception as e:
            logging.error(f"Solscan Mine Error: {e}")
            return self._get_creator_mints_helius_fallback(wallet_address)

    def _get_creator_mints_helius_fallback(self, wallet_address):
        """
        Scans Helius transaction logs for token minting events associated with the wallet.
        """
        from src.config import HELIUS_API_KEY
        if not HELIUS_API_KEY: return []
        
        logging.info(f"🛡️ Helius Trace: Searching for mints by {wallet_address}...")
        url = f"https://api.helius.xyz/v0/addresses/{wallet_address}/transactions?api-key={HELIUS_API_KEY}"
        try:
            resp = self.session.get(url, timeout=12)
            if resp.status_code != 200: return []
            txs = resp.json()
            mints = []
            for tx in txs:
                # TOKEN_MINTING or CREATE_ACCOUNT often signifies a launch
                if tx.get("type") in ["TOKEN_MINTING", "CREATE_ACCOUNT", "UNKNOWN"]:
                    events = tx.get("events", {})
                    token_events = events.get("token", [])
                    for te in token_events:
                        mint = te.get("token")
                        if mint and mint not in mints:
                            mints.append({"address": mint})
            return mints
        except Exception as e:
            logging.error(f"Helius Fallback Error: {e}")
            return []

    def get_token_market_data(self, mint_address):
        """
        Retrieves historical MC and price data for a mint.
        """
        key = self._get_next_key()
        if not key: return None

        url = f"https://pro-api.solscan.io/v2/token/meta?address={mint_address}"
        headers = {"token": key}

        try:
            response = self.session.get(url, headers=headers, timeout=15)
            if response.status_code == 429:
                return self.get_token_market_data(mint_address)
            
            response.raise_for_status()
            data = response.json()
            if data.get("success"):
                return data.get("data", {})
            return None
        except Exception as e:
            logging.error(f"Solscan Meta Error: {e}")
            return None
