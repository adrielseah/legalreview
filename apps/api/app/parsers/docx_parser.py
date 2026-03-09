"""
DOCX parser for ClauseLens.

Extracts legal comments and their associated clause text from .docx files.

Approach:
1. Parse word/comments.xml for comment bodies + metadata
2. Parse word/commentsExtended.xml for threaded replies (concat into one comment_text)
3. Parse word/document.xml to:
   - Apply accepted-view tracked changes (w:ins kept, w:del ignored)
   - Find commentRangeStart/End markers to extract anchor text
4. Expand anchor to smallest enclosing numbered subclause using regex patterns
5. If no numbering, fall back to containing paragraph (confidence=medium)
6. Handle boundary-spanning anchors (merge two clauses, confidence=medium)
"""

from __future__ import annotations

import logging
import re
import zipfile
from dataclasses import dataclass, field
from datetime import datetime
from typing import Iterator
from xml.etree import ElementTree as ET

from app.parsers.clause_patterns import (
    PATTERNS_BY_SPECIFICITY,
    ExtractedClause,
    extract_clause_number,
    merge_clause_range,
    specificity_score,
)

logger = logging.getLogger(__name__)

# XML namespaces
NS = {
    "w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main",
    "w14": "http://schemas.microsoft.com/office/word/2010/wordml",
    "w15": "http://schemas.microsoft.com/office/word/2012/wordml",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
}

COMMENTS_XML = "word/comments.xml"
COMMENTS_EXTENDED_XML = "word/commentsExtended.xml"
DOCUMENT_XML = "word/document.xml"
NUMBERING_XML = "word/numbering.xml"


def _int_to_roman(n: int) -> str:
    val = [1000, 900, 500, 400, 100, 90, 50, 40, 10, 9, 5, 4, 1]
    syms = ["M","CM","D","CD","C","XC","L","XL","X","IX","V","IV","I"]
    result, n = "", max(1, n)
    for v, s in zip(val, syms):
        while n >= v:
            result += s
            n -= v
    return result


def _format_counter(num_fmt: str, counter: int) -> str:
    """Format a single counter value according to its numFmt."""
    fmt = num_fmt.lower()
    if fmt == "decimal":
        return str(counter)
    if fmt == "lowerletter":
        return chr(ord("a") + (counter - 1) % 26)
    if fmt == "upperletter":
        return chr(ord("A") + (counter - 1) % 26)
    if fmt == "lowerroman":
        return _int_to_roman(counter).lower()
    if fmt == "upperroman":
        return _int_to_roman(counter).upper()
    return str(counter)


def _make_list_label(
    num_fmt: str,
    lvl_text: str,
    counter: int,
    all_level_counters: dict[str, int] | None = None,
    all_level_formats: dict[str, str] | None = None,
) -> str:
    """Generate a list label such as '(a)', '1.2', 'iv.' from format + counter.

    Word's lvl_text uses %1 for level 0's value, %2 for level 1's, etc.
    We resolve all placeholders using parent level counters.
    """
    fmt = num_fmt.lower()
    if fmt in ("bullet", "none", ""):
        return ""

    if not lvl_text:
        return _format_counter(num_fmt, counter)

    result = lvl_text
    # Resolve all %N placeholders (N = 1..9, where %N refers to level N-1)
    for n in range(1, 10):
        placeholder = f"%{n}"
        if placeholder not in result:
            continue
        lvl_key = str(n - 1)  # %1 → ilvl "0", %2 → ilvl "1", etc.
        lvl_counter = (all_level_counters or {}).get(lvl_key, 0)
        lvl_fmt = (all_level_formats or {}).get(lvl_key, "decimal")
        if lvl_counter > 0:
            result = result.replace(placeholder, _format_counter(lvl_fmt, lvl_counter))
        else:
            result = result.replace(placeholder, _format_counter(num_fmt, counter))

    return result


