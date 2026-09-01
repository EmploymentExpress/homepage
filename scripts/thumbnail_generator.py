#!/usr/bin/env python3
"""
Professional Dynamic Job Thumbnail Generator for EmploymentExpress
Generates publication-quality 1200x630 Open Graph & Social Share thumbnail cards
with 2x super-sampling, dynamic text fitting, official YouTube channel branding,
role/department-specific AI imagery, and a 100% scannable WhatsApp Channel QR Code.
"""

import os
import sys
import re
import json
import argparse
from pathlib import Path
import qrcode
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageOps

ROOT_DIR = Path(__file__).resolve().parent.parent
ASSETS_DIR = ROOT_DIR / "assets"
VISUALS_DIR = ASSETS_DIR / "visuals"
THUMBNAIL_DIR = ASSETS_DIR / "thumbnails"

FONT_BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
FONT_REG = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
FONT_SERIF_BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf"

WHATSAPP_CHANNEL_URL = "https://whatsapp.com/channel/0029Va9xQHV4tRrxpVKaG93w"


def get_font(path, size):
    """Loads a TrueType font with robust fallback."""
    try:
        return ImageFont.truetype(path, int(size))
    except Exception:
        return ImageFont.load_default()


def fit_text_font(draw, text, max_w, max_h, font_path=FONT_BOLD, start_size=80, min_size=32):
    """Dynamically calculates the largest font size that fits inside (max_w, max_h)."""
    size = start_size
    while size >= min_size:
        font = get_font(font_path, size)
        bbox = draw.textbbox((0, 0), text, font=font)
        w = bbox[2] - bbox[0]
        h = bbox[3] - bbox[1]
        if w <= max_w and h <= max_h:
            return font
        size -= 3
    return get_font(font_path, min_size)


def draw_rounded_rect(draw, bbox, radius, fill=None, outline=None, width=1):
    """Draws a smooth rounded rectangle."""
    draw.rounded_rectangle(bbox, radius=radius, fill=fill, outline=outline, width=width)


def make_circular_masked_image(img_path, size):
    """Loads an image, crops it square, and returns a circular masked RGBA image."""
    try:
        im = Image.open(img_path).convert("RGBA")
        w, h = im.size
        min_dim = min(w, h)
        left = (w - min_dim) // 2
        top = (h - min_dim) // 2
        im = im.crop((left, top, left + min_dim, top + min_dim))
        im = im.resize((size, size), Image.Resampling.LANCZOS)
        
        mask = Image.new("L", (size, size), 0)
        mask_draw = ImageDraw.Draw(mask)
        mask_draw.ellipse([0, 0, size, size], fill=255)
        
        output = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        output.paste(im, (0, 0), mask=mask)
        return output
    except Exception as e:
        print(f"Error loading circular image {img_path}: {e}")
        return None


def get_whatsapp_qr_code_image(box_size=2, border=2):
    """
    Generates a pixel-perfect, crisp, 100% scannable QR Code for the official WhatsApp Channel.
    Uses integer module sizing (box_size=2, border=2 -> 74x74 px) to guarantee rapid optical scanning.
    """
    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=box_size,
        border=border,
    )
    qr.add_data(WHATSAPP_CHANNEL_URL)
    qr.make(fit=True)
    return qr.make_image(fill_color="black", back_color="white").convert("RGB")


def resolve_visual_path(visual_key_or_path, job_title="", job_dept=""):
    """
    Intelligently determines the best visual image to use:
    - If a specific key or file path is supplied, uses it.
    - Otherwise auto-detects from job title and department keywords.
    """
    if visual_key_or_path:
        p = Path(visual_key_or_path)
        if p.exists():
            return p
        vk_path = VISUALS_DIR / f"{visual_key_or_path}.png"
        if vk_path.exists():
            return vk_path
        vk_path_jpg = VISUALS_DIR / f"{visual_key_or_path}.jpg"
        if vk_path_jpg.exists():
            return vk_path_jpg

    combined = f"{job_title} {job_dept}".lower()
    
    if any(k in combined for k in ["police", "constable", "sub inspector", "si recruitment", "head constable"]):
        return VISUALS_DIR / "police.png"
    elif any(k in combined for k in ["india post", "department of post", "dak sevak", "gds", "postman", "mail guard", "postal", "gramin dak"]):
        return VISUALS_DIR / "postman.png"
    elif any(k in combined for k in ["doctor", "medical", "nurse", "health", "aiims", "surgeon", "pharmacist"]):
        return VISUALS_DIR / "doctor.png"
    elif any(k in combined for k in ["high court", "court", "judicial", "driver", "mali", "safai sewak", "clerk in court"]):
        return VISUALS_DIR / "high_court_building.png"
    elif any(k in combined for k in ["teacher", "professor", "lecturer", "master cadre", "ett", "tgt", "pgt"]):
        return VISUALS_DIR / "teacher.png"
    elif any(k in combined for k in ["clerk", "steno", "assistant", "data entry", "office"]):
        return VISUALS_DIR / "clerk_office.png"
    elif any(k in combined for k in ["ssc", "chte", "translator", "secretariat"]):
        if (VISUALS_DIR / "ssc_building.png").exists():
            return VISUALS_DIR / "ssc_building.png"
        return VISUALS_DIR / "student_aspirant.png"
    
    if (VISUALS_DIR / "student_aspirant.png").exists():
        return VISUALS_DIR / "student_aspirant.png"
    return ASSETS_DIR / "student_aspirant.png"


def composite_job_visual(canvas, visual_path, x1=1260, y1=36, x2=2352, y2=584, department_name="GOVERNMENT OF INDIA"):
    """
    Composites the chosen role-specific visual (Postman, Police, Doctor, Building, etc.)
    at 2x scale with rounded framing and appropriate overlays.
    """
    target_w = x2 - x1
    target_h = y2 - y1
    
    if visual_path and Path(visual_path).exists():
        try:
            im = Image.open(visual_path).convert("RGB")
            im_w, im_h = im.size
            
            target_aspect = target_w / target_h
            im_aspect = im_w / im_h
            
            if im_aspect > target_aspect:
                new_w = int(im_h * target_aspect)
                left = (im_w - new_w) // 2
                cropped = im.crop((left, 0, left + new_w, im_h))
            else:
                new_h = int(im_w / target_aspect)
                top = int((im_h - new_h) * 0.22)
                top = max(0, min(top, im_h - new_h))
                cropped = im.crop((0, top, im_w, top + new_h))
                
            resized = cropped.resize((target_w, target_h), Image.Resampling.LANCZOS)
            
            mask = Image.new("L", (target_w, target_h), 0)
            mdraw = ImageDraw.Draw(mask)
            mdraw.rounded_rectangle([0, 0, target_w, target_h], radius=20, fill=255)
            
            canvas.paste(resized, (x1, y1), mask=mask)
            
            draw = ImageDraw.Draw(canvas)
            draw.rounded_rectangle([x1, y1, x2, y2], radius=20, outline="#cbd5e1", width=4)
            
            if "student_aspirant" in str(visual_path):
                desk_y = y2 - 24
                book_x1 = x2 - 370
                book_x2 = x2 - 20
                
                draw.rectangle([book_x1 - 20, desk_y - 40, book_x2, desk_y], fill="#15803d", outline="#14532d", width=2)
                font_book = get_font(FONT_BOLD, 18)
                draw.text((book_x1 + 165, desk_y - 20), "PRACTICE & USAGE", font=font_book, fill="#ffffff", anchor="mm")
                
                draw.rectangle([book_x1 - 10, desk_y - 80, book_x2 - 10, desk_y - 42], fill="#1e3a8a", outline="#172554", width=2)
                draw.text((book_x1 + 170, desk_y - 60), "TRANSLATION THEORY", font=font_book, fill="#ffffff", anchor="mm")
                
                draw.rectangle([book_x1, desk_y - 120, book_x2 - 20, desk_y - 82], fill="#d97706", outline="#78350f", width=2)
                draw.text((book_x1 + 165, desk_y - 100), "GENERAL HINDI / VYAKARAN", font=font_book, fill="#ffffff", anchor="mm")
                
            return
        except Exception as e:
            print(f"Failed to composite visual photo: {e}")
            
    # Fallback to architectural plate
    draw = ImageDraw.Draw(canvas)
    draw.rounded_rectangle([x1, y1, x2, y2], radius=20, fill="#0f172a", outline="#f59e0b", width=4)
    
    cx = (x1 + x2) // 2
    draw.polygon([(cx, y1 + 50), (x1 + 60, y1 + 140), (x2 - 60, y1 + 140)], fill="#d97706", outline="#facc15", width=3)
    
    p_step = (target_w - 200) // 4
    for i in range(4):
        px = x1 + 100 + i * p_step
        draw.rectangle([px, y1 + 150, px + 40, y2 - 90], fill="#e2e8f0", outline="#94a3b8", width=2)
        draw.rectangle([px - 6, y1 + 140, px + 46, y1 + 152], fill="#f59e0b")
        draw.rectangle([px - 8, y2 - 92, px + 48, y2 - 80], fill="#f59e0b")
        
    draw.rounded_rectangle([x1 + 40, y2 - 76, x2 - 40, y2 - 20], radius=10, fill="#1e3a8a", outline="#facc15", width=2)
    font_plaque = get_font(FONT_BOLD, 22)
    dept_label = department_name[:38].upper()
    draw.text((cx, y2 - 48), dept_label, font=font_plaque, fill="#ffffff", anchor="mm")


