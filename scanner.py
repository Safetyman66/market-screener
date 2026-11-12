#!/usr/bin/env python3
"""Corp Acuity // Master Market Screener & Alpha Engine.

Author: Corp Acuity Ltd

Architecture:
  - Stage 0: Instant in-memory metadata pruning (drops non-momentum sectors with 0 network calls).
  - Stage 1: Ultra-lightweight 5-day liquidity scan (Price >= $10, 5D ADDV >= $12M).
  - Stage 2: 15-month historical deep-dive (period='15mo') exclusively on liquid survivors.
  - Pattern Engines: Base-Resets, Momentum Bull Flags (Blue-Sky friendly), Pocket Pivots, Liquidity Sweeps.
  - Knowledge Base Integration: Synthesizes Zacks tenure, earnings proximity, OpEx gamma,
    and TOM calendar cycles into operational Execution Protocols for each setup.
  - Multi-Output: Produces standard watchlists, LinkedIn carousel PDF, X cards, terminal JSON,
    and a unified 'master_screener_results.csv' spreadsheet.
"""

# ====================================================================================================================
# GLOBAL WARNING SUPPRESSION (MUST BE FIRST)
# ====================================================================================================================
import warnings
warnings.warn = lambda *args, **kwargs: None
warnings.filterwarnings("ignore")

from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
import datetime
import io
import json
import os
import random
import re
import time

import numpy as np
import pandas as pd
import requests
import yfinance as yf

from pdf_engine import create_linkedin_carousel_pdf, export_carousel_cards_for_web, CAROUSEL_PDF_FILENAME
from setups import (
    calculate_atr,
    calculate_macd,
    check_base_reset,
    check_htf,
    check_liquidity_sweep,
    check_pocket_pivot,
    resample_daily_to_weekly,
    evaluate_episodic_pivot,
    evaluate_ema_reclaim,
    evaluate_alpha_flag
)
from universe import (
    SECTOR_CACHE_FILE,
    load_json_cache,
    save_json_cache,
    fetch_institutional_universe_and_sectors,
    stage_0_prune_by_sector,
    stage_1_prune_by_liquidity,
)
from research_engine import (
    MacroEventCalendar,
    profile_zacks_with_local_tenure,
    evaluate_earnings_proximity,
    generate_kb_execution_protocol,
    determine_structural_catalyst,
)

from reportlab.lib.colors import HexColor
from reportlab.pdfgen import canvas

from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame
from alpaca.data.enums import DataFeed

try:
    ALPACA_CLIENT = StockHistoricalDataClient(os.environ["ALPACA_API_KEY"], os.environ["ALPACA_SECRET_KEY"])
except KeyError:
    print("[!] ERROR: Alpaca API keys not found in environment variables. Pipeline will fail.")
    ALPACA_CLIENT = None

class NumpyJSONEncoder(json.JSONEncoder):
    """Safely converts Pandas/NumPy data types into native Python JSON formats."""
    def default(self, obj):
        if isinstance(obj, (np.integer, np.int64, np.int32)):
            return int(obj)
        if isinstance(obj, (np.floating, np.float64, np.float32)):
            return float(obj)
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        if pd.isna(obj):
            return None
        if isinstance(obj, (datetime.date, datetime.datetime, pd.Timestamp)):
            return obj.isoformat()
        try:
            return super().default(obj)
        except TypeError:
            return str(obj)

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
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML,"
        " like Gecko) Chrome/128.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Sec-Ch-Ua": '"Chromium";v="128", "Not;A=Brand";v="24", "Google Chrome";v="128"',
    "Sec-Ch-Ua-Mobile": "?0",
    "Sec-Ch-Ua-Platform": '"Windows"',
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Upgrade-Insecure-Requests": "1",
})


