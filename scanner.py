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
