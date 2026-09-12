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
YOUTUBE_CHANNEL_URL = "https://www.youtube.com/channel/UCI39CbrtpEflEPabKeCAd9A"


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


def get_qr_code_image(url, box_size=2, border=2):
    """
    Generates a pixel-perfect, crisp, 100% scannable QR Code for any URL.
    Uses integer module sizing to guarantee rapid optical scanning.
    """
    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=box_size,
        border=border,
    )
    qr.add_data(url)
    qr.make(fit=True)
    return qr.make_image(fill_color="black", back_color="white").convert("RGB")


def get_whatsapp_qr_code_image(box_size=2, border=2):
    """
    Generates a pixel-perfect, crisp, 100% scannable QR Code for the official WhatsApp Channel.
    Uses integer module sizing (box_size=2, border=2 -> 74x74 px) to guarantee rapid optical scanning.
    """
    return get_qr_code_image(WHATSAPP_CHANNEL_URL, box_size=box_size, border=border)


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


try:
    _RUPEE = "\u20b9" if get_font(FONT_BOLD, 30).getmask("\u20b9").getbbox() else "Rs "
except Exception:
    _RUPEE = "Rs "


def _parse_salary(job):
    """Extract Level-N and pay-range text from a job's details/qualification."""
    blob = " ".join(str(job.get(k) or "") for k in ("details", "qualification", "title"))
    level = ""
    m = re.search(r"Level\s*[-\xE2\x80\x93]?\s*(\d+)", blob, re.IGNORECASE)
    if m:
        level = "Level-" + m.group(1)
    rng = ""
    m = re.search(r"(\d[\d,]{2,})\s*[-\xE2\x80\x93\xE2\x80\x94]\s*(\d[\d,]{2,})", blob)
    if m:
        a, b = m.group(1), m.group(2)
        try:
            av, bv = int(a.replace(",", "")), int(b.replace(",", ""))
            if 8000 <= av < bv <= 10000000:
                rng = _RUPEE + a + " \u2013 " + _RUPEE + b
        except ValueError:
            pass
    return level, rng


# --- small white vector icons for card headers (2x scale) --------------------
def _icon_people(d, cx, cy, s, color):
    d.ellipse([cx - s, cy - s, cx - s * 0.2, cy - s * 0.15], fill=color)
    d.chord([cx - s * 1.5, cy - s * 0.1, cx + s * 0.3, cy + s * 1.1], start=180, end=360, fill=color)
    d.ellipse([cx + s * 0.35, cy - s * 0.85, cx + s * 1.05, cy - s * 0.05], fill=color)
    d.chord([cx - s * 0.1, cy - s * 0.05, cx + s * 1.5, cy + s * 1.1], start=180, end=360, fill=color)


def _icon_cap(d, cx, cy, s, color):
    d.polygon([(cx - s * 1.4, cy - s * 0.2), (cx, cy - s * 0.9), (cx + s * 1.4, cy - s * 0.2),
               (cx, cy + s * 0.5)], fill=color)
    d.rectangle([cx - s, cy + s * 0.25, cx + s, cy + s * 0.55], fill=color)
    d.line([(cx + s * 1.4, cy - s * 0.2), (cx + s * 1.4, cy + s * 0.7)], fill=color, width=3)
    d.ellipse([cx + s * 1.3, cy + s * 0.7, cx + s * 1.5, cy + s * 0.9], fill=color)


def _icon_calendar(d, cx, cy, s, color):
    d.rounded_rectangle([cx - s, cy - s * 0.8, cx + s, cy + s], radius=4, outline=color, width=3)
    d.rectangle([cx - s, cy - s * 0.35, cx + s, cy + s * 0.05], fill=color)
    d.line([(cx - s * 0.55, cy - s * 1.1), (cx - s * 0.55, cy - s * 0.6)], fill=color, width=3)
    d.line([(cx + s * 0.55, cy - s * 1.1), (cx + s * 0.55, cy - s * 0.6)], fill=color, width=3)


def _icon_rupee(d, cx, cy, s, color):
    f = get_font(FONT_BOLD, int(s * 1.7))
    d.text((cx, cy), "\u20b9", font=f, fill=color, anchor="mm")


def _icon_person(d, cx, cy, s, color):
    d.ellipse([cx - s * 0.5, cy - s, cx + s * 0.5, cy], fill=color)
    d.chord([cx - s * 0.95, cy + s * 0.05, cx + s * 0.95, cy + s * 1.4], start=180, end=360, fill=color)


def _icon_doc(d, cx, cy, s, color):
    d.rounded_rectangle([cx - s * 0.75, cy - s, cx + s * 0.75, cy + s], radius=4, outline=color, width=3)
    d.line([(cx - s * 0.4, cy - s * 0.45), (cx + s * 0.4, cy - s * 0.45)], fill=color, width=3)
    d.line([(cx - s * 0.4, cy), (cx + s * 0.4, cy)], fill=color, width=3)
    d.line([(cx - s * 0.4, cy + s * 0.45), (cx + s * 0.1, cy + s * 0.45)], fill=color, width=3)


