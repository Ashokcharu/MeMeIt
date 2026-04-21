import requests
import json
from src.config import HELIUS_API_KEY

def get_mints(address):
    url = f"https://api.helius.xyz/v0/addresses/{address}/transactions?api-key={HELIUS_API_KEY}"
    try:
        resp = requests.get(url, timeout=15)
        if resp.status_code != 200: return []
        txs = resp.json()
        mints = []
        for tx in txs:
            if tx.get("type") == "CREATE_ACCOUNT" or tx.get("type") == "TOKEN_MINTING":
                # Look for token address in instructions
                # Helius v0 format
                events = tx.get("events", {})
                token_events = events.get("token", [])
                for te in token_events:
                    mint = te.get("token")
                    if mint and mint not in mints:
                        mints.append(mint)
        return mints
    except Exception as e:
        print(f"Error: {e}")
        return []

if __name__ == "__main__":
    wallet = "ARgVmGrPpsZwvrT3C1p23Pfm5Ew8N7U1bsRDRCcvpump"
    mints = get_mints(wallet)
    print(f"Found {len(mints)} mints: {mints}")
