from src.application.city_search import (
    normalize_city_query,
    normalize_ascii_query,
    pick_localized_name,
)


def test_normalize_city_query():
    assert normalize_city_query("   Buenos---Aires   ") == "buenos aires"
    assert normalize_city_query("Кейп\t\tТаун") == "кейп таун"
    assert normalize_city_query("Ёлгава") == "елгава"


def test_normalize_ascii_query():
    assert normalize_ascii_query("кейптаун").startswith("keipt")
    assert normalize_ascii_query("Málaga") == "malaga"


def test_pick_localized_name_ru_prefers_cyrillic():
    localized = pick_localized_name(
        name="Buenos Aires",
        name_ascii="Buenos Aires",
        alternate_names=["Buenos Aires", "Буэнос-Айрес"],
        lang="ru",
    )
    assert localized == "Буэнос-Айрес"


def test_pick_localized_name_ru_uses_best_query_match_not_first_cyrillic():
    localized = pick_localized_name(
        name="Cape Town",
        name_ascii="Cape Town",
        alternate_names=["Капске Місто", "Кейптаун", "Кејптаун"],
        lang="ru",
        query="кейптаун",
    )
    assert localized == "Кейптаун"


def test_pick_localized_name_en_prefers_ascii():
    localized = pick_localized_name(
        name="München",
        name_ascii="Munchen",
        alternate_names=["Мюнхен"],
        lang="en",
    )
    assert localized == "Munchen"