def draw_icon_circle(draw, cx, cy, radius, bg_color, icon_type="doc"):
    """Draws crisp circular vector icon badge at 2x scale."""
    draw.ellipse([cx - radius, cy - radius, cx + radius, cy + radius], fill=bg_color, outline="#ffffff", width=4)
    
    if icon_type == "doc":
        draw.rectangle([cx - 18, cy - 24, cx + 18, cy + 24], fill="#ffffff", outline="#1e293b", width=2)
        draw.line([(cx - 10, cy - 10), (cx + 10, cy - 10)], fill=bg_color, width=4)
        draw.line([(cx - 10, cy), (cx + 10, cy)], fill=bg_color, width=4)
        draw.line([(cx - 10, cy + 10), (cx + 4, cy + 10)], fill=bg_color, width=4)
    elif icon_type == "users":
        draw.ellipse([cx - 10, cy - 16, cx + 10, cy - 2], fill="#ffffff")
        draw.chord([cx - 20, cy, cx + 20, cy + 24], start=180, end=360, fill="#ffffff")
    elif icon_type == "calendar":
        draw.rectangle([cx - 20, cy - 18, cx + 20, cy + 22], fill="#ffffff", outline="#1e293b", width=2)
        draw.rectangle([cx - 20, cy - 18, cx + 20, cy - 6], fill="#dc2626")
        draw.line([(cx - 10, cy - 24), (cx - 10, cy - 16)], fill="#ffffff", width=4)
        draw.line([(cx + 10, cy - 24), (cx + 10, cy - 16)], fill="#ffffff", width=4)
        draw.ellipse([cx - 6, cy + 4, cx + 6, cy + 14], fill=bg_color)
    elif icon_type == "target":
        draw.ellipse([cx - 24, cy - 24, cx + 24, cy + 24], fill="#ffffff", outline=bg_color, width=4)
        draw.ellipse([cx - 14, cy - 14, cx + 14, cy + 14], fill=bg_color, outline="#ffffff", width=2)
        draw.ellipse([cx - 6, cy - 6, cx + 6, cy + 6], fill="#ffffff")


def draw_whatsapp_badge(draw, cx, cy, radius):
    """Draws vector WhatsApp icon with green circular base and speech bubble at 2x scale."""
    draw.ellipse([cx - radius, cy - radius, cx + radius, cy + radius], fill="#25D366", outline="#ffffff", width=3)
    
    # White speech bubble
    tail_pts = [
        (cx - int(radius * 0.45), cy + int(radius * 0.3)),
        (cx - int(radius * 0.75), cy + int(radius * 0.75)),
        (cx - int(radius * 0.15), cy + int(radius * 0.55))
    ]
    draw.polygon(tail_pts, fill="#ffffff")
    wb_r = int(radius * 0.65)
    draw.ellipse([cx - wb_r, cy - wb_r, cx + wb_r, cy + wb_r], fill="#ffffff")
    
    # Inner green handset/dot
    draw.ellipse([cx - int(radius * 0.35), cy - int(radius * 0.35), cx + int(radius * 0.35), cy + int(radius * 0.35)], fill="#25D366")
    draw.arc([cx - int(radius * 0.22), cy - int(radius * 0.22), cx + int(radius * 0.22), cy + int(radius * 0.22)], 90, 270, fill="#ffffff", width=3)


def draw_vector_icon(draw, cx, cy, icon_type, color="#facc15"):
    """Draws sharp vector icons for the bottom ribbon at 2x scale."""
    if icon_type == "book":
        draw.polygon([(cx - 18, cy - 14), (cx - 2, cy - 10), (cx - 2, cy + 14), (cx - 18, cy + 10)], fill=color)
        draw.polygon([(cx + 2, cy - 10), (cx + 18, cy - 14), (cx + 18, cy + 10), (cx + 2, cy + 14)], fill=color)
        draw.line([(cx, cy - 12), (cx, cy + 16)], fill="#78350f", width=4)
    elif icon_type == "shield":
        draw.polygon([
            (cx, cy - 18), (cx + 16, cy - 8), (cx + 12, cy + 8),
            (cx, cy + 18), (cx - 12, cy + 8), (cx - 16, cy - 8)
        ], fill=color)
        draw.line([(cx - 6, cy), (cx - 2, cy + 6), (cx + 6, cy - 4)], fill="#78350f", width=4)
    elif icon_type == "chart":
        draw.rectangle([cx - 16, cy + 4, cx - 8, cy + 14], fill=color)
        draw.rectangle([cx - 6, cy - 4, cx + 2, cy + 14], fill=color)
        draw.rectangle([cx + 4, cy - 12, cx + 12, cy + 14], fill=color)
        draw.polygon([(cx + 4, cy - 18), (cx + 16, cy - 18), (cx + 16, cy - 6)], fill=color)
    elif icon_type == "users":
        draw.ellipse([cx - 10, cy - 16, cx + 10, cy - 2], fill=color)
        draw.chord([cx - 16, cy, cx + 16, cy + 16], start=180, end=360, fill=color)
    elif icon_type == "star":
        draw.polygon([
            (cx, cy - 18), (cx + 6, cy - 6), (cx + 18, cy - 6),
            (cx + 8, cy + 4), (cx + 12, cy + 16), (cx, cy + 8),
            (cx - 12, cy + 16), (cx - 8, cy + 4), (cx - 18, cy - 6), (cx - 6, cy - 6)
        ], fill=color)


