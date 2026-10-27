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

from pdf_engine import create_linkedin_carousel_pdf, export_carousel_cards_for_web, CAROUSEL_PDF_FILENAME  # PyMuPDF
from setups import (
    calculate_atr,
    calculate_macd,
    check_base_reset,
    check_htf,
    check_liquidity_sweep,
    check_pocket_pivot,
    resample_daily_to_weekly,
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
import requests
import yfinance as yf

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
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Sec-Ch-Ua": (
        '"Chromium";v="128", "Not;A=Brand";v="24", "Google Chrome";v="128"'
    ),
    "Sec-Ch-Ua-Mobile": "?0",
    "Sec-Ch-Ua-Platform": '"Windows"',
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Upgrade-Insecure-Requests": "1",
})

EXCLUDED_SECTORS = {
    "Real Estate",
    "Utilities",
    "Consumer Defensive",
    "Consumer Staples",
    "Financials",
    "Financial Services",
    "Basic Materials",
    "Healthcare",
    "Health Care",
    "Consumer Discretionary",
}

BANNED_INDUSTRY_KEYWORDS = [
    "apparel",
    "retail",
    "truck",
    "freight",
    "footwear",
    "bank",
    "credit",
    "mortgage",
    "homebuild",
    "grocery",
    "hotel",
    "resort",
    "cruise",
    "marine",
    "tobacco",
    "publishing",
    "broadcasting",
    "ground transportation",
    "building products",
    "consumer finance",
    "packaging",
    "containers",
    "auto parts",
    "dealership",
    "biotechnology",
    "drug",
    "pharmaceutical",
    "medical devices",
    "diagnostics",
    "healthcare providers",
    "industrial distribution",
    "restaurant",
    "machinery",
    "heavy equipment",
    "oil & gas midstream",
    "pipeline",
    "electronic manufacturing services",
    "it consulting",
    "research services",
]

# ---------------------------------------------------------

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


def evaluate_all_setups(ticker, daily_df, spy_1m_perf, sector_map):
  if is_acquisition_freeze(daily_df):
    return {
      "diagnostics": "Acquisition freeze / cash buyout pin",
      "above_200": False,
      "setups": [],
    }

  try:
    daily_df = daily_df.dropna()
    if len(daily_df) < 120:
      return {
          "diagnostics": "Insufficient data (<120 sessions)",
          "above_200": False,
      }

    c0 = daily_df["Close"].iloc[-1]
    daily_ema200 = (
        daily_df["Close"].ewm(span=200, adjust=False).mean().iloc[-1]
    )
    is_above_200 = bool(c0 > daily_ema200)

    volume = daily_df["Volume"]
    vol_sma50 = volume.rolling(50).mean().iloc[-1]
    adv_20_shares = int(volume.tail(20).mean())

    daily_dollar_vol = c0 * vol_sma50
    if c0 < 10.0 or daily_dollar_vol < 12_000_000:
      return {
          "diagnostics": "Liquidity Gate: Price <$10 or ADDV <$12M",
          "above_200": is_above_200,
      }

    stock_1m_perf = (
        (c0 - daily_df["Close"].iloc[-21]) / daily_df["Close"].iloc[-21]
    ) * 100
    rs_relative = stock_1m_perf - spy_1m_perf
    if rs_relative < -12.0:
      return {
          "diagnostics": "Relative Strength: Lagging S&P 500 by >12% (1M)",
          "above_200": is_above_200,
      }

    pct_above_200 = ((c0 - daily_ema200) / daily_ema200) * 100

    w_df = resample_daily_to_weekly(daily_df)
    if len(w_df) < 24:
      return {
          "diagnostics": "Insufficient weekly history (<24 weeks)",
          "above_200": is_above_200,
      }

    high_52w = (
        daily_df["High"].tail(252).max()
        if len(daily_df) >= 252
        else daily_df["High"].max()
    )

    results = {
        "ticker": ticker,
        "above_200": is_above_200,
        "base_reset": None,
        "htf": None,
        "pocket_pivot": None,
        "liquidity_sweep": None,
        "br_reason": None,
        "htf_reason": None,
        "pp_reason": None,
        "ls_reason": None,
        "diagnostics": "Evaluated",
    }

    res_br, r_br = check_base_reset(
        ticker,
        daily_df,
        w_df,
        c0,
        daily_ema200,
        pct_above_200,
        high_52w,
        adv_20_shares,
    )
    results["base_reset"] = res_br
    results["br_reason"] = r_br

    res_htf, r_htf = check_htf(
        ticker, daily_df, c0, daily_ema200, high_52w, adv_20_shares
    )
    results["htf"] = res_htf
    results["htf_reason"] = r_htf

    res_pp, r_pp = check_pocket_pivot(
        ticker, daily_df, c0, daily_ema200, high_52w, adv_20_shares
    )
    results["pocket_pivot"] = res_pp
    results["pp_reason"] = r_pp

    res_ls, r_ls = check_liquidity_sweep(
        ticker, daily_df, c0, daily_ema200, high_52w, adv_20_shares
    )
    results["liquidity_sweep"] = res_ls
    results["ls_reason"] = r_ls

    return results

  except Exception as e:
    return {"diagnostics": f"Error: {type(e).__name__}", "above_200": False}


