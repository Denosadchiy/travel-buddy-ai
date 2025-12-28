//
//  TripSummary.swift
//  Travell Buddy
//
//  Models for trip and day summary statistics.
//

import Foundation

// MARK: - Day Summary

struct DaySummary: Identifiable {
    let dayIndex: Int
    let date: Date

    // Walking stats
    let totalDistanceMeters: Int
    let estimatedSteps: Int
    let totalWalkingTimeMinutes: Int

    // Activity stats
    let activitiesCount: Int
    let mealsCount: Int
    let attractionsCount: Int

    // Time stats
    let firstActivityTime: String?
    let lastActivityTime: String?
    let totalActivityTimeMinutes: Int

    // Cost estimate
    let estimatedCostLow: Double
    let estimatedCostHigh: Double
    let currency: String

    // Weather (optional, fetched separately)
    var weather: DayWeather?

    var id: Int { dayIndex }

    // Computed properties
    var totalDistanceKm: Double {
        Double(totalDistanceMeters) / 1000.0
    }

    var formattedDistance: String {
        if totalDistanceMeters >= 1000 {
            return String(format: "%.1f км", totalDistanceKm)
        }
        return "\(totalDistanceMeters) м"
    }

    var formattedSteps: String {
        let formatter = NumberFormatter()
        formatter.numberStyle = .decimal
        formatter.groupingSeparator = " "
        return formatter.string(from: NSNumber(value: estimatedSteps)) ?? "\(estimatedSteps)"
    }

    var formattedWalkingTime: String {
        if totalWalkingTimeMinutes >= 60 {
            let hours = totalWalkingTimeMinutes / 60
            let minutes = totalWalkingTimeMinutes % 60
            if minutes == 0 {
                return "\(hours) ч"
            }
            return "\(hours) ч \(minutes) мин"
        }
        return "\(totalWalkingTimeMinutes) мин"
    }

    var formattedCostRange: String {
        let formatter = NumberFormatter()
        formatter.numberStyle = .currency
        formatter.currencyCode = currency
        formatter.maximumFractionDigits = 0

        let low = formatter.string(from: NSNumber(value: estimatedCostLow)) ?? "\(Int(estimatedCostLow))"
        let high = formatter.string(from: NSNumber(value: estimatedCostHigh)) ?? "\(Int(estimatedCostHigh))"

        return "\(low) – \(high)"
    }

    var activityIntensity: ActivityIntensity {
        if totalDistanceMeters > 10000 || estimatedSteps > 15000 {
            return .high
        } else if totalDistanceMeters > 5000 || estimatedSteps > 8000 {
            return .moderate
        }
        return .light
    }
}

// MARK: - Trip Summary (Overall)

struct TripSummary {
    let tripId: UUID
    let city: String
    let startDate: Date
    let endDate: Date
    let daysCount: Int
    let travelersCount: Int

    // Aggregated walking stats
    let totalDistanceMeters: Int
    let totalEstimatedSteps: Int
    let totalWalkingTimeMinutes: Int

    // Aggregated activity stats
    let totalActivities: Int
    let totalMeals: Int
    let totalAttractions: Int

    // Cost estimates
    let totalEstimatedCostLow: Double
    let totalEstimatedCostHigh: Double
    let averageDailyCostLow: Double
    let averageDailyCostHigh: Double
    let currency: String

    // Day summaries
    let daySummaries: [DaySummary]

    // Computed properties
    var totalDistanceKm: Double {
        Double(totalDistanceMeters) / 1000.0
    }

    var formattedTotalDistance: String {
        String(format: "%.1f км", totalDistanceKm)
    }

    var formattedTotalSteps: String {
        let formatter = NumberFormatter()
        formatter.numberStyle = .decimal
        formatter.groupingSeparator = " "
        return formatter.string(from: NSNumber(value: totalEstimatedSteps)) ?? "\(totalEstimatedSteps)"
    }

    var formattedTotalCostRange: String {
        let formatter = NumberFormatter()
        formatter.numberStyle = .currency
        formatter.currencyCode = currency
        formatter.maximumFractionDigits = 0

        let low = formatter.string(from: NSNumber(value: totalEstimatedCostLow)) ?? "\(Int(totalEstimatedCostLow))"
        let high = formatter.string(from: NSNumber(value: totalEstimatedCostHigh)) ?? "\(Int(totalEstimatedCostHigh))"

        return "\(low) – \(high)"
    }

