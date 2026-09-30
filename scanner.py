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

from reportlab.lib.colors import HexColor
from reportlab.pdfgen import canvas

# ---------------------------------------------------------
# GLOBAL CONSTANTS & SHARED HTTP SESSION
# ---------------------------------------------------------
CHUNK_SIZE = 80
ZACKS_TRACKER_FILE = "zacks_rank_tracker.json"
SECTOR_CACHE_FILE = "sector_cache.json"
CAROUSEL_PDF_FILENAME = "daily_market_intelligence.pdf"

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
# 1. UNIVERSE INGESTION & OFFLINE SECTOR METADATAimport io
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

from reportlab.lib.colors import HexColor
from reportlab.pdfgen import canvas

# ---------------------------------------------------------
# GLOBAL CONSTANTS & SHARED HTTP SESSION
# ---------------------------------------------------------
CHUNK_SIZE = 80
ZACKS_TRACKER_FILE = "zacks_rank_tracker.json"
SECTOR_CACHE_FILE = "sector_cache.json"
CAROUSEL_PDF_FILENAME = "daily_market_intelligence.pdf"

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
        print(f"Warning: Ingestion error ({e}). Falling back to cached lists...")

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

        horizon_count = 0
        for d, desc, evt_type, diff in upcoming:
            if diff > 3 and horizon_count < 3:
                alerts.append(f"📅 IN {diff} DAYS ({d}): {desc}")
                horizon_count += 1

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
# 5. PATTERN GATES (TUNED FOR 100% HARDWARE CAPTURE)
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
            return {'diagnostics': "Insufficient data (<120 sessions)"}

        c0 = daily_df['Close'].iloc[-1]
        volume = daily_df['Volume']
        vol_sma50 = volume.rolling(50).mean().iloc[-1]
        
        daily_dollar_vol = c0 * vol_sma50
        if c0 < 10.0 or daily_dollar_vol < 12_000_000:
            return {'diagnostics': "Liquidity Gate: Price <$10 or ADDV <$12M"}

        stock_1m_perf = ((c0 - daily_df['Close'].iloc[-21]) / daily_df['Close'].iloc[-21]) * 100
        rs_relative = stock_1m_perf - spy_1m_perf
        if rs_relative < -12.0:
            return {'diagnostics': "Relative Strength: Lagging S&P 500 by >12% (1M)"}

        sec_info = sector_map.get(ticker, {'sector': 'Unknown', 'industry': 'Unknown'})
        sec_name = sec_info.get('sector', '')
        ind_name = sec_info.get('industry', '').lower()

        if ticker not in ['TPL', 'EME']:
            if sec_name in EXCLUDED_SECTORS or any(kw in ind_name for kw in BANNED_INDUSTRY_KEYWORDS):
                return {'diagnostics': f"Sector Excluded ({sec_name} / {sec_info.get('industry')})"}

        daily_ema200 = daily_df['Close'].ewm(span=200, adjust=False).mean().iloc[-1]
        pct_above_200 = ((c0 - daily_ema200) / daily_ema200) * 100

        w_df = resample_daily_to_weekly(daily_df)
        if len(w_df) < 24:
            return {'diagnostics': "Insufficient weekly history (<24 weeks)"}

        high_52w = daily_df['High'].tail(252).max() if len(daily_df) >= 252 else daily_df['High'].max()

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
        res_br, r_br = check_base_reset(ticker, daily_df, w_df, c0, daily_ema200, pct_above_200, high_52w)
        results['base_reset'] = res_br
        results['br_reason'] = r_br

        # 2. Momentum Bull Flag
        res_htf, r_htf = check_htf(ticker, daily_df, c0, high_52w)
        results['htf'] = res_htf
        results['htf_reason'] = r_htf

        # 3. Pocket Pivot Squeeze
        res_pp, r_pp = check_pocket_pivot(ticker, daily_df, c0, daily_ema200, high_52w)
        results['pocket_pivot'] = res_pp
        results['pp_reason'] = r_pp

        # 4. Liquidity Sweep
        res_ls, r_ls = check_liquidity_sweep(ticker, daily_df, c0, daily_ema200, high_52w)
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
        'calendar': calendar_alerts[:2]
    }
    return regime_status, dashboard_data

