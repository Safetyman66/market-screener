\# CORP ACUITY: SYSTEM ARCHITECTURE \& PIPELINE SCHEMA

\*\*Last Updated:\*\* November 2026

\*\*Primary Goal:\*\* Fully automated, regime-adaptive quantitative market screener, live algorithmic execution engine, visual charting generator, and social media dispatch pipeline.



\---



\## 1. DATA TOPOLOGY \& FEED ARCHITECTURE

The system utilizes decoupled data feeds to separate EOD historical screening from live intraday execution.

\*   \*\*Alpaca SIP (Historical):\*\* Fetches 15-month EOD consolidated tape data (OHLCV) for the master scan.

\*   \*\*Yahoo Finance (Macro):\*\* Fetches live index (SPY, QQQ), yield (^TNX), and crude (CL=F) data for regime classification.

\*   \*\*Interactive Brokers (Live Execution):\*\* Streams real-time, non-consolidated SMART-routed tick data for live VWAP and volume generation.



\---



\## 2. THE CONTROL ROOM (`regime\\\_parameters.json`)

The pipeline's quantitative logic is completely decoupled from its code tuning. This JSON file acts as the master control room, storing the exact mathematical thresholds for three distinct market environments. The scanner automatically loads the active regime ruleset before evaluating setups.



\*   \*\*EXPANSION (Risk-On / Bull):\*\* Aggressive breakout parameters. Minimum R:R drops to 2.0. Price can extend up to 12.5% above the 21 EMA. Sweeps require only a 0.99x 200-EMA floor.

\*   \*\*ROTATION (Consolidation):\*\* Selective parameters. Enforces a 2.2 R:R minimum and caps 21 EMA extension at 10.0%.

\*   \*\*CONTRACTION (Risk-Off / Defensive):\*\* Capital Preservation posture. Enforces strict 2.5 R:R minimums. Kills extended charts (>8.5% above 21 EMA). Widens the liquidity sweep floor (0.95x 200 EMA) and undercut maximum (12.5%) to catch deep, violent capitulation traps.



\---



\## 3. THE ARCHITECT: EOD ORCHESTRATION (`scanner.py`)

`scanner.py` is the End-of-Day (EOD) master screener. It is strictly locked to EOD data by silently dropping any active, incomplete intraday daily bars, preventing 30-minute volume candles from collapsing the historical indicators.



\*\*Chronological Execution Pipeline:\*\*

1\.  \*\*Preliminary Regime Detection:\*\* Evaluates SPY and QQQ 50-day SMAs and cross-asset drags (10Y Yield, WTI Crude) to classify the market as EXPANSION, ROTATION, or CONTRACTION. Loads the matching JSON dictionary.

2\.  \*\*Stage 0 (Sector Pruning):\*\* In-memory metadata pruning instantly drops low-momentum/defensive sectors (e.g., Utilities, REITs) without making network calls.

3\.  \*\*Stage 1 (Liquidity Gate):\*\* Filters the universe, enforcing a hard floor of Price >= $10.00 and 5-Day Average Daily Dollar Volume (ADDV) >= $12M.

4\.  \*\*Stage 2 (Historical Deep-Dive):\*\* Ingests 15 months of OHLCV data exclusively for liquid survivors and passes them to `setups.py` via asynchronous thread pooling.

5\.  \*\*Regime Slotting:\*\* Sorts passing candidates by `Conviction\\\_Score` (R:R weighted by volume and ATR) and assigns the top candidates to 4 execution slots, deferring to Cash/Sidelined if the regime dictates a freeze.

6\.  \*\*Data Export:\*\* Generates the `breakouts\\\_for\\\_execution.csv` payload for the live execution engine, and JSON metadata (`latest\\\_post\\\_meta.json`, `terminal\\\_feed.json`) for the web and social systems.



\---



\## 4. THE QUANTITATIVE EVALUATORS (`setups.py`)

This module houses the strict mathematical geometry that validates the four core institutional archetypes. It applies the JSON regime parameters to the historical data arrays.



1\.  \*\*Base-Reset Inflections:\*\* Hunts for macro structural bases. Validates weekly MACD histogram curling, ensures ATR14 is >1.8%, checks trend alignment (>0.5% above 200 EMA), and caps 21-day EMA rubber-band extension.

2\.  \*\*Momentum Bull Flags (HTF):\*\* Identifies High-Tight Flags. Demands a massive minimum pole gain (e.g., >45%), strict flag duration (3 to 18 days), max depth caps (e.g., <14%), and 5-day volume dry-up (<0.82x 50-day average).

3\.  \*\*Pocket Pivot Squeezes:\*\* Identifies explosive compression. Requires a mathematically validated Bollinger Band / Keltner Channel squeeze. Enforces that today's volume is greater than the highest down-day volume of the prior 10 sessions.