    var averageStepsPerDay: Int {
        guard daysCount > 0 else { return 0 }
        return totalEstimatedSteps / daysCount
    }

    var overallIntensity: ActivityIntensity {
        let avgDistance = totalDistanceMeters / max(daysCount, 1)
        if avgDistance > 10000 {
            return .high
        } else if avgDistance > 5000 {
            return .moderate
        }
        return .light
    }
}

// MARK: - Weather

struct DayWeather {
    let date: Date
    let temperatureHigh: Double
    let temperatureLow: Double
    let condition: WeatherCondition
    let precipitationProbability: Int // 0-100
    let humidity: Int // 0-100
    let windSpeed: Double // km/h
    let uvIndex: Int

    var formattedTemperature: String {
        "\(Int(temperatureLow))° – \(Int(temperatureHigh))°"
    }

    var clothingRecommendation: String {
        if temperatureHigh < 5 {
            return "Тёплая куртка, шапка, перчатки"
        } else if temperatureHigh < 15 {
            return "Куртка или пальто, лёгкий шарф"
        } else if temperatureHigh < 22 {
            return "Лёгкая куртка или кофта"
        } else if temperatureHigh < 28 {
            return "Лёгкая одежда, солнцезащитные очки"
        } else {
            return "Очень лёгкая одежда, головной убор, вода"
        }
    }
}

enum WeatherCondition: String, CaseIterable {
    case sunny
    case partlyCloudy
    case cloudy
    case rain
    case heavyRain
    case thunderstorm
    case snow
    case fog

    var icon: String {
        switch self {
        case .sunny: return "sun.max.fill"
        case .partlyCloudy: return "cloud.sun.fill"
        case .cloudy: return "cloud.fill"
        case .rain: return "cloud.rain.fill"
        case .heavyRain: return "cloud.heavyrain.fill"
        case .thunderstorm: return "cloud.bolt.rain.fill"
        case .snow: return "cloud.snow.fill"
        case .fog: return "cloud.fog.fill"
        }
    }

    var displayName: String {
        switch self {
        case .sunny: return "Солнечно"
        case .partlyCloudy: return "Переменная облачность"
        case .cloudy: return "Облачно"
        case .rain: return "Дождь"
        case .heavyRain: return "Сильный дождь"
        case .thunderstorm: return "Гроза"
        case .snow: return "Снег"
        case .fog: return "Туман"
        }
    }

    var recommendation: String {
        switch self {
        case .sunny: return "Отличная погода для прогулок!"
        case .partlyCloudy: return "Хорошая погода, возможно понадобятся очки"
        case .cloudy: return "Прохладно, возьмите кофту"
        case .rain: return "Возьмите зонт или дождевик"
        case .heavyRain: return "Лучше планировать indoor активности"
        case .thunderstorm: return "Оставайтесь в помещении, следите за прогнозом"
        case .snow: return "Тёплая одежда и нескользящая обувь"
        case .fog: return "Ограниченная видимость, будьте осторожны"
        }
    }
}

// MARK: - Activity Intensity

enum ActivityIntensity: String, CaseIterable {
    case light
    case moderate
    case high

    var displayName: String {
        switch self {
        case .light: return "Лёгкий"
        case .moderate: return "Умеренный"
        case .high: return "Активный"
        }
    }

    var icon: String {
        switch self {
        case .light: return "figure.walk"
        case .moderate: return "figure.walk.motion"
        case .high: return "figure.run"
        }
    }

    var color: String {
        switch self {
        case .light: return "green"
        case .moderate: return "orange"
        case .high: return "red"
        }
    }

    var description: String {
        switch self {
        case .light: return "Спокойный темп, много отдыха"
        case .moderate: return "Сбалансированный день"
        case .high: return "Много ходьбы, активный день"
        }
    }
}

// MARK: - Cost Categories

struct CostBreakdown {
    let meals: CostRange
    let attractions: CostRange
    let transport: CostRange
    let shopping: CostRange

    var total: CostRange {
        CostRange(
            low: meals.low + attractions.low + transport.low + shopping.low,
            high: meals.high + attractions.high + transport.high + shopping.high
        )
    }
}

struct CostRange {
    let low: Double
    let high: Double

    var average: Double {
        (low + high) / 2
    }
}
