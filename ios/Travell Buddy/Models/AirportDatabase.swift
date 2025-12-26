//
//  AirportDatabase.swift
//  Travell Buddy
//
//  Database of cities and airports for autocomplete.
//

import Foundation

struct CityAirport: Identifiable, Equatable {
    let id = UUID()
    let cityName: String
    let cityNameEn: String
    let countryName: String
    let airports: [Airport]

    struct Airport: Identifiable, Equatable {
        let id = UUID()
        let code: String
        let name: String
        let cityName: String
    }

    var displayName: String {
        "\(cityName), \(countryName)"
    }

    var primaryAirport: Airport {
        airports.first ?? Airport(code: "", name: "", cityName: cityName)
    }
}

class AirportDatabase {
    static let shared = AirportDatabase()

    private init() {}

    // База данных популярных городов и аэропортов
    let cities: [CityAirport] = [
        // Россия
        CityAirport(
            cityName: "Москва",
            cityNameEn: "Moscow",
            countryName: "Россия",
            airports: [
                .init(code: "SVO", name: "Шереметьево", cityName: "Москва"),
                .init(code: "DME", name: "Домодедово", cityName: "Москва"),
                .init(code: "VKO", name: "Внуково", cityName: "Москва")
            ]
        ),
        CityAirport(
            cityName: "Санкт-Петербург",
            cityNameEn: "Saint Petersburg",
            countryName: "Россия",
            airports: [
                .init(code: "LED", name: "Пулково", cityName: "Санкт-Петербург")
            ]
        ),
        CityAirport(
            cityName: "Сочи",
            cityNameEn: "Sochi",
            countryName: "Россия",
            airports: [
                .init(code: "AER", name: "Адлер", cityName: "Сочи")
            ]
        ),

        // Турция
        CityAirport(
            cityName: "Стамбул",
            cityNameEn: "Istanbul",
            countryName: "Турция",
            airports: [
                .init(code: "IST", name: "Стамбул", cityName: "Стамбул"),
                .init(code: "SAW", name: "Сабиха Гёкчен", cityName: "Стамбул")
            ]
        ),
        CityAirport(
            cityName: "Анталья",
            cityNameEn: "Antalya",
            countryName: "Турция",
            airports: [
                .init(code: "AYT", name: "Анталья", cityName: "Анталья")
            ]
        ),

        // Грузия
        CityAirport(
            cityName: "Тбилиси",
            cityNameEn: "Tbilisi",
            countryName: "Грузия",
            airports: [
                .init(code: "TBS", name: "Тбилиси", cityName: "Тбилиси")
            ]
        ),
        CityAirport(
            cityName: "Батуми",
            cityNameEn: "Batumi",
            countryName: "Грузия",
            airports: [
                .init(code: "BUS", name: "Батуми", cityName: "Батуми")
            ]
        ),

        // ОАЭ
        CityAirport(
            cityName: "Дубай",
            cityNameEn: "Dubai",
            countryName: "ОАЭ",
            airports: [
                .init(code: "DXB", name: "Дубай", cityName: "Дубай"),
                .init(code: "DWC", name: "Аль-Мактум", cityName: "Дубай")
            ]
        ),
        CityAirport(
            cityName: "Абу-Даби",
            cityNameEn: "Abu Dhabi",
            countryName: "ОАЭ",
            airports: [
                .init(code: "AUH", name: "Абу-Даби", cityName: "Абу-Даби")
            ]
        ),

        // Таиланд
        CityAirport(
            cityName: "Бангкок",
            cityNameEn: "Bangkok",
            countryName: "Таиланд",
            airports: [
                .init(code: "BKK", name: "Суварнабхуми", cityName: "Бангкок"),
                .init(code: "DMK", name: "Дон Муанг", cityName: "Бангкок")
            ]
        ),
        CityAirport(
            cityName: "Пхукет",
            cityNameEn: "Phuket",
            countryName: "Таиланд",
            airports: [
                .init(code: "HKT", name: "Пхукет", cityName: "Пхукет")
            ]
        ),

        // Индонезия
        CityAirport(
            cityName: "Бали",
            cityNameEn: "Bali",
            countryName: "Индонезия",
            airports: [
                .init(code: "DPS", name: "Нгурах-Рай", cityName: "Бали")
            ]
        ),

        // Италия
        CityAirport(
            cityName: "Рим",
            cityNameEn: "Rome",
            countryName: "Италия",
            airports: [
                .init(code: "FCO", name: "Фьюмичино", cityName: "Рим"),
                .init(code: "CIA", name: "Чампино", cityName: "Рим")
            ]
        ),
        CityAirport(
            cityName: "Милан",
            cityNameEn: "Milan",
            countryName: "Италия",
            airports: [
                .init(code: "MXP", name: "Мальпенса", cityName: "Милан"),
                .init(code: "LIN", name: "Линате", cityName: "Милан")
            ]
        ),

        // Франция
        CityAirport(
            cityName: "Париж",
            cityNameEn: "Paris",
            countryName: "Франция",
            airports: [
                .init(code: "CDG", name: "Шарль-де-Голль", cityName: "Париж"),
                .init(code: "ORY", name: "Орли", cityName: "Париж")
            ]
        ),

        // Испания
        CityAirport(
            cityName: "Барселона",
            cityNameEn: "Barcelona",
            countryName: "Испания",
            airports: [
                .init(code: "BCN", name: "Эль-Прат", cityName: "Барселона")
            ]
        ),
        CityAirport(
            cityName: "Мадрид",
            cityNameEn: "Madrid",
            countryName: "Испания",
            airports: [
                .init(code: "MAD", name: "Барахас", cityName: "Мадрид")
            ]
        ),

        // Великобритания
        CityAirport(
            cityName: "Лондон",
            cityNameEn: "London",
            countryName: "Великобритания",
            airports: [
                .init(code: "LHR", name: "Хитроу", cityName: "Лондон"),
                .init(code: "LGW", name: "Гатвик", cityName: "Лондон"),
                .init(code: "STN", name: "Станстед", cityName: "Лондон")
            ]
        ),

        // Германия
        CityAirport(
            cityName: "Берлин",
            cityNameEn: "Berlin",
            countryName: "Германия",
            airports: [
                .init(code: "BER", name: "Бранденбург", cityName: "Берлин")
            ]
        ),

        // Азербайджан
        CityAirport(
            cityName: "Баку",
            cityNameEn: "Baku",
            countryName: "Азербайджан",
            airports: [
                .init(code: "GYD", name: "Гейдар Алиев", cityName: "Баку")
            ]
        ),

        // Армения
        CityAirport(
            cityName: "Ереван",
            cityNameEn: "Yerevan",
            countryName: "Армения",
            airports: [
                .init(code: "EVN", name: "Звартноц", cityName: "Ереван")
            ]
        ),

        // Казахстан
        CityAirport(
            cityName: "Алматы",
            cityNameEn: "Almaty",
            countryName: "Казахстан",
            airports: [
                .init(code: "ALA", name: "Алматы", cityName: "Алматы")
            ]
        ),

        // США
        CityAirport(
            cityName: "Нью-Йорк",
            cityNameEn: "New York",
            countryName: "США",
            airports: [
                .init(code: "JFK", name: "Кеннеди", cityName: "Нью-Йорк"),
                .init(code: "EWR", name: "Ньюарк", cityName: "Нью-Йорк"),
                .init(code: "LGA", name: "Ла-Гуардия", cityName: "Нью-Йорк")
            ]
        ),

        // Япония
        CityAirport(
            cityName: "Токио",
            cityNameEn: "Tokyo",
            countryName: "Япония",
            airports: [
                .init(code: "NRT", name: "Нарита", cityName: "Токио"),
                .init(code: "HND", name: "Ханеда", cityName: "Токио")
            ]
        ),

        // Южная Корея
        CityAirport(
            cityName: "Сеул",
            cityNameEn: "Seoul",
            countryName: "Южная Корея",
            airports: [
                .init(code: "ICN", name: "Инчхон", cityName: "Сеул")
            ]
        ),

        // Сингапур
        CityAirport(
            cityName: "Сингапур",
            cityNameEn: "Singapore",
            countryName: "Сингапур",
            airports: [
                .init(code: "SIN", name: "Чанги", cityName: "Сингапур")
            ]
        )
    ]

    /// Поиск городов по запросу (автокомплит)
    func searchCities(query: String) -> [CityAirport] {
        guard !query.isEmpty else { return cities }

        let lowercased = query.lowercased()

        return cities.filter { city in
            city.cityName.lowercased().contains(lowercased) ||
            city.cityNameEn.lowercased().contains(lowercased) ||
            city.countryName.lowercased().contains(lowercased) ||
            city.airports.contains { $0.code.lowercased().contains(lowercased) }
        }
    }

    /// Найти город по точному названию
    func findCity(byName name: String) -> CityAirport? {
        cities.first { city in
            city.cityName.lowercased() == name.lowercased() ||
            city.cityNameEn.lowercased() == name.lowercased()
        }
    }
}
