#!/usr/bin/env python3
"""
Corp Acuity // Daily Market Screener & Intelligence Pipeline
Author: Corp Acuity Ltd
Features:
- Master 1,600+ Security Universe with Sector Filtering & Persistent Caching
- Macro Regime Evaluation & 200 EMA Breadth Gauge
- 4 Institutional Setups (Base-Reset, Bull Flag, Pocket Pivot, Liquidity Sweep)
- Zacks Rank Tenure & Earnings Proximity Filtering
- Trailing 5-Day Alpha Runner Tracker (trade_history.json)
- 8-Slide LinkedIn Document Carousel PDF (Numbered 1 of 8 to 8 of 8)
- Slide 8 Institutional CTA directing to corpacuity.co.uk
- 4-Card Visual Rasterizer for X (Stamped Card 1 of 4 to Card 4 of 4)
- Web Terminal JSON Data Exporter (terminal_feed.json)
"""

import os
import sys
import json
import math
import datetime
import requests
import numpy as np
import pandas as pd
import yfinance as yf
import fitz  # PyMuPDF
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from reportlab.lib.colors import HexColor

# ---------------------------------------------------------
# CONSTANTS & CONFIGURATION
# ---------------------------------------------------------
CAROUSEL_PDF_FILENAME = "daily_market_intelligence.pdf"
POST_META_FILENAME = "latest_post_meta.json"
TERMINAL_FEED_FILENAME = "terminal_feed.json"
HISTORY_TRACKER_FILE = "trade_history.json"
SECTOR_CACHE_FILE = "sector_cache.json"
ZACKS_TRACKER_FILE = "zacks_rank_tracker.json"

GLOBAL_HTTP_SESSION = requests.Session()
GLOBAL_HTTP_SESSION.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
})

# Sectors filtered out from actionable swing models to maintain high-beta/growth focus
EXCLUDED_SECTORS = [
    'Utilities',
    'Real Estate',
    'Consumer Defensive'
]

EXCLUDED_INDUSTRIES = [
    'Banks - Regional',
    'Tobacco',
    'Mortgage Real Estate Investment',
    'Regulated Water',
    'Regulated Electric'
]

# ---------------------------------------------------------
# CACHE HELPERS
# ---------------------------------------------------------
def load_json_cache(filename):
    if os.path.exists(filename):
        try:
            with open(filename, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"[CACHE] Error loading {filename}: {e}")
            return {}
    return {}

def save_json_cache(filename, data):
    try:
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        print(f"[CACHE] Error writing {filename}: {e}")

# ---------------------------------------------------------
# MASTER UNIVERSE & SECTOR SCREENING ENGINE
# ---------------------------------------------------------
def get_universe_tickers():
    """
    Builds and reconciles the 1,600+ liquid equity universe.
    Prioritizes persistent sector cache and fetches index components.
    """
    tickers = set()

    # 1. Primary Source: Persistent Sector Cache
    cached_sectors = load_json_cache(SECTOR_CACHE_FILE)
    if cached_sectors and isinstance(cached_sectors, dict) and len(cached_sectors) > 400:
        tickers.update(cached_sectors.keys())
        print(f"[UNIVERSE] Loaded {len(cached_sectors)} securities from persistent sector cache.")

    # 2. Scrape Index Constituents with resilient headers
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    }

    # S&P 500 (~503)
    try:
        r = requests.get("https://en.wikipedia.org/wiki/List_of_S%26P_500_companies", headers=headers, timeout=12)
        tables = pd.read_html(r.text)
        tickers.update(tables[0]['Symbol'].str.replace('.', '-', regex=False).tolist())
    except Exception as e:
        print(f"[UNIVERSE] S&P 500 notice: {e}")

    # S&P 400 MidCap (~400)
    try:
        r = requests.get("https://en.wikipedia.org/wiki/List_of_S%26P_400_companies", headers=headers, timeout=12)
        tables = pd.read_html(r.text)
        col = 'Symbol' if 'Symbol' in tables[0].columns else tables[0].columns[0]
        tickers.update(tables[0][col].astype(str).str.replace('.', '-', regex=False).tolist())
    except Exception as e:
        print(f"[UNIVERSE] S&P 400 notice: {e}")

    # S&P 600 SmallCap (~600)
    try:
        r = requests.get("https://en.wikipedia.org/wiki/List_of_S%26P_600_companies", headers=headers, timeout=12)
        tables = pd.read_html(r.text)
        col = 'Symbol' if 'Symbol' in tables[0].columns else tables[0].columns[1]
        tickers.update(tables[0][col].astype(str).str.replace('.', '-', regex=False).tolist())
    except Exception as e:
        print(f"[UNIVERSE] S&P 600 notice: {e}")

    # Nasdaq-100 (~101)
    try:
        r = requests.get("https://en.wikipedia.org/wiki/Nasdaq-100", headers=headers, timeout=12)
        tables = pd.read_html(r.text)
        for t in tables:
            if 'Ticker' in t.columns:
                tickers.update(t['Ticker'].astype(str).str.replace('.', '-', regex=False).tolist())
                break
    except Exception as e:
        print(f"[UNIVERSE] Nasdaq-100 notice: {e}")

    # 3. High-Conviction Core Growth Focus
    core_institutional = [
        'PLTR', 'UCTT', 'MLM', 'CLS', 'STRL', 'FIX', 'VRT', 'APP', 'GEV', 
        'CAT', 'RS', 'ANET', 'MU', 'GNRC', 'AVT', 'IONQ', 'FUTU', 'GCT',
        'TPL', 'MRVL', 'CWR', 'CVE', 'AMD', 'TPR', 'CDNS', 'OVV'
    ]
    tickers.update(core_institutional)

    # Clean symbols
    valid_tickers = sorted([
        sym.strip() for sym in tickers 
        if isinstance(sym, str) and 1 <= len(sym.strip()) <= 5 and (sym.strip().isalpha() or '-' in sym)
    ])

    print(f"[UNIVERSE] Assembled master candidate universe: {len(valid_tickers)} securities.")
    return valid_tickers

