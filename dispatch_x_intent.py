import os
import sys
import json
import urllib.parse
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

META_FILE = "latest_post_meta.json"
HELPER_HTML_FILE = "thread_helper.html"

# =====================================================================
# MODULAR PHRASE MATRIX & ANATOMY ASSETS
# =====================================================================
PHRASE_MATRIX = {
    "regime": {
        "bullish": [
            "Broad risk expanding ({breadth}% > 200 EMA).",
            "Institutional bid broadening: {breadth}% above 200 EMA.",
            "Market posture constructive with {breadth}% breadth."
        ],
        "rotational": [
            "Rotational accumulation active ({breadth}% > 200 EMA).",
            "Selective capital allocation: {breadth}% holding long-term trend.",
            "Defensives absorbing flow as breadth holds steady at {breadth}%."
        ],
        "defensive": [
            "Defensive posture active: breadth subdued at {breadth}%.",
            "Selective setups only: {breadth}% above 200 EMA requires tight risk.",
            "Capital preservation focus: market breadth at {breadth}%."
        ]
    },
    "setups": {
        "Base-Reset": {
            "high_r": "High asymmetry base-reset coiling with {r}R structural upside.",
            "tight": "Consolidation base tightening with a defined {risk}% risk window.",
            "standard": "Base-Reset continuation clearing multi-week institutional shelf.",
            "card": "anatomy_base_reset.png",
            "label": "Base-Reset Anatomy"
        },
        "Momentum Flag": {
            "high_r": "Momentum Flag coiling after advance, targeting {r}R asymmetry.",
            "tight": "Supply contraction visible across 10-day flag structure.",
            "standard": "Momentum Flag setting up: tight price compression above trend.",
            "card": "anatomy_momentum_flag.png",
            "label": "Momentum Flag Anatomy"
        },
        "Pocket Pivot": {
            "high_r": "Pocket pivot continuation offering {r}R reward-to-risk ratio.",
            "tight": "Early accumulation pivot with tight {risk}% invalidation level.",
            "standard": "Pocket pivot surfacing out of constructive basing structure.",
            "card": "anatomy_pocket_pivot.png",
            "label": "Pocket Pivot Anatomy"
        },
        "Liquidity Sweep": {
            "high_r": "Mean-reversion sweep reclaiming structural shelf ({r}R target).",
            "tight": "False breakdown reclaimed: tight {risk}% risk cushion.",
            "standard": "Liquidity sweep confirmation: stops cleared, demand re-entering.",
            "card": "anatomy_liquidity_sweep.png",
            "label": "Liquidity Sweep Anatomy"
        }
    },
    "questions": [
        "Which sector are you prioritizing into today's session?",
        "Are you leaning into momentum flags or waiting for base-reset confirmations?",
        "How are you structuring exposure given current index breadth?",
        "Watching defensives or tech leaders for today's pivots?"
    ]
}

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

def get_macro_hook(breadth):
    if breadth >= 60.0:
        bucket = "bullish"
    elif breadth >= 45.0:
        bucket = "rotational"
    else:
        bucket = "defensive"
    idx = int(breadth * 10) % len(PHRASE_MATRIX["regime"][bucket])
    return PHRASE_MATRIX["regime"][bucket][idx].format(breadth=breadth)

def get_setup_narrative(cat, r_ratio_val, risk_pct_val):
    bank = PHRASE_MATRIX["setups"].get(cat, PHRASE_MATRIX["setups"]["Base-Reset"])
    try:
        r_flt = float(r_ratio_val) if r_ratio_val is not None else 0.0
    except (ValueError, TypeError):
        r_flt = 0.0
    try:
        risk_flt = float(risk_pct_val) if risk_pct_val is not None else 5.0
    except (ValueError, TypeError):
        risk_flt = 5.0

    if r_flt >= 6.0:
        return bank["high_r"].format(r=f"{r_flt:.2f}", risk=f"{risk_flt:.2f}")
    elif risk_flt <= 3.0:
        return bank["tight"].format(r=f"{r_flt:.2f}", risk=f"{risk_flt:.2f}")
    return bank["standard"].format(r=f"{r_flt:.2f}", risk=f"{risk_flt:.2f}")

def get_card_info(cat):
    bank = PHRASE_MATRIX["setups"].get(cat, PHRASE_MATRIX["setups"]["Base-Reset"])
    return bank.get("card", "anatomy_base_reset.png"), bank.get("label", "Pattern Anatomy")

