import os
import sys
import json
import time
import re
import requests
import post_writer
import generate_live_charts
import pdf_engine

META_FILE = "latest_post_meta.json"
CAROUSEL_PDF = "corp_acuity_linkedin_carousel.pdf"

def escape_linkedin_text(text):
    """
    LinkedIn Posts API parses commentary with Little Text Format.
    Unescaped parentheses, brackets, or angle brackets cause silent truncation.
    Reserved characters: \\ | { } @ [ ] ( ) < > * _ ~
    """
    # 1. Escape literal backslashes first
    text = text.replace("\\", "\\\\")
    # 2. Escape reserved syntax characters without breaking valid hashtags
    reserved = r'([|{}@\[\]()<>\*_~])'
    text = re.sub(reserved, r'\\\1', text)
    # 3. Escape isolated '#' symbols that are not legitimate hashtags
    text = re.sub(r'#(?![a-zA-Z0-9])', r'\#', text)
    return text

def ensure_carousel_and_charts(meta):
    print("[1/3] Verifying and generating setup chart plates...")
    try:
        generate_live_charts.generate_all()
    except Exception as e:
        print(f"[!] Warning generating charts: {e}")

    print("[2/3] Compiling fresh 8-page LinkedIn carousel PDF...")
    pdf_engine.create_linkedin_carousel_pdf(
        regime_status=meta.get('regime_status', 'AMBER: ROTATIONAL ACCUMULATION'),
        posture_box=meta.get('posture_box', ''),
        max_exposure=meta.get('max_exposure', '30% - 60%'),
        pct_above_200=float(meta.get('pct_above_200', 53.1)),
        top_runner=meta.get('top_runner'),
        top_br=meta.get('top_br'),
        top_htf=meta.get('top_htf'),
        top_pp=meta.get('top_pp'),
        top_ls=meta.get('top_ls'),
        dashboard=meta.get('dashboard'),
        macro_events=meta.get('macro_events')
    )
    print(f"[+] Carousel PDF verified: {CAROUSEL_PDF}")

def publish_to_linkedin(pdf_path, meta):
    token = os.getenv("LINKEDIN_ACCESS_TOKEN")
    author_urn = os.getenv("LINKEDIN_AUTHOR_URN")
    if not token or not author_urn:
        print("[LINKEDIN] Credentials not set in environment. Skipping auto-publish.")
        return

    # Generate full post body using dynamic 4-archetype writer
    body, selected_arch = post_writer.build_post_copy(meta)
    
    # Strip raw URL from body to protect reach
    body = body.replace("Daily quantitative terminal feeds and complete CSV datasets: https://corpacuity.co.uk\n\n", "")
    print(f"[*] Posting narrative archetype: {selected_arch}")

    # Escape commentary for LinkedIn Little Text parser
    escaped_commentary = escape_linkedin_text(body)

    headers = {
        "Authorization": f"Bearer {token}",
        "X-Restli-Protocol-Version": "2.0.0",
        "LinkedIn-Version": "202604"
    }

    try:
        print("[+] Initializing document upload with LinkedIn...")
        init_res = requests.post(
            "https://api.linkedin.com/rest/documents?action=initializeUpload",
            headers=headers,
            json={"initializeUploadRequest": {"owner": author_urn}},
            timeout=15
        )
        if init_res.status_code != 200:
            print(f"[!] Document init failed: {init_res.status_code} - {init_res.text}")
            return

        init_data = init_res.json()["value"]
        upload_url = init_data["uploadUrl"]
        document_urn = init_data["document"]

        print("[+] Uploading carousel PDF binary...")
        with open(pdf_path, "rb") as f:
            pdf_bytes = f.read()

        up_headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/pdf"
        }
        up_res = requests.put(upload_url, headers=up_headers, data=pdf_bytes, timeout=60)
        if up_res.status_code not in (200, 201):
            print(f"[!] PDF binary upload failed: {up_res.status_code} - {up_res.text}")
            return

        print("[+] Checking document processing status...")
        doc_id = document_urn.split(":")[-1]
        for _ in range(10):
            time.sleep(2)
            check_res = requests.get(f"https://api.linkedin.com/rest/documents/{doc_id}", headers=headers, timeout=10)
            if check_res.status_code == 200:
                status = check_res.json().get("status")
                if status == "AVAILABLE":
                    print("[+] Document status: AVAILABLE")
                    break
                elif status == "PROCESSING_FAILED":
                    print("[!] LinkedIn document processing failed.")
                    return

        print("[+] Publishing full post commentary and document...")
        payload = {
            "author": author_urn,
            "commentary": escaped_commentary,
            "visibility": "PUBLIC",
            "distribution": {
                "feedDistribution": "MAIN_FEED",
                "targetEntities": [],
                "thirdPartyDistributionChannels": []
            },
            "content": {
                "media": {
                    "title": "Corp Acuity // Market Intelligence Briefing",
                    "id": document_urn
                }
            },
            "lifecycleState": "PUBLISHED",
            "isReshareDisabledByAuthor": False
        }

        post_res = requests.post("https://api.linkedin.com/rest/posts", headers=headers, json=payload, timeout=15)
        if post_res.status_code == 201:
            post_id = post_res.headers.get("x-restli-id", "Unknown")
            print(f"[SUCCESS] Post successfully published to LinkedIn! Post URN: {post_id}")

            if post_id != "Unknown":
                print(f"[+] Dispatching automated first comment to {post_id}...")
                comment_headers = {
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                    "X-Restli-Protocol-Version": "2.0.0",
                    "LinkedIn-Version": "202604"
                }
                comment_payload = {
                    "actor": author_urn,
                    "object": post_id,
                    "message": {
                        "text": "Full Daily Intelligence Package & Active Watchlist:\n- Complete screened candidate watchlist (CSV export)\n- Intraday alert trigger pivots & invalidation stop levels\n- Full Macro Regime Dashboard & Sector Breadth matrix\n\nAccess today\'s dataset & subscribe for daily morning alerts: https://corpacuity.co.uk"
                    }
                }
                time.sleep(2)
                import urllib.parse
                encoded_post_id = urllib.parse.quote(post_id, safe='')
                c_url = f"https://api.linkedin.com/rest/socialActions/{encoded_post_id}/comments"
                c_res = requests.post(c_url, headers=comment_headers, json=comment_payload, timeout=10)
                if c_res.status_code in (200, 201):
                    print("[+] First comment successfully dispatched to LinkedIn!")
                else:
                    print(f"[!] Warning on first comment dispatch: {c_res.status_code} - {c_res.text}")
        else:
            print(f"[!] LinkedIn post creation failed: {post_res.status_code} - {post_res.text}")

    except Exception as e:
        print(f"[!] Error during LinkedIn dispatch: {e}")

def main():
    print("[BROADCAST] Commencing morning publication cycle...")
    if not os.path.exists(META_FILE):
        print(f"[!] Error: {META_FILE} missing.")
        return

    with open(META_FILE, "r", encoding="utf-8") as f:
        meta = json.load(f)

    ensure_carousel_and_charts(meta)
    publish_to_linkedin(CAROUSEL_PDF, meta)
    print("[BROADCAST] Morning broadcast cycle complete.")

if __name__ == "__main__":
    main()