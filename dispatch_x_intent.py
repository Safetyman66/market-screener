try:
    import generate_live_charts
    generate_live_charts.generate_all()
except Exception as e:
    print(f"[!] Chart generation note: {e}")
import os
import sys
import json
import urllib.parse
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

META_FILE = "latest_post_meta.json"
HELPER_HTML_FILE = "thread_helper.html"

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

    # Tweet 1
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
            f"Focus: ${p_ticker} ({primary_label})\n"
            f"{narrative}\n"
            f"• Pivot: {pivot} | Stop: {stop} ({risk} risk)\n\n"
            f"Invalid if open >2.5% over pivot.\n"
            f"Setups in thread 🧵👇\n\n"
            f"${p_ticker}"
        )
        if len(t1_text) > 280:
            t1_text = t1_text.replace("Invalid if open >2.5% over pivot.\n", "")
    else:
        card_file, card_lbl = "anatomy_regime.png", "Macro Regime Anatomy"
        t1_text = (
            f"CORP ACUITY // ASYMMETRY SCAN\n\n"
            f"{macro_hook}\n"
            f"Radar Focus: {radar_str}\n\n"
            f"Rule: Strict 2.0R asymmetry floor.\n"
            f"Setups in thread 🧵👇\n\n"
            f"$SPY$QQQ"
        )

    thread_posts.append({
        "title": "Tweet 1: Root Anchor Post",
        "role": f"Main tweet (Card: {card_lbl})",
        "card_asset": f"assets/cards/{card_file}",
        "card_label": card_lbl,
        "text": t1_text,
        "url": f"https://x.com/intent/tweet?text={urllib.parse.quote(t1_text)}"
    })

    # Setups 2 & 3
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
            "role": f"Reply (Card: {sub_lbl})",
            "card_asset": f"assets/cards/{sub_card}",
            "card_label": sub_lbl,
            "text": reply_text,
            "url": f"https://x.com/intent/tweet?text={urllib.parse.quote(reply_text)}"
        })

    # Tweet 4: Terminal Link
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
        "card_label": "None",
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
      max-width: 720px;
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
      margin-bottom: 14px;
    }}
    .media-preview-box {{
      display: flex;
      gap: 14px;
      background: #0a0e17;
      border: 1px solid var(--border);
      border-radius: 8px;
      padding: 12px;
      align-items: center;
      margin-bottom: 14px;
    }}
    .media-thumb {{
      width: 140px;
      height: 78px;
      object-fit: cover;
      border-radius: 6px;
      border: 1px solid var(--border);
    }}
    .media-info {{
      flex: 1;
      display: flex;
      flex-direction: column;
      gap: 6px;
    }}
    .card-actions {{
      display: flex;
      gap: 10px;
      align-items: center;
      flex-wrap: wrap;
    }}
    .action-btn {{
      background: #1e293b;
      color: var(--text-main);
      border: 1px solid #334155;
      padding: 8px 14px;
      border-radius: 6px;
      font-size: 13px;
      cursor: pointer;
      font-weight: 500;
      display: inline-flex;
      align-items: center;
      gap: 6px;
      transition: all 0.15s ease;
    }}
    .action-btn:hover {{
      background: #334155;
      border-color: var(--accent);
    }}
    .btn-image {{
      border-color: #0284c7;
      color: var(--accent);
    }}
    .copied {{
      background: var(--success) !important;
      color: #0b0f19 !important;
      border-color: var(--success) !important;
    }}
  </style>