# ---------------------------------------------------------
# 8. LINKEDIN CAROUSEL PDF GENERATOR
# ---------------------------------------------------------
def generate_linkedin_carousel_pdf(output_pdf_path, dashboard, best_cat1, best_cat2, best_cat3, best_cat4):
    page_size = 1080
    c = canvas.Canvas(output_pdf_path, pagesize=(page_size, page_size))
    
    bg_color = HexColor("#0A0A0A")
    card_bg = HexColor("#141414")
    accent_green = HexColor("#00FF66")
    accent_red = HexColor("#FF3344")
    accent_cyan = HexColor("#00E5FF")
    text_white = HexColor("#FFFFFF")
    text_gray = HexColor("#A0A0A0")
    text_dim = HexColor("#666666")

    def draw_background(slide_title="", slide_num=1, total_slides=6):
        c.setFillColor(bg_color)
        c.rect(0, 0, page_size, page_size, fill=1, stroke=0)
        c.setStrokeColor(HexColor("#222222"))
        c.setLineWidth(1)
        c.line(60, page_size - 110, page_size - 60, page_size - 110)
        c.line(60, 90, page_size - 60, 90)

        c.setFont("Helvetica-Bold", 14)
        c.setFillColor(accent_cyan)
        c.drawString(60, page_size - 85, "CORP ACUITY // INSTITUTIONAL MARKET INTELLIGENCE")

        c.setFont("Helvetica", 12)
        c.setFillColor(text_dim)
        c.drawString(page_size - 220, page_size - 85, datetime.date.today().strftime("%b %d, %Y"))

        c.setFont("Helvetica", 11)
        c.drawString(60, 60, "Systematic Swing & Macro Engine")
        c.drawRightString(page_size - 60, 60, f"Slide {slide_num} of {total_slides}")

    # SLIDE 1: Cover & Dashboard
    draw_background("EXECUTIVE INTELLIGENCE", 1, 6)
    c.setFont("Helvetica-Bold", 44)
    c.setFillColor(text_white)
    c.drawString(60, page_size - 200, "DAILY MOMENTUM &")
    c.drawString(60, page_size - 255, "ASYMMETRY INTELLIGENCE")
    
    c.setFont("Helvetica-Bold", 20)
    c.setFillColor(accent_green)
    c.drawString(60, page_size - 315, "1,600+ Stock Institutional Universe Scan")

    c.setFont("Helvetica", 16)
    c.setFillColor(text_gray)
    c.drawString(60, page_size - 365, "A systematic diagnostic screening for high-asymmetry setups:")
    c.drawString(60, page_size - 395, "Base-Resets, High Tight Flags, Pocket Pivots, and Liquidity Sweeps.")

    c.setFillColor(card_bg)
    c.roundRect(60, 140, page_size - 120, 390, 10, fill=1, stroke=0)
    
    c.setFont("Helvetica-Bold", 18)
    c.setFillColor(accent_cyan)
    c.drawString(90, 485, "MACRO REGIME & EXPOSURE COCKPIT")

    regime_str = dashboard.get('regime_status', 'UNKNOWN')
    regime_color = accent_green if "GREEN" in regime_str else (HexColor("#FFAA00") if "AMBER" in regime_str else accent_red)
    
    c.setFont("Helvetica-Bold", 24)
    c.setFillColor(regime_color)
    c.drawString(90, 435, regime_str)

    c.setFont("Helvetica", 16)
    c.setFillColor(text_white)
    c.drawString(90, 390, f"Max Capital Exposure : {dashboard.get('max_exposure', 'N/A')}")
    c.drawString(90, 355, f"Operational Policy  : {dashboard.get('action_plan', 'N/A')}")
    
    c.setFont("Helvetica", 15)
    c.setFillColor(text_gray)
    c.drawString(90, 310, f"SPY Benchmark : ${dashboard.get('spy_c', 0)} ({dashboard.get('spy_status', '')})")
    c.drawString(90, 275, f"QQQ Benchmark : ${dashboard.get('qqq_c', 0)} ({dashboard.get('qqq_status', '')})")
    c.drawString(90, 240, f"US 10Y Yield  : {dashboard.get('tnx', 0)}%   |   WTI Crude: ${dashboard.get('oil', 0)}/bbl")
    c.drawString(90, 205, f"Market Breadth: {dashboard.get('pct_above_200', 0)}% of universe trading > 200 EMA")

    if dashboard.get('warnings'):
        c.setFont("Helvetica-Bold", 14)
        c.setFillColor(accent_red)
        c.drawString(90, 165, f"ALERT: {dashboard['warnings'][0]}")

    c.showPage()

    # SLIDES 2 to 5: Categories
    categories = [
        ("CATEGORY 1: BASE-RESET INFLECTION", best_cat1, "Turnaround base coiling directly off moving average support.", 2),
        ("CATEGORY 2: MOMENTUM BULL FLAG", best_cat2, "Explosive CAN SLIM impulse pole (>45%) with supply dry-up flag.", 3),
        ("CATEGORY 3: POCKET PIVOT SQUEEZE", best_cat3, "Volume-pocket accumulation thrust emerging from a volatility squeeze.", 4),
        ("CATEGORY 4: LIQUIDITY SWEEP (U&R)", best_cat4, "Institutional undercut-and-reclaim of prior structural support.", 5)
    ]

    for title, setup, desc, s_idx in categories:
        draw_background(title, s_idx, 6)

        c.setFont("Helvetica-Bold", 32)
        c.setFillColor(text_white)
        c.drawString(60, page_size - 180, title)

        c.setFont("Helvetica", 16)
        c.setFillColor(text_gray)
        c.drawString(60, page_size - 220, desc)

        if setup is not None:
            c.setFillColor(card_bg)
            c.roundRect(60, 220, page_size - 120, 580, 12, fill=1, stroke=0)

            c.setFont("Helvetica-Bold", 54)
            c.setFillColor(accent_cyan)
            c.drawString(100, 715, setup.get('Ticker', 'UNKNOWN'))

            c.setFont("Helvetica-Bold", 22)
            c.setFillColor(text_white)
            c.drawString(380, 725, f"Last Close: ${setup.get('Close', 0.0):.2f}")

            zacks_rank = setup.get('Zacks_Rank', 'N/A')
            earn_risk = setup.get('Earnings_Risk', 'Unknown')
            c.setFont("Helvetica-Bold", 16)
            c.setFillColor(accent_green)
            c.drawString(100, 665, f"Zacks Rank: {zacks_rank}    |    Earnings Status: {earn_risk}")

            c.setStrokeColor(HexColor("#262626"))
            c.line(100, 635, page_size - 100, 635)

            c.setFont("Helvetica-Bold", 20)
            c.setFillColor(text_white)
            c.drawString(100, 580, "EXECUTION SPECIFICATIONS:")

            params = [
                ("Order Type / Pivot Trigger", f"${setup.get('Pivot_Trigger', 0.0):.2f} (Buy Stop-Limit)", accent_green),
                ("Tactical Stop Loss", f"${setup.get('Stop_Loss', 0.0):.2f}", accent_red),
                ("Capital Risk Margin", f"{setup.get('Risk_%', 0.0):.2f}%", text_white),
                ("Reward-to-Risk Asymmetry", f"{setup.get('R_Ratio', 0.0):.2f} : 1.00", accent_cyan),
                ("Headroom to 52W High", f"+{setup.get('Headroom_%', 0.0):.1f}% Runway", text_white),
                ("Algorithmic Conviction Score", f"{setup.get('Conviction_Score', 0.0):.3f}", accent_green),
                ("Relative Position to 200 EMA", f"+{setup.get('Above_200_%', setup.get('Above_200EMA_%', 0.0)):.1f}%", text_gray)
            ]

            y_pos = 525
            for label, val, color in params:
                c.setFont("Helvetica", 16)
                c.setFillColor(text_gray)
                c.drawString(100, y_pos, label)

                c.setFont("Helvetica-Bold", 18)
                c.setFillColor(color)
                c.drawRightString(page_size - 100, y_pos, str(val))
                y_pos -= 42

            c.setFont("Helvetica-Oblique", 13)
            c.setFillColor(text_dim)
            c.drawString(100, 160, "* Position size must be calculated based strictly on tactical stop risk.")
        else:
            c.setFillColor(card_bg)
            c.roundRect(60, 360, page_size - 120, 360, 12, fill=1, stroke=0)

            c.setFont("Helvetica-Bold", 28)
            c.setFillColor(accent_red)
            c.drawCentredString(page_size / 2, 570, "NO RECOMMENDATIONS AVAILABLE")

            c.setFont("Helvetica", 18)
            c.setFillColor(text_gray)
            c.drawCentredString(page_size / 2, 510, "No setups met quality gates for this category in today's universe scan.")
            c.drawCentredString(page_size / 2, 470, "Capital is preserved in cash until asymmetric conditions confirm.")

        c.showPage()

    # SLIDE 6: Outro & Disclaimer
    draw_background("DISCLAIMER & ACCESS", 6, 6)
    c.setFont("Helvetica-Bold", 40)
    c.setFillColor(text_white)
    c.drawString(60, page_size - 220, "SYSTEMATIC EXECUTION //")
    c.drawString(60, page_size - 275, "FULL WATCHLIST ACCESS")

    c.setFillColor(card_bg)
    c.roundRect(60, 320, page_size - 120, 420, 12, fill=1, stroke=0)

    c.setFont("Helvetica-Bold", 20)
    c.setFillColor(accent_cyan)
    c.drawString(100, 680, "INSTITUTIONAL DATA ACCESS:")

    c.setFont("Helvetica", 17)
    c.setFillColor(text_white)
    c.drawString(100, 630, "This carousel provides only the single highest-conviction setup per category.")
    c.drawString(100, 595, "The full daily watchlists containing all screened candidates, complete technical")
    c.drawString(100, 560, "parameters, sector heatmaps, and diagnostic elimination tables are available.")

    c.setFont("Helvetica-Bold", 19)
    c.setFillColor(accent_green)
    c.drawString(100, 490, "For full access and custom quantitative risk queries:")
    
    c.setFont("Helvetica-Bold", 26)
    c.setFillColor(accent_cyan)
    c.drawString(100, 435, "Andrew McNeil")
    
    c.setFont("Helvetica-Bold", 22)
    c.setFillColor(text_white)
    c.drawString(100, 385, "am@corpacuity.co.uk")

    c.setFont("Helvetica-Bold", 14)
    c.setFillColor(HexColor("#888888"))
    c.drawString(60, 260, "IMPORTANT REGULATORY & EDUCATIONAL DISCLAIMER:")
    
    disclaimer_text = (
        "This presentation is strictly for institutional educational and analytical purposes only and does "
        "not constitute financial, investment, or trading advice. Trading equities, leveraged instruments, "
        "and derivatives involves substantial risk of capital loss. Past algorithmic performance or asymmetry "
        "metrics do not guarantee future market results. All traders must execute their own independent due diligence."
    )
    
    text_obj = c.beginText(60, 230)
    text_obj.setFont("Helvetica", 11)
    text_obj.setFillColor(text_dim)
    text_obj.setLeading(16)
    
    words = disclaimer_text.split()
    line = ""
    for w in words:
        if len(line + " " + w) > 115:
            text_obj.textLine(line)
            line = w
        else:
            line = line + " " + w if line else w
    if line:
        text_obj.textLine(line)
    c.drawText(text_obj)

    c.save()
    print(f"\n[CAROUSEL] Generated clean 6-slide dark-mode PDF: {output_pdf_path}")