def _icon_monitor(d, cx, cy, s, color):
    d.rounded_rectangle([cx - s, cy - s * 0.75, cx + s, cy + s * 0.35], radius=4, outline=color, width=3)
    d.line([(cx, cy + s * 0.35), (cx, cy + s * 0.75)], fill=color, width=3)
    d.line([(cx - s * 0.5, cy + s * 0.75), (cx + s * 0.5, cy + s * 0.75)], fill=color, width=3)


def _icon_bell(d, cx, cy, s, color):
    d.pieslice([cx - s * 0.7, cy - s * 0.8, cx + s * 0.7, cy + s * 0.6], start=180, end=360, fill=color)
    d.rectangle([cx - s * 0.85, cy - s * 0.15, cx + s * 0.85, cy + s * 0.05], fill=color)
    d.ellipse([cx - s * 0.2, cy + s * 0.15, cx + s * 0.2, cy + s * 0.55], fill=color)


CARD_ICONS = {"people": _icon_people, "cap": _icon_cap, "calendar": _icon_calendar,
              "rupee": _icon_rupee, "person": _icon_person, "doc": _icon_doc,
              "monitor": _icon_monitor}


def generate_job_thumbnail(
    job_data,
    output_path,
    channel_name="EmploymentExpress",
    subscribe_text="SUBSCRIBE FOR DAILY GOVT ALERTS",
    visual_key=None,
    show_building=True
):
    """
    Generates the example-style 1200x630 share card (2x super-sampled at
    2400x1260, Lanczos downscale) matching the user's reference prompt:

      TOP (35%):    navy gradient + blended institute visual (optional),
                    website logo + department name, 3-line headline
                    (org: yellow+white / post: black on yellow banner /
                    alert: white on red banner)
      MIDDLE (50%): 3 big cards (TOTAL VACANCY red, QUALIFICATION green,
                    LAST DATE royal blue) + 4 small cards (SALARY purple,
                    AGE LIMIT orange, APPLICATION FEE teal,
                    SELECTION PROCESS magenta)
      PROMO BAR:    navy - YouTube promo + QR (left), WhatsApp promo + QR
                    (right)
      FOOTER:       yellow strip - Like | Share | Subscribe
    """
    w2, h2 = 2400, 1260
    canvas = Image.new("RGBA", (w2, h2), (255, 255, 255, 255))
    draw = ImageDraw.Draw(canvas)

    NAVY = "#071C38"
    NAVY_TOP = "#0b2545"
    NAVY_DEEP = "#04101F"
    YELLOW = "#FFD800"
    RED = "#E10600"
    RED_NUM = "#D71919"
    GREEN = "#0B6B35"
    BLUE = "#1D4ED8"
    PURPLE = "#5B259F"
    ORANGE = "#F06A00"
    TEAL = "#087D85"
    MAGENTA = "#C90062"
    CARD_BG = "#F5F5F5"
    MID_BG = "#E8ECF2"
    TEXT = "#111111"
    SLATE = "#334155"
    SHADOW = "#B9C2D0"

    org_code = str(job_data.get("org_code", "GOVT")).upper()
    org_full = str(job_data.get("org_full", "GOVERNMENT RECRUITMENT")).upper()
    main_title = str(job_data.get("main_title", "RECRUITMENT")).upper()
    ribbon_alert = str(job_data.get("ribbon_alert", "OFFICIAL NOTIFICATION 2026")).upper()
    alert_type = job_data.get("alert_type", "recruitment")
    vac_number = str(job_data.get("vacancy_badge_number") or job_data.get("vacancies_count") or "").strip()
    vac_label = str(job_data.get("vacancy_badge_label") or "POSTS").upper()

    qualification = str(job_data.get("qualification") or "").strip()
    age_limit = str(job_data.get("age_limit") or "").strip()
    apply_mode = str(job_data.get("apply_mode") or "Online").strip()
    exam_note = str(job_data.get("exam_note") or "").strip()
    fee_lines = [str(l) for l in (job_data.get("fee_lines") or ["See Official Notification"])]
    date_parts = job_data.get("date_parts")
    last_date_raw = str(job_data.get("last_date_raw") or "").strip()
    advt_no = str(job_data.get("advt_no") or "").strip()
    salary_level = str(job_data.get("salary_level") or "").strip()
    salary_range = str(job_data.get("salary_range") or "").strip()

    hl = job_data.get("highlights") or {}
    if not qualification:
        for k in ("Result For", "Answer Key For", "Admit Card For", "Course",
                  "Qualification", "Post Name"):
            if hl.get(k):
                qualification = str(hl[k])
                break
        qualification = qualification or "See Official Notification"
    if not age_limit and alert_type in ("recruitment", "admission"):
        age_limit = "As Per Notification"

    is_recruit = alert_type in ("recruitment", "admission")
    notice_word = {"result": "RESULT OUT", "answer_key": "ANSWER KEY",
                   "admit_card": "ADMIT CARD", "admission": "ADMISSION"}.get(alert_type, "NEW NOTICE")
    notice_type_word = {"result": "RESULT DECLARED", "answer_key": "ANSWER KEY OUT",
                        "admit_card": "ADMIT CARD OUT", "admission": "ADMISSION NOTICE"}.get(alert_type, "NOTICE")

    # ================================================================ TOP 35%
    top_h = 440
    navy_top_rgb = tuple(int(NAVY_TOP[i + 1:i + 3], 16) for i in (0, 2, 4))
    navy_rgb0 = tuple(int(NAVY[i + 1:i + 3], 16) for i in (0, 2, 4))
    for y in range(top_h):
        t = y / (top_h - 1)
        c = tuple(int(navy_top_rgb[k] + (navy_rgb0[k] - navy_top_rgb[k]) * t) for k in range(3))
        draw.line([(0, y), (w2, y)], fill=c + (255,))

    # Blended institute visual (right side). The image stays clearly visible:
    # only a short fade at its left edge blends it into the navy background
    # (heavy overlays made the picture invisible in earlier revisions).
    if show_building:
        visual_path = resolve_visual_path(visual_key or job_data.get("visual_key"),
                                          job_title=main_title, job_dept=org_full)
        try:
            vis = Image.open(visual_path).convert("RGB")
            vx1, vx2 = 1560, w2
            target_w, target_h = vx2 - vx1, top_h
            ratio = max(target_w / vis.width, target_h / vis.height)
            vis = vis.resize((int(vis.width * ratio) + 1, int(vis.height * ratio) + 1), Image.LANCZOS)
            # top-anchored crop keeps the subject (person / building top) in view
            crop_y = int((vis.height - target_h) * 0.15)
            vis = vis.crop(((vis.width - target_w) // 2, crop_y,
                            (vis.width - target_w) // 2 + target_w, crop_y + target_h))
            canvas.paste(vis, (vx1, 0))
            # short fade on the left edge only + gentle bottom shade
            overlay = Image.new("RGBA", (target_w, top_h), (0, 0, 0, 0))
            odraw = ImageDraw.Draw(overlay)
            navy_rgb = tuple(int(NAVY[i + 1:i + 3], 16) for i in (0, 2, 4))
            fade_w = 340
            for x in range(min(fade_w, target_w)):
                alpha = int(255 * (1 - x / fade_w))
                odraw.line([(x, 0), (x, top_h)], fill=navy_rgb + (alpha,))
            for y in range(top_h):
                a = int(55 * (y / (top_h - 1)))
                if a:
                    odraw.line([(0, y), (target_w, y)], fill=navy_rgb + (a,))
            canvas = Image.alpha_composite(canvas, overlay)
            draw = ImageDraw.Draw(canvas)
        except Exception:
            pass  # keep plain navy gradient

    # Middle-section backdrop (drawn before the tilted banner so the banner
    # can visually bridge the two sections without being overpainted)
    draw.rectangle([0, top_h, w2, 1036], fill=MID_BG)

    # Website logo (yellow ring) - never an institution seal
    if (ASSETS_DIR / "logo.png").exists():
        logo_img = make_circular_masked_image(ASSETS_DIR / "logo.png", 240)
        if logo_img:
            canvas.paste(logo_img, (70, 42), mask=logo_img)
            draw = ImageDraw.Draw(canvas)
            draw.ellipse([70, 42, 310, 282], outline=YELLOW, width=8)

    # Department name under the logo
    d_lines, d_font = _wrap_words(draw, org_full, FONT_BOLD, 300, 3)
    dy = 300
    for ln in d_lines:
        draw.text((190, dy), ln, font=d_font, fill="#dce6f5", anchor="mm")
        dy += 36
    if advt_no:
        f_advt = get_font(FONT_BOLD, 22)
        draw.text((190, dy + 8), _clip(advt_no, 38), font=f_advt, fill="#93a8c7", anchor="mm")

    # ---- headline stack (x 420..1520)
    hx1, hx2 = 420, 1520
    hcx = (hx1 + hx2) // 2

    # L1: first word yellow, rest white
    words = org_code.split()
    l1_first = words[0] if words else org_code
    l1_rest = " ".join(words[1:])
    if len(l1_first) > 14:
        l1_first, l1_rest = l1_first[:12] + "...", ""
    elif len(org_code) > 22:
        l1_first, l1_rest = org_code, ""
    f_l1 = fit_text_font(draw, (l1_first + " " + l1_rest).strip(), max_w=hx2 - hx1, max_h=104,
                         font_path=FONT_BOLD, start_size=120, min_size=60)
    if l1_rest:
        w_first = draw.textlength(l1_first + " ", font=f_l1)
        w_rest = draw.textlength(l1_rest, font=f_l1)
        total = w_first + w_rest
        x0 = hcx - total / 2
        draw.text((x0 + 4, 84 + 5), l1_first + " ", font=f_l1, fill=NAVY_DEEP, anchor="lm")
        draw.text((x0 + w_first + 4, 84 + 5), l1_rest, font=f_l1, fill=NAVY_DEEP, anchor="lm")
        draw.text((x0, 84), l1_first + " ", font=f_l1, fill=YELLOW, anchor="lm")
        draw.text((x0 + w_first, 84), l1_rest, font=f_l1, fill="#ffffff", anchor="lm")
    else:
        draw.text((hcx + 4, 84 + 5), l1_first, font=f_l1, fill=NAVY_DEEP, anchor="mm")
        draw.text((hcx, 84), l1_first, font=f_l1, fill=YELLOW, anchor="mm")

    # L2: main title - black on yellow banner. Long titles wrap to 2 lines so
    # they can never overflow the banner width (80/202 live titles need this).
    l2_max_w = hx2 - hx1 - 90
    f_single = fit_text_font(draw, main_title, max_w=l2_max_w, max_h=96,
                             font_path=FONT_BOLD, start_size=110, min_size=44)
    if f_single.size >= 64:
        # short title: one big line
        l2_lines, f_l2 = [main_title], f_single
    else:
        # long title: two lines with the largest font that fits both lines
        l2_lines, f_l2 = _wrap_words(draw, main_title, FONT_BOLD, l2_max_w, 2)
        widest = max(draw.textlength(ln, font=f_l2) for ln in l2_lines)
        while widest > l2_max_w and f_l2.size > 36:
            f_l2 = get_font(FONT_BOLD, f_l2.size - 4)
            widest = max(draw.textlength(ln, font=f_l2) for ln in l2_lines)
    l2_w = max(draw.textlength(ln, font=f_l2) for ln in l2_lines)
    bx1 = max(hx1 - 20, int(hcx - l2_w / 2 - 40))
    bx2 = min(hx2 + 20, int(hcx + l2_w / 2 + 40))
    if len(l2_lines) == 1:
        draw.rectangle([bx1 + 6, 148 + 7, bx2 + 6, 262 + 7], fill=NAVY_DEEP)      # shadow
        draw.rectangle([bx1, 148, bx2, 262], fill=YELLOW)
        draw.text((hcx, 205), l2_lines[0], font=f_l2, fill=TEXT, anchor="mm")
    else:
        draw.rectangle([bx1 + 6, 136 + 7, bx2 + 6, 300 + 7], fill=NAVY_DEEP)      # shadow
        draw.rectangle([bx1, 136, bx2, 300], fill=YELLOW)
        draw.text((hcx, 180), l2_lines[0], font=f_l2, fill=TEXT, anchor="mm")
        draw.text((hcx, 254), l2_lines[1], font=f_l2, fill=TEXT, anchor="mm")

    # L3: alert banner - white on red (straight, shadowed; sits clear of both
    # the yellow banner above and the cards below)
    f_l3 = fit_text_font(draw, ribbon_alert, max_w=hx2 - hx1 - 130, max_h=80,
                         font_path=FONT_BOLD, start_size=88, min_size=42)
    l3_w = draw.textlength(ribbon_alert, font=f_l3)
    rb_x1 = max(hx1 - 20, int(hcx - l3_w / 2 - 55))
    rb_x2 = min(hx2 + 20, int(hcx + l3_w / 2 + 55))
    draw.rounded_rectangle([rb_x1 + 6, 318 + 7, rb_x2 + 6, 424 + 7], radius=20, fill=NAVY_DEEP)
    draw.rounded_rectangle([rb_x1, 318, rb_x2, 424], radius=20, fill=RED)
    draw.text((hcx, 371), ribbon_alert, font=f_l3, fill="#ffffff", anchor="mm")

    # ============================================================== MIDDLE
    def card(x1, y1, x2, y2, color, label, icon, head_h=62):
        draw.rounded_rectangle([x1 + 7, y1 + 9, x2 + 7, y2 + 9], radius=18, fill=SHADOW)
        draw.rounded_rectangle([x1, y1, x2, y2], radius=18, fill=CARD_BG, outline=color, width=5)
        draw.rounded_rectangle([x1, y1, x2, y1 + head_h], radius=18, fill=color)
        draw.rectangle([x1, y1 + head_h - 22, x2, y1 + head_h], fill=color)
        # icon in white-ring circle
        cx0, cy0 = x1 + 48, y1 + head_h // 2
        draw.ellipse([cx0 - 25, cy0 - 25, cx0 + 25, cy0 + 25], outline="#ffffff", width=3)
        CARD_ICONS[icon](draw, cx0, cy0, 14, "#ffffff")
        f_lbl = get_font(FONT_BOLD, 34)
        draw.text((x1 + 88, cy0), label, font=f_lbl, fill="#ffffff", anchor="lm")

    # ---- Row 1: three big cards (y 460..790)
    r1y1, r1y2 = 460, 790
    c1x1, c1x2 = 40, 793
    c2x1, c2x2 = 823, 1576
    c3x1, c3x2 = 1606, 2360

    if vac_number and vac_number not in ("NEW",):
        card(c1x1, r1y1, c1x2, r1y2, RED, "TOTAL VACANCY", "people")
        f_num = fit_text_font(draw, vac_number, max_w=430, max_h=126,
                              font_path=FONT_BOLD, start_size=160, min_size=72)
        draw.text(((c1x1 + c1x2) // 2, 640), vac_number, font=f_num, fill=RED_NUM, anchor="mm")
        # 'Posts' navy pill
        f_pl = get_font(FONT_BOLD, 30)
        pl_w = int(draw.textlength(vac_label, font=f_pl)) + 70
        draw.rounded_rectangle([(c1x1 + c1x2) / 2 - pl_w / 2, 726,
                                (c1x1 + c1x2) / 2 + pl_w / 2, 774], radius=24, fill=NAVY)
        draw.text(((c1x1 + c1x2) // 2, 750), vac_label, font=f_pl, fill="#ffffff", anchor="mm")
    else:
        card(c1x1, r1y1, c1x2, r1y2, RED, "NOTICE", "people")
        f_nw = fit_text_font(draw, notice_word, max_w=440, max_h=84,
                             font_path=FONT_BOLD, start_size=92, min_size=48)
        draw.text(((c1x1 + c1x2) // 2, 655), notice_word, font=f_nw, fill=RED_NUM, anchor="mm")

    q_label = "QUALIFICATION" if is_recruit else "POST / NOTICE DETAILS"
    card(c2x1, r1y1, c2x2, r1y2, GREEN, q_label, "cap")
    qcx = (c2x1 + c2x2) // 2
    q_body_top, q_body_bot = 584, 782          # inside the card, under its header
    q_max_w = c2x2 - c2x1 - 70
    q_parts = re.split(r"\s+OR\s+", qualification, flags=re.IGNORECASE) if qualification else []
    if len(q_parts) == 2 and all(len(p) < 90 for p in q_parts):
        # Two qualification options separated by a green OR pill.
        # Line budget: at most 3 text lines + the pill must fit 584..782.
        p1_lines, p1_font = _wrap_words(draw, q_parts[0], FONT_BOLD, q_max_w, 2)
        p2_lines, p2_font = _wrap_words(draw, q_parts[1], FONT_BOLD, q_max_w, 2)
        if len(p1_lines) + len(p2_lines) > 3:
            # give the longer part 2 lines, force the shorter to 1 (shrunk to fit)
            if len(q_parts[0]) >= len(q_parts[1]):
                p1_lines, p1_font = _wrap_words(draw, q_parts[0], FONT_BOLD, q_max_w, 2)
                p2_lines = [q_parts[1]]
                p2_font = fit_text_font(draw, q_parts[1], max_w=q_max_w, max_h=44,
                                        font_path=FONT_BOLD, start_size=44, min_size=24)
            else:
                p2_lines, p2_font = _wrap_words(draw, q_parts[1], FONT_BOLD, q_max_w, 2)
                p1_lines = [q_parts[0]]
                p1_font = fit_text_font(draw, q_parts[0], max_w=q_max_w, max_h=44,
                                        font_path=FONT_BOLD, start_size=44, min_size=24)
        lh = 46
        f_or = get_font(FONT_BOLD, 28)
        or_w = int(draw.textlength("OR", font=f_or)) + 44
        total_h = lh * (len(p1_lines) + len(p2_lines)) + 52
        y = q_body_top + (q_body_bot - q_body_top - total_h) / 2 + lh / 2
        for ln in p1_lines:
            draw.text((qcx, y), ln, font=p1_font, fill=TEXT, anchor="mm"); y += lh
        draw.rounded_rectangle([qcx - or_w / 2, y - 14, qcx + or_w / 2, y + 28], radius=21, fill=GREEN)
        draw.text((qcx, y + 7), "OR", font=f_or, fill="#ffffff", anchor="mm")
        y += 52
        for ln in p2_lines:
            draw.text((qcx, y), ln, font=p2_font, fill=TEXT, anchor="mm"); y += lh
    else:
        # Single blob of text: wrap to at most 4 lines, font capped so the
        # whole block stays inside the card body.
        q_lines, q_font = _wrap_words(draw, qualification or "See Official Notification", FONT_BOLD,
                                      q_max_w, 4)
        if q_font.size > 44:
            q_font = get_font(FONT_BOLD, 44)
        lh = 46
        total_h = lh * len(q_lines)
        qy = q_body_top + (q_body_bot - q_body_top - total_h) / 2 + lh / 2
        for ln in q_lines:
            draw.text((qcx, qy), ln, font=q_font, fill=TEXT, anchor="mm"); qy += lh

    ld_label = "LAST DATE" if (is_recruit and date_parts) else ("NOTICE DATE" if date_parts else "STATUS")
    card(c3x1, r1y1, c3x2, r1y2, BLUE, ld_label, "calendar")
    lcx = (c3x1 + c3x2) // 2
    if date_parts:
        day, mon, yr = date_parts
        f_day = fit_text_font(draw, day, max_w=300, max_h=118, font_path=FONT_BOLD,
                              start_size=150, min_size=76)
        draw.text((lcx, 620), day, font=f_day, fill=RED_NUM, anchor="mm")
        f_my = get_font(FONT_BOLD, 56)
        draw.text((lcx, 730), str(mon) + " " + str(yr), font=f_my, fill=NAVY, anchor="mm")
    else:
        big_word = {"result": "OUT NOW", "answer_key": "OUT NOW",
                    "admit_card": "RELEASED"}.get(alert_type, "NEW")
        f_bw = fit_text_font(draw, big_word, max_w=520, max_h=104, font_path=FONT_BOLD,
                             start_size=130, min_size=60)
        draw.text((lcx, 620), big_word, font=f_bw, fill=RED_NUM, anchor="mm")
        f_sub = get_font(FONT_BOLD, 34)
        draw.text((lcx, 726), "CHECK OFFICIAL SITE", font=f_sub, fill=NAVY, anchor="mm")

    # ---- Row 2: four small cards (y 810..1030)
    r2y1, r2y2 = 810, 1030
    gap, mx = 24, 40
    cw = (w2 - 2 * mx - 3 * gap) // 4
    xs = [mx + i * (cw + gap) for i in range(4)]

    # Card 4: SALARY (purple) - or ORGANISATION for notices
    if is_recruit:
        card(xs[0], r2y1, xs[0] + cw, r2y2, PURPLE, "SALARY", "rupee", head_h=56)
        scx = xs[0] + cw // 2
        if salary_level:
            f_lv = get_font(FONT_BOLD, 30)
            draw.text((scx, 890), salary_level, font=f_lv, fill=SLATE, anchor="mm")
        s_text = salary_range or "As Per Notification"
        f_sal = fit_text_font(draw, s_text, max_w=cw - 60, max_h=52, font_path=FONT_BOLD,
                              start_size=48, min_size=26)
        s_w = draw.textlength(s_text, font=f_sal)
        draw.rectangle([scx - s_w / 2 - 16, 932, scx + s_w / 2 + 16, 992], fill=YELLOW)
        draw.text((scx, 962), s_text, font=f_sal, fill=TEXT, anchor="mm")
    else:
        card(xs[0], r2y1, xs[0] + cw, r2y2, PURPLE, "ORGANISATION", "rupee", head_h=56)
        o_lines, o_font = _wrap_words(draw, org_full, FONT_BOLD, cw - 50, 3)
        oy = 950 - (len(o_lines) - 1) * 18
        for ln in o_lines:
            draw.text((xs[0] + cw // 2, oy), ln, font=o_font, fill=TEXT, anchor="mm"); oy += 40

    # Card 5: AGE LIMIT (orange) - or NOTICE TYPE for notices
    if is_recruit:
        card(xs[1], r2y1, xs[1] + cw, r2y2, ORANGE, "AGE LIMIT", "person", head_h=56)
        acx = xs[1] + cw // 2
        age_text = age_limit or "As Per Notification"
        a_lines, a_font = _wrap_words(draw, age_text, FONT_BOLD, cw - 50, 2)
        ay = 908 if len(a_lines) > 1 else 916
        for ln in a_lines:
            draw.text((acx, ay), ln, font=a_font, fill=TEXT, anchor="mm"); ay += 48
        f_rel = get_font(FONT_BOLD, 22)
        draw.text((acx, 1000), "(Age Relaxation Applicable)", font=f_rel, fill=SLATE, anchor="mm")
    else:
        card(xs[1], r2y1, xs[1] + cw, r2y2, ORANGE, "NOTICE TYPE", "person", head_h=56)
        f_nt = fit_text_font(draw, notice_type_word, max_w=cw - 50, max_h=60,
                             font_path=FONT_BOLD, start_size=56, min_size=30)
        draw.text((xs[1] + cw // 2, 930), notice_type_word, font=f_nt, fill=TEXT, anchor="mm")
        f_nt2 = get_font(FONT_BOLD, 24)
        draw.text((xs[1] + cw // 2, 1000), "Official Update 2026", font=f_nt2, fill=SLATE, anchor="mm")

    # Card 6: APPLICATION FEE (teal) - amounts highlighted red. Every line is
    # individually fitted to the card width so text can never spill out.
    card(xs[2], r2y1, xs[2] + cw, r2y2, TEAL, "APPLICATION FEE", "doc", head_h=56)
    fcx = xs[2] + cw // 2
    fee_max_w = cw - 44
    fee_items = fee_lines[:3]
    fee_fonts = []
    for ln in fee_items:
        fee_fonts.append(fit_text_font(draw, ln, max_w=fee_max_w, max_h=40,
                                       font_path=FONT_BOLD, start_size=28, min_size=16))
    fy = 884 + (146 - 46 * len(fee_items)) / 2 + 4
    for ln, f_fee in zip(fee_items, fee_fonts):
        if ":" in ln:
            key_part, val_part = ln.split(":", 1)
            kw = draw.textlength(key_part + ": ", font=f_fee)
            vw = draw.textlength(val_part.strip(), font=f_fee)
            x0 = fcx - (kw + vw) / 2
            # left-anchored so the key starts at x0 and the value follows it -
            # centre-anchored parts overlapped each other and spilled left
            draw.text((x0, fy), key_part + ": ", font=f_fee, fill=TEXT, anchor="lm")
            draw.text((x0 + kw, fy), val_part.strip(), font=f_fee, fill=RED_NUM, anchor="lm")
        else:
            draw.text((fcx, fy), ln, font=f_fee, fill=TEXT, anchor="mm")
        fy += 46

    # Card 7: SELECTION PROCESS (magenta)
    card(xs[3], r2y1, xs[3] + cw, r2y2, MAGENTA, "SELECTION PROCESS", "monitor", head_h=56)
    spx = xs[3] + cw // 2
    sel_text = exam_note or "As Per Official Notification"
    s_lines, s_font = _wrap_words(draw, sel_text, FONT_BOLD, cw - 50, 2)
    sy = 910 if len(s_lines) > 1 else 918
    for ln in s_lines:
        draw.text((spx, sy), ln, font=s_font, fill=TEXT, anchor="mm"); sy += 46
    badge_txt = "(No Interview)" if "no interview" in sel_text.lower() else "As Notified"
    f_bd = get_font(FONT_BOLD, 22)
    bd_w = int(draw.textlength(badge_txt, font=f_bd)) + 36
    draw.rounded_rectangle([spx - bd_w / 2, 986, spx + bd_w / 2, 1020], radius=17, fill=MAGENTA)
    draw.text((spx, 1003), badge_txt, font=f_bd, fill="#ffffff", anchor="mm")

    # ============================================================ PROMO BAR
    pb_y1, pb_y2 = 1036, 1206
    draw.rectangle([0, pb_y1, w2, pb_y2], fill=NAVY)
    draw.rectangle([0, pb_y1, w2, pb_y1 + 4], fill=YELLOW)

    f_pb1 = get_font(FONT_BOLD, 32)
    f_pb2 = get_font(FONT_BOLD, 38)

    # LEFT - YouTube
    draw.rounded_rectangle([60, 1074, 168, 1182], radius=20, fill="#ff0000")
    draw.polygon([(92, 1098), (146, 1128), (92, 1158)], fill="#ffffff")
    draw.text((196, 1078), "Subscribe My", font=f_pb1, fill="#ffffff", anchor="lm")
    draw.text((196, 1116), "YouTube Channel", font=f_pb1, fill="#ffffff", anchor="lm")
    ch_w = int(draw.textlength(channel_name, font=f_pb2)) + 76
    draw.rounded_rectangle([196, 1140, 196 + ch_w, 1192], radius=26, fill=RED)
    draw.text((196 + ch_w / 2, 1166), channel_name, font=f_pb2, fill="#ffffff", anchor="mm")
    _icon_bell(draw, 196 + ch_w + 40, 1166, 20, YELLOW)
    # YouTube QR zone (2x): x 1000..1148, y 1044..1192 -> crisp paste at final
    draw.text((1074, 1196), "SCAN & SUBSCRIBE", font=get_font(FONT_BOLD, 18), fill="#ffffff", anchor="mm")

    # RIGHT - WhatsApp (badge/texts stay left of the QR zone x2212..2360)
    draw_whatsapp_badge(draw, 2150, 1128, 40)
    draw.text((2090, 1078), "Follow My", font=f_pb1, fill="#ffffff", anchor="rm")
    draw.text((2090, 1116), "WhatsApp Channel", font=f_pb1, fill="#ffffff", anchor="rm")
    btn_w = int(draw.textlength("Scan & Join", font=f_pb2)) + 70
    draw.rounded_rectangle([2090 - btn_w, 1140, 2090, 1192], radius=26, fill="#16a34a")
    draw.text((2090 - btn_w / 2, 1166), "Scan & Join", font=f_pb2, fill="#ffffff", anchor="mm")
    # WhatsApp QR zone (2x): x 2212..2360, y 1044..1192
    draw.text((2286, 1196), "SCAN & JOIN", font=get_font(FONT_BOLD, 18), fill="#ffffff", anchor="mm")

    # ========================================================= YELLOW FOOTER
    draw.rectangle([0, 1206, w2, h2], fill=YELLOW)
    f_foot = get_font(FONT_BOLD, 38)
    draw.text((w2 // 2, 1233), "Like  |  Share  |  Subscribe", font=f_foot, fill=TEXT, anchor="mm")
    # red decorative bursts on both sides
    for sx in (w2 // 2 - 470, w2 // 2 + 470):
        draw.polygon([(sx, 1218), (sx + 46, 1233), (sx, 1248)], fill=RED)
        draw.polygon([(sx - 56, 1218), (sx - 10, 1233), (sx - 56, 1248)], fill=RED)

    # ------------------------------- downsample to 1200x630 (Lanczos)
    final_img = canvas.convert("RGB").resize((1200, 630), Image.Resampling.LANCZOS)
    final_img = final_img.quantize(colors=256, method=Image.MEDIANCUT).convert("RGB")

    # Crisp-paste both scannable QR codes (74x74, integer modules) at final
    # scale - palette quantization first so dithering cannot corrupt modules.
    yt_qr = get_qr_code_image(YOUTUBE_CHANNEL_URL, box_size=2, border=2)
    wa_qr = get_whatsapp_qr_code_image(box_size=2, border=2)
    yt_cx, yt_cy = (1000 + 1148) // 4, (1044 + 1192) // 4     # 2x zone -> final centre
    wa_cx, wa_cy = (2212 + 2360) // 4, (1044 + 1192) // 4
    final_img.paste(yt_qr, (yt_cx - yt_qr.width // 2, yt_cy - yt_qr.height // 2))
    final_img.paste(wa_qr, (wa_cx - wa_qr.width // 2, wa_cy - wa_qr.height // 2))

    master_qr_path = ASSETS_DIR / "whatsapp_channel_qr.png"
    if not master_qr_path.exists():
        qr_master = get_whatsapp_qr_code_image(box_size=8, border=2)
        qr_master.save(master_qr_path, "PNG")

    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    final_img.save(output_path, "PNG", optimize=True)
    print("Generated thumbnail successfully: " + str(output_path))
    return str(output_path)


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


_MONTHS = ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"]


def parse_date_parts(raw):
    """Split a job date string ('18-09-2026', '03.10.2026', ISO…) into
    (day, 'MON', 'YEAR') big-box parts, or None when not a concrete date."""
    if not raw:
        return None
    text = str(raw).strip().split("T")[0]
    low = text.lower()
    if "see" in low or "not" in low or text == "-":
        return None
    m = re.search(r"(\d{1,2})[-/.](\d{1,2})[-/.](\d{2,4})", text)
    if m:
        d, mon, yr = int(m.group(1)), int(m.group(2)), m.group(3)
        if 1 <= mon <= 12 and 1 <= d <= 31:
            if len(yr) == 2:
                yr = "20" + yr
            return str(d), _MONTHS[mon - 1], yr
    m = re.search(r"(\d{4})-(\d{2})-(\d{2})", text)
    if m:
        yr, mon, d = m.groups()
        if 1 <= int(mon) <= 12 and 1 <= int(d) <= 31:
            return str(int(d)), _MONTHS[int(mon) - 1], yr
    return None


def _clip(text, limit):
    text = str(text or "").strip()
    if not text:
        return ""
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def _wrap_words(draw, text, font_path, max_w, max_lines):
    """Word-wrap ``text`` into at most ``max_lines`` lines that each fit
    ``max_w`` at a font size chosen by fitting the longest candidate line.
    Returns (lines, font)."""
    words = str(text or "").split()
    if not words:
        return [""], get_font(font_path, 20)

    def layout(size):
        font = get_font(font_path, size)
        lines, cur = [], ""
        for w in words:
            cand = (cur + " " + w).strip()
            if cur and draw.textlength(cand, font=font) > max_w:
                lines.append(cur)
                cur = w
            else:
                cur = cand
        if cur:
            lines.append(cur)
        return lines, font

    for size in (52, 48, 44, 40, 36, 32, 28, 24, 20):
        lines, font = layout(size)
        if len(lines) <= max_lines and all(draw.textlength(l, font=font) <= max_w for l in lines):
            if len(lines) == max_lines and len(words) > sum(len(l.split()) for l in lines):
                continue  # truncated: try smaller font so all words fit
            return lines[:max_lines], font
    lines, font = layout(20)
    return lines[:max_lines], font


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

    # --- Info-box data for the example-style card -----------------------------
    qualification = _clip(job.get("qualification"), 120)
    age_limit = _clip(job.get("age"), 60)
    apply_mode = _clip(job.get("applyMode") or "Online", 40)
    exam_note = _clip(job.get("examDate") or "As Per Official Notification", 90)
    salary_level, salary_range = _parse_salary(job)

    fee_lines = []
    fee_gen = _clip(job.get("feeGen"), 36)
    fee_sc = _clip(job.get("feeSC"), 36)
    if fee_gen:
        fee_lines.append(f"General: {fee_gen}")
    if fee_sc and fee_sc != fee_gen:
        fee_lines.append(f"SC/ST/BC: {fee_sc}")
    if not fee_lines:
        fee_lines = ["See Official Notification"]

    date_parts = parse_date_parts(job.get("lastDate"))
    if not date_parts:
        pub_raw = str(job.get("publishedAt") or "")
        date_parts = parse_date_parts(pub_raw)

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
        "qualification": qualification,
        "age_limit": age_limit,
        "apply_mode": apply_mode,
        "exam_note": exam_note,
        "fee_lines": fee_lines,
        "date_parts": date_parts,
        "last_date_raw": _clip(job.get("lastDate"), 40),
        "advt_no": advt,
        "salary_level": salary_level,
        "salary_range": salary_range,
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