def get_preliminary_regime():
    """Lightweight check to lock in parameters before scanning the entire universe."""
    try:
        cross_assets = yf.download(["SPY", "QQQ"], period="1y", interval="1d", progress=False, session=GLOBAL_HTTP_SESSION)["Close"]
        spy_c = cross_assets["SPY"].dropna().iloc[-1]
        spy_sma50 = cross_assets["SPY"].dropna().rolling(50).mean().iloc[-1]
        qqq_c = cross_assets["QQQ"].dropna().iloc[-1]
        qqq_sma50 = cross_assets["QQQ"].dropna().rolling(50).mean().iloc[-1]
        
        if spy_c < spy_sma50 and qqq_c < qqq_sma50:
            return "CONTRACTION"
        elif spy_c > spy_sma50 and qqq_c > qqq_sma50:
            return "EXPANSION"
        else:
            return "ROTATION"
    except Exception:
        return "ROTATION"


def is_acquisition_freeze(daily_df, lookback=5):
    """Detects stocks pinned in a narrow merger arbitrage / cash buyout spread."""
    if daily_df is None or len(daily_df) < lookback + 1:
        return False

    try:
        df = daily_df.tail(lookback).copy()
        if hasattr(df.columns, 'nlevels') and df.columns.nlevels > 1:
            df.columns = df.columns.get_level_values(0)

        for col in ['High', 'Low', 'Close']:
            if col not in df.columns:
                return False

        high = df['High'].squeeze()
        low = df['Low'].squeeze()
        close = df['Close'].squeeze()

        pct_daily_ranges = (high - low) / close
        median_adr_5d = float(pct_daily_ranges.median()) * 100.0

        start_close = float(close.iloc[0])
        end_close = float(close.iloc[-1])
        if start_close <= 0:
            return False
        net_drift_5d = abs(end_close - start_close) / start_close * 100.0

        mean_close = float(close.mean())
        if mean_close <= 0:
            return False
        max_dev = (float(close.max()) - float(close.min())) / mean_close * 100.0

        if median_adr_5d < 0.50 and net_drift_5d < 0.60 and max_dev < 0.85:
            return True
    except Exception:
        return False

    return False

