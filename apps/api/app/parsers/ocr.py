"""
OCR fallback using pytesseract.
Used when PDF annotation anchor text extraction fails (empty or garbled).
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def ocr_region(page_image_bytes: bytes, bbox: tuple[float, float, float, float]) -> str:
    """
    OCR a specific region of a page image.

    Args:
        page_image_bytes: PNG bytes of the full page rendered at some DPI
        bbox: (x0, y0, x1, y1) in page coordinates (PDF points)

    Returns:
        Extracted text string (may be empty if OCR finds nothing)
    """
    try:
        from PIL import Image
        import pytesseract
        import io

        img = Image.open(io.BytesIO(page_image_bytes))
        # Crop to bbox (already in pixel coords if rendered at correct DPI)
        x0, y0, x1, y1 = int(bbox[0]), int(bbox[1]), int(bbox[2]), int(bbox[3])
        # Ensure valid crop bounds
        x0, x1 = max(0, x0), min(img.width, x1)
        y0, y1 = max(0, y0), min(img.height, y1)
        if x1 <= x0 or y1 <= y0:
            return ""

        cropped = img.crop((x0, y0, x1, y1))
        # Upscale for better OCR accuracy
        scale = 3
        cropped = cropped.resize((cropped.width * scale, cropped.height * scale), Image.LANCZOS)
        text = pytesseract.image_to_string(cropped, config="--psm 6")
        return text.strip()
    except Exception as exc:
        logger.warning("OCR failed: %s", exc)
        return ""


def render_page_to_image(pdf_bytes: bytes, page_number: int, dpi: int = 150) -> bytes:
    """
    Render a PDF page to PNG bytes using PyMuPDF.

    Returns PNG bytes of the rendered page.
    """
    import fitz  # PyMuPDF

    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    page = doc[page_number]
    mat = fitz.Matrix(dpi / 72, dpi / 72)
    pix = page.get_pixmap(matrix=mat)
    return pix.tobytes("png")


def is_garbage_text(text: str, alpha_ratio_threshold: float = 0.3) -> bool:
    """
    Return True if text appears to be OCR garbage or empty:
    - Empty
    - Alphanumeric ratio below threshold (lots of symbols/noise)
    """
    if not text or not text.strip():
        return True
    alphanumeric = sum(1 for c in text if c.isalnum())
    ratio = alphanumeric / len(text)
    return ratio < alpha_ratio_threshold
