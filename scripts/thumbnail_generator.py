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
    elif any(k in combined for k in ["post", "dak sevak", "gds", "postman", "mail guard"]):
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
    
    # Official Logo Medallion
    logo_path = None
    if "SSC" in org_code and (ASSETS_DIR / "ssc_logo.png").exists():
        logo_path = ASSETS_DIR / "ssc_logo.png"
    elif ("PUNJAB" in org_code or "PSSSB" in org_code or "POLICE" in org_code) and (ASSETS_DIR / "punjab_logo.png").exists():
        logo_path = ASSETS_DIR / "punjab_logo.png"
        
    if logo_path:
        logo_img = make_circular_masked_image(logo_path, 176)
        if logo_img:
            canvas.paste(logo_img, (52, 40), mask=logo_img)
            draw.ellipse([52, 40, 228, 216], outline="#f59e0b", width=4)
    else:
        draw.ellipse([52, 40, 228, 216], fill="#c21807", outline="#f59e0b", width=6)
        draw.ellipse([68, 56, 212, 200], fill="#8b0000", outline="#facc15", width=4)
        font_tiny = get_font(FONT_BOLD, 20)
        draw.text((140, 128), org_code[:6], font=font_tiny, fill="#ffffff", anchor="mm")

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

    # Vacancy Oval Badge attached on the right side of Navy Box
    vac_cx, vac_cy = 1120, 368
    vac_rx, vac_ry = 120, 96
    draw.ellipse([vac_cx - vac_rx, vac_cy - vac_ry, vac_cx + vac_rx, vac_cy + vac_ry], fill="#dc2626", outline="#facc15", width=8)
    
    font_vac_num = fit_text_font(draw, vacancies_count, max_w=190, max_h=76, font_path=FONT_BOLD, start_size=76, min_size=42)
    font_vac_lbl = get_font(FONT_BOLD, 28)
    draw.text((vac_cx, vac_cy - 18), vacancies_count, font=font_vac_num, fill="#fef08a", anchor="mm")
    draw.text((vac_cx, vac_cy + 42), "POSTS", font=font_vac_lbl, fill="#ffffff", anchor="mm")

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
        "Post Name": main_title[:30],
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
    font_cta_main = get_font(FONT_BOLD, 38)
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


def parse_job_for_thumbnail(job):
    """Transforms any job dictionary into structured data for thumbnail generator."""
    title = job.get("title", "")
    dept = job.get("department", "") or job.get("organization", "") or "Govt Recruitment"
    vacancies = job.get("vacancies", "See Notification")
    
    org_code = "GOVT JOB"
    if "SSC" in dept or "Staff Selection" in dept or "SSC" in title:
        org_code = "SSC"
        org_full = "STAFF SELECTION COMMISSION"
    elif "Punjab Police" in dept or "Punjab Police" in title:
        org_code = "PUNJAB POLICE"
        org_full = "DEPARTMENT OF POLICE, PUNJAB"
    elif "High Court" in dept or "PHHC" in dept or "High Court" in title:
        org_code = "HIGH COURT"
        org_full = "HIGH COURT OF PUNJAB & HARYANA"
    elif "PSSSB" in dept or "Subordinate Services" in dept:
        org_code = "PSSSB"
        org_full = "PUNJAB SUBORDINATE SERVICES SELECTION BOARD"
    elif "UPSC" in dept or "Union Public" in dept:
        org_code = "UPSC"
        org_full = "UNION PUBLIC SERVICE COMMISSION"
    elif "Post" in dept or "India Post" in dept or "Dak Sevak" in title or "GDS" in title:
        org_code = "INDIA POST"
        org_full = "DEPARTMENT OF POSTS (INDIA POST)"
    elif "AIIMS" in dept or "Health" in dept or "Doctor" in title or "Medical" in dept:
        org_code = "AIIMS / HEALTH"
        org_full = "MINISTRY OF HEALTH & FAMILY WELFARE"
    elif "Railway" in dept or "RRB" in dept or "RRC" in dept:
        org_code = "RAILWAYS"
        org_full = "MINISTRY OF RAILWAYS (RRB / RRC)"
    elif "Army" in dept or "Air Force" in dept or "Navy" in dept:
        org_code = "DEFENCE"
        org_full = dept.upper()
    elif "CSIR" in dept or "NAL" in dept:
        org_code = "CSIR - NAL"
        org_full = "COUNCIL OF SCIENTIFIC & INDUSTRIAL RESEARCH"
    else:
        org_code = dept[:14].upper()
        org_full = dept.upper()

    main_title = job.get("headline") or title
    for prefix in [f"{dept} —", f"{dept} -", "Recruitment of", "Advertisement No."]:
        if prefix in main_title:
            main_title = main_title.split(prefix)[-1].strip()
            
    vac_num_match = re.search(r'(\d+)', str(vacancies))
    vac_num = vac_num_match.group(1) if vac_num_match else "NEW"
    
    badge = job.get("badge", "NEW RECRUITMENT 2026")
    ribbon = f"{badge} 2026" if "2026" not in badge else badge
    if "EXAM CITY" in title.upper() or "INTIMATION" in title.upper():
        ribbon = "EXAM CITY INTIMATION SLIP OUT 2026"
    elif "ADMIT CARD" in title.upper():
        ribbon = "ADMIT CARD RELEASED 2026"
    elif "RESULT" in title.upper():
        ribbon = "RESULT DECLARED 2026"
        
    highlights = {
        "Post Name": main_title[:30],
        "Vacancies": vacancies[:28],
        "Department": dept[:32],
        "Last Date": job.get("lastDate", "See Notification"),
        "Exam / Mode": job.get("applyMode", "Online CBT")
    }
    
    return {
        "org_code": org_code,
        "org_full": org_full,
        "main_title": main_title[:28],
        "subtitle": f"—— {job.get('advtNo', 'OFFICIAL NOTIFICATION')} ——",
        "vacancies_count": vac_num,
        "ribbon_alert": ribbon,
        "top_badge_text": ["NEW", "REVISED"] if "revised" in title.lower() else ["NEW", "ALERT"],
        "highlights": highlights,
        "cta_text": "APPLY ONLINE" if "exam" not in ribbon.lower() else "CHECK EXAM CITY"
    }


def main():
    parser = argparse.ArgumentParser(description="Generate job thumbnail cards")
    parser.add_argument("--all", action="store_true", help="Generate thumbnails for all jobs")
    parser.add_argument("--sample", action="store_true", help="Generate sample reference thumbnails")
    parser.add_argument("--job-id", type=int, help="Job ID to generate thumbnail for")
    args = parser.parse_args()

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
