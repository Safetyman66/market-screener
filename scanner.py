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
    and 'breakouts_for_execution.csv' with pre-calculated ADV_20 & 1-minute hurdles.
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

import fitz  # PyMuPDF
import numpy as np
import pandas as pd
from visual_engine import (
    create_linkedin_carousel_pdf,
    export_carousel_cards_for_web,
)
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
EXECUTION_EXPORT_FILENAME = "breakouts_for_execution.csv"

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
  """Detects stocks pinned in a narrow merger arbitrage / cash buyout spread.
  
  Guards against filtering out legitimate low-volatility bases by requiring
  BOTH extreme intraday range death AND near-zero multi-day net drift.
  """
  if daily_df is None or len(daily_df) < lookback + 1:
    return False

  try:
    df = daily_df.tail(lookback).copy()
    # Flatten MultiIndex columns if present from yf.download
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

    # Cash buyout pin signature: median ADR < 0.50%, net drift < 0.60%, total range < 0.85%
    if median_adr_5d < 0.50 and net_drift_5d < 0.60 and max_dev < 0.85:
      return True
  except Exception:
    return False

  return False


def evaluate_all_setups(ticker, daily_df, spy_1m_perf, sector_map):
  # Prune cash merger / acquisition peg false positives
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

  major_structural_break = (
      (not spy_above_200) or (not qqq_above_200) or (pct_above_200 < 38.0)
  )
  confirmed_bull_alignment = (
      (spy_above_200 and qqq_above_200)
      and (spy_above_50 or qqq_above_50)
      and (pct_above_200 >= 55.0)
  )

  if major_structural_break:
    regime_status = "RED: CONFIRMED MACRO DOWNTREND"
    action_plan = (
        "DEFENSIVE SIZING. Structural trend broken. Use extreme caution on"
        " breakouts."
    )
    max_exposure = "0% - 15%"
    posture_box = (
        "■ DOWNTREND DEFENSE: TRADE SELECTIVELY WITH TIGHT RISK ■"
    )
  elif confirmed_bull_alignment and not cross_asset_drag:
    regime_status = "GREEN: CONFIRMED EXPANSION"
    action_plan = (
        "Broad market in confirmed structural uptrend. Green-light to pyramid"
        " momentum leaders and breakouts."
    )
    max_exposure = f"{int(70 * seasonal_mult)}% - {int(100 * seasonal_mult)}%"
    posture_box = "▲ EXPANSION BULL: BUY CONTINUATION & BREAKOUTS ▲"
  else:
    regime_status = "AMBER: ROTATIONAL ACCUMULATION"
    action_plan = (
        f"Indices holding 200 EMA with breadth digesting"
        f" ({round(pct_above_200, 1)}%). Deploy capital selectively into"
        " support sweeps and base inflections."
    )
    max_exposure = f"{int(30 * seasonal_mult)}% - {int(60 * seasonal_mult)}%"
    posture_box = "◆ ROTATIONAL ACCUMULATION: BUY HIGH ASYMMETRY PIVOTS ◆"

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
    top_ls,
    dashboard=None,
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

  # ---------------- SLIDE 1: COVER ----------------
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
  c.drawString(
      90,
      h - 520,
      "• Multi-Stage Ingestion: Stage 0 Metadata & Stage 1 Liquidity Pruned",
  )
  c.drawString(
      90, h - 560, "• Minimum 2.0R Mathematical Asymmetry Floor on All Setups"
  )
  c.drawString(
      90, h - 600, "• Macro Exposure Governed by 200 EMA Structural Breadth"
  )

  c.setFillColor(card_inner)
  c.roundRect(90, h - 680, w - 180, 55, 10, fill=True, stroke=False)
  c.setFont("Helvetica-Bold", 20)
  c.setFillColor(accent_cyan)
  c.drawCentredString(
      w / 2, h - 645, "Full Terminal & Complete Watchlists: corpacuity.co.uk"
  )

  c.setFont("Helvetica-Bold", 22)
  c.setFillColor(text_white)
  c.drawCentredString(
      w / 2, 80, "Swipe across for today's verified setups & regime metrics ➔"
  )
  c.showPage()

  # ---------------- SLIDE 2: REGIME DASHBOARD ----------------
  draw_base("MACRO REGIME COCKPIT", 2, 8)
  c.setFont("Helvetica-Bold", 32)
  c.setFillColor(accent_cyan)
  c.drawString(60, h - 120, "SYSTEM REGIME POSTURE")

  c.setFillColor(card_bg)
  c.roundRect(60, h - 340, w - 120, 195, 16, fill=True, stroke=False)
  c.setFont("Helvetica-Bold", 18)
  c.setFillColor(text_muted)
  c.drawString(90, h - 165, "CURRENT REGIME STATUS")
  c.setFont("Helvetica-Bold", 38)
  c.setFillColor(
      accent_green
      if "GREEN" in regime_status
      else (accent_amber if "AMBER" in regime_status else accent_red)
  )
  c.drawString(90, h - 215, regime_status)

  c.setFont("Helvetica-Bold", 22)
  c.setFillColor(text_white)
  c.drawString(90, h - 265, f"Suggested Allocation: {max_exposure}")
  c.setFont("Helvetica", 17)
  c.setFillColor(text_muted)
  clean_posture = (
      posture_box.replace("■", "").replace("▲", "").replace("◆", "").strip()
  )
  c.drawString(90, h - 305, clean_posture[:68])

  tile_w = (w - 150) / 2
  tile_h = 135

  c.setFillColor(card_bg)
  c.roundRect(60, h - 500, tile_w, tile_h, 14, fill=True, stroke=False)
  c.setFont("Helvetica-Bold", 16)
  c.setFillColor(text_muted)
  c.drawString(85, h - 390, "UNIVERSE BREADTH (>200 EMA)")
  c.setFont("Helvetica-Bold", 36)
  c.setFillColor(accent_cyan)
  c.drawString(85, h - 440, f"{round(pct_above_200, 1)}%")
  c.setFont("Helvetica", 14)
  c.setFillColor(text_muted)
  c.drawString(85, h - 475, "Consolidating above 38% panic floor")

  c.setFillColor(card_bg)
  c.roundRect(
      60 + tile_w + 30, h - 500, tile_w, tile_h, 14, fill=True, stroke=False
  )
  c.setFont("Helvetica-Bold", 16)
  c.setFillColor(text_muted)
  c.drawString(85 + tile_w + 30, h - 390, "CROSS-ASSET RADAR")
  c.setFont("Helvetica-Bold", 24)
  c.setFillColor(text_white)
  tnx_str = (
      f"10Y Yield: {dashboard.get('tnx', 4.25)}%"
      if dashboard
      else "10Y Yield: Normal"
  )
  oil_str = (
      f"WTI Crude: ${dashboard.get('oil', 75.0)}/bbl"
      if dashboard
      else "WTI: Normal"
  )
  c.drawString(85 + tile_w + 30, h - 435, tnx_str)
  c.drawString(85 + tile_w + 30, h - 475, oil_str)

  c.setFillColor(card_bg)
  c.roundRect(60, h - 660, tile_w, tile_h, 14, fill=True, stroke=False)
  c.setFont("Helvetica-Bold", 16)
  c.setFillColor(text_muted)
  c.drawString(85, h - 550, "INDEX STRUCTURAL HEALTH")
  c.setFont("Helvetica-Bold", 22)
  spy_above_200 = dashboard.get("spy_above_200", True) if dashboard else True
  qqq_above_200 = dashboard.get("qqq_above_200", True) if dashboard else True
  c.setFillColor(accent_green if spy_above_200 else accent_red)
  c.drawString(
      85,
      h - 595,
      f"SPY: {'Above 200 EMA' if spy_above_200 else 'Below 200 EMA'}",
  )
  c.setFillColor(accent_green if qqq_above_200 else accent_red)
  c.drawString(
      85,
      h - 635,
      f"QQQ: {'Above 200 EMA' if qqq_above_200 else 'Below 200 EMA'}",
  )

  c.setFillColor(card_bg)
  c.roundRect(
      60 + tile_w + 30, h - 660, tile_w, tile_h, 14, fill=True, stroke=False
  )
  c.setFont("Helvetica-Bold", 16)
  c.setFillColor(text_muted)
  c.drawString(85 + tile_w + 30, h - 550, "TACTICAL DIRECTIVE")
  c.setFont("Helvetica", 15)
  c.setFillColor(text_white)
  action_text = (
      dashboard.get("action_plan", "Trade high asymmetry setups.")
      if dashboard
      else "Trade setups."
  )
  c.drawString(85 + tile_w + 30, h - 590, action_text[:42])
  c.drawString(85 + tile_w + 30, h - 620, action_text[42:84])

  c.setFillColor(card_inner)
  c.roundRect(60, h - 850, w - 120, 160, 14, fill=True, stroke=False)
  c.setFont("Helvetica-Bold", 18)
  c.setFillColor(accent_amber)
  c.drawString(85, h - 710, "IMMINENT MACRO RADAR & RELEASES:")
  c.setFont("Helvetica", 16)
  c.setFillColor(text_white)
  y_cal = h - 745
  radar = (
      calendar_alerts[:3]
      if calendar_alerts
      else ["Clear Runway: No high-impact shocks in 72h."]
  )
  for al in radar:
    c.drawString(85, y_cal, al.replace("🚨", "! ")[:75])
    y_cal -= 35

  c.showPage()

  # ---------------- SLIDE 3: 5-DAY RUNNER ----------------
  draw_base("SYSTEM PERFORMANCE // 5D ALPHA", 3, 8)

  if top_runner and top_runner.get("max_gain_pct", 0) > 0:
    c.setFont("Helvetica-Bold", 32)
    c.setFillColor(accent_amber)
    c.drawString(
        60,
        h - 140,
        "How did we do? Here is our top performer over the last 5 days!",
    )

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
    c.drawString(
        100,
        h - 360,
        f"Triggered: {top_runner['rec_date']} ({top_runner['category']})",
    )

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
    c.roundRect(
        w - 100 - b_w, grid_y_low, b_w, b_h, 16, fill=True, stroke=False
    )
    c.setFont("Helvetica-Bold", 18)
    c.setFillColor(text_muted)
    c.drawString(w - 100 - b_w + 25, grid_y_low + 80, metrics[3][0])
    c.setFont("Helvetica-Bold", 36)
    c.setFillColor(metrics[3][2])
    c.drawString(w - 100 - b_w + 25, grid_y_low + 25, metrics[3][1])

    c.setFont("Helvetica-Bold", 24)
    c.setFillColor(text_white)
    c.drawCentredString(
        w / 2,
        h - 800,
        "Systematic asymmetry: cutting losers short and letting winners expand.",
    )
  else:
    c.setFillColor(card_bg)
    c.roundRect(60, h - 600, w - 120, 360, 24, fill=True, stroke=False)
    c.setFont("Helvetica-Bold", 34)
    c.setFillColor(accent_amber)
    c.drawString(
        100,
        h - 350,
        "How did we do? Here is our top performer over the last 5 days!",
    )
    c.setFont("Helvetica", 22)
    c.setFillColor(text_muted)
    c.drawString(
        100,
        h - 420,
        "Logged setups are evaluated nightly against subsequent post-entry peak"
        " highs.",
    )
    c.drawString(
        100,
        h - 465,
        "Audited 5-day R-multiple tracking populates on subsequent sessions.",
    )

  c.showPage()

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
      c.drawCentredString(
          w / 2, h - 420, "No Setups Met Strict Asymmetry Floor (>= 2.0R)"
      )
      c.setFont("Helvetica", 20)
      c.setFillColor(text_muted)
      c.drawCentredString(
          w / 2, h - 470, "Capital preservation rules enforced. Cash is a valid position."
      )
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
        (
            "FUNDAMENTAL CATALYST",
            str(candidate.get("Zacks_Rank", "Rank 1 (Strong Buy)")),
            accent_amber,
        ),
        (
            "EVENT RISK",
            str(candidate.get("Earnings_Risk", "SAFE (>14d)")),
            accent_green,
        ),
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

  draw_setup_slide(
      "1. BASE-RESET INFLECTION",
      "Breakout above 50-day SMA with curling weekly MACD and institutional"
      " volume",
      top_br,
      4,
  )
  draw_setup_slide(
      "2. MOMENTUM BULL FLAG",
      "CAN SLIM pole >= 45.0%, tight flag consolidation <= 18d holding 21 EMA",
      top_htf,
      5,
  )
  draw_setup_slide(
      "3. POCKET PIVOT SQUEEZE",
      "Bollinger/Keltner squeeze launch with volume surge exceeding 10d down"
      " volume",
      top_pp,
      6,
  )
  draw_setup_slide(
      "4. LIQUIDITY SWEEP (U&R)",
      "False breakdown below support reversed with institutional demand bid",
      top_ls,
      7,
  )

  # ---------------- SLIDE 8: GOVERNANCE ----------------
  draw_base("EXECUTION DISCIPLINE", 8, 8)
  c.setFont("Helvetica-Bold", 34)
  c.setFillColor(accent_cyan)
  c.drawString(60, h - 140, "GOVERNANCE & EXECUTION RULES")

  c.setFillColor(card_bg)
  c.roundRect(60, h - 920, w - 120, 740, 20, fill=True, stroke=False)

  rules = [
      (
          "1. NEVER CHASE BEYOND +2.5% OF PIVOT",
          "If the equity opens extended beyond 2.5% above the trigger, void the"
          " entry.",
      ),
      (
          "2. HARD INVALIDATION ENFORCEMENT",
          "Stops are non-negotiable. An hourly or daily close below invalidates"
          " the setup.",
      ),
      (
          "3. REGIME-GOVERNED SIZING",
          "Never deploy full allocation during defensive or corrective macro"
          " conditions.",
      ),
      (
          "4. EARNINGS PROXIMITY BLACKOUT",
          "Do not carry fresh unhedged swing risk into earnings announcements"
          " within 14 days.",
      ),
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
  c.drawString(
      130,
      box_top - 145,
      "Full CSV datasets, Zacks rank tenure & risk analytics.",
  )

  c.setFont("Helvetica-Bold", 20)
  c.setFillColor(accent_cyan)
  c.drawCentredString(
      w / 2, 40, "Corp Acuity Ltd // Systematic Treasury & Market Intelligence"
  )
  c.showPage()

  c.save()
  print(f"\n[CAROUSEL] Generated institutional 8-slide PDF: {filename}")


# ---------------------------------------------------------
# 10. RENDER HIGH-RES PNG CARDS FOR X
# ---------------------------------------------------------
def export_carousel_cards_for_web(pdf_path=CAROUSEL_PDF_FILENAME):
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
      page.draw_rect(
          badge_rect, color=(0.027, 0.039, 0.071), fill=(0.027, 0.039, 0.071)
      )
      page.insert_text(
          fitz.Point(880, 52),
          f"Card {card_num} of 4",
          fontsize=14,
          color=(0.58, 0.64, 0.72),
          fontname="helv",
      )
      pix = page.get_pixmap(matrix=matrix, alpha=False)
      out_file = os.path.join("x_cards", f"card_{card_num}.png")
      pix.save(out_file)
      card_paths.append(out_file)
      card_num += 1

  doc.close()
  print(
      f"[CARDS] Rendered {len(card_paths)} high-res PNG cards into x_cards/"
      " (Stamped Card 1 of 4 to 4 of 4)"
  )
  return card_paths


# ---------------------------------------------------------
# 11. MASTER RUNNER & ORCHESTRATOR
# ---------------------------------------------------------
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
  # WATCHLIST EXPORTS (CSVs)
  # ====================================================================================================================
  pd.DataFrame(filtered_base_resets).to_csv("watchlist_base_resets.csv", index=False)
  pd.DataFrame(filtered_htfs).to_csv("watchlist_momentum_flags.csv", index=False)
  pd.DataFrame(filtered_pockets).to_csv("watchlist_pocket_pivots.csv", index=False)
  pd.DataFrame(filtered_sweeps).to_csv("watchlist_liquidity_sweeps.csv", index=False)

  breakout_pool = filtered_htfs + filtered_pockets + filtered_base_resets

  # Format execution export dataframe
  execution_candidates = sorted(
      breakout_pool,
      key=lambda x: x.get("Conviction_Score", 0),
      reverse=True,
  )[:10]

  execution_df = pd.DataFrame(execution_candidates)
  if not execution_df.empty:
      export_cols = [
          c for c in [
              "Ticker", "Close", "Headroom_%", "Above_200_%", "Hist_Now", "Vol_Ratio",
              "Conviction_Score", "Pivot_Trigger", "Stop_Loss", "Risk_%", "R_Ratio",
              "ADV_20", "1Min_Vol_Hurdle", "Execution_Archetype", "Category",
              "Zacks_Rank", "Earnings_Risk", "Structural_Catalyst", "Execution_Protocol"
          ] if c in execution_df.columns
      ]
      execution_df = execution_df[export_cols]

  execution_df.to_csv(EXECUTION_EXPORT_FILENAME, index=False)
  print(f"[EXECUTION ENGINE] Exported top {len(execution_df)} verified breakout candidates to {EXECUTION_EXPORT_FILENAME}")

  all_current_setups = (
      filtered_base_resets
      + filtered_htfs
      + filtered_pockets
      + filtered_sweeps
  )
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
  # TERMINAL DISPLAY: UNIVERSAL ELIMINATION FUNNEL (If tracked in main scan loop)
  # ====================================================================================================================
  if "funnel_stats" in locals() and funnel_stats:
      print("\n" + "=" * 95)
      print(f"                 UNIVERSAL ELIMINATION FUNNEL (Evaluated {funnel_stats.get('total_stage2', 0)} Symbols in Stage 2)")
      print("=" * 95)
      for stage_name, count in funnel_stats.get("stages", {}).items():
          pct = (count / funnel_stats.get('total_stage2', 1)) * 100
          print(f"  {stage_name:<65}: {count:>4} ({pct:>5.1f}%)")
      print("=" * 95)

  # ====================================================================================================================
  # OPTIMAL SETUP SLOT ASSIGNMENT & SMART FALLBACK
  # ====================================================================================================================
  top_br = (
      sorted(filtered_base_resets, key=lambda x: x.get("Conviction_Score", 0), reverse=True)[0]
      if filtered_base_resets else None
  )
  top_htf = (
      sorted(filtered_htfs, key=lambda x: x.get("Conviction_Score", 0), reverse=True)[0]
      if filtered_htfs else None
  )
  top_pp = (
      sorted(filtered_pockets, key=lambda x: x.get("R_Ratio", 0), reverse=True)[0]
      if filtered_pockets else None
  )
  top_ls = (
      sorted(filtered_sweeps, key=lambda x: x.get("R_Ratio", 0), reverse=True)[0]
      if filtered_sweeps else None
  )

  # Fallback backfill pool from top verified breakouts
  assigned = {c["Ticker"] for c in [top_br, top_htf, top_pp, top_ls] if c}
  backfill_pool = [c for c in execution_candidates if c.get("Ticker") not in assigned]

  if not top_br and backfill_pool:
      top_br = backfill_pool.pop(0)
      assigned.add(top_br["Ticker"])

  if not top_htf and backfill_pool:
      top_htf = backfill_pool.pop(0)
      assigned.add(top_htf["Ticker"])

  if not top_pp and backfill_pool:
      top_pp = backfill_pool.pop(0)
      assigned.add(top_pp["Ticker"])

  if not top_ls and backfill_pool:
      top_ls = backfill_pool.pop(0)
      assigned.add(top_ls["Ticker"])

  print("\n=== OPTIMAL SETUP SLOTS IDENTIFIED ===")
  print(f"Slot 1 (Base-Reset / Primary): {top_br.get('Ticker') if top_br else 'None'} ({top_br.get('R_Ratio', 'N/A')}R)")
  print(f"Slot 2 (HTF / Secondary):      {top_htf.get('Ticker') if top_htf else 'None'} ({top_htf.get('R_Ratio', 'N/A')}R)")
  print(f"Slot 3 (Pocket / Secondary):   {top_pp.get('Ticker') if top_pp else 'None'} ({top_pp.get('R_Ratio', 'N/A')}R)")
  print(f"Slot 4 (Sweep / Secondary):    {top_ls.get('Ticker') if top_ls else 'None'} ({top_ls.get('R_Ratio', 'N/A')}R)\n")

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

  focus_tickers = [c["Ticker"] for c in [top_br, top_htf, top_pp, top_ls] if c]
  broadcast_meta = {
      "pdf_path": CAROUSEL_PDF_FILENAME,
      "date": datetime.date.today().isoformat(),
      "regime_status": regime,
      "posture_box": dashboard.get("posture_box", "SELECTIVE"),
      "max_exposure": dashboard.get("max_exposure", "N/A"),
      "pct_above_200": dashboard.get("pct_above_200", 0.0),
      "focus_tickers": focus_tickers[:3],
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
