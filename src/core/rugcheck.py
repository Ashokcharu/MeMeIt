import requests
import time

class RugCheckClient:
    """
    Client for Layer 1 validation via RugCheck.xyz
    """
    def __init__(self):
        self.base_url = "https://api.rugcheck.xyz/v1"
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (MeMeIt Smart Dashboard)"
        })

    def get_token_report(self, ca):
        """
        Fetches safety data for a token CA.
        """
        # Supports Solana primarily.
        try:
            # RugCheck API endpoint for tokens
            url = f"{self.base_url}/tokens/{ca}/report"
            resp = self.session.get(url, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                score = data.get("score", 1000)
                risks = [r.get("name") for r in data.get("risks", [])]
                is_locked = any("locked" in r.get("name", "").lower() for r in data.get("risks", []))
                
                # If score is very low, it's safe and likely "Verified/Burnt" LP
                if score < 100:
                    is_locked = True
                
                # Deep Metadata Extraction
                holders_count = data.get("totalHolders", 0)
                
                # Extract Socials from RugCheck's internal meta or URI
                socials = {}
                meta = data.get("tokenMeta", {})
                uri = meta.get("uri")
                
                if uri:
                    try:
                        meta_resp = self.session.get(uri, timeout=5)
                        if meta_resp.status_code == 200:
                            meta_json = meta_resp.json()
                            if meta_json.get("twitter"): socials["twitter"] = meta_json["twitter"]
                            if meta_json.get("telegram"): socials["telegram"] = meta_json["telegram"]
                            if meta_json.get("website"): socials["website"] = meta_json["website"]
                    except: pass

                return {
                    "is_safe": score < 500,
                    "score": score,
                    "risks": risks,
                    "liquidity_locked": is_locked,
                    "total_holders": holders_count,
                    "socials": socials,
                    "name": meta.get("name"),
                    "symbol": meta.get("symbol")
                }
        except Exception as e:
            print(f"RugCheck Error: {e}")
        return None

if __name__ == "__main__":
    # Test with a known CA
    client = RugCheckClient()
    report = client.get_token_report("9gYEWVXJG5cYZAkThuTXB6LP1JELg9GKAYJk89Gepump")
    print(f"RugCheck Report: {report}")
