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
        ),

        // Дополнительные популярные города
        CityAirport(
            cityName: "Амстердам",
            cityNameEn: "Amsterdam",
            countryName: "Нидерланды",
            airports: [.init(code: "AMS", name: "Схипхол", cityName: "Амстердам")]
        ),
        CityAirport(
            cityName: "Прага",
            cityNameEn: "Prague",
            countryName: "Чехия",
            airports: [.init(code: "PRG", name: "Вацлав Гавел", cityName: "Прага")]
        ),
        CityAirport(
            cityName: "Вена",
            cityNameEn: "Vienna",
            countryName: "Австрия",
            airports: [.init(code: "VIE", name: "Швехат", cityName: "Вена")]
        ),
        CityAirport(
            cityName: "Будапешт",
            cityNameEn: "Budapest",
            countryName: "Венгрия",
            airports: [.init(code: "BUD", name: "Ференц Лист", cityName: "Будапешт")]
        ),
        CityAirport(
            cityName: "Лиссабон",
            cityNameEn: "Lisbon",
            countryName: "Португалия",
            airports: [.init(code: "LIS", name: "Портела", cityName: "Лиссабон")]
        ),
        CityAirport(
            cityName: "Афины",
            cityNameEn: "Athens",
            countryName: "Греция",
            airports: [.init(code: "ATH", name: "Элефтериос Венизелос", cityName: "Афины")]
        ),
        CityAirport(
            cityName: "Каир",
            cityNameEn: "Cairo",
            countryName: "Египет",
            airports: [.init(code: "CAI", name: "Каир", cityName: "Каир")]
        ),
        CityAirport(
            cityName: "Марракеш",
            cityNameEn: "Marrakech",
            countryName: "Марокко",
            airports: [.init(code: "RAK", name: "Менара", cityName: "Марракеш")]
        ),
        CityAirport(
            cityName: "Шанхай",
            cityNameEn: "Shanghai",
            countryName: "Китай",
            airports: [
                .init(code: "PVG", name: "Пудун", cityName: "Шанхай"),
                .init(code: "SHA", name: "Хунцяо", cityName: "Шанхай")
            ]
        ),
        CityAirport(
            cityName: "Пекин",
            cityNameEn: "Beijing",
            countryName: "Китай",
            airports: [
                .init(code: "PEK", name: "Столичный", cityName: "Пекин"),
                .init(code: "PKX", name: "Дасин", cityName: "Пекин")
            ]
        ),
        CityAirport(
            cityName: "Гонконг",
            cityNameEn: "Hong Kong",
            countryName: "Гонконг",
            airports: [.init(code: "HKG", name: "Чхеклапкок", cityName: "Гонконг")]
        ),
        CityAirport(
            cityName: "Мельбурн",
            cityNameEn: "Melbourne",
            countryName: "Австралия",
            airports: [.init(code: "MEL", name: "Мельбурн", cityName: "Мельбурн")]
        ),
        CityAirport(
            cityName: "Сидней",
            cityNameEn: "Sydney",
            countryName: "Австралия",
            airports: [.init(code: "SYD", name: "Кингсфорд Смит", cityName: "Сидней")]
        ),
        CityAirport(
            cityName: "Лос-Анджелес",
            cityNameEn: "Los Angeles",
            countryName: "США",
            airports: [.init(code: "LAX", name: "Лос-Анджелес", cityName: "Лос-Анджелес")]
        ),
        CityAirport(
            cityName: "Майами",
            cityNameEn: "Miami",
            countryName: "США",
            airports: [.init(code: "MIA", name: "Майами", cityName: "Майами")]
        ),
        CityAirport(
            cityName: "Мальдивы",
            cityNameEn: "Maldives",
            countryName: "Мальдивы",
            airports: [.init(code: "MLE", name: "Велана", cityName: "Мале")]
        ),
        CityAirport(
            cityName: "Канкун",
            cityNameEn: "Cancun",
            countryName: "Мексика",
            airports: [.init(code: "CUN", name: "Канкун", cityName: "Канкун")]
        ),
        CityAirport(
            cityName: "Венеция",
            cityNameEn: "Venice",
            countryName: "Италия",
            airports: [.init(code: "VCE", name: "Марко Поло", cityName: "Венеция")]
        ),
        CityAirport(
            cityName: "Флоренция",
            cityNameEn: "Florence",
            countryName: "Италия",
            airports: [.init(code: "FLR", name: "Перетола", cityName: "Флоренция")]
        ),
        CityAirport(
            cityName: "Ницца",
            cityNameEn: "Nice",
            countryName: "Франция",
            airports: [.init(code: "NCE", name: "Лазурный Берег", cityName: "Ницца")]
        ),
        CityAirport(
            cityName: "Мюнхен",
            cityNameEn: "Munich",
            countryName: "Германия",
            airports: [.init(code: "MUC", name: "Мюнхен", cityName: "Мюнхен")]
        ),
        CityAirport(
            cityName: "Цюрих",
            cityNameEn: "Zurich",
            countryName: "Швейцария",
            airports: [.init(code: "ZRH", name: "Цюрих", cityName: "Цюрих")]
        ),
        CityAirport(
            cityName: "Копенгаген",
            cityNameEn: "Copenhagen",
            countryName: "Дания",
            airports: [.init(code: "CPH", name: "Каструп", cityName: "Копенгаген")]
        ),
        CityAirport(
            cityName: "Стокгольм",
            cityNameEn: "Stockholm",
            countryName: "Швеция",
            airports: [.init(code: "ARN", name: "Арланда", cityName: "Стокгольм")]
        ),
        CityAirport(
            cityName: "Осло",
            cityNameEn: "Oslo",
            countryName: "Норвегия",
            airports: [.init(code: "OSL", name: "Гардермуэн", cityName: "Осло")]
        ),
        CityAirport(
            cityName: "Хельсинки",
            cityNameEn: "Helsinki",
            countryName: "Финляндия",
            airports: [.init(code: "HEL", name: "Вантаа", cityName: "Хельсинки")]
        ),
        CityAirport(
            cityName: "Варшава",
            cityNameEn: "Warsaw",
            countryName: "Польша",
            airports: [.init(code: "WAW", name: "Шопен", cityName: "Варшава")]
        ),
        CityAirport(
            cityName: "Краков",
            cityNameEn: "Krakow",
            countryName: "Польша",
            airports: [.init(code: "KRK", name: "Балице", cityName: "Краков")]
        ),
        CityAirport(
            cityName: "Дублин",
            cityNameEn: "Dublin",
            countryName: "Ирландия",
            airports: [.init(code: "DUB", name: "Дублин", cityName: "Дублин")]
        ),
        CityAirport(
            cityName: "Эдинбург",
            cityNameEn: "Edinburgh",
            countryName: "Великобритания",
            airports: [.init(code: "EDI", name: "Эдинбург", cityName: "Эдинбург")]
        ),
        CityAirport(
            cityName: "Брюссель",
            cityNameEn: "Brussels",
            countryName: "Бельгия",
            airports: [.init(code: "BRU", name: "Завентем", cityName: "Брюссель")]
        ),
        CityAirport(
            cityName: "Калининград",
            cityNameEn: "Kaliningrad",
            countryName: "Россия",
            airports: [.init(code: "KGD", name: "Храброво", cityName: "Калининград")]
        ),
        CityAirport(
            cityName: "Казань",
            cityNameEn: "Kazan",
            countryName: "Россия",
            airports: [.init(code: "KZN", name: "Казань", cityName: "Казань")]
        ),
        CityAirport(
            cityName: "Екатеринбург",
            cityNameEn: "Yekaterinburg",
            countryName: "Россия",
            airports: [.init(code: "SVX", name: "Кольцово", cityName: "Екатеринбург")]
        ),
        CityAirport(
            cityName: "Новосибирск",
            cityNameEn: "Novosibirsk",
            countryName: "Россия",
            airports: [.init(code: "OVB", name: "Толмачёво", cityName: "Новосибирск")]
        ),
        CityAirport(
            cityName: "Владивосток",
            cityNameEn: "Vladivostok",
            countryName: "Россия",
            airports: [.init(code: "VVO", name: "Кневичи", cityName: "Владивосток")]
        ),
        CityAirport(
            cityName: "Минск",
            cityNameEn: "Minsk",
            countryName: "Беларусь",
            airports: [.init(code: "MSQ", name: "Минск", cityName: "Минск")]
        ),
        CityAirport(
            cityName: "Ташкент",
            cityNameEn: "Tashkent",
            countryName: "Узбекистан",
            airports: [.init(code: "TAS", name: "Ташкент", cityName: "Ташкент")]
        ),
        CityAirport(
            cityName: "Самарканд",
            cityNameEn: "Samarkand",
            countryName: "Узбекистан",
            airports: [.init(code: "SKD", name: "Самарканд", cityName: "Самарканд")]
        ),
        CityAirport(
            cityName: "Бухара",
            cityNameEn: "Bukhara",
            countryName: "Узбекистан",
            airports: [.init(code: "BHK", name: "Бухара", cityName: "Бухара")]
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
