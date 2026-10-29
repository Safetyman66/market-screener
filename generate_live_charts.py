import os
import json
import time
import shutil
import requests
import yfinance as yf
import pandas as pd
from PIL import Image, ImageDraw, ImageFont

META_FILE = "latest_post_meta.json"
FEED_FILE = "terminal_feed.json"
OUT_DIR = os.path.join("assets", "cards")
THUMB_DIR = "thumbnails"

os.makedirs(OUT_DIR, exist_ok=True)

# Stealth Session for bulk downloading to bypass rate limits
GLOBAL_HTTP_SESSION = requests.Session()
GLOBAL_HTTP_SESSION.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
})

# Base HD Canvas Size (used natively for Twitter/LinkedIn)
W, H = 1200, 675
BG_COLOR = "#0b0f19"
PANEL_BG = "#111827"
BORDER = "#1e293b"
TEXT_MAIN = "#f8fafc"
TEXT_MUTED = "#94a3b8"
GREEN = "#22c55e"
RED = "#ef4444"
VOL_GREEN = "#15803d"
VOL_RED = "#991b1b"

def get_fonts():
    try:
        f_title = ImageFont.truetype("arialbd.ttf", 26)
        f_sub = ImageFont.truetype("arial.ttf", 17)
        f_badge = ImageFont.truetype("arialbd.ttf", 14)
        f_axis = ImageFont.truetype("arial.ttf", 13)
        f_body = ImageFont.truetype("arialbd.ttf", 15)
        f_tag = ImageFont.truetype("arialbd.ttf", 13)
    except:
        f_title = f_sub = f_badge = f_axis = f_body = f_tag = ImageFont.load_default()
    return f_title, f_sub, f_badge, f_axis, f_body, f_tag

F_TITLE, F_SUB, F_BADGE, F_AXIS, F_BODY, F_TAG = get_fonts()

def dash_h(draw, x0, x1, y, col, width=2):
    for x in range(int(x0), int(x1), 16):
        draw.line([(x, y), (min(x + 10, x1), y)], fill=col, width=width)

def axis_flag(draw, x, y, text, bg, fg="#ffffff"):
    bbox = F_TAG.getbbox(text)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    box_w = tw + 14
    box_h = th + 10
    top_y = y - box_h // 2
    draw.rectangle([(x, top_y), (x + box_w, top_y + box_h)], fill=bg, outline="#000000", width=1)
    draw.text((x + 7, top_y + 4), text, fill=fg, font=F_TAG)

def safe_float(val):
    """Safely cast JSON data to float, skipping strings like 'N/A' or empty fields."""
    try:
        if val is None or str(val).strip() == "":
            return None
        return float(val)
    except (ValueError, TypeError):
        return None

def calculate_tactical_geometry(pivot, stop, structural_resistance=None):
    if not pivot or not stop or pivot <= stop:
        return None, None
        
    risk_dollar = pivot - stop
    target_ceiling = pivot + (3.0 * risk_dollar)
    
    if structural_resistance and structural_resistance > pivot:
        target = min(structural_resistance, target_ceiling)
    else:
        target = target_ceiling
        
    final_r = (target - pivot) / risk_dollar
    
    if final_r < 2.0:
        target = pivot + (2.0 * risk_dollar)
        final_r = 2.0
        
    return target, final_r