</head>
<body>
  <div class="container">
    <div class="header">
      <h1>Corp Acuity // X Thread Dispatch Console</h1>
      <p class="instructions">
        <strong>Fast Flow:</strong><br>
        1. Click <em>"Open X Composer"</em> (loads Tweet 1 text).<br>
        2. Click <strong>"📋 Copy Card Image"</strong>, click into the tweet on X, and press <strong>Ctrl+V</strong> to attach the image.<br>
        3. Add slot <strong>(+)</strong> in X, copy next text & image, paste, and repeat.
      </p>
      <div class="action-bar">
        <a href="{thread_posts[0]['url']}" target="_blank" class="primary-btn">
          🚀 1. Open X Composer with Tweet 1
        </a>
      </div>
    </div>

    <div id="thread-cards"></div>
  </div>

  <script>
    const posts = {cards_js};
    const titles = {json.dumps([p["title"] for p in thread_posts])};
    const roles = {json.dumps([p["role"] for p in thread_posts])};
    const assets = {json.dumps([p.get("card_asset", "None") for p in thread_posts])};
    const labels = {json.dumps([p.get("card_label", "None") for p in thread_posts])};

    const container = document.getElementById('thread-cards');

    posts.forEach((text, idx) => {{
      const card = document.createElement('div');
      card.className = 'card';
      const charCount = text.length;
      const assetPath = assets[idx];
      const assetLabel = labels[idx];

      let mediaHtml = '';
      if (assetPath !== "None") {{
        mediaHtml = `
          <div class="media-preview-box">
            <img class="media-thumb" src="${{assetPath}}" alt="${{assetLabel}}" />
            <div class="media-info">
              <strong style="font-size: 13px; color: var(--accent);">${{assetLabel}}</strong>
              <span style="font-size: 11px; color: var(--text-dim);">${{assetPath}}</span>
              <div>
                <button class="action-btn btn-image" onclick="copyCardImage('${{assetPath}}', this)">
                  🖼️ Copy Card Image (Ctrl+V into X)
                </button>
              </div>
            </div>
          </div>
        `;
      }}

      card.innerHTML = `
        <div class="card-header">
          <h2 class="card-title">${{titles[idx]}}</h2>
          <span class="char-badge">${{charCount}} / 280 chars</span>
        </div>
        ${{mediaHtml}}
        <div class="text-box" id="text-${{idx}}">${{text}}</div>
        <div class="card-actions">
          <button class="action-btn" onclick="copySlotText(${{idx}}, this)">📋 Copy Tweet #${{idx + 1}} Text</button>
          <span style="font-size: 11px; color: var(--text-dim); margin-left: auto;">${{roles[idx]}}</span>
        </div>
      `;
      container.appendChild(card);
    }});

    function copySlotText(idx, btn) {{
      const text = posts[idx];
      navigator.clipboard.writeText(text).then(() => {{
        const originalText = btn.innerHTML;
        btn.innerHTML = '✓ Text Copied!';
        btn.classList.add('copied');
        setTimeout(() => {{
          btn.innerHTML = originalText;
          btn.classList.remove('copied');
        }}, 1800);
      }});
    }}

    async function copyCardImage(imgPath, btn) {{
      const originalText = btn.innerHTML;
      try {{
        const response = await fetch(imgPath);
        const blob = await response.blob();
        await navigator.clipboard.write([
          new ClipboardItem({{ [blob.type]: blob }})
        ]);
        btn.innerHTML = '✓ Image Copied! Press Ctrl+V in X';
        btn.classList.add('copied');
        setTimeout(() => {{
          btn.innerHTML = originalText;
          btn.classList.remove('copied');
        }}, 2200);
      }} catch (err) {{
        console.error('Clipboard image error:', err);
        btn.innerHTML = '⚠️ Open image in tab';
        window.open(imgPath, '_blank');
      }}
    }}
  </script>
