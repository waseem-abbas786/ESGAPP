# app/esg/services/text_extraction.py
from __future__ import annotations

from dataclasses import dataclass

import fitz  # PyMuPDF
import pdfplumber
from docx import Document as DocxDocument


@dataclass(frozen=True)
class ExtractionResult:
    text: str
    extractor: str


def extract_text_from_file(path: str, file_format: str) -> ExtractionResult:
    fmt = (file_format or "").upper()

    if fmt == "PDF":
        # Try fast extractor first; fallback for PDFs where layout extraction is better
        try:
            return ExtractionResult(text=_pdf_pymupdf(path), extractor="pymupdf")
        except Exception:
            return ExtractionResult(text=_pdf_pdfplumber(path), extractor="pdfplumber")

    if fmt == "DOCX":
        return ExtractionResult(text=_docx(path), extractor="python-docx")

    raise ValueError(f"Unsupported file_format: {file_format}")


def _pdf_pymupdf(path: str) -> str:
    doc = fitz.open(path)
    try:
        return "\n".join((page.get_text("text") or "") for page in doc).strip()
    finally:
        doc.close()


def _pdf_pdfplumber(path: str) -> str:
    chunks: list[str] = []
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            chunks.append(page.extract_text() or "")
    return "\n".join(chunks).strip()


def _docx(path: str) -> str:
    d = DocxDocument(path)
    return "\n".join(p.text for p in d.paragraphs if p.text).strip()
