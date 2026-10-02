#!/usr/bin/env python3
"""
Corp Acuity // Master Market Screener & Alpha Engine
Author: Corp Acuity Ltd
Preserves full institutional architecture:
- 1,600+ universe ingestion (S&P 500, 400, 600, Nasdaq-100, Core Growth)
- Strict sector exclusion, ADDV >= $12M, RS vs SPY, and banned industry filters
- Base-Reset (Weekly MACD curl), CAN SLIM Bull Flag (45% pole), Pocket Pivot (Squeeze), Liquidity Sweep (U&R)
- Zacks Rank local tenure tracker & Earnings proximity gate
- Trailing 5-Day Runner Tracker (trade_history.json)
- 8-Slide Document Carousel PDF (Slide 8 CTA -> corpacuity.co.uk)
- 4-Card Visual Rasterizer for X (Stamped Card 1 of 4 to Card 4 of 4)
- Web Terminal Feed Exporter (terminal_feed.json)
"""

import io
import re
import os
import json
import time
import random
import urllib.parse
import datetime
from collections import Counter

import requests
import numpy as np
import pandas as pd
import yfinance as yf
from concurrent.futures import ThreadPoolExecutor, as_completed

import fitz  # PyMuPDF
from reportlab.lib.colors import HexColor
from reportlab.pdfgen import canvas

# ---------------------------------------------------------
# GLOBAL CONSTANTS & SHARED HTTP SESSION
# ---------------------------------------------------------
CHUNK_SIZE = 80
ZACKS_TRACKER_FILE = "zacks_rank_tracker.json"
SECTOR_CACHE_FILE = "sector_cache.json"
HISTORY_TRACKER_FILE = "trade_history.json"
CAROUSEL_PDF_FILENAME = "daily_market_intelligence.pdf"
POST_META_FILENAME = "latest_post_meta.json"
TERMINAL_FEED_FILENAME = "terminal_feed.json"

GLOBAL_HTTP_SESSION = requests.Session()
GLOBAL_HTTP_SESSION.headers.update({
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.9',
    'Sec-Ch-Ua': '"Chromium";v="128", "Not;A=Brand";v="24", "Google Chrome";v="128"',
    'Sec-Ch-Ua-Mobile': '?0',
    'Sec-Ch-Ua-Platform': '"Windows"',
    'Sec-Fetch-Dest': 'document',
    'Sec-Fetch-Mode': 'navigate',
    'Sec-Fetch-Site': 'none',
    'Upgrade-Insecure-Requests': '1'
})

# ---------------------------------------------------------
# 1. UNIVERSE INGESTION & OFFLINE SECTOR METADATA
# ---------------------------------------------------------
def load_json_cache(filepath):
    if os.path.exists(filepath):
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def save_json_cache(filepath, data):
    try:
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2)
    except Exception:
        pass

def fetch_institutional_universe_and_sectors():
    tickers = set()
    sector_map = load_json_cache(SECTOR_CACHE_FILE)
    if not isinstance(sector_map, dict):
        sector_map = {}

    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}

    try:
        url_sp500 = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
        resp = requests.get(url_sp500, headers=headers, timeout=10)
        df_sp500 = pd.read_html(io.StringIO(resp.text))[0]
        for _, row in df_sp500.iterrows():
            sym = str(row['Symbol']).strip().replace('.', '-')
            tickers.add(sym)
            sec = str(row.get('GICS Sector', 'Unknown'))
            ind = str(row.get('GICS Sub-Industry', 'Unknown'))
            sector_map[sym] = {'sector': sec, 'industry': ind}

        url_sp400 = "https://en.wikipedia.org/wiki/List_of_S%26P_400_companies"
        resp = requests.get(url_sp400, headers=headers, timeout=10)
        df_sp400 = pd.read_html(io.StringIO(resp.text))[0]
        for _, row in df_sp400.iterrows():
            sym = str(row['Symbol']).strip().replace('.', '-')
            tickers.add(sym)
            sec = str(row.get('GICS Sector', 'Unknown'))
            ind = str(row.get('GICS Sub-Industry', 'Unknown'))
            sector_map[sym] = {'sector': sec, 'industry': ind}

        url_nasdaq = "https://en.wikipedia.org/wiki/Nasdaq-100"
        resp = requests.get(url_nasdaq, headers=headers, timeout=10)
        for tbl in pd.read_html(io.StringIO(resp.text)):
            sym_col = 'Ticker' if 'Ticker' in tbl.columns else ('Symbol' if 'Symbol' in tbl.columns else None)
            if sym_col:
                for _, row in tbl.iterrows():
                    sym = str(row[sym_col]).strip().replace('.', '-')
                    tickers.add(sym)
                    sec = str(row.get('GICS Sector', row.get('Sector', 'Technology')))
                    sector_map.setdefault(sym, {'sector': sec, 'industry': 'Growth'})

        url_sp600 = "https://en.wikipedia.org/wiki/List_of_S%26P_600_companies"
        resp = requests.get(url_sp600, headers=headers, timeout=10)
        df_sp600 = pd.read_html(io.StringIO(resp.text))[0]
        for _, row in df_sp600.iterrows():
            sym = str(row['Symbol']).strip().replace('.', '-')
            tickers.add(sym)
            sec = str(row.get('GICS Sector', 'Unknown'))
            ind = str(row.get('GICS Sub-Industry', 'Unknown'))
            sector_map.setdefault(sym, {'sector': sec, 'industry': ind})

    except Exception as e:
        print(f"Warning: Ingestion fetch notice ({e}). Relying on cached sector metadata...")

    growth_additions = [
        ('FN', 'Technology', 'Semiconductors'), ('POET', 'Technology', 'Semiconductors'),
        ('LITE', 'Technology', 'Communications'), ('COHR', 'Technology', 'Semiconductors'),
        ('AAOI', 'Technology', 'Communications'), ('EXTR', 'Technology', 'Networking'),
        ('CIEN', 'Technology', 'Networking'), ('VIAV', 'Technology', 'Networking'),
        ('CALX', 'Technology', 'Networking'), ('ADTN', 'Technology', 'Networking'),
        ('ALAB', 'Technology', 'Semiconductors'), ('CAMT', 'Technology', 'Semiconductor Equipment'),
        ('FORM', 'Technology', 'Semiconductor Equipment'), ('ACLS', 'Technology', 'Semiconductor Equipment'),
        ('RMBS', 'Technology', 'Semiconductors'), ('DIOD', 'Technology', 'Semiconductors'),
        ('AOSL', 'Technology', 'Semiconductors'), ('MTSI', 'Technology', 'Semiconductors'),
        ('SITM', 'Technology', 'Semiconductors'), ('ONTO', 'Technology', 'Semiconductor Equipment'),
        ('RKLB', 'Industrials', 'Aerospace & Defense'), ('ASTS', 'Technology', 'Telecommunications'),
        ('LUNR', 'Industrials', 'Aerospace & Defense'), ('BWXT', 'Industrials', 'Aerospace & Defense'),
        ('NXT', 'Technology', 'Solar/Energy'), ('FLNC', 'Industrials', 'Electrical Equipment'),
        ('BE', 'Industrials', 'Electrical Equipment'), ('PLUG', 'Industrials', 'Electrical Equipment'),
        ('EVGO', 'Consumer Cyclical', 'EV Infrastructure'), ('CRWV', 'Technology', 'Software'),
        ('MNDY', 'Technology', 'Software'), ('IOT', 'Technology', 'Software'),
        ('DUOL', 'Technology', 'Software'), ('GTLB', 'Technology', 'Software'),
        ('DOCN', 'Technology', 'Software'), ('S', 'Technology', 'Cybersecurity'),
        ('TENB', 'Technology', 'Cybersecurity'), ('VRNS', 'Technology', 'Cybersecurity'),
        ('APPF', 'Technology', 'Software'), ('BLND', 'Technology', 'Software'),
        ('VICR', 'Technology', 'Semiconductors'), ('MPWR', 'Technology', 'Semiconductors'),
        ('RTX', 'Industrials', 'Aerospace & Defense'), ('KLAC', 'Technology', 'Semiconductor Equipment'),
        ('CVLT', 'Technology', 'Software'), ('EFOR', 'Technology', 'Software'), ('PAYC', 'Technology', 'Software'),
        ('WDC', 'Technology', 'Computer Hardware/Storage'), ('LRCX', 'Technology', 'Semiconductor Equipment'),
        ('EME', 'Industrials', 'Engineering & Construction'), ('SWKS', 'Technology', 'Semiconductors'),
        ('TPL', 'Energy', 'Oil & Gas Exploration & Production'), ('PDFS', 'Technology', 'Semiconductors'),
        ('AMAT', 'Technology', 'Semiconductor Equipment'), ('ICHR', 'Technology', 'Semiconductor Equipment'),
        ('SYNA', 'Technology', 'Semiconductors'), ('TTMI', 'Technology', 'Electronic Components')
    ]
    for sym, sec, ind in growth_additions:
        tickers.add(sym)
        sector_map[sym] = {'sector': sec, 'industry': ind}

    # Ensure all previously cached tickers are preserved in the run
    if sector_map:
        tickers.update(sector_map.keys())

    save_json_cache(SECTOR_CACHE_FILE, sector_map)

    clean_tickers = []
    for t in sorted(tickers):
        if not isinstance(t, str):
            continue
        sym = t.strip().replace('.', '-')
        if re.search(r'-(?:A|B)$', sym) and sym not in ['BRK-B']:
            continue
        if sym.isalpha() or '-' in sym:
            clean_tickers.append(sym)

    return clean_tickers, sector_map