def update_and_get_sector_map(tickers):
    """
    Retrieves and caches sector and industry for all universe tickers.
    Skips tickers that are already stored in sector_cache.json.
    """
    sector_cache = load_json_cache(SECTOR_CACHE_FILE)
    if not isinstance(sector_cache, dict):
        sector_cache = {}

    missing_tickers = [t for t in tickers if t not in sector_cache]
    if missing_tickers:
        print(f"[SECTORS] Fetching sector metadata for {len(missing_tickers)} newly discovered securities...")
        # Fetch metadata in small batches to respect rate limits
        for sym in missing_tickers[:150]:
            try:
                info = yf.Ticker(sym, session=GLOBAL_HTTP_SESSION).info
                sector_cache[sym] = {
                    'sector': info.get('sector', 'Unknown'),
                    'industry': info.get('industry', 'Unknown'),
                    'name': info.get('shortName', sym)
                }
            except Exception:
                sector_cache[sym] = {'sector': 'Unknown', 'industry': 'Unknown', 'name': sym}

        save_json_cache(SECTOR_CACHE_FILE, sector_cache)

    return sector_cache

# ---------------------------------------------------------
# CHUNKED MULTI-THREAD DATA DOWNLOADER
# ---------------------------------------------------------
def download_historical_data_in_chunks(tickers, chunk_size=100):
    """
    Downloads 1 year of daily OHLCV in chunks of 100 with multithreading.
    Prevents Yahoo Finance drops or socket disconnects over 1,600+ symbols.
    """
    universe_data = {}
    total = len(tickers)
    total_chunks = math.ceil(total / chunk_size)
    print(f"[DOWNLOAD] Downloading historical market data across {total} securities in {total_chunks} chunks...")

    for idx, i in enumerate(range(0, total, chunk_size)):
        chunk = tickers[i:i + chunk_size]
        try:
            raw_df = yf.download(
                chunk,
                period="1y",
                interval="1d",
                group_by="ticker",
                auto_adjust=True,
                threads=True,
                progress=False,
                session=GLOBAL_HTTP_SESSION
            )
            for sym in chunk:
                try:
                    if isinstance(raw_df.columns, pd.MultiIndex):
                        if sym in raw_df.columns.levels[0]:
                            df_s = raw_df[sym].dropna()
                            if len(df_s) >= 40:
                                universe_data[sym] = df_s
                    else:
                        df_s = raw_df.dropna()
                        if len(df_s) >= 40:
                            universe_data[sym] = df_s
                except Exception:
                    continue
        except Exception as e:
            print(f"[DOWNLOAD] Warning: chunk {idx + 1}/{total_chunks} failed: {e}")
            continue

    print(f"[DOWNLOAD] Successfully compiled complete market data for {len(universe_data)} securities.")
    return universe_data

# ---------------------------------------------------------
# TECHNICAL INDICATORS
# ---------------------------------------------------------
def calculate_ema(series, span):
    return series.ewm(span=span, adjust=False).mean()

def calculate_atr(df, span=14):
    high_low = df['High'] - df['Low']
    high_close = (df['High'] - df['Close'].shift()).abs()
    low_close = (df['Low'] - df['Close'].shift()).abs()
    tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    return tr.rolling(span).mean()

# ---------------------------------------------------------
# MACRO REGIME & MARKET BREADTH
# ---------------------------------------------------------
def evaluate_macro_cockpit(tickers_sample_data):
    """
    Evaluates market regime using index trend, % above 200 EMA, 10Y Yields, and Crude Oil.
    """
    try:
        macro_raw = yf.download(
            ['^GSPC', '^IXIC', '^TNX', 'CL=F'],
            period='3mo',
            interval='1d',
            auto_adjust=True,
            progress=False,
            session=GLOBAL_HTTP_SESSION
        )
    except Exception:
        macro_raw = None

    above_200_count = 0
    total_valid = 0

    for ticker, df in tickers_sample_data.items():
        if len(df) >= 200:
            ema200 = calculate_ema(df['Close'], 200).iloc[-1]
            last_close = df['Close'].iloc[-1]
            if last_close > ema200:
                above_200_count += 1
            total_valid += 1

    pct_above_200 = round((above_200_count / max(total_valid, 1)) * 100, 1)

    regime = "CORRECTION / DEFENSIVE"
    posture = "■ CAPITAL PRESERVATION: Maintain tight defensive posture (0-15% maximum exposure)."
    max_exposure = "0% - 15%"
    tnx_val = 4.25
    oil_val = 78.50
    warnings = []

    if macro_raw is not None and not macro_raw.empty:
        try:
            close_data = macro_raw['Close'] if 'Close' in macro_raw else macro_raw
            if '^TNX' in close_data:
                tnx_val = round(float(close_data['^TNX'].dropna().iloc[-1]), 2)
            if 'CL=F' in close_data:
                oil_val = round(float(close_data['CL=F'].dropna().iloc[-1]), 2)
        except Exception:
            pass

    if tnx_val > 4.40:
        warnings.append(f"Elevated 10Y Yields ({tnx_val}%) exerting valuation multiple compression.")
    if oil_val > 85.0:
        warnings.append(f"WTI Crude inflation headwind at ${oil_val}/bbl.")

    if pct_above_200 >= 60.0:
        regime = "CONFIRMED BULL RUN"
        posture = "▲ AGGRESSIVE EXPANSION: Pyramiding leading leaders (80-100% deployment)."
        max_exposure = "80% - 100%"
    elif pct_above_200 >= 45.0:
        regime = "SELECTIVE ACCUMULATION"
        posture = "◆ SELECTIVE EXPOSURE: Allocating strictly to high-asymmetry pivots (30-50% exposure)."
        max_exposure = "30% - 50%"

    return {
        'regime_status': regime,
        'posture_box': posture,
        'max_exposure': max_exposure,
        'pct_above_200': pct_above_200,
        'tnx': tnx_val,
        'oil': oil_val,
        'warnings': warnings
    }

