//
//  TripSummaryCalculator.swift
//  Travell Buddy
//
//  Calculates trip and day statistics from itinerary data.
//

import Foundation

final class TripSummaryCalculator {

    // MARK: - Constants

    // Average step length in meters (global average)
    private static let averageStepLength: Double = 0.75

    // Cost estimates per category per person (in EUR, as base currency)
    private static let mealCosts: CostRange = CostRange(low: 15, high: 40)
    private static let attractionCosts: CostRange = CostRange(low: 10, high: 25)
    private static let cafeCosts: CostRange = CostRange(low: 5, high: 15)
    private static let nightlifeCosts: CostRange = CostRange(low: 20, high: 50)

    // Currency mapping by city (simplified)
    private static let cityCurrencies: [String: String] = [
        "Istanbul": "TRY",
        "Стамбул": "TRY",
        "Rome": "EUR",
        "Рим": "EUR",
        "Paris": "EUR",
        "Париж": "EUR",
        "London": "GBP",
        "Лондон": "GBP",
        "New York": "USD",
        "Нью-Йорк": "USD",
        "Tokyo": "JPY",
        "Токио": "JPY",
        "Dubai": "AED",
        "Дубай": "AED",
        "Bangkok": "THB",
        "Бангкок": "THB",
        "Moscow": "RUB",
        "Москва": "RUB",
        "Saint Petersburg": "RUB",
        "Санкт-Петербург": "RUB"
    ]

    // Exchange rates to EUR (approximate)
    private static let exchangeRates: [String: Double] = [
        "EUR": 1.0,
        "USD": 1.08,
        "GBP": 0.85,
        "TRY": 35.0,
        "JPY": 165.0,
        "AED": 4.0,
        "THB": 38.0,
        "RUB": 100.0
    ]

    // MARK: - Public Methods

    static func calculateTripSummary(from plan: TripPlan) -> TripSummary {
        let daySummaries = plan.days.map { calculateDaySummary(from: $0, city: plan.destinationCity, travelers: plan.travellersCount) }

        let totalDistance = daySummaries.reduce(0) { $0 + $1.totalDistanceMeters }
        let totalSteps = daySummaries.reduce(0) { $0 + $1.estimatedSteps }
        let totalWalkingTime = daySummaries.reduce(0) { $0 + $1.totalWalkingTimeMinutes }
        let totalActivities = daySummaries.reduce(0) { $0 + $1.activitiesCount }
        let totalMeals = daySummaries.reduce(0) { $0 + $1.mealsCount }
        let totalAttractions = daySummaries.reduce(0) { $0 + $1.attractionsCount }

        let totalCostLow = daySummaries.reduce(0.0) { $0 + $1.estimatedCostLow }
        let totalCostHigh = daySummaries.reduce(0.0) { $0 + $1.estimatedCostHigh }

        let daysCount = max(plan.days.count, 1)
        let currency = currencyForCity(plan.destinationCity)

        return TripSummary(
            tripId: plan.tripId,
            city: plan.destinationCity,
            startDate: plan.startDate,
            endDate: plan.endDate,
            daysCount: daysCount,
            travelersCount: plan.travellersCount,
            totalDistanceMeters: totalDistance,
            totalEstimatedSteps: totalSteps,
            totalWalkingTimeMinutes: totalWalkingTime,
            totalActivities: totalActivities,
            totalMeals: totalMeals,
            totalAttractions: totalAttractions,
            totalEstimatedCostLow: totalCostLow,
            totalEstimatedCostHigh: totalCostHigh,
            averageDailyCostLow: totalCostLow / Double(daysCount),
            averageDailyCostHigh: totalCostHigh / Double(daysCount),
            currency: currency,
            daySummaries: daySummaries
        )
    }

    static func calculateDaySummary(from day: TripDay, city: String, travelers: Int) -> DaySummary {
        let activities = day.activities

        // Calculate distance from travel info
        let totalDistance = activities.compactMap { $0.travelDistanceMeters }.reduce(0, +)

        // Estimate steps from distance
        let estimatedSteps = Int(Double(totalDistance) / averageStepLength)

        // Calculate walking time
        let totalWalkingTime = activities.compactMap { $0.travelTimeMinutes }.reduce(0, +)

        // Count activities by type
        let mealsCount = activities.filter { $0.category == .food }.count
        let attractionsCount = activities.filter {
            $0.category == .museum || $0.category == .viewpoint || $0.category == .walk
        }.count
        let nightlifeCount = activities.filter { $0.category == .nightlife }.count

        // Get first and last activity times
        let firstTime = activities.first?.time
        let lastTime = activities.last?.time

        // Calculate total activity time
        let totalActivityTime = activities.compactMap { $0.durationMinutes }.reduce(0, +)

        // Estimate costs
        let currency = currencyForCity(city)
        let exchangeRate = exchangeRates[currency] ?? 1.0
        let travelersMultiplier = Double(travelers)

        let mealsCostLow = Double(mealsCount) * mealCosts.low * exchangeRate * travelersMultiplier
        let mealsCostHigh = Double(mealsCount) * mealCosts.high * exchangeRate * travelersMultiplier

        let attractionsCostLow = Double(attractionsCount) * attractionCosts.low * exchangeRate * travelersMultiplier
        let attractionsCostHigh = Double(attractionsCount) * attractionCosts.high * exchangeRate * travelersMultiplier

        let nightlifeCostLow = Double(nightlifeCount) * nightlifeCosts.low * exchangeRate * travelersMultiplier
        let nightlifeCostHigh = Double(nightlifeCount) * nightlifeCosts.high * exchangeRate * travelersMultiplier

        let totalCostLow = mealsCostLow + attractionsCostLow + nightlifeCostLow
        let totalCostHigh = mealsCostHigh + attractionsCostHigh + nightlifeCostHigh

        return DaySummary(
            dayIndex: day.index,
            date: day.date,
            totalDistanceMeters: totalDistance,
            estimatedSteps: estimatedSteps,
            totalWalkingTimeMinutes: totalWalkingTime,
            activitiesCount: activities.count,
            mealsCount: mealsCount,
            attractionsCount: attractionsCount,
            firstActivityTime: firstTime,
            lastActivityTime: lastTime,
            totalActivityTimeMinutes: totalActivityTime,
            estimatedCostLow: totalCostLow,
            estimatedCostHigh: totalCostHigh,
            currency: currency,
            weather: nil // Weather will be fetched separately
        )
    }

    // MARK: - Private Helpers

    private static func currencyForCity(_ city: String) -> String {
        // Try exact match first
        if let currency = cityCurrencies[city] {
            return currency
        }

        // Try case-insensitive match
        let lowercasedCity = city.lowercased()
        for (knownCity, currency) in cityCurrencies {
            if knownCity.lowercased() == lowercasedCity {
                return currency
            }
        }

        // Default to EUR
        return "EUR"
    }
}

// MARK: - TripPlan Extension

extension TripPlan {
    var summary: TripSummary {
        TripSummaryCalculator.calculateTripSummary(from: self)
    }
}

// MARK: - TripDay Extension

extension TripDay {
    func summary(city: String, travelers: Int) -> DaySummary {
        TripSummaryCalculator.calculateDaySummary(from: self, city: city, travelers: travelers)
    }
}
