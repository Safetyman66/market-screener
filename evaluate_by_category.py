#!/usr/bin/env python3
"""Category & Pool Attribution Backtester (Legacy Core 1-4 vs. Alpha High-Torque 5-7)."""

import os
import numpy as np
import pandas as pd
import yfinance as yf

MANIFEST_FILE = "historical_setup_manifest.csv"
CACHE_DIR = "cache_1m_full_universe"
OUTPUT_RESULTS = "category_attribution_results.csv"


def load_spy_trend():
    """Builds daily SPY > 5-EMA regime map."""
    spy = yf.download("SPY", period="3y", interval="1d", progress=False)
    if isinstance(spy.columns, pd.MultiIndex):
        spy.columns = spy.columns.get_level_values(0)
    spy["ema_5"] = spy["Close"].ewm(span=5, adjust=False).mean()
    return {str(idx.date()): bool(c > e) for idx, c, e in zip(spy.index, spy["Close"], spy["ema_5"])}


def compute_morning_box(df):
    """Computes 70% Value Area High (VAH) and Value Area Low (VAL) from 09:30-10:15 bars."""
    if df.empty:
        return np.nan, np.nan
    min_p, max_p = float(df["low"].min()), float(df["high"].max())
    if min_p == max_p:
        return min_p, min_p

    bins = np.linspace(min_p, max_p, 40)
    safe_vol = np.where(df["volume"] <= 0, 1.0, df["volume"])
    vol_profile, _ = np.histogram(df["close"], bins=bins, weights=safe_vol)

    poc_idx = int(np.argmax(vol_profile))
    total_vol = float(np.sum(vol_profile))
    target_vol = total_vol * 0.70
    current_vol = float(vol_profile[poc_idx])
    lower_idx, upper_idx = poc_idx, poc_idx

    for _ in range(100):
        if current_vol >= target_vol or (lower_idx == 0 and upper_idx == len(vol_profile) - 1):
            break
        lower_vol = vol_profile[lower_idx - 1] if lower_idx > 0 else 0
        upper_vol = vol_profile[upper_idx + 1] if upper_idx < len(vol_profile) - 1 else 0
        if lower_vol == 0 and upper_vol == 0:
            break
        if lower_idx == 0 or (upper_idx < len(vol_profile) - 1 and upper_vol >= lower_vol):
            upper_idx += 1
            current_vol += upper_vol
        else:
            lower_idx -= 1
            current_vol += lower_vol

    vah = bins[upper_idx + 1] if (upper_idx + 1) < len(bins) else bins[-1]
    val = bins[lower_idx]
    return float(vah), float(val)


