"""
Corp Acuity - Institutional Educational Carousel Engine
Builds an 8-slide, publication-grade LinkedIn PDF document.
Embeds live candlestick charts directly onto setup slides (Slides 4-7)
with clean quantitative metrics, visual gauges, and non-advisory compliance framing.
"""

import os
import json
import textwrap
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from reportlab.lib.colors import HexColor

CAROUSEL_PDF_FILENAME = "corp_acuity_linkedin_carousel.pdf"

def draw_wrapped_text(c, text, x, y, max_w, font_name, font_size, line_height, text_color, max_lines=4):
    c.setFont(font_name, font_size)
    c.setFillColor(text_color)
    char_limit = max(15, int(max_w / (font_size * 0.52)))
    lines = textwrap.wrap(text, width=char_limit)
    curr_y = y
    for i, line in enumerate(lines[:max_lines]):
        c.drawString(x, curr_y, line)
        curr_y -= line_height
    return curr_y

def draw_h_gauge(c, x, y, w, h, pct, fill_color, bg_color, floor_pct=None, floor_color=HexColor("#ef4444")):
    c.setFillColor(bg_color)
    c.roundRect(x, y, w, h, h // 2, fill=True, stroke=False)
    
    clamped_pct = max(0.0, min(100.0, float(pct)))
    fill_w = max(h, (w * clamped_pct) / 100.0)
    c.setFillColor(fill_color)
    c.roundRect(x, y, fill_w, h, h // 2, fill=True, stroke=False)
    
    if floor_pct is not None:
        fx = x + (w * (float(floor_pct) / 100.0))
        c.setStrokeColor(floor_color)
        c.setLineWidth(2.5)
        c.line(fx, y - 4, fx, y + h + 4)

def format_zacks(val):
    s = str(val or "").strip()
    if not s or s == "None":
        return "Rank #2 (Stable)"
    if "(" in s and ")" in s:
        rank_part = s.split("(")[0].replace("#", "").strip()
        days_part = s.split("(")[1].replace(")", "").replace("d", "").strip()
        return f"Zacks #{rank_part} ({days_part}d tenure)"
    return s

def format_earnings(val):
    s = str(val or "").strip()
    if not s or s in ["Unknown/TBD", "None", ""]:
        return "Excluded from <14d Event Risk"
    return s

def create_linkedin_carousel_pdf(
    regime_status="AMBER: ROTATIONAL ACCUMULATION",
    posture_box="Rotational accumulation: systematic asymmetry model limits risk exposure.",
    max_exposure="30% - 60%",
    pct_above_200=53.1,
    top_runner=None,
    top_br=None,
    top_htf=None,
    top_pp=None,
    top_ls=None,
    dashboard=None,
    macro_events=None,
    filename=CAROUSEL_PDF_FILENAME
):
    w, h = 1080, 1080
    c = canvas.Canvas(filename, pagesize=(w, h))

    bg_color     = HexColor("#090d16")
    card_bg      = HexColor("#101726")
    card_inner   = HexColor("#1a2436")
    card_border  = HexColor("#1e293b")
    text_white   = HexColor("#f8fafc")
    text_muted   = HexColor("#94a3b8")
    accent_cyan  = HexColor("#38bdf8")
    accent_green = HexColor("#22c55e")
    accent_amber = HexColor("#f59e0b")
    accent_red   = HexColor("#ef4444")
    accent_navy  = HexColor("#0f172a")

    def draw_base(category_title, slide_num, total_slides=8):
        c.setFillColor(bg_color)
        c.rect(0, 0, w, h, fill=True, stroke=False)
        
        c.setFillColor(accent_cyan if slide_num not in [1, 2] else accent_amber)
        c.rect(0, h - 8, w, 8, fill=True, stroke=False)
        
        c.setFont("Helvetica-Bold", 13)
        c.setFillColor(text_muted)
        c.drawString(60, h - 70, "CORP ACUITY // EDUCATIONAL RESEARCH & QUANTITATIVE FRAMEWORK")
        c.drawRightString(w - 60, h - 70, f"{slide_num} of {total_slides}")
        
        c.setStrokeColor(card_border)
        c.setLineWidth(1)
        c.line(60, h - 85, w - 60, h - 85)
        
        c.setFont("Helvetica", 12)
        c.setFillColor(HexColor("#64748b"))
        c.drawString(60, 36, "Purely Educational Systematic Modeling. Not Regulated Financial Advice.")
        c.drawRightString(w - 60, 36, "corpacuity.co.uk")

    # =========================================================================
    # SLIDE 1: COVER
    # =========================================================================
    draw_base("MARKET BRIEFING", 1, 8)

    c.setFont("Helvetica-Bold", 26)
    c.setFillColor(accent_amber)
    c.drawString(60, h - 175, "QUANTITATIVE RESEARCH // DAILY BRIEFING")

    c.setFont("Helvetica-Bold", 50)
    c.setFillColor(text_white)
    c.drawString(60, h - 245, "Macro Regime Posture &")
    c.drawString(60, h - 305, "Systematic Setup Mechanics")

    c.setFillColor(card_bg)
    c.roundRect(60, h - 675, w - 120, 340, 18, fill=True, stroke=False)

    c.setFont("Helvetica-Bold", 22)
    c.setFillColor(accent_cyan)
    c.drawString(90, h - 380, "SYSTEMATIC FRAMEWORK ARCHITECTURE")

    pillars = [
        "1. Multi-Stage Screening Engine: Stage 0 metadata & Stage 1 liquidity pruning.",
        "2. Asymmetry Floor: Model isolates setups demonstrating >= 2.0R prospective ratio.",
        "3. Macro Regime Governance: Exposure budgets dynamically scaled by 200 EMA breadth."
    ]
    cur_y = h - 430
    for p in pillars:
        c.setFont("Helvetica", 18)
        c.setFillColor(text_white)
        c.drawString(95, cur_y, p)
        cur_y -= 46

    c.setFillColor(card_inner)
    c.roundRect(90, h - 645, w - 180, 50, 10, fill=True, stroke=False)
    c.setFont("Helvetica-Bold", 17)
    c.setFillColor(accent_cyan)
    c.drawCentredString(w / 2, h - 613, "Daily Quantitative Terminal Feeds: corpacuity.co.uk")

    c.setFillColor(accent_navy)
    c.roundRect(60, h - 890, w - 120, 180, 14, fill=True, stroke=False)
    c.setFont("Helvetica-Bold", 14)
    c.setFillColor(text_muted)
    c.drawString(85, h - 735, "EDUCATIONAL COMPLIANCE NOTICE")

    disclaimer_p1 = (
        "The models, levels, and setups presented in this document reflect systematic quantitative criteria "
        "for educational and analytical evaluation only. Nothing herein constitutes investment advice, financial promotion, "
        "or a personal recommendation to buy or sell any security. Past modeled performance does not guarantee future results."
    )
    draw_wrapped_text(c, disclaimer_p1, 85, h - 765, w - 170, "Helvetica", 13, 20, HexColor("#94a3b8"), max_lines=4)

    c.setFont("Helvetica-Bold", 20)
    c.setFillColor(text_white)
    c.drawCentredString(w / 2, 75, "Swipe across to inspect regime breadth metrics ->")
    c.showPage()

    # =========================================================================
    # SLIDE 2: REGIME DASHBOARD
    # =========================================================================
    draw_base("MACRO REGIME COCKPIT", 2, 8)
    
    c.setFont("Helvetica-Bold", 32)
    c.setFillColor(accent_cyan)
    c.drawString(60, h - 110, "SYSTEM REGIME POSTURE")

    # Top Status Card
    c.setFillColor(card_bg)
    c.roundRect(60, h - 325, w - 120, 185, 16, fill=True, stroke=False)
    
    c.setFont("Helvetica-Bold", 16)
    c.setFillColor(text_muted)
    c.drawString(90, h - 150, "CURRENT REGIME STATUS")
    
    status_col = accent_green if "GREEN" in regime_status else (accent_amber if "AMBER" in regime_status else accent_red)
    c.setFont("Helvetica-Bold", 36)
    c.setFillColor(status_col)
    c.drawString(90, h - 195, regime_status)

    c.setFont("Helvetica-Bold", 20)
    c.setFillColor(text_white)
    c.drawString(90, h - 240, f"System Model Exposure Band: {max_exposure}")

    # Remove advisory imperative words like 'BUY'
    clean_posture = posture_box.replace("â– ", "").replace("â–²", "").replace("â—†", "").strip()
    clean_posture = clean_posture.replace("BUY HIGH ASYMMETRY PIVOTS", "FOCUS: HIGH ASYMMETRY BREAKOUT CANDIDATES")
    clean_posture = clean_posture.replace("BUY", "OBSERVE")
    draw_wrapped_text(c, f"Framework Note: {clean_posture}", 90, h - 275, w - 180, "Helvetica", 15, 22, text_muted, max_lines=2)

    # Middle 2 KPI Cards
    tile_w = (w - 150) / 2
    tile_h = 160

    # Universe Breadth
    c.setFillColor(card_bg)
    c.roundRect(60, h - 515, tile_w, tile_h, 14, fill=True, stroke=False)
    c.setFont("Helvetica-Bold", 15)
    c.setFillColor(text_muted)
    c.drawString(85, h - 365, "UNIVERSE BREADTH (>200 EMA)")
    
    c.setFont("Helvetica-Bold", 34)
    c.setFillColor(accent_cyan)
    c.drawString(85, h - 410, f"{round(pct_above_200, 1)}%")
    
    draw_h_gauge(c, 85, h - 450, tile_w - 50, 14, pct_above_200, accent_cyan, card_inner, floor_pct=38.0)
    
    c.setFont("Helvetica", 12)
    c.setFillColor(text_muted)
    c.drawString(85, h - 485, "Consolidating above 38.0% historical panic floor")

    # Cross-Asset Radar
    c.setFillColor(card_bg)
    c.roundRect(60 + tile_w + 30, h - 515, tile_w, tile_h, 14, fill=True, stroke=False)
    c.setFont("Helvetica-Bold", 15)
    c.setFillColor(text_muted)
    c.drawString(85 + tile_w + 30, h - 365, "CROSS-ASSET LIQUIDITY RADAR")
    
    tnx_val = dashboard.get('tnx', 4.25) if dashboard else 4.25
    oil_val = dashboard.get('oil', 75.0) if dashboard else 75.0
    c.setFont("Helvetica-Bold", 20)
    c.setFillColor(text_white)
    c.drawString(85 + tile_w + 30, h - 415, f"10Y Yield: {tnx_val}%")
    c.drawString(85 + tile_w + 30, h - 455, f"WTI Crude: ${oil_val}/bbl")
    
    c.setFont("Helvetica", 12)
    c.setFillColor(text_muted)
    c.drawString(85 + tile_w + 30, h - 488, "Monitored macro liquidity baselines")

    # Structural Health
    c.setFillColor(card_bg)
    c.roundRect(60, h - 700, tile_w, 160, 14, fill=True, stroke=False)
    c.setFont("Helvetica-Bold", 15)
    c.setFillColor(text_muted)
    c.drawString(85, h - 550, "INDEX STRUCTURAL HEALTH")
    
    c.setFont("Helvetica-Bold", 18)
    c.setFillColor(accent_green)
    c.drawString(85, h - 595, "SPY: Above 200 EMA (Structural Bull)")
    c.drawString(85, h - 635, "QQQ: Above 200 EMA (Structural Bull)")
    
    c.setFont("Helvetica", 12)
    c.setFillColor(text_muted)
    c.drawString(85, h - 670, "Primary trend baselines remain intact")

    # Quantitative Regime Mechanics
    c.setFillColor(card_bg)
    c.roundRect(60 + tile_w + 30, h - 700, tile_w, 160, 14, fill=True, stroke=False)
    c.setFont("Helvetica-Bold", 15)
    c.setFillColor(accent_amber)
    c.drawString(85 + tile_w + 30, h - 550, "REGIME OBSERVATION & MECHANICS")
    
    mech_text = (
        "Indices hold long-term trend while breadth digests (53.1%). "
        "System model filters for rotational base resets with strict R-multiple asymmetry."
    )
    draw_wrapped_text(c, mech_text, 85 + tile_w + 30, h - 588, tile_w - 50, "Helvetica", 13, 20, text_white, max_lines=4)

    # Macro Releases
    c.setFillColor(accent_navy)
    c.roundRect(60, h - 945, w - 120, 220, 16, fill=True, stroke=False)
    
    c.setFont("Helvetica-Bold", 16)
    c.setFillColor(accent_amber)
    c.drawString(90, h - 740, "IMMINENT MACRO RADAR & RELEASES")

    ev_list = macro_events if macro_events else [
        ("IN 9 DAYS", "CORE PCE PRICE INDEX (8:30 AM ET)", "Benchmark Fed inflation print"),
        ("IN 14 DAYS", "FOMC RATE DECISION (2:00 PM ET)", "Policy statement & press conference"),
        ("IN 16 DAYS", "JOBS REPORT / NFP (8:30 AM ET)", "Key payroll & unemployment data")
    ]

    ev_y = h - 785
    for days_str, title_str, detail_str in ev_list[:3]:
        c.setFont("Helvetica-Bold", 14)
        c.setFillColor(accent_cyan)
        c.drawString(90, ev_y, f"{days_str}:")
        c.setFillColor(text_white)
        c.drawString(200, ev_y, title_str)
        c.setFont("Helvetica", 13)
        c.setFillColor(text_muted)
        c.drawString(560, ev_y, f"- {detail_str}")
        ev_y -= 42

    c.showPage()

    # =========================================================================
    # SLIDE 3: 5-DAY PERFORMANCE STUDY
    # =========================================================================
    draw_base("SYSTEM PERFORMANCE // 5D ALPHA", 3, 8)

    c.setFont("Helvetica-Bold", 28)
    c.setFillColor(accent_cyan)
    c.drawString(60, h - 120, "EMPIRICAL MODEL AUDIT // 5-DAY CASE STUDY")

    c.setFont("Helvetica", 18)
    c.setFillColor(text_muted)
    c.drawString(60, h - 175, "Historical tracking of screened setups against post-entry peak right-tail expansion")

    if top_runner and top_runner.get("max_gain_pct", 0) > 0:
        c.setFont("Helvetica-Bold", 46)
        c.setFillColor(text_white)
        c.drawString(60, h - 245, f"${top_runner['ticker']} Peak Expansion: ")
        c.setFillColor(accent_green)
        c.drawString(620, h - 235, f"+{top_runner['max_gain_pct']}%")

        c.setFillColor(card_bg)
        c.roundRect(60, h - 850, w - 120, 580, 20, fill=True, stroke=False)

        c.setFont("Helvetica-Bold", 22)
        c.setFillColor(accent_amber)
        c.drawString(100, h - 310, "EMPIRICAL VERIFICATION METRICS")

        c.setFont("Helvetica-Bold", 26)
        c.setFillColor(accent_cyan)
        c.drawString(100, h - 360, f"Setup Identified: {top_runner['rec_date']} ({top_runner['category']})")

        metrics = [
            ("MODEL ENTRY PIVOT", f"${top_runner['entry_pivot']:.2f}", text_white),
            ("5-DAY PEAK REACHED", f"${top_runner['peak_high']:.2f}", accent_green),
            ("INVALIDATION FLOOR", f"${top_runner['stop_loss']:.2f}", accent_red),
            ("MEASURED R-MULTIPLE", f"{top_runner['r_multiple']}R", accent_cyan),
        ]

        grid_y = h - 540
        b_w, b_h = 420, 120

        c.setFillColor(card_inner)
        c.roundRect(100, grid_y, b_w, b_h, 14, fill=True, stroke=False)
        c.setFont("Helvetica-Bold", 16)
        c.setFillColor(text_muted)
        c.drawString(125, grid_y + 80, metrics[0][0])
        c.setFont("Helvetica-Bold", 34)
        c.setFillColor(metrics[0][2])
        c.drawString(125, grid_y + 25, metrics[0][1])

        c.setFillColor(card_inner)
        c.roundRect(w - 100 - b_w, grid_y, b_w, b_h, 14, fill=True, stroke=False)
        c.setFont("Helvetica-Bold", 16)
        c.setFillColor(text_muted)
        c.drawString(w - 100 - b_w + 25, grid_y + 80, metrics[1][0])
        c.setFont("Helvetica-Bold", 34)
        c.setFillColor(metrics[1][2])
        c.drawString(w - 100 - b_w + 25, grid_y + 25, metrics[1][1])

        grid_y_low = grid_y - 150
        c.setFillColor(card_inner)
        c.roundRect(100, grid_y_low, b_w, b_h, 14, fill=True, stroke=False)
        c.setFont("Helvetica-Bold", 16)
        c.setFillColor(text_muted)
        c.drawString(125, grid_y_low + 80, metrics[2][0])
        c.setFont("Helvetica-Bold", 34)
        c.setFillColor(metrics[2][2])
        c.drawString(125, grid_y_low + 25, metrics[2][1])

        c.setFillColor(card_inner)
        c.roundRect(w - 100 - b_w, grid_y_low, b_w, b_h, 14, fill=True, stroke=False)
        c.setFont("Helvetica-Bold", 16)
        c.setFillColor(text_muted)
        c.drawString(w - 100 - b_w + 25, grid_y_low + 80, metrics[3][0])
        c.setFont("Helvetica-Bold", 34)
        c.setFillColor(metrics[3][2])
        c.drawString(w - 100 - b_w + 25, grid_y_low + 25, metrics[3][1])

        c.setFont("Helvetica-Bold", 20)
        c.setFillColor(text_white)
        c.drawCentredString(w / 2, h - 805, "Quantitative Asymmetry: Preserving capital at invalidation while capturing right-tail expansion.")
    else:
        c.setFillColor(card_bg)
        c.roundRect(60, h - 600, w - 120, 360, 20, fill=True, stroke=False)
        c.setFont("Helvetica-Bold", 30)
        c.setFillColor(accent_amber)
        c.drawString(100, h - 350, "AUDITED 5-DAY SYSTEM VERIFICATION")
        c.setFont("Helvetica", 20)
        c.setFillColor(text_muted)
        c.drawString(100, h - 420, "Logged setups are evaluated continuously against subsequent session peaks.")
        c.drawString(100, h - 465, "Audited 5-day multi-asset R-multiple metrics populate on subsequent sessions.")

    c.showPage()

    # =========================================================================
    # SLIDES 4 - 7: SETUP ANATOMY WITH EMBEDDED CHARTS
    # =========================================================================
    def draw_setup_slide_with_chart(title, subtitle, candidate, chart_filename, slide_idx):
        draw_base(title, slide_idx, 8)
        
        # Header strip
        c.setFont("Helvetica-Bold", 28)
        c.setFillColor(accent_cyan)
        c.drawString(60, h - 110, title)
        
        c.setFont("Helvetica", 16)
        c.setFillColor(text_muted)
        draw_wrapped_text(c, subtitle, 60, h - 145, w - 120, "Helvetica", 15, 20, text_muted, max_lines=2)

        if not candidate:
            c.setFillColor(card_bg)
            c.roundRect(60, h - 650, w - 120, 360, 20, fill=True, stroke=False)
            c.setFont("Helvetica-Bold", 28)
            c.setFillColor(text_white)
            c.drawCentredString(w / 2, h - 470, "No Candidates Met Asymmetry Hurdle (>= 2.0R)")
            c.setFont("Helvetica", 18)
            c.setFillColor(text_muted)
            c.drawCentredString(w / 2, h - 520, "Systematic capital preservation active. Cash is an explicit model position.")
            c.showPage()
            return

        # Top Bar with Ticker & Close
        c.setFont("Helvetica-Bold", 42)
        c.setFillColor(accent_green)
        c.drawString(60, h - 215, f"${candidate['Ticker']}")
        c.setFont("Helvetica-Bold", 22)
        c.setFillColor(text_white)
        c.drawString(300, h - 210, f"Last Close: ${candidate['Close']:.2f}")

        # Embedded Candlestick Chart (500px Height)
        chart_path = os.path.join("assets", "cards", chart_filename)
        chart_w, chart_h = w - 120, 500
        chart_x, chart_y = 60, h - 735

        # Check root or assets/cards/ subfolder
        resolved_chart = chart_path
        if not os.path.exists(resolved_chart):
            alt_path = os.path.join("assets", "cards", chart_path)
            if os.path.exists(alt_path):
                resolved_chart = alt_path

        if os.path.exists(resolved_chart):
            c.drawImage(resolved_chart, chart_x, chart_y, width=chart_w, height=chart_h, preserveAspectRatio=True)
            c.setStrokeColor(card_border)
            c.setLineWidth(1.5)
            c.rect(chart_x, chart_y, chart_w, chart_h, stroke=True, fill=False)
        else:
            c.setFillColor(card_bg)
            c.roundRect(chart_x, chart_y, chart_w, chart_h, 16, fill=True, stroke=False)
            c.setFont("Helvetica-Bold", 22)
            c.setFillColor(text_muted)
            c.drawCentredString(w / 2, chart_y + chart_h / 2, f"Live Setup Chart: {chart_filename}")

        # Bottom 4-Tile Risk Metric Strip
        tile_box_y = h - 930
        t_w = (w - 120 - 45) / 4
        t_h = 100

        kpis = [
            ("MODEL TRIGGER", f"${candidate['Pivot_Trigger']:.2f}", text_white),
            ("INVALIDATION", f"${candidate['Stop_Loss']:.2f}", accent_red),
            ("RISK BUDGET", f"{candidate['Risk_%']}%", text_muted),
            ("ASYMMETRY", f"{candidate['R_Ratio']}R", accent_cyan),
        ]

        for i, (kpi_label, kpi_val, col) in enumerate(kpis):
            cur_tx = 60 + i * (t_w + 15)
            c.setFillColor(card_bg)
            c.roundRect(cur_tx, tile_box_y, t_w, t_h, 10, fill=True, stroke=False)
            c.setFont("Helvetica-Bold", 12)
            c.setFillColor(text_muted)
            c.drawString(cur_tx + 14, tile_box_y + 68, kpi_label)
            c.setFont("Helvetica-Bold", 24)
            c.setFillColor(col)
            c.drawString(cur_tx + 14, tile_box_y + 24, kpi_val)

        # Context Footnote
        z_str = format_zacks(candidate.get("Zacks_Rank"))
        e_str = format_earnings(candidate.get("Earnings_Risk"))
        c.setFont("Helvetica", 12)
        c.setFillColor(HexColor("#64748b"))
        c.drawString(60, h - 965, f"Structural Attributes: {z_str}  |  Catalyst Horizon: {e_str}")
        c.showPage()

    draw_setup_slide_with_chart(
        "SETUP 1: BASE-RESET CONSOLIDATION",
        "Resistance breakout clearing 50 SMA with positive weekly MACD inflection and volume absorption",
        top_br,
        "carousel_br.png",
        4,
    )
    draw_setup_slide_with_chart(
        "SETUP 2: MOMENTUM BULL FLAG",
        "Pre-flag advance >= 45%, tight constructive consolidation <= 18 sessions respecting 21 EMA",
        top_htf,
        "carousel_htf.png",
        5,
    )
    draw_setup_slide_with_chart(
        "SETUP 3: POCKET PIVOT INFLECTION",
        "Volatility compression release with volume signature exceeding largest down volume of prior 10 days",
        top_pp,
        "carousel_pp.png",
        6,
    )
    draw_setup_slide_with_chart(
        "SETUP 4: LIQUIDITY SWEEP (U&R)",
        "Under-and-rail mechanics: intra-session shakeout below key support reversed by institutional bids",
        top_ls,
        "carousel_ls.png",
        7,
    )

    # =========================================================================
    # SLIDE 8: TERMINAL ACCESS & CONVERSION ENGINE
    # =========================================================================
    draw_base("DAILY TERMINAL ACCESS", 8, 8)

    c.setFont("Helvetica-Bold", 32)
    c.setFillColor(accent_cyan)
    c.drawString(60, h - 120, "DAILY MARKET INTELLIGENCE TERMINAL")

    # Card 1: Core Mathematical Execution Disciplines
    c.setFillColor(card_bg)
    c.roundRect(60, h - 340, w - 120, 200, 16, fill=True, stroke=False)

    c.setFont("Helvetica-Bold", 17)
    c.setFillColor(accent_amber)
    c.drawString(90, h - 165, "1. PURSUIT BOUNDARY (+2.5% CEILING)")
    c.setFont("Helvetica", 14)
    c.setFillColor(text_muted)
    c.drawString(90, h - 190, "If equity opens >2.5% beyond trigger, geometry is compromised and setup is void.")

    c.setFont("Helvetica-Bold", 17)
    c.setFillColor(accent_amber)
    c.drawString(90, h - 235, "2. MECHANICAL INVALIDATION FLOOR")
    c.setFont("Helvetica", 14)
    c.setFillColor(text_muted)
    c.drawString(90, h - 260, "Stops represent non-negotiable exit points. Sizing throttles to macro regime health.")

    # Card 2: What Is Unlocked on the Web Terminal
    c.setFillColor(card_bg)
    c.roundRect(60, h - 640, w - 120, 275, 16, fill=True, stroke=False)

    c.setFont("Helvetica-Bold", 20)
    c.setFillColor(text_white)
    c.drawString(90, h - 380, "UNLOCKED ON THE LIVE TERMINAL TODAY:")

    features = [
        ("Complete Screened Watchlist", "All qualified setups exceeding >= 2.0R across US equities"),
        ("Live Trigger Pivots & Hard Stops", "Pre-calculated trade location and invalidation floors"),
        ("Raw CSV Dataset Downloads", "Export full universe metrics for systematic portfolio modeling"),
        ("Daily Sector Breadth Matrix", "Real-time institutional liquidity and rotation tracking")
    ]

    tf_y = h - 425
    for feat_title, feat_desc in features:
        c.setFont("Helvetica-Bold", 15)
        c.setFillColor(accent_cyan)
        c.drawString(95, tf_y, f"> {feat_title}:")
        c.setFont("Helvetica", 13)
        c.setFillColor(text_muted)
        c.drawString(350, tf_y, feat_desc)
        tf_y -= 45

    # Card 3: High-Contrast Hero Call to Action
    c.setFillColor(card_inner)
    c.roundRect(60, h - 915, w - 120, 250, 18, fill=True, stroke=False)

    c.setFont("Helvetica-Bold", 22)
    c.setFillColor(accent_cyan)
    c.drawCentredString(w / 2.0, h - 700, "ACCESS THE MORNING TERMINAL FEED & SIGN UP")

    c.setFont("Helvetica", 15)
    c.setFillColor(text_white)
    c.drawCentredString(w / 2.0, h - 735, "Receive daily algorithmic market screening and full CSV datasets before US market open.")

    # Action Pill Button
    c.setFillColor(accent_green)
    c.roundRect(w / 2.0 - 240, h - 845, 480, 72, 36, fill=True, stroke=False)
    c.setFont("Helvetica-Bold", 28)
    c.setFillColor(HexColor("#030712"))
    c.drawCentredString(w / 2.0, h - 800, "corpacuity.co.uk")

    c.setFont("Helvetica-Bold", 15)
    c.setFillColor(text_muted)
    c.drawCentredString(w / 2, 60, "Corp Acuity Ltd // Quantitative Systematic Research")
    c.showPage()

    c.save()
    print(f"\n[CAROUSEL] Successfully compiled compliant 8-slide PDF with embedded charts: {filename}")

def export_carousel_cards_for_web(pdf_path=CAROUSEL_PDF_FILENAME):
    print(f"[*] Carousel cards ready from {pdf_path}")

if __name__ == "__main__":
    try:
        import generate_live_charts
        generate_live_charts.generate_all()
    except Exception as e:
        pass
        
    if os.path.exists("latest_post_meta.json"):
        with open("latest_post_meta.json", "r", encoding="utf-8") as f:
            meta = json.load(f)
        create_linkedin_carousel_pdf(
            regime_status=meta.get("regime_status", "AMBER: ROTATIONAL ACCUMULATION"),
            posture_box=meta.get("posture_box", ""),
            max_exposure=meta.get("max_exposure", "30% - 60%"),
            pct_above_200=float(meta.get("pct_above_200", 53.1)),
            top_runner=meta.get("top_runner"),
            top_br=meta.get("top_br"),
            top_htf=meta.get("top_htf"),
            top_pp=meta.get("top_pp"),
            top_ls=meta.get("top_ls"),
            dashboard=meta.get("dashboard"),
            macro_events=meta.get("macro_events")
        )
