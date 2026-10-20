"""Corp Acuity // Universe Ingestion & Liquidity Gates.

Handles Wikipedia universe ingestion (S&P 500, S&P 400), SEC metadata mapping,
offline sector caching, and multi-stage liquidity gates (Stage 0 & Stage 1).
"""

import io
import json
import os
import time
import pandas as pd
import requests
import yfinance as yf

SECTOR_CACHE_FILE = "sector_cache.json"


BANNED_HEALTHCARE_KEYWORDS = {
    "biotechnology",
    "biopharmaceutical",
    "clinical trials",
    "drug discovery",
    "therapeutics",
    "pharmaceuticals",
}

ALLOWED_HEALTHCARE_SUBINDUSTRIES = {
    "medical devices",
    "medical instruments",
    "diagnostics & research",
    "healthcare plans",
    "medical care facilities",
    "health information services",
    "medical distribution",
}

EXCLUDED_SECTORS = {
    "Financials",
    "Financial Services",
    "Real Estate",
    "Utilities",
    "Consumer Staples",
    "Consumer Defensive",
}

BANNED_HEALTHCARE_KEYWORDS = {
    "biotechnology",
    "biopharmaceutical",
    "pharmaceutical",
    "clinical trials",
    "drug discovery",
    "therapeutics",
}

BANNED_INDUSTRY_KEYWORDS = [
    "apparel",
    "retail",
    "truck",
    "freight",
    "footwear",
    "bank",
    "credit",
    "mortgage",
    "homebuild",
    "grocery",
    "hotel",
    "resort",
    "cruise",
    "marine",
    "tobacco",
    "publishing",
    "broadcasting",
    "ground transportation",
    "building products",
    "consumer finance",
    "packaging",
    "containers",
    "auto parts",
    "dealership",
    "biotechnology",
    "drug",
    "pharmaceutical",
    "medical devices",
    "diagnostics",
    "healthcare providers",
    "industrial distribution",
    "restaurant",
    "machinery",
    "heavy equipment",
    "oil & gas midstream",
    "pipeline",
    "electronic manufacturing services",
    "it consulting",
    "research services",
]


def load_json_cache(filepath):
  if os.path.exists(filepath):
    try:
      with open(filepath, "r", encoding="utf-8") as f:
        return json.load(f)
    except Exception:
      return {}
  return {}


def save_json_cache(filepath, data):
  try:
    with open(filepath, "w", encoding="utf-8") as f:
      json.dump(data, f, indent=2)
  except Exception:
    pass


def fetch_institutional_universe_and_sectors():
  tickers = set()
  sector_map = load_json_cache(SECTOR_CACHE_FILE)
  if not isinstance(sector_map, dict):
    sector_map = {}

  headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

  try:
    url_sp500 = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
    resp = requests.get(url_sp500, headers=headers, timeout=10)
    df_sp500 = pd.read_html(io.StringIO(resp.text))[0]
    for _, row in df_sp500.iterrows():
      sym = str(row["Symbol"]).strip().replace(".", "-")
      tickers.add(sym)
      sec = str(row.get("GICS Sector", "Unknown"))
      ind = str(row.get("GICS Sub-Industry", "Unknown"))
      sector_map[sym] = {"sector": sec, "industry": ind}

    url_sp400 = "https://en.wikipedia.org/wiki/List_of_S%26P_400_companies"
    resp = requests.get(url_sp400, headers=headers, timeout=10)
    df_sp400 = pd.read_html(io.StringIO(resp.text))[0]
    for _, row in df_sp400.iterrows():
      sym = str(row["Symbol"]).strip().replace(".", "-")
      tickers.add(sym)
      sec = str(row.get("GICS Sector", "Unknown"))
      ind = str(row.get("GICS Sub-Industry", "Unknown"))
      sector_map[sym] = {"sector": sec, "industry": ind}
  except Exception as e:
    print(f"Warning: Wikipedia fetch encountered issue: {e}")

  save_json_cache(SECTOR_CACHE_FILE, sector_map)
  return sorted(list(tickers)), sector_map


def stage_0_prune_by_sector(universe, sector_map):
  """Filters universe by excluding defensive/financial sectors and binary biotech/pharma stocks."""
  survivors = []
  for ticker in universe:
    meta = sector_map.get(ticker, {})
    if isinstance(meta, dict):
      sec = meta.get("sector", "") or ""
      ind = meta.get("industry", "") or ""
    else:
      sec = str(meta)
      ind = ""

    # Sector exclusion gate
    if sec in EXCLUDED_SECTORS:
      continue

    # Binary healthcare gate: exclude clinical drug developers, keep medical devices & equipment
    if "health" in sec.lower():
      ind_lower = ind.lower()
      if any(banned in ind_lower for banned in BANNED_HEALTHCARE_KEYWORDS):
        continue

    survivors.append(ticker)

  return survivors


def stage_1_prune_by_liquidity(tickers_pool, chunk_size=100):
  qualified = []
  total = len(tickers_pool)
  for i in range(0, total, chunk_size):
    chunk = tickers_pool[i : i + chunk_size]
    print(
        f"Stage 1: Scanning {i + 1}-{min(i + chunk_size, total)} of {total}...",
        end="",
        flush=True,
    )
    batch_passed = 0
    try:
      data = yf.download(
          chunk,
          period="5d",
          interval="1d",
          group_by="ticker",
          threads=True,
          progress=False,
      )
    except Exception:
      qualified.extend(chunk)
      print(f" (fallback {len(chunk)})")
      continue

    for sym in chunk:
      try:
        df = data[sym].dropna() if len(chunk) > 1 else data.dropna()
        if len(df) >= 3:
          c0 = float(df["Close"].iloc[-1])
          v5 = df["Volume"].tail(5).mean()
          dollar_vol_5d = c0 * v5
          if c0 >= 10.0 and dollar_vol_5d >= 12_000_000:
            qualified.append(sym)
            batch_passed += 1
        else:
          qualified.append(sym)
      except Exception:
        qualified.append(sym)

    print(f" done ({batch_passed} liquid)")
    time.sleep(0.5)

  return sorted(list(set(qualified)))

def is_binary_healthcare(industry_str):
    if not industry_str:
        return False
    ind_lower = industry_str.lower()
    for kw in BANNED_HEALTHCARE_KEYWORDS:
        if kw in ind_lower:
            return True
    return False
