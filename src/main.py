import os, sys
# Add project root to sys.path to resolve 'src' package
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.core.on_chain import OnChainAnalyzer
from src.core.social import SocialAnalyzer
from src.core.creator import CreatorTracker
from src.core.scoring import ScoringEngine
from src.core.report import ReportGenerator
from src.core.database import get_connection, init_db

def get_latest_ca():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT ca FROM token_history ORDER BY created_at DESC LIMIT 1")
    res = cursor.fetchone()
    conn.close()
    return res[0] if res else None

def main():
    if len(sys.argv) < 2:
        ca = get_latest_ca()
        if not ca:
            print("Usage: python src/main.py <Contract_Address> or --serve")
            print("No previous research found in database.")
            sys.exit(1)
        print(f"No CA provided. Analyzing latest submission: {ca}")
    else:
        arg = sys.argv[1]
        if arg in ["--serve", "-s"]:
            print("🚀 Starting MeMeIt Service Mode (Telegram Bot)...")
            from src.bot import main as start_bot
            start_bot()
            return
        ca = arg
    
    print(f"--- Starting MeMeIt Research for {ca} ---")
    # Initialize DB (one-time logic for MVP)
    init_db()
    db_conn = get_connection()

    # Layer initialization
    on_chain = OnChainAnalyzer()
    social = SocialAnalyzer()
    creator_track = CreatorTracker(db_conn)
    scoring = ScoringEngine()
    reporter = ReportGenerator()

    print(f"--- Starting MeMeIt Research for {ca} ---")

    # 1. On-chain analysis
    token_data = on_chain.analyze_token(ca)
    if not token_data:
        print("Analysis failed: DexScreener could not find token.")
        return

    # 2. Social Layer (placeholder for demo)
    social_meta = social.get_x_account_metadata("TokenOfficial_X")
    sentiment = social.analyze_sentiment(["Mooning soon!", "Safe dev."])
    token_data["social"] = {
        "sentiment": sentiment,
        "engagement_ratio": 0.08
    }

    # 3. Creator tracking (placeholder for demo)
    creator_wallet = creator_track.identify_creator_wallet(ca)
    token_data["creator"] = {
        "wallet": creator_wallet,
        "risk_level": creator_track.analyze_creator_risk(creator_wallet)
    }

    # 4. Score calculation
    final_score = scoring.calculate_score(token_data, token_data["social"], token_data["creator"])
    
    # 5. Generate report
    report_path = reporter.generate_report(ca, token_data, final_score)

    print("\n--- Research Complete ---")
    print(f"Risk Score: {final_score}%")
    print(f"Report generated: {report_path}")

    db_conn.close()

if __name__ == "__main__":
    main()
