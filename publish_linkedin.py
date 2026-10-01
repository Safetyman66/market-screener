import os
import sys
import json
from scanner import publish_to_linkedin

META_FILE = "latest_post_meta.json"

def main():
    # 1. Verify metadata exists from overnight scan
    if not os.path.exists(META_FILE):
        print(f"[ERROR] {META_FILE} not found. The overnight scanner must run before publishing.")
        sys.exit(1)

    with open(META_FILE, "r") as f:
        meta = json.load(f)

    pdf_path = meta.get("pdf_path", "daily_market_intelligence.pdf")
    
    # 2. Verify carousel PDF exists
    if not os.path.exists(pdf_path):
        print(f"[ERROR] PDF '{pdf_path}' not found. Cannot publish.")
        sys.exit(1)

    print(f"[BROADCAST] Commencing morning publication of {pdf_path} to LinkedIn...")
    
    # 3. Publish carousel and trigger dynamic first comment
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
