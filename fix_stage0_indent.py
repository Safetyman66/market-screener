with open("universe.py", "r", encoding="utf-8") as f:
    text = f.read()

# Define stage_0_prune_by_sector with strict 2-space indentation
replacement_stage_0 = """def stage_0_prune_by_sector(universe, sector_map):
  \"\"\"Filters universe by excluding defensive/financial sectors and binary biotech/pharma stocks.\"\"\"
  survivors = []
  for ticker in universe:
    meta = sector_map.get(ticker, {})
    if isinstance(meta, dict):
      sec = meta.get("sector", "") or ""
      ind = meta.get("industry", "") or ""
    else:
      sec = str(meta)
      ind = ""

    # Sector gate
    if sec in EXCLUDED_SECTORS:
      continue

    # Binary healthcare gate: drop clinical trials / drug development, retain medical devices & equipment
    if "health" in sec.lower():
      ind_lower = ind.lower()
      if any(banned in ind_lower for banned in BANNED_HEALTHCARE_KEYWORDS):
        continue

    survivors.append(ticker)

  return survivors"""

import re
pattern = r"def stage_0_prune_by_sector\(universe, sector_map\):[\s\S]*?return survivors"

if re.search(pattern, text):
    text = re.sub(pattern, replacement_stage_0, text, count=1)
    with open("universe.py", "w", encoding="utf-8") as f:
        f.write(text)
    print("[SUCCESS] Fixed indentation to 2 spaces in stage_0_prune_by_sector.")
else:
    print("[ERROR] Could not match stage_0_prune_by_sector block.")