def build_thread_payloads():
    if not os.path.exists(META_FILE):
        print(f"[X INTENT] {META_FILE} not found.")
        sys.exit(1)

    with open(META_FILE, "r", encoding="utf-8") as f:
        meta = json.load(f)

    regime = meta.get("regime_status", "ACTIVE")
    exposure = meta.get("max_exposure", "30% - 60%")
    pct_above_200 = meta.get("pct_above_200", 0.0)

    regime_label = "EXPANSION" if "GREEN" in regime else ("DEFENSIVE" if "RED" in regime else "ACCUMULATION")
    macro_hook = get_macro_hook(pct_above_200)

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
        narrative = get_setup_narrative(primary_label, primary_cand.get('R_Ratio'), primary_cand.get('Risk_%'))
        card_file, card_lbl = get_card_info(primary_label)

        t1_text = (
            f"CORP ACUITY // ASYMMETRY SCAN\n\n"
            f"{macro_hook}\n"
            f"Exposure: {exposure}\n\n"
            f"Focus: ${p_ticker} ({primary_label})\n"
            f"{narrative}\n"
            f"• Pivot: {pivot} | Stop: {stop} ({risk} risk)\n\n"
            f"Invalid if open >2.5% over pivot.\n"
            f"Setups in thread 🧵👇\n\n"
            f"${p_ticker} #FinTwit"
        )
        if len(t1_text) > 280:
            t1_text = t1_text.replace(f"Exposure: {exposure}\n\n", "")
        if len(t1_text) > 280:
            t1_text = t1_text.replace(" #FinTwit", "")
        if len(t1_text) > 280:
            t1_text = t1_text.replace("Invalid if open >2.5% over pivot.\n", "")
    else:
        card_file, card_lbl = "anatomy_regime.png", "Macro Regime Anatomy"
        t1_text = (
            f"CORP ACUITY // ASYMMETRY SCAN\n\n"
            f"{macro_hook}\n"
            f"Exposure: {exposure}\n\n"
            f"Radar Focus: {radar_str}\n\n"
            f"Rule: Strict 2.0R asymmetry floor.\n"
            f"Setups in thread 🧵👇\n\n"
            f"$SPY$QQQ #FinTwit"
        )

    thread_posts.append({
        "title": "Tweet 1: Root Anchor Post",
        "role": f"Main tweet (attach Card 1 & {card_lbl})",
        "card_asset": f"assets/cards/{card_file}",
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
        sub_narrative = get_setup_narrative(label, cand.get('R_Ratio'), cand.get('Risk_%'))
        sub_card, sub_lbl = get_card_info(label)

        reply_text = (
            f"Setup #{i}: ${ticker} ({label})\n\n"
            f"{sub_narrative}\n\n"
            f"• Pivot: {pivot}\n"
            f"• Stop: {stop} ({risk} risk)\n"
            f"• Payoff: {asymmetry}\n"
            f"• Catalyst: Zacks {zacks}\n\n"
            f"Execution: Standard swing leeway."
        )
        if len(reply_text) > 280:
            reply_text = reply_text.replace(f"\n• Catalyst: Zacks {zacks}", "")

        thread_posts.append({
            "title": f"Tweet {i}: Thread Reply (Setup #{i})",
            "role": f"Reply in thread (attach {sub_lbl})",
            "card_asset": f"assets/cards/{sub_card}",
            "text": reply_text,
            "url": f"https://x.com/intent/tweet?text={urllib.parse.quote(reply_text)}"
        })

    # 3. FINAL THREAD CLOSER
    closer_num = len(thread_posts) + 1
    q_idx = int(pct_above_200) % len(PHRASE_MATRIX["questions"])
    question = PHRASE_MATRIX["questions"][q_idx]

    t_close_text = (
        f"Execution Governance & Screener Terminal:\n\n"
        f"Access quantitative breakdowns, daily PDF slide deck, and regime exposure directives:\n\n"
        f"👉 corpacuity.co.uk/intel.html\n\n"
        f"{question}"
    )
    thread_posts.append({
        "title": f"Tweet {closer_num}: Final Thread Reply (Terminal Link)",
        "role": "Terminal link reply at end of thread (no media)",
        "card_asset": "None",
        "text": t_close_text,
        "url": f"https://x.com/intent/tweet?text={urllib.parse.quote(t_close_text)}"
    })

    return thread_posts

def generate_thread_helper_html(thread_posts):
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
    .attachment-pill {{
      display: inline-flex;
      align-items: center;
      gap: 6px;
      font-size: 12px;
      background: #0f172a;
      border: 1px solid var(--border);
      color: var(--accent);
      padding: 6px 10px;
      border-radius: 6px;
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
        <strong>Workflow:</strong> Click <em>"Open Composer with Tweet 1"</em>. In X, hit the <strong>(+)</strong> button to add a tweet slot, drag the designated visual card, then click <em>"Copy Tweet #"</em> below and paste into each slot.
      </p>
      <div class="action-bar">
        <a href="{thread_posts[0]['url']}" target="_blank" class="primary-btn">
          🚀 1. Open X Composer with Tweet 1
        </a>
      </div>
    </div>

    <div id="thread-cards"></div>

    <div class="asset-tray">
      <strong style="color: var(--text-dim);">Local Visual Card Assets (Drag & Drop):</strong>
      <div class="asset-links">
        <span class="asset-link">📁 ./assets/cards/anatomy_base_reset.png</span>
        <span class="asset-link">📁 ./assets/cards/anatomy_momentum_flag.png</span>
        <span class="asset-link">📁 ./assets/cards/anatomy_pocket_pivot.png</span>
      </div>
    </div>
  </div>

  <script>
    const posts = {cards_js};
    const titles = {json.dumps([p["title"] for p in thread_posts])};
    const roles = {json.dumps([p["role"] for p in thread_posts])};
    const assets = {json.dumps([p.get("card_asset", "None") for p in thread_posts])};

    const container = document.getElementById('thread-cards');

    posts.forEach((text, idx) => {{
      const card = document.createElement('div');
      card.className = 'card';
      const charCount = text.length;
      const assetHint = assets[idx] !== "None" ? `<div class="attachment-pill">📎 <strong>Attach Card:</strong> ${{assets[idx]}}</div>` : '';

      card.innerHTML = `
        <div class="card-header">
          <h2 class="card-title">${{titles[idx]}}</h2>
          <span class="char-badge">${{charCount}} / 280 chars</span>
        </div>
        ${{assetHint}}
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
          Today's scan is rendered and validated under 280 characters with dynamic setup narratives.
        </p>

        <div style="text-align: center; margin: 25px 0;">
          <a href="{helper_url}" class="btn" target="_blank">🚀 Open Thread Dispatch Console ➔</a>
        </div>
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