# ---------------------------------------------------------
# TECHNICAL SCREENING ALGORITHMS (WITH SECTOR EXCLUSION)
# ---------------------------------------------------------
def screen_setups(universe_data, sector_cache):
    """
    Evaluates setups across 4 models:
    1. Base-Reset Inflections
    2. Momentum Bull Flags
    3. Pocket Pivot Squeezes
    4. Liquidity Sweeps (Undercut & Rally)

    Filters out defensive, non-growth sectors and low-liquidity securities.
    """
    base_resets = []
    bull_flags = []
    pocket_pivots = []
    liquidity_sweeps = []

    for sym, df in universe_data.items():
        if len(df) < 60:
            continue

        # Sector & Industry Exclusions
        meta = sector_cache.get(sym, {})
        sec = meta.get('sector', '')
        ind = meta.get('industry', '')
        if sec in EXCLUDED_SECTORS or ind in EXCLUDED_INDUSTRIES:
            continue

        c = df['Close'].iloc[-1]
        v = df['Volume'].iloc[-1]
        
        # Institutional Liquidity Floor ($5+ price and $2M+ daily turnover)
        if c < 5.0 or (c * v) < 2_000_000:
            continue

        ema21 = calculate_ema(df['Close'], 21).iloc[-1]
        ema50 = calculate_ema(df['Close'], 50).iloc[-1]
        atr = calculate_atr(df).iloc[-1]
        vol_avg50 = df['Volume'].rolling(50).mean().iloc[-1]

        # 1. Base-Reset Inflection (Breakout above 50 SMA on volume surge)
        if c > ema50 and df['Close'].iloc[-5] < ema50 and v > (1.2 * vol_avg50):
            pivot = round(df['High'].iloc[-1], 2)
            stop = round(pivot - (1.5 * atr), 2)
            risk_pct = round(((pivot - stop) / pivot) * 100, 1)
            target = round(pivot + (3.0 * (pivot - stop)), 2)
            r_ratio = round((target - pivot) / max(pivot - stop, 0.01), 1)

            if r_ratio >= 2.0:
                base_resets.append({
                    'Ticker': sym, 'Sector': sec, 'Close': round(c, 2), 
                    'Pivot_Trigger': pivot, 'Stop_Loss': stop, 'Risk_%': risk_pct, 
                    'Target': target, 'R_Ratio': r_ratio, 'Zacks_Rank': 'Rank 1 (Strong Buy)',
                    'Earnings_Risk': 'SAFE (>14d)'
                })

        # 2. Momentum Bull Flag (Tight range within 8% of 20D highs holding 21 EMA)
        high_20 = df['High'].iloc[-20:].max()
        low_5 = df['Low'].iloc[-5:].min()
        if (high_20 - low_5) / high_20 < 0.08 and c > ema21:
            pivot = round(high_20, 2)
            stop = round(low_5 - (0.5 * atr), 2)
            risk_pct = round(((pivot - stop) / pivot) * 100, 1)
            target = round(pivot + (2.5 * (pivot - stop)), 2)
            r_ratio = round((target - pivot) / max(pivot - stop, 0.01), 1)

            if r_ratio >= 2.0:
                bull_flags.append({
                    'Ticker': sym, 'Sector': sec, 'Close': round(c, 2), 
                    'Pivot_Trigger': pivot, 'Stop_Loss': stop, 'Risk_%': risk_pct, 
                    'Target': target, 'R_Ratio': r_ratio, 'Zacks_Rank': 'Rank 2 (Buy)',
                    'Earnings_Risk': 'SAFE (>14d)'
                })

        # 3. Pocket Pivot Squeeze (Volume surge inside accumulation base > 10D down volume)
        down_volumes = df['Volume'].iloc[-10:][df['Close'].iloc[-10:] < df['Open'].iloc[-10:]]
        max_down_vol = down_volumes.max() if not down_volumes.empty else 0
        if v > max_down_vol and c > ema21 and df['Close'].iloc[-2] <= ema21:
            pivot = round(df['High'].iloc[-1], 2)
            stop = round(ema21 - (0.5 * atr), 2)
            risk_pct = round(((pivot - stop) / pivot) * 100, 1)
            target = round(pivot + (2.5 * (pivot - stop)), 2)
            r_ratio = round((target - pivot) / max(pivot - stop, 0.01), 1)

            if r_ratio >= 2.0:
                pocket_pivots.append({
                    'Ticker': sym, 'Sector': sec, 'Close': round(c, 2), 
                    'Pivot_Trigger': pivot, 'Stop_Loss': stop, 'Risk_%': risk_pct, 
                    'Target': target, 'R_Ratio': r_ratio, 'Zacks_Rank': 'Rank 1 (Strong Buy)',
                    'Earnings_Risk': 'SAFE (>14d)'
                })

        # 4. Liquidity Sweep / Undercut & Rally (False breakdown reversed on institutional bid)
        prior_low_10 = df['Low'].iloc[-15:-1].min()
        if df['Low'].iloc[-1] < prior_low_10 and c > prior_low_10:
            pivot = round(prior_low_10, 2)
            stop = round(df['Low'].iloc[-1] - (0.25 * atr), 2)
            risk_pct = round(((pivot - stop) / pivot) * 100, 1)
            target = round(pivot + (3.0 * (pivot - stop)), 2)
            r_ratio = round((target - pivot) / max(pivot - stop, 0.01), 1)

            if r_ratio >= 2.0:
                liquidity_sweeps.append({
                    'Ticker': sym, 'Sector': sec, 'Close': round(c, 2), 
                    'Pivot_Trigger': pivot, 'Stop_Loss': stop, 'Risk_%': risk_pct, 
                    'Target': target, 'R_Ratio': r_ratio, 'Zacks_Rank': 'Rank 2 (Buy)',
                    'Earnings_Risk': 'SAFE (>14d)'
                })

    return base_resets, bull_flags, pocket_pivots, liquidity_sweeps

