import unittest
import os
import tempfile
from pathlib import Path
from PIL import Image
import cv2

from scripts.thumbnail_generator import (
    generate_job_thumbnail,
    parse_job_for_thumbnail,
    draw_rounded_rect,
    draw_icon_circle,
    draw_vector_icon,
    get_font,
    get_whatsapp_qr_code_image,
    WHATSAPP_CHANNEL_URL,
    FONT_BOLD
)

class TestThumbnailGenerator(unittest.TestCase):
    def test_parse_job_for_thumbnail(self):
        job = {
            "title": "SSC — Combined Hindi Translators Examination (CHTE / JHT 2026)",
            "department": "Staff Selection Commission (SSC)",
            "vacancies": "303 Posts",
            "badge": "REVISED NOTIFICATION",
            "advtNo": "CHTE-2026",
            "lastDate": "18-09-2026",
            "applyMode": "Online CBT"
        }
        parsed = parse_job_for_thumbnail(job)
        self.assertEqual(parsed["org_code"], "SSC")
        self.assertEqual(parsed["vacancies_count"], "303")
        self.assertIn("Post Name", parsed["highlights"])
        self.assertEqual(parsed["cta_text"], "APPLY ONLINE")

    def test_generate_job_thumbnail_dimensions_youtube_and_whatsapp_qr(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            out_path = Path(tmpdir) / "test_thumb.png"
            job_data = {
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
            res = generate_job_thumbnail(
                job_data,
                out_path,
                channel_name="EmploymentExpress",
                subscribe_text="SUBSCRIBE FOR DAILY GOVT ALERTS"
            )
            self.assertTrue(out_path.exists())
            
            with Image.open(out_path) as img:
                self.assertEqual(img.size, (1200, 630))
                self.assertEqual(img.mode, "RGB")

            # Optical QR Scan verification via OpenCV
            detector = cv2.QRCodeDetector()
            cv_img = cv2.imread(str(out_path))
            decoded_text, pts, _ = detector.detectAndDecode(cv_img)
            self.assertEqual(decoded_text, WHATSAPP_CHANNEL_URL)

    def test_whatsapp_qr_code_image_generator(self):
        qr_img = get_whatsapp_qr_code_image(box_size=2, border=2)
        self.assertIsNotNone(qr_img)
        self.assertEqual(qr_img.size, (74, 74))

    def test_font_loader_fallback(self):
        font = get_font(FONT_BOLD, 24)
        self.assertIsNotNone(font)
        fallback = get_font("invalid/path/font.ttf", 24)
        self.assertIsNotNone(fallback)

if __name__ == "__main__":
    unittest.main()