def _parse_numbering_formats(
    zf: zipfile.ZipFile,
) -> dict[tuple[str, str], tuple[str, str, int]]:
    """
    Parse word/numbering.xml.
    Returns mapping: (numId, ilvl) -> (numFmt, lvlText, startValue)
    """
    if NUMBERING_XML not in zf.namelist():
        return {}
    W = NS["w"]
    try:
        tree = ET.parse(zf.open(NUMBERING_XML))
    except Exception as exc:
        logger.debug("Failed to parse numbering.xml: %s", exc)
        return {}
    root = tree.getroot()

    # abstractNumId -> {ilvl -> (numFmt, lvlText, start)}
    abstract_nums: dict[str, dict[str, tuple[str, str, int]]] = {}
    for an in root.findall(f"{{{W}}}abstractNum"):
        aid = an.get(f"{{{W}}}abstractNumId", "")
        levels: dict[str, tuple[str, str, int]] = {}
        for lvl in an.findall(f"{{{W}}}lvl"):
            ilvl = lvl.get(f"{{{W}}}ilvl", "0")
            fmt_elem = lvl.find(f"{{{W}}}numFmt")
            text_elem = lvl.find(f"{{{W}}}lvlText")
            start_elem = lvl.find(f"{{{W}}}start")
            fmt = fmt_elem.get(f"{{{W}}}val", "decimal") if fmt_elem is not None else "decimal"
            lvl_text = (text_elem.get(f"{{{W}}}val") or "%1") if text_elem is not None else "%1"
            start = int(start_elem.get(f"{{{W}}}val") or "1") if start_elem is not None else 1
            levels[ilvl] = (fmt, lvl_text, start)
        abstract_nums[aid] = levels

    # numId -> merged config with level overrides applied
    result: dict[tuple[str, str], tuple[str, str, int]] = {}
    for num in root.findall(f"{{{W}}}num"):
        nid = num.get(f"{{{W}}}numId", "")
        if not nid:
            continue
        abstract_ref = num.find(f"{{{W}}}abstractNumId")
        if abstract_ref is None:
            continue
        aid = abstract_ref.get(f"{{{W}}}val", "")
        levels = dict(abstract_nums.get(aid, {}))
        for override in num.findall(f"{{{W}}}lvlOverride"):
            olvl = override.get(f"{{{W}}}ilvl", "0")
            start_override = override.find(f"{{{W}}}startOverride")
            if start_override is not None and olvl in levels:
                fmt, lvl_text, _ = levels[olvl]
                start = int(start_override.get(f"{{{W}}}val") or "1")
                levels[olvl] = (fmt, lvl_text, start)
        for ilvl, config in levels.items():
            result[(nid, ilvl)] = config

    return result


@dataclass
class RawComment:
    comment_id: str
    text: str
    author: str | None
    date: str | None
    parent_id: str | None = None  # for threaded replies


@dataclass
class AnchorRange:
    comment_id: str
    paragraphs: list[str] = field(default_factory=list)  # paragraph texts in anchor range
    anchor_text: str = ""


def _text_of(elem: ET.Element, include_ins: bool = True, skip_del: bool = True) -> str:
    """
    Extract text from an XML element, applying accepted-view tracked changes:
    - Include text within w:ins (insertions)
    - Skip text within w:del (deletions)
    """
    parts = []
    _collect_text(elem, parts, include_ins=include_ins, skip_del=skip_del, in_del=False)
    return "".join(parts)


def _collect_text(
    elem: ET.Element,
    parts: list[str],
    include_ins: bool,
    skip_del: bool,
    in_del: bool,
) -> None:
    tag = elem.tag.split("}")[-1] if "}" in elem.tag else elem.tag

    if skip_del and tag == "del":
        return
    if tag in ("ins", "rPrChange", "pPrChange", "sectPrChange", "tblPrChange", "trPrChange"):
        for child in elem:
            _collect_text(child, parts, include_ins, skip_del, in_del)
        return

    if tag == "t":
        if not in_del:
            parts.append(elem.text or "")
        return
    if tag == "br":
        parts.append("\n")
        return
    if tag == "tab":
        parts.append("\t")
        return

    for child in elem:
        _collect_text(child, parts, include_ins, skip_del, in_del)


