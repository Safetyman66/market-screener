import datetime
import numpy as np
import pandas as pd
# ---------------------------------------------------------
def resample_daily_to_weekly(daily_df):
  daily_df = daily_df.sort_index()
  weekly_df = (
      daily_df.resample("W-FRI")
      .agg({
          "Open": "first",
          "High": "max",
          "Low": "min",
          "Close": "last",
          "Volume": "sum",
      })
      .dropna()
  )

  now_utc = datetime.datetime.now(datetime.timezone.utc)
  if now_utc.weekday() < 4 and len(weekly_df) > 1:
    weekly_df = weekly_df.iloc[:-1]

  return weekly_df


def calculate_macd(series, fast=12, slow=26, signal=9):
  ema_fast = series.ewm(span=fast, adjust=False).mean()
  ema_slow = series.ewm(span=slow, adjust=False).mean()
  macd_line = ema_fast - ema_slow
  signal_line = macd_line.ewm(span=signal, adjust=False).mean()
  hist = macd_line - signal_line
  return macd_line, signal_line, hist


def calculate_atr(df, window=14):
  high = df["High"]
  low = df["Low"]
  close_prev = df["Close"].shift(1)
  tr = pd.concat(
      [high - low, (high - close_prev).abs(), (low - close_prev).abs()], axis=1
  ).max(axis=1)
  return tr.rolling(window=window).mean()



# ---------------------------------------------------------
def check_base_reset(
    ticker,
    daily_df,
    w_df,
    c0,
    daily_ema200,
    pct_above_200,
    high_52w,
    adv_20_shares,
):
  try:
    if pct_above_200 < 0.5:
      return (
          None,
          f"Below 200 EMA uptrend floor ({pct_above_200:.1f}% < +0.5%)",
      )

    atr14 = calculate_atr(daily_df, 14).iloc[-1]
    atr_pct = (atr14 / c0) * 100
    if atr_pct < 1.8:
      return None, f"Sluggish daily range (ATR14 {atr_pct:.2f}% < 1.8%)"

    dist_from_52w = max(0.0, ((high_52w - c0) / high_52w) * 100)
    if dist_from_52w > 28.0:
      return None, f"Deep overhead base lag ({dist_from_52w:.1f}% > 28.0% max)"

    headroom_calc = ((high_52w - c0) / c0) * 100
    effective_headroom = (
        40.0 if headroom_calc < 3.0 else max(15.0, headroom_calc)
    )

    w_close = w_df["Close"]
    macd, signal, hist = calculate_macd(w_close)
    w_ema10 = w_close.ewm(span=10, adjust=False).mean()

    h0, h1, h2 = hist.iloc[-1], hist.iloc[-2], hist.iloc[-3]
    hist_curling = (h0 >= h1 - 0.08) or (h1 >= h2)
    if not hist_curling:
      return None, "Weekly histogram declining consecutively"

    if c0 < (w_ema10.iloc[-1] * 0.93):
      return None, "Price significantly below 10w EMA"

    weekday_idx = min(datetime.date.today().weekday() + 1, 5)
    current_week_vol = w_df["Volume"].iloc[-1]
    projected_week_vol = current_week_vol * (5.0 / weekday_idx)
    w_vol_sma10 = w_df["Volume"].rolling(window=10).mean().iloc[-1]

    vol_ratio = projected_week_vol / max(w_vol_sma10, 1)
    if vol_ratio < 0.40:
      return None, "Paced weekly volume severely dry (<40% of 10w avg)"

    daily_pivot = round(daily_df["High"].tail(5).max(), 2)
    tactical_stop = round(daily_df["Low"].tail(3).min(), 2)
    risk_pct = round(((daily_pivot - tactical_stop) / daily_pivot) * 100, 2)

    if risk_pct > 13.0 or risk_pct <= 0:
      return None, "Stop width invalid or >13.0%"

    reward_risk = effective_headroom / risk_pct
    if reward_risk < 2.5:
      return None, f"Low Asymmetry (R:R {round(reward_risk, 1)} < 2.5)"

    hist_expansion = max(h0 - h2, h0 - h1)
    score = (
        (abs(hist_expansion) / max(atr14, 0.01)) * vol_ratio * reward_risk
    )

    if score < 0.12:
      return None, f"Conviction Score too low ({score:.3f} < 0.12)"

    return {
        "Ticker": ticker,
        "Close": round(c0, 2),
        "Headroom_%": round(headroom_calc, 1),
        "Above_200_%": round(pct_above_200, 1),
        "Hist_Now": round(h0, 3),
        "Vol_Ratio": f"{round(vol_ratio, 2)}x",
        "Conviction_Score": round(score, 3),
        "Pivot_Trigger": daily_pivot,
        "Stop_Loss": tactical_stop,
        "Risk_%": risk_pct,
        "R_Ratio": round(reward_risk, 2),
        "ADV_20": adv_20_shares,
        "1Min_Vol_Hurdle": int(adv_20_shares * 0.0035),
        "Execution_Archetype": "BREAKOUT",
    }, "PASSED"
  except Exception as e:
    return None, f"Error: {type(e).__name__}"


