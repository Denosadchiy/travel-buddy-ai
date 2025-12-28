//
//  WeatherService.swift
//  Travell Buddy
//
//  Fetches weather forecast for trip days using Open-Meteo API (free, no API key required).
//

import Foundation
import CoreLocation

// MARK: - Protocol

protocol WeatherServiceProtocol {
    func fetchWeather(for coordinate: CLLocationCoordinate2D, dates: [Date]) async throws -> [DayWeather]
}

// MARK: - Implementation

final class WeatherService: WeatherServiceProtocol {

    // MARK: - Singleton

    static let shared = WeatherService()

    // MARK: - Dependencies

    private let session: URLSession

    // MARK: - Cache

    private var cache: [String: [DayWeather]] = [:]
    private let cacheLock = NSLock()
    private static let cacheTTL: TimeInterval = 60 * 60 // 1 hour

    // MARK: - Init

    init(session: URLSession = .shared) {
        self.session = session
    }

    // MARK: - Public Methods

    func fetchWeather(for coordinate: CLLocationCoordinate2D, dates: [Date]) async throws -> [DayWeather] {
        guard !dates.isEmpty else { return [] }

        let cacheKey = "\(coordinate.latitude),\(coordinate.longitude)"

        // Check cache
        if let cached = getCached(for: cacheKey, dates: dates) {
            return cached
        }

        // Sort dates and get range
        let sortedDates = dates.sorted()
        guard let startDate = sortedDates.first, let endDate = sortedDates.last else { return [] }

        let forecast = try await fetchFromAPI(
            latitude: coordinate.latitude,
            longitude: coordinate.longitude,
            startDate: startDate,
            endDate: endDate
        )

        // Cache the result
        cacheWeather(forecast, for: cacheKey)

        // Filter to only requested dates
        let calendar = Calendar.current
        return forecast.filter { weather in
            dates.contains { date in
                calendar.isDate(date, inSameDayAs: weather.date)
            }
        }
    }

    // MARK: - Private Methods

    private func getCached(for key: String, dates: [Date]) -> [DayWeather]? {
        cacheLock.lock()
        defer { cacheLock.unlock() }
        return cache[key]
    }

    private func cacheWeather(_ weather: [DayWeather], for key: String) {
        cacheLock.lock()
        defer { cacheLock.unlock() }
        cache[key] = weather
    }

    private func fetchFromAPI(latitude: Double, longitude: Double, startDate: Date, endDate: Date) async throws -> [DayWeather] {
        let dateFormatter = DateFormatter()
        dateFormatter.dateFormat = "yyyy-MM-dd"

        let startStr = dateFormatter.string(from: startDate)
        let endStr = dateFormatter.string(from: endDate)

        // Open-Meteo API (free, no key required)
        var components = URLComponents(string: "https://api.open-meteo.com/v1/forecast")!
        components.queryItems = [
            URLQueryItem(name: "latitude", value: "\(latitude)"),
            URLQueryItem(name: "longitude", value: "\(longitude)"),
            URLQueryItem(name: "daily", value: "temperature_2m_max,temperature_2m_min,precipitation_probability_max,weathercode,relative_humidity_2m_max,windspeed_10m_max,uv_index_max"),
            URLQueryItem(name: "timezone", value: "auto"),
            URLQueryItem(name: "start_date", value: startStr),
            URLQueryItem(name: "end_date", value: endStr)
        ]

        guard let url = components.url else {
            throw WeatherError.invalidURL
        }

        var request = URLRequest(url: url)
        request.httpMethod = "GET"
        request.timeoutInterval = 10

        do {
            let (data, response) = try await session.data(for: request)

            guard let httpResponse = response as? HTTPURLResponse else {
                throw WeatherError.invalidResponse
            }

            guard httpResponse.statusCode == 200 else {
                throw WeatherError.serverError(statusCode: httpResponse.statusCode)
            }

            let decoder = JSONDecoder()
            let dto = try decoder.decode(OpenMeteoResponse.self, from: data)
            return dto.toDayWeather(dateFormatter: dateFormatter)

        } catch let error as WeatherError {
            throw error
        } catch is DecodingError {
            throw WeatherError.decodingError
        } catch {
            throw WeatherError.networkError(error)
        }
    }
}