def _parse_comments(zf: zipfile.ZipFile) -> dict[str, RawComment]:
    """Parse word/comments.xml into a dict keyed by comment ID."""
    comments: dict[str, RawComment] = {}
    if COMMENTS_XML not in zf.namelist():
        return comments

    tree = ET.parse(zf.open(COMMENTS_XML))
    root = tree.getroot()

    for comment_elem in root.findall(".//w:comment", NS):
        cid = comment_elem.get(f"{{{NS['w']}}}id", "")
        author = comment_elem.get(f"{{{NS['w']}}}author")
        date_str = comment_elem.get(f"{{{NS['w']}}}date")
        text_parts = []
        for para in comment_elem.findall(".//w:p", NS):
            para_text = _text_of(para)
            if para_text.strip():
                text_parts.append(para_text.strip())
        full_text = " ".join(text_parts)
        comments[cid] = RawComment(
            comment_id=cid,
            text=full_text,
            author=author,
            date=date_str,
        )

    return comments


def _parse_comments_extended(
    zf: zipfile.ZipFile, comments: dict[str, RawComment]
) -> dict[str, RawComment]:
    """
    Parse commentsExtended.xml to find threaded reply relationships.
    Updates the parent_id on reply comments.
    Returns a dict of root_comment_id -> merged comment (concat thread).
    """
    if COMMENTS_EXTENDED_XML not in zf.namelist():
        return comments

    try:
        tree = ET.parse(zf.open(COMMENTS_EXTENDED_XML))
        root = tree.getroot()

        for ext_elem in root:
            cid = ext_elem.get(f"{{{NS['w15']}}}id", "") or ext_elem.get(
                f"{{{NS['w14']}}}id", ""
            )
            parent_id = ext_elem.get(f"{{{NS['w15']}}}paraIdParent") or ext_elem.get(
                f"{{{NS['w14']}}}paraIdParent"
            )
            if cid and parent_id and cid in comments:
                comments[cid].parent_id = parent_id
    except Exception as exc:
        logger.debug("commentsExtended.xml parse failed (non-critical): %s", exc)

    return comments


def _build_thread_map(comments: dict[str, RawComment]) -> dict[str, str]:
    """
    Build a mapping: comment_id -> concatenated thread text.
    For top-level comments: includes original + all replies.
    """
    # Group children under parents
    children: dict[str, list[str]] = {}
    for cid, c in comments.items():
        if c.parent_id:
            parent = c.parent_id
            children.setdefault(parent, []).append(cid)

    thread_texts: dict[str, str] = {}
    for cid, c in comments.items():
        if not c.parent_id:  # top-level
            parts = [c.text]
            for reply_id in children.get(cid, []):
                if reply_id in comments:
                    reply_text = comments[reply_id].text
                    if reply_text.strip():
                        parts.append(f"[Reply] {reply_text}")
            thread_texts[cid] = "\n".join(parts)

    return thread_texts


@dataclass
class ParagraphInfo:
    text: str
    # clause_number is resolved lazily — only computed for paragraphs near anchors


