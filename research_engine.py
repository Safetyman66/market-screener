"""Corp Acuity // Research and Execution Engine.

Encapsulates Macro Event Calendars (FOMC, PCE, NFP, Monthly OpEx),
Zacks rank scraping with tenure tracking, and operational Execution Protocols.
"""

import datetime
import random
import re
import time
import requests
import pandas as pd
import yfinance as yf
from concurrent.futures import ThreadPoolExecutor, as_completed
from universe import load_json_cache, save_json_cache

ZACKS_TRACKER_FILE = "zacks_rank_tracker.json"

GLOBAL_HTTP_SESSION = requests.Session()
GLOBAL_HTTP_SESSION.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
})

# 3. MACRO CALENDAR & FORWARD HORIZON ENGINE
# ---------------------------------------------------------
class MacroEventCalendar:

  @staticmethod
  def get_nth_weekday_of_month(year, month, nth, weekday):
    first_day = datetime.date(year, month, 1)
    first_target = first_day + datetime.timedelta(
        days=(weekday - first_day.weekday()) % 7
    )
    return first_target + datetime.timedelta(weeks=nth - 1)

  @classmethod
  def get_third_friday(cls, year, month):
    return cls.get_nth_weekday_of_month(year, month, 3, 4)

  @classmethod
  def get_monthly_seasonality(cls, month):
    seasonality_guide = {
        1: (
            "JANUARY EFFECT & NEW INFLOWS: Institutional capital redeployment."
            " Strong early-month momentum often consolidates into late-month"
            " earnings tests."
        ),
        2: (
            "FEBRUARY CHOP: Historically choppy and range-bound post-Q4"
            " earnings; mid-month volatility spikes are common."
        ),
        3: (
            "MARCH Q1 REBALANCE & QUAD WITCHING: Strong late-month pension"
            " rebalancing. Watch for institutional rotation into quarter-end."
        ),
        4: (
            "APRIL TAX DRAIN & SPRING RALLY: Mid-month liquidity pinch around"
            " tax deadlines, often resolving into a strong late-month earnings"
            " ramp."
        ),
        5: (
            "'SELL IN MAY' DRIFT: Transition to lighter summer liquidity;"
            " systematic trend continuation favored over loose breakouts."
        ),
        6: (
            "JUNE MID-YEAR PINNING & TRIPLE WITCHING: Pre-summer window"
            " dressing followed by index roll-overs and options expiration"
            " pinning."
        ),
        7: (
            "JULY EARNINGS MOMENTUM: Historically one of the strongest seasonal"
            " performers for growth and tech leaders during Q2 reporting."
        ),
        8: (
            "AUGUST SUMMER DOLDRUMS: Thin institutional liquidity; volume"
            " drop-offs make breakout pivots susceptible to midday whipsaws."
        ),
        9: (
            "SEPTEMBER SEASONAL DRAG: Statistically the weakest month"
            " historically. Post-OPEX de-risking and mutual fund fiscal-year-end"
            " loss harvesting."
        ),
        10: (
            "OCTOBER VOLATILITY & INFLECTION: Renowned 'bear killer' month."
            " Elevated pre-earnings and OPEX volatility frequently forms major"
            " market swing bottoms."
        ),
        11: (
            "NOVEMBER YEAR-END CHASE: Benchmark underperformance forces"
            " aggressive institutional buying; post-election clarity"
            " historically accelerates rallies."
        ),
        12: (
            "DECEMBER SANTA CLAUS RALLY: Turn-of-month retirement allocations"
            " and systematic window dressing; breakout continuation"
            " historically favored."
        ),
    }
    return seasonality_guide.get(
        month,
        "NEUTRAL SEASONALITY: Focus purely on price/volume technicals and"
        " regime filters.",
    )

  @classmethod
  def get_major_economic_prints(cls, year, month):
    prints = {}
    nfp_date = cls.get_nth_weekday_of_month(year, month, 1, 4)
    prints[nfp_date] = (
        "JOBS REPORT / NFP (8:30 AM ET): Key payroll & unemployment release."
    )

    cpi_date = cls.get_nth_weekday_of_month(year, month, 2, 2)
    prints[cpi_date] = (
        "CPI INFLATION PRINT (8:30 AM ET): Major pre-market index gap risk."
    )

    ppi_date = cpi_date + datetime.timedelta(days=1)
    prints[ppi_date] = (
        "PPI WHOLESALE INFLATION (8:30 AM ET): Wholesale pipeline read."
    )

    if month == 12:
      next_month_first = datetime.date(year + 1, 1, 1)
    else:
      next_month_first = datetime.date(year, month + 1, 1)
    last_day = next_month_first - datetime.timedelta(days=1)
    days_back = (last_day.weekday() - 4) % 7
    pce_date = last_day - datetime.timedelta(days=days_back)
    prints[pce_date] = (
        "CORE PCE PRICE INDEX (8:30 AM ET): Benchmark Fed inflation print."
    )

    return prints

  @classmethod
  def get_rolling_fomc_schedule(cls, year):
    fomc_matrix = [
        (year, 1, 4, 2),
        (year, 3, 3, 2),
        (year, 5, 1, 2),
        (year, 6, 2, 2),
        (year, 7, 4, 2),
        (year, 9, 3, 2),
        (year, 11, 1, 2),
        (year, 12, 2, 2),
        (year + 1, 1, 4, 2),
    ]
    schedule = []
    for y, m, nth, wd in fomc_matrix:
      schedule.append(cls.get_nth_weekday_of_month(y, m, nth, wd))
    return schedule

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
    opx_label = (
        "Triple/Quad Witching"
        if current_opx.month in [3, 6, 9, 12]
        else "Monthly OPEX"
    )

    for y_c, m_c in months_to_check:
      econ_dict = cls.get_major_economic_prints(y_c, m_c)
      for d_val, title in econ_dict.items():
        forward_events.append((d_val, title, "DATA"))

      opx_d = cls.get_third_friday(y_c, m_c)
      w_name = (
          "Triple/Quad Witching"
          if m_c in [3, 6, 9, 12]
          else "Monthly OPEX"
      )
      forward_events.append(
          (opx_d, f"{w_name}: Synthetic pinning & roll-over volume", "OPEX")
      )

    for f_date in cls.get_rolling_fomc_schedule(year):
      forward_events.append((
          f_date,
          "FOMC RATE DECISION (2:00 PM ET): Policy statement & presser",
          "FOMC",
      ))
      min_date = f_date + datetime.timedelta(days=21)
      forward_events.append((
          min_date,
          "FOMC MINUTES RELEASE (2:00 PM ET): Midday algo volatility",
          "MINUTES",
      ))

    upcoming = sorted(
        [
            (d, desc, evt_type, (d - target_date).days)
            for d, desc, evt_type in forward_events
            if (d - target_date).days >= 0
        ],
        key=lambda x: x[3],
    )

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
      alerts.append(
          "TURN-OF-MONTH (TOM) INFLOWS: Automated retirement allocations"
          " supporting baseline."
      )

    seasonal_context = cls.get_monthly_seasonality(month)

    return alerts, exposure_multiplier, seasonal_context, days_to_opx, opx_label


