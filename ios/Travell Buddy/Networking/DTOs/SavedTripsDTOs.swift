//
//  SavedTripsDTOs.swift
//  Travell Buddy
//
//  DTOs for saved trips (bookmarks) endpoints.
//

import Foundation

// MARK: - Request DTOs

struct SaveTripRequestDTO: Codable {
    let tripId: String
    let cityName: String
    let startDate: String  // YYYY-MM-DD
    let endDate: String    // YYYY-MM-DD
    let heroImageUrl: String?
    let routeSnapshot: [String: AnyCodable]?

    enum CodingKeys: String, CodingKey {
        case tripId = "trip_id"
        case cityName = "city_name"
        case startDate = "start_date"
        case endDate = "end_date"
        case heroImageUrl = "hero_image_url"
        case routeSnapshot = "route_snapshot"
    }
}

// MARK: - Response DTOs

struct SavedTripResponseDTO: Codable {
    let id: String
    let tripId: String
    let cityName: String
    let startDate: String  // YYYY-MM-DD
    let endDate: String    // YYYY-MM-DD
    let heroImageUrl: String?
    let alreadySaved: Bool

    enum CodingKeys: String, CodingKey {
        case id
        case tripId = "trip_id"
        case cityName = "city_name"
        case startDate = "start_date"
        case endDate = "end_date"
        case heroImageUrl = "hero_image_url"
        case alreadySaved = "already_saved"
    }
}

struct SavedTripsListResponseDTO: Codable {
    let trips: [SavedTripResponseDTO]
    let total: Int
}

// MARK: - Detail Response

struct SavedTripDetailResponseDTO: Codable {
    let id: String
    let tripId: String
    let cityName: String
    let startDate: String
    let endDate: String
    let heroImageUrl: String?
    let numTravelers: Int
    let itinerary: [SavedItineraryDayDTO]?
    let savedAt: String

    enum CodingKeys: String, CodingKey {
        case id
        case tripId = "trip_id"
        case cityName = "city_name"
        case startDate = "start_date"
        case endDate = "end_date"
        case heroImageUrl = "hero_image_url"
        case numTravelers = "num_travelers"
        case itinerary
        case savedAt = "saved_at"
    }
}

struct SavedItineraryDayDTO: Codable {
    let dayNumber: Int
    let date: String
    let theme: String?
    let blocks: [SavedItineraryBlockDTO]

    enum CodingKeys: String, CodingKey {
        case dayNumber = "day_number"
        case date
        case theme
        case blocks
    }
}

struct SavedItineraryBlockDTO: Codable {
    let blockType: String
    let startTime: String
    let endTime: String
    let poi: SavedPOIDTO?
    let travelTimeFromPrev: Int?
    let travelDistanceMeters: Int?
    let travelPolyline: String?
    let notes: String?

    enum CodingKeys: String, CodingKey {
        case blockType = "block_type"
        case startTime = "start_time"
        case endTime = "end_time"
        case poi
        case travelTimeFromPrev = "travel_time_from_prev"
        case travelDistanceMeters = "travel_distance_meters"
        case travelPolyline = "travel_polyline"
        case notes
    }
}

struct SavedPOIDTO: Codable {
    let poiId: String?  // Backend uses "poi_id" as UUID string
    let id: String?     // Keep for backward compatibility
    let name: String
    let category: String?
    let tags: [String]?
    let address: String?
    let location: String?
    let rating: Double?
    let priceLevel: Int?
    let photoUrl: String?
    let categories: [String]?  // Legacy field, mapped to tags
    let lat: Double?
    let lon: Double?

    enum CodingKeys: String, CodingKey {
        case poiId = "poi_id"
        case id
        case name
        case category
        case tags
        case address
        case location
        case rating
        case priceLevel = "price_level"
        case photoUrl = "photo_url"
        case categories
        case lat
        case lon
    }
}

// MARK: - Domain Models

struct SavedTripCard: Identifiable, Equatable {
    let id: UUID
    let tripId: UUID
    let cityName: String
    let startDate: Date
    let endDate: Date
    let heroImageUrl: String?
    let alreadySaved: Bool

    /// Date range formatted as "12-18 Ноя"
    var dateRangeFormatted: String {
        let formatter = DateFormatter()
        formatter.locale = Locale(identifier: "ru_RU")

        let startDay = Calendar.current.component(.day, from: startDate)
        let endDay = Calendar.current.component(.day, from: endDate)

        formatter.dateFormat = "MMM"
        let month = formatter.string(from: startDate).capitalized

        return "\(startDay)-\(endDay) \(month)"
    }

    /// Convert from DTO
    static func fromDTO(_ dto: SavedTripResponseDTO) -> SavedTripCard? {
        guard let id = UUID(uuidString: dto.id),
              let tripId = UUID(uuidString: dto.tripId) else {
            return nil
        }

        let dateFormatter = DateFormatter()
        dateFormatter.dateFormat = "yyyy-MM-dd"

        guard let startDate = dateFormatter.date(from: dto.startDate),
              let endDate = dateFormatter.date(from: dto.endDate) else {
            return nil
        }

        return SavedTripCard(
            id: id,
            tripId: tripId,
            cityName: dto.cityName,
            startDate: startDate,
            endDate: endDate,
            heroImageUrl: dto.heroImageUrl,
            alreadySaved: dto.alreadySaved
        )
    }
}

// MARK: - Mapping to TripPlan Domain Models