4\.  \*\*Liquidity Sweeps:\*\* Identifies institutional traps. Verifies the price undercut a 60-day historical support shelf by a defined percentage, then closed back up in the upper 48% of the daily range on >0.75x relative volume.



\---



\## 5. MACRO \& RESEARCH INTELLIGENCE (`research\\\_engine.py`)

This module enriches the mathematical setups with fundamental and calendar context before export.

\*   \*\*Zacks Integration:\*\* Scrapes and assigns the latest institutional earnings estimate revision strength (Rank #1 Strong Buy to #5 Strong Sell) and local tenure duration.

\*   \*\*Earnings Proximity:\*\* Calculates days until the next quarterly report, flagging "🚨 DANGER" if within 14 days to prevent event-risk holding.

\*   \*\*OPEX Calendar:\*\* Evaluates days until Monthly Options Expiration to flag synthetic pinning or gamma volatility.



\---



\## 6. THE SNIPER: LIVE EXECUTION ENGINE (`Todays\\\_acquisitions\\\_2.py`)

The autonomous intraday trading engine. It connects to the Interactive Brokers (IBKR) API (specifically configured for the 'P'-prefix Paper Trading username on port 4001/4002) to execute the static EOD candidates in real-time.



\*\*Timing \& Risk Architecture:\*\*

\*   \*\*Risk Sizing:\*\* Dynamically calculates position size based on a fixed Risk Budget ($560) and an absolute Maximum Position Cap ($10,000).

\*   \*\*09:29 ET Pre-Flight Check:\*\* Scans pre-market lows to ensure the setup's stop-loss wasn't breached overnight, and checks the opening cross against a dynamic ATR chase cap.

\*   \*\*The 4-Step Execution Stack (09:30 - 16:00 ET):\*\* Before firing an order, the engine mathematically confirms:

&#x20;   1.  \*Price > Pivot Trigger\* and \*Price > Opening Range High (ORH)\* (post 09:45).

&#x20;   2.  \*Structural Validation:\* Price > Live Intraday VWAP (Volume Weighted Average Price).

&#x20;   3.  \*Micro Polarity:\* Current 1-minute execution bar is green (Close > Open).

&#x20;   4.  \*Kinetic Energy:\* Current 1-minute volume clears the historic ADV baseline, adjusted by a \*\*0.60x Fragmentation Coefficient\*\* to normalize IBKR's non-consolidated smart-routed tape against the consolidated historical benchmark.

\*   \*\*Bracket Routing:\*\* Submits `transmit=True` orders split into a 1R scale-out tranche and a 3R runner tranche, shielded by a hard tactical stop.

\*   \*\*Fast Scratch:\*\* Constantly monitors open positions and executes a market sell if the price breaks -0.5 Standard Deviations below the session VWAP.



\---



\## 7. VISUAL ASSET CREATION (`generate\\\_live\\\_charts.py` \& `pdf\\\_engine.py`)

Triggered chronologically by the scanner, these scripts translate the CSV math into visual intelligence.

\*   \*\*`generate\\\_live\\\_charts.py`:\*\* Generates high-fidelity Matplotlib candlestick charts for every executed setup. Overlays the 200 EMA, 50 SMA, Volume, RSI, MACD, and tactical trigger/stop lines. Saves to `assets/cards/`.

\*   \*\*`pdf\\\_engine.py`:\*\*

&#x20;   \*   Builds the executive-grade 8-slide `daily\\\_market\\\_intelligence.pdf` utilizing ReportLab.

&#x20;   \*   Embeds the candlestick charts directly onto the archetype slides.

&#x20;   \*   \*\*PyMuPDF (fitz) Slicer:\*\* Converts the completed PDF pages into individual high-res images (`card\\\_1.png`, etc.) for seamless web dashboard rendering.



\---



\## 8. SOCIAL DISPATCH \& AUTOMATION (CI/CD)

The pipeline is fully automated via GitHub Actions (`daily-scanner.yml`), running without human intervention.

\*   \*\*Action Workflow:\*\* Installs dependencies (`yfinance`, `alpaca-py`, `ib\\\_async`, `reportlab`, `PyMuPDF`), runs `scanner.py`, and commits the fresh data (CSV, JSON, PDF, PNG) back to the repository.

\*   \*\*`dispatch\\\_x\\\_intent.py`:\*\* Reads the fresh JSON metadata to build a cohesive 4-part X (Twitter) thread and distributes the payload.

\*   \*\*`publish\\\_linkedin.py`:\*\* Reads the regime context, selects a matching marketing archetype (e.g., ROTATIONAL\_COMPRESSION), and uploads the full PDF carousel via the LinkedIn API.

