from pathlib import Path

from pypdf import PdfWriter

from prompt_architect.llm.context import ContextGrantStore, ContextLoader


def test_authorized_text_is_redacted_before_model_context(tmp_path: Path) -> None:
    source = tmp_path / "example.py"
    source.write_text("api_key = 'sk-testonly1234567890abcdef'\nprint('safe')", encoding="utf-8")
    store = ContextGrantStore(tmp_path / "temp")
    grant = store.grant_desktop([str(source)])
    bundle = ContextLoader().load(store.consume([grant.id]))
    assert "[REDACTED]" in bundle.text
    assert "sk-testonly" not in bundle.text
    assert bundle.warnings


def test_image_only_pdf_reports_clear_warning(tmp_path: Path) -> None:
    source = tmp_path / "scan.pdf"
    writer = PdfWriter()
    writer.add_blank_page(width=100, height=100)
    with source.open("wb") as stream:
        writer.write(stream)
    store = ContextGrantStore(tmp_path / "temp")
    grant = store.grant_desktop([str(source)])
    bundle = ContextLoader().load(store.consume([grant.id]))
    assert not bundle.text
    assert any("扫描版" in item for item in bundle.warnings)


def test_stale_uploaded_context_is_removed_on_restart(tmp_path: Path) -> None:
    temp = tmp_path / "temp"
    stale = temp / "stale-session"
    stale.mkdir(parents=True)
    (stale / "secret.txt").write_text("temporary", encoding="utf-8")
    ContextGrantStore(temp)
    assert not stale.exists()
