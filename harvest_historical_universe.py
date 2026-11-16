#!/usr/bin/env python3
"""Historical Universe & 1-Minute Setup Harvester (Legacy Core + Alpha Pool)."""

import os
import time
import datetime
import pandas as pd
import numpy as np

from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame
from alpaca.data.enums import DataFeed

# Reuse your existing screener modules
from universe import (
    fetch_institutional_universe_and_sectors,
    stage_0_prune_by_sector,
    stage_1_prune_by_liquidity,
)
from setups import (
    check_base_reset,
    check_htf,
    check_liquidity_sweep,
    check_pocket_pivot,
    resample_daily_to_weekly,
    evaluate_episodic_pivot,
    evaluate_ema_reclaim,
    evaluate_alpha_flag,
)
import json

ALPACA_CLIENT = StockHistoricalDataClient(
    os.environ["ALPACA_API_KEY"], 
    os.environ["ALPACA_SECRET_KEY"]
)

OUTPUT_DIR = "cache_1m_full_universe"
os.makedirs(OUTPUT_DIR, exist_ok=True)


def get_qualifying_universe():
    """Pulls the ~1,600 Legacy + Alpha universe using your exact Stage 0 & Stage 1 gates."""
    universe, sector_map = fetch_institutional_universe_and_sectors()
    stage0 = stage_0_prune_by_sector(universe, sector_map)
    legacy_survivors, alpha_survivors = stage_1_prune_by_liquidity(stage0, chunk_size=80)

    legacy_set = {s for s in legacy_survivors if "-" not in s and "." not in s}
    alpha_set = {s for s in alpha_survivors if "-" not in s and "." not in s}
    all_tickers = sorted(legacy_set | alpha_set)

    print(f"[*] Qualifying Universe: {len(all_tickers)} unique tickers "
          f"({len(legacy_set)} Legacy, {len(alpha_set)} Alpha)")
    return all_tickers, legacy_set, alpha_set


def download_daily_history(tickers, years=2):
    """Fetches 2+ years of daily OHLCV bars in batches of 100 via Alpaca SIP."""
    start_dt = pd.Timestamp.now(tz="US/Eastern") - pd.DateOffset(years=years, months=6)
    end_dt = pd.Timestamp.now(tz="US/Eastern") - pd.Timedelta(minutes=16)

    daily_map = {}
    for i in range(0, len(tickers), 100):
        chunk = tickers[i:i + 100]
        print(f"[Daily {i+1}-{min(i+100, len(tickers))}/{len(tickers)}] Fetching daily bars...")
        req = StockBarsRequest(
            symbol_or_symbols=chunk,  # <-- Change 'tk' to 'chunk' here
            timeframe=TimeFrame.Day,
            start=start_dt,
            end=end_dt,
            feed=DataFeed.IEX,        # <-- Use DataFeed.IEX here too if Alpaca rejects SIP on daily bars
        )
        bars = ALPACA_CLIENT.get_stock_bars(req)
        if bars and not bars.df.empty:
            df = bars.df.reset_index().rename(columns={
                "timestamp": "Date", "symbol": "Ticker",
                "open": "Open", "high": "High", "low": "Low",
                "close": "Close", "volume": "Volume"
            })
            df["Date"] = pd.to_datetime(df["Date"]).dt.tz_localize(None)
            for tk, grp in df.groupby("Ticker"):
                daily_map[tk] = grp.set_index("Date").sort_index()
        time.sleep(0.4)  # Respect Alpaca 200 req/min rate limit
    return daily_map


