import logging
from pathlib import Path

logger = logging.getLogger(__name__)

def extract_text(pdf_path: str | Path) -> str:
    """Extract full text from a PDF file.
    
    Tries pdfplumber first, falls back to PyMuPDF.
    Returns cleaned text with page markers.
    """
    pdf_path = Path(pdf_path)
    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF file not found: {pdf_path}")
    
    text = _extract_with_pdfplumber(pdf_path)
    if not text.strip():
        logger.info("pdfplumber returned empty text, trying PyMuPDF...")
        text = _extract_with_pymupdf(pdf_path)
    
    if not text.strip():
        raise RuntimeError(f"Failed to extract text from {pdf_path}")
    
    return _clean_text(text)


def extract_text_by_page(pdf_path: str | Path) -> list[str]:
    """Extract text page by page from a PDF file."""
    pdf_path = Path(pdf_path)
    pages = _extract_pages_pdfplumber(pdf_path)
    if not any(p.strip() for p in pages):
        pages = _extract_pages_pymupdf(pdf_path)
    return [_clean_text(p) for p in pages]


def _extract_with_pdfplumber(pdf_path: Path) -> str:
    try:
        import pdfplumber
        with pdfplumber.open(pdf_path) as pdf:
            pages = []
            for page in pdf.pages:
                text = page.extract_text() or ""
                pages.append(text)
            return "\n\n".join(pages)
    except ImportError:
        logger.warning("pdfplumber not installed")
        return ""
    except Exception as e:
        logger.warning(f"pdfplumber extraction failed: {e}")
        return ""


def _extract_with_pymupdf(pdf_path: Path) -> str:
    try:
        import fitz
        doc = fitz.open(pdf_path)
        pages = []
        for page in doc:
            pages.append(page.get_text())
        doc.close()
        return "\n\n".join(pages)
    except ImportError:
        logger.warning("PyMuPDF not installed")
        return ""
    except Exception as e:
        logger.warning(f"PyMuPDF extraction failed: {e}")
        return ""


def _extract_pages_pdfplumber(pdf_path: Path) -> list[str]:
    try:
        import pdfplumber
        with pdfplumber.open(pdf_path) as pdf:
            return [page.extract_text() or "" for page in pdf.pages]
    except Exception:
        return []


def _extract_pages_pymupdf(pdf_path: Path) -> list[str]:
    try:
        import fitz
        doc = fitz.open(pdf_path)
        pages = [page.get_text() for page in doc]
        doc.close()
        return pages
    except Exception:
        return []


def _clean_text(text: str) -> str:
    """Clean extracted text by removing artifacts."""
    import re
    # Remove isolated page numbers (digits alone on a line)
    text = re.sub(r'\n\s*\d{1,3}\s*\n', '\n', text)
    # Remove excessive blank lines (3+ -> 2)
    text = re.sub(r'\n{3,}', '\n\n', text)
    # Remove common PDF artifacts
    text = re.sub(r'\x0c', '\n', text)  # form feed
    # Strip leading/trailing whitespace per line but preserve paragraph structure
    lines = text.split('\n')
    cleaned = []
    for line in lines:
        stripped = line.strip()
        cleaned.append(stripped)
    return '\n'.join(cleaned).strip()
