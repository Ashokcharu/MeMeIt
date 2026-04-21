import requests
import json
from src.config import SOLSCAN_API_KEYS

def test():
    key = SOLSCAN_API_KEYS[0]
    token_ca = "ARgVmGrPpsZwvrT3C1p23Pfm5Ew8N7U1bsRDRCcvpump"
    
    # 1. Get Token Meta (including creator)
    meta_url = f"https://pro-api.solscan.io/v2/token/meta?address={token_ca}"
    headers = {"token": key}
    resp = requests.get(meta_url, headers=headers)
    print(f"Meta Status: {resp.status_code}")
    creator = None
    if resp.status_code == 200:
        data = resp.json().get("data", {})
        creator = data.get("creator")
        print(f"Creator: {creator}")
    
    if creator:
        # 2. Get tokens of that creator
        # Try the endpoint I suspect is the correct one for creator history
        mine_url = f"https://pro-api.solscan.io/v2/account/token/mine?address={creator}"
        resp2 = requests.get(mine_url, headers=headers)
        print(f"Mine Status: {resp2.status_code}")
        print(f"Mine Body: {resp2.text[:200]}")

if __name__ == "__main__":
    test()
