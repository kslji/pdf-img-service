# tests/test_on_real_pdf.py
import unittest
import io
import fitz
import os
from PIL import Image
from app.services.pdf_advanced_processor import (
    convert_pdf_to_images,
    convert_images_to_pdf,
    crop_pdf,
    redact_pdf,
    add_page_numbers,
    sign_pdf,
    unlock_pdf,
)

PDF_PATH = "/Users/arjunsingh/Desktop/tools/pdf-image-service/Kabir_Singh_Lamba copy.pdf"

class TestRealPDF(unittest.TestCase):
    def setUp(self):
        if not os.path.exists(PDF_PATH):
            self.skipTest(f"PDF file not found at: {PDF_PATH}")
        with open(PDF_PATH, "rb") as f:
            self.pdf_bytes = f.read()

    def test_all_services(self):
        print("\n--- Running Tests on Kabir_Singh_Lamba copy.pdf ---")
        
        # 1. Convert PDF to Image
        print("Testing convert_pdf_to_images...")
        zip_bytes = convert_pdf_to_images(self.pdf_bytes, fmt="png", dpi=72)
        self.assertGreater(len(zip_bytes), 0)
        print(f"✓ convert_pdf_to_images: Success (zip size: {len(zip_bytes)} bytes)")

        # Extract an image from the ZIP to use for images-to-pdf
        import zipfile
        with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
            namelist = zf.namelist()
            self.assertTrue(len(namelist) > 0)
            first_image_bytes = zf.read(namelist[0])

        # 2. Convert Images to PDF
        print("Testing convert_images_to_pdf...")
        stitched_pdf = convert_images_to_pdf([first_image_bytes])
        self.assertGreater(len(stitched_pdf), 0)
        print(f"✓ convert_images_to_pdf: Success (pdf size: {len(stitched_pdf)} bytes)")

        # 3. Crop PDF
        print("Testing crop_pdf...")
        # Crop page 1 (points)
        cropped_pts = crop_pdf(self.pdf_bytes, 10, 10, 500, 700, unit="points", pages="1")
        self.assertGreater(len(cropped_pts), 0)
        # Crop all pages (percentage)
        cropped_pct = crop_pdf(self.pdf_bytes, 5, 5, 90, 90, unit="percentage", pages="all")
        self.assertGreater(len(cropped_pct), 0)
        print("✓ crop_pdf: Success")

        # 4. Redact PDF
        print("Testing redact_pdf...")
        # We don't know the exact text, but let's try searching for "Kabir" or "Singh"
        redacted_bytes = redact_pdf(self.pdf_bytes, text_to_redact="Kabir")
        self.assertGreater(len(redacted_bytes), 0)
        print("✓ redact_pdf: Success")

        # 5. Page Number
        print("Testing add_page_numbers...")
        numbered_bytes = add_page_numbers(self.pdf_bytes, pattern="Page {page} of {total}")
        self.assertGreater(len(numbered_bytes), 0)
        print("✓ add_page_numbers: Success")

        # 6. Sign PDF
        print("Testing sign_pdf...")
        # Sign with text
        signed_text_bytes = sign_pdf(self.pdf_bytes, signature_text="Approved Lamba", page_num=1, x=50, y=50, width=150, height=30)
        self.assertGreater(len(signed_text_bytes), 0)
        
        # Sign with image
        img = Image.new("RGB", (60, 20), color="blue")
        img_buf = io.BytesIO()
        img.save(img_buf, format="PNG")
        signed_img_bytes = sign_pdf(self.pdf_bytes, signature_image_bytes=img_buf.getvalue(), page_num=1, x=50, y=100, width=60, height=20)
        self.assertGreater(len(signed_img_bytes), 0)
        print("✓ sign_pdf: Success")

        # 7. Unlock PDF
        print("Testing unlock_pdf (and encrypting a test copy)...")
        # Let's encrypt the PDF first
        doc = fitz.open(stream=self.pdf_bytes, filetype="pdf")
        encrypted_buf = io.BytesIO()
        doc.save(encrypted_buf, user_pw="lamba123", owner_pw="lamba123", encryption=fitz.PDF_ENCRYPT_AES_256)
        encrypted_bytes = encrypted_buf.getvalue()
        doc.close()
        
        # Now unlock it
        unlocked_bytes = unlock_pdf(encrypted_bytes, "lamba123")
        self.assertGreater(len(unlocked_bytes), 0)
        unlocked_doc = fitz.open(stream=unlocked_bytes, filetype="pdf")
        self.assertFalse(unlocked_doc.is_encrypted)
        unlocked_doc.close()
        print("✓ unlock_pdf: Success")
        print("---------------------------------------------")

if __name__ == "__main__":
    unittest.main()