def generate_job_thumbnail(
    job_data,
    output_path,
    channel_name="EmploymentExpress",
    subscribe_text="SUBSCRIBE FOR DAILY GOVT ALERTS",
    visual_key=None
):
    """
    Generates a publication-grade 1200x630 thumbnail card using 2x super-sampling
    featuring official YouTube channel promotion, subscribe headline, dynamic text fitting,
    role/department-specific AI imagery, and an embedded 100% scannable WhatsApp Channel QR Code.
    """
    w2, h2 = 2400, 1260
    canvas = Image.new("RGBA", (w2, h2), (248, 250, 252, 255))
    draw = ImageDraw.Draw(canvas)

    # 1. Outer & Inner Framing
    draw.rectangle([12, 12, w2 - 12, h2 - 12], outline="#0b1a30", width=8)
    draw.rectangle([24, 24, w2 - 24, h2 - 24], outline="#f59e0b", width=4)

    # 2. Top Header Section
    org_code = job_data.get("org_code", "SSC").upper()
    org_full = job_data.get("org_full", "STAFF SELECTION COMMISSION").upper()
    main_title = job_data.get("main_title", "HINDI TRANSLATOR").upper()
    subtitle = job_data.get("subtitle", "—— (CHTE) ——")
    vacancies_count = str(job_data.get("vacancies_count", "303"))
    ribbon_alert = job_data.get("ribbon_alert", "REVISED NOTIFICATION 2026").upper()
    
    # Medallion: official seal when we have one, otherwise the EmploymentExpress
    # channel logo (every card carries the channel mark, like the reference).
    logo_path = None
    if "SSC" in org_code and (ASSETS_DIR / "ssc_logo.png").exists():
        logo_path = ASSETS_DIR / "ssc_logo.png"
    elif (("PUNJAB POLICE" in org_code or org_code == "PUNJAB POLICE") and (ASSETS_DIR / "punjab_logo.png").exists()):
        logo_path = ASSETS_DIR / "punjab_logo.png"
    elif (ASSETS_DIR / "logo.png").exists():
        logo_path = ASSETS_DIR / "logo.png"

    if logo_path:
        logo_img = make_circular_masked_image(logo_path, 176)
        if logo_img:
            canvas.paste(logo_img, (52, 40), mask=logo_img)
            draw.ellipse([52, 40, 228, 216], outline="#f59e0b", width=4)
    else:
        draw.ellipse([52, 40, 228, 216], fill="#c21807", outline="#f59e0b", width=6)
        draw.ellipse([68, 56, 212, 200], fill="#8b0000", outline="#facc15", width=4)
        font_tiny = get_font(FONT_BOLD, 40)
        draw.text((140, 128), "EE", font=font_tiny, fill="#ffffff", anchor="mm")

    # Organization Large Name & Subtext
    font_org_main = fit_text_font(draw, org_code, max_w=670, max_h=90, font_path=FONT_BOLD, start_size=110, min_size=52)
    draw.text((256, 52), org_code, font=font_org_main, fill="#0b2545")

    font_org_sub = get_font(FONT_BOLD, 26)
    org_sub_display = org_full if len(org_full) <= 36 else org_full[:34] + "..."
    draw.text((260, 176), org_sub_display, font=font_org_sub, fill="#1e3a8a")

    # Top Center Badge: "NEW / REVISED"
    badge_lines = job_data.get("top_badge_text", ["NEW", "REVISED"])
    badge_x1, badge_y1, badge_x2, badge_y2 = 950, 52, 1230, 192
    draw_rounded_rect(draw, [badge_x1, badge_y1, badge_x2, badge_y2], radius=16, fill="#dc2626", outline="#ffffff", width=4)
    font_badge = get_font(FONT_BOLD, 36)
    if len(badge_lines) >= 2:
        draw.text(((badge_x1 + badge_x2) // 2, badge_y1 + 40), badge_lines[0], font=font_badge, fill="#ffffff", anchor="mm")
        draw.text(((badge_x1 + badge_x2) // 2, badge_y1 + 96), badge_lines[1], font=font_badge, fill="#ffffff", anchor="mm")
    else:
        draw.text(((badge_x1 + badge_x2) // 2, (badge_y1 + badge_y2) // 2), badge_lines[0], font=font_badge, fill="#ffffff", anchor="mm")

    # Resolve and Composite Job-Specific Visual Image
    chosen_visual_path = resolve_visual_path(
        visual_key or job_data.get("visual_key"),
        job_title=main_title,
        job_dept=org_full
    )
    composite_job_visual(canvas, chosen_visual_path, x1=1260, y1=36, x2=2352, y2=584, department_name=org_full)

    # 3. Main Central Job Title Banner
    title_box_x1, title_box_y1 = 52, 248
    title_box_x2, title_box_y2 = 1230, 488
    draw_rounded_rect(draw, [title_box_x1, title_box_y1, title_box_x2, title_box_y2], radius=28, fill="#0a1931")

    # Title area bounds (leaves space for vacancy badge on right)
    title_max_w = 880
    title_cx = title_box_x1 + (title_max_w // 2) + 16

    font_main = fit_text_font(draw, main_title, max_w=title_max_w, max_h=86, font_path=FONT_BOLD, start_size=76, min_size=36)
    draw.text((title_cx, title_box_y1 + 84), main_title, font=font_main, fill="#ffffff", anchor="mm")

    font_sub = fit_text_font(draw, subtitle, max_w=title_max_w, max_h=48, font_path=FONT_BOLD, start_size=46, min_size=28)
    draw.text((title_cx, title_box_y1 + 172), subtitle, font=font_sub, fill="#facc15", anchor="mm")

    # Alert Oval Badge attached on the right side of Navy Box.
    # Recruitment cards show the vacancy number + "POSTS"; update cards
    # (result / answer key / admit card / admission) show a status word.
    vac_cx, vac_cy = 1120, 368
    vac_rx, vac_ry = 120, 96
    draw.ellipse([vac_cx - vac_rx, vac_cy - vac_ry, vac_cx + vac_rx, vac_cy + vac_ry], fill="#dc2626", outline="#facc15", width=8)

    badge_number = str(job_data.get("vacancy_badge_number", vacancies_count))
    badge_label = str(job_data.get("vacancy_badge_label", "POSTS")).upper()

    if badge_number.strip():
        font_vac_num = fit_text_font(draw, badge_number, max_w=190, max_h=76, font_path=FONT_BOLD, start_size=76, min_size=42)
        font_vac_lbl = get_font(FONT_BOLD, 28)
        draw.text((vac_cx, vac_cy - 18), badge_number, font=font_vac_num, fill="#fef08a", anchor="mm")
        draw.text((vac_cx, vac_cy + 46), badge_label, font=font_vac_lbl, fill="#ffffff", anchor="mm")
    else:
        # No vacancy number (update card): centre a bold status label.
        font_status = fit_text_font(draw, badge_label, max_w=200, max_h=120, font_path=FONT_BOLD, start_size=46, min_size=22)
        draw.text((vac_cx, vac_cy), badge_label, font=font_status, fill="#fef08a", anchor="mm")

    # Attached Red Ribbon Strip underneath Navy Box
    ribbon_y1, ribbon_y2 = 488, 584
    draw.rectangle([title_box_x1, ribbon_y1, title_box_x2, ribbon_y2], fill="#b91c1c")
    font_ribbon = fit_text_font(draw, ribbon_alert, max_w=1120, max_h=52, font_path=FONT_BOLD, start_size=42, min_size=26)
    draw.text(((title_box_x1 + title_box_x2) // 2, (ribbon_y1 + ribbon_y2) // 2), ribbon_alert, font=font_ribbon, fill="#ffffff", anchor="mm")

    # 4. Middle Section: Feature Pills (Left) & Important Highlights (Right)
    default_pills = [
        ("doc", "REVISED\nVACANCY", "#1976d2"),
        ("users", f"{vacancies_count}\nPOSTS", "#2e7d32"),
        ("calendar", "NEW\nNOTIFICATION", "#7b1fa2"),
        ("target", "GREAT\nOPPORTUNITY\nFOR ASPIRANTS", "#e65100")
    ]
    pills = job_data.get("feature_pills", default_pills)
    
    pill_w = 200
    start_px = 52
    pill_gap = 24
    for i, (icon_type, pill_text, icon_col) in enumerate(pills[:4]):
        px = start_px + i * (pill_w + pill_gap)
        py = 608
        draw_rounded_rect(draw, [px, py, px + pill_w, py + 288], radius=20, fill="#ffffff", outline="#cbd5e1", width=4)
        draw_icon_circle(draw, px + pill_w // 2, py + 72, 44, icon_col, icon_type=icon_type)
        
        font_pill = get_font(FONT_BOLD, 20)
        lines = pill_text.split("\n")
        if len(lines) == 1:
            draw.text((px + pill_w // 2, py + 190), lines[0], font=font_pill, fill="#0f172a", anchor="mm")
        elif len(lines) == 2:
            draw.text((px + pill_w // 2, py + 176), lines[0], font=font_pill, fill="#0f172a", anchor="mm")
            draw.text((px + pill_w // 2, py + 216), lines[1], font=font_pill, fill="#0f172a", anchor="mm")
        else:
            font_pill_small = get_font(FONT_BOLD, 17)
            draw.text((px + pill_w // 2, py + 164), lines[0], font=font_pill_small, fill="#0f172a", anchor="mm")
            draw.text((px + pill_w // 2, py + 196), lines[1], font=font_pill_small, fill="#0f172a", anchor="mm")
            draw.text((px + pill_w // 2, py + 228), lines[2], font=font_pill_small, fill="#0f172a", anchor="mm")

    # Important Highlights Box (Right side)
    hl_x1, hl_y1, hl_x2, hl_y2 = 956, 608, 2352, 896
    draw_rounded_rect(draw, [hl_x1, hl_y1, hl_x2, hl_y2], radius=20, fill="#ffffff", outline="#94a3b8", width=4)
    draw_rounded_rect(draw, [hl_x1, hl_y1, hl_x2, hl_y1 + 64], radius=16, fill="#0f284e")
    font_hl_head = get_font(FONT_BOLD, 30)
    draw.text(((hl_x1 + hl_x2) // 2, hl_y1 + 32), "IMPORTANT HIGHLIGHTS", font=font_hl_head, fill="#ffffff", anchor="mm")

    hl_dict = job_data.get("highlights", {
        "Post Name": main_title,
        "Revised Vacancies": f"{vacancies_count} Posts",
        "Department": org_full[:32],
        "Exam": "Computer Based Test (CBT)",
        "Official Notification": "2026"
    })

    item_y = hl_y1 + 92
    font_item_key = get_font(FONT_BOLD, 26)
    font_item_val = get_font(FONT_REG, 26)

    for key, val in list(hl_dict.items())[:5]:
        draw.ellipse([hl_x1 + 32, item_y - 14, hl_x1 + 56, item_y + 10], fill="#0284c7")
        draw.line([(hl_x1 + 38, item_y - 2), (hl_x1 + 44, item_y + 4), (hl_x1 + 52, item_y - 8)], fill="#ffffff", width=4)
        
        draw.text((hl_x1 + 72, item_y), f"{key}: ", font=font_item_key, fill="#0f172a", anchor="lm")
        key_width = draw.textlength(f"{key}: ", font=font_item_key)
        
        val_str = str(val)
        if len(val_str) > 42:
            val_str = val_str[:39] + "..."
        draw.text((hl_x1 + 72 + key_width, item_y), val_str, font=font_item_val, fill="#334155", anchor="lm")
        
        item_y += 42

    # 5. Call To Action, YouTube Channel & WhatsApp QR Code Row
    cta_y1, cta_y2 = 916, 1072
    
    # CTA Box 1 (Left - Yellow Gold: APPLY ONLINE)
    box1_x1, box1_x2 = 52, 532
    draw_rounded_rect(draw, [box1_x1, cta_y1, box1_x2, cta_y2], radius=20, fill="#f59e0b", outline="#d97706", width=4)
    draw.ellipse([box1_x1 + 24, cta_y1 + 28, box1_x1 + 100, cta_y1 + 104], fill="#0f172a", outline="#ffffff", width=4)
    draw.arc([box1_x1 + 36, cta_y1 + 40, box1_x1 + 88, cta_y1 + 92], 0, 360, fill="#ffffff", width=4)
    draw.line([(box1_x1 + 24, cta_y1 + 66), (box1_x1 + 100, cta_y1 + 66)], fill="#ffffff", width=4)
    draw.line([(box1_x1 + 62, cta_y1 + 28), (box1_x1 + 62, cta_y1 + 104)], fill="#ffffff", width=4)
    
    cta_main = job_data.get("cta_text", "APPLY ONLINE").upper()
    font_cta_main = fit_text_font(draw, cta_main, max_w=300, max_h=56, font_path=FONT_BOLD, start_size=38, min_size=22)
    draw.text((box1_x1 + 116, cta_y1 + 48), cta_main, font=font_cta_main, fill="#0a1931", anchor="lm")
    font_cta_sub = get_font(FONT_BOLD, 18)
    draw.text((box1_x1 + 118, cta_y1 + 100), "STAY UPDATED, STAY AHEAD!", font=font_cta_sub, fill="#0f172a", anchor="lm")

    # CTA Box 2 (Center - YouTube Channel: EmploymentExpress)
    box2_x1, box2_x2 = 556, 1456
    draw_rounded_rect(draw, [box2_x1, cta_y1, box2_x2, cta_y2], radius=20, fill="#ffffff", outline="#e2e8f0", width=4)
    
    yt_x1, yt_y1, yt_x2, yt_y2 = box2_x1 + 20, cta_y1 + 34, box2_x1 + 120, cta_y2 - 34
    draw.rounded_rectangle([yt_x1, yt_y1, yt_x2, yt_y2], radius=18, fill="#ff0000")
    draw.polygon([(yt_x1 + 36, yt_y1 + 18), (yt_x1 + 72, yt_y1 + 44), (yt_x1 + 36, yt_y1 + 70)], fill="#ffffff")

    font_ch_name = get_font(FONT_BOLD, 42)
    draw.text((box2_x1 + 138, cta_y1 + 48), channel_name, font=font_ch_name, fill="#0a1931", anchor="lm")

    subscribe_text = job_data.get("subscribe_text", subscribe_text)
    font_sub_head = get_font(FONT_BOLD, 19)
    draw.text((box2_x1 + 140, cta_y1 + 102), subscribe_text, font=font_sub_head, fill="#dc2626", anchor="lm")

    sub_pill_x1, sub_pill_x2 = box2_x2 - 216, box2_x2 - 20
    sub_pill_y1, sub_pill_y2 = cta_y1 + 36, cta_y2 - 36
    draw.rounded_rectangle([sub_pill_x1, sub_pill_y1, sub_pill_x2, sub_pill_y2], radius=34, fill="#dc2626")
    font_btn = get_font(FONT_BOLD, 24)
    draw.text(((sub_pill_x1 + sub_pill_x2) // 2, (sub_pill_y1 + sub_pill_y2) // 2), "SUBSCRIBE", font=font_btn, fill="#ffffff", anchor="mm")

    # CTA Box 3 (Right - WhatsApp Channel with 100% Scannable QR Code)
    box3_x1, box3_x2 = 1480, 2348
    draw_rounded_rect(draw, [box3_x1, cta_y1, box3_x2, cta_y2], radius=20, fill="#ffffff", outline="#22c55e", width=4)
    
    draw_whatsapp_badge(draw, box3_x1 + 54, cta_y1 + 78, 36)
    
    font_wa_head = get_font(FONT_BOLD, 36)
    draw.text((box3_x1 + 104, cta_y1 + 50), "WHATSAPP CHANNEL", font=font_wa_head, fill="#0f172a", anchor="lm")
    
    font_wa_sub = get_font(FONT_BOLD, 20)
    draw.text((box3_x1 + 106, cta_y1 + 102), "SCAN QR FOR INSTANT ALERTS", font=font_wa_sub, fill="#16a34a", anchor="lm")

    # Placeholder box for QR code border (will be crisp-pasted at final scale)
    qr_box_x1, qr_box_y1 = box3_x2 - 164, cta_y1 + 6
    qr_box_x2, qr_box_y2 = box3_x2 - 12, cta_y2 - 6
    draw.rounded_rectangle([qr_box_x1 - 4, qr_box_y1 - 4, qr_box_x2 + 4, qr_box_y2 + 4], radius=8, fill="#ffffff", outline="#cbd5e1", width=2)

    # 6. Bottom Motivational Ribbon (Y: 1100 to 1240)
    foot_y1, foot_y2 = 1100, 1240
    draw.rectangle([28, foot_y1, w2 - 28, foot_y2], fill="#881337")

    motivational_points = [
        ("PRESTIGIOUS\nGOVT. JOB", "book"),
        ("SECURE\nYOUR FUTURE", "shield"),
        ("GROW YOUR\nCAREER", "chart"),
        ("BE A PART OF\nNATION BUILDING", "users"),
        ("PREPARE TODAY\nSUCCESS TOMORROW", "star")
    ]

    m_step = (w2 - 56) // 5
    for i, (m_text, m_icon) in enumerate(motivational_points):
        mx = 28 + i * m_step + m_step // 2
        my = (foot_y1 + foot_y2) // 2
        
        ix = mx - 136
        draw_vector_icon(draw, ix, my, m_icon, color="#facc15")

        font_mot = get_font(FONT_BOLD, 18)
        lines = m_text.split("\n")
        draw.text((mx + 20, my - 12), lines[0], font=font_mot, fill="#ffffff", anchor="mm")
        draw.text((mx + 20, my + 14), lines[1], font=font_mot, fill="#fef08a", anchor="mm")
        
        if i < 4:
            draw.line([(28 + (i + 1) * m_step, foot_y1 + 16), (28 + (i + 1) * m_step, foot_y2 - 16)], fill="#be123c", width=2)

    # 7. Downsample to target 1200x630 using Lanczos
    final_canvas = canvas.convert("RGB")
    final_img = final_canvas.resize((1200, 630), Image.Resampling.LANCZOS)
    
    # 8. Crisp-paste the scannable WhatsApp QR code (74x74 px, box_size=2, border=2)
    # Guaranteed integer module rendering for 100% reliable camera / optical detection
    qr_img = get_whatsapp_qr_code_image(box_size=2, border=2)
    # Position matches (qr_box_x1/2, qr_box_y1/2) -> (1092, 461)
    final_img.paste(qr_img, (1092, 461))
    
    # Save standalone master QR code asset for reuse
    master_qr_path = ASSETS_DIR / "whatsapp_channel_qr.png"
    if not master_qr_path.exists():
        qr_master = get_whatsapp_qr_code_image(box_size=8, border=2)
        qr_master.save(master_qr_path, "PNG")

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    final_img.save(output_path, "PNG", quality=95)
    print(f"Generated thumbnail successfully: {output_path}")
    return output_path


def generate_homepage_cover(output_path):
    """Branded 1200x630 Open Graph cover for the homepage (channel identity card)."""
    w2, h2 = 2400, 1260
    canvas = Image.new("RGBA", (w2, h2), (10, 25, 49, 255))
    draw = ImageDraw.Draw(canvas)

    # Framing
    draw.rectangle([12, 12, w2 - 12, h2 - 12], outline="#f59e0b", width=8)
    draw.rectangle([28, 28, w2 - 28, h2 - 28], outline="#1e3a8a", width=4)

    # Medallion (channel logo)
    logo = ASSETS_DIR / "logo.png"
    logo_img = make_circular_masked_image(logo, 200) if logo.exists() else None
    if logo_img:
        canvas.paste(logo_img, (96, 96), mask=logo_img)
        draw.ellipse([96, 96, 296, 296], outline="#f59e0b", width=6)

    # Title block
    f_brand = get_font(FONT_BOLD, 118)
    draw.text((340, 110), "EMPLOYMENT", font=f_brand, fill="#ffffff")
    draw.text((340, 244), "EXPRESS", font=f_brand, fill="#facc15")

    f_sub = get_font(FONT_BOLD, 46)
    draw.text((344, 404), "PUNJAB  •  CHANDIGARH  •  CENTRAL GOVT JOBS", font=f_sub, fill="#cbd5e1")

    # Red ribbon of coverage categories
    draw.rectangle([96, 520, w2 - 96, 636], fill="#b91c1c")
    f_ribbon = get_font(FONT_BOLD, 52)
    draw.text((w2 // 2, 578), "LATEST VACANCIES  •  RESULTS  •  ADMIT CARDS  •  ANSWER KEYS",
              font=f_ribbon, fill="#ffffff", anchor="mm")

    # Feature chips
    chips = ["DAILY JOB ALERTS", "OFFICIAL SOURCE LINKS", "FREE PDF & SYLLABUS", "WHATSAPP / YOUTUBE"]
    chip_y = 720
    chip_w = 520
    gap = 36
    total = 4 * chip_w + 3 * gap
    start_x = (w2 - total) // 2
    for i, label in enumerate(chips):
        x1 = start_x + i * (chip_w + gap)
        draw_rounded_rect(draw, [x1, chip_y, x1 + chip_w, chip_y + 120], radius=18,
                          fill="#0f284e", outline="#f59e0b", width=3)
        f_chip = get_font(FONT_BOLD, 32)
        draw.text((x1 + chip_w // 2, chip_y + 60), label, font=f_chip, fill="#fef08a", anchor="mm")

    # Bottom CTA row: YouTube + WhatsApp QR
    cta_y1, cta_y2 = 900, 1080
    # YouTube box
    b1x1, b1x2 = start_x, start_x + 1280
    draw_rounded_rect(draw, [b1x1, cta_y1, b1x2, cta_y2], radius=20, fill="#ffffff")
    yt = [b1x1 + 30, cta_y1 + 40, b1x1 + 130, cta_y2 - 40]
    draw.rounded_rectangle(yt, radius=18, fill="#ff0000")
    draw.polygon([(yt[0] + 36, yt[1] + 18), (yt[0] + 72, yt[1] + 45), (yt[0] + 36, yt[1] + 72)], fill="#ffffff")
    draw.text((b1x1 + 150, cta_y1 + 56), "EmploymentExpress", font=get_font(FONT_BOLD, 52), fill="#0a1931", anchor="lm")
    draw.text((b1x1 + 152, cta_y1 + 128), "SUBSCRIBE FOR DAILY GOVT JOB ALERTS", font=get_font(FONT_BOLD, 26), fill="#dc2626", anchor="lm")

    # WhatsApp box
    b2x1, b2x2 = b1x2 + gap, start_x + total
    draw_rounded_rect(draw, [b2x1, cta_y1, b2x2, cta_y2], radius=20, fill="#ffffff", outline="#22c55e", width=4)
    draw_whatsapp_badge(draw, b2x1 + 70, cta_y1 + 90, 40)
    draw.text((b2x1 + 124, cta_y1 + 60), "WHATSAPP CHANNEL", font=get_font(FONT_BOLD, 42), fill="#0f172a", anchor="lm")
    draw.text((b2x1 + 126, cta_y1 + 128), "SCAN QR FOR INSTANT ALERTS", font=get_font(FONT_BOLD, 26), fill="#16a34a", anchor="lm")
    qr_holder = [b2x2 - 180, cta_y1 + 10, b2x2 - 20, cta_y2 - 10]
    draw.rounded_rectangle(qr_holder, radius=8, fill="#ffffff", outline="#cbd5e1", width=2)

    final = canvas.convert("RGB").resize((1200, 630), Image.Resampling.LANCZOS)
    qr_img = get_whatsapp_qr_code_image(box_size=2, border=2)
    # QR paste position scaled from 2x -> 1x (qr_holder maps proportionally).
    qx = int((qr_holder[0] + 6) / 2)
    qy = int((qr_holder[1] + 6) / 2)
    final.paste(qr_img, (qx, qy))

    output_path.parent.mkdir(parents=True, exist_ok=True)
    final.save(output_path, "PNG", quality=95)
    print(f"Generated homepage cover: {output_path}")
    return output_path


def detect_alert_type(job):
    """Classify a job/notice record as a recruitment or an update notice.

    Returns one of: recruitment, result, answer_key, admit_card, admission.
    Trusts the upstream ``alertType`` field first, then falls back to title
    keywords so the parser stays correct even for hand-authored records.
    """
    raw = (job.get("alertType") or "").strip().lower().replace("-", "_")
    if raw in ("result", "answer_key", "admit_card", "admission", "recruitment"):
        return raw

    title = (job.get("title") or "").lower()
    badge = (job.get("badge") or "").lower()
    hay = f"{title} {badge}"
    if "answer key" in hay or "objection" in hay:
        return "answer_key"
    if "result" in hay or "score card" in hay or "score-card" in hay or "merit list" in hay:
        return "result"
    if "exam city" in hay or "intimation" in hay or "admit card" in hay or "call letter" in hay:
        return "admit_card"
    if "admission" in hay or "entrance" in hay:
        return "admission"
    return "recruitment"


def _clean_dept(dept, n=44):
    """Short, tidy organisation name: drop parentheticals/locations and commas."""
    s = re.sub(r"\(.*?\)", "", dept or "")
    s = s.split(",")[0]
    s = re.sub(r"\s+", " ", s).strip(" ,.-–—").upper()
    return s[:n]


def _clean_card_title(title, dept, max_len=40):
    """Reduce a scraped notification title to a short, scannable card headline."""
    t = (title or "").strip()
    # Drop leading source-site fragments like "sbi.bank.in — " or "uco.bank.in — ".
    t = re.sub(r"^https?://", "", t)
    t = re.sub(r"^[\w.-]+\.(?:com|in|ac\.in|gov\.in|org|net)\b\s*[–—-]*\s*", "", t, flags=re.IGNORECASE)
    # Drop the leading organisation prefix (often repeated in the header).
    for prefix in (f"{dept} —", f"{dept} –", f"{dept} -", dept):
        if prefix and t.startswith(prefix):
            t = t[len(prefix):].strip(" –—-")
    # Remove leading filler words / generic verbs.
    for _ in range(3):
        t = re.sub(
            r"^(new|alert|view|download|check|public\s+notice|notice|notification|"
            r"corrigendum|regarding|re[- ]?opening?|important)\b\s*[,:.–—-]*\s*",
            "", t, flags=re.IGNORECASE)
    # For results, keep the post name after "result ... (posts) of".
    m = re.search(r"result\b(?:notification)?\b[^,–—-]*?\b(?:posts?\s+of|of\s+engagement\s+of|for\s+the\s+posts?\s+of|of|for)\s+",
                  t, flags=re.IGNORECASE)
    if m:
        t = t[m.end():]
    # Drop trailing page/PDF noise like "PDF 342" or bare numbers.
    t = re.sub(r"\bpdf\b\s*\d*\s*$", "", t, flags=re.IGNORECASE)
    t = re.sub(r"\s+\d{1,3}$", "", t)
    # Cut at a sentence/separator boundary when too long.
    if len(t) > max_len:
        cut = re.split(r"[.–—|:]|\bAdvertisement\b|\bNotification\b|\bon contract\b", t, flags=re.IGNORECASE)[0]
        t = cut.strip() if len(cut.strip()) >= 12 else t
        if len(t) > max_len:
            t = t[:max_len].rsplit(" ", 1)[0].strip()
    t = re.sub(r"\s+", " ", t).strip(" –—-,&")
    return t[:max_len].strip(" –—-,&").upper()


# Per-alert-type presentation: ribbon, top badge, oval badge label, CTA and
# the four feature-pill labels. Vacancy counts are shown only for recruitment.
ALERT_STYLE = {
    "result": {
        "ribbon": "RESULT DECLARED 2026",
        "badge": ["RESULT", "OUT"],
        "pill": ("doc", "RESULT\nDECLARED", "#1976d2"),
        "pill2": ("target", "OFFICIAL\nUPDATE", "#e65100"),
        "cta": "VIEW RESULT",
        "oval": "RESULT",
        "subscribe": "SUBSCRIBE FOR LATEST RESULTS",
    },
    "answer_key": {
        "ribbon": "ANSWER KEY RELEASED 2026",
        "badge": ["ANSWER", "KEY"],
        "pill": ("doc", "ANSWER\nKEY", "#1976d2"),
        "pill2": ("target", "OFFICIAL\nUPDATE", "#e65100"),
        "cta": "VIEW ANSWER KEY",
        "oval": "ANSWER\nKEY",
        "subscribe": "SUBSCRIBE FOR ANSWER KEYS",
    },
    "admit_card": {
        "ribbon": "ADMIT CARD / EXAM CITY OUT 2026",
        "badge": ["ADMIT", "CARD"],
        "pill": ("doc", "ADMIT\nCARD", "#1976d2"),
        "pill2": ("target", "EXAM CITY\nSLIP", "#e65100"),
        "cta": "DOWNLOAD ADMIT CARD",
        "oval": "ADMIT\nCARD",
        "subscribe": "SUBSCRIBE FOR ADMIT CARDS",
    },
    "admission": {
        "ribbon": "ADMISSION OPEN 2026-27",
        "badge": ["NEW", "ADMISSION"],
        "pill": ("doc", "ADMISSION\nOPEN", "#1976d2"),
        "pill2": ("target", "APPLY\nONLINE", "#e65100"),
        "cta": "APPLY ONLINE",
        "oval": None,  # admissions can still have seat counts
        "subscribe": "SUBSCRIBE FOR ADMISSION UPDATES",
    },
    "recruitment": {
        "ribbon": None,
        "badge": ["NEW", "ALERT"],
        "pill": ("doc", "OFFICIAL\nNOTICE", "#1976d2"),
        "pill2": ("target", "GREAT\nOPPORTUNITY\nFOR ASPIRANTS", "#e65100"),
        "cta": "APPLY ONLINE",
        "oval": None,
        "subscribe": "SUBSCRIBE FOR DAILY GOVT ALERTS",
    },
}


def parse_job_for_thumbnail(job):
    """Transforms any job/notice dictionary into thumbnail-generator card data.

    The card is tailored to the alert type (recruitment, result, answer key,
    admit card, admission) so shared links show that specific notice rather
    than a generic vacancy card.
    """
    title = job.get("title", "")
    dept = job.get("department", "") or job.get("organization", "") or "Govt Recruitment"
    vacancies = str(job.get("vacancies", "") or "")
    alert_type = detect_alert_type(job)
    style = ALERT_STYLE[alert_type]

    # --- Organisation header -------------------------------------------------
    dl = dept.lower()
    tl = title.lower()
    if "ssc" in dl or "staff selection" in dl or "ssc" in tl:
        org_code, org_full = "SSC", "STAFF SELECTION COMMISSION"
    elif "punjab police" in dl or "police" in dl or "constable" in tl:
        org_code, org_full = "PUNJAB POLICE", "DEPARTMENT OF POLICE, PUNJAB"
    elif "high court" in dl or "phhc" in dl or "high court" in tl:
        org_code = "HIGH COURT"
        org_full = _clean_dept(dept, 44) if "high court" in dl else "HIGH COURT OF PUNJAB & HARYANA, CHANDIGARH"
    elif "psssb" in dl or "subordinate services" in dl:
        org_code, org_full = "PSSSB", "PUNJAB SUBORDINATE SERVICES SELECTION BOARD"
    elif "ppsc" in dl or "public service commission" in dl:
        org_code, org_full = "PPSC", "PUNJAB PUBLIC SERVICE COMMISSION"
    elif "upsc" in dl or "union public" in dl:
        org_code, org_full = "UPSC", "UNION PUBLIC SERVICE COMMISSION"
    elif "india post" in dl or "department of post" in dl or "dak sevak" in tl or "gds" in tl:
        org_code, org_full = "INDIA POST", "DEPARTMENT OF POSTS (INDIA POST)"
    elif "aiims" in dl or "health" in dl or "medical" in dl or "doctor" in tl or "nurse" in tl:
        org_code, org_full = "AIIMS / HEALTH", "MINISTRY OF HEALTH & FAMILY WELFARE"
    elif "railway" in dl or "rrb" in dl or "rrc" in dl or "rail coach" in dl:
        org_code, org_full = "RAILWAYS", "MINISTRY OF RAILWAYS (RRB / RRC)"
    elif "army" in dl or "air force" in dl or "navy" in dl or "agniveer" in tl:
        org_code, org_full = "DEFENCE", "MINISTRY OF DEFENCE"
    elif "csir" in dl or "nal" in dl:
        org_code, org_full = "CSIR - NAL", "COUNCIL OF SCIENTIFIC & INDUSTRIAL RESEARCH"
    elif "navodaya" in dl or "nvs" in tl or "jnv" in tl:
        org_code, org_full = "NVS", "NAVODAYA VIDYALAYA SAMITI"
    elif "pau" in dl or "agricultural university" in dl:
        org_code, org_full = "PAU", "PUNJAB AGRICULTURAL UNIVERSITY, LUDHIANA"
    elif "guru nanak dev" in dl or "gndu" in dl:
        org_code, org_full = "GNDU", "GURU NANAK DEV UNIVERSITY, AMRITSAR"
    elif "pspcl" in dl or "power corporation" in dl:
        org_code, org_full = "PSPCL", "PUNJAB STATE POWER CORPORATION LTD"
    elif "pulsa" in dl or "legal services" in dl:
        org_code, org_full = "PULSA", "PUNJAB STATE LEGAL SERVICES AUTHORITY"
    elif "school education" in dl or "master cadre" in tl or "ett" in tl:
        org_code, org_full = "EDUCATION PUNJAB", "DEPARTMENT OF SCHOOL EDUCATION, PUNJAB"
    else:
        # Short, tidy fallback acronym/name from the department.
        words = re.findall(r"[A-Za-z]+", dept)
        org_code = "".join(w[0] for w in words if w[0].isupper())[:12] or dept.split(",")[0][:12]
        org_code = org_code.upper()
        org_full = dept.split(",")[0].upper()[:40]

    # --- Headline ------------------------------------------------------------
    # Prefer the full descriptive title (cleaned to the post/notice name); the
    # short UI ``headline`` is often just "<Org> Vacancy" and too generic for a
    # social card.
    main_title = _clean_card_title(title or job.get("headline"), dept)

    # --- Vacancy / status badge ---------------------------------------------
    # Prefer an explicit total ("167 posts"); fall back to the first number.
    is_recruitment_like = alert_type in ("recruitment", "admission")
    total_match = re.search(r"(\d[\d,]{0,6})\s*(?:posts?|seats?|vacancies?)\b", vacancies, re.IGNORECASE)
    vac_num_match = total_match or re.search(r"(\d[\d,]*)", vacancies)
    if is_recruitment_like and vac_num_match:
        vac_num = vac_num_match.group(1).replace(",", "")
        oval_number, oval_label = vac_num, ("SEATS" if alert_type == "admission" else "POSTS")
    else:
        oval_number = ""
        oval_label = style["oval"] or "NOTICE"

    # --- Ribbon & top badge --------------------------------------------------
    badge = (job.get("badge") or "").strip()
    if style["ribbon"]:
        ribbon = style["ribbon"]
    elif badge:
        ribbon = badge.upper() if "2026" in badge else f"{badge.upper()} 2026"
    else:
        ribbon = "OFFICIAL NOTIFICATION 2026"

    top_badge = style["badge"]
    if "revised" in tl or "re-open" in tl or "extended" in tl:
        top_badge = ["UPDATED", "REVISED"]

    # --- Feature pills --------------------------------------------------------
    if is_recruitment_like:
        if oval_number:
            second_pill = ("users", f"{oval_number}\n{'SEATS' if alert_type == 'admission' else 'POSTS'}", "#2e7d32")
        else:
            second_pill = ("users", "MULTIPLE\nPOSTS", "#2e7d32")
    else:
        second_pill = ("target", "LATEST\nUPDATE", "#2e7d32")

    if is_recruitment_like:
        date_raw = str(job.get("lastDate") or "")
        if re.search(r"\d{4}", date_raw) and "see" not in date_raw.lower():
            third_pill = ("calendar", f"LAST DATE\n{date_raw.split('T')[0][:14]}", "#7b1fa2")
        else:
            third_pill = ("calendar", "NEW\nNOTIFICATION", "#7b1fa2")
    else:
        pub_raw = str(job.get("publishedAt") or job.get("lastDate") or "")
        pub = pub_raw.split("T")[0]
        if re.search(r"\d{4}", pub) and "see" not in pub.lower():
            third_pill = ("calendar", f"PUBLISHED\n{pub[:14]}", "#7b1fa2")
        else:
            third_pill = ("calendar", "NOTICE\nOUT NOW", "#7b1fa2")
    feature_pills = [style["pill"], second_pill, third_pill, style["pill2"]]

    # --- Highlights -----------------------------------------------------------
    highlights = {"Department": _clean_dept(dept, 38)}
    if alert_type == "recruitment":
        highlights = {
            "Post Name": main_title,
            "Vacancies": (vacancies[:28] or "See Notification"),
            "Department": _clean_dept(dept, 38),
            "Last Date": job.get("lastDate", "See Notification"),
            "Apply Mode": job.get("applyMode", "Online"),
        }
    elif alert_type == "admission":
        highlights = {
            "Course": main_title,
            "Seats / Eligibility": (vacancies[:28] or "See Notification"),
            "Institute": _clean_dept(dept, 38),
            "Last Date": job.get("lastDate", "See Notification"),
            "Apply Mode": job.get("applyMode", "Online"),
        }
    else:  # result / answer_key / admit_card
        notice_label = {"result": "Result", "answer_key": "Answer Key", "admit_card": "Admit Card"}[alert_type]
        pub = str(job.get("publishedAt") or job.get("lastDate") or "").split("T")[0]
        pub_val = pub if re.search(r"\d{4}", pub) and "see" not in pub.lower() else "Check Official Notice"
        highlights = {
            f"{notice_label} For": main_title,
            "Organisation": _clean_dept(dept, 38),
            "Notice Type": notice_label.title(),
            "Published": pub_val,
            "Status": "OUT / Released",
        }

    advt = str(job.get("advtNo") or "OFFICIAL UPDATE 2026")
    if len(advt) > 34:
        advt = advt[:32]

    return {
        "org_code": org_code,
        "org_full": org_full,
        "main_title": main_title,
        "subtitle": f"—— {advt[:34]} ——",
        "vacancies_count": oval_number or "NEW",
        "vacancy_badge_number": oval_number,
        "vacancy_badge_label": oval_label,
        "ribbon_alert": ribbon,
        "top_badge_text": top_badge,
        "highlights": highlights,
        "feature_pills": feature_pills,
        "cta_text": style["cta"],
        "subscribe_text": style["subscribe"],
        "alert_type": alert_type,
    }


def main():
    parser = argparse.ArgumentParser(description="Generate job thumbnail cards")
    parser.add_argument("--all", action="store_true", help="Generate thumbnails for all jobs")
    parser.add_argument("--sample", action="store_true", help="Generate sample reference thumbnails")
    parser.add_argument("--job-id", type=int, help="Job ID to generate thumbnail for")
    parser.add_argument("--homepage", action="store_true", help="Generate the branded homepage 1200x630 cover")
    args = parser.parse_args()

    if args.homepage:
        generate_homepage_cover(ASSETS_DIR / "homepage-og-cover.png")
        print("Homepage cover generated successfully!")
        return

    # 1. SSC JHT Reference Card (Student Aspirant Visual)
    ssc_jht_data = {
        "org_code": "SSC",
        "org_full": "STAFF SELECTION COMMISSION",
        "main_title": "HINDI TRANSLATOR",
        "subtitle": "—— (CHTE) ——",
        "vacancies_count": "303",
        "ribbon_alert": "REVISED NOTIFICATION 2026",
        "top_badge_text": ["NEW", "REVISED"],
        "highlights": {
            "Post Name": "Hindi Translator (CHTE)",
            "Revised Vacancies": "303 Posts",
            "Department": "Various Ministries / Departments",
            "Exam": "Computer Based Test (CBT)",
            "Official Notification": "2026"
        },
        "feature_pills": [
            ("doc", "REVISED\nVACANCY", "#1976d2"),
            ("users", "303\nPOSTS", "#2e7d32"),
            ("calendar", "NEW\nNOTIFICATION", "#7b1fa2"),
            ("target", "GREAT\nOPPORTUNITY\nFOR ASPIRANTS", "#e65100")
        ],
        "cta_text": "APPLY ONLINE"
    }

    generate_job_thumbnail(
        ssc_jht_data,
        ASSETS_DIR / "ssc-jht-2026-exam-city-thumbnail.png",
        channel_name="EmploymentExpress",
        subscribe_text="SUBSCRIBE FOR DAILY GOVT ALERTS",
        visual_key="student_aspirant"
    )
    generate_job_thumbnail(
        ssc_jht_data,
        THUMBNAIL_DIR / "ssc-jht-recruitment-2026.png",
        channel_name="EmploymentExpress",
        subscribe_text="SUBSCRIBE FOR DAILY GOVT ALERTS",
        visual_key="student_aspirant"
    )

    # 2. Punjab & Haryana High Court Card (High Court Building Facade Visual)
    phhc_data = {
        "org_code": "HIGH COURT",
        "org_full": "HIGH COURT OF PUNJAB & HARYANA, CHANDIGARH",
        "main_title": "DRIVER, MALI & SAFAI SEWAK",
        "subtitle": "—— ADVT NO. 01/HC/2026 ——",
        "vacancies_count": "167",
        "ribbon_alert": "OFFICIAL NOTIFICATION 2026",
        "top_badge_text": ["NEW", "REVISED"],
        "highlights": {
            "Post Name": "Driver, Frash, Safai Sewak & Mali",
            "Total Vacancies": "167 Posts (25 Driver, 31 Frash, etc.)",
            "Department": "Punjab & Haryana High Court",
            "Last Date": "18-09-2026",
            "Qualification": "10th / 10+2 / Driving License"
        },
        "feature_pills": [
            ("doc", "OFFICIAL\nNOTICE", "#1976d2"),
            ("users", "167\nPOSTS", "#2e7d32"),
            ("calendar", "LAST DATE\n18-09-2026", "#7b1fa2"),
            ("target", "DIRECT\nRECRUITMENT\nFOR ALL", "#e65100")
        ],
        "cta_text": "APPLY ONLINE"
    }
    generate_job_thumbnail(
        phhc_data,
        THUMBNAIL_DIR / "punjab-haryana-high-court-recruitment-2026.png",
        channel_name="EmploymentExpress",
        subscribe_text="SUBSCRIBE FOR DAILY RECRUITMENT NOTICES",
        visual_key="high_court_building"
    )

    # 3. Punjab Police Constable Card (Police Officer Visual)
    police_data = {
        "org_code": "PUNJAB POLICE",
        "org_full": "DEPARTMENT OF POLICE, PUNJAB",
        "main_title": "CONSTABLE & HEAD CONSTABLE",
        "subtitle": "—— RECRUITMENT 2026 ——",
        "vacancies_count": "1800",
        "ribbon_alert": "NEW VACANCY 2026",
        "top_badge_text": ["ACTIVE", "ONLINE"],
        "highlights": {
            "Post Name": "District & Armed Police Cadre",
            "Total Vacancies": "1800+ Posts",
            "Department": "Punjab Police Recruitment Board",
            "Selection": "CBT + Physical Screening (PST)",
            "Qualification": "10+2 (12th Pass) + Punjabi"
        },
        "feature_pills": [
            ("doc", "POLICE\nCADRE", "#1976d2"),
            ("users", "1800+\nPOSTS", "#2e7d32"),
            ("calendar", "APPLY ONLINE\nNOW", "#7b1fa2"),
            ("target", "UNIFORM\nCAREER", "#e65100")
        ],
        "cta_text": "APPLY NOW"
    }
    generate_job_thumbnail(
        police_data,
        THUMBNAIL_DIR / "punjab-police-constable-recruitment-2026.png",
        channel_name="EmploymentExpress",
        subscribe_text="SUBSCRIBE FOR POLICE RECRUITMENT UPDATES",
        visual_key="police"
    )

    # 4. India Post GDS Dak Sevak Card (Postman Visual)
    post_data = {
        "org_code": "INDIA POST",
        "org_full": "DEPARTMENT OF POSTS (INDIA POST)",
        "main_title": "GRAMIN DAK SEVAK (GDS / BPM)",
        "subtitle": "—— SCHEDULE 2026 ——",
        "vacancies_count": "44228",
        "ribbon_alert": "ONLINE APPLICATION OPEN 2026",
        "top_badge_text": ["MERIT", "DIRECT"],
        "highlights": {
            "Post Name": "Gramin Dak Sevak (BPM / ABPM)",
            "Total Vacancies": "44,228 Posts Across Circles",
            "Department": "Ministry of Communications",
            "Selection": "10th Merit Based (No Exam)",
            "Qualification": "10th Pass with Maths & English"
        },
        "feature_pills": [
            ("doc", "DIRECT\nMERIT", "#1976d2"),
            ("users", "44K+\nPOSTS", "#2e7d32"),
            ("calendar", "ACTIVE\nPORTAL", "#7b1fa2"),
            ("target", "CENTRAL\nGOVT JOB", "#e65100")
        ],
        "cta_text": "APPLY ONLINE"
    }
    generate_job_thumbnail(
        post_data,
        THUMBNAIL_DIR / "india-post-gds-recruitment-2026.png",
        channel_name="EmploymentExpress",
        subscribe_text="SUBSCRIBE FOR INDIA POST NOTICES",
        visual_key="postman"
    )

    # 5. AIIMS / Medical Officer Doctor Card (Doctor Visual)
    doctor_data = {
        "org_code": "AIIMS / HEALTH",
        "org_full": "ALL INDIA INSTITUTE OF MEDICAL SCIENCES",
        "main_title": "SENIOR RESIDENT & DOCTOR",
        "subtitle": "—— ADVT NO. AIIMS/2026 ——",
        "vacancies_count": "520",
        "ribbon_alert": "OFFICIAL NOTIFICATION 2026",
        "top_badge_text": ["MEDICAL", "ACTIVE"],
        "highlights": {
            "Post Name": "Senior Resident / Medical Officer",
            "Total Vacancies": "520 Medical Specialist Posts",
            "Institute": "AIIMS Hospitals & Medical Colleges",
            "Qualification": "MBBS / MD / MS / DNB Degree",
            "Pay Scale": "Level-11 (₹67,700 - ₹2,08,700)"
        },
        "feature_pills": [
            ("doc", "MEDICAL\nSPECIALIST", "#1976d2"),
            ("users", "520\nPOSTS", "#2e7d32"),
            ("calendar", "INTERVIEW\nWALK-IN", "#7b1fa2"),
            ("target", "AIIMS\nCAREER", "#e65100")
        ],
        "cta_text": "APPLY ONLINE"
    }
    generate_job_thumbnail(
        doctor_data,
        THUMBNAIL_DIR / "aiims-senior-resident-doctor-recruitment-2026.png",
        channel_name="EmploymentExpress",
        subscribe_text="SUBSCRIBE FOR HEALTHCARE & AIIMS JOBS",
        visual_key="doctor"
    )

    if args.all:
        auto_jobs_file = ROOT_DIR / "data" / "auto-jobs.json"
        if auto_jobs_file.exists():
            with open(auto_jobs_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                jobs = data.get("jobs", [])
                for job in jobs:
                    jdata = parse_job_for_thumbnail(job)
                    slug = f"job-{job.get('id', 'item')}.png"
                    generate_job_thumbnail(jdata, THUMBNAIL_DIR / slug)

    print("All thumbnails generated successfully!")


if __name__ == "__main__":
    main()
