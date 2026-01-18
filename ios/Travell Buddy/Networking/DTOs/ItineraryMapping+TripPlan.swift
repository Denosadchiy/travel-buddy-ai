//
//  ItineraryMapping+TripPlan.swift
//  Travell Buddy
//
//  Mapping from backend DTOs to iOS domain models (TripPlan, TripDay, TripActivity).
//

import Foundation

// MARK: - Date Formatters

private let dateFormatter: DateFormatter = {
    let formatter = DateFormatter()
    formatter.dateFormat = "yyyy-MM-dd"
    formatter.locale = Locale(identifier: "en_US_POSIX")
    formatter.timeZone = TimeZone(secondsFromGMT: 0)
    return formatter
}()

private let timeFormatter: DateFormatter = {
    let formatter = DateFormatter()
    formatter.dateFormat = "HH:mm:ss"
    formatter.locale = Locale(identifier: "en_US_POSIX")
    return formatter
}()

// MARK: - ItineraryResponseDTO → TripPlan

extension ItineraryResponseDTO {
    func toTripPlan(destinationCity: String, budget: String, interests: [String], travelersCount: Int) -> TripPlan {
        let days = self.days.map { $0.toTripDay() }

        // Extract dates from days
        let startDate = days.first?.date ?? Date()
        let endDate = days.last?.date ?? Date()

        // Create interests summary
        let interestsSummary = interests.isEmpty ? "путешествие" : interests.joined(separator: ", ")

        // Parse trip ID from string to UUID
        let tripUUID = UUID(uuidString: self.tripId) ?? UUID()

        return TripPlan(
            tripId: tripUUID,
            destinationCity: destinationCity,
            startDate: startDate,
            endDate: endDate,
            days: days,
            travellersCount: travelersCount,
            comfortLevel: mapBudgetToComfortLevel(budget),
            interestsSummary: interestsSummary,
            tripSummary: tripSummary,
            isLocked: isLocked ?? false,
            cityPhotoReference: cityPhotoReference
        )
    }

    func toTripPlan(
        destinationCity: String,
        budget: String,
        interests: [String],
        travelersCount: Int,
        expectedStartDate: Date,
        expectedEndDate: Date
    ) -> TripPlan {
        let days = self.days.map { $0.toTripDay() }

        let interestsSummary = interests.isEmpty ? "путешествие" : interests.joined(separator: ", ")
        let tripUUID = UUID(uuidString: self.tripId) ?? UUID()

        // Trust server's isLocked value - server handles freemium logic based on FREEMIUM_ENABLED
        let serverIsLocked = isLocked ?? false
        let visibleDays = serverIsLocked
            ? days.filter { $0.index == 1 }
            : days

        return TripPlan(
            tripId: tripUUID,
            destinationCity: destinationCity,
            startDate: expectedStartDate,
            endDate: expectedEndDate,
            days: visibleDays,
            travellersCount: travelersCount,
            comfortLevel: mapBudgetToComfortLevel(budget),
            interestsSummary: interestsSummary,
            tripSummary: tripSummary,
            isLocked: serverIsLocked,
            cityPhotoReference: cityPhotoReference
        )
    }

    func toTripPlan(using existingPlan: TripPlan) -> TripPlan {
        let days = self.days.map { $0.toTripDay() }

        // Trust server's isLocked value - server handles freemium logic based on FREEMIUM_ENABLED
        return TripPlan(
            tripId: existingPlan.tripId,
            destinationCity: existingPlan.destinationCity,
            startDate: existingPlan.startDate,
            endDate: existingPlan.endDate,
            days: days,
            travellersCount: existingPlan.travellersCount,
            comfortLevel: existingPlan.comfortLevel,
            interestsSummary: existingPlan.interestsSummary,
            tripSummary: tripSummary ?? existingPlan.tripSummary,
            isLocked: isLocked ?? false,
            cityPhotoReference: cityPhotoReference ?? existingPlan.cityPhotoReference
        )
    }

    private func mapBudgetToComfortLevel(_ budget: String) -> String {
        switch budget.lowercased() {
        case "low":
            return "Эконом"
        case "medium":
            return "Комфорт"
        case "high":
            return "Премиум"
        default:
            return "Комфорт"
        }
    }
}

// MARK: - TripItineraryDayDTO → TripDay

extension TripItineraryDayDTO {
    func toTripDay() -> TripDay {
        // Parse date
        let date = dateFormatter.date(from: self.date) ?? Date()

        // Convert blocks to activities (filter out blocks without POI or rest blocks)
        let activities = blocks.compactMap { $0.toTripActivity() }

        return TripDay(
            index: dayNumber,
            date: date,
            title: theme,
            summary: summary,
            activities: activities
        )
    }
}

// MARK: - ItineraryBlockDTO → TripActivity

extension ItineraryBlockDTO {
    func toTripActivity() -> TripActivity? {
        // Skip blocks without POI (like rest blocks)
        guard let poi = poi else {
            return nil
        }

        // Format time (strip seconds if present)
        let time = formatTime(startTime)
        let formattedEndTime = formatTime(endTime)

        // Map category from block type
        let category = mapBlockTypeToCategory(blockType)

        return TripActivity(
            id: UUID(), // Generate new UUID since backend uses string IDs
            time: time,
            endTime: formattedEndTime,
            title: poi.name,
            description: poi.location ?? "",
            category: category,
            address: poi.location,
            note: notes,
            latitude: poi.lat,
            longitude: poi.lon,
            travelPolyline: travelPolyline,
            rating: poi.rating,
            tags: poi.tags,
            poiId: poi.poiId,
            travelTimeMinutes: travelTimeFromPrev,
            travelDistanceMeters: travelDistanceMeters
        )
    }

    private func formatTime(_ time: String) -> String {
        // Convert "HH:MM:SS" to "HH:MM"
        let components = time.split(separator: ":")
        if components.count >= 2 {
            return "\(components[0]):\(components[1])"
        }
        return time
    }

    private func mapBlockTypeToCategory(_ blockType: String) -> TripActivityCategory {
        // PRIORITY 1: Check POI category FIRST (more specific than block type)
        if let poi = poi, let poiCategory = poi.category?.lowercased() {
            // Museum & Art
            if poiCategory.contains("museum") || poiCategory.contains("art") || poiCategory.contains("gallery") {
                return .museum
            }
            // Viewpoints & Nature
            if poiCategory.contains("viewpoint") || poiCategory.contains("view") || poiCategory.contains("park") || poiCategory.contains("garden") {
                return .viewpoint
            }
            // Nightlife
            if poiCategory.contains("bar") || poiCategory.contains("club") || poiCategory.contains("nightlife") {
                return .nightlife
            }
            // Food establishments
            if poiCategory.contains("restaurant") || poiCategory.contains("cafe") || poiCategory.contains("food") {
                return .food
            }
        }

        // PRIORITY 2: Fall back to block type if POI category doesn't match
        switch blockType.lowercased() {
        case "meal":
            return .food
        case "nightlife":
            return .nightlife
        case "activity":
            return .walk  // Generic activity
        case "rest":
            return .other
        default:
            return .other
        }
    }
}
