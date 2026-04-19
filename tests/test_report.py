import tempfile
from pathlib import Path
from analyze import analyze
from report import generate_html
from tests.fixtures import SAMPLE_DEALS


class TestGenerateHtml:
    def test_creates_html_file(self):
        stats = analyze(SAMPLE_DEALS, street="דיזנגוף", settlement="תל אביב")
        with tempfile.TemporaryDirectory() as tmpdir:
            path = generate_html(stats, output_dir=tmpdir, street="דיזנגוף")
            assert Path(path).exists()
            assert path.endswith(".html")

    def test_html_contains_street_name(self):
        stats = analyze(SAMPLE_DEALS, street="דיזנגוף", settlement="תל אביב")
        with tempfile.TemporaryDirectory() as tmpdir:
            path = generate_html(stats, output_dir=tmpdir, street="דיזנגוף")
            content = Path(path).read_text(encoding="utf-8")
            assert "דיזנגוף" in content

    def test_html_contains_price_data(self):
        stats = analyze(SAMPLE_DEALS, street="דיזנגוף", settlement="תל אביב")
        with tempfile.TemporaryDirectory() as tmpdir:
            path = generate_html(stats, output_dir=tmpdir, street="דיזנגוף")
            content = Path(path).read_text(encoding="utf-8")
            assert "₪" in content

    def test_html_is_rtl(self):
        stats = analyze(SAMPLE_DEALS, street="דיזנגוף", settlement="תל אביב")
        with tempfile.TemporaryDirectory() as tmpdir:
            path = generate_html(stats, output_dir=tmpdir, street="דיזנגוף")
            content = Path(path).read_text(encoding="utf-8")
            assert 'dir="rtl"' in content

    def test_empty_deals_no_crash(self):
        stats = analyze([], street="טסט", settlement="טסט")
        with tempfile.TemporaryDirectory() as tmpdir:
            path = generate_html(stats, output_dir=tmpdir, street="טסט")
            assert Path(path).exists()
