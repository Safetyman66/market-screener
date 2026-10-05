#!/usr/bin/env python3
"""
Corp Acuity // Master Market Screener & Alpha Engine
Author: Corp Acuity Ltd
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
    def get_monthly_seasonality(cls, month):
        seasonality_guide = {
            1: "JANUARY EFFECT & NEW INFLOWS: Institutional capital redeployment. Strong early-month momentum often consolidates into late-month earnings tests.",
            2: "FEBRUARY CHOP: Historically choppy and range-bound post-Q4 earnings; mid-month volatility spikes are common.",
            3: "MARCH Q1 REBALANCE & QUAD WITCHING: Strong late-month pension rebalancing. Watch for institutional rotation into quarter-end.",
            4: "APRIL TAX DRAIN & SPRING RALLY: Mid-month liquidity pinch around tax deadlines, often resolving into a strong late-month earnings ramp.",
            5: "'SELL IN MAY' DRIFT: Transition to lighter summer liquidity; systematic trend continuation favored over loose breakouts.",
            6: "JUNE MID-YEAR PINNING & TRIPLE WITCHING: Pre-summer window dressing followed by index roll-overs and options expiration pinning.",
            7: "JULY EARNINGS MOMENTUM: Historically one of the strongest seasonal performers for growth and tech leaders during Q2 reporting.",
            8: "AUGUST SUMMER DOLDRUMS: Thin institutional liquidity; volume drop-offs make breakout pivots susceptible to midday whipsaws.",
            9: "SEPTEMBER SEASONAL DRAG: Statistically the weakest month historically. Post-OPEX de-risking and mutual fund fiscal-year-end loss harvesting.",
            10: "OCTOBER VOLATILITY & INFLECTION: Renowned 'bear killer' month. Elevated pre-earnings and OPEX volatility frequently forms major market swing bottoms.",
            11: "NOVEMBER YEAR-END CHASE: Benchmark underperformance forces aggressive institutional buying; post-election clarity historically accelerates rallies.",
            12: "DECEMBER SANTA CLAUS RALLY: Turn-of-month retirement allocations and systematic window dressing; breakout continuation historically favored."
        }
        return seasonality_guide.get(month, "NEUTRAL SEASONALITY: Focus purely on price/volume technicals and regime filters.")

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

        current_opx = cls.get_third_friday(year, month)
        if (current_opx - target_date).days < 0:
            current_opx = cls.get_third_friday(next_y, next_m)
        days_to_opx = (current_opx - target_date).days
        opx_label = "Triple/Quad Witching" if current_opx.month in [3, 6, 9, 12] else "Monthly OPEX"

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
                alerts.append(f"IN {diff} DAY(S): {desc} ({d})")
                if evt_type in ["FOMC", "DATA"]:
                    exposure_multiplier = min(exposure_multiplier, 0.80)

        horizon_count = 0
        for d, desc, evt_type, diff in upcoming:
            if diff > 3 and horizon_count < 3:
                alerts.append(f"IN {diff} DAYS: {desc}")
                horizon_count += 1

        if day in [29, 30, 31, 1, 2, 3]:
            alerts.append("TURN-OF-MONTH (TOM) INFLOWS: Automated retirement allocations supporting baseline.")

        seasonal_context = cls.get_monthly_seasonality(month)

        return alerts, exposure_multiplier, seasonal_context, days_to_opx, opx_label

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
            return
