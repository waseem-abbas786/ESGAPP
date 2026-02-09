
import logging
import re
from dataclasses import dataclass
from typing import Dict, List, Tuple

import fitz  
import pdfplumber
from docx import Document as DocxDocument

logger = logging.getLogger(__name__)

ESG_KEYWORDS = {
    "E": {  
        "environmental policy": 5,
        "carbon emissions": 5,
        "iso 14001": 8,
        "renewable energy": 6,
        "waste management": 4,
        "water conservation": 4,
        "climate change": 5,
        "sustainability": 4,
        "carbon footprint": 5,
        "greenhouse gas": 5,
    },
    "S": {  
        "labour rights": 6,
        "human rights": 7,
        "health and safety": 6,
        "diversity and inclusion": 5,
        "employee welfare": 4,
        "fair wages": 5,
        "working conditions": 5,
        "child labor": 7,
        "supply chain responsibility": 6,
        "community engagement": 4,
    },
    "G": {  
        "anti-corruption": 7,
        "ethics policy": 6,
        "whistleblowing": 6,
        "governance structure": 5,
        "board independence": 5,
        "transparency": 5,
        "risk management": 5,
        "compliance": 5,
        "audit": 4,
        "stakeholder engagement": 4,
    }
}

MAX_POINTS = {
    "E": sum(ESG_KEYWORDS["E"].values()),  
    "S": sum(ESG_KEYWORDS["S"].values()),  
    "G": sum(ESG_KEYWORDS["G"].values()),  
}


@dataclass(frozen=True)
class ExtractionResult:
    text: str
    extractor: str


def extract_text_from_file(path: str, file_format: str) -> ExtractionResult:
    """
    Extract text from PDF or DOCX file.
    
    Args:
        path: File path
        file_format: "PDF" or "DOCX"
    
    Returns:
        ExtractionResult with text and extractor name
    """
    fmt = (file_format or "").upper()
    
    if fmt == "PDF":
        try:
            text = _extract_pdf_pymupdf(path)
            return ExtractionResult(text=text, extractor="pymupdf")
        except Exception:
            text = _extract_pdf_pdfplumber(path)
            return ExtractionResult(text=text, extractor="pdfplumber")
    
    elif fmt == "DOCX":
        text = _extract_docx(path)
        return ExtractionResult(text=text, extractor="python-docx")
    
    else:
        raise ValueError(f"Unsupported file format: {file_format}")


def _extract_pdf_pymupdf(path: str) -> str:
    doc = fitz.open(path)
    try:
        pages = [page.get_text("text") or "" for page in doc]
        return "\n".join(pages).strip()
    finally:
        doc.close()


def _extract_pdf_pdfplumber(path: str) -> str:
    chunks = []
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            chunks.append(page.extract_text() or "")
    return "\n".join(chunks).strip()


def _extract_docx(path: str) -> str:
    """Extract text from DOCX file."""
    doc = DocxDocument(path)
    paragraphs = [p.text for p in doc.paragraphs if p.text]
    return "\n".join(paragraphs).strip()


def normalize_text(text: str) -> str:
    """Normalize text for keyword matching."""
    if not text:
        return ""
    text = text.lower()
    text = re.sub(r'\s+', ' ', text)  
    return text.strip()


def find_keywords_in_text(text: str) -> Dict[str, List[Tuple[str, bool, int]]]:
    normalized_text = normalize_text(text)
    results = {"E": [], "S": [], "G": []}
    
    for category, keywords in ESG_KEYWORDS.items():
        for keyword, points in keywords.items():
            pattern = r'\b' + re.escape(keyword.lower()) + r'\b'
            found = bool(re.search(pattern, normalized_text))
            
            results[category].append((keyword, found, points if found else 0))
            
            if found:
                logger.debug(f"Found keyword '{keyword}' in category {category}")
    
    return results


def calculate_category_scores(keyword_results: Dict[str, List[Tuple[str, bool, int]]]) -> Dict[str, int]:
    """
    Calculate total points for each category.
    
    Args:
        keyword_results: Results from find_keywords_in_text()
    
    Returns:
        Dict with category scores: {"E": 20, "S": 35, "G": 18}
    """
    category_scores = {}
    
    for category, results in keyword_results.items():
        total_points = sum(points for _, _, points in results)
        category_scores[category] = total_points
        logger.debug(f"Category {category}: {total_points}/{MAX_POINTS[category]} points")
    
    return category_scores


def calculate_total_score(category_scores: Dict[str, int]) -> int:
    """
    Calculate overall ESG score (0-100) with weighted categories.
    
    Weights:
    - Environmental: 35%
    - Social: 35%
    - Governance: 30%
    
    Args:
        category_scores: Points per category {"E": 20, "S": 35, "G": 18}
    
    Returns:
        Total score (0-100)
    """
    env_percentage = (category_scores["E"] / MAX_POINTS["E"]) * 100 if MAX_POINTS["E"] > 0 else 0
    social_percentage = (category_scores["S"] / MAX_POINTS["S"]) * 100 if MAX_POINTS["S"] > 0 else 0
    gov_percentage = (category_scores["G"] / MAX_POINTS["G"]) * 100 if MAX_POINTS["G"] > 0 else 0

    total = (env_percentage * 0.35) + (social_percentage * 0.35) + (gov_percentage * 0.30)
    
    return int(round(total))


def determine_risk_level(total_score: int) -> str:
    """
    Determine risk level based on ESG score.
    
    Args:
        total_score: ESG score (0-100)
    
    Returns:
        "LOW", "MEDIUM", or "HIGH"
    """
    if total_score >= 70:
        return "LOW"
    elif total_score >= 40:
        return "MEDIUM"
    else:
        return "HIGH"