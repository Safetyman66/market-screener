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
def is_buyout_or_flatlined(daily_df, min_adr_pct=1.15):
    try:
        tail10 = daily_df.tail(10)
        if len(tail10) < 5:
            return False, 'Sufficient history'
        adr_pct = float(((tail10['High'] - tail10['Low']) / tail10['Close']).mean() * 100)
        if adr_pct < min_adr_pct:
            return True, f'Buyout/Arbitrage flatline: 10d ADR% is {adr_pct:.2f}% (< {min_adr_pct}%)'
        close_cv = float((tail10['Close'].std() / tail10['Close'].mean()) * 100)
        if close_cv < 0.60:
            return True, f'Buyout/Arbitrage freeze: 10d close volatility is {close_cv:.2f}% (< 0.60%)'
        return False, 'Normal organic price action'
    except Exception:
        return False, 'Bypass on exception'


def check_base_reset(
    ticker,
    daily_df,
    w_df,
    c0,
    daily_ema200,
    pct_above_200,
    high_52w,
    adv_20_shares,
    params
):
  try:
    min_trend_alignment = params["min_trend_alignment"]
    max_21_ema_extension = params["max_21_ema_extension"]
    min_r_ratio = params["min_r_ratio"]
    min_macro_headroom = params["min_macro_headroom"]

    if pct_above_200 < min_trend_alignment:
      return (
          None,
          f"Trend Alignment < {min_trend_alignment}%",
      )

    atr14 = calculate_atr(daily_df, 14).iloc[-1]
    atr_pct = (atr14 / c0) * 100
    if atr_pct < 1.8:
      return None, f"Sluggish daily range (ATR14 {atr_pct:.2f}% < 1.8%)"

    dist_from_52w = max(0.0, ((high_52w - c0) / high_52w) * 100)
    if dist_from_52w > 28.0:
      return None, f"Deep overhead base lag ({dist_from_52w:.1f}% > 28.0% max)"

    w_close = w_df["Close"]
    macd, signal, hist = calculate_macd(w_close)
    w_ema10 = w_close.ewm(span=10, adjust=False).mean()

    # DYNAMIC REGIME CHECK: Prevent overextended chases based on active environment rules
    daily_ema21 = daily_df["Close"].ewm(span=21, adjust=False).mean().iloc[-1]
    ext_21 = ((c0 - daily_ema21) / daily_ema21) * 100
    if ext_21 > max_21_ema_extension:
        return None, f"Overextended chase (Price is {ext_21:.1f}% above 21 EMA)"

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
    
    is_flat, flat_reason = is_buyout_or_flatlined(daily_df)
    if is_flat:
        return None, flat_reason

    # Variable Separation
    target_price = round(high_52w, 2)
    entry_pivot_gap_pct = ((daily_pivot - c0) / c0) * 100
    macro_headroom_pct = ((target_price - c0) / c0) * 100
    
    risk_pct = ((daily_pivot - tactical_stop) / daily_pivot) * 100 
    
    if risk_pct > 6.50 or risk_pct < 1.50:
        return None, f'Stop width invalid or outside bounds (Risk {risk_pct:.2f}% not in 1.5%-6.5%)'
        
    r_ratio = macro_headroom_pct / risk_pct if risk_pct > 0 else 0.0

    absolute_ath = daily_df["High"].max()
    is_blue_sky = bool(c0 >= absolute_ath)

    # DYNAMIC REGIME CHECKS
    if not (r_ratio >= min_r_ratio):
        return None, f"R:R ({r_ratio:.2f}) < {min_r_ratio}"

    if not (macro_headroom_pct >= min_macro_headroom or is_blue_sky):
        return None, f"Macro Headroom ({macro_headroom_pct:.1f}%) < {min_macro_headroom}% and not Blue Sky"

    hist_expansion = max(h0 - h2, h0 - h1)
    score = (
        (abs(hist_expansion) / max(atr14, 0.01)) * vol_ratio * r_ratio
    )

    if score < 0.60:
      return None, f"Conviction Score too low ({score:.3f} < 0.60)"

    return {
        "Ticker": ticker,
        "Close": round(c0, 2),
        "Pivot_Trigger": daily_pivot,
        "Target_Price": round(target_price, 2),
        "Stop_Loss": tactical_stop,
        "Entry_Pivot_Gap_%": round(entry_pivot_gap_pct, 2),
        "Macro_Headroom_%": round(macro_headroom_pct, 1),
        "Above_200_%": round(pct_above_200, 1),
        "Hist_Now": round(h0, 3),
        "Vol_Ratio": f"{round(vol_ratio, 2)}x",
        "Conviction_Score": round(score, 3),
        "Risk_%": round(risk_pct, 2),
        "R_Ratio": round(r_ratio, 2),
        "Is_Blue_Sky": is_blue_sky,
        "ADV_20": adv_20_shares,
        "1Min_Vol_Hurdle": int(adv_20_shares * 0.0035),
        "Execution_Archetype": "BREAKOUT",
    }, "PASSED"
  except Exception as e:
    return None, f"Error: {type(e).__name__}"


