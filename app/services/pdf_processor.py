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
    reader = PdfReader(io.BytesIO(contents))
    pages_dict = {}
    for i, page in enumerate(reader.pages):
        writer = PdfWriter()
        writer.add_page(page)
        buf = io.BytesIO()
        writer.write(buf)
        pages_dict[f"page_{i + 1}.pdf"] = buf.getvalue()
    return pages_dict


def split_pdf_by_ranges(
    contents: bytes, ranges: list[tuple[int, int]]
) -> dict[str, bytes]:
    reader = PdfReader(io.BytesIO(contents))
    result = {}
    total_pages = len(reader.pages)
    for idx, (start, end) in enumerate(ranges, 1):
        # start and end are 1-based inclusive
        if start < 1 or end > total_pages or start > end:
            continue
        writer = PdfWriter()
        for page_num in range(start - 1, end):
            writer.add_page(reader.pages[page_num])
        buf = io.BytesIO()
        writer.write(buf)
        result[f"split_{idx}.pdf"] = buf.getvalue()
    return result


def compress_pdf(contents: bytes, level: str = "default") -> bytes:
    reader = PdfReader(io.BytesIO(contents))
    writer = PdfWriter()
    for page in reader.pages:
        writer.add_page(page)
    # Compress content streams
    for page in writer.pages:
        page.compress_content_streams()
    output = io.BytesIO()
    writer.write(output)
    return output.getvalue()


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

