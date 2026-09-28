import io
import re
import os
import json
import time
import requests
from collections import Counter
import datetime
import numpy as np
import pandas as pd
import yfinance as yf
from concurrent.futures import ThreadPoolExecutor, as_completed

# ---------------------------------------------------------
# GLOBAL CONSTANTS & SHARED HTTP SESSION
# ---------------------------------------------------------
CHUNK_SIZE = 80
ZACKS_TRACKER_FILE = "zacks_rank_tracker.json"
SECTOR_CACHE_FILE = "sector_cache.json"

# Persistent browser-mimicking session to bypass Yahoo Crumb & HTTP 429 rate limits
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
            with open(filepath, 'r') as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def save_json_cache(filepath, data):
    try:
        with open(filepath, 'w') as f:
            json.dump(data, f, indent=2)
    except Exception:
        pass

def fetch_institutional_universe_and_sectors():
    tickers = set()
    sector_map = load_json_cache(SECTOR_CACHE_FILE)
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}

    try:
        # S&P 500
        url_sp500 = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
        resp = requests.get(url_sp500, headers=headers, timeout=10)
        df_sp500 = pd.read_html(io.StringIO(resp.text))[0]
        for _, row in df_sp500.iterrows():
            sym = str(row['Symbol']).strip().replace('.', '-')
            tickers.add(sym)
            sec = str(row.get('GICS Sector', 'Unknown'))
            ind = str(row.get('GICS Sub-Industry', 'Unknown'))
            sector_map[sym] = {'sector': sec, 'industry': ind}

        # S&P 400 MidCap
        url_sp400 = "https://en.wikipedia.org/wiki/List_of_S%26P_400_companies"
        resp = requests.get(url_sp400, headers=headers, timeout=10)
        df_sp400 = pd.read_html(io.StringIO(resp.text))[0]
        for _, row in df_sp400.iterrows():
            sym = str(row['Symbol']).strip().replace('.', '-')
            tickers.add(sym)
            sec = str(row.get('GICS Sector', 'Unknown'))
            ind = str(row.get('GICS Sub-Industry', 'Unknown'))
            sector_map[sym] = {'sector': sec, 'industry': ind}

        # Nasdaq-100
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

        # S&P 600 SmallCap
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
        print(f"Warning: Ingestion error ({e}). Falling back to cached lists...")

    # Growth & Liquid Momentum Watchlist Additions
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
        ('AXSM', 'Healthcare', 'Biotechnology'), ('CYTK', 'Healthcare', 'Biotechnology'),
        ('KURA', 'Healthcare', 'Biotechnology'), ('ARVN', 'Healthcare', 'Biotechnology'),
        ('TGTX', 'Healthcare', 'Biotechnology'), ('PCVX', 'Healthcare', 'Biotechnology'),
        ('RARE', 'Healthcare', 'Biotechnology'), ('BBIO', 'Healthcare', 'Biotechnology'),
        ('KRYS', 'Healthcare', 'Biotechnology'), ('INSM', 'Healthcare', 'Biotechnology'),
        ('VICR', 'Technology', 'Semiconductors'), ('MPWR', 'Technology', 'Semiconductors'),
        ('RTX', 'Industrials', 'Aerospace & Defense')
    ]
    for sym, sec, ind in growth_additions:
        tickers.add(sym)
        sector_map[sym] = {'sector': sec, 'industry': ind}

    save_json_cache(SECTOR_CACHE_FILE, sector_map)

    # Sanitize dual-class tickers causing 404s (e.g., CWEN-A, BF-A)
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
# 3. MACRO CALENDAR, RELEASES & FORWARD HORIZON ENGINE
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
        # 1. Non-Farm Payrolls (Jobs Report): 1st Friday
        nfp_date = cls.get_nth_weekday_of_month(year, month, 1, 4)
        prints[nfp_date] = "JOBS REPORT / NFP (8:30 AM ET): Key payroll & unemployment release."

        # 2. CPI Inflation Print: 2nd Wednesday
        cpi_date = cls.get_nth_weekday_of_month(year, month, 2, 2)
        prints[cpi_date] = "CPI INFLATION PRINT (8:30 AM ET): Major pre-market index gap risk."

        # 3. PPI Wholesale Inflation: Thursday following CPI
        ppi_date = cpi_date + datetime.timedelta(days=1)
        prints[ppi_date] = "PPI WHOLESALE INFLATION (8:30 AM ET): Wholesale pipeline read."

        # 4. Core PCE (Fed Preferred Inflation): Last Friday of month
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

        # Immediate threats within 3 days
        for d, desc, evt_type, diff in upcoming:
            if diff == 0:
                alerts.append(f"🚨 TODAY: {desc}")
                if evt_type == "FOMC":
                    exposure_multiplier = min(exposure_multiplier, 0.50)
                elif evt_type == "DATA":
                    exposure_multiplier = min(exposure_multiplier, 0.60)
                elif evt_type == "OPEX":
                    exposure_multiplier = min(exposure_multiplier, 0.70)
            elif 1 <= diff <= 3:
                alerts.append(f"⚠️ {diff} DAY(S) TO {desc} ({d})")
                if evt_type in ["FOMC", "DATA"]:
                    exposure_multiplier = min(exposure_multiplier, 0.80)

        # Forward runway: Next 3 releases
        horizon_count = 0
        for d, desc, evt_type, diff in upcoming:
            if diff > 3 and horizon_count < 3:
                alerts.append(f"📅 IN {diff} DAYS ({d}): {desc}")
                horizon_count += 1

        # Structural Seasonality Models
        if month == 9:
            alerts.append("🍂 SEASONAL DRAG (September Effect): Statistically weakest month. Institutional de-risking active.")
            exposure_multiplier = min(exposure_multiplier, 0.60)
        elif month == 8 and day >= 10:
            alerts.append("☀️ SUMMER DOLDRUMS: Thin liquidity & low volume. Breakouts prone to whipsaw; favor Support Sweeps.")
            exposure_multiplier = min(exposure_multiplier, 0.70)
        elif month == 2 and 14 <= day <= 26:
            alerts.append("❄️ MID-FEBRUARY AIR POCKET: Post-earnings momentum digest. Tighten trailing stops.")
            exposure_multiplier = min(exposure_multiplier, 0.80)
        elif month == 4 and 10 <= day <= 17:
            alerts.append("💸 US TAX FILING DRAIN: Retail cash withdrawals. Expect midday volume drop-offs.")
            exposure_multiplier = min(exposure_multiplier, 0.80)
        elif (month == 11 and day >= 15) or (month == 12 and day >= 15) or (month == 1 and day <= 10):
            alerts.append("🎅 HIGH INFLOW WINDOW (Year-End / Turn-of-Year): Benchmark chasing active. Continuation favored.")

        if day in [29, 30, 31, 1, 2, 3]:
            alerts.append("📈 TURN-OF-MONTH (TOM) INFLOWS: Automated retirement/pension allocations supporting index baselines.")

        if not alerts:
            alerts.append("Clear Macro Runway: No binary macro data prints, FOMC bottlenecks, or OPEX pins within 72h.")

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
                date_set = datetime.date.fromisoformat(date_set_str)

                if prev_rank == raw_rank:
                    days = (today - date_set).days
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
        tk = yf.Ticker(ticker)
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
# 5. PATTERN GATES (PERFECTLY CALIBRATED FOR RMBS & VICR)
# ---------------------------------------------------------
def check_base_reset(ticker, daily_df, w_df, c0, daily_ema200, pct_above_200, headroom_52w):
    try:
        if pct_above_200 > 48.0:
            return None, "Stretched >48% above 200 EMA"
        
        # Headroom Floor at 18.0% (Captures MPWR at 20.1%)
        if not (18.0 <= headroom_52w <= 65.0):
            return None, "Headroom <18% floor or >65%"

        # ATR Contraction Gate relaxed to <= 1.05 (Prevents dropping VICR/RMBS high-beta range)
        atr20 = calculate_atr(daily_df, 20).iloc[-1]
        atr50 = calculate_atr(daily_df, 50).iloc[-1]
        if atr50 <= 0 or (atr20 / atr50) > 1.05:
            return None, "Volatility expanding out of bounds (ATR20/ATR50 > 1.05)"

        w_close = w_df['Close']
        w_vol = w_df['Volume']
        macd, signal, hist = calculate_macd(w_close)
        w_ema10 = w_close.ewm(span=10, adjust=False).mean()
        w_vol_sma10 = w_vol.rolling(window=10).mean()

        h0, h1, h2, h3 = hist.iloc[-1], hist.iloc[-2], hist.iloc[-3], hist.iloc[-4]
        c2 = w_close.iloc[-3]
        v0 = w_vol.iloc[-1]
        v_avg = w_vol_sma10.iloc[-1]

        if not (h0 > h1 and h1 > h2):
            return None, "Histogram not expanding monotonically"

        was_trough = (h2 <= h3) or ((h0 - h1) > (h1 - h2))
        if not was_trough:
            return None, "No trough hook or acceleration spread"

        hist_expansion = h0 - h2
        conviction_magnitude = (hist_expansion / c0) * 100
        if conviction_magnitude < 0.30:
            return None, "Conviction magnitude <0.30% of price"

        if not (c0 > (w_ema10.iloc[-1] * 0.98) and c0 > c2):
            return None, "Price significantly below 10w EMA or <= close 2w ago"

        # Volume Floor relaxed to 0.70x (Permits RMBS supply dry-up bases)
        if v_avg <= 0 or v0 < (v_avg * 0.70):
            return None, "Weekly volume <70% of 10w avg"

        vol_ratio = v0 / v_avg
        score = conviction_magnitude * vol_ratio

        daily_pivot = daily_df['High'].tail(3).max()
        tactical_stop = daily_df['Low'].tail(3).min()
        risk_pct = ((daily_pivot - tactical_stop) / daily_pivot) * 100

        # Max risk allowance bounded to 12.0% for high-conviction bases
        if risk_pct > 12.0 or risk_pct <= 0:
            return None, "Stop width invalid or >12.0%"

        # Reward-to-Risk Gate set to >= 2.0 (Accommodates VICR at 2.59)
        reward_risk = headroom_52w / risk_pct
        if reward_risk < 2.0:
            return None, f"Low Asymmetry (R:R {round(reward_risk, 1)} < 2.0)"

        return {
            'Ticker': ticker,
            'Close': round(c0, 2),
            'Headroom_%': round(headroom_52w, 1),
            'Above_200_%': round(pct_above_200, 1),
            'Hist_Now': round(h0, 3),
            'Vol_Ratio': f"{round(vol_ratio, 2)}x",
            'Conviction_Score': round(score, 3),
            'Pivot_Trigger': round(daily_pivot, 2),
            'Stop_Loss': round(tactical_stop, 2),
            'Risk_%': round(risk_pct, 2),
            'R_Ratio': round(reward_risk, 2)
        }, "PASSED"
    except Exception as e:
        return None, f"Error: {type(e).__name__}"