</body>
</html>
"""
    with open(HELPER_HTML_FILE, "w", encoding="utf-8") as f:
        f.write(html_content)
    print(f"[X INTENT] Generated dispatch helper page: {HELPER_HTML_FILE}")

def send_dispatch_email(thread_posts):
    from email.mime.image import MIMEImage

    host = os.environ.get("SMTP_HOST")
    port = int(os.environ.get("SMTP_PORT", 587))
    user = os.environ.get("SMTP_USER")
    password = os.environ.get("SMTP_PASS")
    recipient = os.environ.get("ALERT_RECIPIENT", "ajmcneilster@gmail.com")

    if not host or not user or not password:
        print("[!] SMTP credentials missing in environment. Skipping email dispatch.")
        return

    # Root container: related so inline images display alongside HTML
    msg_root = MIMEMultipart("related")
    msg_root["Subject"] = "Corp Acuity // Today's X Morning Thread Dispatch"
    msg_root["From"] = user
    msg_root["To"] = recipient

    msg_alt = MIMEMultipart("alternative")
    msg_root.attach(msg_alt)

    # Text fallback
    text_lines = ["Corp Acuity // X Morning Thread Dispatch\n"]
    for i, p in enumerate(thread_posts, 1):
        text_lines.append(f"--- Tweet {i} ({p.get('card_label', 'Text')}) ---")
        text_lines.append(p["text"])
        text_lines.append(f"Composer: {p['url']}\n")
    text_content = "\n".join(text_lines)
    msg_alt.attach(MIMEText(text_content, "plain"))

    # Rich HTML & Embedded Cards
    images_to_attach = []
    html_cards = ""

    for i, p in enumerate(thread_posts, 1):
        card_lbl = p.get('card_label', 'No media')
        card_path = p.get('card_asset', 'None')
        text_formatted = p['text'].replace('\n', '<br>')

        img_html = ""
        # Check if card image exists on disk
        resolved_card = card_path
        if resolved_card and resolved_card != "None":
            if not os.path.exists(resolved_card):
                alt_p = os.path.join("assets", "cards", os.path.basename(resolved_card))
                if os.path.exists(alt_p):
                    resolved_card = alt_p

            if os.path.exists(resolved_card):
                cid_name = f"card_{i}"
                img_html = f"""
                <div style="margin: 12px 0;">
                    <img src="cid:{cid_name}" style="max-width:100%; width:540px; height:auto; border-radius:6px; border:1px solid #1e293b; display:block;" alt="{card_lbl}">
                    <span style="font-size:11px; color:#94a3b8; display:block; margin-top:4px;">Right-click / Long-press image to Copy or Save</span>
                </div>
                """
                images_to_attach.append((cid_name, resolved_card))

        html_cards += f"""
        <div style="background:#161e2e; border:1px solid #1e293b; border-radius:8px; padding:16px; margin-bottom:18px;">
            <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:10px;">
                <strong style="color:#38bdf8; font-size:14px; letter-spacing:0.3px;">{p['title']}</strong>
                <span style="color:#94a3b8; font-size:12px; margin-left:12px; background:#0f172a; padding:2px 8px; border-radius:4px; border:1px solid #1e293b;">{card_lbl}</span>
            </div>
            {img_html}
            <div style="background:#0a0e17; border:1px solid #1e293b; border-radius:6px; padding:12px; font-family:Consolas, Monaco, monospace; font-size:12px; color:#cbd5e1; line-height:1.5; margin-bottom:12px; white-space:pre-wrap;">
{p['text']}
            </div>
            <a href="{p['url']}" target="_blank" style="background:#0284c7; color:#ffffff; text-decoration:none; padding:9px 16px; border-radius:6px; font-size:12px; font-weight:bold; display:inline-block;">
                Open Tweet in X Composer
            </a>
        </div>
        """

    html_content = f"""
    <!DOCTYPE html>
    <html>
    <body style="background:#0b0f19; font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif; color:#f8fafc; padding:20px;">
        <div style="max-width:600px; margin:0 auto;">
            <div style="text-align:center; padding-bottom:16px; margin-bottom:20px; border-bottom:1px solid #1e293b;">
                <h2 style="color:#38bdf8; margin:0 0 6px 0;">Corp Acuity // X Thread Dispatch</h2>
                <p style="color:#94a3b8; font-size:13px; margin:0;">Morning scanner setup thread &bull; Copy image &amp; open composer.</p>
            </div>
            {html_cards}
            <div style="text-align:center; font-size:11px; color:#64748b; margin-top:20px;">
                Corp Acuity Systematic Intelligence &bull; Automated Dispatch Engine
            </div>
        </div>
    </body>
    </html>
    """

    msg_alt.attach(MIMEText(html_content, "html"))

    # Attach all inline images with Content-ID
    for cid_name, img_path in images_to_attach:
        try:
            with open(img_path, "rb") as f:
                img_data = f.read()
                mime_img = MIMEImage(img_data)
                mime_img.add_header("Content-ID", f"<{cid_name}>")
                mime_img.add_header("Content-Disposition", "inline", filename=os.path.basename(img_path))
                msg_root.attach(mime_img)
        except Exception as img_err:
            print(f"[!] Warning attaching image {img_path}: {img_err}")

    try:
        print(f"[+] Connecting to SMTP server {host}:{port}...")
        if port == 465:
            with smtplib.SMTP_SSL(host, port, timeout=15) as server:
                server.login(user, password)
                server.sendmail(user, recipient, msg_root.as_string())
        else:
            with smtplib.SMTP(host, port, timeout=15) as server:
                server.starttls()
                server.login(user, password)
                server.sendmail(user, recipient, msg_root.as_string())
        print(f"[SUCCESS] X thread dispatch email with embedded cards successfully sent to {recipient}")
    except Exception as e:
        print(f"[!] SMTP dispatch failed: {e}")

if __name__ == "__main__":
    thread = build_thread_payloads()
    generate_thread_helper_html(thread)
    send_dispatch_email(thread)