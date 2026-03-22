from pathlib import Path

from scripts.import_geonames_cities import parse_cities15000_line, parse_country_info


def test_parse_country_info(tmp_path: Path):
    file_path = tmp_path / "countryInfo.txt"
    file_path.write_text(
        "# comment\n"
        "AR\tARG\t032\tAR\tArgentina\tBuenos Aires\n"
        "ZA\tZAF\t710\tSF\tSouth Africa\tPretoria\n",
        encoding="utf-8",
    )

    mapping = parse_country_info(file_path)
    assert mapping["AR"] == "Argentina"
    assert mapping["ZA"] == "South Africa"


def test_parse_cities15000_line_success():
    countries = {"AR": "Argentina"}
    line = (
        "3435910\tBuenos Aires\tBuenos Aires\tBuenos Aires,Буэнос-Айрес\t"
        "-34.61315\t-58.37723\tP\tPPLC\tAR\t\t07\t\t\t\t2891082\t0\t0\tAmerica/Argentina/Buenos_Aires\t2024-01-01\n"
    )

    parsed = parse_cities15000_line(line, countries)
    assert parsed is not None
    assert parsed.geoname_id == 3435910
    assert parsed.name == "Buenos Aires"
    assert "Буэнос-Айрес" in parsed.alternate_names
    assert parsed.country_name == "Argentina"
    assert parsed.timezone == "America/Argentina/Buenos_Aires"


def test_parse_cities15000_line_invalid():
    countries = {}
    assert parse_cities15000_line("bad\tline\n", countries) is None
