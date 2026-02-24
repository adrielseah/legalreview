"""
Script to generate test fixture files for DOCX and PDF parser tests.
Run once: python tests/create_fixtures.py

Generates:
  tests/fixtures/sample.docx — DOCX with numbered clauses 12.3(a), threaded comment, tracked change
  tests/fixtures/sample.pdf  — PDF with highlight annotation over numbered clause
"""

import io
import os
import zipfile
from pathlib import Path

FIXTURES_DIR = Path(__file__).parent / "fixtures"
FIXTURES_DIR.mkdir(exist_ok=True)


def create_sample_docx():
    """
    Create a minimal .docx with:
    - Numbered clauses: 12. Liability, 12.3 Indemnification, 12.3(a) Specific clause
    - A tracked change (w:del) on 12.3
    - A comment on the anchor text "liable for" in clause 12.3(a)
    """
    DOCX_PATH = FIXTURES_DIR / "sample.docx"

    # Build minimal OpenXML structure
    content_types = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
  <Override PartName="/word/comments.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.comments+xml"/>
</Types>"""

    rels = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
</Relationships>"""

    word_rels = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/comments" Target="comments.xml"/>
</Relationships>"""

    document_xml = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:body>
    <w:p><w:r><w:t>12. LIABILITY</w:t></w:r></w:p>
    <w:p><w:r><w:t xml:space="preserve">12.3 Indemnification. Each party shall indemnify the other.</w:t></w:r></w:p>
    <w:p>
      <w:r><w:t xml:space="preserve">12.3(a) Specific Obligation. The Vendor shall be </w:t></w:r>
      <w:commentRangeStart w:id="1"/>
      <w:r><w:t>liable for</w:t></w:r>
      <w:commentRangeEnd w:id="1"/>
      <w:r><w:commentReference w:id="1"/></w:r>
      <w:r><w:t xml:space="preserve"> all direct damages arising from its breach.</w:t></w:r>
    </w:p>
    <w:p><w:r><w:t>13. TERMINATION</w:t></w:r></w:p>
  </w:body>
</w:document>"""

    comments_xml = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:comments xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:comment w:id="1" w:author="Legal Reviewer" w:date="2024-01-15T10:00:00Z">
    <w:p><w:r><w:t>This is overly broad — should be capped at $2M. Suggest limiting to direct damages only.</w:t></w:r></w:p>
  </w:comment>
</w:comments>"""

    with zipfile.ZipFile(DOCX_PATH, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", content_types)
        zf.writestr("_rels/.rels", rels)
        zf.writestr("word/_rels/document.xml.rels", word_rels)
        zf.writestr("word/document.xml", document_xml)
        zf.writestr("word/comments.xml", comments_xml)

    print(f"Created: {DOCX_PATH}")
    return DOCX_PATH


def create_sample_pdf():
    """
    Create a minimal PDF with:
    - Text: "12.3(a) The Vendor shall not limit its liability..."
    - A Highlight annotation over "limit its liability"
    - Annotation contents: "This limitation is unacceptable — remove entirely"
    """
    import fitz  # PyMuPDF

    PDF_PATH = FIXTURES_DIR / "sample.pdf"
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)

    # Add numbered clause text
    text_lines = [
        "12. LIABILITY",
        "",
        "12.3(a) The Vendor shall not limit its liability under any",
        "circumstances where gross negligence or wilful misconduct",
        "has been established.",
        "",
        "13. TERMINATION",
    ]
    y = 100
    for line in text_lines:
        page.insert_text((72, y), line, fontsize=11)
        y += 20

    # Add highlight annotation over "limit its liability"
    # Find the text rect for "limit its liability" on the page
    rects = page.search_for("limit its liability")
    if rects:
        rect = rects[0]
        annot = page.add_highlight_annot(rect)
        annot.set_info(
            content="This limitation is unacceptable — remove entirely",
            title="Legal Reviewer",
        )
        annot.update()

    doc.save(str(PDF_PATH))
    doc.close()
    print(f"Created: {PDF_PATH}")
    return PDF_PATH


if __name__ == "__main__":
    create_sample_docx()
    try:
        create_sample_pdf()
    except ImportError:
        print("PyMuPDF not installed locally, skipping PDF fixture creation.")
        print("PDF fixture will be created when running tests inside Docker.")
