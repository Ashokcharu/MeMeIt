# MeMeIt — Solana Meme Token Intelligence Platform Real-time intelligence dashboard for monitoring Solana meme tokens. Automatically discovers, scores, and categorizes newly graduated tokens from pump.fun and Raydium, providing instant risk analysis and market tracking. ## Architecture Overview
┌──────────────────────────────────────────────────────────────────┐
│                     TOKEN DISCOVERY LAYER                        │
│                                                                  │
│  ┌─────────────────┐  ┌──────────────────┐  ┌────────────────┐  │
│  │ DexScreener API │  │ Helius WebSocket │  │ Telegram Bot   │  │
│  │ (Scraper)       │  │ (WSS Listener)   │  │ (Manual CA)    │  │
│  └────────┬────────┘  └────────┬─────────┘  └───────┬────────┘  │
│           │                    │                     │           │
│           ▼                    ▼                     ▼           │
│       ┌─────────────────────────────────────────────────┐       │
│       │          GRADUATION ENGINE (AI Filter)           │       │
│       │   Validates LP creation, filters junk tokens     │       │
│       └──────────────────────┬──────────────────────────┘       │
└──────────────────────────────┼───────────────────────────────────┘
                               │
                               ▼
┌──────────────────────────────────────────────────────────────────┐
│                     PROCESSING LAYER                             │
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │            Huey Task Queue (Redis-backed)                 │   │
│  │                                                           │   │
│  │  ┌─────────────┐  ┌──────────────┐  ┌─────────────────┐ │   │
│  │  │ On-Chain     │  │ Social       │  │ Risk Scoring    │ │   │
│  │  │ Analyzer     │  │ Analyzer     │  │ Engine          │ │   │
│  │  │ (MC, LP,     │  │ (Twitter,    │  │ (0-100 score,   │ │   │
│  │  │  Holders)    │  │  Followers)  │  │  categorization)│ │   │
│  │  └─────────────┘  └──────────────┘  └─────────────────┘ │   │
│  └──────────────────────────┬───────────────────────────────┘   │
│                              │                                   │
│                              ▼                                   │
│                    ┌──────────────────┐                          │
│                    │   SQLite DB      │                          │
│                    │  (meme_it.db)    │                          │
│                    └────────┬─────────┘                          │
└─────────────────────────────┼────────────────────────────────────┘
                              │
                              ▼