# ---------------------------------------------------------
# 9. LINKEDIN REST API PUBLISHER
# ---------------------------------------------------------
def publish_pdf_to_linkedin(pdf_file_path, post_commentary=""):
    access_token = os.environ.get("LINKEDIN_ACCESS_TOKEN")
    author_urn = os.environ.get("LINKEDIN_AUTHOR_URN")

    if not access_token or not author_urn:
        print("[LINKEDIN] Credentials not set in environment. Skipping auto-publish.")
        return False

    headers = {
        "Authorization": f"Bearer {access_token}",
        "X-Restli-Protocol-Version": "2.0.0",
        "LinkedIn-Version": "202401"
    }

    try:
        init_url = "https://api.linkedin.com/rest/documents?action=initializeUpload"
        init_body = {
            "initializeUploadRequest": {
                "owner": author_urn
            }
        }
        r_init = requests.post(init_url, headers=headers, json=init_body, timeout=15)
        if r_init.status_code not in [200, 201]:
            print(f"[LINKEDIN] Init Upload Failed: {r_init.text}")
            return False

        init_data = r_init.json()["value"]
        upload_url = init_data["uploadUrl"]
        document_urn = init_data["document"]

        with open(pdf_file_path, "rb") as f:
            pdf_bytes = f.read()

        r_upload = requests.put(
            upload_url,
            headers={"Authorization": f"Bearer {access_token}"},
            data=pdf_bytes,
            timeout=40
        )
        if r_upload.status_code not in [200, 201]:
            print(f"[LINKEDIN] File Stream Failed: {r_upload.text}")
            return False

        post_url = "https://api.linkedin.com/rest/posts"
        post_payload = {
            "author": author_urn,
            "commentary": post_commentary,
            "visibility": "PUBLIC",
            "distribution": {
                "feedDistribution": "MAIN_FEED",
                "targetEntities": [],
                "thirdPartyDistributionChannels": []
            },
            "content": {
                "media": {
                    "title": f"Market Intelligence // {datetime.date.today().strftime('%b %d, %Y')}",
                    "id": document_urn
                }
            },
            "lifecycleState": "PUBLISHED"
        }

        r_post = requests.post(post_url, headers=headers, json=post_payload, timeout=20)
        if r_post.status_code in [200, 201]:
            print("[LINKEDIN] Successfully published carousel document to feed.")
            return True
        else:
            print(f"[LINKEDIN] Post Publish Failed: {r_post.text}")
            return False

    except Exception as e:
        print(f"[LINKEDIN] Publication Error: {e}")
        return False

