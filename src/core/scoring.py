import time

class ScoringEngine:
    def calculate_score(self, token_data, holder_growth=0.0, long_term_growth=0.0, creator_data=None):
        """
        Calculates a 0-100 score using a 2-Phase approach:
        Phase 1: Creator Trust (Gateway)
        Phase 2: Community Growth & On-Chain metrics
        """
        score = 0
        breakdown = []
        is_zombie = False
        creator_data = creator_data or {}

        # --- Phase 1: Creator Trust (Gateway) ---
        creator_score, creator_breakdown = self._score_creator_trust(token_data, creator_data)
        score += creator_score
        breakdown.extend(creator_breakdown)

        # --- Phase 2: Community & Momentum ---
        
        # 1. Liquidity Locked (+20)
        if token_data.get("liquidity_locked"):
            score += 20
            breakdown.append("+20: Liquidity Locked ✅ (3-Layer Verified)")
        else:
            breakdown.append(" 0: Liquidity NOT Locked / Unverified ⚠️")

        # 2. Momentum & Holder Growth (+25)
        # ── CONTINUOUS SCALING (Phase 64) ───────────────────────────────────
        # Use linear scaling instead of discrete buckets to avoid "Cliff Drops"
        effective_growth = max(holder_growth or 0.0, long_term_growth or 0.0)
        
        # Scale: 0% -> 0 pts, 1% -> 5 pts, 5% -> 25 pts (capped at 25)
        momentum_points = min(25.0, effective_growth * 5.0)
        score += momentum_points
        
        # Descriptive text based on thresholds (Phase 65: .2f precision)
        if effectiveness := (effective_growth > 5.0):
            breakdown.append(f"+{momentum_points:.1f}: High Momentum ({effective_growth:.2f}%) 🚀")
        elif effective_growth > 0.5:
            breakdown.append(f"+{momentum_points:.1f}: Steady Growth ({effective_growth:.2f}%) 📈")
        elif effective_growth > 0:
            breakdown.append(f"+{momentum_points:.1f}: Consistent Base ({effective_growth:.2f}%) 📊")
        else:
            status = "Warming up... ⏳" if (long_term_growth or 0) == 0 else "Static Holder Base"
            breakdown.append(f" 0: {status}")
        
        if (long_term_growth or 0) < -5.0:
            is_zombie = True
        # ───────────────────────────────────────────────────────────────────🚩🚩🚩🚩

        # 3. Social Presence (+15)
        _links = token_data.get("links", {}) or {}
        has_social = bool(
            token_data.get("x_link") or token_data.get("tg_link") or
            _links.get("twitter") or _links.get("telegram")
        )
        if has_social:
            score += 15
            breakdown.append("+15: Active Social Presence (X/TG) 🌐")
        else:
            breakdown.append(" 0: No Social Links Found 🌑")

        # 4. Distribution & Whale Watch (+20)
        top_10 = token_data.get("holders", {}).get("top_10_percent", 100.0)
        if top_10 < 30.0:
            score += 20
            breakdown.append(f"+20: Professional Distribution ({top_10:.1f}%) 💎")
        elif top_10 < 50.0:
            score += 10
            breakdown.append(f"+10: Moderate Distribution ({top_10:.1f}%)")
        else:
            breakdown.append(f" 0: High Concentration ({top_10:.1f}%) ⚠️")

        # 5. Trusted Creator Bonus (+20)
        is_trusted = creator_data.get("is_followed_by_user") or creator_data.get("is_verified_creator")
        reputation = creator_data.get("reputation", "neutral")
        
        if reputation == "trusted":
            score += 30
            breakdown.append("+30: TRUSTED DEV: Previous 10x Success Found ✅")
        elif reputation == "scammer":
            score -= 50
            breakdown.append("-50: SCAMMER: Multiple Rug History Found 🚨")
            
        if is_trusted:
            score += 20
            breakdown.append("+20: In your Trusted X Network ✅")

        # Security Checks (Hard Penalties)
        sec = token_data.get("security", {})
        if sec.get("is_honeypot"):
            return (0.0, ["-100: HONEYPOT DETECTED 🚨"], False)
        
        if sec.get("is_mintable"):
            score -= 15
            breakdown.append("-15: Mintable (High Risk) ⚠️")
        
        final = float(round(max(0, min(100, score))))
        return (final, breakdown, is_zombie)

    def _score_creator_trust(self, token_data, creator_data):
        """
        Calculates Phase 1: Creator Credibility.
        Impacts the total score by -30 to +15.
        """
        points = 0
        lines = []
        social = creator_data.get("social_metadata", {})
        followers = social.get("followers", 0)
        age_days = social.get("account_age_days", 0)
        is_verified = social.get("is_verified", False)
        
        # Data Guard: Unknown followers is neutral
        if followers == 0 and not token_data.get("x_link"):
            return 0, [" 0: Creator: Unverified (No X Link)"]
        if followers == 0:
            return 0, [" 0: Creator: Data Pending (Scraper Sync)"]

        # 1. Account Age vs Token Launch
        # If account was created AFTER the token launch, it's a huge red flag
        pair_created_at = token_data.get("pair_created_at")
        if pair_created_at and age_days > 0:
            account_created_at = time.time() - (age_days * 86400)
            if account_created_at > pair_created_at + 3600: # 1 hour buffer
                points -= 20
                lines.append("-20: SCAMMER SETUP: X account created AFTER token 🚨")
            elif age_days < 1:
                points -= 10
                lines.append("-10: RED FLAG: New Deployer / Account <24h 🌑")
            elif age_days < 7:
                points -= 5
                lines.append("-5: Creator: Brand New Account (<7d) ⚠️")
            elif age_days < 30:
                points -= 5
                lines.append("-5: Creator: Recent Account (<30d)")
            elif age_days > 180:
                points += 5
                lines.append("+5: Creator: Established Account (>6mo) ✅")
        
        # 2. Follower Tiers (only if verified scraped)
        if followers > 10000:
            points += 10
            lines.append(f"+10: Creator: Major Influencer ({followers:,} followers)")
        elif followers > 1000:
            points += 5
            lines.append(f"+5: Creator: Mid-tier Presence ({followers:,} followers)")
        elif followers < 20:
            points -= 15
            lines.append("-15: RED FLAG: Suspiciously low followers (<20) 🌑")
        elif followers < 100:
            points -= 5
            lines.append("-5: Creator: Very low follower count")

        # 3. Velocity / Trending (Placeholder for EMA check)
        velocity = social.get("velocity", 0)
        if velocity > 100:
            points += 5
            lines.append("+5: Creator: Viral Engagement 🚀")
        elif velocity < -10:
            points -= 10
            lines.append("-10: Creator: Losing Follower Momentum 📉")

        # 4. Verified Status
        if is_verified:
            points += 5
            lines.append("+5: Creator: Verified Identity ⭐")

        return points, lines

if __name__ == "__main__":
    pass