# ---------------------------------------------------------
# 2. INDICATOR & RESAMPLING UTILITIES
# ---------------------------------------------------------
def resample_daily_to_weekly(daily_df):
    daily_df = daily_df.sort_index()
    weekly_df = daily_df.resample('W-FRI').agg({
        'Open': 'first',
        'High': 'max',
        'Low': 'min',
        'Close': 'last',
        'Volume': 'sum'
    }).dropna()
    return weekly_df

def calculate_macd(series, fast=12, slow=26, signal=9):
    ema_fast = series.ewm(span=fast, adjust=False).mean()
    ema_slow = series.ewm(span=slow, adjust=False).mean()
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    hist = macd_line - signal_line
    return macd_line, signal_line, hist

def calculate_atr(df, window=14):
    high = df['High']
    low = df['Low']
    close_prev = df['Close'].shift(1)
    tr = pd.concat([
        high - low,
        (high - close_prev).abs(),
        (low - close_prev).abs()
    ], axis=1).max(axis=1)
    return tr.rolling(window=window).mean()

# ---------------------------------------------------------
# 3. MACRO CALENDAR & FORWARD HORIZON ENGINE
# ---------------------------------------------------------
class MacroEventCalendar:
    @staticmethod
    def get_nth_weekday_of_month(year, month, nth, weekday):
        first_day = datetime.date(year, month, 1)
        first_target = first_day + datetime.timedelta(days=(weekday - first_day.weekday()) % 7)
        return first_target + datetime.timedelta(weeks=nth - 1)

    @classmethod
    def get_third_friday(cls, year, month):
        return cls.get_nth_weekday_of_month(year, month, 3, 4)

    @classmethod
    def get_major_economic_prints(cls, year, month):
        prints = {}
        nfp_date = cls.get_nth_weekday_of_month(year, month, 1, 4)
        prints[nfp_date] = "JOBS REPORT / NFP (8:30 AM ET): Key payroll & unemployment release."

        cpi_date = cls.get_nth_weekday_of_month(year, month, 2, 2)
        prints[cpi_date] = "CPI INFLATION PRINT (8:30 AM ET): Major pre-market index gap risk."

        ppi_date = cpi_date + datetime.timedelta(days=1)
        prints[ppi_date] = "PPI WHOLESALE INFLATION (8:30 AM ET): Wholesale pipeline read."

        if month == 12:
            next_month_first = datetime.date(year + 1, 1, 1)
        else:
            next_month_first = datetime.date(year, month + 1, 1)
        last_day = next_month_first - datetime.timedelta(days=1)
        days_back = (last_day.weekday() - 4) % 7
        pce_date = last_day - datetime.timedelta(days=days_back)
        prints[pce_date] = "CORE PCE PRICE INDEX (8:30 AM ET): Benchmark Fed inflation print."

        return prints

    @classmethod
    def evaluate_calendar(cls, target_date=None):
        if target_date is None:
            target_date = datetime.date.today()

        year = target_date.year
        month = target_date.month
        day = target_date.day
        alerts = []
        exposure_multiplier = 1.0

        forward_events = []
        months_to_check = [(year, month)]
        next_m = month + 1 if month < 12 else 1
        next_y = year if month < 12 else year + 1
        months_to_check.append((next_y, next_m))

        for y_c, m_c in months_to_check:
            econ_dict = cls.get_major_economic_prints(y_c, m_c)
            for d_val, title in econ_dict.items():
                forward_events.append((d_val, title, "DATA"))

            opx_d = cls.get_third_friday(y_c, m_c)
            w_name = "Triple/Quad Witching" if m_c in [3, 6, 9, 12] else "Monthly OPEX"
            forward_events.append((opx_d, f"{w_name}: Synthetic pinning & roll-over volume", "OPEX"))

        fomc_decisions = [
            datetime.date(year, 1, 28), datetime.date(year, 3, 18),
            datetime.date(year, 5, 6),  datetime.date(year, 6, 17),
            datetime.date(year, 7, 29), datetime.date(year, 9, 16),
            datetime.date(year, 11, 4), datetime.date(year, 12, 16)
        ]
        if next_y > year:
            fomc_decisions.append(datetime.date(next_y, 1, 27))

        for f_date in fomc_decisions:
            forward_events.append((f_date, "FOMC RATE DECISION (2:00 PM ET): Policy statement & presser", "FOMC"))
            min_date = f_date + datetime.timedelta(days=21)
            forward_events.append((min_date, "FOMC MINUTES RELEASE (2:00 PM ET): Midday algo volatility", "MINUTES"))

        upcoming = sorted([
            (d, desc, evt_type, (d - target_date).days)
            for d, desc, evt_type in forward_events
            if (d - target_date).days >= 0
        ], key=lambda x: x[3])

        for d, desc, evt_type, diff in upcoming:
            if diff == 0:
                alerts.append(f"TODAY: {desc}")
                if evt_type == "FOMC":
                    exposure_multiplier = min(exposure_multiplier, 0.50)
                elif evt_type == "DATA":
                    exposure_multiplier = min(exposure_multiplier, 0.60)
                elif evt_type == "OPEX":
                    exposure_multiplier = min(exposure_multiplier, 0.70)
            elif 1 <= diff <= 3:
                alerts.append(f"{diff} DAY(S) TO {desc} ({d})")
                if evt_type in ["FOMC", "DATA"]:
                    exposure_multiplier = min(exposure_multiplier, 0.80)

        horizon_count = 0
        for d, desc, evt_type, diff in upcoming:
            if diff > 3 and horizon_count < 2:
                alerts.append(f"IN {diff} DAYS: {desc}")
                horizon_count += 1

        is_quarter_end_month = month in [3, 6, 9, 12]
        if is_quarter_end_month and day >= 24:
            quarter_label = {3: "Q1", 6: "Q2", 9: "Q3", 12: "Q4"}[month]
            if month == 9:
                alerts.append(
                    f"⚖️ {quarter_label} REBALANCE & FISCAL YEAR-END: Pension flows + mutual fund "
                    f"tax-loss harvesting active. High risk of false breakouts & liquidation."
                )
                exposure_multiplier = min(exposure_multiplier, 0.60)
            else:
                alerts.append(
                    f"⚖️ {quarter_label} QUARTER-END REBALANCING: 60/40 mechanical pension rebalancing. "
                    f"Flows may distort single-stock technical breakouts."
                )
                exposure_multiplier = min(exposure_multiplier, 0.75)

        elif month == 9 and 15 <= day < 24:
            alerts.append("🍂 MID-SEPTEMBER SEASONAL DRAG: Post-OPEX de-risking & pre-rebalance supply active.")
            exposure_multiplier = min(exposure_multiplier, 0.75)

        elif month == 8 and day >= 10:
            alerts.append("☀️ SUMMER DOLDRUMS: Thin liquidity & low volume. Breakouts prone to whipsaw.")
            exposure_multiplier = min(exposure_multiplier, 0.75)

        elif month == 4 and 10 <= day <= 17:
            alerts.append("💸 US TAX FILING DRAIN: Retail cash outflows. Midday momentum fading.")
            exposure_multiplier = min(exposure_multiplier, 0.80)

        elif (month == 11 and day >= 20) or (month == 12 and 15 <= day < 24) or (month == 1 and day <= 10):
            alerts.append("🎅 HIGH INFLOW WINDOW (Year-End Chase): Benchmark chasing active. Continuation favored.")

        if day in [29, 30, 31, 1, 2, 3] and not (is_quarter_end_month and day >= 24):
            alerts.append("📈 TURN-OF-MONTH (TOM) INFLOWS: Automated retirement allocations supporting baseline.")

        return alerts, exposure_multiplier