# ---------------------------------------------------------
# 10. MASTER RUNNER & QUALITY REPORTING (ALL OUTPUTS RESTORED)
# ---------------------------------------------------------
def run_master_screener():
    universe, sector_map = fetch_institutional_universe_and_sectors()
    total = len(universe)
    print(f"Loaded institutional universe of {total} stocks.")
    print(f"Excluding Healthcare, Staples, Transports, Financials, Utilities, Real Estate, Retail & ADDV <$12M.")
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

    for pool in [base_resets, htfs, pocket_pivots, liquidity_sweeps]:
        for r in pool:
            r['Zacks_Rank'] = zacks_map.get(r['Ticker'], 'N/A')
            r['Earnings_Risk'] = earnings_map.get(r['Ticker'], 'Unknown')

    # CATEGORY 1 QUALITY WEEDER:
    filtered_base_resets = [
        r for r in base_resets
        if (any(r['Zacks_Rank'].startswith(rk) for rk in ['#1', '#2']) or r['Zacks_Rank'] == 'N/A')
        and "🚨 DANGER" not in r['Earnings_Risk']
    ]

    # CATEGORIES 2, 3, 4 QUALITY WEEDER:
    def universal_quality_filter(pool):
        return [
            r for r in pool
            if not any(r['Zacks_Rank'].startswith(rk) for rk in ['#4', '#5'])
            and "🚨 DANGER" not in r['Earnings_Risk']
        ]

    filtered_htfs = universal_quality_filter(htfs)
    filtered_pockets = universal_quality_filter(pocket_pivots)
    filtered_sweeps = universal_quality_filter(liquidity_sweeps)

    # ---------------------------------------------------------
    # PRINT ORIGINAL TERMINAL TABLES & EXPORT CSVS
    # ---------------------------------------------------------
    print("\n" + "="*148)
    print("                    CATEGORY 1: BASE-RESET INFLECTIONS (Above 200 EMA >= 0.5%, Headroom >= 16%, R:R >= 2.5)")
    print("="*148)
    if filtered_base_resets:
        df_br = pd.DataFrame(filtered_base_resets).sort_values(by='Conviction_Score', ascending=False).reset_index(drop=True)
        print(df_br.to_string(index=False))
        df_br.to_csv("watchlist_base_resets.csv", index=False)
    else:
        print("No candidates currently meeting Base-Reset quality gates.")

    print("\n" + "="*148)
    print("                    CATEGORY 2: MOMENTUM BULL FLAGS (CAN SLIM Pole >= 45.0%, Flag <= 18d, Depth <= 14%, Risk >= 1.5%)")
    print("="*148)
    if filtered_htfs:
        df_htf = pd.DataFrame(filtered_htfs).sort_values(by='Pole_Gain_%', ascending=False).reset_index(drop=True)
        print(df_htf.to_string(index=False))
        df_htf.to_csv("watchlist_momentum_flags.csv", index=False)
    else:
        print("No candidates currently meeting Momentum Flag quality gates.")

    print("\n" + "="*148)
    print("                    CATEGORY 3: POCKET PIVOT SQUEEZES (Headroom >= 15%, R:R >= 2.0, Safe Earnings)")
    print("="*148)
    if filtered_pockets:
        df_pp = pd.DataFrame(filtered_pockets).sort_values(by='R_Ratio', ascending=False).reset_index(drop=True)
        print(df_pp.to_string(index=False))
        df_pp.to_csv("watchlist_pocket_pivots.csv", index=False)
    else:
        print("No candidates currently meeting Pocket Pivot criteria.")

    print("\n" + "="*148)
    print("                    CATEGORY 4: LIQUIDITY SWEEPS (Price >= $15, Non-Retail/Midstream, R:R >= 2.5)")
    print("="*148)
    if filtered_sweeps:
        df_ls = pd.DataFrame(filtered_sweeps).sort_values(by='R_Ratio', ascending=False).reset_index(drop=True)
        print(df_ls.to_string(index=False))
        df_ls.to_csv("watchlist_liquidity_sweeps.csv", index=False)
    else:
        print("No candidates currently meeting Liquidity Sweep criteria.")
    print("="*148)

    # ---------------------------------------------------------
    # PRINT ORIGINAL DIAGNOSTIC ELIMINATION FUNNELS
    # ---------------------------------------------------------
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

    # ---------------------------------------------------------
    # PICK TOP 1 PER CATEGORY & GENERATE CAROUSEL PDF
    # ---------------------------------------------------------
    best_cat1 = sorted(filtered_base_resets, key=lambda x: x.get('Conviction_Score', 0), reverse=True)[0] if filtered_base_resets else None
    best_cat2 = sorted(filtered_htfs, key=lambda x: x.get('Conviction_Score', 0), reverse=True)[0] if filtered_htfs else None
    best_cat3 = sorted(filtered_pockets, key=lambda x: x.get('R_Ratio', 0), reverse=True)[0] if filtered_pockets else None
    best_cat4 = sorted(filtered_sweeps, key=lambda x: x.get('R_Ratio', 0), reverse=True)[0] if filtered_sweeps else None

    generate_linkedin_carousel_pdf(
        output_pdf_path=CAROUSEL_PDF_FILENAME,
        dashboard=dashboard,
        best_cat1=best_cat1,
        best_cat2=best_cat2,
        best_cat3=best_cat3,
        best_cat4=best_cat4
    )

    # ---------------------------------------------------------
    # PUBLISH TO LINKEDIN (IF SECRETS ARE PRESENT)
    # ---------------------------------------------------------
    post_commentary = (
        f"Daily Institutional Market Intelligence // {datetime.date.today().strftime('%b %d, %Y')}\n\n"
        f"Macro Regime Status: {dashboard.get('regime_status')}\n"
        f"Max Capital Exposure: {dashboard.get('max_exposure')}\n\n"
        f"Swipe through the daily document for today's highest-conviction momentum & asymmetry setups "
        f"across our 1,600+ stock universe scan.\n\n"
        f"Full data watchlists & risk analytics available by contacting: am@corpacuity.co.uk\n\n"
        f"#Trading #StockMarket #TechnicalAnalysis #Macro #RiskManagement #Semiconductors"
    )
    publish_pdf_to_linkedin(CAROUSEL_PDF_FILENAME, post_commentary)

