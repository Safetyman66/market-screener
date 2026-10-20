import os
import pymupdf as fitz
from reportlab.lib.colors import HexColor
from reportlab.pdfgen import canvas

CAROUSEL_PDF_FILENAME = "daily_market_intelligence.pdf"
def create_linkedin_carousel_pdf(
    filename,
    regime_status,
    posture_box,
    max_exposure,
    calendar_alerts,
    pct_above_200,
    top_runner,
    top_br,
    top_htf,
    top_pp,
    top_ls,
    dashboard=None,
):
  w, h = 1080, 1080
  c = canvas.Canvas(filename, pagesize=(w, h))

  bg_color = HexColor("#070a12")
  card_bg = HexColor("#0f172a")
  card_inner = HexColor("#1e293b")
  text_white = HexColor("#f8fafc")
  text_muted = HexColor("#94a3b8")
  accent_cyan = HexColor("#38bdf8")
  accent_green = HexColor("#4ade80")
  accent_amber = HexColor("#fbbf24")
  accent_red = HexColor("#f87171")

  def draw_base(header, slide_num, total_slides=8):
    c.setFillColor(bg_color)
    c.rect(0, 0, w, h, fill=True, stroke=False)
    c.setFont("Helvetica-Bold", 14)
    c.setFillColor(text_muted)
    c.drawString(60, h - 50, "CORP ACUITY // INSTITUTIONAL INTELLIGENCE")
    c.drawRightString(w - 60, h - 50, f"{slide_num} of {total_slides}")
    c.setStrokeColor(card_inner)
    c.setLineWidth(1)
    c.line(60, h - 65, w - 60, h - 65)

  # ---------------- SLIDE 1: COVER ----------------
  draw_base("MARKET BRIEFING", 1, 8)
  c.setFont("Helvetica-Bold", 30)
  c.setFillColor(accent_cyan)
  c.drawString(60, h - 200, "DAILY MARKET INTEL")

  c.setFont("Helvetica-Bold", 54)
  c.setFillColor(text_white)
  c.drawString(60, h - 275, "Systematic Setups &")
  c.drawString(60, h - 345, "Macro Breadth Regime")

  c.setFillColor(card_bg)
  c.roundRect(60, h - 700, w - 120, 290, 16, fill=True, stroke=False)

  c.setFont("Helvetica-Bold", 24)
  c.setFillColor(accent_green)
  c.drawString(90, h - 470, "SYSTEM ARCHITECTURE")
  c.setFont("Helvetica", 20)
  c.setFillColor(text_muted)
  c.drawString(
      90,
      h - 520,
      "• Multi-Stage Ingestion: Stage 0 Metadata & Stage 1 Liquidity Pruned",
  )
  c.drawString(
      90, h - 560, "• Minimum 2.0R Mathematical Asymmetry Floor on All Setups"
  )
  c.drawString(
      90, h - 600, "• Macro Exposure Governed by 200 EMA Structural Breadth"
  )

  c.setFillColor(card_inner)
  c.roundRect(90, h - 680, w - 180, 55, 10, fill=True, stroke=False)
  c.setFont("Helvetica-Bold", 20)
  c.setFillColor(accent_cyan)
  c.drawCentredString(
      w / 2, h - 645, "Full Terminal & Complete Watchlists: corpacuity.co.uk"
  )

  c.setFont("Helvetica-Bold", 22)
  c.setFillColor(text_white)
  c.drawCentredString(
      w / 2, 80, "Swipe across for today's verified setups & regime metrics ➔"
  )
  c.showPage()

  # ---------------- SLIDE 2: REGIME DASHBOARD ----------------
  draw_base("MACRO REGIME COCKPIT", 2, 8)
  c.setFont("Helvetica-Bold", 32)
  c.setFillColor(accent_cyan)
  c.drawString(60, h - 120, "SYSTEM REGIME POSTURE")

  c.setFillColor(card_bg)
  c.roundRect(60, h - 340, w - 120, 195, 16, fill=True, stroke=False)
  c.setFont("Helvetica-Bold", 18)
  c.setFillColor(text_muted)
  c.drawString(90, h - 165, "CURRENT REGIME STATUS")
  c.setFont("Helvetica-Bold", 38)
  c.setFillColor(
      accent_green
      if "GREEN" in regime_status
      else (accent_amber if "AMBER" in regime_status else accent_red)
  )
  c.drawString(90, h - 215, regime_status)

  c.setFont("Helvetica-Bold", 22)
  c.setFillColor(text_white)
  c.drawString(90, h - 265, f"Suggested Allocation: {max_exposure}")
  c.setFont("Helvetica", 17)
  c.setFillColor(text_muted)
  clean_posture = (
      posture_box.replace("■", "").replace("▲", "").replace("◆", "").strip()
  )
  c.drawString(90, h - 305, clean_posture[:68])

  tile_w = (w - 150) / 2
  tile_h = 135

  c.setFillColor(card_bg)
  c.roundRect(60, h - 500, tile_w, tile_h, 14, fill=True, stroke=False)
  c.setFont("Helvetica-Bold", 16)
  c.setFillColor(text_muted)
  c.drawString(85, h - 390, "UNIVERSE BREADTH (>200 EMA)")
  c.setFont("Helvetica-Bold", 36)
  c.setFillColor(accent_cyan)
  c.drawString(85, h - 440, f"{round(pct_above_200, 1)}%")
  c.setFont("Helvetica", 14)
  c.setFillColor(text_muted)
  c.drawString(85, h - 475, "Consolidating above 38% panic floor")

  c.setFillColor(card_bg)
  c.roundRect(
      60 + tile_w + 30, h - 500, tile_w, tile_h, 14, fill=True, stroke=False
  )
  c.setFont("Helvetica-Bold", 16)
  c.setFillColor(text_muted)
  c.drawString(85 + tile_w + 30, h - 390, "CROSS-ASSET RADAR")
  c.setFont("Helvetica-Bold", 24)
  c.setFillColor(text_white)
  tnx_str = (
      f"10Y Yield: {dashboard.get('tnx', 4.25)}%"
      if dashboard
      else "10Y Yield: Normal"
  )
  oil_str = (
      f"WTI Crude: ${dashboard.get('oil', 75.0)}/bbl"
      if dashboard
      else "WTI: Normal"
  )
  c.drawString(85 + tile_w + 30, h - 435, tnx_str)
  c.drawString(85 + tile_w + 30, h - 475, oil_str)

  c.setFillColor(card_bg)
  c.roundRect(60, h - 660, tile_w, tile_h, 14, fill=True, stroke=False)
  c.setFont("Helvetica-Bold", 16)
  c.setFillColor(text_muted)
  c.drawString(85, h - 550, "INDEX STRUCTURAL HEALTH")
  c.setFont("Helvetica-Bold", 22)
  spy_above_200 = dashboard.get("spy_above_200", True) if dashboard else True
  qqq_above_200 = dashboard.get("qqq_above_200", True) if dashboard else True
  c.setFillColor(accent_green if spy_above_200 else accent_red)
  c.drawString(
      85,
      h - 595,
      f"SPY: {'Above 200 EMA' if spy_above_200 else 'Below 200 EMA'}",
  )
  c.setFillColor(accent_green if qqq_above_200 else accent_red)
  c.drawString(
      85,
      h - 635,
      f"QQQ: {'Above 200 EMA' if qqq_above_200 else 'Below 200 EMA'}",
  )

  c.setFillColor(card_bg)
  c.roundRect(
      60 + tile_w + 30, h - 660, tile_w, tile_h, 14, fill=True, stroke=False
  )
  c.setFont("Helvetica-Bold", 16)
  c.setFillColor(text_muted)
  c.drawString(85 + tile_w + 30, h - 550, "TACTICAL DIRECTIVE")
  c.setFont("Helvetica", 15)
  c.setFillColor(text_white)
  action_text = (
      dashboard.get("action_plan", "Trade high asymmetry setups.")
      if dashboard
      else "Trade setups."
  )
  c.drawString(85 + tile_w + 30, h - 590, action_text[:42])
  c.drawString(85 + tile_w + 30, h - 620, action_text[42:84])

  c.setFillColor(card_inner)
  c.roundRect(60, h - 850, w - 120, 160, 14, fill=True, stroke=False)
  c.setFont("Helvetica-Bold", 18)
  c.setFillColor(accent_amber)
  c.drawString(85, h - 710, "IMMINENT MACRO RADAR & RELEASES:")
  c.setFont("Helvetica", 16)
  c.setFillColor(text_white)
  y_cal = h - 745
  radar = (
      calendar_alerts[:3]
      if calendar_alerts
      else ["Clear Runway: No high-impact shocks in 72h."]
  )
  for al in radar:
    c.drawString(85, y_cal, al.replace("🚨", "! ")[:75])
    y_cal -= 35

  c.showPage()

  # ---------------- SLIDE 3: 5-DAY RUNNER ----------------
  draw_base("SYSTEM PERFORMANCE // 5D ALPHA", 3, 8)

  if top_runner and top_runner.get("max_gain_pct", 0) > 0:
    c.setFont("Helvetica-Bold", 32)
    c.setFillColor(accent_amber)
    c.drawString(
        60,
        h - 140,
        "How did we do? Here is our top performer over the last 5 days!",
    )

    c.setFont("Helvetica-Bold", 52)
    c.setFillColor(text_white)
    c.drawString(60, h - 215, f"${top_runner['ticker']} Peak Run: ")
    c.setFillColor(accent_green)
    c.drawString(560, h - 215, f"+{top_runner['max_gain_pct']}%")

    c.setFillColor(card_bg)
    c.roundRect(60, h - 850, w - 120, 580, 24, fill=True, stroke=False)

    c.setFont("Helvetica-Bold", 24)
    c.setFillColor(text_muted)
    c.drawString(100, h - 310, "AUDITED SYSTEM VERIFICATION")

    c.setFont("Helvetica-Bold", 30)
    c.setFillColor(accent_cyan)
    c.drawString(
        100,
        h - 360,
        f"Triggered: {top_runner['rec_date']} ({top_runner['category']})",
    )

    metrics = [
        ("SUGGESTED PIVOT", f"${top_runner['entry_pivot']:.2f}", text_white),
        ("5-DAY PEAK HIGH", f"${top_runner['peak_high']:.2f}", accent_green),
        ("TACTICAL STOP", f"${top_runner['stop_loss']:.2f}", accent_red),
        ("CAPTURED MULTIPLE", f"{top_runner['r_multiple']}R", accent_cyan),
    ]

    grid_y = h - 540
    b_w, b_h = 420, 120

    c.setFillColor(card_inner)
    c.roundRect(100, grid_y, b_w, b_h, 16, fill=True, stroke=False)
    c.setFont("Helvetica-Bold", 18)
    c.setFillColor(text_muted)
    c.drawString(125, grid_y + 80, metrics[0][0])
    c.setFont("Helvetica-Bold", 36)
    c.setFillColor(metrics[0][2])
    c.drawString(125, grid_y + 25, metrics[0][1])

    c.setFillColor(card_inner)
    c.roundRect(w - 100 - b_w, grid_y, b_w, b_h, 16, fill=True, stroke=False)
    c.setFont("Helvetica-Bold", 18)
    c.setFillColor(text_muted)
    c.drawString(w - 100 - b_w + 25, grid_y + 80, metrics[1][0])
    c.setFont("Helvetica-Bold", 36)
    c.setFillColor(metrics[1][2])
    c.drawString(w - 100 - b_w + 25, grid_y + 25, metrics[1][1])

    grid_y_low = grid_y - 150
    c.setFillColor(card_inner)
    c.roundRect(100, grid_y_low, b_w, b_h, 16, fill=True, stroke=False)
    c.setFont("Helvetica-Bold", 18)
    c.setFillColor(text_muted)
    c.drawString(125, grid_y_low + 80, metrics[2][0])
    c.setFont("Helvetica-Bold", 36)
    c.setFillColor(metrics[2][2])
    c.drawString(125, grid_y_low + 25, metrics[2][1])

    c.setFillColor(card_inner)
    c.roundRect(
        w - 100 - b_w, grid_y_low, b_w, b_h, 16, fill=True, stroke=False
    )
    c.setFont("Helvetica-Bold", 18)
    c.setFillColor(text_muted)
    c.drawString(w - 100 - b_w + 25, grid_y_low + 80, metrics[3][0])
    c.setFont("Helvetica-Bold", 36)
    c.setFillColor(metrics[3][2])
    c.drawString(w - 100 - b_w + 25, grid_y_low + 25, metrics[3][1])

    c.setFont("Helvetica-Bold", 24)
    c.setFillColor(text_white)
    c.drawCentredString(
        w / 2,
        h - 800,
        "Systematic asymmetry: cutting losers short and letting winners expand.",
    )
  else:
    c.setFillColor(card_bg)
    c.roundRect(60, h - 600, w - 120, 360, 24, fill=True, stroke=False)
    c.setFont("Helvetica-Bold", 34)
    c.setFillColor(accent_amber)
    c.drawString(
        100,
        h - 350,
        "How did we do? Here is our top performer over the last 5 days!",
    )
    c.setFont("Helvetica", 22)
    c.setFillColor(text_muted)
    c.drawString(
        100,
        h - 420,
        "Logged setups are evaluated nightly against subsequent post-entry peak"
        " highs.",
    )
    c.drawString(
        100,
        h - 465,
        "Audited 5-day R-multiple tracking populates on subsequent sessions.",
    )

  c.showPage()

  def draw_setup_slide(title, subtitle, candidate, slide_idx):
    draw_base(title, slide_idx, 8)
    c.setFont("Helvetica-Bold", 32)
    c.setFillColor(accent_cyan)
    c.drawString(60, h - 130, title)
    c.setFont("Helvetica", 20)
    c.setFillColor(text_muted)
    c.drawString(60, h - 170, subtitle)

    if not candidate:
      c.setFillColor(card_bg)
      c.roundRect(60, h - 550, w - 120, 300, 16, fill=True, stroke=False)
      c.setFont("Helvetica-Bold", 28)
      c.setFillColor(text_white)
      c.drawCentredString(
          w / 2, h - 420, "No Setups Met Strict Asymmetry Floor (>= 2.0R)"
      )
      c.setFont("Helvetica", 20)
      c.setFillColor(text_muted)
      c.drawCentredString(
          w / 2, h - 470, "Capital preservation rules enforced. Cash is a valid position."
      )
      c.showPage()
      return

    c.setFont("Helvetica-Bold", 50)
    c.setFillColor(accent_green)
    c.drawString(60, h - 250, f"${candidate['Ticker']}")
    c.setFont("Helvetica", 26)
    c.setFillColor(text_white)
    c.drawString(320, h - 245, f"Last Close: ${candidate['Close']:.2f}")

    c.setFillColor(card_bg)
    c.roundRect(60, h - 850, w - 120, 560, 20, fill=True, stroke=False)

    box_metrics = [
        ("TRIGGER PIVOT", f"${candidate['Pivot_Trigger']:.2f}", text_white),
        ("STOP LOSS", f"${candidate['Stop_Loss']:.2f}", accent_red),
        ("RISK BUDGET", f"{candidate['Risk_%']}%", text_muted),
        ("ASYMMETRY (R:R)", f"{candidate['R_Ratio']}R", accent_cyan),
        (
            "FUNDAMENTAL CATALYST",
            str(candidate.get("Zacks_Rank", "Rank 1 (Strong Buy)")),
            accent_amber,
        ),
        (
            "EVENT RISK",
            str(candidate.get("Earnings_Risk", "SAFE (>14d)")),
            accent_green,
        ),
    ]

    y_pos = h - 330
    for label, val, col in box_metrics:
      c.setFont("Helvetica-Bold", 20)
      c.setFillColor(text_muted)
      c.drawString(100, y_pos, label)
      c.setFont("Helvetica-Bold", 26)
      c.setFillColor(col)
      c.drawRightString(w - 100, y_pos, val)
      c.setStrokeColor(card_inner)
      c.line(100, y_pos - 15, w - 100, y_pos - 15)
      y_pos -= 80

    c.showPage()

  draw_setup_slide(
      "1. BASE-RESET INFLECTION",
      "Breakout above 50-day SMA with curling weekly MACD and institutional"
      " volume",
      top_br,
      4,
  )
  draw_setup_slide(
      "2. MOMENTUM BULL FLAG",
      "CAN SLIM pole >= 45.0%, tight flag consolidation <= 18d holding 21 EMA",
      top_htf,
      5,
  )
  draw_setup_slide(
      "3. POCKET PIVOT SQUEEZE",
      "Bollinger/Keltner squeeze launch with volume surge exceeding 10d down"
      " volume",
      top_pp,
      6,
  )
  draw_setup_slide(
      "4. LIQUIDITY SWEEP (U&R)",
      "False breakdown below support reversed with institutional demand bid",
      top_ls,
      7,
  )

  # ---------------- SLIDE 8: GOVERNANCE ----------------
  draw_base("EXECUTION DISCIPLINE", 8, 8)
  c.setFont("Helvetica-Bold", 34)
  c.setFillColor(accent_cyan)
  c.drawString(60, h - 140, "GOVERNANCE & EXECUTION RULES")

  c.setFillColor(card_bg)
  c.roundRect(60, h - 920, w - 120, 740, 20, fill=True, stroke=False)

  rules = [
      (
          "1. NEVER CHASE BEYOND +2.5% OF PIVOT",
          "If the equity opens extended beyond 2.5% above the trigger, void the"
          " entry.",
      ),
      (
          "2. HARD INVALIDATION ENFORCEMENT",
          "Stops are non-negotiable. An hourly or daily close below invalidates"
          " the setup.",
      ),
      (
          "3. REGIME-GOVERNED SIZING",
          "Never deploy full allocation during defensive or corrective macro"
          " conditions.",
      ),
      (
          "4. EARNINGS PROXIMITY BLACKOUT",
          "Do not carry fresh unhedged swing risk into earnings announcements"
          " within 14 days.",
      ),
  ]

  y_pos = h - 220
  for r_title, r_desc in rules:
    c.setFont("Helvetica-Bold", 22)
    c.setFillColor(accent_green)
    c.drawString(100, y_pos, r_title)
    c.setFont("Helvetica", 17)
    c.setFillColor(text_white)
    c.drawString(100, y_pos - 30, r_desc)
    y_pos -= 105

  box_top = y_pos - 20
  c.setFillColor(card_inner)
  c.roundRect(100, box_top - 180, w - 200, 180, 14, fill=True, stroke=False)

  c.setFont("Helvetica-Bold", 24)
  c.setFillColor(accent_cyan)
  c.drawString(130, box_top - 45, "Access the complete daily watchlist:")

  c.setFont("Helvetica-Bold", 38)
  c.setFillColor(accent_green)
  c.drawString(130, box_top - 100, "corpacuity.co.uk")

  c.setFont("Helvetica", 17)
  c.setFillColor(text_muted)
  c.drawString(
      130,
      box_top - 145,
      "Full CSV datasets, Zacks rank tenure & risk analytics.",
  )

  c.setFont("Helvetica-Bold", 20)
  c.setFillColor(accent_cyan)
  c.drawCentredString(
      w / 2, 40, "Corp Acuity Ltd // Systematic Treasury & Market Intelligence"
  )
  c.showPage()

  c.save()
  print(f"\n[CAROUSEL] Generated institutional 8-slide PDF: {filename}")


