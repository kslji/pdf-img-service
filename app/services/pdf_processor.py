# app/services/pdf_processor.py
import io
import zipfile
from pypdf import PdfReader, PdfWriter


def merge_pdfs(file_streams: list[io.BytesIO]) -> bytes:
    writer = PdfWriter()
    for stream in file_streams:
        reader = PdfReader(stream)
        for page in reader.pages:
            writer.add_page(page)
    output = io.BytesIO()
    writer.write(output)
    return output.getvalue()


def split_pdf_to_pages(contents: bytes) -> dict[str, bytes]:
    # First, get total pages using a temporary reader
    temp_reader = PdfReader(io.BytesIO(contents))
    total_pages = len(temp_reader.pages)
    
    pages_dict = {}
    for i in range(total_pages):
        reader = PdfReader(io.BytesIO(contents))
        writer = PdfWriter()
        writer.add_page(reader.pages[i])
        buf = io.BytesIO()
        writer.write(buf)
        pages_dict[f"page_{i + 1}.pdf"] = buf.getvalue()
    return pages_dict


def split_pdf_by_ranges(
    contents: bytes, ranges: list[tuple[int, int]]
) -> dict[str, bytes]:
    # First, get total pages using a temporary reader
    temp_reader = PdfReader(io.BytesIO(contents))
    total_pages = len(temp_reader.pages)
    
    result = {}
    for idx, (start, end) in enumerate(ranges, 1):
        # start and end are 1-based inclusive
        if start < 1 or end > total_pages or start > end:
            continue
        reader = PdfReader(io.BytesIO(contents))
        writer = PdfWriter()
        for page_num in range(start - 1, end):
            writer.add_page(reader.pages[page_num])
        buf = io.BytesIO()
        writer.write(buf)
        result[f"split_{idx}.pdf"] = buf.getvalue()
    return result


def compress_pdf(contents: bytes, level: str = "default") -> bytes:
    import fitz
    
    doc = fitz.open(stream=contents, filetype="pdf")
    
    level = level.lower().strip()
    quality = 70
    if level == "extreme":
        quality = 25
    elif level == "recommended" or level == "default":
        quality = 50
    elif level == "low":
        quality = 85

    for page in doc:
        try:
            if hasattr(page, "rewrite_images"):
                page.rewrite_images(quality=quality, lossy=True)
        except Exception:
            pass

    output_stream = io.BytesIO()
    doc.save(
        output_stream,
        garbage=4,
        deflate=True,
        deflate_images=True,
        deflate_fonts=True
    )
    doc.close()
    return output_stream.getvalue()


def remove_pages(contents: bytes, pages_to_remove: list[int]) -> bytes:
    reader = PdfReader(io.BytesIO(contents))
    writer = PdfWriter()
    total_pages = len(reader.pages)
    for i in range(total_pages):
        if (i + 1) not in pages_to_remove:  # 1‑based
            writer.add_page(reader.pages[i])
    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()