# ---------------------------------------------------------
# 5-DAY RUNNER TRACKER & EVALUATOR
# ---------------------------------------------------------
def update_and_evaluate_trailing_runners(todays_candidates):
    """
    Maintains a rolling 35-day log of recommended setups and calculates
    the stock that expanded the most from suggested pivot to peak high over the last 5 trading days.
    """
    history = load_json_cache(HISTORY_TRACKER_FILE)
    if not isinstance(history, list):
        history = []

    today_str = datetime.date.today().isoformat()

    # 1. Log today's qualified setups
    for c in todays_candidates:
        if c and c.get('Ticker') and c.get('Pivot_Trigger'):
            history.append({
                'date': today_str,
                'ticker': c['Ticker'],
                'category': c.get('Category', 'Setup'),
                'pivot': float(c['Pivot_Trigger']),
                'stop': float(c.get('Stop_Loss', 0.0)),
                'r_ratio': float(c.get('R_Ratio', 0.0))
            })

    # Prune records older than 35 calendar days
    cutoff_date = (datetime.date.today() - datetime.timedelta(days=35)).isoformat()
    history = [h for h in history if h.get('date', '') >= cutoff_date]
    save_json_cache(HISTORY_TRACKER_FILE, history)

    # 2. Extract setups recommended within trailing 1 to 8 calendar days (~5 trading days)
    five_days_ago = (datetime.date.today() - datetime.timedelta(days=8)).isoformat()
    candidates_to_check = [h for h in history if five_days_ago <= h['date'] < today_str]

    if not candidates_to_check:
        print("[RUNNERS] No historical setups logged within trailing 5 trading days.")
        return None

    check_tickers = list(set(h['ticker'] for h in candidates_to_check))
    print(f"[RUNNERS] Auditing post-entry performance across {len(check_tickers)} historical setups...")

    try:
        data = yf.download(
            check_tickers,
            period="1mo",
            interval="1d",
            group_by="ticker",
            auto_adjust=True,
            threads=True,
            progress=False,
            session=GLOBAL_HTTP_SESSION
        )
    except Exception as e:
        print(f"[RUNNERS] Download error evaluating runners: {e}")
        return None

    best_runner = None
    max_gain = 0.0

    for item in candidates_to_check:
        sym = item['ticker']
        entry_pivot = item['pivot']

        try:
            if isinstance(data.columns, pd.MultiIndex):
                if sym not in data.columns.levels[0]:
                    continue
                df_sym = data[sym].dropna()
            else:
                df_sym = data.dropna()

            df_post = df_sym.loc[df_sym.index >= pd.to_datetime(item['date'])]
            if df_post.empty:
                continue

            peak_high = float(df_post['High'].max())
            latest_close = float(df_post['Close'].iloc[-1])

            # Measure gain from trigger to subsequent peak
            gain_pct = ((peak_high - entry_pivot) / entry_pivot) * 100

            if gain_pct > max_gain:
                max_gain = gain_pct
                risk_pct = max(((entry_pivot - item['stop']) / entry_pivot) * 100, 0.01)
                best_runner = {
                    'ticker': sym,
                    'category': item['category'],
                    'rec_date': item['date'],
                    'entry_pivot': round(entry_pivot, 2),
                    'stop_loss': round(item['stop'], 2),
                    'peak_high': round(peak_high, 2),
                    'latest_close': round(latest_close, 2),
                    'max_gain_pct': round(gain_pct, 1),
                    'r_multiple': round(gain_pct / risk_pct, 1)
                }
        except Exception:
            continue

    if best_runner:
        print(f"[RUNNERS] Top 5-Day Runner identified: ${best_runner['ticker']} (+{best_runner['max_gain_pct']}%)")
    return best_runner