def check_htf(ticker, df, c0, daily_ema200, high_52w, adv_20_shares, params):
  try:
    min_pole_gain = params["min_pole_gain"]
    max_flag_depth = params["max_flag_depth"]
    max_flag_tightness = params["max_flag_tightness"]
    min_r_ratio = params["min_r_ratio"]

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

    if pole_gain_pct < min_pole_gain:
      return None, f"Pole gain < {min_pole_gain}% regime standard ({pole_gain_pct:.1f}%)"

    flag_low = low.iloc[-bars_since_peak:].min()
    flag_depth_pct = ((peak_price - flag_low) / peak_price) * 100

    if flag_depth_pct > max_flag_depth:
      return None, f"Flag pullback too loose (> {max_flag_depth}%)"

    last_10_high = high.tail(10).max()
    last_10_low = low.tail(10).min()
    flag_tightness_pct = ((last_10_high - last_10_low) / last_10_high) * 100

    if not (2.0 <= flag_tightness_pct <= max_flag_tightness):
      return None, f"Flag tightness out of bounds ({flag_tightness_pct:.2f}% vs {max_flag_tightness}%)"

    dist_from_peak = ((peak_price - c0) / peak_price) * 100
    if dist_from_peak > 11.0:
      return None, f"Price sagging ({dist_from_peak:.1f}% > 11.0% below peak)"

    v0 = volume.iloc[-1]
    vol_5d_avg = volume.tail(5).mean()
    vol_dryup_5d = vol_5d_avg / max(vol_sma50, 1)
    vol_dryup_d1 = v0 / max(vol_sma50, 1)

    if vol_dryup_5d > 0.82:
      return None, f"5-day volume not dry ({vol_dryup_5d:.2f}x > 0.82x of 50d avg)"
    if vol_dryup_d1 > 1.05:
      return None, f"Prior session volume churn ({vol_dryup_d1:.2f}x > 1.05x of 50d avg)"

    sma_50 = close.rolling(50).mean().iloc[-1]
    if c0 < sma_50:
        return None, 'Price below 50 SMA (not an active momentum flag)'

    ema_21 = close.ewm(span=21, adjust=False).mean().iloc[-1]
    if c0 < (0.99 * ema_21):
        return None, 'Price below 21-day EMA tolerance (< -1%)'

    pivot_trigger = round(peak_price, 2)
    tactical_stop = round(flag_low, 2)
    risk_pct = round(((pivot_trigger - tactical_stop) / pivot_trigger) * 100, 2)

    if risk_pct < 1.5 or risk_pct > 14.5:
      return None, f"Risk % invalid or outside executable limits ({risk_pct:.2f}%)"

    base_run = min(pole_gain_pct * 0.50, 18.0)
    if high_52w > pivot_trigger:
        headroom_52w = ((high_52w - pivot_trigger) / pivot_trigger) * 100
        effective_run = min(base_run, max(headroom_52w, 3.0))
    else:
        effective_run = base_run

    reward_risk = round(effective_run / risk_pct, 2)
    if reward_risk < min_r_ratio:
      return None, f"Low Asymmetry (R:R {round(reward_risk, 1)} < {min_r_ratio})"

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


