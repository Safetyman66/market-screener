import os
import sys
import json
import urllib.parse
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

META_FILE = "latest_post_meta.json"

def build_x_intent_url():
    if not os.path.exists(META_FILE):
        print(f"[X INTENT] {META_FILE} not found.")
        sys.exit(1)

    with open(META_FILE, "r") as f:
        meta = json.load(f)

    regime = meta.get("regime_status", "ACTIVE")
    exposure = meta.get("max_exposure", "N/A")
    pct_above_200 = meta.get("pct_above_200", 0.0)

    # Extract dynamic Focus Cashtags
    tickers = []
    for key in ['top_br', 'top_htf', 'top_pp', 'top_ls']:
        cand = meta.get(key)
        if cand and cand.get('Ticker'):
            tickers.append(f"${cand['Ticker']}")

    seen = set()
    unique_cashtags = [t for t in tickers if not (t in seen or seen.add(t))]
    cashtag_line = " ".join(unique_cashtags) if unique_cashtags else "$SPY $QQQ"

    regime_label = "EXPANSION BULL" if "GREEN" in regime else ("CORRECTION / DEFENSIVE" if "RED" in regime else "ROTATIONAL ACCUMULATION")

    # Clean text payload (no outbound link on main post to protect reach)
    post_text = (
        f"CORP ACUITY // DAILY MARKET INTELLIGENCE\n\n"
        f"• Macro Regime: {regime_label}\n"
        f"• Capital Allocation: {exposure}\n"
        f"• Universe Breadth: {pct_above_200}% > 200 EMA\n"
        f"• Focus Setups: {cashtag_line}\n\n"
        f"4-Card Morning Intelligence Deck below 🧵👇\n\n"
        f"$SPY $QQQ #FinTwit #Trading #StockMarket"
    )

    encoded_text = urllib.parse.quote(post_text)
    intent_url = f"https://x.com/intent/tweet?text={encoded_text}"
    return intent_url, post_text

def send_dispatch_email(intent_url, post_text):
    smtp_host = os.getenv("SMTP_HOST", "smtp.gmail.com")
    smtp_port = int(os.getenv("SMTP_PORT", "587"))
    smtp_user = os.getenv("SMTP_USER")
    smtp_pass = os.getenv("SMTP_PASS")
    recipient = os.getenv("ALERT_RECIPIENT", "ajmcneilster@gmail.com")

    if not smtp_user or not smtp_pass:
        print("[X INTENT] SMTP credentials not provided in environment. Printing intent link to log:")
        print(f"\n{intent_url}\n")
        return

    msg = MIMEMultipart("alternative")
    msg["Subject"] = "🚀 Today's X Morning Post Ready (1-Click Intent)"
    msg["From"] = f"Corp Acuity Screener <{smtp_user}>"
    msg["To"] = recipient

    card_base = "https://corpacuity.co.uk/x_cards"
    
    html_body = f"""
    <!DOCTYPE html>
    <html>
    <head>
      <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; background-color: #0b0f19; color: #f8fafc; padding: 20px; }}
        .card {{ background-color: #161e2e; border: 1px solid #1e293b; border-radius: 12px; padding: 24px; max-width: 600px; margin: 0 auto; }}
        .btn {{ display: inline-block; background-color: #38bdf8; color: #0b0f19 !important; font-weight: bold; padding: 14px 28px; border-radius: 8px; text-decoration: none; font-size: 16px; margin: 20px 0; }}
        pre {{ background-color: #0f172a; padding: 16px; border-radius: 8px; white-space: pre-wrap; font-family: monospace; font-size: 13px; color: #94a3b8; border: 1px solid #1e293b; }}
        .card-preview {{ margin-top: 15px; font-size: 13px; color: #94a3b8; }}
        a.img-link {{ color: #38bdf8; text-decoration: underline; margin-right: 12px; }}
      </style>
    </head>
    <body>
      <div class="card">
        <h2 style="color: #38bdf8; margin-top: 0;">Corp Acuity // X Morning Dispatch</h2>
        <p>Your morning institutional scan has rendered and deployed. Click below to launch X with today's copy pre-filled:</p>
        
        <div style="text-align: center;">
          <a href="{intent_url}" class="btn" target="_blank">Open Composer & Pre-Fill Tweet ➔</a>
        </div>

        <p style="font-size: 13px; margin-bottom: 6px;"><strong>Pre-composed Tweet Copy:</strong></p>
        <pre>{post_text}</pre>

        <div class="card-preview">
          <p><strong>Download Today's 4 Attached Visual Cards:</strong></p>
          <p>
            <a class="img-link" href="{card_base}/card_1.png" target="_blank">Card 1 (Regime)</a>
            <a class="img-link" href="{card_base}/card_2.png" target="_blank">Card 2 (Radar)</a>
            <a class="img-link" href="{card_base}/card_3.png" target="_blank">Card 3 (Setup 1)</a>
            <a class="img-link" href="{card_base}/card_4.png" target="_blank">Card 4 (Setup 2)</a>
          </p>
        </div>

        <hr style="border: 0; border-top: 1px solid #1e293b; margin: 24px 0;">
        <p style="font-size: 12px; color: #64748b; margin: 0;">Automated pipeline running via GitHub Actions on corpacuity.co.uk</p>
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
        print(f"[X INTENT] Successfully emailed 1-click dispatch intent to {recipient}")
    except Exception as e:
        print(f"[X INTENT] Failed to send email: {e}")
        print(f"[X INTENT] Direct Link: {intent_url}")

if __name__ == "__main__":
    url, text = build_x_intent_url()
    send_dispatch_email(url, text)