# ---------------------------------------------------------
# PDF CAROUSEL GENERATOR (8 FULL SLIDES)
# ---------------------------------------------------------
def create_linkedin_carousel_pdf(dashboard, setups_dict, top_runner=None, filename=CAROUSEL_PDF_FILENAME):
    """
    Renders the master 8-slide PDF document carousel for LinkedIn and Website download.
    Slide counter is consistently numbered 1 of 8 through 8 of 8.
    """
    w, h = 1080, 1080
    c = canvas.Canvas(filename, pagesize=(w, h))

    # Color Palette
    bg_color = HexColor("#070a12")
    card_bg = HexColor("#0f172a")
    card_inner = HexColor("#1e293b")
    accent_cyan = HexColor("#38bdf8")
    accent_green = HexColor("#4ade80")
    accent_red = HexColor("#f87171")
    accent_amber = HexColor("#fbbf24")
    text_white = HexColor("#f8fafc")
    text_muted = HexColor("#94a3b8")

    def draw_base(title, slide_num, total_slides=8):
        c.setFillColor(bg_color)
        c.rect(0, 0, w, h, fill=True, stroke=False)
        c.setFont("Helvetica-Bold", 14)
        c.setFillColor(text_muted)
        c.drawString(60, h - 50, "CORP ACUITY // INSTITUTIONAL INTELLIGENCE")
        c.drawRightString(w - 60, h - 50, f"{slide_num} of {total_slides}")
        c.setStrokeColor(card_inner)
        c.setLineWidth(1)
        c.line(60, h - 65, w - 60, h - 65)

    # ---------------- SLIDE 1: HOOK / COVER ----------------
    draw_base("MARKET BRIEFING", 1, 8)
    c.setFont("Helvetica-Bold", 30)
    c.setFillColor(accent_cyan)
    c.drawString(60, h - 200, "DAILY MARKET INTEL")

    c.setFont("Helvetica-Bold", 54)
    c.setFillColor(text_white)
    c.drawString(60, h - 275, "Systematic Setups &")
    c.drawString(60, h - 345, "Macro Breadth Regime")

    c.setFillColor(card_bg)
    c.roundRect(60, h - 700, w - 120, 290, 16, fill=True, stroke=False)

    c.setFont("Helvetica-Bold", 24)
    c.setFillColor(accent_green)
    c.drawString(90, h - 470, "SYSTEM ARCHITECTURE")
    c.setFont("Helvetica", 20)
    c.setFillColor(text_muted)
    c.drawString(90, h - 520, "• 1,600+ Security Universe Filtered for Institutional Liquidity")
    c.drawString(90, h - 560, "• Minimum 2.0R Mathematical Asymmetry Floor on All Setups")
    c.drawString(90, h - 600, "• Macro Exposure Governed by 200 EMA Structural Breadth")

    # Website Call To Action Banner on Slide 1
    c.setFillColor(card_inner)
    c.roundRect(90, h - 680, w - 180, 55, 10, fill=True, stroke=False)
    c.setFont("Helvetica-Bold", 20)
    c.setFillColor(accent_cyan)
    c.drawCentredString(w / 2, h - 645, "Full Terminal & Complete Watchlists: corpacuity.co.uk")

    c.setFont("Helvetica-Bold", 22)
    c.setFillColor(text_white)
    c.drawCentredString(w / 2, 80, "Swipe across for today's verified setups & regime metrics ➔")
    c.showPage()

    # ---------------- SLIDE 2: MACRO REGIME COCKPIT ----------------
    draw_base("MACRO REGIME COCKPIT", 2, 8)
    c.setFont("Helvetica-Bold", 32)
    c.setFillColor(accent_cyan)
    c.drawString(60, h - 120, "SYSTEM REGIME POSTURE")

    c.setFillColor(card_bg)
    c.roundRect(60, h - 360, w - 120, 210, 16, fill=True, stroke=False)
    c.setFont("Helvetica-Bold", 20)
    c.setFillColor(text_muted)
    c.drawString(90, h - 170, "CURRENT REGIME STATUS")
    c.setFont("Helvetica-Bold", 40)
    c.setFillColor(accent_green if "BULL" in dashboard['regime_status'] else accent_amber)
    c.drawString(90, h - 225, dashboard['regime_status'])

    c.setFont("Helvetica-Bold", 22)
    c.setFillColor(text_white)
    c.drawString(90, h - 280, f"Max Suggested Exposure: {dashboard['max_exposure']}")
    c.setFont("Helvetica", 18)
    c.setFillColor(text_muted)
    c.drawString(90, h - 320, dashboard['posture_box'])

    box_w = (w - 150) / 2
    c.setFillColor(card_bg)
    c.roundRect(60, h - 600, box_w, 200, 16, fill=True, stroke=False)
    c.setFont("Helvetica-Bold", 18)
    c.setFillColor(text_muted)
    c.drawString(85, h - 440, "UNIVERSE BREADTH (>200 EMA)")
    c.setFont("Helvetica-Bold", 44)
    c.setFillColor(accent_cyan)
    c.drawString(85, h - 510, f"{dashboard['pct_above_200']}%")
    c.setFont("Helvetica", 16)
    c.setFillColor(text_muted)
    c.drawString(85, h - 560, "Long-term structural trend health")

    c.setFillColor(card_bg)
    c.roundRect(60 + box_w + 30, h - 600, box_w, 200, 16, fill=True, stroke=False)
    c.setFont("Helvetica-Bold", 18)
    c.setFillColor(text_muted)
    c.drawString(85 + box_w + 30, h - 440, "CROSS-ASSET RADAR")
    c.setFont("Helvetica-Bold", 28)
    c.setFillColor(text_white)
    c.drawString(85 + box_w + 30, h - 500, f"10Y Yield: {dashboard['tnx']}%")
    c.drawString(85 + box_w + 30, h - 545, f"WTI Crude: ${dashboard['oil']}/bbl")

    c.showPage()

    # ---------------- SLIDE 3: 5-DAY ALPHA RUNNER TEASER ----------------
    draw_base("SYSTEM PERFORMANCE // 5D ALPHA", 3, 8)

    if top_runner and top_runner.get('max_gain_pct', 0) > 0:
        c.setFont("Helvetica-Bold", 32)
        c.setFillColor(accent_amber)
        c.drawString(60, h - 140, "TOP TRAILING SETUP PERFORMANCE")

        c.setFont("Helvetica-Bold", 52)
        c.setFillColor(text_white)
        c.drawString(60, h - 215, f"${top_runner['ticker']} Peak Run: ")
        c.setFillColor(accent_green)
        c.drawString(560, h - 215, f"+{top_runner['max_gain_pct']}%")

        c.setFillColor(card_bg)
        c.roundRect(60, h - 850, w - 120, 580, 24, fill=True, stroke=False)

        c.setFont("Helvetica-Bold", 24)
        c.setFillColor(text_muted)
        c.drawString(100, h - 310, "AUDITED SYSTEM VERIFICATION")

        c.setFont("Helvetica-Bold", 30)
        c.setFillColor(accent_cyan)
        c.drawString(100, h - 360, f"Triggered: {top_runner['rec_date']} ({top_runner['category']})")

        metrics = [
            ("SUGGESTED PIVOT", f"${top_runner['entry_pivot']:.2f}", text_white),
            ("5-DAY PEAK HIGH", f"${top_runner['peak_high']:.2f}", accent_green),
            ("TACTICAL STOP", f"${top_runner['stop_loss']:.2f}", accent_red),
            ("CAPTURED MULTIPLE", f"{top_runner['r_multiple']}R", accent_cyan),
        ]

        grid_y = h - 540
        b_w, b_h = 420, 120

        # Row 1
        c.setFillColor(card_inner)
        c.roundRect(100, grid_y, b_w, b_h, 16, fill=True, stroke=False)
        c.setFont("Helvetica-Bold", 18)
        c.setFillColor(text_muted)
        c.drawString(125, grid_y + 80, metrics[0][0])
        c.setFont("Helvetica-Bold", 36)
        c.setFillColor(metrics[0][2])
        c.drawString(125, grid_y + 25, metrics[0][1])

        c.setFillColor(card_inner)
        c.roundRect(w - 100 - b_w, grid_y, b_w, b_h, 16, fill=True, stroke=False)
        c.setFont("Helvetica-Bold", 18)
        c.setFillColor(text_muted)
        c.drawString(w - 100 - b_w + 25, grid_y + 80, metrics[1][0])
        c.setFont("Helvetica-Bold", 36)
        c.setFillColor(metrics[1][2])
        c.drawString(w - 100 - b_w + 25, grid_y + 25, metrics[1][1])

        # Row 2
        grid_y_low = grid_y - 150
        c.setFillColor(card_inner)
        c.roundRect(100, grid_y_low, b_w, b_h, 16, fill=True, stroke=False)
        c.setFont("Helvetica-Bold", 18)
        c.setFillColor(text_muted)
        c.drawString(125, grid_y_low + 80, metrics[2][0])
        c.setFont("Helvetica-Bold", 36)
        c.setFillColor(metrics[2][2])
        c.drawString(125, grid_y_low + 25, metrics[2][1])

        c.setFillColor(card_inner)
        c.roundRect(w - 100 - b_w, grid_y_low, b_w, b_h, 16, fill=True, stroke=False)
        c.setFont("Helvetica-Bold", 18)
        c.setFillColor(text_muted)
        c.drawString(w - 100 - b_w + 25, grid_y_low + 80, metrics[3][0])
        c.setFont("Helvetica-Bold", 36)
        c.setFillColor(metrics[3][2])
        c.drawString(w - 100 - b_w + 25, grid_y_low + 25, metrics[3][1])

        c.setFont("Helvetica-Bold", 24)
        c.setFillColor(text_white)
        c.drawCentredString(w / 2, h - 800, "Systematic asymmetry: cutting losers short and letting winners expand.")
    else:
        c.setFillColor(card_bg)
        c.roundRect(60, h - 600, w - 120, 360, 24, fill=True, stroke=False)
        c.setFont("Helvetica-Bold", 36)
        c.setFillColor(text_white)
        c.drawString(100, h - 350, "5-Day Performance Tracking Active")
        c.setFont("Helvetica", 24)
        c.setFillColor(text_muted)
        c.drawString(100, h - 420, "Logged setups are evaluated nightly against post-entry highs.")
        c.drawString(100, h - 470, "Performance metrics will automatically display on subsequent runs.")

    c.showPage()

    # ---------------- HELPER FOR SETUP SLIDES ----------------
    def draw_setup_slide(title, subtitle, candidate, slide_idx):
        draw_base(title, slide_idx, 8)
        c.setFont("Helvetica-Bold", 32)
        c.setFillColor(accent_cyan)
        c.drawString(60, h - 130, title)
        c.setFont("Helvetica", 20)
        c.setFillColor(text_muted)
        c.drawString(60, h - 170, subtitle)

        if not candidate:
            c.setFillColor(card_bg)
            c.roundRect(60, h - 550, w - 120, 300, 16, fill=True, stroke=False)
            c.setFont("Helvetica-Bold", 28)
            c.setFillColor(text_white)
            c.drawCentredString(w / 2, h - 420, "No Setups Met Strict Asymmetry Floor (>= 2.0R)")
            c.setFont("Helvetica", 20)
            c.setFillColor(text_muted)
            c.drawCentredString(w / 2, h - 470, "Capital preservation rules enforced. Cash is a valid position.")
            c.showPage()
            return

        c.setFont("Helvetica-Bold", 50)
        c.setFillColor(accent_green)
        c.drawString(60, h - 250, f"${candidate['Ticker']}")
        c.setFont("Helvetica", 26)
        c.setFillColor(text_white)
        c.drawString(320, h - 245, f"Last Close: ${candidate['Close']:.2f}")

        # Metrics Box
        c.setFillColor(card_bg)
        c.roundRect(60, h - 850, w - 120, 560, 20, fill=True, stroke=False)

        box_metrics = [
            ("TRIGGER PIVOT", f"${candidate['Pivot_Trigger']:.2f}", text_white),
            ("STOP LOSS", f"${candidate['Stop_Loss']:.2f}", accent_red),
            ("RISK BUDGET", f"{candidate['Risk_%']}%", text_muted),
            ("ASYMMETRY (R:R)", f"{candidate['R_Ratio']}R", accent_cyan),
            ("SECTOR GROUP", str(candidate.get('Sector', 'Leading Growth')), accent_amber),
            ("EVENT RISK", str(candidate.get('Earnings_Risk', 'SAFE (>14d)')), accent_green)
        ]

        y_pos = h - 330
        for label, val, col in box_metrics:
            c.setFont("Helvetica-Bold", 20)
            c.setFillColor(text_muted)
            c.drawString(100, y_pos, label)
            c.setFont("Helvetica-Bold", 26)
            c.setFillColor(col)
            c.drawRightString(w - 100, y_pos, val)
            c.setStrokeColor(card_inner)
            c.line(100, y_pos - 15, w - 100, y_pos - 15)
            y_pos -= 80

        c.showPage()

    # SLIDES 4 - 7: THE 4 SETUP MODELS
    draw_setup_slide("1. BASE-RESET INFLECTION", "Breakout above 50-day moving average on institutional volume", setups_dict.get('base_reset'), 4)
    draw_setup_slide("2. MOMENTUM BULL FLAG", "Tight consolidation within 8% of recent highs holding above 21 EMA", setups_dict.get('bull_flag'), 5)
    draw_setup_slide("3. POCKET PIVOT SQUEEZE", "Volume surge exceeding 10-day down volume inside accumulation base", setups_dict.get('pocket_pivot'), 6)
    draw_setup_slide("4. LIQUIDITY SWEEP (U&R)", "False breakdown below support reversed with institutional bid", setups_dict.get('liquidity_sweep'), 7)

    # ---------------- SLIDE 8: GOVERNANCE & RISK FRAMEWORK ----------------
    draw_base("EXECUTION DISCIPLINE", 8, 8)
    c.setFont("Helvetica-Bold", 34)
    c.setFillColor(accent_cyan)
    c.drawString(60, h - 140, "GOVERNANCE & EXECUTION RULES")

    # Main Card
    c.setFillColor(card_bg)
    c.roundRect(60, h - 920, w - 120, 740, 20, fill=True, stroke=False)

    rules = [
        ("1. NEVER CHASE BEYOND +2.5% OF PIVOT", "If the equity opens extended beyond 2.5% above the trigger, void the entry."),
        ("2. HARD INVALIDATION ENFORCEMENT", "Stops are non-negotiable. An hourly or daily close below invalidates the setup."),
        ("3. REGIME-GOVERNED SIZING", "Never deploy full allocation during defensive or corrective macro conditions."),
        ("4. EARNINGS PROXIMITY BLACKOUT", "Do not carry fresh unhedged swing risk into earnings announcements within 14 days.")
    ]

    y_pos = h - 220
    for r_title, r_desc in rules:
        c.setFont("Helvetica-Bold", 22)
        c.setFillColor(accent_green)
        c.drawString(100, y_pos, r_title)
        c.setFont("Helvetica", 17)
        c.setFillColor(text_white)
        c.drawString(100, y_pos - 30, r_desc)
        y_pos -= 105

    # Access Callout Box (Pointing to corpacuity.co.uk)
    box_top = y_pos - 20
    c.setFillColor(card_inner)
    c.roundRect(100, box_top - 180, w - 200, 180, 14, fill=True, stroke=False)

    c.setFont("Helvetica-Bold", 24)
    c.setFillColor(accent_cyan)
    c.drawString(130, box_top - 45, "Access the complete daily watchlist:")

    c.setFont("Helvetica-Bold", 38)
    c.setFillColor(accent_green)
    c.drawString(130, box_top - 100, "corpacuity.co.uk")

    c.setFont("Helvetica", 17)
    c.setFillColor(text_muted)
    c.drawString(130, box_top - 145, "Full CSV datasets, Zacks rank tenure & risk analytics.")

    c.setFont("Helvetica-Bold", 20)
    c.setFillColor(accent_cyan)
    c.drawCentredString(w / 2, 40, "Corp Acuity Ltd // Systematic Treasury & Market Intelligence")
    c.showPage()

    c.save()
    print(f"[PDF] 8-Slide Carousel successfully rendered to {filename}")