def _parse_document_paragraphs(
    zf: zipfile.ZipFile,
) -> tuple[list[ParagraphInfo], dict[str, tuple[int, int]]]:
    """
    Fast single-pass scan of document.xml:
    - Collects paragraph text (no clause-number regex yet)
    - Records commentRangeStart/End positions
    - Prepends generated list labels (e.g. '(a)') to paragraphs whose numbering
      comes from Word list formatting rather than literal text, so that
      _find_enclosing_clause can correctly identify lettered subclauses.

    Clause numbers are extracted lazily in _find_enclosing_clause, only for
    the ~20 paragraphs around each anchor, avoiding O(N) regex over the whole doc.
    """
    W = NS["w"]
    num_config = _parse_numbering_formats(zf)

    tree = ET.parse(zf.open(DOCUMENT_XML))
    root = tree.getroot()

    body = root.find(".//w:body", NS)
    if body is None:
        return [], {}

    paragraphs: list[ParagraphInfo] = []
    open_ranges: dict[str, int] = {}
    anchor_ranges: dict[str, tuple[int, int]] = {}
    # Track list counter per (numId, ilvl)
    list_counters: dict[tuple[str, str], int] = {}

    for para in body.findall(".//w:p", NS):
        para_idx = len(paragraphs)
        para_text = _text_of(para)

        # Attempt to prepend a list label if the paragraph uses Word list numbering
        # and the text doesn't already start with a recognisable clause number.
        list_prefix = ""
        if num_config:
            pPr = para.find(f"{{{W}}}pPr")
            if pPr is not None:
                numPr = pPr.find(f"{{{W}}}numPr")
                if numPr is not None:
                    nid_elem = numPr.find(f"{{{W}}}numId")
                    ilvl_elem = numPr.find(f"{{{W}}}ilvl")
                    if nid_elem is not None and ilvl_elem is not None:
                        nid = nid_elem.get(f"{{{W}}}val", "")
                        ilvl = ilvl_elem.get(f"{{{W}}}val", "0")
                        # numId=0 means "remove list formatting"
                        if nid and nid != "0":
                            config_key = (nid, ilvl)
                            if config_key in num_config:
                                fmt, lvl_text, start = num_config[config_key]
                                if config_key not in list_counters:
                                    list_counters[config_key] = start - 1
                                list_counters[config_key] += 1
                                # Build maps of all level counters/formats for this numId
                                # so multi-level placeholders like %1.%2 resolve correctly
                                all_counters = {
                                    lv: list_counters.get((nid, lv), 0)
                                    for lv in [str(x) for x in range(9)]
                                    if (nid, lv) in num_config
                                }
                                all_formats = {
                                    lv: num_config[(nid, lv)][0]
                                    for lv in [str(x) for x in range(9)]
                                    if (nid, lv) in num_config
                                }
                                generated = _make_list_label(
                                    fmt, lvl_text, list_counters[config_key],
                                    all_counters, all_formats,
                                )
                                if generated and not extract_clause_number(para_text.strip()):
                                    list_prefix = generated + " "

        paragraphs.append(ParagraphInfo(text=list_prefix + para_text if list_prefix else para_text))

        # Scan for comment range markers in this paragraph
        for elem in para.iter():
            tag = elem.tag.split("}")[-1] if "}" in elem.tag else elem.tag
            if tag == "commentRangeStart":
                cid = elem.get(f"{{{W}}}id", "")
                if cid:
                    open_ranges[cid] = para_idx
            elif tag == "commentRangeEnd":
                cid = elem.get(f"{{{W}}}id", "")
                if cid and cid in open_ranges:
                    anchor_ranges[cid] = (open_ranges.pop(cid), para_idx)

    # Close any ranges that never got an End marker
    for cid, start in open_ranges.items():
        anchor_ranges[cid] = (start, len(paragraphs) - 1)

    return paragraphs, anchor_ranges


def _extract_anchor_text(
    paragraphs: list[ParagraphInfo], start_idx: int, end_idx: int
) -> str:
    """Extract the anchor text spanning the given paragraph range."""
    texts = []
    for i in range(start_idx, min(end_idx + 1, len(paragraphs))):
        t = paragraphs[i].text.strip()
        if t:
            texts.append(t)
    return " ".join(texts)


def _clause_num_at(paragraphs: list[ParagraphInfo], idx: int) -> str | None:
    """Lazily extract clause number for a single paragraph by index."""
    return extract_clause_number(paragraphs[idx].text)


def _is_block_start(text: str) -> bool:
    """
    Return True if this paragraph text looks like the start of a new block:
    - Starts with a quote character (definition entry like "GDPR" means…)
    - Is a short ALL-CAPS heading (section title like DPA TERMS)
    - Is a short Title Case heading (section title like "Changes to this Policy")
    """
    t = text.strip()
    if not t:
        return False
    if t[0] in ('"', '\u201c'):
        return True
    # Short heading detection
    if len(t) < 80 and any(c.isalpha() for c in t):
        # Remove trailing punctuation for check
        clean = t.rstrip(".:;")
        # ALL-CAPS heading
        if clean == clean.upper():
            return True
        # Title Case heading: short line, first word capitalized, doesn't end
        # with sentence-continuation punctuation, and no lowercase-starting words
        # except common small words (of, to, the, a, an, and, or, in, for, etc.)
        SMALL_WORDS = {"of", "to", "the", "a", "an", "and", "or", "in", "for", "on", "at", "by", "with", "this", "that"}
        words = clean.split()
        if 2 <= len(words) <= 10 and words[0][0].isupper():
            cap_count = sum(1 for w in words if w[0].isupper() or w.lower() in SMALL_WORDS)
            if cap_count == len(words) and not t.endswith(","):
                return True
    return False