if __name__ == "__main__":
    run_master_screener()
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
        print(f"Warning: Ingestion error ({e}). Falling back to cached lists...")

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
                return f"DANGER ({days_diff}d)"
            elif 8 <= days_diff <= 14:
                return f"CAUTION ({days_diff}d)"
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
# 5. PATTERN GATES
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
            return {'diagnostics': "Insufficient data (<120 sessions)"}

        c0 = daily_df['Close'].iloc[-1]
        volume = daily_df['Volume']
        vol_sma50 = volume.rolling(50).mean().iloc[-1]
        
        daily_dollar_vol = c0 * vol_sma50
        if c0 < 10.0 or daily_dollar_vol < 12_000_000:
            return {'diagnostics': "Liquidity Gate: Price <$10 or ADDV <$12M"}

        stock_1m_perf = ((c0 - daily_df['Close'].iloc[-21]) / daily_df['Close'].iloc[-21]) * 100
        rs_relative = stock_1m_perf - spy_1m_perf
        if rs_relative < -12.0:
            return {'diagnostics': "Relative Strength: Lagging S&P 500 by >12% (1M)"}

        sec_info = sector_map.get(ticker, {'sector': 'Unknown', 'industry': 'Unknown'})
        sec_name = sec_info.get('sector', '')
        ind_name = sec_info.get('industry', '').lower()

        if ticker not in ['TPL', 'EME']:
            if sec_name in EXCLUDED_SECTORS or any(kw in ind_name for kw in BANNED_INDUSTRY_KEYWORDS):
                return {'diagnostics': f"Sector Excluded ({sec_name} / {sec_info.get('industry')})"}

        daily_ema200 = daily_df['Close'].ewm(span=200, adjust=False).mean().iloc[-1]
        pct_above_200 = ((c0 - daily_ema200) / daily_ema200) * 100

        w_df = resample_daily_to_weekly(daily_df)
        if len(w_df) < 24:
            return {'diagnostics': "Insufficient weekly history (<24 weeks)"}

        high_52w = daily_df['High'].tail(252).max() if len(daily_df) >= 252 else daily_df['High'].max()

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
        res_br, r_br = check_base_reset(ticker, daily_df, w_df, c0, daily_ema200, pct_above_200, high_52w)
        results['base_reset'] = res_br
        results['br_reason'] = r_br

        # 2. Momentum Bull Flag
        res_htf, r_htf = check_htf(ticker, daily_df, c0, high_52w)
        results['htf'] = res_htf
        results['htf_reason'] = r_htf

        # 3. Pocket Pivot Squeeze
        res_pp, r_pp = check_pocket_pivot(ticker, daily_df, c0, daily_ema200, high_52w)
        results['pocket_pivot'] = res_pp
        results['pp_reason'] = r_pp

        # 4. Liquidity Sweep
        res_ls, r_ls = check_liquidity_sweep(ticker, daily_df, c0, daily_ema200, high_52w)
        results['liquidity_sweep'] = res_ls
        results['ls_reason'] = r_ls

        return results

    except Exception as e:
        return {'diagnostics': f"Error: {type(e).__name__}"}

# ---------------------------------------------------------
# 7. MACRO REGIME & EXPOSURE DASHBOARD
# ---------------------------------------------------------
def analyze_market_regime(total_evaluated, total_above_200, category_counts):
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
                macro_warnings.append(f"YIELD SURGE: 10Y Yield @ {round(tnx_c, 2)}% (+{round(tnx_5d_chg, 1)}% 5d)")

    oil_c = 0.0
    if 'CL=F' in close_df.columns:
        oil_s = close_df['CL=F'].dropna()
        if not oil_s.empty:
            oil_c = oil_s.iloc[-1]
            oil_5d_chg = ((oil_c - oil_s.iloc[-5]) / oil_s.iloc[-5]) * 100 if len(oil_s) >= 5 else 0.0
            if oil_c >= 85.0 or oil_5d_chg >= 4.5:
                cross_asset_drag = True
                macro_warnings.append(f"OIL SPIKE: WTI @ ${round(oil_c, 2)} (+{round(oil_5d_chg, 1)}% 5d)")

    pct_above_200 = (total_above_200 / max(total_evaluated, 1)) * 100
    htf_cnt = category_counts.get('htf', 0)
    calendar_alerts, seasonal_mult = MacroEventCalendar.evaluate_calendar()

    if cross_asset_drag:
        seasonal_mult = min(seasonal_mult, 0.65)

    if (not spy_above_200) or (not qqq_above_200) or (not spy_above_50 and not qqq_above_50) or (pct_above_200 < 50.0):
        regime_status = "RED: CONFIRMED MACRO DOWNTREND"
        action_plan = "DEFENSIVE SIZING. Structural trend broken. Tight stops."
        max_exposure = "0% - 15%"
    elif (spy_above_21 and spy_above_50 and qqq_above_21 and qqq_above_50 and qqq_above_200) and (pct_above_200 >= 70.0) and (not cross_asset_drag) and (htf_cnt >= 4):
        regime_status = "GREEN: EXPANSION / MOMENTUM REGIME"
        action_plan = "AGGRESSIVE MARKUP. Full momentum breakouts favored."
        eff_exp = int(100 * seasonal_mult)
        max_exposure = f"{int(80 * seasonal_mult)}% - {eff_exp}%"
    else:
        regime_status = "AMBER: ROTATIONAL ACCUMULATION / HEADWIND"
        action_plan = "DEFENSIVE SELECTIVITY. Focus on support sweeps and low-risk pivots."
        eff_exp = int(45 * seasonal_mult)
        max_exposure = f"{int(20 * seasonal_mult)}% - {eff_exp}%"

    dashboard_data = {
        'regime_status': regime_status,
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
        'calendar': calendar_alerts[:2]
    }
    return regime_status, dashboard_data