def render_ticker_chart(ticker, label, pivot, stop, risk_pct, r_ratio, target_price, out_path, is_thumbnail=False):
    try:
        df = yf.download(ticker, period="8mo", interval="1d", progress=False, auto_adjust=True, session=GLOBAL_HTTP_SESSION)
    except Exception as e:
        print(f"[!] yfinance fetch failed for {ticker}: {e}")
        return

    if df.empty or len(df) < 30:
        return

    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    df['EMA20'] = df['Close'].ewm(span=20, adjust=False).mean()
    df['SMA50'] = df['Close'].rolling(window=50).mean()
    view = df.tail(65).copy()

    im = Image.new("RGB", (W, H), BG_COLOR)
    draw = ImageDraw.Draw(im)

    acc = "#38bdf8" if "Base" in label else ("#f59e0b" if "Flag" in label else "#10b981")
    draw.rectangle([(0, 0), (W, 8)], fill=acc)

    target = target_price

    draw.text((45, 20), "CORP ACUITY // LIVE SETUP ANATOMY", fill=TEXT_MUTED, font=F_SUB)
    draw.text((45, 46), f"${ticker} // {label.upper()}", fill=TEXT_MAIN, font=F_TITLE)
    draw.text((45, 80), "Execution Geometry: Origin Pivot Ceiling, Trailing Floor & Projected Target", fill=acc, font=F_SUB)
    draw.text((W - 200, 25), "corpacuity.co.uk", fill=TEXT_MUTED, font=F_SUB)

    p_x0, p_y0, p_x1, p_y1 = 45, 115, W - 145, 475
    v_x0, v_y0, v_x1, v_y1 = 45, 490, W - 145, 575
    f_x0, f_y0, f_x1, f_y1 = 45, 595, W - 45, 655

    draw.rectangle([(p_x0, p_y0), (p_x1, p_y1)], fill=PANEL_BG, outline=BORDER, width=2)
    draw.rectangle([(v_x0, v_y0), (v_x1, v_y1)], fill=PANEL_BG, outline=BORDER, width=2)
    draw.rectangle([(f_x0, f_y0), (f_x1, f_y1)], fill="#0f172a", outline=acc, width=2)

    draw.text((p_x1 - 220, p_y0 - 25), "— 20 EMA", fill="#38bdf8", font=F_AXIS)
    draw.text((p_x1 - 120, p_y0 - 25), "— 50 SMA", fill="#818cf8", font=F_AXIS)

    all_prices = [view['Low'].min(), view['High'].max()]
    if stop: all_prices.append(stop)
    if pivot: all_prices.append(pivot)
    if target: all_prices.append(target)
    
    p_min = min(all_prices) * 0.98
    p_max = max(all_prices) * 1.02
    p_range = p_max - p_min if p_max > p_min else 1.0

    num_grid = 6
    for i in range(num_grid + 1):
        grid_p = p_min + (i / num_grid) * p_range
        grid_y = p_y1 - 15 - (i / num_grid) * (p_y1 - p_y0 - 35)
        draw.line([(p_x0, grid_y), (p_x1, grid_y)], fill="#1a2436", width=1)
        draw.text((p_x1 + 10, grid_y - 7), f"${grid_p:.2f}", fill="#475569", font=F_AXIS)

    draw.text((55, 498), "VOL", fill=TEXT_MUTED, font=F_AXIS)
    v_max = view['Volume'].max() if view['Volume'].max() > 0 else 1.0

    n = len(view)
    step = (p_x1 - p_x0 - 60) / n
    cw = max(step * 0.65, 7)

    def p2y(val):
        return p_y1 - 15 - ((val - p_min) / p_range) * (p_y1 - p_y0 - 35)

    coords = []
    dates = view.index.tolist()

    for i, idx in enumerate(dates):
        row = view.loc[idx]
        cx = p_x0 + 30 + i * step + step / 2
        o, h, l, c, v = row['Open'], row['High'], row['Low'], row['Close'], row['Volume']

        yo, yh, yl, yc = p2y(o), p2y(h), p2y(l), p2y(c)
        col = GREEN if c >= o else RED
        vcol = VOL_GREEN if c >= o else VOL_RED

        draw.line([(cx, yl), (cx, yh)], fill=col, width=2)
        top_y, bot_y = min(yo, yc), max(yo, yc)
        draw.rectangle([(cx - cw/2, top_y), (cx + cw/2, max(bot_y, top_y + 2))], fill=col)

        vh = (v / v_max) * 65
        draw.rectangle([(cx - cw/2, v_y1 - 4 - vh), (cx + cw/2, v_y1 - 4)], fill=vcol)

        if i % 14 == 0:
            draw.text((cx - 18, v_y1 + 6), idx.strftime('%b %d'), fill=TEXT_MUTED, font=F_AXIS)

        coords.append((cx, yc))

    ema20_pts = [(coords[i][0], p2y(view['EMA20'].iloc[i])) for i in range(n) if not pd.isna(view['EMA20'].iloc[i])]
    sma50_pts = [(coords[i][0], p2y(view['SMA50'].iloc[i])) for i in range(n) if not pd.isna(view['SMA50'].iloc[i])]

    for i in range(len(ema20_pts) - 1):
        draw.line([ema20_pts[i], ema20_pts[i+1]], fill="#38bdf8", width=3)
    for i in range(len(sma50_pts) - 1):
        draw.line([sma50_pts[i], sma50_pts[i+1]], fill="#818cf8", width=3)

    if pivot:
        highs = view['High'].values
        search_window = int(n * 0.75)
        candidates = [i for i in range(search_window) if abs(highs[i] - pivot) / pivot <= 0.05]
        piv_idx = candidates[0] if candidates else int(view['High'].iloc[:search_window].values.argmax())

        y_piv = p2y(pivot)
        x_piv_start = coords[piv_idx][0]
        dash_h(draw, x_piv_start, p_x1, y_piv, "#38bdf8", width=2)
        draw.ellipse([(x_piv_start - 3, y_piv - 3), (x_piv_start + 3, y_piv + 3)], fill="#38bdf8")
        axis_flag(draw, p_x1 + 4, y_piv, f"PIVOT ${pivot:.2f}", "#0284c7")

    if stop:
        y_stp = p2y(stop)
        stop_start_x = coords[max(0, n - 18)][0]
        dash_h(draw, stop_start_x, p_x1, y_stp, "#ef4444", width=2)
        draw.ellipse([(stop_start_x - 3, y_stp - 3), (stop_start_x + 3, y_stp + 3)], fill="#ef4444")
        axis_flag(draw, p_x1 + 4, y_stp, f"STOP ${stop:.2f}", "#dc2626")

    if target:
        y_tgt = p2y(target)
        tgt_start_x = coords[max(0, n - 22)][0]
        dash_h(draw, tgt_start_x, p_x1, y_tgt, "#22c55e", width=2)
        axis_flag(draw, p_x1 + 4, y_tgt, f"TARGET ${target:.2f}", "#15803d")

    r_txt = f"{r_ratio:.2f}R" if r_ratio else ">= 3.0R"
    risk_txt = f"{risk_pct:.2f}%" if risk_pct else "2.0% - 3.5%"
    draw.text((65, 615), f"SETUP PAYOFF: {r_txt} ASYMMETRY   |   RISK BUDGET: {risk_txt}   |   INVALIDATION: GAP > +2.5%", fill=TEXT_MAIN, font=F_BODY)

    # TIERED ARCHITECTURE: Resize and highly compress web thumbnails
    if is_thumbnail:
        im = im.resize((600, 337), Image.Resampling.LANCZOS)
        im.save(out_path, format="PNG", optimize=True)
        print(f"[+] Rendered Web Thumbnail: {out_path}")
    else:
        im.save(out_path, format="PNG")
        print(f"[+] Rendered HD Hero Chart: {out_path}")

