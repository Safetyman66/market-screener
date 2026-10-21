import os
import sys
import json
import time
import random
import datetime
import requests

META_FILE = "latest_post_meta.json"

def build_dynamic_linkedin_post(regime_status, posture_box, max_exposure, top_br, top_htf, top_pp, top_ls, pct_above_200=53.1, top_runner=None):
    # Dynamic Candidate Ticker Highlights
    active_tickers = [c['Ticker'] for c in [top_br, top_htf, top_pp, top_ls] if c and c.get('Ticker')]
    ticker_str = ", ".join([f"${t}" for t in active_tickers[:4]]) if active_tickers else "Screened Candidates"

    # Data-Driven Institutional Hooks (Appears before '...see more')
    HOOKS = [
        f"{pct_above_200:.1f}% of our US institutional universe is holding above its 200 EMA.\n\nWhen breadth consolidates near the median, capital allocation is governed by strict regime exposure ceilings rather than momentum pursuit.",
        f"Macro Regime Posture: {regime_status} (Exposure Model: {max_exposure}).\n\nPreserving capital during rotational absorption is an active mathematical position. Systematic screening filters out emotional bias before individual tickers are considered.",
        f"Systematic Asymmetry: Screening across the complete US equity universe isolates setups with >= 2.0R geometry.\n\nCurrent regime breadth ({pct_above_200:.1f}% > 200 EMA) throttles model exposure to {max_exposure}."
    ]

    hook = random.choice(HOOKS)

    # Dynamic Case Study Mention
    runner_mention = ""
    if top_runner and top_runner.get('ticker') and top_runner.get('max_gain_pct', 0) > 0:
        runner_mention = f"\n- Audited 5-Day Case Study: ${top_runner['ticker']} (+{top_runner['max_gain_pct']}% peak expansion / {top_runner.get('r_multiple', '1.4')}R)"

    body = (
        f"{hook}\n\n"
        f"Our nightly quantitative engine evaluates US equities through three non-negotiable risk gates:\n\n"
        f"1. Regime Sizing: Capital deployment scaled to 200 EMA breadth health ({max_exposure}).\n"
        f"2. Structural Baseline: Zero tolerance for negative drift; price must respect long-term moving averages.\n"
        f"3. Asymmetry Hurdle: Strict >= 2.0R reward-to-risk floor on every candidate.\n\n"
        f"Swipe through today's 8-page briefing deck for:\n"
        f"- System Regime Cockpit & Cross-Asset Liquidity Radar\n"
        f"- Full Candlestick Setup Anatomies ({ticker_str}){runner_mention}\n"
        f"- Mechanical Governance Rules & Pursuit Ceilings (+2.5%)\n\n"
        f"Daily quantitative terminal feeds and complete CSV datasets: https://corpacuity.co.uk\n\n"
        f"---\n"
        f"Purely educational research & systematic quantitative modeling. Not investment advice or financial promotion.\n\n"
        f"#QuantitativeFinance #MarketRegime #SystematicTrading #RiskManagement #Macroeconomics"
    )
    return body
def publish_to_linkedin(pdf_path, regime_status, posture_box, max_exposure, pct_above_200, top_br, top_htf, top_pp, top_ls):
    token = os.getenv("LINKEDIN_ACCESS_TOKEN")
    author_urn = os.getenv("LINKEDIN_AUTHOR_URN")
    if not token or not author_urn:
        print("[LINKEDIN] Credentials not set in environment. Skipping auto-publish.")
        return

    headers = {
        "Authorization": f"Bearer {token}",
        "X-Restli-Protocol-Version": "2.0.0",
        "LinkedIn-Version": "202604"
    }

    try:
        init_res = requests.post(
            "https://api.linkedin.com/rest/documents?action=initializeUpload",
            headers=headers,
            json={"initializeUploadRequest": {"owner": author_urn}},
            timeout=15
        )
        if init_res.status_code not in [200, 201]:
            print(f"[LINKEDIN] Init Upload Failed ({init_res.status_code}): {init_res.text}")
            return

        init_data = init_res.json()["value"]
        upload_url = init_data["uploadUrl"]
        doc_urn = init_data["document"]

        with open(pdf_path, "rb") as f:
            pdf_bytes = f.read()

        r_upload = requests.put(
            upload_url,
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/pdf"},
            data=pdf_bytes,
            timeout=45
        )
        if r_upload.status_code not in [200, 201]:
            print(f"[LINKEDIN] File Stream Failed ({r_upload.status_code}): {r_upload.text}")
            return

        print("[LINKEDIN] Document uploaded. Pausing 6 seconds for LinkedIn media processing...")
        time.sleep(6.0)

        commentary = build_dynamic_linkedin_post(
            regime_status,
            posture_box,
            max_exposure,
            top_br,
            top_htf,
            top_pp,
            top_ls
        )

        post_payload = {
            "author": author_urn,
            "commentary": commentary,
            "visibility": "PUBLIC",
            "distribution": {
                "feedDistribution": "MAIN_FEED",
                "targetEntities": [],
                "thirdPartyDistributionChannels": []
            },
            "lifecycleState": "PUBLISHED",
            "content": {
                "media": {
                    "title": f"CorpAcuity Market Intel // {datetime.date.today().strftime('%b %d, %Y')}",
                    "id": doc_urn
                }
            }
        }

        create_resp = requests.post(
            "https://api.linkedin.com/rest/posts",
            headers=headers,
            json=post_payload,
            timeout=20
        )

        post_urn = create_resp.headers.get("x-restli-id") or create_resp.json().get("id")
        if create_resp.status_code in [200, 201] and post_urn:
            print("[LINKEDIN] Successfully published carousel document to feed.")
        else:
            print(f"[LINKEDIN] Post Publish Failed ({create_resp.status_code}): {create_resp.text}")

    except Exception as e:
        print(f"[LINKEDIN] Automation Error: {e}")

def main():
    if not os.path.exists(META_FILE):
        print(f"[ERROR] {META_FILE} not found. The overnight scanner must run before publishing.")
        sys.exit(1)

    with open(META_FILE, "r", encoding="utf-8") as f:
        meta = json.load(f)

    pdf_path = meta.get("pdf_path", "daily_market_intelligence.pdf")

    if not os.path.exists(pdf_path):
        print(f"[ERROR] PDF '{pdf_path}' not found. Cannot publish.")
        sys.exit(1)

    print(f"[BROADCAST] Commencing morning publication of {pdf_path} to LinkedIn...")

    publish_to_linkedin(
        pdf_path=pdf_path,
        regime_status=meta.get("regime_status", "UNKNOWN"),
        posture_box=meta.get("posture_box", "SELECTIVE"),
        max_exposure=meta.get("max_exposure", "N/A"),
        pct_above_200=meta.get("pct_above_200", 0.0),
        top_br=meta.get("top_br"),
        top_htf=meta.get("top_htf"),
        top_pp=meta.get("top_pp"),
        top_ls=meta.get("top_ls")
    )

    print("[BROADCAST] Morning broadcast cycle complete.")

if __name__ == "__main__":
    main()