# ---------------------------------------------------------
# 4. ZACKS RANK RETRIEVAL & LOCAL TENURE TRACKER
# ---------------------------------------------------------
def fetch_raw_zacks_rank(ticker):
  session = requests.Session()
  headers = {
      "User-Agent": (
          "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML,"
          " like Gecko) Chrome/128.0.0.0 Safari/537.36"
      ),
      "Accept": "application/json, text/javascript, */*; q=0.01",
      "Referer": f"https://www.zacks.com/stock/quote/{ticker}",
      "X-Requested-With": "XMLHttpRequest",
  }
  try:
    feed_url = f"https://quote-feed.zacks.com/index?t={ticker}"
    resp = session.get(feed_url, headers=headers, timeout=3)
    if resp.status_code == 200:
      data = resp.json()
      if ticker in data:
        rank = data[ticker].get("zacks_rank")
        if rank:
          return str(rank).strip()

    snap_url = (
        "https://www.zacks.com/includes/classes/zacks_screener_tables.php?scr_id=stock_research&ticker="
        f"{ticker}"
    )
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
    future_to_tk = {
        executor.submit(fetch_raw_zacks_rank, t): t for t in tickers
    }
    for future in as_completed(future_to_tk):
      tk = future_to_tk[future]
      raw_rank = future.result()

      if not raw_rank or raw_rank not in ["1", "2", "3", "4", "5"]:
        results[tk] = "N/A"
        continue

      if tk in tracker:
        prev_rank = tracker[tk].get("rank")
        date_set_str = tracker[tk].get("date_set", today_str)
        try:
          date_set = datetime.date.fromisoformat(date_set_str)
          days = (today - date_set).days
        except Exception:
          days = 1

        if prev_rank == raw_rank:
          tenure_label = f"{days}d" if days > 0 else "New"
        else:
          tracker[tk] = {"rank": raw_rank, "date_set": today_str}
          tenure_label = "New"
      else:
        tracker[tk] = {"rank": raw_rank, "date_set": today_str}
        tenure_label = "1d"

      results[tk] = f"#{raw_rank} ({tenure_label})"

  save_json_cache(ZACKS_TRACKER_FILE, tracker)
  return results


