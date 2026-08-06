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
            pix = page.get_pixmap(matrix=mat, alpha=False)
            img_data = pix.tobytes(fmt.lower())
            zip_file.writestr(f"page_{page_num + 1}.{fmt.lower()}", img_data)
    return zip_buffer.getvalue()

def convert_images_to_pdf(images_data: list[bytes]) -> bytes:
    doc = fitz.open()
    for img_bytes in images_data:
        img = Image.open(io.BytesIO(img_bytes))
        width, height = img.width, img.height
        page = doc.new_page(width=width, height=height)
        page.insert_image(fitz.Rect(0, 0, width, height), stream=img_bytes)
    return doc.write()


def get_page_image(contents: bytes, page_num: int = 1, dpi: int = 96) -> bytes:
    """Render a single PDF page to PNG bytes."""
    doc = fitz.open(stream=contents, filetype="pdf")
    if page_num < 1 or page_num > len(doc):
        raise ValueError(f"Page {page_num} out of range (1–{len(doc)})")
    page = doc.load_page(page_num - 1)
    mat = fitz.Matrix(dpi / 72.0, dpi / 72.0)
    pix = page.get_pixmap(matrix=mat, alpha=False)
    return pix.tobytes("png")


def crop_pdf_per_page(contents: bytes, crops: list[dict]) -> bytes:
    """Apply independent crop settings to individual pages.
    
    Each crop dict: { page (1-indexed), x, y, width, height, unit ("percentage"|"points") }
    Pages not in the list keep their original crop box.
    """
    doc = fitz.open(stream=contents, filetype="pdf")
    for crop in crops:
        page_num = int(crop.get("page", 1)) - 1
        if page_num < 0 or page_num >= len(doc):
            continue
        page = doc.load_page(page_num)
        page_rect = page.rect
        x = float(crop["x"])
        y = float(crop["y"])
        w = float(crop["width"])
        h = float(crop["height"])
        if crop.get("unit", "percentage") == "percentage":
            x = (x / 100.0) * page_rect.width
            y = (y / 100.0) * page_rect.height
            w = (w / 100.0) * page_rect.width
            h = (h / 100.0) * page_rect.height
        page.set_cropbox(fitz.Rect(x, y, x + w, y + h))
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
        # Split comma-separated search queries
        terms = [t.strip() for t in text_to_redact.split(",") if t.strip()]
        for page in doc:
            for term in terms:
                rects = page.search_for(term)
                for rect in rects:
                    page.add_redact_annot(rect, fill=fill_color)
            page.apply_redactions(images=fitz.PDF_REDACT_IMAGE_NONE)
            
    # Coordinate-based redaction
    if rects_json:
        rects_data = json.loads(rects_json)
        for item in rects_data:
            if isinstance(item, dict):
                page_num = item.get("page", 1) - 1
                x = item.get("x")
                y = item.get("y")
                width = item.get("width")
                height = item.get("height")
                unit = item.get("unit", "points")
            elif isinstance(item, (list, tuple)) and len(item) >= 5:
                page_num = int(item[0]) - 1
                x = float(item[1])
                y = float(item[2])
                width = float(item[3])
                height = float(item[4])
                unit = "points"
            else:
                continue

            if 0 <= page_num < len(doc):
                page = doc.load_page(page_num)
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

def watermark_pdf(
    contents: bytes,
    text: str = None,
    image_bytes: bytes = None,
    opacity: float = 0.5,
    rotation: float = 45.0,
    size: float = 36.0,
) -> bytes:
    doc = fitz.open(stream=contents, filetype="pdf")
    for page in doc:
        rect = page.rect
        cx, cy = rect.width / 2, rect.height / 2
        
        if text:
            font = "helv"
            text_len = fitz.get_text_length(text, fontname=font, fontsize=size)
            p = fitz.Point(cx - text_len / 2, cy)
            page.insert_text(
                p,
                text,
                fontname=font,
                fontsize=size,
                color=(0, 0, 0),
                fill_opacity=opacity,
                rotate=rotation
            )
        elif image_bytes:
            w = rect.width * (size / 100.0)
            h = w
            image_rect = fitz.Rect(cx - w/2, cy - h/2, cx + w/2, cy + h/2)
            page.insert_image(image_rect, stream=image_bytes, keep_proportion=True, overlay=True)
    return doc.write()

def protect_pdf(contents: bytes, password: str) -> bytes:
    doc = fitz.open(stream=contents, filetype="pdf")
    doc.save(
        clean=True,
        encryption=fitz.PDF_ENCRYPT_AES_128,
        owner_pw=password,
        user_pw=password
    )
    out = doc.write()
    doc.close()
    return out

def flatten_pdf(contents: bytes) -> bytes:
    doc = fitz.open(stream=contents, filetype="pdf")
    for page in doc:
        for annot in page.annots():
            annot.set_flags(fitz.PDF_ANNOT_IS_LOCKED | fitz.PDF_ANNOT_IS_PRINT)
        page.clean_contents()
    out = doc.write(clean=True)
    doc.close()
    return out