def check_htf(ticker, df, c0, daily_ema200, high_52w, adv_20_shares):
  try:
    if c0 < (0.96 * daily_ema200):
      return None, "Price below 200 EMA tolerance (< -4%)"

    close = df["Close"]
    high = df["High"]
    low = df["Low"]
    volume = df["Volume"]
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

    dist_from_peak = ((peak_price - c0) / peak_price) * 100
    if dist_from_peak > 11.0:
      return None, f"Price sagging ({dist_from_peak:.1f}% > 11.0% below peak)"

    v0 = volume.iloc[-1]
    vol_5d_avg = volume.tail(5).mean()
    vol_dryup_5d = vol_5d_avg / max(vol_sma50, 1)
    vol_dryup_d1 = v0 / max(vol_sma50, 1)

    if vol_dryup_5d > 0.82:
      return (
          None,
          f"5-day volume not dry ({vol_dryup_5d:.2f}x > 0.82x of 50d avg)",
      )
    if vol_dryup_d1 > 1.05:
      return (
          None,
          f"Prior session volume churn ({vol_dryup_d1:.2f}x > 1.05x of 50d"
          " avg)",
      )

    ema_21 = close.ewm(span=21, adjust=False).mean().iloc[-1]
    if c0 < (0.95 * ema_21):
      return None, "Broken below 21-day EMA"

    pivot_trigger = round(peak_price, 2)
    tactical_stop = round(flag_low, 2)
    risk_pct = round(
        ((pivot_trigger - tactical_stop) / pivot_trigger) * 100, 2
    )

    if risk_pct < 1.5 or risk_pct > 14.5:
      return (
          None,
          f"Risk % invalid or outside executable limits ({risk_pct:.2f}%)",
      )

    projected_run = pole_gain_pct * 0.50
    reward_risk = projected_run / risk_pct
    if reward_risk < 2.0:
      return None, f"Low Asymmetry (R:R {round(reward_risk, 1)} < 2.0)"

    return {
        "Ticker": ticker,
        "Close": round(c0, 2),
        "Pole_Gain_%": round(pole_gain_pct, 1),
        "Flag_Days": bars_since_peak,
        "Flag_Depth_%": round(flag_depth_pct, 1),
        "10d_Tightness_%": round(flag_tightness_pct, 1),
        "Vol_DryUp": f"{round(vol_dryup_5d, 2)}x",
        "Conviction_Score": round(reward_risk, 2),
        "Pivot_Trigger": pivot_trigger,
        "Stop_Loss": tactical_stop,
        "Risk_%": risk_pct,
        "R_Ratio": round(reward_risk, 2),
        "ADV_20": adv_20_shares,
        "1Min_Vol_Hurdle": int(adv_20_shares * 0.0035),
        "Execution_Archetype": "BREAKOUT",
    }, "PASSED"
  except Exception as e:
    return None, f"Error: {type(e).__name__}"


