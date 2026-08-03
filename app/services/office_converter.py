import asyncio
import subprocess
import tempfile
import logging
from typing import Optional
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


def translate_text_helper(text: str, target_lang: str) -> str:
    if not text.strip():
        return text
    from deep_translator import GoogleTranslator
    try:
        translator = GoogleTranslator(source="auto", target=target_lang)
        if len(text) < 4500:
            return translator.translate(text)
        else:
            chunks = []
            current_chunk = ""
            for paragraph in text.split("\n"):
                if len(current_chunk) + len(paragraph) + 1 < 4500:
                    current_chunk += ("\n" if current_chunk else "") + paragraph
                else:
                    if current_chunk:
                        chunks.append(translator.translate(current_chunk))
                    current_chunk = paragraph
            if current_chunk:
                chunks.append(translator.translate(current_chunk))
            return "\n".join(chunks)
    except Exception as e:
        logger.error(f"Translation helper failed: {e}")
        return text


def _pdf_to_text_sync(contents: bytes, target_lang: Optional[str] = None) -> str:
    with pdfplumber.open(BytesIO(contents)) as pdf:
        text = "\n".join(page.extract_text() or "" for page in pdf.pages)
    if target_lang and target_lang != "none":
        text = translate_text_helper(text, target_lang)
    return text


async def pdf_to_text(contents: bytes, target_lang: Optional[str] = None) -> str:
    return await asyncio.to_thread(_pdf_to_text_sync, contents, target_lang)


def _pdf_to_csv_sync(contents: bytes, target_lang: Optional[str] = None) -> bytes:
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
    if target_lang and target_lang != "none":
        from deep_translator import GoogleTranslator
        translator = GoogleTranslator(source="auto", target=target_lang)
        for col in combined.columns:
            new_col = str(col)
            try:
                if new_col.strip():
                    new_col = translator.translate(new_col)
            except Exception:
                pass
            combined.rename(columns={col: new_col}, inplace=True)
            combined[new_col] = combined[new_col].apply(
                lambda val: translator.translate(str(val)) if val and isinstance(val, str) and val.strip() else val
            )
    return combined.to_csv(index=False).encode("utf-8")


async def pdf_to_csv(contents: bytes, target_lang: Optional[str] = None) -> bytes:
    return await asyncio.to_thread(_pdf_to_csv_sync, contents, target_lang)


def _pdf_to_docx_sync(contents: bytes, target_lang: Optional[str] = None) -> bytes:
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp_pdf:
        tmp_pdf.write(contents)
        pdf_path = tmp_pdf.name
    docx_path = pdf_path.replace(".pdf", ".docx")
    try:
        cv = Pdf2DocxConverter(pdf_path)
        cv.convert(docx_path)
        cv.close()
        
        if target_lang and target_lang != "none":
            doc = Document(docx_path)
            from deep_translator import GoogleTranslator
            translator = GoogleTranslator(source="auto", target=target_lang)

            def translate_runs(runs):
                for run in runs:
                    if run.text and run.text.strip():
                        try:
                            translated = translator.translate(run.text)
                            if translated:
                                run.text = translated
                        except Exception as te:
                            logger.error(f"Pdf-to-docx run translation error: {te}")

            for paragraph in doc.paragraphs:
                translate_runs(paragraph.runs)
            for table in doc.tables:
                for row in table.rows:
                    for cell in row.cells:
                        for paragraph in cell.paragraphs:
                            translate_runs(paragraph.runs)
            doc.save(docx_path)

        with open(docx_path, "rb") as f:
            docx_bytes = f.read()
        return docx_bytes
    finally:
        Path(pdf_path).unlink(missing_ok=True)
        Path(docx_path).unlink(missing_ok=True)


async def pdf_to_docx(contents: bytes, target_lang: Optional[str] = None) -> bytes:
    return await asyncio.to_thread(_pdf_to_docx_sync, contents, target_lang)


