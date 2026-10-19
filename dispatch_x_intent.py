import os
import sys
import json
import urllib.parse
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

META_FILE = "latest_post_meta.json"
HELPER_HTML_FILE = "thread_helper.html"

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

def build_thread_payloads():
    if not os.path.exists(META_FILE):
        print(f"[X INTENT] {META_FILE} not found.")
        sys.exit(1)

    with open(META_FILE, "r", encoding="utf-8") as f:
        meta = json.load(f)

    regime = meta.get("regime_status", "ACTIVE")
    exposure = meta.get("max_exposure", "30% - 60%")
    pct_above_200 = meta.get("pct_above_200", 0.0)

    # Concise regime labels for strict character compliance
    regime_label = "EXPANSION" if "GREEN" in regime else ("DEFENSIVE" if "RED" in regime else "ACCUMULATION")

    setup_slots = [
        ('top_br', 'Base-Reset'),
        ('top_htf', 'Momentum Flag'),
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
    radar_str = " ".join(cashtags) if cashtags else "$SPY$QQQ"

    thread_posts = []

    # 1. ROOT ANCHOR TWEET
    if active_setups:
        primary_cand, primary_label = active_setups[0]
        p_ticker = primary_cand.get('Ticker')
        pivot = format_num(primary_cand.get('Pivot_Trigger'), prefix="$")
        stop = format_num(primary_cand.get('Stop_Loss'), prefix="$")
        risk = format_num(primary_cand.get('Risk_%'), suffix="%")
        asymmetry = format_num(primary_cand.get('R_Ratio'), suffix="R")
        earnings = primary_cand.get('Earnings_Risk', 'SAFE')

        t1_text = (
            f"CORP ACUITY // ASYMMETRY SCAN\n\n"
            f"Regime: {regime_label} ({exposure})\n"
            f"Breadth: {pct_above_200}% > 200 EMA\n\n"
            f"Focus: ${p_ticker} ({primary_label})\n"
            f"• Pivot: {pivot}\n"
            f"• Stop: {stop} ({risk} risk)\n"
            f"• Payoff: {asymmetry}\n"
            f"• Runway: {earnings}\n\n"
            f"Void if open >2.5% past pivot.\n"
            f"Setups in thread 🧵👇\n\n"
            f"$SPY$QQQ #FinTwit"
        )
    else:
        t1_text = (
            f"CORP ACUITY // ASYMMETRY SCAN\n\n"
            f"Regime: {regime_label} ({exposure})\n"
            f"Breadth: {pct_above_200}% > 200 EMA\n\n"
            f"Radar Focus: {radar_str}\n\n"
            f"Rule: Strict 2.0R asymmetry floor.\n"
            f"Setups in thread 🧵👇\n\n"
            f"$SPY$QQQ #FinTwit"
        )

    thread_posts.append({
        "title": "Tweet 1: Root Anchor Post",
        "role": "Post this as your main tweet (attach Card 1 & Card 2)",
        "text": t1_text,
        "url": f"https://x.com/intent/tweet?text={urllib.parse.quote(t1_text)}"
    })

    # 2. SUBSEQUENT SETUPS
    for i, (cand, label) in enumerate(active_setups[1:3], start=2):
        ticker = cand.get('Ticker')
        pivot = format_num(cand.get('Pivot_Trigger'), prefix="$")
        stop = format_num(cand.get('Stop_Loss'), prefix="$")
        risk = format_num(cand.get('Risk_%'), suffix="%")
        asymmetry = format_num(cand.get('R_Ratio'), suffix="R")
        zacks = clean_zacks(cand.get('Zacks_Rank'))
        earnings = cand.get('Earnings_Risk', 'SAFE')

        reply_text = (
            f"Setup #{i}: ${ticker} ({label})\n\n"
            f"• Pivot: {pivot}\n"
            f"• Stop: {stop} ({risk} risk)\n"
            f"• Payoff: {asymmetry}\n"
            f"• Catalyst: Zacks {zacks}\n"
            f"• Runway: {earnings}\n\n"
            f"Execution: Standard swing leeway."
        )
        thread_posts.append({
            "title": f"Tweet {i}: Thread Reply (Setup #{i})",
            "role": f"Reply in thread (attach Card {i+1})",
            "text": reply_text,
            "url": f"https://x.com/intent/tweet?text={urllib.parse.quote(reply_text)}"
        })

    # 3. FINAL THREAD CLOSER
    closer_num = len(thread_posts) + 1
    t_close_text = (
        f"Execution Governance & Screener Terminal:\n\n"
        f"Access quantitative breakdowns, daily PDF slide deck, and regime exposure directives:\n\n"
        f"👉 corpacuity.co.uk/intel.html"
    )
    thread_posts.append({
        "title": f"Tweet {closer_num}: Final Thread Reply (Terminal Link)",
        "role": "Terminal link reply at end of thread",
        "text": t_close_text,
        "url": f"https://x.com/intent/tweet?text={urllib.parse.quote(t_close_text)}"
    })

    return thread_posts

def generate_thread_helper_html(thread_posts):
    card_base = "https://corpacuity.co.uk/x_cards"
    cards_js = json.dumps([p["text"] for p in thread_posts])

    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Corp Acuity // X Thread Dispatch Console</title>
  <style>
    :root {{
      --bg: #0b0f19;
      --card-bg: #161e2e;
      --border: #1e293b;
      --accent: #38bdf8;
      --success: #4ade80;
      --text-main: #f8fafc;
      --text-dim: #94a3b8;
    }}
    body {{
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
      background-color: var(--bg);
      color: var(--text-main);
      margin: 0;
      padding: 24px 16px;
      display: flex;
      justify-content: center;
    }}
    .container {{
      max-width: 680px;
      width: 100%;
    }}
    .header {{
      text-align: center;
      margin-bottom: 24px;
      padding-bottom: 20px;
      border-bottom: 1px solid var(--border);
    }}
    h1 {{
      font-size: 22px;
      color: var(--accent);
      margin: 0 0 8px 0;
      letter-spacing: 0.5px;
    }}
    .instructions {{
      font-size: 13px;
      color: var(--text-dim);
      line-height: 1.5;
    }}
    .action-bar {{
      display: flex;
      gap: 12px;
      justify-content: center;
      margin-top: 16px;
      flex-wrap: wrap;
    }}
    .primary-btn {{
      background: var(--accent);
      color: #0b0f19;
      font-weight: bold;
      padding: 12px 20px;
      border-radius: 8px;
      text-decoration: none;
      font-size: 14px;
      display: inline-flex;
      align-items: center;
      gap: 6px;
      border: none;
      cursor: pointer;
    }}
    .card {{
      background: var(--card-bg);
      border: 1px solid var(--border);
      border-radius: 10px;
      padding: 18px;
      margin-bottom: 18px;
      position: relative;
    }}
    .card-header {{
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 12px;
    }}
    .card-title {{
      font-size: 15px;
      font-weight: 600;
      color: var(--accent);
      margin: 0;
    }}
    .char-badge {{
      font-size: 11px;
      padding: 3px 8px;
      border-radius: 12px;
      background: #0f172a;
      border: 1px solid var(--border);
      color: var(--success);
      font-family: monospace;
    }}
    .text-box {{
      background: #0a0e17;
      border: 1px solid var(--border);
      border-radius: 8px;
      padding: 14px;
      font-family: monospace;
      font-size: 13px;
      line-height: 1.5;
      color: #cbd5e1;
      white-space: pre-wrap;
      margin-bottom: 12px;
    }}
    .card-actions {{
      display: flex;
      justify-content: space-between;
      align-items: center;
    }}
    .copy-btn {{
      background: #1e293b;
      color: var(--text-main);
      border: 1px solid #334155;
      padding: 8px 16px;
      border-radius: 6px;
      font-size: 13px;
      cursor: pointer;
      font-weight: 500;
      transition: all 0.15s ease;
    }}
    .copy-btn:hover {{
      background: #334155;
      border-color: var(--accent);
    }}
    .copied {{
      background: var(--success) !important;
      color: #0b0f19 !important;
      border-color: var(--success) !important;
    }}
    .asset-tray {{
      margin-top: 24px;
      background: #0f172a;
      border: 1px solid var(--border);
      border-radius: 8px;
      padding: 16px;
      font-size: 13px;
    }}
    .asset-links {{
      display: flex;
      gap: 12px;
      flex-wrap: wrap;
      margin-top: 8px;
    }}
    .asset-link {{
      color: var(--accent);
      text-decoration: underline;
    }}
  </style>
</head>
<body>
  <div class="container">
    <div class="header">
      <h1>Corp Acuity // X Thread Dispatcher</h1>
      <p class="instructions">
        <strong>Workflow:</strong> Click <em>"Open Composer with Tweet 1"</em>. In X, hit the <strong>(+)</strong> button to add a tweet slot, then simply click <em>"Copy Tweet #"</em> below and paste into each slot.
      </p>
      <div class="action-bar">
        <a href="{thread_posts[0]['url']}" target="_blank" class="primary-btn">
          🚀 1. Open X Composer with Tweet 1
        </a>
      </div>
    </div>

    <div id="thread-cards"></div>

    <div class="asset-tray">
      <strong style="color: var(--text-dim);">Visual Card Attachments:</strong>
      <div class="asset-links">
        <a class="asset-link" href="{card_base}/card_1.png" target="_blank">Card 1 (Regime)</a>
        <a class="asset-link" href="{card_base}/card_2.png" target="_blank">Card 2 (Radar)</a>
        <a class="asset-link" href="{card_base}/card_3.png" target="_blank">Card 3 (Setup 1)</a>
        <a class="asset-link" href="{card_base}/card_4.png" target="_blank">Card 4 (Setup 2)</a>
      </div>
    </div>
  </div>

  <script>
    const posts = {cards_js};
    const titles = {json.dumps([p["title"] for p in thread_posts])};
    const roles = {json.dumps([p["role"] for p in thread_posts])};

    const container = document.getElementById('thread-cards');

    posts.forEach((text, idx) => {{
      const card = document.createElement('div');
      card.className = 'card';
      const charCount = text.length;

      card.innerHTML = `
        <div class="card-header">
          <h2 class="card-title">${{titles[idx]}}</h2>
          <span class="char-badge">${{charCount}} / 280 chars</span>
        </div>
        <div class="text-box" id="text-${{idx}}">${{text}}</div>
        <div class="card-actions">
          <button class="copy-btn" onclick="copySlot(${{idx}}, this)">📋 Copy Tweet #${{idx + 1}}</button>
          <span style="font-size: 11px; color: var(--text-dim);">${{roles[idx]}}</span>
        </div>
      `;
      container.appendChild(card);
    }});

    function copySlot(idx, btn) {{
      const text = posts[idx];
      navigator.clipboard.writeText(text).then(() => {{
        const originalText = btn.innerHTML;
        btn.innerHTML = '✓ Copied!';
        btn.classList.add('copied');
        setTimeout(() => {{
          btn.innerHTML = originalText;
          btn.classList.remove('copied');
        }}, 1800);
      }});
    }}
  </script>
</body>
</html>
"""
    with open(HELPER_HTML_FILE, "w", encoding="utf-8") as f:
        f.write(html_content)
    print(f"[X INTENT] Generated dispatch helper page: {HELPER_HTML_FILE}")

def send_dispatch_email(thread_posts):
    smtp_host = os.getenv("SMTP_HOST", "smtp.gmail.com")
    smtp_port = int(os.getenv("SMTP_PORT", "587"))
    smtp_user = os.getenv("SMTP_USER")
    smtp_pass = os.getenv("SMTP_PASS")
    recipient = os.getenv("ALERT_RECIPIENT", "ajmcneilster@gmail.com")

    helper_url = "https://corpacuity.co.uk/thread_helper.html"

    if not smtp_user or not smtp_pass:
        print(f"[X INTENT] SMTP credentials not provided locally. Thread helper saved locally to {HELPER_HTML_FILE}")
        return

    msg = MIMEMultipart("alternative")
    msg["Subject"] = "🚀 Today's X Morning Thread Console Ready"
    msg["From"] = f"Corp Acuity Screener <{smtp_user}>"
    msg["To"] = recipient

    html_body = f"""
    <!DOCTYPE html>
    <html>
    <head>
      <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; background-color: #0b0f19; color: #f8fafc; padding: 20px; }}
        .card {{ background-color: #161e2e; border: 1px solid #1e293b; border-radius: 12px; padding: 24px; max-width: 620px; margin: 0 auto; }}
        .btn {{ display: inline-block; background-color: #38bdf8; color: #0b0f19 !important; font-weight: bold; padding: 14px 24px; border-radius: 8px; text-decoration: none; font-size: 15px; margin: 15px 0; }}
      </style>
    </head>
    <body>
      <div class="card">
        <h2 style="color: #38bdf8; margin-top: 0;">Corp Acuity // Morning Dispatch Console</h2>
        <p style="font-size: 14px; color: #94a3b8; line-height: 1.5;">
          Today's scan is rendered and validated under 280 characters. Use the single-click dispatch console to copy and deploy each thread slot into X in under 30 seconds:
        </p>

        <div style="text-align: center; margin: 25px 0;">
          <a href="{helper_url}" class="btn" target="_blank">🚀 Open Thread Dispatch Console ➔</a>
        </div>

        <p style="font-size: 12px; color: #64748b; line-height: 1.4;">
          <strong>Quick steps:</strong><br>
          1. Tap the button above to open the console.<br>
          2. Click <em>"Open X Composer"</em> (loads Tweet 1 automatically).<br>
          3. Tap <strong>(+)</strong> in X, then click <em>"Copy Tweet #2"</em> on the console and paste.<br>
          4. Repeat for #3 and #4, then click <strong>Post all</strong>.
        </p>

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
        print(f"[X INTENT] Successfully emailed thread dispatch console link to {recipient}")
    except Exception as e:
        print(f"[X INTENT] Failed to send email: {e}")

if __name__ == "__main__":
    thread = build_thread_payloads()
    generate_thread_helper_html(thread)
    send_dispatch_email(thread)