def _refine_around_anchor(
    paragraphs: list[ParagraphInfo],
    anchor_start: int,
    anchor_end: int,
    clause_start: int,
    clause_end: int,
) -> tuple[int, int]:
    """
    Narrow a large clause range to just the block around the anchor.
    Scans backward/forward for block boundaries (blank lines, definition starts,
    or section headings). Falls back to anchor ± 2 paragraphs if none found.
    """
    # Scan backward: find the nearest block start before the anchor.
    # The anchor paragraph itself might be a block start — that's fine, keep it.
    # But a *different* block start before us means we stop after it.
    blk_start = anchor_start
    for i in range(anchor_start - 1, max(clause_start - 1, anchor_start - 21), -1):
        text = paragraphs[i].text.strip()
        if not text:
            # Empty paragraph — block boundary; start after it
            blk_start = i + 1
            break
        if _is_block_start(text):
            # This is the start of the *previous* block — don't include it
            blk_start = i + 1
            break
    else:
        # No boundary found — just use the anchor range itself
        blk_start = anchor_start

    # Scan forward: find the next block start or empty line after the anchor.
    blk_end = anchor_end
    for i in range(anchor_end + 1, min(clause_end + 1, anchor_end + 21)):
        text = paragraphs[i].text.strip()
        if not text:
            blk_end = i - 1
            break
        if _is_block_start(text):
            # Next block starts here — stop before it
            blk_end = i - 1
            break
    else:
        # No boundary found — just use the anchor range itself
        blk_end = anchor_end

    return blk_start, blk_end


def _find_enclosing_clause(
    paragraphs: list[ParagraphInfo],
    anchor_start: int,
    anchor_end: int,
) -> tuple[str | None, str, str, str]:
    """
    Find the smallest numbered subclause that fully contains the anchor range.
    Clause numbers are extracted on-demand only for the ~20 paragraphs searched.

    Returns: (clause_number, clause_text, expansion_method, confidence)
    """
    best_clause_num: str | None = None
    best_score = -1
    best_clause_start = anchor_start
    best_clause_end = anchor_end

    # Search backward up to 20 paragraphs for the nearest clause heading
    search_start = max(0, anchor_start - 20)
    for i in range(anchor_start, search_start - 1, -1):
        num = _clause_num_at(paragraphs, i)
        if num:
            score = specificity_score(num)
            if score > best_score:
                best_score = score
                best_clause_num = num
                best_clause_start = i
                best_clause_end = _find_clause_end(paragraphs, i, num)
                break

    if best_clause_num is None:
        # Fallback: scan for block boundaries (blank lines or definition starts).
        blk_start, blk_end = _refine_around_anchor(
            paragraphs, anchor_start, anchor_end,
            max(0, anchor_start - 20), min(len(paragraphs) - 1, anchor_end + 20),
        )
        para_text = "\n\n".join(
            paragraphs[i].text
            for i in range(blk_start, blk_end + 1)
            if paragraphs[i].text.strip()
        )
        return None, para_text or paragraphs[anchor_start].text, "blank_line_boundary", "medium"

    clause_text = "\n\n".join(
        paragraphs[i].text
        for i in range(best_clause_start, min(best_clause_end + 1, len(paragraphs)))
        if paragraphs[i].text.strip()
    )

    # Refine when clause text is large OR the anchor is far from the clause heading.
    # This catches cases where a numbered heading was found several sections above
    # and the total text is moderate but includes unrelated sections.
    MAX_CLAUSE_CHARS = 800
    anchor_distance = anchor_start - best_clause_start
    if len(clause_text) > MAX_CLAUSE_CHARS or anchor_distance > 3:
        blk_start, blk_end = _refine_around_anchor(
            paragraphs, anchor_start, anchor_end, best_clause_start, best_clause_end
        )
        refined = "\n\n".join(
            paragraphs[i].text
            for i in range(blk_start, blk_end + 1)
            if paragraphs[i].text.strip()
        )
        if refined.strip() and len(refined) < len(clause_text):
            return best_clause_num, refined, "numbered_refined", "high"

    return best_clause_num, clause_text, "numbered_subclause", "high"


def _find_clause_end(
    paragraphs: list[ParagraphInfo], start_idx: int, clause_number: str
) -> int:
    """
    Find the last paragraph belonging to this clause.
    Scans forward up to 100 paragraphs, extracting clause numbers on demand.
    """
    base_level = specificity_score(clause_number)
    for i in range(start_idx + 1, min(start_idx + 100, len(paragraphs))):
        num = _clause_num_at(paragraphs, i)
        if num and specificity_score(num) >= base_level:
            return i - 1
    return min(start_idx + 50, len(paragraphs) - 1)