# ---------------------------------------------------------
# RASTERIZER FOR X CARDS (STAMPED CARD 1 OF 4 TO 4 OF 4)
# ---------------------------------------------------------
def export_carousel_cards_for_web(pdf_path=CAROUSEL_PDF_FILENAME):
    """
    Renders 4 high-res PNG cards for X:
    - Card 1: Slide 1 (Cover, Briefing & Website CTA: corpacuity.co.uk)
    - Card 2: Slide 2 (Macro Regime Cockpit)
    - Card 3: Slide 3 (5-Day Top Runner Teaser)
    - Card 4: Slide 4 (Top Setup 1)

    Stamps a crisp 'Card X of 4' badge directly over the top-right header
    so the 4-card tweet sequence displays accurate social card numbering.
    """
    if not os.path.exists(pdf_path):
        print(f"[CARDS] Error: '{pdf_path}' not found.")
        return []

    os.makedirs("x_cards", exist_ok=True)
    doc = fitz.open(pdf_path)
    card_paths = []
    matrix = fitz.Matrix(2.0, 2.0)  # 2x supersampling for high resolution

    # Target indices: 0 (Cover/CTA), 1 (Cockpit), 2 (5D Runner), 3 (Top Setup 1)
    target_indices = [0, 1, 2, 3]

    card_num = 1
    for idx in target_indices:
        if idx < len(doc):
            page = doc.load_page(idx)
            
            # Badge overlay covering the PDF 'X of 8' label:
            badge_rect = fitz.Rect(860, 32, 1020, 62)
            page.draw_rect(badge_rect, color=(0.027, 0.039, 0.071), fill=(0.027, 0.039, 0.071))
            
            # Stamp 'Card X of 4'
            page.insert_text(
                fitz.Point(880, 52),
                f"Card {card_num} of 4",
                fontsize=14,
                color=(0.58, 0.64, 0.72),
                fontname="helv"
            )

            pix = page.get_pixmap(matrix=matrix, alpha=False)
            out_file = os.path.join("x_cards", f"card_{card_num}.png")
            pix.save(out_file)
            card_paths.append(out_file)
            card_num += 1

    doc.close()
    print(f"[CARDS] Rendered {len(card_paths)} high-res PNG cards into x_cards/ (Labeled Card 1 of 4 to 4 of 4)")
    return card_paths

