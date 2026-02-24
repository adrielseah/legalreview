"""
Pytest configuration.
Ensures test fixtures are created before tests run.
"""
import pytest
from pathlib import Path


def pytest_configure(config):
    """Create test fixtures if they don't exist."""
    fixtures_dir = Path(__file__).parent / "tests" / "fixtures"
    fixtures_dir.mkdir(exist_ok=True)
    docx_path = fixtures_dir / "sample.docx"
    if not docx_path.exists():
        try:
            from tests.create_fixtures import create_sample_docx
            create_sample_docx()
        except Exception as e:
            print(f"Warning: Could not create DOCX fixture: {e}")

    pdf_path = fixtures_dir / "sample.pdf"
    if not pdf_path.exists():
        try:
            from tests.create_fixtures import create_sample_pdf
            create_sample_pdf()
        except Exception as e:
            print(f"Warning: Could not create PDF fixture: {e}")