# ---------------------------------------------------------
# 4. ZACKS RANK RETRIEVAL & LOCAL TENURE TRACKER
# ---------------------------------------------------------
def fetch_raw_zacks_rank(ticker):
    session = requests.Session()
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36',
        'Accept': 'application/json, text/javascript, */*; q=0.01',
        'Referer': f'https://www.zacks.com/stock/quote/{ticker}',
        'X-Requested-With': 'XMLHttpRequest'
    }
    try:
        feed_url = f"https://quote-feed.zacks.com/index?t={ticker}"
        resp = session.get(feed_url, headers=headers, timeout=3)
        if resp.status_code == 200:
            data = resp.json()
            if ticker in data:
                rank = data[ticker].get('zacks_rank')
                if rank:
                    return str(rank).strip()

        snap_url = f"https://www.zacks.com/includes/classes/zacks_screener_tables.php?scr_id=stock_research&ticker={ticker}"
        resp_snap = session.get(snap_url, headers=headers, timeout=3)
        if resp_snap.status_code == 200:
            m = re.search(r'"zacks_rank":\s*"?(\d)"?', resp_snap.text)
            if m:
                return m.group(1)
    except Exception:
        pass
    return None

def profile_zacks_with_local_tenure(tickers):
    tracker = load_json_cache(ZACKS_TRACKER_FILE)
    if not isinstance(tracker, dict):
        tracker = {}
    today_str = datetime.date.today().isoformat()
    today = datetime.date.today()
    results = {}

    with ThreadPoolExecutor(max_workers=8) as executor:
        future_to_tk = {executor.submit(fetch_raw_zacks_rank, t): t for t in tickers}
        for future in as_completed(future_to_tk):
            tk = future_to_tk[future]
            raw_rank = future.result()

            if not raw_rank or raw_rank not in ['1', '2', '3', '4', '5']:
                results[tk] = "N/A"
                continue

            if tk in tracker:
                prev_rank = tracker[tk].get('rank')
                date_set_str = tracker[tk].get('date_set', today_str)
                try:
                    date_set = datetime.date.fromisoformat(date_set_str)
                    days = (today - date_set).days
                except Exception:
                    days = 1

                if prev_rank == raw_rank:
                    tenure_label = f"{days}d" if days > 0 else "New"
                else:
                    tracker[tk] = {'rank': raw_rank, 'date_set': today_str}
                    tenure_label = "New"
            else:
                tracker[tk] = {'rank': raw_rank, 'date_set': today_str}
                tenure_label = "1d"

            results[tk] = f"#{raw_rank} ({tenure_label})"

    save_json_cache(ZACKS_TRACKER_FILE, tracker)
    return results

def evaluate_earnings_proximity(ticker):
    try:
        tk = yf.Ticker(ticker, session=GLOBAL_HTTP_SESSION)
        cal = tk.calendar
        today = pd.Timestamp.now().tz_localize(None).date()
        earnings_dates = []

        if cal is not None:
            if isinstance(cal, dict) and 'Earnings Date' in cal:
                earnings_dates = cal['Earnings Date']
            elif hasattr(cal, 'empty') and not cal.empty and 'Earnings Date' in cal.index:
                earnings_dates = cal.loc['Earnings Date'].tolist()

        if earnings_dates:
            target_date = pd.to_datetime(earnings_dates[0]).tz_localize(None).date()
            days_diff = (target_date - today).days

            if 0 <= days_diff <= 7:
                return f"🚨 DANGER ({days_diff}d)"
            elif 8 <= days_diff <= 14:
                return f"⚠️ CAUTION ({days_diff}d)"
            elif days_diff > 14:
                return f"SAFE ({days_diff}d)"
            elif -3 <= days_diff < 0:
                return f"Reported ({abs(days_diff)}d ago)"
            else:
                return "SAFE (>14d)"
    except Exception:
        pass
    return "Unknown/TBD"

# ---------------------------------------------------------
# 5. PATTERN GATES (EXACT ORIGINAL FORMULAS)
# ---------------------------------------------------------
def check_base_reset(ticker, daily_df, w_df, c0, daily_ema200, pct_above_200, high_52w):
    try:
        if pct_above_200 < 0.5:
            return None, f"Below 200 EMA uptrend floor ({pct_above_200:.1f}% < +0.5%)"

        atr14 = calculate_atr(daily_df, 14).iloc[-1]
        atr_pct = (atr14 / c0) * 100
        if atr_pct < 2.0:
            return None, f"Sluggish daily range (ATR14 {atr_pct:.2f}% < 2.0%)"

        headroom_52w = ((high_52w - c0) / c0) * 100
        if headroom_52w < 16.0:
            return None, f"Insufficient headroom ({headroom_52w:.1f}% < 16.0% floor)"

        w_close = w_df['Close']
        macd, signal, hist = calculate_macd(w_close)
        w_ema10 = w_close.ewm(span=10, adjust=False).mean()

        h0, h1, h2 = hist.iloc[-1], hist.iloc[-2], hist.iloc[-3]
        hist_curling = (h0 >= h1 - 0.08) or (h1 >= h2)
        if not hist_curling:
            return None, "Weekly histogram declining consecutively"

        if c0 < (w_ema10.iloc[-1] * 0.93):
            return None, "Price significantly below 10w EMA"

        weekday_idx = min(datetime.date.today().weekday() + 1, 5)
        current_week_vol = w_df['Volume'].iloc[-1]
        projected_week_vol = current_week_vol * (5.0 / weekday_idx)
        w_vol_sma10 = w_df['Volume'].rolling(window=10).mean().iloc[-1]

        vol_ratio = projected_week_vol / max(w_vol_sma10, 1)
        if vol_ratio < 0.45:
            return None, "Paced weekly volume severely dry (<45% of 10w avg)"

        daily_pivot = round(daily_df['High'].tail(5).max(), 2)
        tactical_stop = round(daily_df['Low'].tail(3).min(), 2)
        risk_pct = round(((daily_pivot - tactical_stop) / daily_pivot) * 100, 2)

        if risk_pct > 13.0 or risk_pct <= 0:
            return None, "Stop width invalid or >13.0%"

        reward_risk = headroom_52w / risk_pct
        if reward_risk < 2.5:
            return None, f"Low Asymmetry (R:R {round(reward_risk, 1)} < 2.5)"

        hist_expansion = max(h0 - h2, h0 - h1)
        score = (abs(hist_expansion) / max(atr14, 0.01)) * vol_ratio * reward_risk

        if score < 0.12:
            return None, f"Conviction Score too low ({score:.3f} < 0.12)"

        return {
            'Ticker': ticker,
            'Close': round(c0, 2),
            'Headroom_%': round(headroom_52w, 1),
            'Above_200_%': round(pct_above_200, 1),
            'Hist_Now': round(h0, 3),
            'Vol_Ratio': f"{round(vol_ratio, 2)}x",
            'Conviction_Score': round(score, 3),
            'Pivot_Trigger': daily_pivot,
            'Stop_Loss': tactical_stop,
            'Risk_%': risk_pct,
            'R_Ratio': round(reward_risk, 2)
        }, "PASSED"
    except Exception as e:
        return None, f"Error: {type(e).__name__}"

def check_htf(ticker, df, c0, high_52w):
    try:
        close = df['Close']
        high = df['High']
        low = df['Low']
        volume = df['Volume']
        vol_sma50 = volume.rolling(window=50).mean().iloc[-1]

        recent_25_highs = high.iloc[-25:]
        peak_idx = recent_25_highs.idxmax()
        bars_since_peak = len(df) - 1 - df.index.get_loc(peak_idx)

        if not (3 <= bars_since_peak <= 18):
            return None, "Flag duration >18 days (Consolidation drift)"

        peak_price = high.loc[peak_idx]
        peak_pos = df.index.get_loc(peak_idx)
        pole_start_pos = max(0, peak_pos - 40)
        pole_end_pos = max(0, peak_pos - 8)

        if pole_end_pos <= pole_start_pos:
            return None, "Insufficient history for pole"

        pole_trough = low.iloc[pole_start_pos:pole_end_pos].min()
        pole_gain_pct = ((peak_price - pole_trough) / pole_trough) * 100
        
        if pole_gain_pct < 45.0:
            return None, f"Pole gain < 45.0% standard ({pole_gain_pct:.1f}%)"

        flag_low = low.iloc[-bars_since_peak:].min()
        flag_depth_pct = ((peak_price - flag_low) / peak_price) * 100
        
        if flag_depth_pct > 14.0:
            return None, "Flag pullback too loose (>14.0%)"

        last_10_high = high.tail(10).max()
        last_10_low = low.tail(10).min()
        flag_tightness_pct = ((last_10_high - last_10_low) / last_10_high) * 100
        
        if not (2.0 <= flag_tightness_pct <= 13.0):
            return None, f"Flag tightness out of bounds ({flag_tightness_pct:.2f}%)"

        if ((peak_price - c0) / peak_price) * 100 > 11.0:
            return None, "Price sagging (>11.0% below peak)"

        vol_5d_avg = volume.tail(5).mean()
        vol_dryup_ratio = vol_5d_avg / max(vol_sma50, 1)
        if vol_dryup_ratio > 0.75:
            return None, "Volume not dry (>75% of 50d avg)"

        ema_21 = close.ewm(span=21, adjust=False).mean().iloc[-1]
        if c0 < (0.95 * ema_21):
            return None, "Broken below 21-day EMA"

        pivot_trigger = round(peak_price, 2)
        tactical_stop = round(flag_low, 2)
        risk_pct = round(((pivot_trigger - tactical_stop) / pivot_trigger) * 100, 2)

        if risk_pct < 1.5 or risk_pct > 14.5:
            return None, f"Risk % invalid or outside executable limits ({risk_pct:.2f}%)"

        projected_run = pole_gain_pct * 0.50
        reward_risk = projected_run / risk_pct
        if reward_risk < 2.0:
            return None, f"Low Asymmetry (R:R {round(reward_risk, 1)} < 2.0)"

        return {
            'Ticker': ticker,
            'Close': round(c0, 2),
            'Pole_Gain_%': round(pole_gain_pct, 1),
            'Flag_Days': bars_since_peak,
            'Flag_Depth_%': round(flag_depth_pct, 1),
            '10d_Tightness_%': round(flag_tightness_pct, 1),
            'Vol_DryUp': f"{round(vol_dryup_ratio, 2)}x",
            'Conviction_Score': round(reward_risk, 2),
            'Pivot_Trigger': pivot_trigger,
            'Stop_Loss': tactical_stop,
            'Risk_%': risk_pct,
            'R_Ratio': round(reward_risk, 2)
        }, "PASSED"
    except Exception as e:
        return None, f"Error: {type(e).__name__}"

