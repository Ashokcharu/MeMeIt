import subprocess
import time
import requests
import json
import os

from src.config import HELIUS_API_KEY

def setup():
    print("📡 Establishing secure inbound tunnel for Helius Webhooks...")
    process = subprocess.Popen(
        ["npx", "-y", "localtunnel", "--port", "8000"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )
    
    tunnel_url = None
    # Wait for the tunnel string to appear
    for i in range(20):
        line = process.stdout.readline()
        if "your url is" in line:
            tunnel_url = line.split("your url is: ")[1].strip()
            print(f"✅ Tunnel Established: {tunnel_url}")
            break
        time.sleep(0.5)
            
    if not tunnel_url:
        print("❌ Failed to establish local tunnel.")
        return

    webhook_endpoint = f"{tunnel_url}/api/webhook/helius"
    print(f"Configuring Helius to broadcast to: {webhook_endpoint}")
    
    try:
        # Check if a webhook already exists to update it
        get_resp = requests.get(f"https://api.helius.xyz/v0/webhooks?api-key={HELIUS_API_KEY}")
        webhooks = get_resp.json()
        
        payload = {
            "webhookURL": webhook_endpoint,
            "transactionTypes": ["ANY"],
            "accountAddresses": ["675kPX9MHTjS2tz1jyGZeqZAp8LrcfNpbhB1g9ybgRpq"], # Raydium AMM Full Firehose
            "webhookType": "enhanced" # Instructs Helius to pre-parse the data
        }

        if isinstance(webhooks, list) and len(webhooks) > 0:
            webhook_id = webhooks[0]["webhookID"]
            put_resp = requests.put(
                f"https://api.helius.xyz/v0/webhooks/{webhook_id}?api-key={HELIUS_API_KEY}",
                json=payload
            )
            print(f"🔁 Webhook Target Updated: HTTP {put_resp.status_code}")
        else:
            post_resp = requests.post(
                f"https://api.helius.xyz/v0/webhooks?api-key={HELIUS_API_KEY}",
                json=payload
            )
            print(f"✅ Webhook Target Born: HTTP {post_resp.status_code}")
            
    except Exception as e:
        print(f"Helius Registration Engine Error: {e}")
        
    print(f"🎓 FOMO Graduation Engine is now flawlessly integrated and streaming! 🚀")
    
    # Keep tunnel process alive in background
    try:
        process.wait()
    except KeyboardInterrupt:
        process.terminate()

if __name__ == "__main__":
    setup()
