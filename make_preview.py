import json, os, base64

meta_path = 'latest_post_meta.json'
thread_posts = []

if os.path.exists(meta_path):
    try:
        with open(meta_path, 'r', encoding='utf-8') as f:
            meta = json.load(f)
            thread_posts = meta.get('thread_posts', [])
    except Exception:
        pass

if not thread_posts:
    thread_posts = [
        {'title': 'Tweet 1: Focus Setup & Context', 'card_asset': 'x_cards/card_1.png', 'text': '$AEHR Base-Reset Setup\n\n• Clean reclaim of 200 EMA\n• Volume expansion > 2.4x\n• High conviction score'},
        {'title': 'Tweet 2: Technical Structure', 'card_asset': 'x_cards/card_2.png', 'text': 'Daily structure breaking multi-week contraction.\n\nRisk: 1.2%\nTarget: 3.5R pivot\nBaseline: 20 EMA cushion'},
        {'title': 'Tweet 3: Secondary Watchlist', 'card_asset': 'x_cards/card_3.png', 'text': 'Pocket Pivot alerts:\n\n1. Setup A — tight vcp flag\n2. Setup B — high volume ignition'},
        {'title': 'Tweet 4: Portfolio Risk Plan', 'card_asset': 'x_cards/card_4.png', 'text': 'Execution Plan:\n\n• Max 1% equity risk per trade\n• Stops hard at prior day low\n• No pre-market chasing'}
    ]

def get_img_tag(card_path):
    # Check current dir, then assets/cards
    candidates = [
        card_path,
        os.path.join('assets', 'cards', os.path.basename(card_path)) if card_path else '',
        f"x_cards/{os.path.basename(card_path)}" if card_path else ''
    ]
    found = None
    for c in candidates:
        if c and os.path.exists(c):
            found = c
            break
            
    if found:
        with open(found, 'rb') as img_f:
            b64_data = base64.b64encode(img_f.read()).decode('utf-8')
        return f'''<div style="margin: 12px 0;">
            <img src="data:image/png;base64,{b64_data}" style="max-width:100%; width:540px; height:auto; border-radius:6px; border:1px solid #1e293b; display:block; cursor:pointer;" alt="Setup Chart">
            <span style="font-size:11px; color:#38bdf8; display:block; margin-top:6px; font-weight:500;">👉 Right-Click (or Long-press) image &rarr; <strong>"Copy Image"</strong> &rarr; Ctrl+V into X</span>
        </div>'''
    return '<div style="color:#64748b; font-size:12px; margin:8px 0; font-style:italic;">[Chart image not found on disk]</div>'

cards_html = []
for i, p in enumerate(thread_posts, 1):
    card_img_html = get_img_tag(p.get('card_asset', f'x_cards/card_{i}.png'))
    
    if i == 1:
        action_html = f'''<a href="{p.get("url", "https://x.com/intent/tweet")}" target="_blank" style="background:#0284c7; color:#ffffff; text-decoration:none; padding:10px 18px; border-radius:6px; font-size:13px; font-weight:bold; display:inline-block; margin-top:6px;">🚀 1. Open Thread in X Composer</a>'''
    else:
        action_html = '''<div style="color:#94a3b8; font-size:12px; font-weight:500; padding:6px 0;">📋 Highlight &amp; copy text above &rarr; paste into thread reply slot (+)</div>'''

    card = f'''
    <div style="background:#161e2e; border:1px solid #1e293b; border-radius:8px; padding:16px; margin-bottom:20px;">
        <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:8px;">
            <strong style="color:#38bdf8; font-size:14px; letter-spacing:0.3px;">{p.get('title', f'Tweet {i}')}</strong>
            <span style="color:#94a3b8; font-size:11px; background:#0f172a; padding:2px 8px; border-radius:4px; border:1px solid #1e293b;">Slot {i}</span>
        </div>
        {card_img_html}
        <pre style="background:#0a0e17; border:1px solid #1e293b; border-radius:6px; padding:12px; font-family:Consolas, Monaco, monospace; font-size:12px; color:#cbd5e1; line-height:1.5; margin-bottom:12px; white-space:pre-wrap; word-break:break-word;">{p['text']}</pre>
        {action_html}
    </div>
    '''
    cards_html.append(card)

html_content = f'''<!DOCTYPE html>
<html>
<body style="background:#0b0f19; font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif; color:#f8fafc; padding:24px;">
    <div style="max-width:600px; margin:0 auto;">
        <div style="text-align:center; padding-bottom:16px; margin-bottom:20px; border-bottom:1px solid #1e293b;">
            <h2 style="color:#38bdf8; margin:0 0 6px 0;">Corp Acuity // X Thread Dispatch Preview</h2>
            <p style="color:#94a3b8; font-size:13px; margin:0;">Full cards with visual charts, uncrunched text, and single-click composer flow.</p>
        </div>
        {''.join(cards_html)}
    </div>
</body>
</html>'''

with open('preview_email.html', 'w', encoding='utf-8') as f:
    f.write(html_content)

print('[+] Generated preview_email.html with embedded chart images.')