def check_pocket_pivot(ticker, df, c0, daily_ema200, high_52w, adv_20_shares, params):
  try:
    min_r_ratio = params["min_r_ratio"]
    max_200_ema_extension = params["max_200_ema_extension"]
    max_10_ema_extension = params["max_10_ema_extension"]

    close = df["Close"]
    high = df["High"]
    low = df["Low"]
    volume = df["Volume"]
    v0 = volume.iloc[-1]
    vol_sma50 = volume.rolling(50).mean().iloc[-1]
    is_flat, flat_reason = is_buyout_or_flatlined(df)
    if is_flat:
        return None, flat_reason

    sma_50 = close.rolling(50).mean().iloc[-1]
    if not (c0 > daily_ema200 and c0 > sma_50 and sma_50 > daily_ema200):
      return None, "Trend not aligned (C > SMA50 > EMA200)"

    ext_200 = ((c0 - daily_ema200) / daily_ema200) * 100
    if ext_200 > max_200_ema_extension:
      return None, f"Stretched >{max_200_ema_extension}% above 200 EMA"

    headroom_calc = ((high_52w - c0) / c0) * 100
    tr14 = pd.concat([high - low, (high - close.shift(1)).abs(), (low - close.shift(1)).abs()], axis=1).max(axis=1)
    pp_atr_pct = float((tr14.rolling(14).mean().iloc[-1] / c0) * 100)
    if headroom_calc < 3.0:
        effective_headroom = min(18.0, max(6.0, round(4.0 * pp_atr_pct, 1)))
    else:
        effective_headroom = headroom_calc

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

    if not (touched_ema and closed_above_ema and ext_10 <= max_10_ema_extension):
      return None, f"Not launching off 10/21 EMA (or ext > {max_10_ema_extension}%)"

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

    reward_risk = effective_headroom / risk_pct
    if reward_risk < min_r_ratio:
      return None, f"Low Asymmetry (R:R {round(reward_risk, 1)} < {min_r_ratio})"

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
    ticker, df, c0, daily_ema200, high_52w, adv_20_shares, params
):
  try:
    min_200_ema_floor = params["min_200_ema_floor"]
    max_undercut_pct = params["max_undercut_pct"]
    min_r_ratio = params["min_r_ratio"]

    if c0 < 15.0:
      return None, "Price < $15.00 floor (Anti-Penny Gate)"

    is_flat, flat_reason = is_buyout_or_flatlined(df)
    if is_flat:
        return None, flat_reason

    if c0 < (min_200_ema_floor * daily_ema200):
        return None, f'Price below 200 EMA dynamic regime floor (< {min_200_ema_floor}x)'

    high = df["High"]
    low = df["Low"]
    volume = df["Volume"]
    current_low = low.iloc[-1]
    current_high = high.iloc[-1]
    vol_sma50 = volume.rolling(50).mean().iloc[-1]
    is_flat, flat_reason = is_buyout_or_flatlined(df)
    if is_flat:
        return None, flat_reason

    raw_headroom = ((high_52w - c0) / c0) * 100
    shelf_window = low.iloc[-60:-5]
    if len(shelf_window) < 18:
      return None, "Insufficient base formation window"

    support_shelf = shelf_window.min()
    recent_flush_low = low.iloc[-4:].min()

    undercut_pct = ((support_shelf - recent_flush_low) / support_shelf) * 100
    if not (0.20 <= undercut_pct <= max_undercut_pct):
      return None, f"No clean undercut (Needs 0.20%-{max_undercut_pct}% sweep)"

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
    if reward_risk < min_r_ratio:
      return None, f"Low Asymmetry (R:R {round(reward_risk, 1)} < {min_r_ratio})"

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

