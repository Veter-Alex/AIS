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
    list_rows = module.parse_vessel_list_page(_read_fixture("marinetraffic_list.html"))
    assert len(list_rows) == 1
    detail = module.parse_vessel_detail_page(_read_fixture("marinetraffic_detail.html"))
    assert detail["mmsi"] == "477642800"
    assert detail["gt"] == 153115
    assert detail["dwt"] == 281456


def test_myshiptracking_golden():
    module = _load_scraper("myshiptracking_scraper", "myshiptracking")
    list_rows = module.parse_vessel_list_page(_read_fixture("myshiptracking_list.html"))
    assert len(list_rows) == 1
    vessel = module.parse_vessel_detail_page(
        _read_fixture("myshiptracking_detail.html"), dict(list_rows[0])
    )
    assert vessel["mmsi"] == "305123456"
    assert vessel["gt"] == 30024
    assert vessel["dwt"] == 46219


def test_maritime_database_golden():
    module = _load_scraper("maritime_scraper", "maritime_database")
    list_rows = module.parse_vessel_list_page(_read_fixture("maritime_list.html"))
    assert len(list_rows) == 1
    vessel = module.parse_vessel_detail_page(
        _read_fixture("maritime_detail.html"), dict(list_rows[0])
    )
    assert vessel["mmsi"] == "477642800"
    assert vessel["length"] == 399
    assert vessel["width"] == 60


def test_vesselfinder_golden(monkeypatch):
    module = _load_scraper("vesselfinder_scraper", "vesselfinder")
    monkeypatch.setattr(
        module, "get_html_with_selenium", lambda *_args, **_kwargs: _read_fixture("vesselfinder_detail.html")
    )
    monkeypatch.setattr(module, "download_image", lambda *_args, **_kwargs: None)
    vessel = module.parse_vessel("https://example.com/vessel")
    assert vessel is not None
    assert vessel["mmsi"] == "477642800"
    assert vessel["year_built"] == 2016

