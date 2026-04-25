import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "marinetraffic"))
sys.path.insert(0, str(ROOT / "myshiptracking"))
sys.path.insert(0, str(ROOT / "maritime_database"))
sys.path.insert(0, str(ROOT / "vesselfinder"))


def test_marinetraffic_list_parser_smoke():
    import scraper as marinetraffic_scraper  # type: ignore

    result = marinetraffic_scraper.parse_vessel_list_page("<html></html>")
    assert isinstance(result, list)


def test_myshiptracking_list_parser_smoke():
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "myshiptracking_scraper", ROOT / "myshiptracking" / "scraper.py"
    )
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    result = module.parse_vessel_list_page("<html></html>")
    assert isinstance(result, list)


def test_maritime_list_parser_smoke():
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "maritime_scraper", ROOT / "maritime_database" / "scraper.py"
    )
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    result = module.parse_vessel_list_page("<html></html>")
    assert isinstance(result, list)


def test_vesselfinder_parse_smoke():
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "vesselfinder_scraper", ROOT / "vesselfinder" / "scraper.py"
    )
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    assert hasattr(module, "parse_vessel")
    assert hasattr(module, "get_vessel_links")