def check_pocket_pivot(ticker, df, c0, daily_ema200, high_52w, adv_20_shares):
  try:
    close = df["Close"]
    high = df["High"]
    low = df["Low"]
    volume = df["Volume"]
    v0 = volume.iloc[-1]
    vol_sma50 = volume.rolling(50).mean().iloc[-1]

    sma_50 = close.rolling(50).mean().iloc[-1]
    if not (c0 > sma_50 and sma_50 > (0.96 * daily_ema200)):
      return None, "Trend not aligned (C > SMA50 > EMA200)"

    ext_200 = ((c0 - daily_ema200) / daily_ema200) * 100
    if ext_200 > 45.0:
      return None, "Stretched >45% above 200 EMA"

    headroom_calc = ((high_52w - c0) / c0) * 100
    effective_headroom = (
        35.0 if headroom_calc < 3.0 else max(15.0, headroom_calc)
    )

    ema_10 = close.ewm(span=10, adjust=False).mean()
    ema_21 = close.ewm(span=21, adjust=False).mean()

    sma_20 = close.rolling(20).mean()
    std_20 = close.rolling(20).std()
    upper_bb = sma_20 + (2.0 * std_20)
    lower_bb = sma_20 - (2.0 * std_20)

    tr = pd.concat(
        [high - low, (high - close.shift(1)).abs(), (low - close.shift(1)).abs()],
        axis=1,
    ).max(axis=1)
    atr_20 = tr.rolling(20).mean()
    upper_kc = sma_20 + (1.5 * atr_20)
    lower_kc = sma_20 - (1.5 * atr_20)

    squeeze_active = (upper_bb.iloc[-6:] < upper_kc.iloc[-6:]) & (
        lower_bb.iloc[-6:] > lower_kc.iloc[-6:]
    )
    if not squeeze_active.any():
      return None, "No Bollinger/Keltner squeeze"

    if c0 <= close.iloc[-2]:
      return None, "Pivot bar must close green"

    touched_ema = (low.iloc[-1] <= (1.02 * ema_10.iloc[-1])) or (
        low.iloc[-1] <= (1.02 * ema_21.iloc[-1])
    )
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
    risk_pct = round(
        ((pivot_trigger - tactical_stop) / pivot_trigger) * 100, 2
    )

    if risk_pct > 6.5 or risk_pct < 1.5:
      return None, "Tactical risk invalid or outside 1.5%-6.5%"

    reward_risk = effective_headroom / risk_pct
    if reward_risk < 2.0:
      return None, f"Low Asymmetry (R:R {round(reward_risk, 1)} < 2.0)"

    return {
        "Ticker": ticker,
        "Close": round(c0, 2),
        "Headroom_%": round(headroom_calc, 1),
        "Ext_10EMA_%": round(ext_10, 1),
        "Above_200EMA_%": round(ext_200, 1),
        "Vol_Pocket_Ratio": f"{vol_pocket_ratio}x",
        "Conviction_Score": round(reward_risk, 2),
        "Pivot_Trigger": pivot_trigger,
        "Stop_Loss": tactical_stop,
        "Risk_%": risk_pct,
        "R_Ratio": round(reward_risk, 2),
        "ADV_20": adv_20_shares,
        "1Min_Vol_Hurdle": int(adv_20_shares * 0.0035),
        "Execution_Archetype": "BREAKOUT",
    }, "PASSED"
  except Exception as e:
    return None, f"Error: {type(e).__name__}"


def check_liquidity_sweep(
    ticker, df, c0, daily_ema200, high_52w, adv_20_shares
):
  try:
    if c0 < 15.0:
      return None, "Price < $15.00 floor (Anti-Penny Gate)"

    if c0 < (0.95 * daily_ema200):
      return None, "Price below 200 EMA tolerance (< -5%)"

    high = df["High"]
    low = df["Low"]
    volume = df["Volume"]
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
    risk_pct = round(
        ((pivot_trigger - tactical_stop) / pivot_trigger) * 100, 2
    )

    if risk_pct > 6.5 or risk_pct < 1.5:
      return None, "Tactical risk invalid or outside 1.5%-6.5%"

    reward_risk = raw_headroom / risk_pct
    if reward_risk < 2.5:
      return None, f"Low Asymmetry (R:R {round(reward_risk, 1)} < 2.5)"

    return {
        "Ticker": ticker,
        "Close": round(c0, 2),
        "Shelf_Level": round(support_shelf, 2),
        "Flush_Low": round(recent_flush_low, 2),
        "Sweep_Depth_%": round(undercut_pct, 2),
        "Headroom_%": round(raw_headroom, 1),
        "Vol_Ratio": f"{round(vol_ratio, 2)}x",
        "Conviction_Score": round(reward_risk, 2),
        "Pivot_Trigger": pivot_trigger,
        "Stop_Loss": tactical_stop,
        "Risk_%": risk_pct,
        "R_Ratio": round(reward_risk, 2),
        "ADV_20": adv_20_shares,
        "1Min_Vol_Hurdle": int(adv_20_shares * 0.0035),
        "Execution_Archetype": "MEAN_REVERSION",
    }, "PASSED"
  except Exception as e:
    return None, f"Error: {type(e).__name__}"


# ---------------------------------------------------------