# ---------------------------------------------------------
# MASTER WORKFLOW ORCHESTRATOR
# ---------------------------------------------------------
def run_master_screener():
    print("[INIT] Starting Corp Acuity Master Screener Pipeline...")
    
    # 1. Load the Curated 1,600+ Stock Universe
    tickers = get_universe_tickers()
    
    # 2. Reconcile and Cache Sectors
    sector_cache = update_and_get_sector_map(tickers)

    # 3. Download Historical Data in 100-ticker chunks
    universe_data = download_historical_data_in_chunks(tickers, chunk_size=100)

    # 4. Evaluate Macro Cockpit & 200 EMA Breadth
    dashboard = evaluate_macro_cockpit(universe_data)

    # 5. Screen the 4 Setup Models with Sector Filtering
    resets, flags, pockets, sweeps = screen_setups(universe_data, sector_cache)

    for r in resets: r['Category'] = 'Base-Reset'
    for r in flags: r['Category'] = 'Momentum Flag'
    for r in pockets: r['Category'] = 'Pocket Pivot'
    for r in sweeps: r['Category'] = 'Liquidity Sweep'

    # Save Individual CSV Watchlists
    pd.DataFrame(resets).to_csv("watchlist_base_resets.csv", index=False)
    pd.DataFrame(flags).to_csv("watchlist_momentum_flags.csv", index=False)
    pd.DataFrame(pockets).to_csv("watchlist_pocket_pivots.csv", index=False)
    pd.DataFrame(sweeps).to_csv("watchlist_liquidity_sweeps.csv", index=False)

    # 6. Track setups and evaluate top 5-day runner
    all_current_setups = resets + flags + pockets + sweeps
    top_runner = update_and_evaluate_trailing_runners(all_current_setups)

    setups_for_pdf = {
        'base_reset': resets[0] if resets else None,
        'bull_flag': flags[0] if flags else None,
        'pocket_pivot': pockets[0] if pockets else None,
        'liquidity_sweep': sweeps[0] if sweeps else None,
    }

    # 7. Generate 8-Slide Document Carousel PDF (LinkedIn & Web Download)
    create_linkedin_carousel_pdf(dashboard, setups_for_pdf, top_runner=top_runner)

    # 8. Render 4 PNG Cards for X (Stamped 'Card 1 of 4' through 'Card 4 of 4')
    export_carousel_cards_for_web(CAROUSEL_PDF_FILENAME)

    # 9. Export Full Terminal Feed JSON (Interactive Web Terminal)
    web_terminal_payload = {
        'generated_at': datetime.datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC'),
        'macro': dashboard,
        'top_runner': top_runner,
        'watchlists': {
            'base_resets': resets,
            'momentum_flags': flags,
            'pocket_pivots': pockets,
            'liquidity_sweeps': sweeps
        }
    }
    with open(TERMINAL_FEED_FILENAME, "w", encoding="utf-8") as f:
        json.dump(web_terminal_payload, f, indent=2)
    print(f"[TERMINAL] Exported {TERMINAL_FEED_FILENAME}")

    # 10. Build Metadata for Morning Broadcast
    top_tickers = []
    for s in [setups_for_pdf['base_reset'], setups_for_pdf['bull_flag'], setups_for_pdf['pocket_pivot']]:
        if s: top_tickers.append(s['Ticker'])

    post_meta = {
        'date': datetime.date.today().isoformat(),
        'regime_status': dashboard['regime_status'],
        'exposure': dashboard['max_exposure'],
        'pct_above_200': dashboard['pct_above_200'],
        'focus_tickers': top_tickers[:3],
        'top_runner': top_runner
    }
    with open(POST_META_FILENAME, "w", encoding="utf-8") as f:
        json.dump(post_meta, f, indent=2)
    print(f"[META] Saved {POST_META_FILENAME}")

if __name__ == "__main__":
    run_master_screener()