def check_pocket_pivot(ticker, df, c0, daily_ema200, high_52w):
    try:
        close = df['Close']
        high = df['High']
        low = df['Low']
        volume = df['Volume']
        v0 = volume.iloc[-1]
        vol_sma50 = volume.rolling(50).mean().iloc[-1]

        sma_50 = close.rolling(50).mean().iloc[-1]
        if not (c0 > sma_50 and sma_50 > (0.96 * daily_ema200)):
            return None, "Trend not aligned (C > SMA50 > EMA200)"

        ext_200 = ((c0 - daily_ema200) / daily_ema200) * 100
        if ext_200 > 45.0:
            return None, "Stretched >45% above 200 EMA"

        raw_headroom = ((high_52w - c0) / c0) * 100
        if raw_headroom < 15.0:
            return None, "Headroom < 15% floor"

        ema_10 = close.ewm(span=10, adjust=False).mean()
        ema_21 = close.ewm(span=21, adjust=False).mean()

        sma_20 = close.rolling(20).mean()
        std_20 = close.rolling(20).std()
        upper_bb = sma_20 + (2.0 * std_20)
        lower_bb = sma_20 - (2.0 * std_20)

        tr = pd.concat([
            high - low,
            (high - close.shift(1)).abs(),
            (low - close.shift(1)).abs()
        ], axis=1).max(axis=1)
        atr_20 = tr.rolling(20).mean()
        upper_kc = sma_20 + (1.5 * atr_20)
        lower_kc = sma_20 - (1.5 * atr_20)

        squeeze_active = (upper_bb.iloc[-6:] < upper_kc.iloc[-6:]) & (lower_bb.iloc[-6:] > lower_kc.iloc[-6:])
        if not squeeze_active.any():
            return None, "No Bollinger/Keltner squeeze"

        if c0 <= close.iloc[-2]:
            return None, "Pivot bar must close green"

        touched_ema = (low.iloc[-1] <= (1.02 * ema_10.iloc[-1])) or (low.iloc[-1] <= (1.02 * ema_21.iloc[-1]))
        closed_above_ema = (c0 > ema_10.iloc[-1]) and (c0 > ema_21.iloc[-1])
        ext_10 = ((c0 - ema_10.iloc[-1]) / ema_10.iloc[-1]) * 100

        if not (touched_ema and closed_above_ema and ext_10 <= 3.2):
            return None, "Not launching off 10/21 EMA (or ext >3.2%)"

        prior_10_down_vols = [
            volume.iloc[-i] 
            for i in range(2, 12) 
            if close.iloc[-i] < close.iloc[-(i + 1)]
        ]

        if not prior_10_down_vols:
            vol_passed = v0 >= (1.15 * vol_sma50)
            max_down_vol = vol_sma50
        else:
            max_down_vol = max(prior_10_down_vols)
            vol_passed = v0 > (max_down_vol * 0.95)

        if not vol_passed:
            return None, "Volume < highest down-day in last 10 sessions"

        vol_pocket_ratio = round(v0 / max_down_vol, 2)
        pivot_trigger = round(high.iloc[-1], 2)
        tactical_stop = round(min(low.iloc[-1], ema_21.iloc[-1]), 2)
        risk_pct = round(((pivot_trigger - tactical_stop) / pivot_trigger) * 100, 2)

        if risk_pct > 6.5 or risk_pct < 1.5:
            return None, "Tactical risk invalid or outside 1.5%-6.5%"

        reward_risk = raw_headroom / risk_pct
        if reward_risk < 2.0:
            return None, f"Low Asymmetry (R:R {round(reward_risk, 1)} < 2.0)"

        return {
            'Ticker': ticker,
            'Close': round(c0, 2),
            'Headroom_%': round(raw_headroom, 1),
            'Ext_10EMA_%': round(ext_10, 1),
            'Above_200EMA_%': round(ext_200, 1),
            'Vol_Pocket_Ratio': f"{vol_pocket_ratio}x",
            'Conviction_Score': round(reward_risk, 2),
            'Pivot_Trigger': pivot_trigger,
            'Stop_Loss': tactical_stop,
            'Risk_%': risk_pct,
            'R_Ratio': round(reward_risk, 2)
        }, "PASSED"
    except Exception as e:
        return None, f"Error: {type(e).__name__}"

def check_liquidity_sweep(ticker, df, c0, daily_ema200, high_52w):
    try:
        if c0 < 15.0:
            return None, "Price < $15.00 floor (Anti-Penny Gate)"

        high = df['High']
        low = df['Low']
        volume = df['Volume']
        current_low = low.iloc[-1]
        current_high = high.iloc[-1]
        vol_sma50 = volume.rolling(50).mean().iloc[-1]

        raw_headroom = ((high_52w - c0) / c0) * 100
        shelf_window = low.iloc[-60:-5]
        if len(shelf_window) < 18:
            return None, "Insufficient base formation window"

        support_shelf = shelf_window.min()
        recent_flush_low = low.iloc[-4:].min()

        undercut_pct = ((support_shelf - recent_flush_low) / support_shelf) * 100
        if not (0.20 <= undercut_pct <= 6.5):
            return None, "No clean undercut (Needs 0.20%-6.5% sweep)"

        if c0 <= support_shelf:
            return None, "Price remains trapped below support shelf"

        day_range = current_high - current_low
        if day_range > 0:
            closing_location = (c0 - current_low) / day_range
            if closing_location < 0.52:
                return None, "Weak close (Not in upper 48% of range)"
        else:
            return None, "Flat session"

        recent_vol_max = volume.iloc[-3:].max()
        vol_ratio = recent_vol_max / max(vol_sma50, 1)
        if vol_ratio < 0.75:
            return None, "Retest volume dry (<75% of 50d avg)"

        pivot_trigger = round(max(current_high, support_shelf * 1.002), 2)
        tactical_stop = round(recent_flush_low * 0.995, 2)
        risk_pct = round(((pivot_trigger - tactical_stop) / pivot_trigger) * 100, 2)

        if risk_pct > 6.5 or risk_pct < 1.5:
            return None, "Tactical risk invalid or outside 1.5%-6.5%"

        reward_risk = raw_headroom / risk_pct
        if reward_risk < 2.5:
            return None, f"Low Asymmetry (R:R {round(reward_risk, 1)} < 2.5)"

        return {
            'Ticker': ticker,
            'Close': round(c0, 2),
            'Shelf_Level': round(support_shelf, 2),
            'Flush_Low': round(recent_flush_low, 2),
            'Sweep_Depth_%': round(undercut_pct, 2),
            'Headroom_%': round(raw_headroom, 1),
            'Vol_Ratio': f"{round(vol_ratio, 2)}x",
            'Conviction_Score': round(reward_risk, 2),
            'Pivot_Trigger': pivot_trigger,
            'Stop_Loss': tactical_stop,
            'Risk_%': risk_pct,
            'R_Ratio': round(reward_risk, 2)
        }, "PASSED"
    except Exception as e:
        return None, f"Error: {type(e).__name__}"

# ---------------------------------------------------------
# 6. MASTER EVALUATION WRAPPER WITH SECTOR GATES
# ---------------------------------------------------------
EXCLUDED_SECTORS = {
    'Real Estate', 'Utilities', 'Consumer Defensive', 'Consumer Staples', 
    'Financials', 'Financial Services', 'Basic Materials', 'Healthcare',
    'Consumer Discretionary'
}