# ---------------------------------------------------------
# 7. MACRO REGIME & EXPOSURE ENGINE
# ---------------------------------------------------------
def analyze_market_regime(total_evaluated, total_above_200, category_counts):
  print("\n" + "=" * 112)
  print(
      "                      MACRO MARKET REGIME & CAPITAL EXPOSURE DASHBOARD"
  )
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
      tnx_5d_chg = (
          ((tnx_c - tnx_s.iloc[-5]) / tnx_s.iloc[-5]) * 100
          if len(tnx_s) >= 5
          else 0.0
      )
      if tnx_c >= 4.75 or tnx_5d_chg >= 4.0:
        cross_asset_drag = True
        macro_warnings.append(
            f"⚡ YIELD SURGE: 10-Yr Yield at {round(tnx_c, 2)}%"
            f" ({'+' if tnx_5d_chg >= 0 else ''}{round(tnx_5d_chg, 1)}% 5d)."
            " Multiple drag active."
        )

  oil_c = 0.0
  oil_5d_chg = 0.0
  if "CL=F" in close_df.columns:
    oil_s = close_df["CL=F"].dropna()
    if not oil_s.empty:
      oil_c = oil_s.iloc[-1]
      oil_5d_chg = (
          ((oil_c - oil_s.iloc[-5]) / oil_s.iloc[-5]) * 100
          if len(oil_s) >= 5
          else 0.0
      )
      if oil_c >= 88.0:
        cross_asset_drag = True
        macro_warnings.append(
            f"🛢️ OIL PRICE SPIKE: WTI Crude at ${round(oil_c, 2)}/bbl"
            f" ({'+' if oil_5d_chg >= 0 else ''}{round(oil_5d_chg, 1)}% 5d)."
            " Inflation expectations repricing."
        )

  pct_above_200 = (total_above_200 / max(total_evaluated, 1)) * 100
  pct_below_200 = 100.0 - pct_above_200
  calendar_alerts, seasonal_mult, seasonal_context, days_to_opx, opx_label = (
      MacroEventCalendar.evaluate_calendar()
  )

  both_above_200 = bool(spy_above_200 and qqq_above_200)
  both_above_50 = bool(spy_above_50 and qqq_above_50)
  both_above_21 = bool(spy_above_21 and qqq_above_21)
  
  both_below_50 = bool(not spy_above_50 and not qqq_above_50)
  any_below_200 = bool(not spy_above_200 or not qqq_above_200)

  if any_below_200 or both_below_50 or pct_above_200 < 42.0:
    regime_status = "RED: STRUCTURAL CONTRACTION"
    action_plan = (
        "CAPITAL PRESERVATION POSTURE. Benchmarks trapped below 50 SMA / breadth compressed. "
        "Breakout failure rates peak here. Stand aside or trade small-sized liquidity sweeps only."
    )
    max_exposure = "0% - 20%"
    posture_box = "[!] DEFENSIVE POSTURE: CASH PRESERVATION / RISK-OFF"
    regime_code = "CONTRACTION"

  elif both_above_200 and both_above_50 and both_above_21 and pct_above_200 >= 56.0 and not cross_asset_drag:
    regime_status = "GREEN: CONFIRMED EXPANSION"
    action_plan = (
        "Broad market in synchronized structural uptrend (Price > 21 EMA > 50 SMA > 200 EMA). "
        "Full authorization to pyramid momentum flags and stage-2 base resets."
    )
    max_exposure = f"{int(75 * seasonal_mult)}% - {int(100 * seasonal_mult)}%"
    posture_box = "[+] EXPANSION POSTURE: BUY LEADING BREAKOUTS & FLAGS"
    regime_code = "EXPANSION"

  else:
    regime_status = "AMBER: ROTATIONAL DIGESTION"
    action_plan = (
        f"Benchmarks consolidating (Breadth: {round(pct_above_200, 1)}% > 200 EMA). "
        "Index chop active; selective capital deployment into high-conviction base-resets and shelf sweeps only."
    )
    max_exposure = f"{int(30 * seasonal_mult)}% - {int(55 * seasonal_mult)}%"
    posture_box = "[*] ROTATIONAL POSTURE: SELECTIVE HIGH-ASYMMETRY ENTRIES"
    regime_code = "ROTATION"

  momentum_count = category_counts.get("reset", 0) + category_counts.get(
      "htf", 0
  )
  sweep_count = category_counts.get("sweep", 0) + category_counts.get(
      "pivot", 0
  )

  print(f"  Regime Status       : {regime_status}")
  print(f"  Macro Posture       : {posture_box}")
  print(
      f"  Max Account Exposure: {max_exposure} (Calendar Multiplier:"
      f" {round(seasonal_mult, 2)}x)"
  )
  print(f"  Recommended Tactics : {action_plan}")
  print(
      "  Eligible Setups     : Watchlist evaluation active. High-expectancy"
      " setups only."
  )
  print("-" * 112)
  print(
      f"  EQUITY BENCHMARKS   : SPY = ${round(spy_c, 2)} (Above 21 EMA:"
      f" {spy_above_21} | Above 50 SMA: {spy_above_50} | Above 200 EMA:"
      f" {spy_above_200})"
  )
  print(
      f"                        QQQ = ${round(qqq_c, 2)} (Above 21 EMA:"
      f" {qqq_above_21} | Above 50 SMA: {qqq_above_50} | Above 200 EMA:"
      f" {qqq_above_200})"
  )
  print(
      f"  CROSS-ASSET MACRO   : 10Y Treasury Yield = {round(tnx_c, 2)}% | WTI"
      f" Crude Oil = ${round(oil_c, 2)}/bbl"
  )
  print(
      f"  UNIVERSE BREADTH    : {round(pct_above_200, 1)}% of stocks > 200 EMA"
      f" | {round(pct_below_200, 1)}% in Structural Downtrends"
  )
  print(
      f"  CANDIDATE PROFILE   : Breakout/Momentum ({momentum_count}) vs."
      f" False-Breakdown Sweeps ({sweep_count})"
  )
  print("-" * 112)

  if macro_warnings:
    for w in macro_warnings:
      print(f"  EXOGENOUS SHOCK     : {w}")

  for cal in calendar_alerts:
    print(f"  CALENDAR & RELEASES : {cal}")

  print(f"  MONTHLY SEASONALITY : {seasonal_context}")
  print(
      f"  OPEX COUNTDOWN      : {days_to_opx} days to {opx_label} (Expiration"
      " volatility & synthetic pinning)"
  )
  print("=" * 112 + "\n")

  dashboard_data = {
      "regime_status": regime_status,
      "regime_code": regime_code,
      "posture_box": posture_box,
      "max_exposure": max_exposure,
      "action_plan": action_plan,
      "spy_c": round(spy_c, 2),
      "spy_above_21": spy_above_21,
      "spy_above_50": spy_above_50,
      "spy_above_200": spy_above_200,
      "qqq_c": round(qqq_c, 2),
      "qqq_above_21": qqq_above_21,
      "qqq_above_50": qqq_above_50,
      "qqq_above_200": qqq_above_200,
      "tnx": round(tnx_c, 2),
      "tnx_5d_chg": round(tnx_5d_chg, 1),
      "oil": round(oil_c, 2),
      "oil_5d_chg": round(oil_5d_chg, 1),
      "pct_above_200": round(pct_above_200, 1),
      "pct_below_200": round(pct_below_200, 1),
      "momentum_count": momentum_count,
      "sweep_count": sweep_count,
      "warnings": macro_warnings,
      "calendar": calendar_alerts,
      "seasonality": seasonal_context,
      "days_to_opx": days_to_opx,
      "opx_label": opx_label,
  }
  return regime_status, dashboard_data