def find_historical_setup_events(daily_map, legacy_set, alpha_set, years=2):
    """Walks forward day-by-day over the last 2 years to tag exact Category 1-7 triggers."""
    with open("regime_parameters.json", "r") as f:
        regime_params = json.load(f)["EXPANSION"]  # Or dynamically map SPY/QQQ 50-SMA per date

    cutoff_date = pd.Timestamp.now() - pd.DateOffset(years=years)
    events = []  # List of dicts: {Ticker, Trigger_Date, Category, Pool}

    for tk, full_df in daily_map.items():
        if len(full_df) < 120:
            continue

        full_df["ema200"] = full_df["Close"].ewm(span=200, adjust=False).mean()
        full_df["vol_sma50"] = full_df["Volume"].rolling(50).mean()
        test_dates = full_df.index[full_df.index >= cutoff_date]

        for dt in test_dates:
            hist = full_df.loc[:dt]
            if len(hist) < 120:
                continue

            c0 = float(hist["Close"].iloc[-1])
            ema200 = float(hist["ema200"].iloc[-1])
            dollar_vol = c0 * float(hist["vol_sma50"].iloc[-1])
            adv20 = int(hist["Volume"].tail(20).mean())
            high_52w = float(hist["High"].tail(252).max())
            pct_above_200 = ((c0 - ema200) / ema200) * 100.0

            matched_cat = None
            pool = None

            # Check Alpha High-Torque Pool first (Categories 5 - 7)
            if tk in alpha_set and c0 >= 4.0 and dollar_vol >= 3_000_000:
                if evaluate_episodic_pivot(hist, regime_params).get("valid"):
                    matched_cat, pool = "Episodic Pivot", "ALPHA"
                elif evaluate_ema_reclaim(hist, regime_params).get("valid"):
                    matched_cat, pool = "EMA Reclaim", "ALPHA"
                elif evaluate_alpha_flag(hist, regime_params).get("valid"):
                    matched_cat, pool = "Alpha Flag", "ALPHA"

            # Check Legacy Core Pool (Categories 1 - 4) if not already tagged
            if not matched_cat and tk in legacy_set and c0 >= 10.0 and dollar_vol >= 12_000_000:
                w_df = resample_daily_to_weekly(hist)
                if len(w_df) >= 24:
                    if check_base_reset(tk, hist, w_df, c0, ema200, pct_above_200, high_52w, adv20, regime_params["base_reset"])[0]:
                        matched_cat, pool = "Base-Reset", "LEGACY"
                    elif check_htf(tk, hist, c0, ema200, high_52w, adv20, regime_params["momentum_flag"])[0]:
                        matched_cat, pool = "Momentum Flag", "LEGACY"
                    elif check_pocket_pivot(tk, hist, c0, ema200, high_52w, adv20, regime_params["pocket_pivot"])[0]:
                        matched_cat, pool = "Pocket Pivot", "LEGACY"
                    elif check_liquidity_sweep(tk, hist, c0, ema200, high_52w, adv20, regime_params["liquidity_sweep"])[0]:
                        matched_cat, pool = "Liquidity Sweep", "LEGACY"

            if matched_cat:
                # Signal fires after close on `dt`; execution happens next trading session
                events.append({
                    "Ticker": tk,
                    "Signal_Date": dt.strftime("%Y-%m-%d"),
                    "Category": matched_cat,
                    "Pool": pool,
                })

    events_df = pd.DataFrame(events)
    events_df.to_csv("historical_setup_manifest.csv", index=False)
    print(f"[*] Saved {len(events_df)} historical setup events to 'historical_setup_manifest.csv'")
    return events_df


def harvest_1m_windows(events_df, hold_days=4, batch_size=50):
    """Downloads 1-minute bars in multi-ticker batches grouped by Signal_Date."""
    grouped = list(events_df.groupby("Signal_Date"))
    total_dates = len(grouped)

    for d_idx, (sig_date_str, grp) in enumerate(grouped, 1):
        # Skip tickers already harvested for this signal date
        pending_tickers = [
            tk for tk in grp["Ticker"].unique()
            if not os.path.exists(os.path.join(OUTPUT_DIR, f"{tk}_{sig_date_str}.csv"))
        ]
        if not pending_tickers:
            continue

        sig_dt = pd.to_datetime(sig_date_str)
        start_ts = (sig_dt + pd.Timedelta(days=1)).tz_localize("US/Eastern")
        end_ts = (sig_dt + pd.Timedelta(days=hold_days + 2)).tz_localize("US/Eastern")

        for i in range(0, len(pending_tickers), batch_size):
            chunk = pending_tickers[i:i + batch_size]
            try:
                req = StockBarsRequest(
                    symbol_or_symbols=chunk,
                    timeframe=TimeFrame.Minute,
                    start=start_ts,
                    end=end_ts,
                    feed=DataFeed.IEX,
                )
                bars = ALPACA_CLIENT.get_stock_bars(req)
                if bars and not bars.df.empty:
                    df_all = bars.df.reset_index().rename(columns={
                        "timestamp": "date",
                        "vwap": "average",
                    })
                    for tk, tk_df in df_all.groupby("symbol"):
                        out_file = os.path.join(OUTPUT_DIR, f"{tk}_{sig_date_str}.csv")
                        tk_df.drop(columns=["symbol"]).to_csv(out_file, index=False)
            except Exception as e:
                print(f"[!] Batch failed on {sig_date_str} ({len(chunk)} tickers): {e}", flush=True)

            time.sleep(0.35)

        if d_idx % 25 == 0 or d_idx == total_dates:
            print(f"[1m Harvest] Completed {d_idx}/{total_dates} signal dates...", flush=True)


if __name__ == "__main__":
    tickers, legacy_set, alpha_set = get_qualifying_universe()
    daily_map = download_daily_history(tickers, years=2)
    events_df = find_historical_setup_events(daily_map, legacy_set, alpha_set, years=2)
    harvest_1m_windows(events_df, hold_days=4)