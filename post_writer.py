"""
Corp Acuity - Dynamic LinkedIn Post Writer Engine
Generates regime-conditioned, institutional post copy across 4 distinct archetypes:
  1. ROTATIONAL_COMPRESSION (Amber tape, digestion, selective setups)
  2. MOMENTUM_EXPANSION    (Green market, broad thrust, discipline against chasing)
  3. EMPIRICAL_AUDIT       (5-day runner post-mortem, mathematical asymmetry proof)
  4. CAPITAL_PRESERVATION  (Red regime / defensive breadth, active cash discipline)
"""

import os
import json
import random

def format_ticker_list(meta):
    tickers = []
    for k in ['top_br', 'top_htf', 'top_pp', 'top_ls']:
        cand = meta.get(k)
        if cand and cand.get('Ticker'):
            tickers.append(f"${cand['Ticker']}")
    return ", ".join(tickers) if tickers else "$TJX, $WST, $TMO, $BWA"

def build_post_copy(meta, forced_archetype=None):
    regime = meta.get("regime_status", "AMBER: ROTATIONAL ACCUMULATION")
    posture = meta.get("posture_box", "Rotational accumulation: systematic asymmetry model limits risk exposure.")
    exposure = meta.get("max_exposure", "30% - 60%")
    breadth = float(meta.get("pct_above_200", 53.1))
    runner = meta.get("top_runner", {})
    runner_gain = float(runner.get("max_gain_pct", 0) if runner else 0)
    runner_ticker = runner.get("ticker", "CXT") if runner else "CXT"
    runner_r = runner.get("r_multiple", "1.4") if runner else "1.4"
    
    dashboard = meta.get("dashboard", {})
    tnx = dashboard.get("tnx", 4.25)
    oil = dashboard.get("oil", 75.0)

    ticker_str = format_ticker_list(meta)

    # 1. Determine Archetype
    if forced_archetype:
        archetype = forced_archetype.upper()
    else:
        if runner_gain >= 10.0 and random.random() < 0.40:
            archetype = "EMPIRICAL_AUDIT"
        elif "RED" in str(regime) or breadth < 45.0:
            archetype = "CAPITAL_PRESERVATION"
        elif "GREEN" in str(regime) and breadth > 60.0:
            archetype = "MOMENTUM_EXPANSION"
        else:
            archetype = "ROTATIONAL_COMPRESSION"

    # 2. Build Specific Archetype Content
    if archetype == "MOMENTUM_EXPANSION":
        lead_hooks = [
            f"{breadth:.1f}% of our US institutional universe is printing above rising 200-day EMAs.\n\nBroad momentum expansion creates high-velocity opportunities, but chasing extended breakouts without structural trade location destroys edge.",
            f"Macro Regime Posture: {regime} (Model Exposure Band: {exposure}).\n\nWhen structural trend baselines hold and liquidity confirms, systematic offensive sizing is authorized across qualified breakout pivots.",
            f"Expansionary Market Breadth: Universe metric expands to {breadth:.1f}% > 200 EMA.\n\nControlled offense requires isolating coiled base consolidations before right-tail volatility expansion occurs."
        ]
        hook = random.choice(lead_hooks)
        theme_body = (
            f"Our quantitative screening engine isolates setups exhibiting constructive accumulation while enforcing strict discipline against late chase:\n\n"
            f"1. Structural Floor: Candidates must maintain primary slope above 50 SMA and 200 EMA.\n"
            f"2. Pursuit Ceiling: Any gap or open > +2.5% beyond the trigger ceiling voids the entry geometry.\n"
            f"3. Asymmetry Hurdle: Strict >= 2.0R prospective reward-to-risk floor on every candidate.\n\n"
            f"Swipe through today's 8-page briefing deck for:\n"
            f"- Momentum Expansion Cockpit & Regime Liquidity Radar\n"
            f"- Coiled High-Tight Flags & Base-Reset Candlestick Anatomies ({ticker_str})\n"
            f"- Systematic Pursuit Boundaries & Model Invalidation Floors\n\n"
            f"Discussion for portfolio managers: In broad momentum thrusts, are you taking partial profits at +2R, or letting trailing 21 EMAs govern full runners?"
        )
        tags = "#QuantitativeFinance #MomentumTrading #Breakouts #SystematicTrading #RiskManagement"

    elif archetype == "EMPIRICAL_AUDIT":
        lead_hooks = [
            f"A setup doesn't need a +50% move to generate institutional alpha if the invalidation floor is tight.\n\nAudited 5-Day Case Study: ${runner_ticker} expands +{runner_gain:.1f}% from trigger ({runner_r}R payoff).",
            f"Positive expectancy is about payoff asymmetry, not win-rate vanity.\n\nCase Study: How our screening model isolated ${runner_ticker} before its +{runner_gain:.1f}% multi-session advance.",
            f"The mechanics of an asymmetrical trade: Tight invalidation box meets right-tail expansion.\n\nEvaluating the 5-day post-entry trajectory of ${runner_ticker} (+{runner_gain:.1f}% peak high)."
        ]
        hook = random.choice(lead_hooks)
        theme_body = (
            f"Examining the empirical execution geometry of the ${runner_ticker} screened setup:\n\n"
            f"- Model Entry Pivot: ${runner.get('entry_pivot', 51.77):.2f}\n"
            f"- Invalidation Floor: ${runner.get('stop_loss', 47.31):.2f} (Defined Risk Box: ${(runner.get('entry_pivot', 51.77) - runner.get('stop_loss', 47.31)):.2f})\n"
            f"- 5-Day Measured High: ${runner.get('peak_high', 57.87):.2f} (+{runner_gain:.1f}% peak right-tail expansion)\n"
            f"- Empirical Return: {runner_r}R on capital at initial invalidation\n\n"
            f"When risk is defined prior to trade commitment, the math does the heavy lifting.\n\n"
            f"Swipe through today's 8-page briefing deck for:\n"
            f"- Full Audited 5-Day Performance Metrics & Case Study Breakdown\n"
            f"- Current Macro Regime Cockpit (Permitted Exposure: {exposure})\n"
            f"- 4 Fresh Nightly Setups Meeting the >= 2.0R Asymmetry Floor ({ticker_str})\n\n"
            f"Question for systematic traders: Do you prefer time-based exits at Day 5, or mechanical trailing stops anchored to the 20 EMA?"
        )
        tags = "#TradingAlpha #EmpiricalAudit #RiskReward #QuantitativeTrading #PortfolioManagement"

    elif archetype == "CAPITAL_PRESERVATION":
        defensive_exposure = "0% - 20%" if ("RED" in str(regime) or breadth < 45.0) else exposure
        defensive_regime = "RED: CAPITAL PRESERVATION" if ("RED" in str(regime) or breadth < 45.0) else regime

        lead_hooks = [
            f"Preserving dry powder during market degradation is an active quantitative position.\n\nUniverse breadth has compressed to {breadth:.1f}% > 200 EMA, triggering model capital preservation rules.",
            f"Macro Regime Posture: {defensive_regime} (Defensive Exposure Model: {defensive_exposure}).\n\nForcing risk into a negative-drift tape degrades compounding. Systematic models step aside when mathematical gates fail.",
            f"Cross-Asset Stress Check: 10Y Yield holding at {tnx}%, universe breadth suppressed at {breadth:.1f}%.\n\nWhen systematic hurdle rates are not satisfied, cash is the highest-yielding asset."
        ]
        hook = random.choice(lead_hooks)
        theme_body = (
            f"Our algorithmic rules throttle portfolio exposure down to {defensive_exposure} to guard capital against drawdown:\n\n"
            f"1. Breadth Invalidation: Sub-45% universe breadth restricts fresh long commitments.\n"
            f"2. Zero-Hurdle Filtering: If no candidate achieves >= 2.0R asymmetry with low overhead supply, no setups are logged.\n"
            f"3. Strict Liquidity Gates: Pruning names where institutional participation has dried up.\n\n"
            f"Swipe through today's 8-page briefing deck for:\n"
            f"- Macro Stress Radar & Benchmark Index Health Checks\n"
            f"- Historical Drawdown Analysis across Market Regime Shifts\n"
            f"- Systematic Governance Rules & Capital Protection Protocols\n\n"
            f"How does your fund or strategy handle defensive regimes: Complete cash posture, or defensive sector rotation?"
        )
        tags = "#CapitalPreservation #RiskManagement #Macroeconomics #QuantitativeFinance #DownsideProtection"

    else:  # ROTATIONAL_COMPRESSION (Default Amber)
        lead_hooks = [
            f"{breadth:.1f}% of our US institutional universe is holding above its 200 EMA.\n\nWhen breadth consolidates near the median while benchmark 10Y yields test {tnx}%, capital allocation is governed by regime ceilings rather than momentum pursuit.",
            f"Macro Regime Posture: {regime} (Model Exposure Band: {exposure}).\n\nHeadline indices continue to hold primary trend, but internal rotational chop requires mathematical selectivity over broad index beta.",
            f"Rotational Digestion: 53% of stocks above their 200-day trendline.\n\nSystematic screening filters out narrative noise to isolate isolated base-resets and liquidity sweeps."
        ]
        hook = random.choice(lead_hooks)
        theme_body = (
            f"Our nightly quantitative engine processes the institutional US universe through three non-negotiable risk gates:\n\n"
            f"1. Regime Sizing: Capital deployment throttled to {exposure} during rotational accumulation.\n"
            f"2. Structural Baseline: Zero tolerance for negative drift; price must hold above rising 200 EMA baselines.\n"
            f"3. Asymmetry Floor: A strict >= 2.0R prospective payoff hurdle on every candidate.\n\n"
            f"Swipe through today's 8-page briefing deck for:\n"
            f"- System Regime Cockpit & Cross-Asset Liquidity Radar\n"
            f"- Full Candlestick Setup Anatomies ({ticker_str})\n"
            f"- Audited 5-Day Case Study: ${runner_ticker} (+{runner_gain:.1f}% Peak / {runner_r}R)\n"
            f"- Systematic Risk Governance & Pursuit Ceilings (+2.5%)\n\n"
            f"In rotational markets, are you finding better asymmetry in base-resets or liquidity sweeps under key support?"
        )
        tags = "#QuantitativeFinance #MarketRegime #SystematicTrading #RiskManagement #Macroeconomics"

    full_post = (
        f"{hook}\n\n"
        f"{theme_body}\n\n"
        f"Daily quantitative terminal feeds and complete CSV datasets: https://corpacuity.co.uk\n\n"
        f"---\n"
        f"Purely educational research & systematic quantitative modeling. Not investment advice or financial promotion.\n\n"
        f"{tags}"
    )
    return full_post, archetype