// MARK: - Errors

enum WeatherError: LocalizedError {
    case invalidURL
    case invalidResponse
    case serverError(statusCode: Int)
    case networkError(Error)
    case decodingError
    case noData

    var errorDescription: String? {
        switch self {
        case .invalidURL:
            return "Некорректный URL"
        case .invalidResponse:
            return "Некорректный ответ сервера"
        case .serverError(let code):
            return "Ошибка сервера (\(code))"
        case .networkError:
            return "Ошибка сети. Проверьте подключение."
        case .decodingError:
            return "Ошибка обработки данных"
        case .noData:
            return "Нет данных о погоде"
        }
    }
}

// MARK: - API Response DTOs

private struct OpenMeteoResponse: Decodable {
    let daily: DailyData?

    struct DailyData: Decodable {
        let time: [String]
        let temperature_2m_max: [Double?]
        let temperature_2m_min: [Double?]
        let precipitation_probability_max: [Int?]
        let weathercode: [Int?]
        let relative_humidity_2m_max: [Int?]
        let windspeed_10m_max: [Double?]
        let uv_index_max: [Double?]
    }

    func toDayWeather(dateFormatter: DateFormatter) -> [DayWeather] {
        guard let daily = daily else { return [] }

        var result: [DayWeather] = []

        for (index, dateStr) in daily.time.enumerated() {
            guard let date = dateFormatter.date(from: dateStr) else { continue }

            let tempHigh = daily.temperature_2m_max[safe: index] ?? 20.0
            let tempLow = daily.temperature_2m_min[safe: index] ?? 15.0
            let precipProb = daily.precipitation_probability_max[safe: index] ?? 0
            let weatherCode = daily.weathercode[safe: index] ?? 0
            let humidity = daily.relative_humidity_2m_max[safe: index] ?? 50
            let windSpeed = daily.windspeed_10m_max[safe: index] ?? 10.0
            let uvIndex = Int(daily.uv_index_max[safe: index] ?? 5.0)

            let weather = DayWeather(
                date: date,
                temperatureHigh: tempHigh,
                temperatureLow: tempLow,
                condition: WeatherCondition.from(weatherCode: weatherCode),
                precipitationProbability: precipProb,
                humidity: humidity,
                windSpeed: windSpeed,
                uvIndex: uvIndex
            )

            result.append(weather)
        }

        return result
    }
}

// MARK: - Weather Code Mapping

private extension WeatherCondition {
    static func from(weatherCode: Int) -> WeatherCondition {
        // WMO Weather interpretation codes
        // https://open-meteo.com/en/docs
        switch weatherCode {
        case 0:
            return .sunny
        case 1, 2:
            return .partlyCloudy
        case 3:
            return .cloudy
        case 45, 48:
            return .fog
        case 51, 53, 55, 56, 57, 61, 63:
            return .rain
        case 65, 66, 67:
            return .heavyRain
        case 71, 73, 75, 77, 85, 86:
            return .snow
        case 80, 81, 82:
            return .rain
        case 95, 96, 99:
            return .thunderstorm
        default:
            return .partlyCloudy
        }
    }
}

// MARK: - Array Extension

private extension Array {
    subscript(safe index: Index) -> Element? {
        indices.contains(index) ? self[index] : nil
    }
}

// MARK: - Optional Double Unwrap Extension

private extension Optional where Wrapped == Double {
    static func ?? (optional: Double??, defaultValue: Double) -> Double {
        if let outer = optional, let inner = outer {
            return inner
        }
        return defaultValue
    }
}

private extension Optional where Wrapped == Int {
    static func ?? (optional: Int??, defaultValue: Int) -> Int {
        if let outer = optional, let inner = outer {
            return inner
        }
        return defaultValue
    }
}
