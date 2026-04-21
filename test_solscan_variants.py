import requests
from src.config import SOLSCAN_API_KEYS

def test_url(url, key):
    headers = {"token": key}
    try:
        resp = requests.get(url, headers=headers, timeout=10)
        print(f"URL: {url} -> Status: {resp.status_code}")
        if resp.status_code == 200:
            print(f"Success! Body contains: {resp.text[:200]}")
            return True
    except: pass
    return False

if __name__ == "__main__":
    key = SOLSCAN_API_KEYS[0]
    wallet = "ARgVmGrPpsZwvrT3C1p23Pfm5Ew8N7U1bsRDRCcvpump"
    variants = [
        f"https://pro-api.solscan.io/v2/token/mine?address={wallet}",
        f"https://pro-api.solscan.io/v2/account/tokens/mine?address={wallet}",
        f"https://pro-api.solscan.io/v2/token/list?creator={wallet}",
        f"https://pro-api.solscan.io/v2/account/token/mine?address={wallet}", # This was the 404
        f"https://pro-api.solscan.io/v2/account/mines?address={wallet}"
    ]
    for v in variants:
        if test_url(v, key): break
