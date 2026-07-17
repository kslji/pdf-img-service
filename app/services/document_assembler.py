import io
from PIL import Image
from pypdf import PdfReader, PdfWriter, PageObject
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader
import tempfile
from app.services.office_converter import docx_to_pdf


async def assemble_pdf(files: list[tuple[str, bytes, str]]) -> bytes:
    """
    files: list of (filename, contents, content_type)
    """
    writer = PdfWriter()
    for fname, content, mime in files:
        if mime.startswith("image/"):
            # Convert image to PDF page
            img = Image.open(io.BytesIO(content))
            # Create a single‑page PDF with the image
            img_pdf_bytes = image_to_pdf_page(img)
            reader = PdfReader(io.BytesIO(img_pdf_bytes))
            writer.add_page(reader.pages[0])
        elif mime == "application/pdf":
            reader = PdfReader(io.BytesIO(content))
            for page in reader.pages:
                writer.add_page(page)
        elif (
            mime
            == "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        ):
            pdf_content = await docx_to_pdf(content)
            reader = PdfReader(io.BytesIO(pdf_content))
            for page in reader.pages:
                writer.add_page(page)
        elif mime == "text/plain":
            # Convert TXT to PDF page
            pdf_content = text_to_pdf_page(content.decode("utf-8"))
            reader = PdfReader(io.BytesIO(pdf_content))
            writer.add_page(reader.pages[0])
        else:
            raise ValueError(f"Unsupported file type: {mime}")
    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


def image_to_pdf_page(image: Image.Image) -> bytes:
    # Use reportlab to create a PDF with the image fitting the page
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=(image.width, image.height))
    c.drawImage(ImageReader(image), 0, 0, width=image.width, height=image.height)
    c.showPage()
    c.save()
    return buf.getvalue()


def text_to_pdf_page(text: str) -> bytes:
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=(612, 792))
    c.drawString(72, 720, text)  # crude, can be improved with wrapping
    c.showPage()
    c.save()
    return buf.getvalue()