def _docx_translate_sync(contents: bytes, target_lang: str) -> bytes:
    doc = Document(BytesIO(contents))
    from deep_translator import GoogleTranslator
    translator = GoogleTranslator(source="auto", target=target_lang)

    def translate_runs(runs):
        """Translate each run's text individually, preserving run-level formatting."""
        for run in runs:
            if run.text and run.text.strip():
                try:
                    translated = translator.translate(run.text)
                    if translated:
                        run.text = translated
                except Exception as te:
                    logger.error(f"Run translation error: {te}")

    for paragraph in doc.paragraphs:
        translate_runs(paragraph.runs)

    for table in doc.tables:
        for row in table.rows:
            for cell in row.cells:
                for paragraph in cell.paragraphs:
                    translate_runs(paragraph.runs)

    out_buf = BytesIO()
    doc.save(out_buf)
    return out_buf.getvalue()


async def docx_to_pdf(contents: bytes, target_lang: Optional[str] = None) -> bytes:
    import shutil
    import os
    libreoffice_bin = shutil.which("libreoffice") or shutil.which("soffice")
    if not libreoffice_bin and os.path.exists("/Applications/LibreOffice.app/Contents/MacOS/soffice"):
        libreoffice_bin = "/Applications/LibreOffice.app/Contents/MacOS/soffice"
    
    if not libreoffice_bin:
        raise FileNotFoundError("LibreOffice executable not found. Please install LibreOffice (e.g. 'brew install --cask libreoffice').")

    if target_lang and target_lang != "none":
        logger.info(f"docx_to_pdf: translating to '{target_lang}'")
        contents = await asyncio.to_thread(_docx_translate_sync, contents, target_lang)
        logger.info(f"docx_to_pdf: translation complete, new size={len(contents)} bytes")

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
        shutil.rmtree(output_dir, ignore_errors=True)


def _txt_to_pdf_sync(contents: bytes, target_lang: Optional[str] = None) -> bytes:
    text = contents.decode("utf-8")
    if target_lang and target_lang != "none":
        text = translate_text_helper(text, target_lang)
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


async def txt_to_pdf(contents: bytes, target_lang: Optional[str] = None) -> bytes:
    return await asyncio.to_thread(_txt_to_pdf_sync, contents, target_lang)


def _csv_to_pdf_sync(contents: bytes, target_lang: Optional[str] = None) -> bytes:
    df = pd.read_csv(BytesIO(contents))
    if target_lang and target_lang != "none":
        from deep_translator import GoogleTranslator
        translator = GoogleTranslator(source="auto", target=target_lang)
        for col in df.columns:
            new_col = str(col)
            try:
                if new_col.strip():
                    new_col = translator.translate(new_col)
            except Exception:
                pass
            df.rename(columns={col: new_col}, inplace=True)
            df[new_col] = df[new_col].apply(
                lambda val: translator.translate(str(val)) if val and isinstance(val, str) and val.strip() else val
            )
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter)
    elements = []
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


async def csv_to_pdf(contents: bytes, target_lang: Optional[str] = None) -> bytes:
    return await asyncio.to_thread(_csv_to_pdf_sync, contents, target_lang)


def _pdf_to_excel_sync(contents: bytes, target_lang: Optional[str] = None) -> bytes:
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
    if target_lang and target_lang != "none":
        from deep_translator import GoogleTranslator
        translator = GoogleTranslator(source="auto", target=target_lang)
        for col in combined.columns:
            new_col = str(col)
            try:
                if new_col.strip():
                    new_col = translator.translate(new_col)
            except Exception:
                pass
            combined.rename(columns={col: new_col}, inplace=True)
            combined[new_col] = combined[new_col].apply(
                lambda val: translator.translate(str(val)) if val and isinstance(val, str) and val.strip() else val
            )
    out_buf = BytesIO()
    with pd.ExcelWriter(out_buf, engine='openpyxl') as writer:
        combined.to_excel(writer, index=False)
    return out_buf.getvalue()


async def pdf_to_excel(contents: bytes, target_lang: Optional[str] = None) -> bytes:
    return await asyncio.to_thread(_pdf_to_excel_sync, contents, target_lang)