def generate_social_cards():
    """Generates the 4 core hero charts for the PDF and Twitter pipelines (HD Resolution)."""
    if not os.path.exists(META_FILE):
        return
    with open(META_FILE, "r", encoding="utf-8") as f:
        meta = json.load(f)

    slots = [
        ('top_br', 'Base-Reset', 'carousel_br.png'),
        ('top_htf', 'Momentum Flag', 'carousel_htf.png'),
        ('top_pp', 'Pocket Pivot', 'carousel_pp.png'),
        ('top_ls', 'Liquidity Sweep', 'carousel_ls.png')
    ]

    for key, label, fname in slots:
        cand = meta.get(key)
        if cand and cand.get('Ticker'):
            t = cand.get('Ticker')
            
            p = safe_float(cand.get('Pivot_Trigger'))
            s = safe_float(cand.get('Stop_Loss'))
            r_pct = safe_float(cand.get('Risk_%'))
            struct_res = safe_float(cand.get('Structural_Resistance'))
            
            if not p or not s:
                continue
                
            safe_target, safe_r = calculate_tactical_geometry(p, s, struct_res)
            
            if safe_target and safe_r:
                cand['Tactical_Target'] = round(safe_target, 2)
                cand['Tactical_R_Ratio'] = round(safe_r, 2)
                out_path = os.path.join(OUT_DIR, fname)
                render_ticker_chart(t, label, p, s, r_pct, safe_r, safe_target, out_path, is_thumbnail=False)

    with open(META_FILE, "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=4)

def generate_web_thumbnails():
    """Generates lightweight, downscaled thumbnails for all qualifying items in the terminal feed."""
    if not os.path.exists(FEED_FILE):
        return
    
    # Wipe old thumbnails to prevent repository bloat
    if os.path.exists(THUMB_DIR):
        shutil.rmtree(THUMB_DIR)
    os.makedirs(THUMB_DIR, exist_ok=True)

    with open(FEED_FILE, "r", encoding="utf-8") as f:
        feed = json.load(f)

    watchlists = feed.get("watchlists", {})
    categories = {
        'base_resets': 'Base-Reset',
        'momentum_flags': 'Momentum Flag',
        'pocket_pivots': 'Pocket Pivot',
        'liquidity_sweeps': 'Liquidity Sweep'
    }

    generated = set()
    for cat_key, cat_label in categories.items():
        candidates = watchlists.get(cat_key, [])
        for cand in candidates:
            t = cand.get('Ticker')
            if not t or t in generated:
                continue

            p = safe_float(cand.get('Pivot_Trigger'))
            s = safe_float(cand.get('Stop_Loss'))
            r_pct = safe_float(cand.get('Risk_%'))
            struct_res = safe_float(cand.get('Structural_Resistance'))
            
            if not p or not s:
                continue

            safe_target, safe_r = calculate_tactical_geometry(p, s, struct_res)
            
            if safe_target and safe_r:
                out_path = os.path.join(THUMB_DIR, f"{t}.png")
                # Flag as True to drastically compress and scale down for the web terminal
                render_ticker_chart(t, cat_label, p, s, r_pct, safe_r, safe_target, out_path, is_thumbnail=True)
                generated.add(t)
                time.sleep(0.5)  # Micro-delay to prevent Yahoo Finance IP blocks

def generate_all():
    """Master function called by scanner.py to run both pipelines."""
    print("[*] Generating HD Hero Assets for Social & PDF pipelines...")
    generate_social_cards()
    print("[*] Generating Lightweight Web Thumbnails for Screener Terminal...")
    generate_web_thumbnails()

if __name__ == "__main__":
    generate_all()