def evaluate_all_setups(ticker, daily_df, spy_1m_perf, sector_map, regime_params, is_legacy, is_alpha):
    if is_acquisition_freeze(daily_df):
        return {"diagnostics": "Acquisition freeze / cash buyout pin", "above_200": False}

    try:
        daily_df = daily_df.dropna()
        if len(daily_df) < 45: # Lowered to 45 specifically to allow the Alpha track
            return {"diagnostics": "Insufficient data (<45 sessions)", "above_200": False}

        c0 = daily_df["Close"].iloc[-1]
        daily_ema200 = daily_df["Close"].ewm(span=200, adjust=False).mean().iloc[-1]
        is_above_200 = bool(c0 > daily_ema200)

        volume = daily_df["Volume"]
        vol_sma50 = volume.rolling(50).mean().iloc[-1]
        adv_20_shares = int(volume.tail(20).mean())
        daily_dollar_vol = c0 * vol_sma50
        
        # Dual-Track Intraday Liquidity Verification
        passed_legacy = is_legacy and c0 >= 10.0 and daily_dollar_vol >= 12_000_000 and len(daily_df) >= 120
        passed_alpha = is_alpha and c0 >= 4.0 and daily_dollar_vol >= 3_000_000

        if not passed_legacy and not passed_alpha:
            return {"diagnostics": "Liquidity Gate: Failed intraday thresholds", "above_200": is_above_200}

        stock_1m_perf = ((c0 - daily_df["Close"].iloc[-21]) / daily_df["Close"].iloc[-21]) * 100
        rs_relative = stock_1m_perf - spy_1m_perf
        if rs_relative < -12.0:
            return {"diagnostics": "Relative Strength: Lagging S&P 500 by >12% (1M)", "above_200": is_above_200}

        pct_above_200 = ((c0 - daily_ema200) / daily_ema200) * 100

        w_df = resample_daily_to_weekly(daily_df)
        if len(w_df) < 24 and passed_legacy:
            return {"diagnostics": "Insufficient weekly history (<24 weeks)", "above_200": is_above_200}

        high_52w = daily_df["High"].tail(252).max() if len(daily_df) >= 252 else daily_df["High"].max()

        results = {
            "ticker": ticker,
            "above_200": is_above_200,
            "base_reset": None, "htf": None, "pocket_pivot": None, "liquidity_sweep": None,
            "episodic_pivot": None, "ema_reclaim": None, "alpha_flag": None,
            "br_reason": None, "htf_reason": None, "pp_reason": None, "ls_reason": None,
            "diagnostics": "Evaluated",
        }

        if passed_legacy:
            res_br, r_br = check_base_reset(ticker, daily_df, w_df, c0, daily_ema200, pct_above_200, high_52w, adv_20_shares, regime_params["base_reset"])
            results["base_reset"] = res_br
            results["br_reason"] = r_br

            res_htf, r_htf = check_htf(ticker, daily_df, c0, daily_ema200, high_52w, adv_20_shares, regime_params["momentum_flag"])
            results["htf"] = res_htf
            results["htf_reason"] = r_htf

            res_pp, r_pp = check_pocket_pivot(ticker, daily_df, c0, daily_ema200, high_52w, adv_20_shares, regime_params["pocket_pivot"])
            results["pocket_pivot"] = res_pp
            results["pp_reason"] = r_pp

            res_ls, r_ls = check_liquidity_sweep(ticker, daily_df, c0, daily_ema200, high_52w, adv_20_shares, regime_params["liquidity_sweep"])
            results["liquidity_sweep"] = res_ls
            results["ls_reason"] = r_ls

        if passed_alpha:
            # Standardize Alpha outputs so they display cleanly in the CSV and Terminal
            def standardize(res_dict, cat_name):
                res_dict["Ticker"] = ticker
                res_dict["Close"] = round(c0, 2)
                res_dict["Category"] = cat_name
                res_dict["Pivot_Trigger"] = res_dict.get("trigger", c0)
                res_dict["Stop_Loss"] = res_dict.get("stop", c0)
                res_dict["Risk_%"] = round(((res_dict["Pivot_Trigger"] - res_dict["Stop_Loss"]) / res_dict["Pivot_Trigger"]) * 100, 2) if res_dict["Pivot_Trigger"] > 0 else 0
                res_dict["Conviction_Score"] = 9.99 # Force-sort Discovery pool to the top
                return res_dict

            res_ep = evaluate_episodic_pivot(daily_df, regime_params)
            if res_ep.get("valid"): results["episodic_pivot"] = standardize(res_ep, "Episodic Pivot")
            
            res_ema = evaluate_ema_reclaim(daily_df, regime_params)
            if res_ema.get("valid"): results["ema_reclaim"] = standardize(res_ema, "EMA Reclaim")
            
            res_af = evaluate_alpha_flag(daily_df, regime_params)
            if res_af.get("valid"): results["alpha_flag"] = standardize(res_af, "Alpha Flag")

        return results

    except Exception as e:
        return {"diagnostics": f"Error: {type(e).__name__}", "above_200": False}


