# app/services/pdf_advanced_processor.py
import io
import json
import zipfile
import fitz  # PyMuPDF
from PIL import Image

def convert_pdf_to_images(contents: bytes, fmt: str = "png", dpi: int = 150) -> bytes:
    doc = fitz.open(stream=contents, filetype="pdf")
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
        for page_num in range(len(doc)):
            page = doc.load_page(page_num)
            zoom = dpi / 72.0
            mat = fitz.Matrix(zoom, zoom)
            pix = page.get_pixmap(matrix=mat, alpha=(fmt.lower() == "png"))
            img_data = pix.tobytes(fmt.lower())
            zip_file.writestr(f"page_{page_num + 1}.{fmt.lower()}", img_data)
    return zip_buffer.getvalue()

def convert_images_to_pdf(images_data: list[bytes]) -> bytes:
    doc = fitz.open()
    for img_bytes in images_data:
        img = Image.open(io.BytesIO(img_bytes))
        img_format = img.format.lower() if img.format else "png"
        img_doc = fitz.open(stream=img_bytes, filetype=img_format)
        pdf_bytes = img_doc.convert_to_pdf()
        pdf_page_doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        doc.insert_pdf(pdf_page_doc)
    return doc.write()

def crop_pdf(
    contents: bytes,
    x: float,
    y: float,
    width: float,
    height: float,
    unit: str = "points",
    pages: str = "all"
) -> bytes:
    doc = fitz.open(stream=contents, filetype="pdf")
    pages_to_crop = []
    if pages == "all":
        pages_to_crop = list(range(len(doc)))
    else:
        pages_to_crop = [int(p) - 1 for p in pages.split(",") if p.strip().isdigit() and 0 < int(p) <= len(doc)]
    
    for page_num in pages_to_crop:
        page = doc.load_page(page_num)
        page_rect = page.rect
        px, py, pw, ph = x, y, width, height
        if unit == "percentage":
            px = (x / 100.0) * page_rect.width
            py = (y / 100.0) * page_rect.height
            pw = (width / 100.0) * page_rect.width
            ph = (height / 100.0) * page_rect.height
        
        rect = fitz.Rect(px, py, px + pw, py + ph)
        page.set_cropbox(rect)
    return doc.write()

def redact_pdf(
    contents: bytes,
    text_to_redact: str = None,
    rects_json: str = None,
    fill_color: tuple[float, float, float] = (0, 0, 0)
) -> bytes:
    doc = fitz.open(stream=contents, filetype="pdf")
    
    # Text-based redaction
    if text_to_redact:
        for page in doc:
            rects = page.search_for(text_to_redact)
            for rect in rects:
                page.add_redact_annot(rect, fill=fill_color)
            page.apply_redactions(images=fitz.PDF_REDACT_IMAGE_NONE)
            
    # Coordinate-based redaction
    if rects_json:
        rects_data = json.loads(rects_json)
        for item in rects_data:
            page_num = item.get("page", 1) - 1
            if 0 <= page_num < len(doc):
                page = doc.load_page(page_num)
                x = item.get("x")
                y = item.get("y")
                width = item.get("width")
                height = item.get("height")
                unit = item.get("unit", "points")
                
                page_rect = page.rect
                if unit == "percentage":
                    x = (x / 100.0) * page_rect.width
                    y = (y / 100.0) * page_rect.height
                    width = (width / 100.0) * page_rect.width
                    height = (height / 100.0) * page_rect.height
                
                rect = fitz.Rect(x, y, x + width, y + height)
                page.add_redact_annot(rect, fill=fill_color)
                
        # Apply redactions once all coordinates have been annotated
        for page in doc:
            page.apply_redactions(images=fitz.PDF_REDACT_IMAGE_NONE)
            
    return doc.write()

def add_page_numbers(
    contents: bytes,
    pattern: str = "Page {page} of {total}",
    position: str = "bottom-right",
    margin: float = 36,
    font_size: float = 10,
    font_color: str = "000000",
    start_number: int = 1,
    exclude_first_page: bool = False
) -> bytes:
    doc = fitz.open(stream=contents, filetype="pdf")
    total_pages = len(doc)
    
    color_hex = font_color.lstrip('#')
    if len(color_hex) == 6:
        rgb = tuple(int(color_hex[i:i+2], 16) / 255.0 for i in (0, 2, 4))
    else:
        rgb = (0, 0, 0)
        
    for idx in range(total_pages):
        if idx == 0 and exclude_first_page:
            continue
        
        page = doc.load_page(idx)
        page_rect = page.rect
        width, height = page_rect.width, page_rect.height
        
        text = pattern.replace("{page}", str(idx + start_number)).replace("{total}", str(total_pages))
        
        font = "helv"
        text_len = fitz.get_text_length(text, fontname=font, fontsize=font_size)
        
        if position == "bottom-right":
            x = width - margin - text_len
            y = height - margin
        elif position == "bottom-center":
            x = (width - text_len) / 2
            y = height - margin
        elif position == "bottom-left":
            x = margin
            y = height - margin
        elif position == "top-right":
            x = width - margin - text_len
            y = margin + font_size
        elif position == "top-center":
            x = (width - text_len) / 2
            y = margin + font_size
        else:  # top-left
            x = margin
            y = margin + font_size
            
        page.insert_text(fitz.Point(x, y), text, fontname=font, fontsize=font_size, color=rgb)
        
    return doc.write()

def sign_pdf(
    contents: bytes,
    signature_image_bytes: bytes = None,
    signature_text: str = None,
    page_num: int = 1,
    x: float = 0,
    y: float = 0,
    width: float = 150,
    height: float = 50,
    unit: str = "points"
) -> bytes:
    doc = fitz.open(stream=contents, filetype="pdf")
    page_idx = page_num - 1
    if not (0 <= page_idx < len(doc)):
        raise ValueError(f"Invalid page number {page_num}")
        
    page = doc.load_page(page_idx)
    page_rect = page.rect
    
    px, py, pw, ph = x, y, width, height
    if unit == "percentage":
        px = (x / 100.0) * page_rect.width
        py = (y / 100.0) * page_rect.height
        pw = (width / 100.0) * page_rect.width
        ph = (height / 100.0) * page_rect.height
        
    rect = fitz.Rect(px, py, px + pw, py + ph)
    
    if signature_image_bytes:
        page.insert_image(rect, stream=signature_image_bytes)
    elif signature_text:
        font = "hebi"
        font_size = height * 0.6
        text_len = fitz.get_text_length(signature_text, fontname=font, fontsize=font_size)
        if text_len > rect.width:
            font_size = font_size * (rect.width / text_len)
            text_len = rect.width
            
        tx = rect.x0 + (rect.width - text_len) / 2
        ty = rect.y0 + (rect.height + font_size * 0.75) / 2
        page.insert_text(fitz.Point(tx, ty), signature_text, fontname=font, fontsize=font_size, color=(0,0,0))
        
    return doc.write()

def unlock_pdf(contents: bytes, password: str) -> bytes:
    doc = fitz.open(stream=contents, filetype="pdf")
    if doc.is_encrypted:
        success = doc.authenticate(password)
        if not success:
            raise ValueError("Incorrect password")
    return doc.write(clean=True)