def _check_boundary_span(
    paragraphs: list[ParagraphInfo], anchor_start: int, anchor_end: int
) -> bool:
    """Return True if the anchor range straddles two distinct clause boundaries.

    We find the enclosing clause heading for anchor_start (scanning backward)
    and for anchor_end (scanning backward from end). Only if they resolve to
    different clause numbers is this a true boundary span.
    """
    start_num = None
    end_num = None

    # Find clause heading for the start of the anchor (scan backward)
    for i in range(anchor_start, max(-1, anchor_start - 21), -1):
        num = _clause_num_at(paragraphs, i)
        if num:
            start_num = num
            break

    # Find clause heading for the end of the anchor (scan backward from end)
    for i in range(anchor_end, max(-1, anchor_end - 21), -1):
        num = _clause_num_at(paragraphs, i)
        if num:
            end_num = num
            break

    return start_num is not None and end_num is not None and start_num != end_num


def parse_docx(file_bytes: bytes) -> list[ExtractedClause]:
    """
    Parse a DOCX file and extract all legal comments with their clause context.

    Returns a list of ExtractedClause objects (one per comment; merging to clause
    cards happens in the Celery task).
    """
    import io
    results: list[ExtractedClause] = []
    buf = io.BytesIO(file_bytes)

    with zipfile.ZipFile(buf) as zf:
        # Step 1: Parse comments
        raw_comments = _parse_comments(zf)
        if not raw_comments:
            logger.info("No comments found in DOCX")
            return []

        # Step 2: Thread concat
        raw_comments = _parse_comments_extended(zf, raw_comments)
        thread_map = _build_thread_map(raw_comments)

        # Step 3: Parse document paragraphs
        paragraphs, anchor_ranges = _parse_document_paragraphs(zf)

        # Step 4: For each top-level comment, find anchor and expand clause
        for cid, thread_text in thread_map.items():
            if not thread_text.strip():
                continue

            comment = raw_comments.get(cid)
            if comment is None:
                continue

            if cid not in anchor_ranges:
                logger.debug("Comment %s has no anchor range, skipping", cid)
                continue

            anchor_start, anchor_end = anchor_ranges[cid]
            anchor_text = _extract_anchor_text(paragraphs, anchor_start, anchor_end)

            # Check if anchor straddles a boundary
            is_boundary = _check_boundary_span(paragraphs, anchor_start, anchor_end)

            if is_boundary:
                # Get both clause texts and merge
                _, clause_a, _, _ = _find_enclosing_clause(paragraphs, anchor_start, anchor_start)
                _, clause_b, _, _ = _find_enclosing_clause(paragraphs, anchor_end, anchor_end)
                merged = merge_clause_range(clause_a, clause_b, anchor_text)
                merged.comment_texts = [thread_text]
                merged.comment_authors = [comment.author]
                merged.comment_timestamps = [comment.date]
                merged.anchor_para_idx = anchor_start
                results.append(merged)
            else:
                clause_num, clause_text, expansion_method, confidence = _find_enclosing_clause(
                    paragraphs, anchor_start, anchor_end
                )
                results.append(
                    ExtractedClause(
                        clause_number=clause_num,
                        anchor_text=anchor_text,
                        clause_text=clause_text,
                        expansion_method=expansion_method,
                        confidence=confidence,
                        comment_texts=[thread_text],
                        comment_authors=[comment.author],
                        comment_timestamps=[comment.date],
                        anchor_para_idx=anchor_start,
                    )
                )

    return results


def get_first_page_text_docx(file_bytes: bytes) -> str:
    """Extract text from the first ~3000 chars of the document for doc_kind detection."""
    import io

    buf = io.BytesIO(file_bytes)
    with zipfile.ZipFile(buf) as zf:
        tree = ET.parse(zf.open(DOCUMENT_XML))
        root = tree.getroot()
        body = root.find(".//w:body", NS)
        if body is None:
            return ""
        text_parts = []
        for para in body.findall(".//w:p", NS):
            t = _text_of(para).strip()
            if t:
                text_parts.append(t)
            if sum(len(p) for p in text_parts) > 3000:
                break
        return "\n".join(text_parts)[:3000]
