import asyncio
import subprocess
import tempfile
import logging
from pathlib import Path
import pdfplumber
import pandas as pd
from io import BytesIO
from pdf2docx import Converter as Pdf2DocxConverter
from docx import Document
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib import colors

logger = logging.getLogger(__name__)


async def pdf_to_text(contents: bytes) -> str:
    with pdfplumber.open(BytesIO(contents)) as pdf:
        text = "\n".join(page.extract_text() or "" for page in pdf.pages)
    return text


async def pdf_to_csv(contents: bytes) -> bytes:
    all_tables = []
    with pdfplumber.open(BytesIO(contents)) as pdf:
        for page in pdf.pages:
            tables = page.extract_tables()
            for table in tables:
                if table:
                    all_tables.append(pd.DataFrame(table[1:], columns=table[0]))
    if not all_tables:
        raise ValueError("No tables found in PDF")
    combined = pd.concat(all_tables, ignore_index=True)
    return combined.to_csv(index=False).encode("utf-8")


async def pdf_to_docx(contents: bytes) -> bytes:
    # pdf2docx works with file paths
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp_pdf:
        tmp_pdf.write(contents)
        pdf_path = tmp_pdf.name
    docx_path = pdf_path.replace(".pdf", ".docx")
    try:
        cv = Pdf2DocxConverter(pdf_path)
        cv.convert(docx_path)
        cv.close()
        with open(docx_path, "rb") as f:
            docx_bytes = f.read()
        return docx_bytes
    finally:
        Path(pdf_path).unlink(missing_ok=True)
        Path(docx_path).unlink(missing_ok=True)


async def docx_to_pdf(contents: bytes) -> bytes:
    import shutil
    import os
    libreoffice_bin = shutil.which("libreoffice") or shutil.which("soffice")
    if not libreoffice_bin and os.path.exists("/Applications/LibreOffice.app/Contents/MacOS/soffice"):
        libreoffice_bin = "/Applications/LibreOffice.app/Contents/MacOS/soffice"
    
    if not libreoffice_bin:
        raise FileNotFoundError("LibreOffice executable not found. Please install LibreOffice (e.g. 'brew install --cask libreoffice').")

    # Use LibreOffice headless for reliable conversion
    with tempfile.NamedTemporaryFile(suffix=".docx", delete=False) as tmp_docx:
        tmp_docx.write(contents)
        docx_path = tmp_docx.name
    output_dir = tempfile.mkdtemp()
    try:
        cmd = [
            libreoffice_bin,
            "--headless",
            "--convert-to",
            "pdf",
            "--outdir",
            output_dir,
            docx_path,
        ]
        proc = await asyncio.create_subprocess_exec(
            *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=30)
        if proc.returncode != 0:
            raise RuntimeError(f"LibreOffice failed: {stderr.decode()}")
        pdf_file = Path(output_dir) / (Path(docx_path).stem + ".pdf")
        with open(pdf_file, "rb") as f:
            pdf_bytes = f.read()
        return pdf_bytes
    finally:
        Path(docx_path).unlink(missing_ok=True)
        # Cleanup output dir
        import shutil

        shutil.rmtree(output_dir, ignore_errors=True)


async def txt_to_pdf(contents: bytes) -> bytes:
    text = contents.decode("utf-8")
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter)
    styles = getSampleStyleSheet()
    story = []
    for line in text.split("\n"):
        story.append(Paragraph(line, styles["Normal"]))
        story.append(Spacer(1, 2))
    doc.build(story)
    buffer.seek(0)
    return buffer.read()


async def csv_to_pdf(contents: bytes) -> bytes:
    df = pd.read_csv(BytesIO(contents))
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter)
    elements = []
    # Convert DataFrame to table data
    data = [df.columns.tolist()] + df.values.tolist()
    table = Table(data)
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.grey),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("BOTTOMPADDING", (0, 0), (-1, 0), 12),
                ("BACKGROUND", (0, 1), (-1, -1), colors.beige),
                ("GRID", (0, 0), (-1, -1), 1, colors.black),
            ]
        )
    )
    elements.append(table)
    doc.build(elements)
    buffer.seek(0)
    return buffer.read()


async def pdf_to_excel(contents: bytes) -> bytes:
    all_tables = []
    with pdfplumber.open(BytesIO(contents)) as pdf:
        for page in pdf.pages:
            tables = page.extract_tables()
            for table in tables:
                if table:
                    all_tables.append(pd.DataFrame(table[1:], columns=table[0]))
    if not all_tables:
        raise ValueError("No tables found in PDF")
    combined = pd.concat(all_tables, ignore_index=True)
    out_buf = BytesIO()
    with pd.ExcelWriter(out_buf, engine='openpyxl') as writer:
        combined.to_excel(writer, index=False)
    return out_buf.getvalue()