def preview_all_archetypes():
    meta_path = "latest_post_meta.json"
    if os.path.exists(meta_path):
        with open(meta_path, "r", encoding="utf-8") as f:
            meta = json.load(f)
    else:
        meta = {
            "regime_status": "AMBER: ROTATIONAL ACCUMULATION",
            "max_exposure": "30% - 60%",
            "pct_above_200": 53.1,
            "top_runner": {"ticker": "CXT", "max_gain_pct": 11.8, "r_multiple": "1.4", "entry_pivot": 51.77, "stop_loss": 47.31, "peak_high": 57.87},
            "top_br": {"Ticker": "TJX"}, "top_htf": {"Ticker": "WST"},
            "top_pp": {"Ticker": "TMO"}, "top_ls": {"Ticker": "BWA"},
            "dashboard": {"tnx": 4.25, "oil": 75.0}
        }

    archetypes = ["ROTATIONAL_COMPRESSION", "MOMENTUM_EXPANSION", "EMPIRICAL_AUDIT", "CAPITAL_PRESERVATION"]
    
    print("\n" + "="*80)
    print(" CORP ACUITY // DYNAMIC LINKEDIN COPY GENERATOR - ARCHETYPE PREVIEW")
    print("="*80)
    for arch in archetypes:
        post_text, selected = build_post_copy(meta, forced_archetype=arch)
        print(f"\n>>> [ARCHETYPE: {selected}] <<<\n")
        print(post_text)
        print("\n" + "-"*80)

if __name__ == "__main__":
    import sys
    if "--preview" in sys.argv:
        preview_all_archetypes()
    else:
        meta_path = "latest_post_meta.json"
        if os.path.exists(meta_path):
            with open(meta_path, "r", encoding="utf-8") as f:
                meta = json.load(f)
            post, arch = build_post_copy(meta)
            print(f"[Selected Archetype: {arch}]\n")
            print(post)
        else:
            preview_all_archetypes()