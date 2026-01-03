//
//  TripSummaryCalculator.swift
//  Travell Buddy
//
//  Calculates trip and day statistics from itinerary data.
//

import Foundation
import CoreLocation

final class TripSummaryCalculator {

    // MARK: - Constants

    // Average step length in meters (global average)
    private static let averageStepLength: Double = 0.75

    // Average walking speed in meters per minute (~5 km/h)
    private static let averageWalkingSpeedMetersPerMin: Double = 80.0

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

        // Check if at least one day has distance data
        let hasAnyDistanceData = daySummaries.contains { $0.hasDistanceData }

        let daysCount = max(plan.days.count, 1)
        let currency = currencyForCity(plan.destinationCity)

        return TripSummary(
            tripId: plan.tripId,
            city: plan.destinationCity,
            startDate: plan.startDate,
            endDate: plan.endDate,
            daysCount: daysCount,
            travelersCount: plan.travellersCount,
            tripDescription: plan.tripSummary,
            totalDistanceMeters: totalDistance,
            totalEstimatedSteps: totalSteps,
            totalWalkingTimeMinutes: totalWalkingTime,
            hasDistanceData: hasAnyDistanceData,
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

        // Calculate distance using backend data or haversine fallback
        let (totalDistance, hasDistanceData) = calculateDayDistance(activities: activities)

        // Estimate steps from distance (only if we have distance data)
        let estimatedSteps = hasDistanceData ? Int(Double(totalDistance) / averageStepLength) : 0

        // Calculate walking time using backend data or estimate from distance
        let (totalWalkingTime, _) = calculateWalkingTime(activities: activities, distanceMeters: totalDistance)

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
            title: day.title,
            summary: day.summary,
            totalDistanceMeters: totalDistance,
            estimatedSteps: estimatedSteps,
            totalWalkingTimeMinutes: totalWalkingTime,
            hasDistanceData: hasDistanceData,
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

    // MARK: - Distance Calculation

    /// Calculates total distance for a day using backend data or haversine fallback.
    /// Returns (totalDistanceMeters, hasRealData)
    private static func calculateDayDistance(activities: [TripActivity]) -> (Int, Bool) {
        // First, try to sum backend-provided distances
        let backendDistances = activities.compactMap { $0.travelDistanceMeters }
        let backendTotal = backendDistances.reduce(0, +)

        // If we have backend data, use it
        if backendTotal > 0 {
            return (backendTotal, true)
        }

        // Fallback: calculate haversine distances between consecutive POIs
        var haversineTotal: Double = 0
        var hasAnyCoordinates = false

        for i in 1..<activities.count {
            let prev = activities[i - 1]
            let curr = activities[i]

            if let prevCoord = prev.coordinate, let currCoord = curr.coordinate {
                hasAnyCoordinates = true
                haversineTotal += haversineDistance(from: prevCoord, to: currCoord)
            }
        }

        if hasAnyCoordinates {
            return (Int(haversineTotal), true)
        }

        // No data available
        return (0, false)
    }

    /// Calculates total walking time using backend data or estimate from distance.
    /// Returns (totalMinutes, hasRealData)
    private static func calculateWalkingTime(activities: [TripActivity], distanceMeters: Int) -> (Int, Bool) {
        // First, try to sum backend-provided times
        let backendTimes = activities.compactMap { $0.travelTimeMinutes }
        let backendTotal = backendTimes.reduce(0, +)

        // If we have backend data, use it
        if backendTotal > 0 {
            return (backendTotal, true)
        }

        // Fallback: estimate from distance (5 km/h average walking speed)
        if distanceMeters > 0 {
            let estimatedMinutes = Int(Double(distanceMeters) / averageWalkingSpeedMetersPerMin)
            return (estimatedMinutes, true)
        }

        // No data available
        return (0, false)
    }

    /// Calculates the haversine distance between two coordinates in meters.
    private static func haversineDistance(
        from coord1: CLLocationCoordinate2D,
        to coord2: CLLocationCoordinate2D
    ) -> Double {
        let earthRadiusMeters: Double = 6_371_000

        let lat1 = coord1.latitude * .pi / 180
        let lat2 = coord2.latitude * .pi / 180
        let deltaLat = (coord2.latitude - coord1.latitude) * .pi / 180
        let deltaLon = (coord2.longitude - coord1.longitude) * .pi / 180

        let a = sin(deltaLat / 2) * sin(deltaLat / 2) +
                cos(lat1) * cos(lat2) *
                sin(deltaLon / 2) * sin(deltaLon / 2)
        let c = 2 * atan2(sqrt(a), sqrt(1 - a))

        return earthRadiusMeters * c
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
