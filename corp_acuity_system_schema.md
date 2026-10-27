# CORP ACUITY: SYSTEM ARCHITECTURE & PIPELINE SCHEMA
**Last Updated:** October 2026
**Primary Goal:** Fully automated quantitative market screener, visual charting engine, and social media dispatch pipeline.

## 1. PIPELINE ORCHESTRATION (`scanner.py`)
`scanner.py` is the master engine. It must execute its final generation block in a strict chronological order to ensure data freshness:
1. **Mathematical Screening:** Processes universe, applies asymmetry gates, calculates regime breadth.
2. **CSV Generation:** Exports `watchlist_*.csv` and the critical `breakouts_for_execution.csv`.
3. **Chart Generation:** Triggers `generate_live_charts.py` to read the fresh CSVs and draw candlestick PNGs.
4. **PDF & Web Slicing:** Triggers `pdf_engine.py` to embed the charts, build the PDF, and slice web images.
5. **JSON Metadata:** Exports `latest_post_meta.json` and `terminal_feed.json` for social scripts and the website.

## 2. VISUAL ASSET CREATION (`generate_live_charts.py` & `pdf_engine.py`)
These two scripts handle all visual marketing and graphics. They must never be bypassed or truncated.
* **`generate_live_charts.py`:** Reads `breakouts_for_execution.csv` and draws custom Matplotlib candlestick charts directly into the `assets/cards/` directory.
* **`pdf_engine.py`:** 
  * Builds the highly-designed 8-slide `daily_market_intelligence.pdf` utilizing ReportLab.
  * Embeds the candlestick charts from `assets/cards/` directly onto slides 4 through 7.
  * **CRITICAL DEPENDENCY:** Relies on `PyMuPDF (fitz)` to slice the completed PDF into individual images (`card_1.png`, `card_2.png`, etc.) saved to `assets/cards/` for the web dashboard.

## 3. SOCIAL DISPATCH ENGINE
The social scripts are completely decoupled from chart generation. They act strictly as couriers, broadcasting the assets that `scanner.py` already produced.
* **`dispatch_x_intent.py`:** Reads `latest_post_meta.json` to build a 4-part X (Twitter) thread. It pulls fresh chart images exclusively from `assets/cards/` and emails the thread payloads.
* **`publish_linkedin.py`:** Reads `latest_post_meta.json` to select a regime-conditioned marketing archetype (e.g., ROTATIONAL_COMPRESSION, MOMENTUM_EXPANSION). It uploads the pre-built `daily_market_intelligence.pdf` directly to the LinkedIn API.

## 4. GITHUB ACTIONS CI/CD (`daily-scanner.yml`)
The entire pipeline runs daily via a unified GitHub Actions workflow:
1. Installs dependencies (`yfinance`, `pandas`, `reportlab`, `PyMuPDF`).
2. Runs `scanner.py` to calculate data and generate all assets natively.
3. Commits and pushes the fresh CSVs, JSON, PDF, and PNGs to the `main` branch.
4. Executes `publish_linkedin.py` and `dispatch_x_intent.py` to broadcast the finalized assets.