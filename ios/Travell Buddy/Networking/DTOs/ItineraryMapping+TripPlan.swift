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
            interestsSummary: interestsSummary
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

// MARK: - ItineraryDayDTO → TripDay

extension ItineraryDayDTO {
    func toTripDay() -> TripDay {
        // Parse date
        let date = dateFormatter.date(from: self.date) ?? Date()

        // Convert blocks to activities (filter out blocks without POI or rest blocks)
        let activities = blocks.compactMap { $0.toTripActivity() }

        return TripDay(
            index: dayNumber,
            date: date,
            title: theme,
            summary: theme,
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
        switch blockType.lowercased() {
        case "meal":
            return .food
        case "activity":
            // Check if it's a museum or viewpoint based on POI category
            if let poi = poi, let category = poi.category?.lowercased() {
                if category.contains("museum") || category.contains("art") {
                    return .museum
                }
                if category.contains("viewpoint") || category.contains("view") {
                    return .viewpoint
                }
            }
            return .walk
        case "nightlife":
            return .nightlife
        case "rest":
            return .other
        default:
            return .other
        }
    }
}