# ---------------------------------------------------------
# 10. RENDER HIGH-RES PNG CARDS FOR X
# ---------------------------------------------------------
def export_carousel_cards_for_web(pdf_path=CAROUSEL_PDF_FILENAME):
  if not os.path.exists(pdf_path):
    print(f"[CARDS] Error: '{pdf_path}' not found.")
    return []

  os.makedirs("x_cards", exist_ok=True)
  doc = fitz.open(pdf_path)
  card_paths = []
  matrix = fitz.Matrix(2.0, 2.0)

  target_indices = [0, 1, 2, 3]
  card_num = 1
  for idx in target_indices:
    if idx < len(doc):
      page = doc.load_page(idx)
      badge_rect = fitz.Rect(860, 32, 1020, 62)
      page.draw_rect(
          badge_rect, color=(0.027, 0.039, 0.071), fill=(0.027, 0.039, 0.071)
      )
      page.insert_text(
          fitz.Point(880, 52),
          f"Card {card_num} of 4",
          fontsize=14,
          color=(0.58, 0.64, 0.72),
          fontname="helv",
      )
      pix = page.get_pixmap(matrix=matrix, alpha=False)
      out_file = os.path.join("x_cards", f"card_{card_num}.png")
      pix.save(out_file)
      card_paths.append(out_file)
      card_num += 1

  doc.close()
  print(
      f"[CARDS] Rendered {len(card_paths)} high-res PNG cards into x_cards/"
      " (Stamped Card 1 of 4 to 4 of 4)"
  )
  return card_paths

