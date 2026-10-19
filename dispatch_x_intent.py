import os
import sys
import json
import urllib.parse
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

META_FILE = "latest_post_meta.json"

def format_num(val, prefix="", suffix="", decimals=2):
    if val is None:
        return "N/A"
    try:
        num = float(val)
        return f"{prefix}{num:.{decimals}f}{suffix}"
    except (ValueError, TypeError):
        return f"{prefix}{val}{suffix}"

def clean_zacks(rank_val):
    if not rank_val:
        return "N/A"
    rank_str = str(rank_val).strip()
    return rank_str if rank_str.startswith("#") else f"#{rank_str}"

def format_setup_block(cand, category_name):
    ticker = cand.get('Ticker', 'TICKER')
    pivot = format_num(cand.get('Pivot_Trigger'), prefix="$")
    stop = format_num(cand.get('Stop_Loss'), prefix="$")
    risk = format_num(cand.get('Risk_%'), suffix="%")
    asymmetry = format_num(cand.get('R_Ratio'), suffix="R")
    zacks = clean_zacks(cand.get('Zacks_Rank'))
    earnings = cand.get('Earnings_Risk', 'SAFE')

    return (
        f"• Pivot Trigger: {pivot}\n"
        f"• Tactical Stop: {stop} ({risk} risk)\n"
        f"• Modeled Asymmetry: {asymmetry}\n"
        f"• Catalyst: Zacks {zacks}\n"
        f"• Event Risk: {earnings}"
    )

def build_thread_payloads():
    if not os.path.exists(META_FILE):
        print(f"[X INTENT] {META_FILE} not found.")
        sys.exit(1)

    with open(META_FILE, "r", encoding="utf-8") as f:
        meta = json.load(f)

    regime = meta.get("regime_status", "ACTIVE")
    exposure = meta.get("max_exposure", "30% - 60%")
    pct_above_200 = meta.get("pct_above_200", 0.0)

    regime_label = "EXPANSION BULL" if "GREEN" in regime else ("CORRECTION / DEFENSIVE" if "RED" in regime else "ROTATIONAL ACCUMULATION")

    # Gather available setups across categories
    setup_slots = [
        ('top_br', 'Base-Reset Inflection'),
        ('top_htf', 'High-Tight Flag'),
        ('top_pp', 'Pocket Pivot'),
        ('top_ls', 'Liquidity Sweep')
    ]

    active_setups = []
    for key, label in setup_slots:
        cand = meta.get(key)
        if cand and cand.get('Ticker'):
            active_setups.append((cand, label))

    focus_tickers = meta.get("focus_tickers", [])
    seen = set()
    cashtags = [f"${t}" for t in focus_tickers if not (t in seen or seen.add(t))]
    radar_str = " ".join(cashtags) if cashtags else "$SPY $QQQ"

    thread_posts = []

    # 1. ANCHOR TWEET (Root Tweet)
    if active_setups:
        primary_cand, primary_label = active_setups[0]
        p_ticker = primary_cand.get('Ticker')
        p_block = format_setup_block(primary_cand, primary_label)

        t1_text = (
            f"CORP ACUITY // ASYMMETRY SCAN\n\n"
            f"Regime: {regime_label} (Exposure: {exposure})\n"
            f"Breadth: {pct_above_200}% > 200 EMA\n\n"
            f"Top Asymmetric Setup: ${p_ticker} ({primary_label})\n"
            f"{p_block}\n\n"
            f"Rule: Void entry if opened >2.5% past pivot.\n"
            f"Secondary setups in thread 🧵👇\n\n"
            f"$SPY $QQQ #FinTwit #Trading"
        )
    else:
        t1_text = (
            f"CORP ACUITY // ASYMMETRY SCAN\n\n"
            f"Regime: {regime_label} (Exposure: {exposure})\n"
            f"Breadth: {pct_above_200}% > 200 EMA\n\n"
            f"Radar Focus: {radar_str}\n\n"
            f"Rule: Strict 2.0R asymmetry floor across all candidates.\n"
            f"Secondary setups in thread 🧵👇\n\n"
            f"#FinTwit #Trading"
        )
    thread_posts.append({
        "title": "Tweet 1: Root Anchor Post",
        "role": "Post this as your main tweet (attach Card 1 & Card 2)",
        "text": t1_text,
        "url": f"https://x.com/intent/tweet?text={urllib.parse.quote(t1_text)}"
    })

    # 2. SUBSEQUENT SETUPS (Thread Replies)
    for i, (cand, label) in enumerate(active_setups[1:3], start=2):
        ticker = cand.get('Ticker')
        block = format_setup_block(cand, label)
        proto = cand.get('Execution_Protocol', 'STANDARD RUNWAY: Full swing leeway.')

        reply_text = (
            f"Setup #{i}: ${ticker} ({label})\n\n"
            f"{block}\n\n"
            f"Directive: {proto}"
        )
        thread_posts.append({
            "title": f"Tweet {i}: Thread Reply (Setup #{i})",
            "role": f"Reply directly to Tweet 1 (attach Card {i+1})",
            "text": reply_text,
            "url": f"https://x.com/intent/tweet?text={urllib.parse.quote(reply_text)}"
        })

    # 3. FINAL THREAD CLOSER (CTA + Link)
    closer_num = len(thread_posts) + 1
    t_close_text = (
        f"Execution Governance & Complete Terminal Blotter:\n\n"
        f"Full quantitative breakdowns, interactive PDF carousel, and dynamic risk directives:\n\n"
        f"👉 corpacuity.co.uk/intel.html"
    )
    thread_posts.append({
        "title": f"Tweet {closer_num}: Final Thread Reply (Terminal Link)",
        "role": "Reply to the last tweet in the thread to protect main reach",
        "text": t_close_text,
        "url": f"https://x.com/intent/tweet?text={urllib.parse.quote(t_close_text)}"
    })

    return thread_posts