extension SavedTripDetailResponseDTO {
    /// Convert SavedTripDetailResponseDTO to TripPlan
    func toTripPlan() -> TripPlan? {
        guard let tripId = UUID(uuidString: self.tripId) else {
            return nil
        }

        let dateFormatter = DateFormatter()
        dateFormatter.dateFormat = "yyyy-MM-dd"

        guard let startDate = dateFormatter.date(from: self.startDate),
              let endDate = dateFormatter.date(from: self.endDate) else {
            return nil
        }

        // Convert itinerary days to TripDay array
        let days = itinerary?.map { $0.toTripDay() } ?? []

        return TripPlan(
            tripId: tripId,
            destinationCity: cityName,
            startDate: startDate,
            endDate: endDate,
            days: days,
            travellersCount: numTravelers,
            comfortLevel: "Комфорт", // Default comfort level for saved trips
            interestsSummary: "путешествие",
            tripSummary: nil,
            isLocked: false, // Saved trips are always unlocked for authenticated users
            cityPhotoReference: nil // Could be extracted from heroImageUrl if needed
        )
    }
}

extension SavedItineraryDayDTO {
    /// Convert SavedItineraryDayDTO to TripDay
    func toTripDay() -> TripDay {
        let dateFormatter = DateFormatter()
        dateFormatter.dateFormat = "yyyy-MM-dd"
        let date = dateFormatter.date(from: self.date) ?? Date()

        // Convert blocks to activities (filter out blocks without POI)
        let activities = blocks.compactMap { $0.toTripActivity() }

        return TripDay(
            index: dayNumber,
            date: date,
            title: theme,
            summary: nil,
            activities: activities
        )
    }
}

extension SavedItineraryBlockDTO {
    /// Convert SavedItineraryBlockDTO to TripActivity
    func toTripActivity() -> TripActivity? {
        // Skip blocks without POI
        guard let poi = poi else {
            return nil
        }

        // Format time (strip seconds if present)
        let time = formatTime(startTime)
        let formattedEndTime = formatTime(endTime)

        // Map category from block type
        let category = mapBlockTypeToCategory(blockType, poi: poi)

        // Combine tags and categories (prefer tags, fallback to categories for backward compatibility)
        let allTags = poi.tags ?? poi.categories

        return TripActivity(
            id: UUID(), // Generate new UUID
            time: time,
            endTime: formattedEndTime,
            title: poi.name,
            description: poi.address ?? poi.location ?? "",
            category: category,
            address: poi.address ?? poi.location,
            note: notes,
            latitude: poi.lat,
            longitude: poi.lon,
            travelPolyline: travelPolyline,
            rating: poi.rating,
            tags: allTags,
            poiId: poi.poiId ?? poi.id,  // Prefer poi_id, fallback to id
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

    private func mapBlockTypeToCategory(_ blockType: String, poi: SavedPOIDTO) -> TripActivityCategory {
        // Check POI category field first (most specific)
        if let category = poi.category?.lowercased() {
            if category.contains("museum") || category.contains("art") || category.contains("gallery") {
                return .museum
            }
            if category.contains("viewpoint") || category.contains("view") || category.contains("park") || category.contains("garden") {
                return .viewpoint
            }
            if category.contains("bar") || category.contains("club") || category.contains("nightlife") {
                return .nightlife
            }
            if category.contains("restaurant") || category.contains("cafe") || category.contains("food") {
                return .food
            }
        }

        // PRIORITY 2: Check POI tags (backward compatible with categories)
        let allTags = poi.tags ?? poi.categories
        if let tags = allTags {
            for tag in tags {
                let lowercasedTag = tag.lowercased()

                // Museum & Art
                if lowercasedTag.contains("museum") || lowercasedTag.contains("art") || lowercasedTag.contains("gallery") {
                    return .museum
                }
                // Viewpoints & Nature
                if lowercasedTag.contains("viewpoint") || lowercasedTag.contains("view") || lowercasedTag.contains("park") || lowercasedTag.contains("garden") {
                    return .viewpoint
                }
                // Nightlife
                if lowercasedTag.contains("bar") || lowercasedTag.contains("club") || lowercasedTag.contains("nightlife") {
                    return .nightlife
                }
                // Food establishments
                if lowercasedTag.contains("restaurant") || lowercasedTag.contains("cafe") || lowercasedTag.contains("food") {
                    return .food
                }
            }
        }

        // PRIORITY 3: Fall back to block type if POI category/tags don't match
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

// MARK: - Helper for encoding arbitrary JSON

struct AnyCodable: Codable {
    let value: Any

    init(_ value: Any) {
        self.value = value
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.singleValueContainer()

        if container.decodeNil() {
            self.value = NSNull()
        } else if let bool = try? container.decode(Bool.self) {
            self.value = bool
        } else if let int = try? container.decode(Int.self) {
            self.value = int
        } else if let double = try? container.decode(Double.self) {
            self.value = double
        } else if let string = try? container.decode(String.self) {
            self.value = string
        } else if let array = try? container.decode([AnyCodable].self) {
            self.value = array.map { $0.value }
        } else if let dictionary = try? container.decode([String: AnyCodable].self) {
            self.value = dictionary.mapValues { $0.value }
        } else {
            throw DecodingError.dataCorruptedError(in: container, debugDescription: "Unknown type")
        }
    }

    func encode(to encoder: Encoder) throws {
        var container = encoder.singleValueContainer()

        switch value {
        case is NSNull:
            try container.encodeNil()
        case let bool as Bool:
            try container.encode(bool)
        case let int as Int:
            try container.encode(int)
        case let double as Double:
            try container.encode(double)
        case let string as String:
            try container.encode(string)
        case let array as [Any]:
            try container.encode(array.map { AnyCodable($0) })
        case let dictionary as [String: Any]:
            try container.encode(dictionary.mapValues { AnyCodable($0) })
        default:
            throw EncodingError.invalidValue(value, EncodingError.Context(codingPath: container.codingPath, debugDescription: "Unknown type"))
        }
    }
}