# ---------------------------------------------------------
# 8. TRAILING 5-DAY RUNNER TRACKER & EVALUATOR
# ---------------------------------------------------------
def update_and_evaluate_trailing_runners(todays_candidates):
  history = load_json_cache(HISTORY_TRACKER_FILE)
  if not isinstance(history, list):
    history = []

  today_str = datetime.date.today().isoformat()

  for c in todays_candidates:
    if c and c.get("Ticker") and c.get("Pivot_Trigger"):
      history.append({
          "date": today_str,
          "ticker": c["Ticker"],
          "category": c.get("Category", "Setup"),
          "pivot": float(c["Pivot_Trigger"]),
          "stop": float(c.get("Stop_Loss", 0.0)),
          "r_ratio": float(c.get("R_Ratio", 0.0)),
      })

  cutoff_date = (
      datetime.date.today() - datetime.timedelta(days=35)
  ).isoformat()
  history = [h for h in history if h.get("date", "") >= cutoff_date]
  save_json_cache(HISTORY_TRACKER_FILE, history)

  five_days_ago = (
      datetime.date.today() - datetime.timedelta(days=8)
  ).isoformat()
  candidates_to_check = [
      h for h in history if five_days_ago <= h["date"] < today_str
  ]

  if not candidates_to_check:
    print(
        "[RUNNERS] No historical setups logged within trailing 5 trading days."
    )
    return None

  check_tickers = list(set(h["ticker"] for h in candidates_to_check))
  print(
      f"[RUNNERS] Auditing post-entry expansion across {len(check_tickers)}"
      " historical setups..."
  )

  try:
    data = yf.download(
        check_tickers,
        period="1mo",
        interval="1d",
        group_by="ticker",
        auto_adjust=True,
        threads=True,
        progress=False,
        session=GLOBAL_HTTP_SESSION,
    )
  except Exception as e:
    print(f"[RUNNERS] Download error evaluating runners: {e}")
    return None

  best_runner = None
  max_gain = 0.0

  for item in candidates_to_check:
    sym = item["ticker"]
    entry_pivot = item["pivot"]

    try:
      if isinstance(data.columns, pd.MultiIndex):
        if sym not in data.columns.levels[0]:
          continue
        df_sym = data[sym].dropna()
      else:
        df_sym = data.dropna()

      df_post = df_sym.loc[df_sym.index >= pd.to_datetime(item["date"])]
      if df_post.empty:
        continue

      peak_high = float(df_post["High"].max())
      latest_close = float(df_post["Close"].iloc[-1])
      gain_pct = ((peak_high - entry_pivot) / entry_pivot) * 100

      if gain_pct > max_gain:
        max_gain = gain_pct
        risk_pct = max(
            ((entry_pivot - item["stop"]) / entry_pivot) * 100, 0.01
        )
        best_runner = {
            "ticker": sym,
            "category": item["category"],
            "rec_date": item["date"],
            "entry_pivot": round(entry_pivot, 2),
            "stop_loss": round(item["stop"], 2),
            "peak_high": round(peak_high, 2),
            "latest_close": round(latest_close, 2),
            "max_gain_pct": round(gain_pct, 1),
            "r_multiple": round(gain_pct / risk_pct, 1),
        }
    except Exception:
      continue

  if best_runner:
    print(
        "[RUNNERS] Top 5-Day Runner identified: $"
        f"{best_runner['ticker']} (+{best_runner['max_gain_pct']}%)"
    )
  return best_runner


