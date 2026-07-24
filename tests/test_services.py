# tests/test_services.py
import unittest
import io
import fitz
import json
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

class TestPDFServices(unittest.TestCase):
    def setUp(self):
        # Create a dummy 2-page PDF in memory
        doc = fitz.open()
        
        # Page 1
        page1 = doc.new_page(width=600, height=800)
        page1.insert_text(fitz.Point(100, 100), "Hello World", fontsize=20)
        page1.insert_text(fitz.Point(100, 200), "This is sensitive information: SECRET123", fontsize=14)
        
        # Page 2
        page2 = doc.new_page(width=600, height=800)
        page2.insert_text(fitz.Point(100, 100), "Page Two", fontsize=20)
        
        self.dummy_pdf_bytes = doc.write()
        doc.close()

    def test_convert_pdf_to_images(self):
        zip_bytes = convert_pdf_to_images(self.dummy_pdf_bytes, fmt="png", dpi=72)
        self.assertGreater(len(zip_bytes), 0)
        
        # Verify it's a zip file with 2 png images
        import zipfile
        with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
            namelist = zf.namelist()
            self.assertIn("page_1.png", namelist)
            self.assertIn("page_2.png", namelist)

    def test_convert_images_to_pdf(self):
        # Create 2 simple images
        img1 = Image.new("RGB", (100, 100), color="red")
        img2 = Image.new("RGBA", (150, 150), color="blue")
        
        buf1 = io.BytesIO()
        img1.save(buf1, format="PNG")
        buf2 = io.BytesIO()
        img2.save(buf2, format="PNG")
        
        pdf_bytes = convert_images_to_pdf([buf1.getvalue(), buf2.getvalue()])
        self.assertGreater(len(pdf_bytes), 0)
        
        # Check generated PDF pages
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        self.assertEqual(len(doc), 2)
        doc.close()

    def test_crop_pdf_points(self):
        # Crop page 1 to 300x400 at top-left (0,0)
        cropped_bytes = crop_pdf(self.dummy_pdf_bytes, 0, 0, 300, 400, unit="points", pages="1")
        doc = fitz.open(stream=cropped_bytes, filetype="pdf")
        
        page1 = doc.load_page(0)
        self.assertEqual(page1.rect.width, 300)
        self.assertEqual(page1.rect.height, 400)
        
        # Page 2 should be untouched
        page2 = doc.load_page(1)
        self.assertEqual(page2.rect.width, 600)
        self.assertEqual(page2.rect.height, 800)
        doc.close()

    def test_crop_pdf_percentage(self):
        # Crop all pages to 10% from top-left, with 50% width and height
        cropped_bytes = crop_pdf(self.dummy_pdf_bytes, 10, 10, 50, 50, unit="percentage", pages="all")
        doc = fitz.open(stream=cropped_bytes, filetype="pdf")
        
        for page in doc:
            self.assertEqual(page.rect.width, 300)  # 50% of 600
            self.assertEqual(page.rect.height, 400)  # 50% of 800
        doc.close()

    def test_redact_pdf_text(self):
        redacted_bytes = redact_pdf(self.dummy_pdf_bytes, text_to_redact="SECRET123")
        doc = fitz.open(stream=redacted_bytes, filetype="pdf")
        # Ensure text is no longer present
        text = doc.load_page(0).get_text()
        self.assertNotIn("SECRET123", text)
        doc.close()

    def test_redact_pdf_rect(self):
        # Redact the top area containing "Hello World"
        import json
        rects_json = json.dumps([
            {"page": 1, "x": 90, "y": 80, "width": 120, "height": 30, "unit": "points"}
        ])
        redacted_bytes = redact_pdf(self.dummy_pdf_bytes, rects_json=rects_json)
        doc = fitz.open(stream=redacted_bytes, filetype="pdf")
        text = doc.load_page(0).get_text()
        self.assertNotIn("Hello World", text)
        doc.close()

    def test_add_page_numbers(self):
        numbered_bytes = add_page_numbers(self.dummy_pdf_bytes, pattern="[{page}/{total}]")
        doc = fitz.open(stream=numbered_bytes, filetype="pdf")
        text1 = doc.load_page(0).get_text()
        text2 = doc.load_page(1).get_text()
        self.assertIn("[1/2]", text1)
        self.assertIn("[2/2]", text2)
        doc.close()

    def test_sign_pdf_text(self):
        signed_bytes = sign_pdf(self.dummy_pdf_bytes, signature_text="Arjun Singh", page_num=1, x=100, y=500, width=200, height=50)
        doc = fitz.open(stream=signed_bytes, filetype="pdf")
        text = doc.load_page(0).get_text()
        self.assertIn("Arjun Singh", text)
        doc.close()

    def test_sign_pdf_image(self):
        # Create a tiny signature image
        img = Image.new("RGB", (50, 20), color="black")
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        
        signed_bytes = sign_pdf(self.dummy_pdf_bytes, signature_image_bytes=buf.getvalue(), page_num=1, x=100, y=500, width=50, height=20)
        doc = fitz.open(stream=signed_bytes, filetype="pdf")
        # Ensure we can load page and not error
        self.assertEqual(len(doc), 2)
        doc.close()

    def test_unlock_pdf(self):
        # Create encrypted PDF
        doc = fitz.open()
        page = doc.new_page()
        page.insert_text(fitz.Point(100, 100), "Secret Content")
        
        # Save with password
        encrypted_buf = io.BytesIO()
        doc.save(encrypted_buf, user_pw="mypassword", owner_pw="mypassword", encryption=fitz.PDF_ENCRYPT_AES_256)
        encrypted_bytes = encrypted_buf.getvalue()
        doc.close()
        
        # Test unlock
        unlocked_bytes = unlock_pdf(encrypted_bytes, "mypassword")
        unlocked_doc = fitz.open(stream=unlocked_bytes, filetype="pdf")
        self.assertFalse(unlocked_doc.is_encrypted)
        text = unlocked_doc.load_page(0).get_text()
        self.assertIn("Secret Content", text)
        unlocked_doc.close()

    def test_redact_pdf_multiple_text(self):
        # The dummy PDF has "Hello World" on page 1 and "Page 2 Content" on page 2
        # Let's redact both terms
        redacted_bytes = redact_pdf(self.dummy_pdf_bytes, text_to_redact="Hello, Content")
        doc = fitz.open(stream=redacted_bytes, filetype="pdf")
        text1 = doc.load_page(0).get_text()
        text2 = doc.load_page(1).get_text()
        self.assertNotIn("Hello World", text1)
        self.assertNotIn("Page 2 Content", text2)
        doc.close()

    def test_redact_pdf_list_rect(self):
        # Test the list of lists coordinate format
        rects_json = json.dumps([
            [1, 90, 80, 120, 30]
        ])
        redacted_bytes = redact_pdf(self.dummy_pdf_bytes, rects_json=rects_json)
        doc = fitz.open(stream=redacted_bytes, filetype="pdf")
        text = doc.load_page(0).get_text()
        self.assertNotIn("Hello World", text)
        doc.close()

if __name__ == "__main__":
    unittest.main()