def send_dispatch_email(thread_posts):
    smtp_host = os.getenv("SMTP_HOST", "smtp.gmail.com")
    smtp_port = int(os.getenv("SMTP_PORT", "587"))
    smtp_user = os.getenv("SMTP_USER")
    smtp_pass = os.getenv("SMTP_PASS")
    recipient = os.getenv("ALERT_RECIPIENT", "ajmcneilster@gmail.com")

    if not smtp_user or not smtp_pass:
        print("[X INTENT] SMTP credentials not provided. Printing thread intents to log:\n")
        for p in thread_posts:
            print(f"--- {p['title']} ---")
            print(p['url'])
            print(p['text'])
            print()
        return

    msg = MIMEMultipart("alternative")
    msg["Subject"] = "🚀 Today's X Morning Post Ready (1-Click Intent)"
    msg["From"] = f"Corp Acuity Screener <{smtp_user}>"
    msg["To"] = recipient

    card_base = "https://corpacuity.co.uk/x_cards"

    # Build HTML blocks for each tweet in the thread
    cards_html = ""
    for idx, item in enumerate(thread_posts, start=1):
        btn_label = "1. Post Root Anchor Tweet ➔" if idx == 1 else f"{idx}. Pre-fill Thread Reply #{idx} ➔"
        cards_html += f"""
        <div style="background: #0f172a; border: 1px solid #1e293b; border-radius: 8px; padding: 16px; margin-bottom: 20px;">
          <h3 style="margin: 0 0 6px 0; font-size: 15px; color: #38bdf8;">{item['title']}</h3>
          <p style="margin: 0 0 12px 0; font-size: 12px; color: #94a3b8;">{item['role']}</p>
          <div style="text-align: left; margin-bottom: 12px;">
            <a href="{item['url']}" target="_blank" style="display: inline-block; background-color: #38bdf8; color: #0b0f19 !important; font-weight: bold; padding: 10px 18px; border-radius: 6px; text-decoration: none; font-size: 14px;">{btn_label}</a>
          </div>
          <pre style="background-color: #070a12; padding: 12px; border-radius: 6px; white-space: pre-wrap; font-family: monospace; font-size: 12px; color: #cbd5e1; border: 1px solid #334155; margin: 0;">{item['text']}</pre>
        </div>
        """

    html_body = f"""
    <!DOCTYPE html>
    <html>
    <head>
      <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; background-color: #0b0f19; color: #f8fafc; padding: 20px; }}
        .wrapper {{ background-color: #161e2e; border: 1px solid #1e293b; border-radius: 12px; padding: 24px; max-width: 640px; margin: 0 auto; }}
        a.img-link {{ color: #38bdf8; text-decoration: underline; margin-right: 12px; font-size: 13px; }}
      </style>
    </head>
    <body>
      <div class="wrapper">
        <h2 style="color: #38bdf8; margin-top: 0; font-size: 20px;">Corp Acuity // Morning X Thread Dispatch</h2>
        <p style="font-size: 13px; color: #94a3b8; margin-bottom: 20px;">
          Today's scan is rendered. Post Tweet #1 first, then use the subsequent buttons to reply to your own tweet as a high-retention thread.
        </p>

        {cards_html}

        <div style="margin-top: 20px; padding: 12px; background: #0f172a; border-radius: 8px; border: 1px solid #1e293b;">
          <p style="font-size: 13px; color: #94a3b8; margin: 0 0 8px 0;"><strong>Visual Assets (Download to attach):</strong></p>
          <p style="margin: 0;">
            <a class="img-link" href="{card_base}/card_1.png" target="_blank">Card 1 (Regime)</a>
            <a class="img-link" href="{card_base}/card_2.png" target="_blank">Card 2 (Radar)</a>
            <a class="img-link" href="{card_base}/card_3.png" target="_blank">Card 3 (Setup 1)</a>
            <a class="img-link" href="{card_base}/card_4.png" target="_blank">Card 4 (Setup 2)</a>
          </p>
        </div>

        <hr style="border: 0; border-top: 1px solid #1e293b; margin: 24px 0;">
        <p style="font-size: 11px; color: #64748b; margin: 0;">Automated pipeline running via GitHub Actions on corpacuity.co.uk</p>
      </div>
    </body>
    </html>
    """

    msg.attach(MIMEText(html_body, "html"))

    try:
        server = smtplib.SMTP(smtp_host, smtp_port)
        server.starttls()
        server.login(smtp_user, smtp_pass)
        server.sendmail(smtp_user, recipient, msg.as_string())
        server.quit()
        print(f"[X INTENT] Successfully emailed multi-part thread intent to {recipient}")
    except Exception as e:
        print(f"[X INTENT] Failed to send email: {e}")

if __name__ == "__main__":
    thread = build_thread_payloads()
    send_dispatch_email(thread)