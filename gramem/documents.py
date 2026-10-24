"""Explicit local knowledge import. Transport and crawling belong to Hermes tools."""

from pathlib import Path

from .tokens import limit


def read_document(path: Path):
    path = Path(path)
    if path.stat().st_size > 20_000_000:
        raise ValueError("document exceeds 20 MB")
    if path.suffix.lower() == ".pdf":
        try:
            from pypdf import PdfReader
        except ImportError as exc:
            raise ValueError("PDF import requires the documents optional dependencies") from exc

        return "\n".join(page.extract_text() or "" for page in PdfReader(path).pages)
    if path.suffix.lower() == ".docx":
        try:
            from docx import Document
        except ImportError as exc:
            raise ValueError("DOCX import requires the documents optional dependencies") from exc

        doc = Document(path)
        return "\n".join(
            [p.text for p in doc.paragraphs]
            + [" | ".join(c.text for c in row.cells) for table in doc.tables for row in table.rows]
        )
    return path.read_text(encoding="utf-8")


def chunks(text, budget=500, overlap=50):
    if budget <= overlap or overlap < 0:
        raise ValueError("invalid chunk budget")
    remaining = text
    while remaining:
        piece = limit(remaining, budget)
        if not piece:
            raise ValueError("chunk budget is too small")
        yield piece
        if len(piece) == len(remaining):
            break
        tail = limit(piece[::-1], overlap)[::-1]
        # Ensure progress even when tokenizer counts vary across reversed text.
        remaining = tail + remaining[len(piece) :]


def ingest(engine, p, path, **kwargs):
    """Compatibility entry: preserve originals and index source-located knowledge."""
    from .knowledge import Knowledge

    return Knowledge(engine).ingest(p, path, **kwargs)
