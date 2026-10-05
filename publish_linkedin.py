import os
import sys
import json
import time
import random
import datetime
import requests

META_FILE = "latest_post_meta.json"

def build_dynamic_linkedin_post(regime_status, posture_box, max_exposure, top_br, top_htf, top_pp, top_ls):
    HOOKS = [
        "Most accounts suffer catastrophic drawdowns not from bad stock picks, but from ignoring macro regime shifts.",
        "Quantitative discipline requires sizing capital to broad market health before selecting individual tickers.",
        "Trading without a macro regime circuit breaker is simply guessing in high volatility.",
        "When the index turns choppy, preserving dry powder is as active a decision as buying breakouts."
    ]

    base_tags = ["#SwingTrading", "#RiskManagement"]
    context_pool = []
    if "GREEN" in str(regime_status):
        context_pool += ["#BullMarket", "#Breakouts", "#MomentumTrading"]
    else:
        context_pool += ["#CapitalPreservation", "#MarketBreadth", "#RiskOff"]
    if top_htf:
        context_pool.append("#HighTightFlag")
    if top_pp:
        context_pool.append("#PocketPivot")
    if top_br:
        context_pool.append("#CANSLIM")

    selected_tags = base_tags + random.sample(context_pool, min(2, len(context_pool)))
    tag_line = " ".join(selected_tags)

    body = (
        f"{random.choice(HOOKS)}\n\n"
        f"Our algorithmic screen evaluates the complete US institutional universe nightly, filtering out sentiment in favor of mathematical gates:\n\n"
        f"1. Macro Breadth & Exposure: Establishing whether capital should be deployed or protected before taking risk.\n"
        f"2. Structural Alignment: All candidates must hold above their rising 200-day EMA.\n"
        f"3. Asymmetry Floor: A strict 2:1 reward-to-risk requirement on every setup.\n\n"
        f"Swipe through today's deck for:\n"
        f"• Current Market Regime & Permitted Exposure ({regime_status})\n"
        f"• Universe Breadth (% of stocks > 200 EMA)\n"
        f"• Top setups across Base-Resets, Momentum Bull Flags, Pocket Pivots, and Liquidity Sweeps.\n\n"
        f"Quantitative discipline beats emotional conviction every time.\n\n"
        f"🔗 Access the live terminal, regime analytics & complete watchlists: https://corpacuity.co.uk\n\n"
        f"{tag_line}"
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