def check_htf(ticker, df, c0, headroom_52w):
    try:
        close = df['Close']
        high = df['High']
        low = df['Low']
        volume = df['Volume']
        vol_sma50 = volume.rolling(window=50).mean().iloc[-1]

        recent_25_highs = high.iloc[-25:]
        peak_idx = recent_25_highs.idxmax()
        bars_since_peak = len(df) - 1 - df.index.get_loc(peak_idx)

        if not (3 <= bars_since_peak <= 16):
            return None, "Flag duration >16 days (Consolidation drift)"

        peak_price = high.loc[peak_idx]
        peak_pos = df.index.get_loc(peak_idx)
        pole_start_pos = max(0, peak_pos - 40)
        pole_end_pos = max(0, peak_pos - 8)

        if pole_end_pos <= pole_start_pos:
            return None, "Insufficient history for pole"

        pole_trough = low.iloc[pole_start_pos:pole_end_pos].min()
        pole_gain_pct = ((peak_price - pole_trough) / pole_trough) * 100
        if pole_gain_pct < 32.0:
            return None, "Pole gain <32% in 4-8 week window"

        flag_low = low.iloc[-bars_since_peak:].min()
        flag_depth_pct = ((peak_price - flag_low) / peak_price) * 100
        
        if flag_depth_pct > 15.0:
            return None, "Flag pullback too loose (>15%)"

        last_10_high = high.tail(10).max()
        last_10_low = low.tail(10).min()
        flag_tightness_pct = ((last_10_high - last_10_low) / last_10_high) * 100
        if flag_tightness_pct > 13.0:
            return None, "Loose 10-day range (>13%)"

        if ((peak_price - c0) / peak_price) * 100 > 11.0:
            return None, "Price sagging (>11% below peak)"

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

        if risk_pct <= 0:
            return None, "Invalid stop geometry"

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
            'Pivot_Trigger': pivot_trigger,
            'Stop_Loss': tactical_stop,
            'Risk_%': risk_pct,
            'R_Ratio': round(reward_risk, 2)
        }, "PASSED"
    except Exception as e:
        return None, f"Error: {type(e).__name__}"

