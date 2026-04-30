import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures"


def _read_fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def _load_scraper(module_name: str, scraper_dir: str):
    module_path = ROOT / scraper_dir / "scraper.py"
    sys.path.insert(0, str(ROOT))
    sys.path.insert(0, str(ROOT / scraper_dir))
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def test_marinetraffic_golden():
    module = _load_scraper("marinetraffic_scraper", "marinetraffic")
    list_rows = module.parse_vessel_list_page(
        _read_fixture("marinetraffic_list.html")
    )
    assert len(list_rows) == 1
    detail = module.parse_vessel_detail_page(
        _read_fixture("marinetraffic_detail.html")
    )
    assert detail["mmsi"] == "477642800"
    assert detail["gt"] == 153115
    assert detail["dwt"] == 281456


def test_marinetraffic_normalize_mmsi():
    module = _load_scraper("marinetraffic_norm", "marinetraffic")
    assert module.normalize_mmsi("477642800") == "477642800"
    assert module.normalize_mmsi("477 642 800") == "477642800"
    assert module.normalize_mmsi("MMSI: 477642800") == "477642800"
    assert module.normalize_mmsi("1") is None
    assert module.normalize_mmsi("") is None
    assert module.normalize_mmsi(None) is None


def test_marinetraffic_detail_invalid_mmsi_not_stored():
    module = _load_scraper("marinetraffic_bad_mmsi", "marinetraffic")
    detail = module.parse_vessel_detail_page(
        _read_fixture("marinetraffic_detail_bad_mmsi.html")
    )
    assert detail.get("mmsi") is None


def test_marinetraffic_detail_spaced_mmsi_normalized():
    module = _load_scraper("marinetraffic_spaced", "marinetraffic")
    detail = module.parse_vessel_detail_page(
        _read_fixture("marinetraffic_detail_mmsi_spaced.html")
    )
    assert detail["mmsi"] == "477642800"


def test_marinetraffic_name_cleanup():
    module = _load_scraper("marinetraffic_name_cleanup", "marinetraffic")
    assert (
        module.normalize_vessel_name("BLUEIMO: 9862231MMSI: 319239400")
        == "BLUE"
    )
    rows = module.parse_vessel_list_page(
        _read_fixture("marinetraffic_list_bad_name.html")
    )
    assert len(rows) == 1
    assert rows[0]["name"] == "BLUE"


def test_marinetraffic_label_and_numeric_cleanup():
    module = _load_scraper("marinetraffic_label_cleanup", "marinetraffic")
    assert module.normalize_label_text(" unknown ") is None
    assert module.normalize_label_text("Panama") == "Panama"
    assert module.normalize_label_text("Cargo IMO: 1234567") == "Cargo"
    assert module.sanitize_numeric("399", min_value=10, max_value=500) == 399
    assert module.sanitize_numeric("1", min_value=10, max_value=500) is None


def test_myshiptracking_golden():
    module = _load_scraper("myshiptracking_scraper", "myshiptracking")
    list_rows = module.parse_vessel_list_page(
        _read_fixture("myshiptracking_list.html")
    )
    assert len(list_rows) == 1
    vessel = module.parse_vessel_detail_page(
        _read_fixture("myshiptracking_detail.html"), dict(list_rows[0])
    )
    assert vessel["mmsi"] == "305123456"
    assert vessel["gt"] == 30024
    assert vessel["dwt"] == 46219


def test_myshiptracking_normalizers():
    module = _load_scraper("myshiptracking_norm", "myshiptracking")
    assert module.normalize_mmsi("305 123 456") == "305123456"
    assert module.normalize_mmsi("1") is None
    assert (
        module.normalize_vessel_name("BLUE IMO: 9862231 MMSI: 319239400")
        == "BLUE"
    )
    assert module.normalize_label_text(" unknown ") is None
    assert module.sanitize_numeric("399", min_value=10, max_value=500) == 399
    assert module.sanitize_numeric("1", min_value=10, max_value=500) is None


def test_maritime_database_golden():
    module = _load_scraper("maritime_scraper", "maritime_database")
    list_rows = module.parse_vessel_list_page(
        _read_fixture("maritime_list.html")
    )
    assert len(list_rows) == 1
    vessel = module.parse_vessel_detail_page(
        _read_fixture("maritime_detail.html"), dict(list_rows[0])
    )
    assert vessel["mmsi"] == "477642800"
    assert vessel["length"] == 399
    assert vessel["width"] == 60


def test_maritime_database_normalizers():
    module = _load_scraper("maritime_norm", "maritime_database")
    assert module.normalize_mmsi("477 642 800") == "477642800"
    assert module.normalize_mmsi("1") is None
    assert (
        module.normalize_vessel_name("ARAON IMO: 9490935 MMSI: 441619000")
        == "ARAON"
    )
    assert module.normalize_label_text(" unknown ") is None
    assert module.sanitize_numeric("399", min_value=10, max_value=500) == 399
    assert module.sanitize_numeric("1", min_value=10, max_value=500) is None


def test_vesselfinder_golden(monkeypatch):
    module = _load_scraper("vesselfinder_scraper", "vesselfinder")
    monkeypatch.setattr(
        module,
        "fetch_page",
        lambda *_args, **_kwargs: _read_fixture("vesselfinder_detail.html"),
    )
    monkeypatch.setattr(
        module, "download_image", lambda *_args, **_kwargs: None
    )
    vessel = module.parse_vessel("https://example.com/vessel")
    assert vessel is not None
    assert vessel["mmsi"] == "477642800"
    assert vessel["year_built"] == 2016


def test_vesselfinder_handles_broken_html(monkeypatch):
    module = _load_scraper("vesselfinder_scraper_broken", "vesselfinder")
    monkeypatch.setattr(
        module,
        "fetch_page",
        lambda *_args, **_kwargs: "<html><body>broken</body></html>",
    )
    monkeypatch.setattr(
        module, "download_image", lambda *_args, **_kwargs: None
    )
    vessel = module.parse_vessel("https://example.com/broken")
    assert vessel is not None
    assert vessel["mmsi"] is None


def test_vesselfinder_normalizers():
    module = _load_scraper("vesselfinder_norm", "vesselfinder")
    assert module.normalize_mmsi("477 642 800") == "477642800"
    assert module.normalize_mmsi("1") is None
    assert (
        module.normalize_vessel_name("BLUE IMO: 9862231 MMSI: 319239400")
        == "BLUE"
    )
    assert module.normalize_label_text(" unknown ") is None
    assert module.sanitize_numeric("399", min_value=10, max_value=500) == 399
    assert module.sanitize_numeric("1", min_value=10, max_value=500) is None


def test_vesselfinder_metric_fallbacks(monkeypatch):
    module = _load_scraper("vesselfinder_metric_fallbacks", "vesselfinder")
    html = """
    <html><body>
      <h1>TEST SHIP</h1>
      <div>IMO 1234567 MMSI 477642800</div>
      <div>LOA: 399 m</div>
      <div>GT: 153,115</div>
      <div>DWT: 281,456 t</div>
      <img class="main-photo" src="https://example.com/a.jpg" />
    </body></html>
    """
    monkeypatch.setattr(
        module, "fetch_page", lambda *_args, **_kwargs: html
    )
    monkeypatch.setattr(
        module, "download_image", lambda *_args, **_kwargs: None
    )
    vessel = module.parse_vessel("https://example.com/fallback")
    assert vessel is not None
    assert vessel["length"] == 399
    assert vessel["gt"] == 153115
    assert vessel["dwt"] == 281456