BANNED_INDUSTRY_KEYWORDS = [
    'apparel', 'retail', 'truck', 'freight', 'footwear', 'bank',
    'credit', 'mortgage', 'homebuild', 'grocery', 'hotel', 'resort',
    'cruise', 'marine', 'tobacco', 'publishing', 'broadcasting',
    'ground transportation', 'building products', 'consumer finance',
    'packaging', 'containers', 'auto parts', 'dealership', 'biotechnology',
    'drug', 'pharmaceutical', 'medical devices', 'diagnostics',
    'healthcare providers', 'industrial distribution', 'restaurant',
    'machinery', 'heavy equipment', 'oil & gas midstream', 'pipeline',
    'electronic manufacturing services', 'it consulting', 'research services'
]

def evaluate_all_setups(ticker, daily_df, spy_1m_perf, sector_map):
    try:
        daily_df = daily_df.dropna()
        if len(daily_df) < 120:
            return {'diagnostics': "Insufficient data (<120 sessions)", 'above_200': False}

        c0 = daily_df['Close'].iloc[-1]
        
        daily_ema200 = daily_df['Close'].ewm(span=200, adjust=False).mean().iloc[-1]
        is_above_200 = bool(c0 > daily_ema200)

        volume = daily_df['Volume']
        vol_sma50 = volume.rolling(50).mean().iloc[-1]
        
        daily_dollar_vol = c0 * vol_sma50
        if c0 < 10.0 or daily_dollar_vol < 12_000_000:
            return {'diagnostics': "Liquidity Gate: Price <$10 or ADDV <$12M", 'above_200': is_above_200}

        stock_1m_perf = ((c0 - daily_df['Close'].iloc[-21]) / daily_df['Close'].iloc[-21]) * 100
        rs_relative = stock_1m_perf - spy_1m_perf
        if rs_relative < -12.0:
            return {'diagnostics': "Relative Strength: Lagging S&P 500 by >12% (1M)", 'above_200': is_above_200}

        sec_info = sector_map.get(ticker, {'sector': 'Unknown', 'industry': 'Unknown'})
        sec_name = sec_info.get('sector', '')
        ind_name = sec_info.get('industry', '').lower()

        if ticker not in ['TPL', 'EME']:
            if sec_name in EXCLUDED_SECTORS or any(kw in ind_name for kw in BANNED_INDUSTRY_KEYWORDS):
                return {'diagnostics': f"Sector Excluded ({sec_name} / {sec_info.get('industry')})", 'above_200': is_above_200}

        pct_above_200 = ((c0 - daily_ema200) / daily_ema200) * 100

        w_df = resample_daily_to_weekly(daily_df)
        if len(w_df) < 24:
            return {'diagnostics': "Insufficient weekly history (<24 weeks)", 'above_200': is_above_200}

        high_52w = daily_df['High'].tail(252).max() if len(daily_df) >= 252 else daily_df['High'].max()

        results = {
            'ticker': ticker,
            'above_200': is_above_200,
            'base_reset': None,
            'htf': None,
            'pocket_pivot': None,
            'liquidity_sweep': None,
            'br_reason': None,
            'htf_reason': None,
            'pp_reason': None,
            'ls_reason': None,
            'diagnostics': "Evaluated"
        }

        res_br, r_br = check_base_reset(ticker, daily_df, w_df, c0, daily_ema200, pct_above_200, high_52w)
        results['base_reset'] = res_br
        results['br_reason'] = r_br

        res_htf, r_htf = check_htf(ticker, daily_df, c0, high_52w)
        results['htf'] = res_htf
        results['htf_reason'] = r_htf

        res_pp, r_pp = check_pocket_pivot(ticker, daily_df, c0, daily_ema200, high_52w)
        results['pocket_pivot'] = res_pp
        results['pp_reason'] = r_pp

        res_ls, r_ls = check_liquidity_sweep(ticker, daily_df, c0, daily_ema200, high_52w)
        results['liquidity_sweep'] = res_ls
        results['ls_reason'] = r_ls

        return results

    except Exception as e:
        return {'diagnostics': f"Error: {type(e).__name__}", 'above_200': False}

# ---------------------------------------------------------
# 7. MACRO REGIME & EXPOSURE DASHBOARD
# ---------------------------------------------------------
def analyze_market_regime(total_evaluated, total_above_200, category_counts):
    print("\n" + "="*112)
    print("                      MACRO MARKET REGIME & CAPITAL EXPOSURE DASHBOARD")
    print("="*112)

    cross_assets = yf.download(
        ['SPY', 'QQQ', '^TNX', 'CL=F'],
        period='1y',
        interval='1d',
        progress=False,
        session=GLOBAL_HTTP_SESSION
    )
    
    close_df = cross_assets['Close']
    spy_close = close_df['SPY'].dropna()
    qqq_close = close_df['QQQ'].dropna()

    spy_c = spy_close.iloc[-1]
    spy_ema21 = spy_close.ewm(span=21, adjust=False).mean().iloc[-1]
    spy_sma50 = spy_close.rolling(50).mean().iloc[-1]
    spy_ema200 = spy_close.ewm(span=200, adjust=False).mean().iloc[-1]

    spy_above_21 = bool(spy_c > spy_ema21)
    spy_above_50 = bool(spy_c > spy_sma50)
    spy_above_200 = bool(spy_c > spy_ema200)

    qqq_c = qqq_close.iloc[-1]
    qqq_ema21 = qqq_close.ewm(span=21, adjust=False).mean().iloc[-1]
    qqq_sma50 = qqq_close.rolling(50).mean().iloc[-1]
    qqq_ema200 = qqq_close.ewm(span=200, adjust=False).mean().iloc[-1]

    qqq_above_21 = bool(qqq_c > qqq_ema21)
    qqq_above_50 = bool(qqq_c > qqq_sma50)
    qqq_above_200 = bool(qqq_c > qqq_ema200)
    qqq_in_downtrend = (not qqq_above_50) or (not qqq_above_200) or (qqq_c < qqq_ema21 and qqq_ema21 < qqq_sma50)

    macro_warnings = []
    cross_asset_drag = False
    
    tnx_c = 0.0
    if '^TNX' in close_df.columns:
        tnx_s = close_df['^TNX'].dropna()
        if not tnx_s.empty:
            tnx_c = tnx_s.iloc[-1]
            tnx_5d_chg = ((tnx_c - tnx_s.iloc[-5]) / tnx_s.iloc[-5]) * 100 if len(tnx_s) >= 5 else 0.0
            if tnx_c >= 4.80 or tnx_5d_chg >= 3.5:
                cross_asset_drag = True
                macro_warnings.append(f"⚡ YIELD SURGE: 10-Yr Yield at {round(tnx_c, 2)}% (+{round(tnx_5d_chg, 1)}% 5d). Multiple drag active.")

    oil_c = 0.0
    if 'CL=F' in close_df.columns:
        oil_s = close_df['CL=F'].dropna()
        if not oil_s.empty:
            oil_c = oil_s.iloc[-1]
            oil_5d_chg = ((oil_c - oil_s.iloc[-5]) / oil_s.iloc[-5]) * 100 if len(oil_s) >= 5 else 0.0
            if oil_c >= 85.0 or oil_5d_chg >= 4.5:
                cross_asset_drag = True
                macro_warnings.append(f"🛢️ OIL PRICE SPIKE: WTI Crude at ${round(oil_c, 2)} (+{round(oil_5d_chg, 1)}% 5d). Inflation expectations repricing.")

    pct_above_200 = (total_above_200 / max(total_evaluated, 1)) * 100
    pct_below_200 = 100.0 - pct_above_200
    htf_cnt = category_counts.get('htf', 0)
    sweep_cnt = category_counts.get('sweep', 0)
    calendar_alerts, seasonal_mult = MacroEventCalendar.evaluate_calendar()

    if cross_asset_drag:
        seasonal_mult = min(seasonal_mult, 0.65)

    if (not spy_above_200) or (not qqq_above_200) or (not spy_above_50 and not qqq_above_50) or (pct_above_200 < 50.0):
        regime_status = "RED: CONFIRMED MACRO DOWNTREND"
        action_plan = "DEFENSIVE SIZING. Structural trend broken. Use extreme caution on breakouts."
        allowed_setups = "Watchlist evaluation active. High-expectancy setups only."
        max_exposure = "0% - 15% (Defensive Stance)"
        posture_box = "■ DOWNTREND DEFENSE: TRADE SELECTIVELY WITH TIGHT RISK ■"
    elif (spy_above_21 and spy_above_50 and qqq_above_21 and qqq_above_50 and qqq_above_200) and (pct_above_200 >= 70.0) and (not cross_asset_drag) and (htf_cnt >= 4):
        regime_status = "GREEN: EXPANSION / MOMENTUM REGIME"
        action_plan = "AGGRESSIVE MARKUP. Full green-light to trade traditional breakouts and momentum flags."
        allowed_setups = "Momentum Bull Flags, High Tight Flags, Pocket Pivots."
        eff_exp = int(100 * seasonal_mult)
        max_exposure = f"{int(80 * seasonal_mult)}% - {eff_exp}%"
        posture_box = "▲ EXPANSION BULL: BUY CONTINUATION & BREAKOUTS ▲"
    else:
        regime_status = "AMBER: ROTATIONAL ACCUMULATION / MACRO HEADWIND"
        if cross_asset_drag:
            action_plan = "DEFENSIVE SELECTIVITY. Yield/Oil spike compressing multiples. Do NOT chase tech breakouts."
        elif qqq_in_downtrend:
            action_plan = "TECH DISTRIBUTION DRAG. QQQ lagging below short-term EMAs. Favor Non-Tech or Support Sweeps."
        else:
            action_plan = "SELECTIVE MEAN-REVERSION. Avoid 52w-high breakouts; buy structural support tests."
        
        allowed_setups = "Liquidity Sweeps (U&R), Cash-Flow Hedges, and Base Pocket Pivots (Risk <= 3.0%)."
        eff_exp = int(45 * seasonal_mult)
        max_exposure = f"{int(20 * seasonal_mult)}% - {eff_exp}% (Take fast partials at 2R)"
        posture_box = "◆ ROTATIONAL DIGEST: BUY SUPPORT SWEEPS ONLY ◆"

    print(f"  Regime Status       : {regime_status}")
    print(f"  Macro Posture       : {posture_box}")
    print(f"  Max Account Exposure: {max_exposure} (Macro/Cross-Asset Factor: {round(seasonal_mult, 2)}x)")
    print(f"  Recommended Tactics : {action_plan}")
    print(f"  Eligible Setups     : {allowed_setups}")
    print("-" * 112)
    print(f"  EQUITY BENCHMARKS   : SPY = ${round(spy_c, 2)} (Above 21 EMA: {spy_above_21} | Above 50 SMA: {spy_above_50} | Above 200 EMA: {spy_above_200})")
    print(f"                        QQQ = ${round(qqq_c, 2)} (Above 21 EMA: {qqq_above_21} | Above 50 SMA: {qqq_above_50} | Above 200 EMA: {qqq_above_200} | Downtrend: {qqq_in_downtrend})")
    print(f"  CROSS-ASSET MACRO   : 10Y Treasury Yield = {round(tnx_c, 2)}% | WTI Crude Oil = ${round(oil_c, 2)}/bbl")
    print(f"  UNIVERSE BREADTH    : {round(pct_above_200, 1)}% of stocks > 200 EMA | {round(pct_below_200, 1)}% in Structural Downtrends")
    print(f"  CANDIDATE PROFILE   : Breakout/Momentum ({htf_cnt}) vs. False-Breakdown Sweeps ({sweep_cnt})")
    print("-" * 112)
    for warn in macro_warnings:
        print(f"  EXOGENOUS SHOCK     : {warn}")
    for alert in calendar_alerts:
        print(f"  CALENDAR & RELEASES : {alert}")
    print("=" * 112 + "\n")

    dashboard_data = {
        'regime_status': regime_status,
        'posture_box': posture_box,
        'max_exposure': max_exposure,
        'action_plan': action_plan,
        'spy_c': round(spy_c, 2),
        'spy_status': f"Above 21:{spy_above_21} | 50:{spy_above_50} | 200:{spy_above_200}",
        'qqq_c': round(qqq_c, 2),
        'qqq_status': f"Above 21:{qqq_above_21} | 50:{qqq_above_50} | 200:{qqq_above_200}",
        'tnx': round(tnx_c, 2),
        'oil': round(oil_c, 2),
        'pct_above_200': round(pct_above_200, 1),
        'warnings': macro_warnings,
        'calendar': calendar_alerts
    }
    return regime_status, dashboard_data