def check_pocket_pivot(ticker, df, c0, daily_ema200, headroom_52w):
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
        if ext_200 > 40.0:
            return None, "Stretched >40% above 200 EMA"

        if not (2.5 <= headroom_52w <= 32.0):
            return None, "Headroom out of bounds (<2.5% or >32%)"

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

        if risk_pct > 6.5 or risk_pct <= 0:
            return None, "Tactical risk invalid or >6.5%"

        reward_risk = headroom_52w / risk_pct
        if reward_risk < 2.0:
            return None, f"Low Asymmetry (R:R {round(reward_risk, 1)} < 2.0)"

        return {
            'Ticker': ticker,
            'Close': round(c0, 2),
            'Headroom_%': round(headroom_52w, 1),
            'Ext_10EMA_%': round(ext_10, 1),
            'Above_200EMA_%': round(ext_200, 1),
            'Vol_Pocket_Ratio': f"{vol_pocket_ratio}x",
            'Pivot_Trigger': pivot_trigger,
            'Stop_Loss': tactical_stop,
            'Risk_%': risk_pct,
            'R_Ratio': round(reward_risk, 2)
        }, "PASSED"
    except Exception as e:
        return None, f"Error: {type(e).__name__}"

def check_liquidity_sweep(ticker, df, c0, daily_ema200, headroom_52w):
    try:
        high = df['High']
        low = df['Low']
        volume = df['Volume']
        current_low = low.iloc[-1]
        current_high = high.iloc[-1]
        vol_sma50 = volume.rolling(50).mean().iloc[-1]

        # Minimum Headroom Floor at 14.0% (Captures RTX at 16.3%)
        if not (14.0 <= headroom_52w <= 55.0):
            return None, "Headroom <14% floor or >55%"

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

        if risk_pct > 6.5 or risk_pct <= 0:
            return None, "Tactical risk invalid or >6.5%"

        reward_risk = headroom_52w / risk_pct
        if reward_risk < 2.0:
            return None, f"Low Asymmetry (R:R {round(reward_risk, 1)} < 2.0)"

        return {
            'Ticker': ticker,
            'Close': round(c0, 2),
            'Shelf_Level': round(support_shelf, 2),
            'Flush_Low': round(recent_flush_low, 2),
            'Sweep_Depth_%': round(undercut_pct, 2),
            'Headroom_%': round(headroom_52w, 1),
            'Vol_Ratio': f"{round(vol_ratio, 2)}x",
            'Pivot_Trigger': pivot_trigger,
            'Stop_Loss': tactical_stop,
            'Risk_%': risk_pct,
            'R_Ratio': round(reward_risk, 2)
        }, "PASSED"
    except Exception as e:
        return None, f"Error: {type(e).__name__}"