┌──────────────────────────────────────────────────────────────────┐
│                     DELIVERY LAYER                               │
│                                                                  │
│  ┌──────────────┐    ┌──────────────┐    ┌───────────────────┐  │
│  │ Redis Cache  │───▶│ FastAPI      │───▶│ Web Dashboard     │  │
│  │ (10s TTL)    │    │ REST + SSE   │    │ (Vite + Vanilla)  │  │
│  └──────────────┘    └──────────────┘    └───────────────────┘  │
│                                                                  │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │ Telegram Alerts (Trending tokens only, auto-triggered)    │  │
│  └───────────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────────┘
## Tech Stack | Component | Technology | |-----------|-----------| | **Backend API** | Python, FastAPI | | **Task Queue** | Huey (Redis-backed, 2 queues) | | **Database** | SQLite (data/meme_it.db) | | **Cache** | Redis (10s TTL for API responses) | | **Dashboard** | Vanilla JS + CSS, served via Vite | | **Bot** | python-telegram-bot | | **On-Chain Data** | DexScreener API, Helius RPC | | **Risk Analysis** | RugCheck API, Creator history | ## Project Structure
MeMeIt/
├── src/
│   ├── api.py                 # FastAPI server (REST + SSE + Helius webhook)
│   ├── bot.py                 # Telegram bot (manual CA lookup + alerts)
│   ├── workers.py             # Huey background tasks (monitoring, scoring, pruning)
│   ├── graduation_ai.py       # Graduation Engine - validates new tokens
│   ├── graduation_scraper.py  # DexScreener polling scraper
│   ├── graduation_wss.py      # Helius WebSocket listener
│   ├── bootstrap.py           # Resumes monitoring for existing DB tokens
│   ├── config.py              # Environment variables & paths
│   ├── core/
│   │   ├── database.py        # Schema initialization & migrations
│   │   ├── on_chain.py        # Market cap, liquidity, holder analysis
│   │   ├── social.py          # Twitter/X follower analysis
│   │   ├── scoring.py         # Risk scoring engine (0-100)
│   │   ├── rugcheck.py        # Rug pull detection
│   │   ├── creator.py         # Creator wallet history
│   │   ├── helius.py          # Helius RPC client
│   │   └── report.py          # Detailed token reports
│   └── utils/
│       ├── db.py              # SQLite connection pool
│       ├── redis.py           # Redis pub/sub & caching
│       └── telegram.py        # Telegram notification helpers
├── dashboard/
│   ├── index.html             # Dashboard entry point
│   ├── main.js                # Token rendering, search, SSE client
│   └── src/style.css          # Glassmorphic premium UI
├── start.sh                   # One-command startup script
├── requirements.txt           # Python dependencies
└── .gitignore
## Token Lifecycle
Discovery → Graduation Filter → Initial Analysis → Categorization → Continuous Monitoring
### Categories | Category | Description | |----------|------------| | **Graduated** | Newly discovered, awaiting first analysis | | **Gems (24H)** | High-score tokens < 24 hours old with locked liquidity | | **Established** | Mature tokens with strong fundamentals | | **Legacy (+7D)** | Tokens older than 7 days still performing | | **Trending** | Actively gaining MC and momentum | | **Hall of Fame** | Hit 10x or $500k+ market cap | | **Scam Trending** | Flagged as risky but gaining traction | | **Scams** | Failed security checks | | **Rugged** | Confirmed rug pulls | | **Died / Low MC** | Inactive tokens (auto-pruned after 48h) | ## Data Flow & Scalability ### How data reaches the dashboard: 1. **Scrapers** (DexScreener + Helius WSS) discover new tokens 2. **Graduation Engine** validates LP creation and filters junk 3. **Huey workers** analyze on-chain metrics, social data, and risk factors 4. **Results written to SQLite** (data/meme_it.db) 5. **API reads from Redis cache** (10-second TTL) — NOT directly from scrapers 6. **Dashboard fetches from API** and receives live updates via SSE > **Important**: No user request ever triggers a scraper or Helius API call. All 10,000+ concurrent users hit the same Redis cache. The database is queried at most once every 10 seconds. ### Telegram Alerts - Only tokens that **newly enter the Trending tab** trigger a Telegram alert - Each token is alerted **once** (tracked via trending_alerted flag in DB) - Manual CA lookups via Telegram bot always return full details regardless of category ## Setup ### Prerequisites - Python 3.10+ - Redis server - Node.js 18+ (for dashboard) ### Installation
bash
# Clone the repo
git clone https://github.com/your-username/MeMeIt.git
cd MeMeIt

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install Python dependencies
pip install -r requirements.txt

# Install dashboard dependencies
cd dashboard && npm install && cd ..

# Configure environment
cp .env.example .env
# Edit .env with your API keys
### Environment Variables
env
TELEGRAM_BOT_TOKEN=your_bot_token
HELIUS_API_KEY=your_helius_key
AUTHORIZED_USER_IDS=your_telegram_user_id
### Running
bash
# Single command to start everything
./start.sh
This starts: - **2 Huey worker pools** (8 monitoring + 2 intake threads) - **FastAPI server** on port 8000 - **DexScreener scraper** (45s polling) - **Helius WebSocket** listener - **Vite dashboard** on port 5173 - **Telegram bot** (foreground process) ### Dashboard Access Open http://localhost:5173 in your browser. ## API Endpoints | Endpoint | Method | Description | |----------|--------|-------------| | /api/tokens | GET | Returns all monitored tokens (Redis cached) | | /api/token/{ca} | GET | Get detailed data for a specific token | | /api/report/{ca} | GET | Full risk analysis report | | /api/stream | GET | SSE stream for real-time updates | | /api/webhook/helius | POST | Helius webhook receiver | ## License MIT