# ---------------------------------------------------------
# 8. LINKEDIN CAROUSEL PDF GENERATOR (DARK MODE: WHITE ON BLACK)
# ---------------------------------------------------------
def generate_linkedin_carousel_pdf(output_pdf_path, dashboard, best_cat1, best_cat2, best_cat3, best_cat4):
    """
    Renders an executive, high-contrast, terminal dark-mode 6-slide PDF (1080x1080 px).
    Formatted in clean white-on-black for LinkedIn Document carousels.
    """
    page_size = 1080
    c = canvas.Canvas(output_pdf_path, pagesize=(page_size, page_size))
    
    bg_color = HexColor("#0A0A0A")
    card_bg = HexColor("#141414")
    accent_green = HexColor("#00FF66")
    accent_red = HexColor("#FF3344")
    accent_cyan = HexColor("#00E5FF")
    text_white = HexColor("#FFFFFF")
    text_gray = HexColor("#A0A0A0")
    text_dim = HexColor("#666666")

    def draw_background(slide_title="", slide_num=1, total_slides=6):
        c.setFillColor(bg_color)
        c.rect(0, 0, page_size, page_size, fill=1, stroke=0)
        
        # Subtle terminal top-bar grid
        c.setStrokeColor(HexColor("#222222"))
        c.setLineWidth(1)
        c.line(60, page_size - 110, page_size - 60, page_size - 110)
        c.line(60, 90, page_size - 60, 90)

        # Header branding
        c.setFont("Helvetica-Bold", 14)
        c.setFillColor(accent_cyan)
        c.drawString(60, page_size - 85, "CORP ACUITY // INSTITUTIONAL MARKET INTELLIGENCE")

        c.setFont("Helvetica", 12)
        c.setFillColor(text_dim)
        c.drawString(page_size - 220, page_size - 85, datetime.date.today().strftime("%b %d, %Y"))

        # Footer
        c.setFont("Helvetica", 11)
        c.drawString(60, 60, "Systematic Swing & Macro Engine")
        c.drawRightString(page_size - 60, 60, f"Slide {slide_num} of {total_slides}")

    # =====================================================
    # SLIDE 1: COVER & MACRO DASHBOARD
    # =====================================================
    draw_background("EXECUTIVE INTELLIGENCE", 1, 6)
    
    c.setFont("Helvetica-Bold", 44)
    c.setFillColor(text_white)
    c.drawString(60, page_size - 200, "DAILY MOMENTUM &")
    c.drawString(60, page_size - 255, "ASYMMETRY INTELLIGENCE")
    
    c.setFont("Helvetica-Bold", 20)
    c.setFillColor(accent_green)
    c.drawString(60, page_size - 315, "1,600+ Stock Institutional Universe Scan")

    c.setFont("Helvetica", 16)
    c.setFillColor(text_gray)
    c.drawString(60, page_size - 365, "A systematic diagnostic screening for high-asymmetry setups:")
    c.drawString(60, page_size - 395, "Base-Resets, High Tight Flags, Pocket Pivots, and Liquidity Sweeps.")

    # Macro Regime Card
    c.setFillColor(card_bg)
    c.roundRect(60, 140, page_size - 120, 390, 10, fill=1, stroke=0)
    
    c.setFont("Helvetica-Bold", 18)
    c.setFillColor(accent_cyan)
    c.drawString(90, 485, "MACRO REGIME & EXPOSURE COCKPIT")

    regime_str = dashboard.get('regime_status', 'UNKNOWN')
    regime_color = accent_green if "GREEN" in regime_str else (HexColor("#FFAA00") if "AMBER" in regime_str else accent_red)
    
    c.setFont("Helvetica-Bold", 24)
    c.setFillColor(regime_color)
    c.drawString(90, 435, regime_str)

    c.setFont("Helvetica", 16)
    c.setFillColor(text_white)
    c.drawString(90, 390, f"Max Capital Exposure : {dashboard.get('max_exposure', 'N/A')}")
    c.drawString(90, 355, f"Operational Policy  : {dashboard.get('action_plan', 'N/A')}")
    
    c.setFont("Helvetica", 15)
    c.setFillColor(text_gray)
    c.drawString(90, 310, f"SPY Benchmark : ${dashboard.get('spy_c', 0)} ({dashboard.get('spy_status', '')})")
    c.drawString(90, 275, f"QQQ Benchmark : ${dashboard.get('qqq_c', 0)} ({dashboard.get('qqq_status', '')})")
    c.drawString(90, 240, f"US 10Y Yield  : {dashboard.get('tnx', 0)}%   |   WTI Crude: ${dashboard.get('oil', 0)}/bbl")
    c.drawString(90, 205, f"Market Breadth: {dashboard.get('pct_above_200', 0)}% of universe trading > 200 EMA")

    if dashboard.get('warnings'):
        c.setFont("Helvetica-Bold", 14)
        c.setFillColor(accent_red)
        c.drawString(90, 165, f"ALERT: {dashboard['warnings'][0]}")

    c.showPage()

    # =====================================================
    # SLIDES 2 to 5: CATEGORY RECOMMENDATIONS
    # =====================================================
    categories = [
        ("CATEGORY 1: BASE-RESET INFLECTION", best_cat1, "Turnaround base coiling directly off moving average support.", 2),
        ("CATEGORY 2: MOMENTUM BULL FLAG", best_cat2, "Explosive CAN SLIM impulse pole (>45%) with supply dry-up flag.", 3),
        ("CATEGORY 3: POCKET PIVOT SQUEEZE", best_cat3, "Volume-pocket accumulation thrust emerging from a volatility squeeze.", 4),
        ("CATEGORY 4: LIQUIDITY SWEEP (U&R)", best_cat4, "Institutional undercut-and-reclaim of prior structural support.", 5)
    ]

    for title, setup, desc, s_idx in categories:
        draw_background(title, s_idx, 6)

        c.setFont("Helvetica-Bold", 32)
        c.setFillColor(text_white)
        c.drawString(60, page_size - 180, title)

        c.setFont("Helvetica", 16)
        c.setFillColor(text_gray)
        c.drawString(60, page_size - 220, desc)

        if setup is not None:
            # Active Recommendation Box
            c.setFillColor(card_bg)
            c.roundRect(60, 220, page_size - 120, 580, 12, fill=1, stroke=0)

            # Ticker & Header
            c.setFont("Helvetica-Bold", 54)
            c.setFillColor(accent_cyan)
            c.drawString(100, 715, setup.get('Ticker', 'UNKNOWN'))

            c.setFont("Helvetica-Bold", 22)
            c.setFillColor(text_white)
            c.drawString(380, 725, f"Last Close: ${setup.get('Close', 0.0):.2f}")

            # Sub-badges
            zacks_rank = setup.get('Zacks_Rank', 'N/A')
            earn_risk = setup.get('Earnings_Risk', 'Unknown')
            c.setFont("Helvetica-Bold", 16)
            c.setFillColor(accent_green)
            c.drawString(100, 665, f"Zacks Rank: {zacks_rank}    |    Earnings Status: {earn_risk}")

            # Execution Parameters Table
            c.setStrokeColor(HexColor("#262626"))
            c.line(100, 635, page_size - 100, 635)

            c.setFont("Helvetica-Bold", 20)
            c.setFillColor(text_white)
            c.drawString(100, 580, "EXECUTION SPECIFICATIONS:")

            params = [
                ("Order Type / Pivot Trigger", f"${setup.get('Pivot_Trigger', 0.0):.2f} (Buy Stop-Limit)", accent_green),
                ("Tactical Stop Loss", f"${setup.get('Stop_Loss', 0.0):.2f}", accent_red),
                ("Capital Risk Margin", f"{setup.get('Risk_%', 0.0):.2f}%", text_white),
                ("Reward-to-Risk Asymmetry", f"{setup.get('R_Ratio', 0.0):.2f} : 1.00", accent_cyan),
                ("Headroom to 52W High", f"+{setup.get('Headroom_%', 0.0):.1f}% Runway", text_white),
                ("Algorithmic Conviction Score", f"{setup.get('Conviction_Score', 0.0):.3f}", accent_green),
                ("Relative Position to 200 EMA", f"+{setup.get('Above_200_%', setup.get('Above_200EMA_%', 0.0)):.1f}%", text_gray)
            ]

            y_pos = 525
            for label, val, color in params:
                c.setFont("Helvetica", 16)
                c.setFillColor(text_gray)
                c.drawString(100, y_pos, label)

                c.setFont("Helvetica-Bold", 18)
                c.setFillColor(color)
                c.drawRightString(page_size - 100, y_pos, str(val))
                y_pos -= 42

            c.setFont("Helvetica-Oblique", 13)
            c.setFillColor(text_dim)
            c.drawString(100, 160, "* Position size must be calculated based strictly on tactical stop risk.")
        else:
            # Empty state
            c.setFillColor(card_bg)
            c.roundRect(60, 360, page_size - 120, 360, 12, fill=1, stroke=0)

            c.setFont("Helvetica-Bold", 28)
            c.setFillColor(accent_red)
            c.drawCentredString(page_size / 2, 570, "NO RECOMMENDATIONS AVAILABLE")

            c.setFont("Helvetica", 18)
            c.setFillColor(text_gray)
            c.drawCentredString(page_size / 2, 510, "No setups met quality gates for this category in today's universe scan.")
            c.drawCentredString(page_size / 2, 470, "Capital is preserved in cash until asymmetric conditions confirm.")

        c.showPage()

    # =====================================================
    # SLIDE 6: DISCLAIMER & CONTACT
    # =====================================================
    draw_background("DISCLAIMER & ACCESS", 6, 6)

    c.setFont("Helvetica-Bold", 40)
    c.setFillColor(text_white)
    c.drawString(60, page_size - 220, "SYSTEMATIC EXECUTION //")
    c.drawString(60, page_size - 275, "FULL WATCHLIST ACCESS")

    c.setFillColor(card_bg)
    c.roundRect(60, 320, page_size - 120, 420, 12, fill=1, stroke=0)

    c.setFont("Helvetica-Bold", 20)
    c.setFillColor(accent_cyan)
    c.drawString(100, 680, "INSTITUTIONAL DATA ACCESS:")

    c.setFont("Helvetica", 17)
    c.setFillColor(text_white)
    c.drawString(100, 630, "This carousel provides only the single highest-conviction setup per category.")
    c.drawString(100, 595, "The full daily watchlists containing all screened candidates, complete technical")
    c.drawString(100, 560, "parameters, sector heatmaps, and diagnostic elimination tables are available.")

    c.setFont("Helvetica-Bold", 19)
    c.setFillColor(accent_green)
    c.drawString(100, 490, "For full access and custom quantitative risk queries:")
    
    c.setFont("Helvetica-Bold", 26)
    c.setFillColor(accent_cyan)
    c.drawString(100, 435, "Andrew McNeil")
    
    c.setFont("Helvetica-Bold", 22)
    c.setFillColor(text_white)
    c.drawString(100, 385, "am@corpacuity.co.uk")

    # Disclaimer Footer
    c.setFont("Helvetica-Bold", 14)
    c.setFillColor(HexColor("#888888"))
    c.drawString(60, 260, "IMPORTANT REGULATORY & EDUCATIONAL DISCLAIMER:")
    
    c.setFont("Helvetica", 12)
    c.setFillColor(text_dim)
    disclaimer_text = (
        "This presentation is strictly for institutional educational and analytical purposes only and does "
        "not constitute financial, investment, or trading advice. Trading equities, leveraged instruments, "
        "and derivatives involves substantial risk of capital loss. Past algorithmic performance or asymmetry "
        "metrics do not guarantee future market results. All traders must execute their own independent due diligence."
    )
    
    text_obj = c.beginText(60, 230)
    text_obj.setFont("Helvetica", 11)
    text_obj.setFillColor(text_dim)
    text_obj.setLeading(16)
    
    words = disclaimer_text.split()
    line = ""
    for w in words:
        if len(line + " " + w) > 115:
            text_obj.textLine(line)
            line = w
        else:
            line = line + " " + w if line else w
    if line:
        text_obj.textLine(line)
    c.drawText(text_obj)

    c.save()
    print(f"Generated clean 6-slide dark-mode carousel PDF: {output_pdf_path}")