# ---------------------------------------------------------
# 6. MASTER EVALUATION WRAPPER
# ---------------------------------------------------------
EXCLUDED_SECTORS = {'Real Estate', 'Utilities'}
EXCLUDED_INDUSTRIES = {'Banks - Regional', 'Regional - Banks', 'Savings & Cooperative Banks'}

def evaluate_all_setups(ticker, daily_df, spy_3m_perf, sector_map):
    try:
        daily_df = daily_df.dropna()
        if len(daily_df) < 220:
            return {'diagnostics': "Insufficient data (<220 sessions)"}

        c0 = daily_df['Close'].iloc[-1]
        volume = daily_df['Volume']
        vol_sma50 = volume.rolling(50).mean().iloc[-1]
        
        daily_dollar_vol = c0 * vol_sma50
        if c0 < 10.0 or daily_dollar_vol < 18_000_000:
            return {'diagnostics': "Liquidity Gate: Price <$10 or ADDV <$18M"}

        # Relative Strength Gate (Allows -5.0% lag vs. SPY for defense/industrial hedges)
        stock_3m_perf = ((c0 - daily_df['Close'].iloc[-63]) / daily_df['Close'].iloc[-63]) * 100
        rs_relative = stock_3m_perf - spy_3m_perf
        if rs_relative < -5.0:
            return {'diagnostics': "Relative Strength: Lagging S&P 500 by >5% (3M)"}

        # Offline Sector Exclusions
        sec_info = sector_map.get(ticker, {'sector': 'Unknown', 'industry': 'Unknown'})
        if sec_info['sector'] in EXCLUDED_SECTORS or sec_info['industry'] in EXCLUDED_INDUSTRIES:
            return {'diagnostics': f"Sector Excluded ({sec_info['sector']} / {sec_info['industry']})"}

        daily_ema200 = daily_df['Close'].ewm(span=200, adjust=False).mean().iloc[-1]
        pct_above_200 = ((c0 - daily_ema200) / daily_ema200) * 100

        if c0 < (0.95 * daily_ema200):
            return {'diagnostics': "Universal Macro: Below Daily 200 EMA"}

        w_df = resample_daily_to_weekly(daily_df)
        if len(w_df) < 40:
            return {'diagnostics': "Insufficient weekly history (<40 weeks)"}

        high_52w = daily_df['High'].tail(252).max() if len(daily_df) >= 252 else daily_df['High'].max()
        headroom_52w = ((high_52w - c0) / high_52w) * 100

        results = {
            'ticker': ticker,
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

        # 1. Base-Reset Inflection
        res_br, r_br = check_base_reset(ticker, daily_df, w_df, c0, daily_ema200, pct_above_200, headroom_52w)
        results['base_reset'] = res_br
        results['br_reason'] = r_br

        # 2. Momentum Bull Flag
        res_htf, r_htf = check_htf(ticker, daily_df, c0, headroom_52w)
        results['htf'] = res_htf
        results['htf_reason'] = r_htf

        # 3. Pocket Pivot Squeeze
        res_pp, r_pp = check_pocket_pivot(ticker, daily_df, c0, daily_ema200, headroom_52w)
        results['pocket_pivot'] = res_pp
        results['pp_reason'] = r_pp

        # 4. Liquidity Sweep
        res_ls, r_ls = check_liquidity_sweep(ticker, daily_df, c0, daily_ema200, headroom_52w)
        results['liquidity_sweep'] = res_ls
        results['ls_reason'] = r_ls

        return results

    except Exception as e:
        return {'diagnostics': f"Error: {type(e).__name__}"}

# ---------------------------------------------------------
# 7. MACRO REGIME & EXPOSURE DASHBOARD
# ---------------------------------------------------------
def analyze_market_regime(total_evaluated, total_above_200, category_counts):
    print("\n" + "="*112)
    print("                      MACRO MARKET REGIME & CAPITAL EXPOSURE DASHBOARD")
    print("="*112)

    benchmarks = yf.download(
        ['SPY', 'QQQ'],
        period='1y',
        interval='1d',
        progress=False,
        session=GLOBAL_HTTP_SESSION
    )
    spy_close = benchmarks['Close']['SPY'].dropna()
    qqq_close = benchmarks['Close']['QQQ'].dropna()

    spy_c = spy_close.iloc[-1]
    spy_ema21 = spy_close.ewm(span=21, adjust=False).mean().iloc[-1]
    spy_sma50 = spy_close.rolling(50).mean().iloc[-1]
    spy_ema200 = spy_close.ewm(span=200, adjust=False).mean().iloc[-1]

    qqq_c = qqq_close.iloc[-1]
    qqq_sma50 = qqq_close.rolling(50).mean().iloc[-1]

    spy_above_21 = bool(spy_c > spy_ema21)
    spy_above_50 = bool(spy_c > spy_sma50)
    spy_above_200 = bool(spy_c > spy_ema200)
    qqq_above_50 = bool(qqq_c > qqq_sma50)

    pct_above_200 = (total_above_200 / max(total_evaluated, 1)) * 100
    pct_below_200 = 100.0 - pct_above_200

    htf_cnt = category_counts.get('htf', 0)
    sweep_cnt = category_counts.get('sweep', 0)

    calendar_alerts, seasonal_mult = MacroEventCalendar.evaluate_calendar()

    if (not spy_above_200) or (not spy_above_50 and not qqq_above_50) or (pct_above_200 < 50.0):
        regime_status = "RED: CONFIRMED MACRO DOWNTREND"
        action_plan = "AVOID ALL TRADING (100% Cash). Sidelined to preserve capital."
        allowed_setups = "NONE. Correlation approaches 1.0; breakdowns cascade."
        max_exposure = "0% (Sidelined)"
        posture_box = "■ DOWNTREND DEFENSE: DO NOT DEPLOY CAPITAL ■"
    elif spy_above_21 and spy_above_50 and (pct_above_200 >= 70.0) and (htf_cnt >= 5):
        regime_status = "GREEN: EXPANSION / MOMENTUM REGIME"
        action_plan = "AGGRESSIVE MARKUP. Trade traditional breakouts and continuation flags."
        allowed_setups = "Momentum Bull Flags, High Tight Flags, Pocket Pivots."
        eff_exp = int(100 * seasonal_mult)
        max_exposure = f"{int(80 * seasonal_mult)}% - {eff_exp}%"
        posture_box = "▲ EXPANSION BULL: BUY CONTINUATION & BREAKOUTS ▲"
    else:
        regime_status = "AMBER: ROTATIONAL ACCUMULATION / RANGE DIGEST"
        action_plan = "SELECTIVE MEAN-REVERSION. Strictly avoid chasing 52w-high breakouts."
        allowed_setups = "Liquidity Sweeps (U&R) and Base Pocket Pivots (Risk <= 2.5%)."
        eff_exp = int(50 * seasonal_mult)
        max_exposure = f"{int(30 * seasonal_mult)}% - {eff_exp}% (Tight partials at 2R to 3R)"
        posture_box = "◆ ROTATIONAL DIGEST: BUY SUPPORT SWEEPS ONLY ◆"

    print(f"  Regime Status       : {regime_status}")
    print(f"  Macro Posture       : {posture_box}")
    print(f"  Max Account Exposure: {max_exposure} (Seasonal factor: {seasonal_mult}x)")
    print(f"  Recommended Tactics : {action_plan}")
    print(f"  Eligible Setups     : {allowed_setups}")
    print("-" * 112)
    print(f"  INDEX BENCHMARKS    : SPY = ${round(spy_c, 2)} (Above 21 EMA: {spy_above_21} | Above 50 SMA: {spy_above_50})")
    print(f"                        QQQ = ${round(qqq_c, 2)} (Above 50 SMA: {qqq_above_50})")
    print(f"  UNIVERSE BREADTH    : {round(pct_above_200, 1)}% of stocks > 200 EMA | {round(pct_below_200, 1)}% in Structural Downtrends")
    print(f"  CANDIDATE PROFILE   : Breakout/Momentum ({htf_cnt}) vs. False-Breakdown Sweeps ({sweep_cnt})")
    print("-" * 112)
    for alert in calendar_alerts:
        print(f"  CALENDAR & RELEASES : {alert}")
    print("=" * 112 + "\n")

    return regime_status

# ---------------------------------------------------------
# 8. MASTER RUNNER & QUALITY REPORTING
# ---------------------------------------------------------
def run_master_screener():
    universe, sector_map = fetch_institutional_universe_and_sectors()
    total = len(universe)
    print(f"Loaded institutional universe of {total} stocks.")
    print(f"Excluding Real Estate, Utilities, Regional Banks & ADDV <$18M.")
    print(f"Scanning across 4 Setup Categories in batches of {CHUNK_SIZE}...\n")

    # SPY 3-month performance benchmark
    spy_data = yf.download(
        'SPY',
        period='6mo',
        interval='1d',
        progress=False,
        session=GLOBAL_HTTP_SESSION
    )['Close']
    spy_3m_perf = ((spy_data.iloc[-1] - spy_data.iloc[-63]) / spy_data.iloc[-63]) * 100
    if isinstance(spy_3m_perf, pd.Series):
        spy_3m_perf = spy_3m_perf.iloc[0]

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
                        future_to_sym[executor.submit(evaluate_all_setups, sym, batch_data[sym], spy_3m_perf, sector_map)] = sym
                else:
                    future_to_sym[executor.submit(evaluate_all_setups, sym, batch_data, spy_3m_perf, sector_map)] = sym

            for future in as_completed(future_to_sym):
                total_evaluated += 1
                res = future.result()
                diag_status = res.get('diagnostics', 'Unknown')
                macro_diag[diag_status] += 1

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
        time.sleep(3.0)

    category_counts = {
        'reset': len(base_resets),
        'htf': len(htfs),
        'pivot': len(pocket_pivots),
        'sweep': len(liquidity_sweeps)
    }
    total_above_200 = total_evaluated - macro_diag["Universal Macro: Below Daily 200 EMA"]
    regime = analyze_market_regime(total_evaluated, total_above_200, category_counts)

    if "RED" in regime:
        print("!"*112)
        print(" [CIRCUIT BREAKER ACTIVE] Market conditions are unfavorable for swing trading.")
        print(" Candidate outputs are locked to prevent capital allocation into a macro distribution tape.")
        print("!"*112 + "\n")
        return

    # Profile Zacks Ranks and Earnings Dates
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
        r['Zacks_Rank'] = zacks_map.get(r['Ticker'], 'N/A')
        r['Earnings_Risk'] = earnings_map.get(r['Ticker'], 'Unknown')
    for r in htfs:
        r['Zacks_Rank'] = zacks_map.get(r['Ticker'], 'N/A')
        r['Earnings_Risk'] = earnings_map.get(r['Ticker'], 'Unknown')
    for r in pocket_pivots:
        r['Zacks_Rank'] = zacks_map.get(r['Ticker'], 'N/A')
        r['Earnings_Risk'] = earnings_map.get(r['Ticker'], 'Unknown')
    for r in liquidity_sweeps:
        r['Zacks_Rank'] = zacks_map.get(r['Ticker'], 'N/A')
        r['Earnings_Risk'] = earnings_map.get(r['Ticker'], 'Unknown')

    # Exclude Zacks #4/#5 (Sell/Strong Sell)
    filtered_base_resets = [r for r in base_resets if any(r['Zacks_Rank'].startswith(rk) for rk in ['#1', '#2', '#3'])]
    filtered_htfs = [r for r in htfs if any(r['Zacks_Rank'].startswith(rk) for rk in ['#1', '#2', '#3'])]

    # Candidate Output Tables & CSV Exports
    print("\n" + "="*148)
    print("                    CATEGORY 1: BASE-RESET INFLECTIONS (R:R >= 2.0, Headroom >= 18%)")
    print("="*148)
    if filtered_base_resets:
        df_br = pd.DataFrame(filtered_base_resets).sort_values(by='Conviction_Score', ascending=False).reset_index(drop=True)
        print(df_br.to_string(index=False))
        df_br.to_csv("watchlist_base_resets.csv", index=False)
    else:
        print("No candidates currently meeting Base-Reset quality gates.")

    print("\n" + "="*148)
    print("                    CATEGORY 2: MOMENTUM BULL FLAGS (Flag <= 16d, Depth <= 15%, R:R >= 2.0)")
    print("="*148)
    if filtered_htfs:
        df_htf = pd.DataFrame(filtered_htfs).sort_values(by='Pole_Gain_%', ascending=False).reset_index(drop=True)
        print(df_htf.to_string(index=False))
        df_htf.to_csv("watchlist_momentum_flags.csv", index=False)
    else:
        print("No candidates currently meeting Momentum Flag quality gates.")

    print("\n" + "="*148)
    print("                    CATEGORY 3: POCKET PIVOT SQUEEZES (R:R >= 2.0, Launch Off 10/21 EMA)")
    print("="*148)
    if pocket_pivots:
        df_pp = pd.DataFrame(pocket_pivots).sort_values(by='R_Ratio', ascending=False).reset_index(drop=True)
        print(df_pp.to_string(index=False))
        df_pp.to_csv("watchlist_pocket_pivots.csv", index=False)
    else:
        print("No candidates currently meeting Pocket Pivot criteria.")

    print("\n" + "="*148)
    print("                    CATEGORY 4: LIQUIDITY SWEEPS (Non-Bank/REIT, Headroom >= 14%, R:R >= 2.0)")
    print("="*148)
    if liquidity_sweeps:
        df_ls = pd.DataFrame(liquidity_sweeps).sort_values(by='R_Ratio', ascending=False).reset_index(drop=True)
        print(df_ls.to_string(index=False))
        df_ls.to_csv("watchlist_liquidity_sweeps.csv", index=False)
    else:
        print("No candidates currently meeting Liquidity Sweep criteria.")
    print("="*148)

    # Diagnostic Elimination Funnels
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
    print_sub_funnel("CATEGORY 3 (POCKET PIVOT SQUEEZE)", pp_diag, len(pocket_pivots))
    print_sub_funnel("CATEGORY 4 (LIQUIDITY SWEEP)", ls_diag, len(liquidity_sweeps))
    print("="*95 + "\n")

if __name__ == "__main__":
    run_master_screener()