def evaluate_episodic_pivot(data, regime_params):
    """Category 5: High-torque catalyst gap-ups (PEADs)"""
    if len(data) < 50: return {"valid": False}
    
    today = data.iloc[-1]
    yest = data.iloc[-2]
    
    # Gap: Prior close to open gap >= 8.0%
    gap_pct = (today['Open'] - yest['Close']) / yest['Close']
    if gap_pct < 0.08: return {"valid": False}
    
    # Volume: Day-1 volume >= 2.5x 50-day ADV
    adv_50 = data['Volume'].rolling(50).mean().iloc[-1]
    if today['Volume'] < (2.5 * adv_50): return {"valid": False}
    
    # Base: Pre-gap consolidation range >= 15 sessions (simplified check)
    base_high = data['High'].iloc[-16:-1].max()
    base_low = data['Low'].iloc[-16:-1].min()
    if (base_high - base_low) / base_low > 0.30: return {"valid": False} # Exclude if wildly volatile before gap
    
    # Risk calculation
    atr_14 = data['High'].iloc[-14:].sub(data['Low'].iloc[-14:]).mean()
    max_risk_dist = 1.25 * atr_14
    
    stop_loss = today['Low']
    if (today['Close'] - stop_loss) > max_risk_dist:
        stop_loss = today['Close'] - max_risk_dist
        
    return {
        "valid": True, "category": 5, "trigger": today['Close'], "stop": round(stop_loss, 2),
        "daily_atr": round(atr_14, 2), "1Min_Vol_Hurdle": int((adv_50 / 390) * 1.5)
    }

def evaluate_ema_reclaim(data, regime_params):
    """Category 6: Tight Wedge Pops / 10 & 21 EMA Reclaims"""
    if len(data) < 50: return {"valid": False}
    
    today = data.iloc[-1]
    ema_10 = data['Close'].ewm(span=10, adjust=False).mean()
    ema_21 = data['Close'].ewm(span=21, adjust=False).mean()
    
    # Turn Geometry: Must have traded below 21 EMA recently, but closing above 10 & 21 today
    traded_below_recently = any(data['Low'].iloc[-11:-1] < ema_21.iloc[-11:-1])
    if not traded_below_recently: return {"valid": False}
    if today['Close'] <= ema_10.iloc[-1] or today['Close'] <= ema_21.iloc[-1]: return {"valid": False}
    
    # Volume: >= 1.4x 50-day ADV
    adv_50 = data['Volume'].rolling(50).mean().iloc[-1]
    if today['Volume'] < (1.4 * adv_50): return {"valid": False}
    
    # Risk Calculation
    atr_14 = data['High'].iloc[-14:].sub(data['Low'].iloc[-14:]).mean()
    low_3d = data['Low'].iloc[-3:].min()
    base_stop = min(low_3d, ema_21.iloc[-1])
    
    max_risk_dist = 1.25 * atr_14
    stop_loss = base_stop
    if (today['Close'] - stop_loss) > max_risk_dist:
        stop_loss = today['Close'] - max_risk_dist
        
    return {
        "valid": True, "category": 6, "trigger": today['Close'], "stop": round(stop_loss, 2),
        "daily_atr": round(atr_14, 2), "1Min_Vol_Hurdle": int((adv_50 / 390) * 1.5)
    }

def evaluate_alpha_flag(data, regime_params):
    """Category 7: High-velocity momentum flags"""
    if len(data) < 50: return {"valid": False}
    
    today = data.iloc[-1]
    
    # Pole Gain: >= 30% over rolling 15 days
    pole_low = data['Low'].iloc[-15:].min()
    pole_high = data['High'].iloc[-15:].max()
    if (pole_high - pole_low) / pole_low < 0.30: return {"valid": False}
    
    # Consolidation Depth
    atr_14 = data['High'].iloc[-14:].sub(data['Low'].iloc[-14:]).mean()
    current_depth = (pole_high - today['Close'])
    if current_depth > (1.25 * atr_14) and current_depth > (pole_high * 0.12): return {"valid": False}
    
    # Volume Dry-Up
    adv_50 = data['Volume'].rolling(50).mean().iloc[-1]
    vol_3d = data['Volume'].iloc[-3:].mean()
    if vol_3d > (0.70 * adv_50): return {"valid": False}
    
    # Risk Calculation
    flag_low = data['Low'].iloc[-5:].min() # Dynamic swing low of the flag
    stop_loss = flag_low
    max_risk_dist = 1.25 * atr_14
    if (today['Close'] - stop_loss) > max_risk_dist:
        stop_loss = today['Close'] - max_risk_dist
        
    return {
        "valid": True, "category": 7, "trigger": pole_high, "stop": round(stop_loss, 2),
        "daily_atr": round(atr_14, 2), "1Min_Vol_Hurdle": int((adv_50 / 390) * 1.5)
    }