# ---------------------------------------------------------
# 9. LINKEDIN REST API PUBLISHER (WITH ASYNC PROCESSING DELAY)
# ---------------------------------------------------------
def publish_pdf_to_linkedin(pdf_file_path, post_commentary=""):
    access_token = os.environ.get("LINKEDIN_ACCESS_TOKEN")
    author_urn = os.environ.get("LINKEDIN_AUTHOR_URN")

    if not access_token or not author_urn:
        print("[LINKEDIN] Credentials not set in environment. Skipping auto-publish.")
        return False

    headers = {
        "Authorization": f"Bearer {access_token}",
        "X-Restli-Protocol-Version": "2.0.0",
        "LinkedIn-Version": "202604"
    }

    try:
        # Step 1: Initialize Document Upload
        init_url = "https://api.linkedin.com/rest/documents?action=initializeUpload"
        init_body = {
            "initializeUploadRequest": {
                "owner": author_urn
            }
        }
        r_init = requests.post(init_url, headers=headers, json=init_body, timeout=15)
        if r_init.status_code not in [200, 201]:
            print(f"[LINKEDIN] Init Upload Failed ({r_init.status_code}): {r_init.text}")
            return False

        init_data = r_init.json()["value"]
        upload_url = init_data["uploadUrl"]
        document_urn = init_data["document"]

        # Step 2: Stream PDF Binary
        with open(pdf_file_path, "rb") as f:
            pdf_bytes = f.read()

        put_headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/pdf"
        }
        r_upload = requests.put(upload_url, headers=put_headers, data=pdf_bytes, timeout=45)
        if r_upload.status_code not in [200, 201]:
            print(f"[LINKEDIN] File Stream Failed ({r_upload.status_code}): {r_upload.text}")
            return False

        print("[LINKEDIN] Document uploaded. Waiting 6 seconds for LinkedIn document processing...")
        time.sleep(6.0)

        # Step 3: Create LinkedIn Document Post
        post_url = "https://api.linkedin.com/rest/posts"
        post_payload = {
            "author": author_urn,
            "commentary": post_commentary,
            "visibility": "PUBLIC",
            "distribution": {
                "feedDistribution": "MAIN_FEED",
                "targetEntities": [],
                "thirdPartyDistributionChannels": []
            },
            "content": {
                "media": {
                    "title": f"Market Intelligence // {datetime.date.today().strftime('%b %d, %Y')}",
                    "id": document_urn
                }
            },
            "lifecycleState": "PUBLISHED"
        }

        r_post = requests.post(post_url, headers=headers, json=post_payload, timeout=20)
        if r_post.status_code in [200, 201]:
            print("[LINKEDIN] Successfully published carousel document to feed.")
            return True
        else:
            print(f"[LINKEDIN] Post Publish Failed ({r_post.status_code}): {r_post.text}")
            return False

    except Exception as e:
        print(f"[LINKEDIN] Publication Error: {e}")
        return False

