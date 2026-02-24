"""
Shared clause numbering patterns and expansion utilities.
Used by both DOCX and PDF parsers.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Literal

Confidence = Literal["high", "medium", "low"]
ExpansionMethod = Literal["numbered_subclause", "paragraph", "pdf_paragraph", "boundary_merge"]

# ─── Clause number regex patterns (most-specific first) ───────────────────────

# e.g. 12.3.1(a), 1.2.3(iv)
_PAT_DEEP_LETTERED = re.compile(
    r"^(\d+\.\d+\.\d+\s*\([a-zA-Z]+(?:\s*[ivxlcdm]+)?\))", re.IGNORECASE
)
# e.g. 12.3(a), 1.2(iv)
_PAT_MID_LETTERED = re.compile(
    r"^(\d+\.\d+\s*\([a-zA-Z]+(?:\s*[ivxlcdm]+)?\))", re.IGNORECASE
)
# e.g. 12.3.1
_PAT_DEEP = re.compile(r"^(\d+\.\d+\.\d+)")
# e.g. 12.3
_PAT_MID = re.compile(r"^(\d+\.\d+)")
# e.g. 12.
_PAT_TOP = re.compile(r"^(\d+\.)")
# e.g. (a), (i), (iv)
_PAT_LETTERED = re.compile(r"^(\([a-zA-Z]+(?:\s*[ivxlcdm]+)?\))", re.IGNORECASE)
# e.g. Section 5, Section 5.1
_PAT_SECTION = re.compile(r"^(Section\s+\d+(?:\.\d+)*)", re.IGNORECASE)
# e.g. Clause 12, Clause 12.3
_PAT_CLAUSE_WORD = re.compile(r"^(Clause\s+\d+(?:\.\d+)*)", re.IGNORECASE)
# e.g. Article 5
_PAT_ARTICLE = re.compile(r"^(Article\s+\d+(?:\.\d+)*)", re.IGNORECASE)

PATTERNS_BY_SPECIFICITY = [
    _PAT_DEEP_LETTERED,
    _PAT_MID_LETTERED,
    _PAT_DEEP,
    _PAT_MID,
    _PAT_TOP,
    _PAT_LETTERED,
    _PAT_SECTION,
    _PAT_CLAUSE_WORD,
    _PAT_ARTICLE,
]

# Inline cross-reference pattern (used in UI highlighting, not expansion)
CROSS_REF_PATTERN = re.compile(
    r"\b(?:clause|section|article|schedule|appendix|exhibit)\s+\d+(?:\.\d+)*(?:\([a-z]+\))?",
    re.IGNORECASE,
)


@dataclass
class ExtractedClause:
    clause_number: str | None
    anchor_text: str
    clause_text: str
    expansion_method: ExpansionMethod
    confidence: Confidence
    page_number: int | None = None
    bbox: list[dict] | None = None  # [{page, rect}]
    ocr_used: bool = False
    comment_texts: list[str] = field(default_factory=list)
    comment_authors: list[str | None] = field(default_factory=list)
    comment_timestamps: list[str | None] = field(default_factory=list)
    # Paragraph index of the anchor in the source document (DOCX only).
    # Used as a fallback merge-key discriminator when clause_number is unavailable.
    anchor_para_idx: int | None = None


def extract_clause_number(line: str) -> str | None:
    """
    Attempt to extract a clause number from the beginning of a text line.
    Returns the matched number string, or None.
    """
    stripped = line.strip()
    for pat in PATTERNS_BY_SPECIFICITY:
        m = pat.match(stripped)
        if m:
            return m.group(1).strip()
    return None


def specificity_score(clause_number: str | None) -> int:
    """
    Higher score = more specific clause numbering.
    Used to prefer e.g. 12.3(a) over 12.3 over 12.
    """
    if clause_number is None:
        return 0
    if re.search(r"\d+\.\d+\.\d+\s*\([a-zA-Z]", clause_number, re.IGNORECASE):
        return 6
    if re.search(r"\d+\.\d+\s*\([a-zA-Z]", clause_number, re.IGNORECASE):
        return 5
    if re.search(r"\d+\.\d+\.\d+", clause_number):
        return 4
    if re.search(r"\d+\.\d+", clause_number):
        return 3
    if re.search(r"\d+\.", clause_number):
        return 2
    if re.search(r"\([a-zA-Z]", clause_number, re.IGNORECASE):
        return 1
    return 0


def merge_clause_range(
    clause_a: str, clause_b: str, anchor_text: str
) -> ExtractedClause:
    """Create a boundary-merge clause card from two clauses."""
    merged_text = clause_a.rstrip() + "\n\n[Clause boundary — annotation spans both clauses]\n\n" + clause_b.lstrip()
    return ExtractedClause(
        clause_number=None,
        anchor_text=anchor_text,
        clause_text=merged_text,
        expansion_method="boundary_merge",
        confidence="medium",
    )
