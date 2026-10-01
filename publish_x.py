import os
import sys
import json
import time
import fitz  # PyMuPDF
import tweepy

META_FILE = "latest_post_meta.json"

def extract_slide_images(pdf_path="daily_market_intelligence.pdf", max_pages=4):
    if not os.path.exists(pdf_path):
        print(f"[X] Error: {pdf_path} not found.")
        return []
    
    doc = fitz.open(pdf_path)
    exported_images = []
    
    # 2x dpi scale ensures crisp text readability on mobile feeds
    pages_to_render = min(len(doc), max_pages)
    for index in range(pages_to_render):
        page = doc[index]
        pixmap = page.get_pixmap(dpi=200)
        image_filename = f"slide_{index + 1}.png"
        pixmap.save(image_filename)
        exported_images.append(image_filename)
        
    doc.close()
    return exported_images

def publish_market_tweet():
    # 1. Load scanner metadata
    if not os.path.exists(META_FILE):
        print(f"[X] Error: {META_FILE} not found. Scanner must run first.")
        sys.exit(1)

    with open(META_FILE, "r") as f:
        meta = json.load(f)

    pdf_path = meta.get("pdf_path", "daily_market_intelligence.pdf")
    regime = meta.get("regime_status", "ACTIVE")
    exposure = meta.get("max_exposure", "N/A")
    pct_above_200 = meta.get("pct_above_200", 0.0)

    # 2. Extract top setup tickers for $CASHTAGS
    tickers = []
    for key in ['top_br', 'top_htf', 'top_pp', 'top_ls']:
        cand = meta.get(key)
        if cand and cand.get('Ticker'):
            tickers.append(f"${cand['Ticker']}")

    seen = set()
    unique_cashtags = [t for t in tickers if not (t in seen or seen.add(t))]
    cashtag_line = " ".join(unique_cashtags) if unique_cashtags else "$SPY $QQQ"

    # 3. Retrieve X API credentials
    api_key = os.getenv("X_API_KEY")
    api_secret = os.getenv("X_API_SECRET")
    access_token = os.getenv("X_ACCESS_TOKEN")
    access_token_secret = os.getenv("X_ACCESS_SECRET")
    bearer_token = os.getenv("X_BEARER_TOKEN")

    if not all([api_key, api_secret, access_token, access_token_secret]):
        print("[X] Missing required credentials. Skipping X broadcast.")
        sys.exit(1)

    # 4. Authenticate APIs (v1.1 for media, v2 for tweet creation)
    auth = tweepy.OAuth1UserHandler(api_key, api_secret, access_token, access_token_secret)
    api_v1 = tweepy.API(auth)

    client_v2 = tweepy.Client(
        bearer_token=bearer_token,
        consumer_key=api_key,
        consumer_secret=api_secret,
        access_token=access_token,
        access_token_secret=access_token_secret
    )

    # 5. Extract slides from PDF
    slide_images = extract_slide_images(pdf_path=pdf_path, max_pages=4)
    if not slide_images:
        print("[X] No slide images extracted. Skipping post.")
        sys.exit(1)

    try:
        # 6. Upload 4 cards
        media_ids = []
        for image_path in slide_images:
            print(f"[X] Uploading {image_path} to X media servers...")
            media = api_v1.media_upload(filename=image_path)
            media_ids.append(media.media_id)

        # 7. Compose dynamic post body
        regime_label = "EXPANSION BULL" if "GREEN" in regime else ("CORRECTION / DEFENSIVE" if "RED" in regime else "ROTATIONAL ACCUMULATION")

        main_post_text = (
            f"CORP ACUITY // DAILY MARKET INTELLIGENCE\n\n"
            f"• Macro Regime: {regime_label}\n"
            f"• Capital Allocation: {exposure}\n"
            f"• Universe Breadth: {pct_above_200}% > 200 EMA\n"
            f"• Focus Setups: {cashtag_line}\n\n"
            f"Morning Intelligence Deck below 🧵👇\n\n"
            f"$SPY $QQQ #StockMarket #Trading #FinTwit"
        )

        print("[X] Publishing main tweet...")
        response = client_v2.create_tweet(text=main_post_text, media_ids=media_ids)
        main_tweet_id = response.data["id"]
        print(f"[X] Main tweet published: https://x.com/i/web/status/{main_tweet_id}")

        # 8. Threaded conversion reply with website link
        time.sleep(4.0)
        reply_post_text = (
            "Access the full institutional slide deck, daily PDF carousel, and screening matrix:\n"
            "🔗 https://corpacuity.co.uk\n\n"
            "Includes complete CAN SLIM scans, pocket pivots, and liquidity metrics across 1,600+ equities."
        )
        client_v2.create_tweet(text=reply_post_text, in_reply_to_tweet_id=main_tweet_id)
        print("[X] Conversion reply thread published successfully.")

    finally:
        # Clean up temporary PNG cards
        for image_path in slide_images:
            if os.path.exists(image_path):
                os.remove(image_path)

if __name__ == "__main__":
    publish_market_tweet()