def run_master_screener():
  universe, sector_map = fetch_institutional_universe_and_sectors()
  total_raw = len(universe)
  print(f"Loaded institutional universe of {total_raw} stocks.")

  stage0_candidates = stage_0_prune_by_sector(universe, sector_map)
  print(
      f"[*] Stage 0: Pruned {total_raw - len(stage0_candidates)} non-momentum"
      f" tickers via sector metadata. {len(stage0_candidates)} remain."
  )

  stage1_survivors = stage_1_prune_by_liquidity(
      stage0_candidates, chunk_size=CHUNK_SIZE
  )
  print(
      f"[*] Stage 1 Complete: {len(stage1_survivors)} liquid institutional"
      " candidates qualified for deep scan."
  )
  print(
      "[*] Stage 2: Ingesting 15-month historical data (period='15mo') only for"
      " survivors...\n"
  )

  spy_data = yf.download(
      "SPY",
      period="6mo",
      interval="1d",
      progress=False,
      session=GLOBAL_HTTP_SESSION,
  )["Close"]
  spy_1m_perf = (
      (spy_data.iloc[-1] - spy_data.iloc[-21]) / spy_data.iloc[-21]
  ) * 100
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
  total_chunks = (len(stage1_survivors) + CHUNK_SIZE - 1) // CHUNK_SIZE

  for idx in range(0, len(stage1_survivors), CHUNK_SIZE):
    chunk = stage1_survivors[idx : idx + CHUNK_SIZE]
    chunk_idx = (idx // CHUNK_SIZE) + 1
    print(
        f"[{chunk_idx:>2}/{total_chunks}] Analyzing 15-month OHLCV for"
        f" {len(chunk):>2} tickers...",
        end="",
        flush=True,
    )

    batch_data = None
    for attempt in range(3):
      try:
        batch_data = yf.download(
            tickers=chunk,
            period="15mo",
            interval="1d",
            group_by="ticker",
            auto_adjust=True,
            threads=False,
            session=GLOBAL_HTTP_SESSION,
            progress=False,
            ignore_tz=True,
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
        try:
          if isinstance(batch_data.columns, pd.MultiIndex):
            if sym in batch_data.columns.levels[0]:
              future_to_sym[
                  executor.submit(
                      evaluate_all_setups,
                      sym,
                      batch_data[sym],
                      spy_1m_perf,
                      sector_map,
                  )
              ] = sym
          else:
            future_to_sym[
                executor.submit(
                    evaluate_all_setups,
                    sym,
                    batch_data,
                    spy_1m_perf,
                    sector_map,
                )
            ] = sym
        except Exception as e:
          print(f" [!] Task dispatch error for {sym}: {e}")

      for future in as_completed(future_to_sym):
        total_evaluated += 1
        sym = future_to_sym[future]
        try:
          res = future.result()
        except Exception as exc:
          print(f" [!] Unhandled exception processing {sym}: {exc}")
          continue

        diag_status = res.get("diagnostics", "Unknown")
        macro_diag[diag_status] += 1

        if res.get("above_200"):
          total_above_200 += 1

        if diag_status == "Evaluated":
          total_passed_universal += 1
          matched_any = False

          if res["base_reset"]:
            base_resets.append(res["base_reset"])
            matched_any = True
          else:
            br_diag[res["br_reason"]] += 1

          if res["htf"]:
            htfs.append(res["htf"])
            matched_any = True
          else:
            htf_diag[res["htf_reason"]] += 1

          if res["pocket_pivot"]:
            pocket_pivots.append(res["pocket_pivot"])
            matched_any = True
          else:
            pp_diag[res["pp_reason"]] += 1

          if res["liquidity_sweep"]:
            liquidity_sweeps.append(res["liquidity_sweep"])
            matched_any = True
          else:
            ls_diag[res["ls_reason"]] += 1

          if matched_any:
            chunk_matches += 1

    print(f" done ({chunk_matches} setups flagged)")
    time.sleep(1.0)

  category_counts = {
      "reset": len(base_resets),
      "htf": len(htfs),
      "pivot": len(pocket_pivots),
      "sweep": len(liquidity_sweeps),
  }

  regime, dashboard = analyze_market_regime(
      total_evaluated, total_above_200, category_counts
  )
  days_to_opx = dashboard.get("days_to_opx", 15)

  unique_passed_tickers = list(
      set(
          [r["Ticker"] for r in base_resets]
          + [r["Ticker"] for r in htfs]
          + [r["Ticker"] for r in pocket_pivots]
          + [r["Ticker"] for r in liquidity_sweeps]
      )
  )

  print(
      f"\nProfiling Earnings Dates & Zacks Ranks for"
      f" {len(unique_passed_tickers)} candidates...",
      end="",
      flush=True,
  )
  earnings_map = {}
  with ThreadPoolExecutor(max_workers=8) as executor:
    earn_futures = {
        executor.submit(evaluate_earnings_proximity, t): t
        for t in unique_passed_tickers
    }
    for future in as_completed(earn_futures):
      tk = earn_futures[future]
      earnings_map[tk] = future.result()

  zacks_map = profile_zacks_with_local_tenure(unique_passed_tickers)
  print(" done.\n")

  for r in base_resets:
    r["Category"] = "Base-Reset"
    r["Zacks_Rank"] = zacks_map.get(r["Ticker"], "N/A")
    r["Earnings_Risk"] = earnings_map.get(r["Ticker"], "Unknown")
    r["Structural_Catalyst"] = determine_structural_catalyst(r, days_to_opx)
    r["Execution_Protocol"] = generate_kb_execution_protocol(r, days_to_opx)

  for r in htfs:
    r["Category"] = "Momentum Flag"
    r["Zacks_Rank"] = zacks_map.get(r["Ticker"], "N/A")
    r["Earnings_Risk"] = earnings_map.get(r["Ticker"], "Unknown")
    r["Structural_Catalyst"] = determine_structural_catalyst(r, days_to_opx)
    r["Execution_Protocol"] = generate_kb_execution_protocol(r, days_to_opx)

  for r in pocket_pivots:
    r["Category"] = "Pocket Pivot"
    r["Zacks_Rank"] = zacks_map.get(r["Ticker"], "N/A")
    r["Earnings_Risk"] = earnings_map.get(r["Ticker"], "Unknown")
    r["Structural_Catalyst"] = determine_structural_catalyst(r, days_to_opx)
    r["Execution_Protocol"] = generate_kb_execution_protocol(r, days_to_opx)

  for r in liquidity_sweeps:
    r["Category"] = "Liquidity Sweep"
    r["Zacks_Rank"] = zacks_map.get(r["Ticker"], "N/A")
    r["Earnings_Risk"] = earnings_map.get(r["Ticker"], "Unknown")
    r["Structural_Catalyst"] = determine_structural_catalyst(r, days_to_opx)
    r["Execution_Protocol"] = generate_kb_execution_protocol(r, days_to_opx)

  filtered_base_resets = [
      r
      for r in base_resets
      if (
          any(r["Zacks_Rank"].startswith(rk) for rk in ["#1", "#2"])
          or r["Zacks_Rank"] == "N/A"
      )
      and "🚨 DANGER" not in r["Earnings_Risk"]
  ]

  def universal_quality_filter(pool):
    return [
        r
        for r in pool
        if not any(r["Zacks_Rank"].startswith(rk) for rk in ["#4", "#5"])
        and "🚨 DANGER" not in r["Earnings_Risk"]
    ]

  filtered_htfs = universal_quality_filter(htfs)
  filtered_pockets = universal_quality_filter(pocket_pivots)
  filtered_sweeps = universal_quality_filter(liquidity_sweeps)


  # ====================================================================================================================
  # WATCHLIST EXPORTS (CSVs) FOR SOCIAL CHARTING ENGINE
  # ====================================================================================================================
  pd.DataFrame(filtered_base_resets).to_csv("watchlist_base_resets.csv", index=False)
  pd.DataFrame(filtered_htfs).to_csv("watchlist_momentum_flags.csv", index=False)
  pd.DataFrame(filtered_pockets).to_csv("watchlist_pocket_pivots.csv", index=False)
  pd.DataFrame(filtered_sweeps).to_csv("watchlist_liquidity_sweeps.csv", index=False)


  # ====================================================================================================================
  # ASSET GENERATION (CHARTS)
  # ====================================================================================================================
  try:
      print("[*] Generating lovely custom candlestick charts...")
      import generate_live_charts
      generate_live_charts.generate_all()
  except Exception as e:
      print(f"[!] Chart generation error: {e}")


  # ====================================================================================================================
  # MASTER SPREADSHEET EXPORT
  # ====================================================================================================================
  all_current_setups = (
      filtered_base_resets
      + filtered_htfs
      + filtered_pockets
      + filtered_sweeps
  )
  
  if all_current_setups:
      master_df = pd.DataFrame(all_current_setups)
      
      front_cols = ["Ticker", "Category", "Close", "Pivot_Trigger", "Stop_Loss", "Risk_%", "R_Ratio", "Conviction_Score"]
      export_cols = front_cols + [c for c in master_df.columns if c not in front_cols]
      master_df = master_df[[c for c in export_cols if c in master_df.columns]]
      
      master_df.sort_values(by=["Category", "Conviction_Score"], ascending=[True, False], inplace=True)
      
      master_df.to_csv("master_screener_results.csv", index=False)
      print(f"[SPREADSHEET] Exported {len(master_df)} consolidated setups to master_screener_results.csv")
  else:
      print("[SPREADSHEET] No setups met the quality criteria for export today.")

  top_runner = update_and_evaluate_trailing_runners(all_current_setups)


  # ====================================================================================================================
  # TERMINAL DISPLAY: CATEGORY TABLES 1 - 4
  # ====================================================================================================================
  terminal_categories = [
      ("CATEGORY 1: BASE-RESET INFLECTIONS (Above 200 EMA >= 0.5%, Headroom >= 16% or ATH, R:R >= 2.5)", filtered_base_resets),
      ("CATEGORY 2: MOMENTUM BULL FLAGS (CAN SLIM Pole >= 45.0%, Flag <= 18d, Depth <= 14%, Blue Sky Friendly)", filtered_htfs),
      ("CATEGORY 3: POCKET PIVOT SQUEEZES (Headroom >= 15% or ATH, R:R >= 2.0, Safe Earnings)", filtered_pockets),
      ("CATEGORY 4: LIQUIDITY SWEEPS (Price >= $15, Non-Retail/Midstream, Mean-Reversion R:R >= 2.5)", filtered_sweeps),
  ]

  for title, pool in terminal_categories:
      print("\n" + "=" * 148)
      print(f"                    {title}")
      print("=" * 148)
      if pool:
          df_disp = pd.DataFrame(pool)
          disp_cols = [
              c for c in [
                  "Ticker", "Close", "Headroom_%", "Above_200_%", "Shelf_Level", "Flush_Low",
                  "Ext_10EMA_%", "Above_200EMA_%", "Vol_Ratio", "Vol_Pocket_Ratio", "Conviction_Score",
                  "Pivot_Trigger", "Stop_Loss", "Risk_%", "R_Ratio", "ADV_20", "1Min_Vol_Hurdle",
                  "Execution_Archetype", "Category", "Zacks_Rank", "Earnings_Risk"
              ] if c in df_disp.columns
          ]
          print(df_disp[disp_cols].to_string(index=False))
      else:
          print("No candidates currently meeting quality gates.")


  # ====================================================================================================================
  # REGIME-AWARE OPTIMAL SETUP SLOT ASSIGNMENT & ADAPTIVE ALLOCATION
  # ====================================================================================================================
  regime_tag = dashboard.get("regime_code", "ROTATION")
  is_contraction = regime_tag == "CONTRACTION" or "CONTRACTION" in dashboard.get("regime_status", "")
  is_expansion = regime_tag == "EXPANSION" or "EXPANSION" in dashboard.get("regime_status", "")

  cand_br = sorted(filtered_base_resets, key=lambda x: x.get("Conviction_Score", 0), reverse=True)
  cand_htf = sorted(filtered_htfs, key=lambda x: x.get("Conviction_Score", 0), reverse=True)
  cand_pp = sorted(filtered_pockets, key=lambda x: x.get("Conviction_Score", 0), reverse=True)
  cand_ls = sorted(filtered_sweeps, key=lambda x: x.get("Conviction_Score", 0), reverse=True)

  if is_contraction:
      top_br = None
      top_htf = None
      top_pp = None
      top_ls = cand_ls[0] if cand_ls else None
  elif is_expansion:
      top_br = cand_br[0] if cand_br else None
      top_htf = cand_htf[0] if cand_htf else None
      top_pp = cand_pp[0] if cand_pp else None
      top_ls = cand_ls[0] if cand_ls else None
      assigned = {c["Ticker"] for c in [top_br, top_htf, top_pp, top_ls] if c}
      backfill_pool = [c for c in all_current_setups if c.get("Ticker") not in assigned]
      if not top_br and backfill_pool: top_br = backfill_pool.pop(0); assigned.add(top_br["Ticker"])
      if not top_htf and backfill_pool: top_htf = backfill_pool.pop(0); assigned.add(top_htf["Ticker"])
      if not top_pp and backfill_pool: top_pp = backfill_pool.pop(0); assigned.add(top_pp["Ticker"])
      if not top_ls and backfill_pool: top_ls = backfill_pool.pop(0); assigned.add(top_ls["Ticker"])
  else:
      top_br = cand_br[0] if cand_br else None
      top_htf = cand_htf[0] if cand_htf else None
      top_pp = cand_pp[0] if cand_pp else None
      top_ls = cand_ls[0] if cand_ls else None

  print("\n=== OPTIMAL SETUP SLOTS IDENTIFIED ===")
  def _fmt(s):
      return f"{s['Ticker']} ({s.get('R_Ratio', 'N/A')}R)" if s else "None (Cash / Sidelined)"

  print(f"Slot 1 (Base-Reset / Primary): {_fmt(top_br)}")
  print(f"Slot 2 (HTF / Secondary):      {_fmt(top_htf)}")
  print(f"Slot 3 (Pocket / Secondary):   {_fmt(top_pp)}")
  print(f"Slot 4 (Sweep / Secondary):    {_fmt(top_ls)}\n")


  # ====================================================================================================================
  # PDF GENERATION & WEB EXPORT
  # ====================================================================================================================
  try:
      print("[*] Compiling fresh daily market intelligence PDF...")
      create_linkedin_carousel_pdf(
          filename=CAROUSEL_PDF_FILENAME,
          regime_status=regime,
          posture_box=dashboard.get("posture_box", "SELECTIVE"),
          max_exposure=dashboard.get("max_exposure", "N/A"),
          calendar_alerts=dashboard.get("calendar", []),
          pct_above_200=dashboard.get("pct_above_200", 0.0),
          top_runner=top_runner,
          top_br=top_br,
          top_htf=top_htf,
          top_pp=top_pp,
          top_ls=top_ls,
          dashboard=dashboard,
      )
      export_carousel_cards_for_web(CAROUSEL_PDF_FILENAME)
  except Exception as e:
      print(f"[!] PDF generation error: {e}")

  web_terminal_payload = {
      "generated_at": datetime.datetime.now(datetime.timezone.utc).strftime(
          "%Y-%m-%d %H:%M UTC"
      ),
      "macro": dashboard,
      "top_runner": top_runner,
      "watchlists": {
          "base_resets": filtered_base_resets,
          "momentum_flags": filtered_htfs,
          "pocket_pivots": filtered_pockets,
          "liquidity_sweeps": filtered_sweeps,
      },
  }
  with open(TERMINAL_FEED_FILENAME, "w", encoding="utf-8") as f:
    json.dump(web_terminal_payload, f, indent=2)
  print(f"[TERMINAL] Exported {TERMINAL_FEED_FILENAME}")

  slot_tickers = [c["Ticker"] for c in [top_br, top_htf, top_pp, top_ls] if c]
  primary_ticker = top_br["Ticker"] if top_br else (slot_tickers[0] if slot_tickers else None)

  broadcast_meta = {
      "pdf_path": CAROUSEL_PDF_FILENAME,
      "date": datetime.date.today().isoformat(),
      "regime_code": dashboard.get("regime_code", "ROTATION"),
      "regime_status": regime,
      "posture_box": dashboard.get("posture_box", "SELECTIVE"),
      "max_exposure": dashboard.get("max_exposure", "N/A"),
      "pct_above_200": dashboard.get("pct_above_200", 0.0),
      "primary_ticker": primary_ticker,
      "slot_tickers": slot_tickers,
      "focus_tickers": slot_tickers[:3],
      "top_runner": top_runner,
      "top_br": top_br,
      "top_htf": top_htf,
      "top_pp": top_pp,
      "top_ls": top_ls,
  }
  with open(POST_META_FILENAME, "w", encoding="utf-8") as f:
    json.dump(broadcast_meta, f, indent=2)
  print(f"[METADATA] Saved {POST_META_FILENAME}")


if __name__ == "__main__":
  try:
    run_master_screener()
  finally:
    GLOBAL_HTTP_SESSION.close()
    print("\n[COMPLETE] Screener run finished successfully.")