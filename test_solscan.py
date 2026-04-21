import requests
import json
from src.config import SOLSCAN_API_KEYS

def test():
    key = SOLSCAN_API_KEYS[0]
    wallet = "ARgVmGrPpsZwvrT3C1p23Pfm5Ew8N7U1bsRDRCcvpump" # Creator of ARg...
    url = f"https://pro-api.solscan.io/v2/account/token/mine?address={wallet}"
    headers = {"token": key}
    try:
        resp = requests.get(url, headers=headers, timeout=10)
        print(f"Status: {resp.status_code}")
        print(f"Body: {resp.text[:500]}")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    test()