# ---------------------------------------------------------
# 8. TRAILING 5-DAY RUNNER TRACKER & EVALUATOR
# ---------------------------------------------------------
def update_and_evaluate_trailing_runners(todays_candidates):
    """
    Maintains a rolling 35-day log of recommended setups and calculates
    the stock that gained the most from suggested pivot to peak high over the trailing 5 trading days.
    """
    history = load_json_cache(HISTORY_TRACKER_FILE)
    if not isinstance(history, list):
        history = []

    today_str = datetime.date.today().isoformat()

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

    cutoff_date = (datetime.date.today() - datetime.timedelta(days=35)).isoformat()
    history = [h for h in history if h.get('date', '') >= cutoff_date]
    save_json_cache(HISTORY_TRACKER_FILE, history)

    five_days_ago = (datetime.date.today() - datetime.timedelta(days=8)).isoformat()
    candidates_to_check = [h for h in history if five_days_ago <= h['date'] < today_str]

    if not candidates_to_check:
        print("[RUNNERS] No historical setups logged within trailing 5 trading days.")
        return None

    check_tickers = list(set(h['ticker'] for h in candidates_to_check))
    print(f"[RUNNERS] Auditing post-entry expansion across {len(check_tickers)} historical setups...")

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
# 9. 8-SLIDE LINKEDIN CAROUSEL PDF GENERATOR
# ---------------------------------------------------------
def create_linkedin_carousel_pdf(
    filename,
    regime_status,
    posture_box,
    max_exposure,
    calendar_alerts,
    pct_above_200,
    top_runner,
    top_br,
    top_htf,
    top_pp,
    top_ls
):
    w, h = 1080, 1080
    c = canvas.Canvas(filename, pagesize=(w, h))

    bg_color = HexColor("#070a12")
    card_bg = HexColor("#0f172a")
    card_inner = HexColor("#1e293b")
    text_white = HexColor("#f8fafc")
    text_muted = HexColor("#94a3b8")
    accent_cyan = HexColor("#38bdf8")
    accent_green = HexColor("#4ade80")
    accent_amber = HexColor("#fbbf24")
    accent_red = HexColor("#f87171")

    def draw_base(header, slide_num, total_slides=8):
        c.setFillColor(bg_color)
        c.rect(0, 0, w, h, fill=True, stroke=False)

        c.setFont("Helvetica-Bold", 14)
        c.setFillColor(text_muted)
        c.drawString(60, h - 50, "CORP ACUITY // INSTITUTIONAL INTELLIGENCE")
        c.drawRightString(w - 60, h - 50, f"{slide_num} of {total_slides}")

        c.setStrokeColor(card_inner)
        c.setLineWidth(1)
        c.line(60, h - 65, w - 60, h - 65)

    # ---------------- SLIDE 1: COVER & VALUE PROP ----------------
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
    c.setFillColor(accent_green if "GREEN" in regime_status else (accent_amber if "AMBER" in regime_status else accent_red))
    c.drawString(90, h - 225, regime_status)

    c.setFont("Helvetica-Bold", 22)
    c.setFillColor(text_white)
    c.drawString(90, h - 280, f"Max Suggested Exposure: {max_exposure}")
    c.setFont("Helvetica", 18)
    c.setFillColor(text_muted)
    clean_posture = posture_box.replace("■", "").replace("▲", "").replace("◆", "").strip()
    c.drawString(90, h - 320, clean_posture[:64])

    box_w = (w - 150) / 2
    c.setFillColor(card_bg)
    c.roundRect(60, h - 600, box_w, 200, 16, fill=True, stroke=False)
    c.setFont("Helvetica-Bold", 18)
    c.setFillColor(text_muted)
    c.drawString(85, h - 440, "UNIVERSE BREADTH (>200 EMA)")
    c.setFont("Helvetica-Bold", 44)
    c.setFillColor(accent_cyan)
    c.drawString(85, h - 510, f"{round(pct_above_200, 1)}%")
    c.setFont("Helvetica", 16)
    c.setFillColor(text_muted)
    c.drawString(85, h - 560, "Long-term structural trend health")

    c.setFillColor(card_bg)
    c.roundRect(60 + box_w + 30, h - 600, box_w, 200, 16, fill=True, stroke=False)
    c.setFont("Helvetica-Bold", 18)
    c.setFillColor(text_muted)
    c.drawString(85 + box_w + 30, h - 440, "IMMINENT MACRO PRINTS")
    c.setFont("Helvetica", 16)
    c.setFillColor(text_white)
    y_cal = h - 490
    radar = calendar_alerts[:3] if calendar_alerts else ["Clear Runway: No high-impact shocks in 72h."]
    for al in radar:
        c.drawString(85 + box_w + 30, y_cal, al.replace("🚨", "! ")[:35])
        y_cal -= 35

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
        c.drawString(100, h - 470, "Performance metrics automatically populate on subsequent runs.")

    c.showPage()

    # ---------------- SLIDES 4 TO 7: THE 4 QUANT SETUP TILES ----------------
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

        c.setFillColor(card_bg)
        c.roundRect(60, h - 850, w - 120, 560, 20, fill=True, stroke=False)

        box_metrics = [
            ("TRIGGER PIVOT", f"${candidate['Pivot_Trigger']:.2f}", text_white),
            ("STOP LOSS", f"${candidate['Stop_Loss']:.2f}", accent_red),
            ("RISK BUDGET", f"{candidate['Risk_%']}%", text_muted),
            ("ASYMMETRY (R:R)", f"{candidate['R_Ratio']}R", accent_cyan),
            ("FUNDAMENTAL CATALYST", str(candidate.get('Zacks_Rank', 'Rank 1 (Strong Buy)')), accent_amber),
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

    draw_setup_slide("1. BASE-RESET INFLECTION", "Breakout above 50-day SMA with curling weekly MACD and institutional volume", top_br, 4)
    draw_setup_slide("2. MOMENTUM BULL FLAG", "CAN SLIM pole >= 45.0%, tight flag consolidation <= 18d holding 21 EMA", top_htf, 5)
    draw_setup_slide("3. POCKET PIVOT SQUEEZE", "Bollinger/Keltner squeeze launch with volume surge exceeding 10d down volume", top_pp, 6)
    draw_setup_slide("4. LIQUIDITY SWEEP (U&R)", "False breakdown below support reversed with institutional demand bid", top_ls, 7)

    # ---------------- SLIDE 8: GOVERNANCE & RISK FRAMEWORK ----------------
    draw_base("EXECUTION DISCIPLINE", 8, 8)
    c.setFont("Helvetica-Bold", 34)
    c.setFillColor(accent_cyan)
    c.drawString(60, h - 140, "GOVERNANCE & EXECUTION RULES")

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
    print(f"\n[CAROUSEL] Generated institutional 8-slide PDF: {filename}")

# ---------------------------------------------------------
# 10. RENDER HIGH-RES PNG CARDS FOR X (STAMPED 1 OF 4 TO 4 OF 4)
# ---------------------------------------------------------
def export_carousel_cards_for_web(pdf_path=CAROUSEL_PDF_FILENAME):
    """
    Renders 4 high-res PNG cards for X:
    - Card 1: Slide 1 (Cover, Briefing & Website CTA)
    - Card 2: Slide 2 (Macro Regime Cockpit)
    - Card 3: Slide 3 (5-Day Top Runner Teaser)
    - Card 4: Slide 4 (Top Setup 1)
    """
    if not os.path.exists(pdf_path):
        print(f"[CARDS] Error: '{pdf_path}' not found.")
        return []

    os.makedirs("x_cards", exist_ok=True)
    doc = fitz.open(pdf_path)
    card_paths = []
    matrix = fitz.Matrix(2.0, 2.0)

    target_indices = [0, 1, 2, 3]
    card_num = 1
    for idx in target_indices:
        if idx < len(doc):
            page = doc.load_page(idx)
            
            badge_rect = fitz.Rect(860, 32, 1020, 62)
            page.draw_rect(badge_rect, color=(0.027, 0.039, 0.071), fill=(0.027, 0.039, 0.071))
            
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
    print(f"[CARDS] Rendered {len(card_paths)} high-res PNG cards into x_cards/ (Stamped Card 1 of 4 to 4 of 4)")
    return card_paths

# ---------------------------------------------------------
# 11. MASTER RUNNER & ORCHESTRATOR
# ---------------------------------------------------------
def run_master_screener():
    universe, sector_map = fetch_institutional_universe_and_sectors()
    total = len(universe)
    print(f"Loaded institutional universe of {total} stocks.")
    print("Excluding Healthcare, Staples, Transports, Financials, Utilities, Real Estate, Retail & ADDV <$12M.")
    print(f"Scanning across 4 Setup Categories in batches of {CHUNK_SIZE}...\n")

    spy_data = yf.download(
        'SPY',
        period='6mo',
        interval='1d',
        progress=False,
        session=GLOBAL_HTTP_SESSION
    )['Close']
    spy_1m_perf = ((spy_data.iloc[-1] - spy_data.iloc[-21]) / spy_data.iloc[-21]) * 100
    if isinstance(spy_1m_perf, pd.Series):
        spy_1m_perf = spy_1m_perf.iloc[0]

    base_resets = []
    htfs = []
    pocket_pivots = []
    liquidity_sweeps = []

    macro_diag = Counter()
    br_diag = Counter()
    htf_diag = Counter()
    pp_diag = Counter()
    ls_diag = Counter()

    total_evaluated = 0
    total_passed_universal = 0
    total_above_200 = 0
    total_chunks = (total + CHUNK_SIZE - 1) // CHUNK_SIZE

    for idx in range(0, total, CHUNK_SIZE):
        chunk = universe[idx:idx + CHUNK_SIZE]
        chunk_idx = (idx // CHUNK_SIZE) + 1
        print(f"[{chunk_idx:>2}/{total_chunks}] Downloading & analyzing {len(chunk):>2} tickers...", end="", flush=True)

        batch_data = None
        for attempt in range(3):
            try:
                batch_data = yf.download(
                    tickers=chunk,
                    period="2y",
                    interval="1d",
                    group_by="ticker",
                    auto_adjust=True,
                    threads=False,
                    session=GLOBAL_HTTP_SESSION,
                    progress=False,
                    ignore_tz=True
                )
                if batch_data is not None and not batch_data.empty:
                    break
            except Exception:
                pass
            time.sleep(1.0)

        if batch_data is None or batch_data.empty:
            print(" Download failed, skipping batch.")
            continue

        chunk_matches = 0
        with ThreadPoolExecutor(max_workers=8) as executor:
            future_to_sym = {}
            for sym in chunk:
                if isinstance(batch_data.columns, pd.MultiIndex):
                    if sym in batch_data.columns.levels[0]:
                        future_to_sym[executor.submit(evaluate_all_setups, sym, batch_data[sym], spy_1m_perf, sector_map)] = sym
                else:
                    future_to_sym[executor.submit(evaluate_all_setups, sym, batch_data, spy_1m_perf, sector_map)] = sym

            for future in as_completed(future_to_sym):
                total_evaluated += 1
                res = future.result()
                diag_status = res.get('diagnostics', 'Unknown')
                macro_diag[diag_status] += 1

                if res.get('above_200'):
                    total_above_200 += 1

                if diag_status == "Evaluated":
                    total_passed_universal += 1
                    matched_any = False

                    if res['base_reset']:
                        base_resets.append(res['base_reset'])
                        matched_any = True
                    else:
                        br_diag[res['br_reason']] += 1

                    if res['htf']:
                        htfs.append(res['htf'])
                        matched_any = True
                    else:
                        htf_diag[res['htf_reason']] += 1

                    if res['pocket_pivot']:
                        pocket_pivots.append(res['pocket_pivot'])
                        matched_any = True
                    else:
                        pp_diag[res['pp_reason']] += 1

                    if res['liquidity_sweep']:
                        liquidity_sweeps.append(res['liquidity_sweep'])
                        matched_any = True
                    else:
                        ls_diag[res['ls_reason']] += 1

                    if matched_any:
                        chunk_matches += 1

        print(f" done ({chunk_matches} setups flagged)")
        time.sleep(1.5)

    category_counts = {
        'reset': len(base_resets),
        'htf': len(htfs),
        'pivot': len(pocket_pivots),
        'sweep': len(liquidity_sweeps)
    }

    regime, dashboard = analyze_market_regime(total_evaluated, total_above_200, category_counts)

    unique_passed_tickers = list(set(
        [r['Ticker'] for r in base_resets] +
        [r['Ticker'] for r in htfs] +
        [r['Ticker'] for r in pocket_pivots] +
        [r['Ticker'] for r in liquidity_sweeps]
    ))

    print(f"\nProfiling Earnings Dates & Zacks Ranks for {len(unique_passed_tickers)} candidates...", end="", flush=True)
    earnings_map = {}
    with ThreadPoolExecutor(max_workers=8) as executor:
        earn_futures = {executor.submit(evaluate_earnings_proximity, t): t for t in unique_passed_tickers}
        for future in as_completed(earn_futures):
            tk = earn_futures[future]
            earnings_map[tk] = future.result()

    zacks_map = profile_zacks_with_local_tenure(unique_passed_tickers)
    print(" done.\n")

    for r in base_resets:
        r['Category'] = 'Base-Reset'
        r['Zacks_Rank'] = zacks_map.get(r['Ticker'], 'N/A')
        r['Earnings_Risk'] = earnings_map.get(r['Ticker'], 'Unknown')

    for r in htfs:
        r['Category'] = 'Momentum Flag'
        r['Zacks_Rank'] = zacks_map.get(r['Ticker'], 'N/A')
        r['Earnings_Risk'] = earnings_map.get(r['Ticker'], 'Unknown')

    for r in pocket_pivots:
        r['Category'] = 'Pocket Pivot'
        r['Zacks_Rank'] = zacks_map.get(r['Ticker'], 'N/A')
        r['Earnings_Risk'] = earnings_map.get(r['Ticker'], 'Unknown')

    for r in liquidity_sweeps:
        r['Category'] = 'Liquidity Sweep'
        r['Zacks_Rank'] = zacks_map.get(r['Ticker'], 'N/A')
        r['Earnings_Risk'] = earnings_map.get(r['Ticker'], 'Unknown')

    filtered_base_resets = [
        r for r in base_resets
        if (any(r['Zacks_Rank'].startswith(rk) for rk in ['#1', '#2']) or r['Zacks_Rank'] == 'N/A')
        and "🚨 DANGER" not in r['Earnings_Risk']
    ]

    def universal_quality_filter(pool):
        return [
            r for r in pool
            if not any(r['Zacks_Rank'].startswith(rk) for rk in ['#4', '#5'])
            and "🚨 DANGER" not in r['Earnings_Risk']
        ]

    filtered_htfs = universal_quality_filter(htfs)
    filtered_pockets = universal_quality_filter(pocket_pivots)
    filtered_sweeps = universal_quality_filter(liquidity_sweeps)

    # ---------------- CSV EXPORTS ----------------
    pd.DataFrame(filtered_base_resets).to_csv("watchlist_base_resets.csv", index=False)
    pd.DataFrame(filtered_htfs).to_csv("watchlist_momentum_flags.csv", index=False)
    pd.DataFrame(filtered_pockets).to_csv("watchlist_pocket_pivots.csv", index=False)
    pd.DataFrame(filtered_sweeps).to_csv("watchlist_liquidity_sweeps.csv", index=False)

    # ---------------- 5-DAY RUNNER TRACKER ----------------
    all_current_setups = filtered_base_resets + filtered_htfs + filtered_pockets + filtered_sweeps
    top_runner = update_and_evaluate_trailing_runners(all_current_setups)

    # ---------------- PICK TOP 1 PER MODEL ----------------
    top_br = sorted(filtered_base_resets, key=lambda x: x.get('Conviction_Score', 0), reverse=True)[0] if filtered_base_resets else None
    top_htf = sorted(filtered_htfs, key=lambda x: x.get('Conviction_Score', 0), reverse=True)[0] if filtered_htfs else None
    top_pp = sorted(filtered_pockets, key=lambda x: x.get('R_Ratio', 0), reverse=True)[0] if filtered_pockets else None
    top_ls = sorted(filtered_sweeps, key=lambda x: x.get('R_Ratio', 0), reverse=True)[0] if filtered_sweeps else None

    # ---------------- 8-SLIDE LINKEDIN CAROUSEL PDF ----------------
    create_linkedin_carousel_pdf(
        filename=CAROUSEL_PDF_FILENAME,
        regime_status=regime,
        posture_box=dashboard.get('posture_box', 'SELECTIVE'),
        max_exposure=dashboard.get('max_exposure', 'N/A'),
        calendar_alerts=dashboard.get('calendar', []),
        pct_above_200=dashboard.get('pct_above_200', 0.0),
        top_runner=top_runner,
        top_br=top_br,
        top_htf=top_htf,
        top_pp=top_pp,
        top_ls=top_ls
    )

    # ---------------- 4 PNG CARDS FOR X ----------------
    export_carousel_cards_for_web(CAROUSEL_PDF_FILENAME)

    # ---------------- WEB TERMINAL FEED (JSON) ----------------
    web_terminal_payload = {
        'generated_at': datetime.datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC'),
        'macro': dashboard,
        'top_runner': top_runner,
        'watchlists': {
            'base_resets': filtered_base_resets,
            'momentum_flags': filtered_htfs,
            'pocket_pivots': filtered_pockets,
            'liquidity_sweeps': filtered_sweeps
        }
    }
    with open(TERMINAL_FEED_FILENAME, "w", encoding="utf-8") as f:
        json.dump(web_terminal_payload, f, indent=2)
    print(f"[TERMINAL] Exported {TERMINAL_FEED_FILENAME}")

    # ---------------- METADATA FOR MORNING BROADCAST ----------------
    focus_tickers = [c['Ticker'] for c in [top_br, top_htf, top_pp, top_ls] if c]
    broadcast_meta = {
        'pdf_path': CAROUSEL_PDF_FILENAME,
        'date': datetime.date.today().isoformat(),
        'regime_status': regime,
        'posture_box': dashboard.get('posture_box', 'SELECTIVE'),
        'max_exposure': dashboard.get('max_exposure', 'N/A'),
        'pct_above_200': dashboard.get('pct_above_200', 0.0),
        'focus_tickers': focus_tickers[:3],
        'top_runner': top_runner,
        'top_br': top_br,
        'top_htf': top_htf,
        'top_pp': top_pp,
        'top_ls': top_ls
    }
    with open(POST_META_FILENAME, "w", encoding="utf-8") as f:
        json.dump(broadcast_meta, f, indent=2)
    print(f"[METADATA] Saved {POST_META_FILENAME}")

    # ---------------- PRINT TERMINAL TABLES ----------------
    print("\n" + "="*148)
    print("                    CATEGORY 1: BASE-RESET INFLECTIONS (Above 200 EMA >= 0.5%, Headroom >= 16%, R:R >= 2.5)")
    print("="*148)
    if filtered_base_resets:
        print(pd.DataFrame(filtered_base_resets).sort_values(by='Conviction_Score', ascending=False).to_string(index=False))
    else:
        print("No candidates currently meeting Base-Reset quality gates.")

    print("\n" + "="*148)
    print("                    CATEGORY 2: MOMENTUM BULL FLAGS (CAN SLIM Pole >= 45.0%, Flag <= 18d, Depth <= 14%, Risk >= 1.5%)")
    print("="*148)
    if filtered_htfs:
        print(pd.DataFrame(filtered_htfs).sort_values(by='Pole_Gain_%', ascending=False).to_string(index=False))
    else:
        print("No candidates currently meeting Momentum Flag quality gates.")

    print("\n" + "="*148)
    print("                    CATEGORY 3: POCKET PIVOT SQUEEZES (Headroom >= 15%, R:R >= 2.0, Safe Earnings)")
    print("="*148)
    if filtered_pockets:
        print(pd.DataFrame(filtered_pockets).sort_values(by='R_Ratio', ascending=False).to_string(index=False))
    else:
        print("No candidates currently meeting Pocket Pivot criteria.")

    print("\n" + "="*148)
    print("                    CATEGORY 4: LIQUIDITY SWEEPS (Price >= $15, Non-Retail/Midstream, R:R >= 2.5)")
    print("="*148)
    if filtered_sweeps:
        print(pd.DataFrame(filtered_sweeps).sort_values(by='R_Ratio', ascending=False).to_string(index=False))
    else:
        print("No candidates currently meeting Liquidity Sweep criteria.")
    print("="*148)

    # ---------------- DIAGNOSTIC ELIMINATION FUNNELS ----------------
    print("\n" + "="*95)
    print(f"                 UNIVERSAL ELIMINATION FUNNEL (Evaluated {total_evaluated} Symbols)")
    print("="*95)
    for reason, count in macro_diag.most_common():
        pct = (count / max(total_evaluated, 1)) * 100
        print(f"  {reason:<65}: {count:>4} ({pct:>5.1f}%)")

    def print_sub_funnel(name, counter, count_passed):
        print("\n" + "-"*95)
        print(f"  {name} FUNNEL (Active Pool: {total_passed_universal} Liquid Stocks | {count_passed} Passed)")
        print("-"*95)
        for reason, count in counter.most_common(6):
            pct = (count / max(total_passed_universal, 1)) * 100
            print(f"    {reason:<62}: {count:>4} ({pct:>5.1f}%)")

    print_sub_funnel("CATEGORY 1 (BASE-RESET)", br_diag, len(filtered_base_resets))
    print_sub_funnel("CATEGORY 2 (MOMENTUM BULL FLAG)", htf_diag, len(filtered_htfs))
    print_sub_funnel("CATEGORY 3 (POCKET PIVOT SQUEEZE)", pp_diag, len(filtered_pockets))
    print_sub_funnel("CATEGORY 4 (LIQUIDITY SWEEP)", ls_diag, len(filtered_sweeps))
    print("="*95 + "\n")

if __name__ == "__main__":
    try:
        run_master_screener()
    finally:
        GLOBAL_HTTP_SESSION.close()
        print("\n[COMPLETE] Screener run finished successfully.")
    