def run_category_backtest():
    manifest = pd.read_csv(MANIFEST_FILE)
    spy_trend = load_spy_trend()
    triggers = []

    for _, row in manifest.iterrows():
        tk = row["Ticker"]
        sig_date = row["Signal_Date"]
        filepath = os.path.join(CACHE_DIR, f"{tk}_{sig_date}.csv")
        if not os.path.exists(filepath):
            continue

        master_df = pd.read_csv(filepath)
        if master_df.empty:
            continue

        master_df.columns = [c.lower() for c in master_df.columns]
        master_df["date"] = pd.to_datetime(master_df["date"], utc=True).dt.tz_convert("US/Eastern")
        master_df = master_df.sort_values("date").reset_index(drop=True)
        master_df["trading_day"] = master_df["date"].dt.date

        # Execute on the immediate trading day following the nightly scan signal
        exec_day = master_df["trading_day"].min()
        exec_date_str = str(exec_day)
        if not spy_trend.get(exec_date_str, True):
            continue

        day_df = master_df[master_df["trading_day"] == exec_day].copy()
        day_df = day_df.set_index("date").between_time("09:30", "16:00").reset_index()
        if len(day_df) < 30:
            continue

        # Fallback if 'average' (VWAP) is missing or zero on thin IEX bars
        typical_price = (day_df["high"] + day_df["low"] + day_df["close"]) / 3.0
        bar_vwap = np.where(day_df.get("average", 0) > 0, day_df["average"], typical_price)
        day_df["vwap"] = (bar_vwap * day_df["volume"]).cumsum() / day_df["volume"].cumsum().replace(0, 1)

        morning_df = day_df[day_df["date"].dt.time < pd.to_datetime("10:15").time()]
        if morning_df.empty:
            continue

        vah, val = compute_morning_box(morning_df)
        orh_df = day_df[day_df["date"].dt.time < pd.to_datetime("09:45").time()]
        orh = float(orh_df["high"].max()) if not orh_df.empty else vah
        vol_hurdle = float(morning_df["volume"].mean()) * 0.60

        trade_df = day_df[day_df["date"].dt.time >= pd.to_datetime("10:15").time()]
        bars_above_pivot = 0

        for _, bar in trade_df.iterrows():
            c_price = float(bar["close"])
            is_green = c_price > float(bar["open"])
            vol_passed = float(bar["volume"]) > vol_hurdle

            if c_price >= vah and c_price >= orh:
                bars_above_pivot += 1
            else:
                bars_above_pivot = 0

            if (
                c_price >= vah
                and c_price >= orh
                and c_price > float(bar["vwap"])
                and is_green
                and vol_passed
                and bars_above_pivot >= 2
            ):
                stop_loss = val - (c_price * 0.002)
                if (c_price - stop_loss) / c_price < 0.005:
                    stop_loss = c_price * 0.995

                risk_pct = ((c_price - stop_loss) / c_price) * 100.0
                triggers.append({
                    "Signal_Date": sig_date,
                    "Exec_Date": exec_date_str,
                    "Ticker": tk,
                    "Pool": row["Pool"],
                    "Category": row["Category"],
                    "Entry_Time": bar["date"],
                    "Entry_Price": round(c_price, 2),
                    "Stop_Loss": round(stop_loss, 2),
                    "Risk_Pct": round(risk_pct, 2),
                    "filepath": filepath,
                })
                break

    # Enforce daily max-3 concurrent position slot limit sorted by earliest trigger time
    triggers.sort(key=lambda x: x["Entry_Time"])
    by_day = {}
    for t in triggers:
        by_day.setdefault(t["Exec_Date"], []).append(t)

    executed = []
    for d in sorted(by_day.keys()):
        executed.extend(by_day[d][:3])

    # Simulate 50/50 Split-Scale Exits (+2R / +4R) with +1R Breakeven Trail
    results = []
    for tr in executed:
        df_m = pd.read_csv(tr["filepath"])
        df_m.columns = [c.lower() for c in df_m.columns]
        df_m["date"] = pd.to_datetime(df_m["date"], utc=True).dt.tz_convert("US/Eastern")
        future_df = df_m[df_m["date"] > tr["Entry_Time"]]

        entry = tr["Entry_Price"]
        stop = tr["Stop_Loss"]
        risk = entry - stop
        t1r, t2r, t4r = entry + risk, entry + (2 * risk), entry + (4 * risk)

        active_stop = stop
        trailed = False
        p1_open, p2_open = True, True
        p1_pnl, p2_pnl = 0.0, 0.0

        for _, f_bar in future_df.iterrows():
            if not p1_open and not p2_open:
                break
            hi, lo = float(f_bar["high"]), float(f_bar["low"])
            if not trailed and hi >= t1r:
                active_stop = entry
                trailed = True
            if p1_open:
                if lo <= active_stop:
                    p1_pnl = 0.0 if trailed else -1.0
                    p1_open = False
                elif hi >= t2r:
                    p1_pnl = 2.0
                    p1_open = False
            if p2_open:
                if lo <= active_stop:
                    p2_pnl = 0.0 if trailed else -1.0
                    p2_open = False
                elif hi >= t4r:
                    p2_pnl = 4.0
                    p2_open = False

        if p1_open or p2_open:
            last_c = float((future_df.iloc[-1] if not future_df.empty else df_m.iloc[-1])["close"])
            if p1_open:
                p1_pnl = (last_c - entry) / risk
            if p2_open:
                p2_pnl = (last_c - entry) / risk

        blended_r = round((p1_pnl * 0.5) + (p2_pnl * 0.5), 2)
        del tr["filepath"]
        tr["Blended_PnL_R"] = blended_r
        tr["Trail_Activated"] = trailed
        results.append(tr)

    res_df = pd.DataFrame(results)
    res_df.to_csv(OUTPUT_RESULTS, index=False)
    print(f"\n[*] Saved {len(res_df)} executed trades to '{OUTPUT_RESULTS}'")

    if res_df.empty:
        print("[!] No trades triggered.")
        return

    # 1. Pool Comparison (Legacy Core vs Alpha High-Torque)
    print("\n" + "=" * 85)
    print("POOL ATTRIBUTION: LEGACY CORE (CATS 1-4) vs. ALPHA HIGH-TORQUE (CATS 5-7)")
    print("=" * 85)
    pool_summary = res_df.groupby("Pool").agg(
        Trades=("Ticker", "count"),
        Avg_Price=("Entry_Price", "mean"),
        Avg_Risk_Pct=("Risk_Pct", "mean"),
        Hit_1R_Pct=("Trail_Activated", lambda x: round(x.mean() * 100, 1)),
        Total_R=("Blended_PnL_R", "sum"),
        Expectancy_R=("Blended_PnL_R", "mean"),
    )
    print(pool_summary.round(2).to_string())

    # 2. Granular Category 1-7 Breakdown
    print("\n" + "=" * 85)
    print("SETUP CATEGORY ATTRIBUTION (CATEGORIES 1 - 7)")
    print("=" * 85)
    cat_summary = res_df.groupby(["Pool", "Category"]).agg(
        Trades=("Ticker", "count"),
        Avg_Risk_Pct=("Risk_Pct", "mean"),
        Hit_1R_Pct=("Trail_Activated", lambda x: round(x.mean() * 100, 1)),
        Total_R=("Blended_PnL_R", "sum"),
        Expectancy_R=("Blended_PnL_R", "mean"),
    ).sort_values("Total_R", ascending=False)
    print(cat_summary.round(2).to_string())

    # 3. Volatility / Stop-Width Test by Pool
    res_df["Box_Width_Tier"] = pd.cut(
        res_df["Risk_Pct"],
        bins=[0, 1.0, 1.75, 100],
        labels=["Tight (<1.0%)", "Moderate (1.0%-1.75%)", "Wide / High-Vol (>1.75%)"],
    )
    print("\n" + "=" * 85)
    print("VOLATILITY / STOP-WIDTH ATTRIBUTION BY POOL")
    print("=" * 85)
    vol_pool = res_df.groupby(["Pool", "Box_Width_Tier"], observed=False).agg(
        Trades=("Ticker", "count"),
        Hit_1R_Pct=("Trail_Activated", lambda x: round(x.mean() * 100, 1)),
        Total_R=("Blended_PnL_R", "sum"),
        Expectancy_R=("Blended_PnL_R", "mean"),
    )
    print(vol_pool.round(2).to_string())


if __name__ == "__main__":
    run_category_backtest()