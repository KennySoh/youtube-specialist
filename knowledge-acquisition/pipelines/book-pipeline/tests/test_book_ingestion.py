"""Book store tests. store.py needs only the standard library, so these run without Docker."""
import pytest

from book_ingestion import store


@pytest.fixture(autouse=True)
def tmp_knowledge(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "KNOWLEDGE", tmp_path / "books")
    monkeypatch.setattr(store, "STATE", tmp_path / "state")
    monkeypatch.setattr(store, "BOOKS", tmp_path / "raw")
    (tmp_path / "books").mkdir()
    (tmp_path / "state").mkdir()
    return tmp_path


def test_read_books():
    (store.STATE / "books.txt").write_text(
        "# <slug> <path>\n\n# product-manager\nthe-mom-test    Business/The Mom Test.pdf\n  ddd  DDD/Evans - Domain Driven.pdf  \n")
    assert store.read_books() == {"the-mom-test": store.BOOKS / "Business/The Mom Test.pdf",
                                  "ddd": store.BOOKS / "DDD/Evans - Domain Driven.pdf"}


def test_write_chapters_format_and_keeps_notes(tmp_path):
    book = store.book_dir("b")
    book.mkdir()
    (book / "notes.md").write_text("curated")
    (book / "chapters").mkdir()
    (book / "chapters" / "99-stale.md").write_text("old")
    pages = ["first page", "second page", "third page"]
    store.write_chapters("b", tmp_path / "Some Book.pdf", pages, [("Front matter", 0, 1), ("Chapter 1: Why?", 1, 3)])
    assert (book / "notes.md").read_text() == "curated"
    assert sorted(p.name for p in (book / "chapters").iterdir()) == ["00-front-matter.md", "01-chapter-1-why.md"]
    assert (book / "chapters" / "01-chapter-1-why.md").read_text() == (
        "<!-- Chapter 1: Why? | Some Book.pdf | PDF pages 2-3 -->\n\n"
        "<!-- p.2 -->\nsecond page\n\n<!-- p.3 -->\nthird page")
    assert store.has_chapters("b") and not store.has_chapters("other")


def test_acquisition_files_stay_out_of_the_library():
    """books.txt and the OCR cache are Acquisition's; the library only gets chapters/ (and notes.md from /extract-book)."""
    assert store.ocr_cache("b") == store.STATE / "b" / "ocr.pdf"
    store.write_chapters("b", store.BOOKS / "B.pdf", ["page"], [("One", 0, 1)])
    assert [p.name for p in store.book_dir("b").iterdir()] == ["chapters"]
