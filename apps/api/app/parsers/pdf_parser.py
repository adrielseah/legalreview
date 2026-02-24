"""
PDF parser for ClauseLens using PyMuPDF (fitz).

Extracts annotations (Highlight, Underline, Squiggly, Text/FreeText — not StrikeOut)
and expands each to the smallest enclosing numbered subclause.

Special handling:
- FreeText annotations with no geometry: find nearest text block centroid
- OCR fallback: if anchor_text extraction is empty or alphanumeric ratio < threshold
- Multi-page bbox: stored as [{page, rect}, ...]
- Paragraph fallback: same x-indent, no blank-line gap
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from typing import Optional

import fitz  # type: ignore[import-untyped]

from app.config import get_settings
from app.parsers.clause_patterns import (
    ExtractedClause,
    extract_clause_number,
    merge_clause_range,
    specificity_score,
)
from app.parsers.ocr import is_garbage_text

logger = logging.getLogger(__name__)
settings = get_settings()

# Annotation subtypes to include
INCLUDE_SUBTYPES = {"Highlight", "Underline", "Squiggly", "Text", "FreeText"}
# Annotation subtypes to exclude
EXCLUDE_SUBTYPES = {"StrikeOut", "Ink", "Stamp", "Redact", "Caret"}


@dataclass
class RawAnnotation:
    page_number: int
    subtype: str
    contents: str
    author: str | None
    date_str: str | None
    anchor_text: str
    rects: list[tuple[float, float, float, float]]  # [(x0,y0,x1,y1), ...]
    ocr_used: bool = False


def _rect_centroid(rect: tuple[float, float, float, float]) -> tuple[float, float]:
    return ((rect[0] + rect[2]) / 2, (rect[1] + rect[3]) / 2)


def _distance(p1: tuple[float, float], p2: tuple[float, float]) -> float:
    return math.sqrt((p1[0] - p2[0]) ** 2 + (p1[1] - p2[1]) ** 2)


def _extract_anchor_from_rects(
    page,
    rects: list[tuple[float, float, float, float]],
    pdf_bytes: bytes,
    page_number: int,
) -> tuple[str, bool]:
    """
    Extract text within the annotation rects.
    Falls back to OCR if text is empty/garbage.
    Returns (anchor_text, ocr_used).
    """

    # Merge all rects into a bounding box
    if not rects:
        return "", False

    x0 = min(r[0] for r in rects)
    y0 = min(r[1] for r in rects)
    x1 = max(r[2] for r in rects)
    y1 = max(r[3] for r in rects)
    clip_rect = fitz.Rect(x0, y0, x1, y1)

    # Try native text extraction
    words = page.get_text("words", clip=clip_rect)
    anchor_text = " ".join(w[4] for w in words).strip()

    if not anchor_text or is_garbage_text(anchor_text, settings.ocr_alpha_ratio_threshold):
        if not settings.disable_ocr:
            from app.parsers.ocr import ocr_region, render_page_to_image

            # Render page at 150 DPI and scale bbox accordingly
            dpi = 150
            scale = dpi / 72
            page_img = render_page_to_image(pdf_bytes, page_number, dpi=dpi)
            scaled_bbox = (x0 * scale, y0 * scale, x1 * scale, y1 * scale)
            ocr_text = ocr_region(page_img, scaled_bbox)
            if ocr_text and not is_garbage_text(ocr_text, settings.ocr_alpha_ratio_threshold):
                return ocr_text, True
        return anchor_text or "", False

    return anchor_text, False


def _find_nearest_text_block(
    page, freetext_rect
) -> tuple[str, tuple[float, float, float, float] | None]:
    """
    For FreeText annotations without geometry, find the nearest text block.
    Returns (text, rect) of the nearest block.
    """
    cx, cy = _rect_centroid((freetext_rect.x0, freetext_rect.y0, freetext_rect.x1, freetext_rect.y1))
    blocks = page.get_text("blocks")
    best_text = ""
    best_rect = None
    best_dist = float("inf")

    for block in blocks:
        bx0, by0, bx1, by1, text, *_ = block
        if not text.strip():
            continue
        bx, by = _rect_centroid((bx0, by0, bx1, by1))
        dist = _distance((cx, cy), (bx, by))
        if dist < best_dist:
            best_dist = dist
            best_text = text.strip()
            best_rect = (bx0, by0, bx1, by1)

    return best_text, best_rect


def _get_page_text_blocks(page) -> list[dict]:
    """Get all text blocks with their bounding boxes."""
    blocks = []
    for block in page.get_text("blocks"):
        bx0, by0, bx1, by1, text, block_no, block_type = block
        if block_type == 0 and text.strip():  # text block
            blocks.append({"x0": bx0, "y0": by0, "x1": bx1, "y1": by1, "text": text.strip()})
    return blocks


def _find_enclosing_clause_pdf(
    page,
    anchor_rect: tuple[float, float, float, float],
    page_number: int,
) -> tuple[str | None, str, str, str]:
    """
    Find the smallest numbered subclause containing the anchor bbox on a PDF page.

    Returns: (clause_number, clause_text, expansion_method, confidence)
    """
    ax0, ay0, ax1, ay1 = anchor_rect
    anchor_height = ay1 - ay0
    search_margin = max(anchor_height * 20, 300)

    blocks = _get_page_text_blocks(page)

    # Find blocks near the annotation (vertical proximity)
    near_blocks = [
        b for b in blocks
        if b["y0"] >= ay0 - search_margin and b["y1"] <= ay1 + search_margin
    ]

    if not near_blocks:
        near_blocks = blocks

    # Sort by vertical position
    near_blocks.sort(key=lambda b: b["y0"])

    # Find the block that contains or is nearest to the anchor
    anchor_cx = (ax0 + ax1) / 2
    anchor_cy = (ay0 + ay1) / 2

    # Try to find a numbered clause heading at or above the anchor
    best_clause_num: str | None = None
    best_score = -1
    best_start_idx = 0

    for i, block in enumerate(near_blocks):
        if block["y0"] <= anchor_cy:
            num = extract_clause_number(block["text"])
            if num:
                score = specificity_score(num)
                if score > best_score:
                    best_score = score
                    best_clause_num = num
                    best_start_idx = i

    if best_clause_num:
        # Collect clause body until next same-level or higher clause
        clause_lines = []
        for i in range(best_start_idx, len(near_blocks)):
            b = near_blocks[i]
            if i > best_start_idx:
                num = extract_clause_number(b["text"])
                if num and specificity_score(num) >= best_score:
                    break
            clause_lines.append(b["text"])
        clause_text = "\n".join(clause_lines)
        return best_clause_num, clause_text, "numbered_subclause", "high"

    # Fallback: paragraph expansion using x-indent and line spacing
    # Find blocks that form a continuous paragraph around the anchor
    anchor_block = min(
        blocks,
        key=lambda b: abs((b["y0"] + b["y1"]) / 2 - anchor_cy),
        default=None,
    )
    if anchor_block:
        ref_x0 = anchor_block["x0"]
        para_blocks = []
        prev_y1 = None
        for b in sorted(blocks, key=lambda b: b["y0"]):
            if abs(b["x0"] - ref_x0) < 20:  # same indent
                if prev_y1 is not None and b["y0"] - prev_y1 > 20:
                    # gap too large — different paragraph
                    if b["y0"] > anchor_cy:
                        break
                    else:
                        para_blocks = []
                para_blocks.append(b["text"])
                prev_y1 = b["y1"]
        if para_blocks:
            return None, "\n".join(para_blocks), "pdf_paragraph", "medium"

    # Final fallback: just use blocks near the anchor
    fallback_text = "\n".join(b["text"] for b in near_blocks[:5])
    return None, fallback_text, "pdf_paragraph", "medium"


def parse_pdf(file_bytes: bytes, progress_callback=None) -> list[ExtractedClause]:
    """
    Parse a PDF and extract all annotations with their clause context.
    """
    results: list[ExtractedClause] = []
    doc = fitz.open(stream=file_bytes, filetype="pdf")
    total_pages = len(doc)

    for page_number in range(total_pages):
        if progress_callback:
            progress_callback(page_number + 1, total_pages)

        page = doc[page_number]
        annots = page.annots()
        if annots is None:
            continue

        for annot in annots:
            subtype = annot.type[1]  # string subtype name

            # Skip excluded types
            if subtype in EXCLUDE_SUBTYPES:
                continue
            if subtype not in INCLUDE_SUBTYPES:
                continue

            contents = (annot.info.get("content", "") or "").strip()
            author = annot.info.get("title") or annot.info.get("author")
            date_str = annot.info.get("modDate") or annot.info.get("creationDate")

            # Skip if no comment text (some highlights are purely visual)
            if not contents:
                continue

            # Get geometry
            annot_rect = annot.rect
            rects = []

            if subtype == "FreeText":
                # FreeText: no quadpoints — find nearest text block
                anchor_text, nearest_rect = _find_nearest_text_block(page, annot_rect)
                ocr_used = False
                if nearest_rect:
                    rects = [nearest_rect]
            else:
                # Extract quadpoints for highlight/underline
                quad_points = annot.vertices  # list of (x,y) tuples
                if quad_points and len(quad_points) >= 4:
                    # Group into quads of 4 points
                    for i in range(0, len(quad_points), 4):
                        quad = quad_points[i : i + 4]
                        if len(quad) == 4:
                            xs = [p[0] for p in quad]
                            ys = [p[1] for p in quad]
                            rects.append((min(xs), min(ys), max(xs), max(ys)))
                else:
                    rects = [(annot_rect.x0, annot_rect.y0, annot_rect.x1, annot_rect.y1)]

                anchor_text, ocr_used = _extract_anchor_from_rects(
                    page, rects, file_bytes, page_number
                )

            # Get the anchor bounding box (union of all rects)
            if rects:
                x0 = min(r[0] for r in rects)
                y0 = min(r[1] for r in rects)
                x1 = max(r[2] for r in rects)
                y1 = max(r[3] for r in rects)
                anchor_bbox = (x0, y0, x1, y1)
            else:
                anchor_bbox = (annot_rect.x0, annot_rect.y0, annot_rect.x1, annot_rect.y1)

            # Expand to enclosing clause
            clause_num, clause_text, expansion_method, confidence = _find_enclosing_clause_pdf(
                page, anchor_bbox, page_number
            )

            # Override confidence if OCR was used
            if ocr_used:
                confidence = "low"

            bbox_list = [{"page": page_number, "rect": list(anchor_bbox)}]

            results.append(
                ExtractedClause(
                    clause_number=clause_num,
                    anchor_text=anchor_text,
                    clause_text=clause_text,
                    expansion_method=expansion_method,
                    confidence=confidence,
                    page_number=page_number,
                    bbox=bbox_list,
                    ocr_used=ocr_used,
                    comment_texts=[contents],
                    comment_authors=[author],
                    comment_timestamps=[date_str],
                )
            )

    doc.close()
    return results


def get_first_page_text_pdf(file_bytes: bytes) -> str:
    """Extract text from first page for doc_kind detection."""
    doc = fitz.open(stream=file_bytes, filetype="pdf")
    if len(doc) == 0:
        return ""
    text = doc[0].get_text()
    doc.close()
    return text[:3000]