# ---------------------------------------------------------
# 10. MASTER RUNNER & ORCHESTRATOR
# ---------------------------------------------------------
def run_master_screener():
    universe, sector_map = fetch_institutional_universe_and_sectors()
    total = len(universe)
    print(f"Loaded institutional universe of {total} stocks.")
    print(f"Excluding Healthcare, Staples, Transports, Financials, Utilities, Real Estate, Retail & ADDV <$12M.")
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

    for pool in [base_resets, htfs, pocket_pivots, liquidity_sweeps]:
        for r in pool:
            r['Zacks_Rank'] = zacks_map.get(r['Ticker'], 'N/A')
            r['Earnings_Risk'] = earnings_map.get(r['Ticker'], 'Unknown')

    # CATEGORY 1 QUALITY WEEDER:
    filtered_base_resets = [
        r for r in base_resets
        if (any(r['Zacks_Rank'].startswith(rk) for rk in ['#1', '#2']) or r['Zacks_Rank'] == 'N/A')
        and "DANGER" not in r['Earnings_Risk']
    ]

    # CATEGORIES 2, 3, 4 QUALITY WEEDER:
    def universal_quality_filter(pool):
        return [
            r for r in pool
            if not any(r['Zacks_Rank'].startswith(rk) for rk in ['#4', '#5'])
            and "DANGER" not in r['Earnings_Risk']
        ]

    filtered_htfs = universal_quality_filter(htfs)
    filtered_pockets = universal_quality_filter(pocket_pivots)
    filtered_sweeps = universal_quality_filter(liquidity_sweeps)

    # Export Full Tables to CSV
    if filtered_base_resets:
        pd.DataFrame(filtered_base_resets).sort_values(by='Conviction_Score', ascending=False).to_csv("watchlist_base_resets.csv", index=False)
    if filtered_htfs:
        pd.DataFrame(filtered_htfs).sort_values(by='Pole_Gain_%', ascending=False).to_csv("watchlist_momentum_flags.csv", index=False)
    if filtered_pockets:
        pd.DataFrame(filtered_pockets).sort_values(by='R_Ratio', ascending=False).to_csv("watchlist_pocket_pivots.csv", index=False)
    if filtered_sweeps:
        pd.DataFrame(filtered_sweeps).sort_values(by='R_Ratio', ascending=False).to_csv("watchlist_liquidity_sweeps.csv", index=False)

    # ---------------------------------------------------------
    # SELECT SINGLE HIGHEST-CONVICTION SETUP PER CATEGORY
    # ---------------------------------------------------------
    best_cat1 = sorted(filtered_base_resets, key=lambda x: x.get('Conviction_Score', 0), reverse=True)[0] if filtered_base_resets else None
    best_cat2 = sorted(filtered_htfs, key=lambda x: x.get('Conviction_Score', 0), reverse=True)[0] if filtered_htfs else None
    best_cat3 = sorted(filtered_pockets, key=lambda x: x.get('R_Ratio', 0), reverse=True)[0] if filtered_pockets else None
    best_cat4 = sorted(filtered_sweeps, key=lambda x: x.get('R_Ratio', 0), reverse=True)[0] if filtered_sweeps else None

    # Render PDF Carousel
    generate_linkedin_carousel_pdf(
        output_pdf_path=CAROUSEL_PDF_FILENAME,
        dashboard=dashboard,
        best_cat1=best_cat1,
        best_cat2=best_cat2,
        best_cat3=best_cat3,
        best_cat4=best_cat4
    )

    # Publish to LinkedIn if credentials exist
    post_commentary = (
        f"Daily Institutional Market Intelligence // {datetime.date.today().strftime('%b %d, %Y')}\n\n"
        f"Macro Regime Status: {dashboard.get('regime_status')}\n"
        f"Max Capital Exposure: {dashboard.get('max_exposure')}\n\n"
        f"Swipe through the daily document for today's highest-conviction momentum & asymmetry setups "
        f"across our 1,600+ stock universe scan.\n\n"
        f"Full data watchlists & risk analytics available by contacting: am@corpacuity.co.uk\n\n"
        f"#Trading #StockMarket #TechnicalAnalysis #Macro #RiskManagement #Semiconductors"
    )
    publish_pdf_to_linkedin(CAROUSEL_PDF_FILENAME, post_commentary)

if __name__ == "__main__":
    try:
        run_master_screener()
    finally:
        # Close shared network session and cleanly release sockets
        GLOBAL_HTTP_SESSION.close()
        print("\n[COMPLETE] Screener run finished successfully.")