def evaluate_earnings_proximity(ticker):
  try:
    # Route through the stealth global session to bypass Yahoo rate-limiting
    tk = yf.Ticker(ticker, session=GLOBAL_HTTP_SESSION)
    cal = tk.calendar
    today = pd.Timestamp.now().tz_localize(None).date()
    earnings_dates = []

    if cal is not None:
      if isinstance(cal, dict) and "Earnings Date" in cal:
        earnings_dates = cal["Earnings Date"]
      elif hasattr(cal, "empty") and not cal.empty and "Earnings Date" in cal.index:
        earnings_dates = cal.loc["Earnings Date"].tolist()
      elif hasattr(cal, "empty") and not cal.empty and "Earnings Date" in cal.columns:
        earnings_dates = cal["Earnings Date"].tolist()

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
# 4.1 KNOWLEDGE BASE CATALYST & EXECUTION DIRECTIVE ENGINES

def generate_kb_execution_protocol(item, days_to_opx):
  """Synthesizes Knowledge Base research modules into strict, actionable execution rules.

  Incorporates: Binary Events, OpEx Gamma, Zacks Diffusion Decay, and TOM Flows.
  """
  earnings = item.get("Earnings_Risk", "")
  zacks = item.get("Zacks_Rank", "")
  day_of_month = datetime.date.today().day

  # 1. Binary Event Guardrails (Highest Priority)
  if "DANGER" in earnings:
    return "BLOCKED: Binary event blackout (<7d). Hard pass; overnight gap risk unhedged."
  if "CAUTION" in earnings:
    return "DEFENSIVE RUNWAY: Blackout in <14d. Scale out at +1.5R or exit before day 7."

  # 2. Options Expiration (OpEx) Gamma Dynamics
  if days_to_opx <= 2:
    return "OPEX PINNING: Gamma suppression active. Expect range pinning at strike."

  # 3. Zacks Rank Revision Diffusion Tenure
  if any(k in zacks for k in ["#1 (New)", "#1 (1d)", "#1 (2d)", "#1 (3d)"]):
    return "PEAK DIFFUSION: Fresh Rank 1 revision. Full swing leeway to 3.0R+ expansion."
  elif "#2" in zacks and any(d in zacks for d in ["14d", "15d", "16d", "17d", "18d", "19d", "20d"]):
    return "MATURING DRIFT: Late Rank 2 drift. Trail tactical stop tightly along 10 EMA."

  # 4. Turn-of-Month (TOM) Inflow Window
  if day_of_month in [29, 30, 31, 1, 2, 3]:
    return "TOM INFLOW TAILWIND: Automated allocations active. Standard trailing stop."

  # 5. Default Momentum Protocol
  return "STANDARD RUNWAY: Full swing leeway. Void entry if opened >2.5% past pivot."


# 6. MASTER EVALUATION WRAPPER

def determine_structural_catalyst(item, days_to_opx):
    """Synthesizes structural catalyst tags based on technical setup, Zacks tenure, and calendar."""
    catalysts = []
    setup = item.get("Setup", "")
    zacks = item.get("Zacks_Rank", "")
    adr = float(item.get("ADR_Pct", 0.0))
    
    if "#1" in zacks:
        catalysts.append("ZACKS #1 STRONG BUY")
    elif "#2" in zacks:
        catalysts.append("ZACKS #2 BUY")
        
    if "EP" in setup or "Earnings" in setup:
        catalysts.append("EARNINGS CATALYST")
    if "Breakout" in setup or "Base" in setup:
        catalysts.append("VOLATILITY CONTRACTION EXPANSION")
        
    if days_to_opx is not None and days_to_opx <= 5:
        catalysts.append("OPEX PINNING RISK")
        
    if not catalysts:
        catalysts.append("TECHNICAL MOMENTUM")
        
    return " | ".join(catalysts)