# ---------------------------------------------------------
# MACRO REGIME & EXPOSURE ENGINE
# ---------------------------------------------------------
def analyze_market_regime(total_evaluated, total_above_200, category_counts):
    print("\n" + "=" * 112)
    print("                      MACRO MARKET REGIME & CAPITAL EXPOSURE DASHBOARD")
    print("=" * 112)

    cross_assets = yf.download(
        ["SPY", "QQQ", "^TNX", "CL=F"],
        period="1y",
        interval="1d",
        progress=False,
        session=GLOBAL_HTTP_SESSION,
    )

    close_df = cross_assets["Close"]
    spy_close = close_df["SPY"].dropna()
    qqq_close = close_df["QQQ"].dropna()

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

    macro_warnings = []
    cross_asset_drag = False

    tnx_c = 0.0
    tnx_5d_chg = 0.0
    if "^TNX" in close_df.columns:
        tnx_s = close_df["^TNX"].dropna()
        if not tnx_s.empty:
            tnx_c = tnx_s.iloc[-1]
            tnx_5d_chg = (((tnx_c - tnx_s.iloc[-5]) / tnx_s.iloc[-5]) * 100 if len(tnx_s) >= 5 else 0.0)
            if tnx_c >= 4.75 or tnx_5d_chg >= 4.0:
                cross_asset_drag = True
                macro_warnings.append(f"⚡ YIELD SURGE: 10-Yr Yield at {round(tnx_c, 2)}% ({'+' if tnx_5d_chg >= 0 else ''}{round(tnx_5d_chg, 1)}% 5d). Multiple drag active.")

    oil_c = 0.0
    oil_5d_chg = 0.0
    if "CL=F" in close_df.columns:
        oil_s = close_df["CL=F"].dropna()
        if not oil_s.empty:
            oil_c = oil_s.iloc[-1]
            oil_5d_chg = (((oil_c - oil_s.iloc[-5]) / oil_s.iloc[-5]) * 100 if len(oil_s) >= 5 else 0.0)
            if oil_c >= 88.0:
                cross_asset_drag = True
                macro_warnings.append(f"🛢️ OIL PRICE SPIKE: WTI Crude at ${round(oil_c, 2)}/bbl ({'+' if oil_5d_chg >= 0 else ''}{round(oil_5d_chg, 1)}% 5d). Inflation expectations repricing.")

    pct_above_200 = (total_above_200 / max(total_evaluated, 1)) * 100
    pct_below_200 = 100.0 - pct_above_200
    calendar_alerts, seasonal_mult, seasonal_context, days_to_opx, opx_label = MacroEventCalendar.evaluate_calendar()

    both_above_200 = bool(spy_above_200 and qqq_above_200)
    both_above_50 = bool(spy_above_50 and qqq_above_50)
    both_above_21 = bool(spy_above_21 and qqq_above_21)
    
    both_below_50 = bool(not spy_above_50 and not qqq_above_50)
    any_below_200 = bool(not spy_above_200 or not qqq_above_200)

    if any_below_200 or both_below_50 or pct_above_200 < 42.0:
        regime_status = "RED: STRUCTURAL CONTRACTION"
        action_plan = "CAPITAL PRESERVATION POSTURE. Benchmarks trapped below 50 SMA / breadth compressed. Breakout failure rates peak here. Stand aside or trade small-sized liquidity sweeps only."
        max_exposure = "0% - 20%"
        posture_box = "[!] DEFENSIVE POSTURE: CASH PRESERVATION / RISK-OFF"
        regime_code = "CONTRACTION"
    elif both_above_200 and both_above_50 and both_above_21 and pct_above_200 >= 56.0 and not cross_asset_drag:
        regime_status = "GREEN: CONFIRMED EXPANSION"
        action_plan = "Broad market in synchronized structural uptrend (Price > 21 EMA > 50 SMA > 200 EMA). Full authorization to pyramid momentum flags and stage-2 base resets."
        max_exposure = f"{int(75 * seasonal_mult)}% - {int(100 * seasonal_mult)}%"
        posture_box = "[+] EXPANSION POSTURE: BUY LEADING BREAKOUTS & FLAGS"
        regime_code = "EXPANSION"
    else:
        regime_status = "AMBER: ROTATIONAL DIGESTION"
        action_plan = f"Benchmarks consolidating (Breadth: {round(pct_above_200, 1)}% > 200 EMA). Index chop active; selective capital deployment into high-conviction base-resets and shelf sweeps only."
        max_exposure = f"{int(30 * seasonal_mult)}% - {int(55 * seasonal_mult)}%"
        posture_box = "[*] ROTATIONAL POSTURE: SELECTIVE HIGH-ASYMMETRY ENTRIES"
        regime_code = "ROTATION"

    momentum_count = category_counts.get("reset", 0) + category_counts.get("htf", 0)
    sweep_count = category_counts.get("sweep", 0) + category_counts.get("pivot", 0)

    print(f"  Regime Status       : {regime_status}")
    print(f"  Macro Posture       : {posture_box}")
    print(f"  Max Account Exposure: {max_exposure} (Calendar Multiplier: {round(seasonal_mult, 2)}x)")
    print(f"  Recommended Tactics : {action_plan}")
    print("  Eligible Setups     : Watchlist evaluation active. High-expectancy setups only.")
    print("-" * 112)
    print(f"  EQUITY BENCH