import os

class ReportGenerator:
    def __init__(self, output_dir="reports"):
        self.output_dir = output_dir
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)

    def generate_report(self, ca, token_data, score):
        """
        Generates a human-readable markdown report for the token.
        """
        report_content = f"""# MeMeIt Risk Analysis Report: {token_data.get('name', 'Unknown')}
**Contract Address:** `{ca}`
**Final Risk Score:** `{score}%` ({self._get_label(score)})

## On-Chain Summary
- **Chain:** {token_data.get('chain')}
- **Liquidity:** ${token_data.get('liquidity', 0):,.2f}
- **Locked/Burned:** {"Safe (Yes)" if token_data.get('liquidity_locked') else "Risky (No)"}
- **Top 10 Holders:** {token_data.get('holders', {}).get('top_10_percent', 0):.2f}%

## Contract Security
- **Honeypot Check:** {"PASS" if not token_data.get('security', {}).get('is_honeypot') else "FAIL"}
- **Mint Function:** {"Disabled" if not token_data.get('security', {}).get('is_mintable') else "ENABLED (High Risk)"}
- **Owner Privileges:** {"Active" if token_data.get('security', {}).get('owner_privileges') else "Renounced/None"}

## Social Sentiment
- **Sentiment Score:** {token_data.get('social', {}).get('sentiment', 'N/A')}
- **Engagement Quality:** {"High/Organic" if token_data.get('social', {}).get('engagement_ratio', 0) > 0.05 else "Low/Bot-like"}

## Creator History
- **Risk Level:** {token_data.get('creator', {}).get('risk_level', 'Unknown')}

## Analysis Conclusion
{self._get_analysis_text(score, token_data)}
"""
        filename = f"report_{ca}.md"
        path = os.path.join(self.output_dir, filename)
        with open(path, "w") as f:
            f.write(report_content)
        return path

    def _get_label(self, score):
        if score > 80: return "Safe / Low Risk"
        if score > 60: return "Moderate Risk"
        if score > 40: return "High Risk"
        return "Critical Risk / Scam Likely"

    def _get_analysis_text(self, score, data):
        if score > 80:
            return "This token shows strong signs of legitimacy. Liquidity is well-distributed and locked."
        if score < 40:
            return "WARNING: This token has multiple high-risk factors. Investment not recommended."
        return "Exercise caution. While some metrics are positive, there are notable risk factors."
