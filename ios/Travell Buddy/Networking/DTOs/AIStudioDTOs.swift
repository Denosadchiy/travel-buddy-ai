//
//  AIStudioDTOs.swift
//  Travell Buddy
//
//  DTOs for AI Studio API communication.
//

import Foundation

// MARK: - GET /trip/{trip_id}/day/{day_id}/studio Response

struct DayStudioResponseDTO: Codable {
    let day: DayStudioDataDTO
    let settings: DaySettingsDTO
    let preset: String?
    let aiSummary: String
    let metrics: DayMetricsDTO
    let suggestions: [DaySuggestionDTO]?
    let revision: Int

    enum CodingKeys: String, CodingKey {
        case day
        case settings
        case preset
        case aiSummary = "ai_summary"
        case metrics
        case suggestions
        case revision
    }
}

struct DayStudioDataDTO: Codable {
    let places: [StudioPlaceDTO]
    let wishes: [WishMessageDTO]
}

struct StudioPlaceDTO: Codable {
    let id: String
    let name: String
    let latitude: Double
    let longitude: Double
    let timeStart: String
    let timeEnd: String
    let category: String
    let rating: Double?
    let priceLevel: Int?
    let photoUrl: String?
    let address: String?

    enum CodingKeys: String, CodingKey {
        case id
        case name
        case latitude
        case longitude
        case timeStart = "time_start"
        case timeEnd = "time_end"
        case category
        case rating
        case priceLevel = "price_level"
        case photoUrl = "photo_url"
        case address
    }
}

struct DaySettingsDTO: Codable {
    let tempo: String
    let startTime: String
    let endTime: String
    let budget: String

    enum CodingKeys: String, CodingKey {
        case tempo
        case startTime = "start_time"
        case endTime = "end_time"
        case budget
    }
}

struct DayMetricsDTO: Codable {
    let distanceKm: Double
    let stepsEstimate: Int
    let placesCount: Int
    let walkingTimeMinutes: Int

    enum CodingKeys: String, CodingKey {
        case distanceKm = "distance_km"
        case stepsEstimate = "steps_estimate"
        case placesCount = "places_count"
        case walkingTimeMinutes = "walking_time_minutes"
    }
}

struct DaySuggestionDTO: Codable {
    let type: String
    let title: String
    let description: String?
}

struct WishMessageDTO: Codable {
    let id: String
    let role: String
    let text: String
    let createdAt: String

    enum CodingKeys: String, CodingKey {
        case id
        case role
        case text
        case createdAt = "created_at"
    }
}

// MARK: - POST /trip/{trip_id}/day/{day_id}/apply_changes Request

struct ApplyChangesRequestDTO: Codable {
    let baseRevision: Int
    let changes: [DayChangeDTO]

    enum CodingKeys: String, CodingKey {
        case baseRevision = "base_revision"
        case changes
    }
}

struct DayChangeDTO: Codable {
    let type: String
    let data: DayChangeDataDTO

    enum CodingKeys: String, CodingKey {
        case type
        case data
    }
}

struct DayChangeDataDTO: Codable {
    // For UpdateSettings
    let tempo: String?
    let startTime: String?
    let endTime: String?
    let budget: String?

    // For SetPreset
    let preset: String?

    // For AddPlace
    let placeId: String?
    let placement: PlacementDTO?

    // For ReplacePlace
    let fromPlaceId: String?
    let toPlaceId: String?

    // For RemovePlace (uses placeId)

    // For AddWishMessage
    let text: String?

    enum CodingKeys: String, CodingKey {
        case tempo
        case startTime = "start_time"
        case endTime = "end_time"
        case budget
        case preset
        case placeId = "place_id"
        case placement
        case fromPlaceId = "from_place_id"
        case toPlaceId = "to_place_id"
        case text
    }

    // Convenience initializers
    static func updateSettings(tempo: String, startTime: String, endTime: String, budget: String) -> DayChangeDataDTO {
        DayChangeDataDTO(
            tempo: tempo, startTime: startTime, endTime: endTime, budget: budget,
            preset: nil, placeId: nil, placement: nil, fromPlaceId: nil, toPlaceId: nil, text: nil
        )
    }

    static func setPreset(_ preset: String?) -> DayChangeDataDTO {
        DayChangeDataDTO(
            tempo: nil, startTime: nil, endTime: nil, budget: nil,
            preset: preset, placeId: nil, placement: nil, fromPlaceId: nil, toPlaceId: nil, text: nil
        )
    }

    static func addPlace(placeId: String, placement: PlacementDTO) -> DayChangeDataDTO {
        DayChangeDataDTO(
            tempo: nil, startTime: nil, endTime: nil, budget: nil,
            preset: nil, placeId: placeId, placement: placement, fromPlaceId: nil, toPlaceId: nil, text: nil
        )
    }

    static func replacePlace(from: String, to: String) -> DayChangeDataDTO {
        DayChangeDataDTO(
            tempo: nil, startTime: nil, endTime: nil, budget: nil,
            preset: nil, placeId: nil, placement: nil, fromPlaceId: from, toPlaceId: to, text: nil
        )
    }

    static func removePlace(_ placeId: String) -> DayChangeDataDTO {
        DayChangeDataDTO(
            tempo: nil, startTime: nil, endTime: nil, budget: nil,
            preset: nil, placeId: placeId, placement: nil, fromPlaceId: nil, toPlaceId: nil, text: nil
        )
    }

    static func addWish(_ text: String) -> DayChangeDataDTO {
        DayChangeDataDTO(
            tempo: nil, startTime: nil, endTime: nil, budget: nil,
            preset: nil, placeId: nil, placement: nil, fromPlaceId: nil, toPlaceId: nil, text: text
        )
    }
}

struct PlacementDTO: Codable {
    let type: String  // "auto", "in_slot", "at_time"
    let slotIndex: Int?
    let hour: Int?
    let minute: Int?

    enum CodingKeys: String, CodingKey {
        case type
        case slotIndex = "slot_index"
        case hour
        case minute
    }

    static var auto: PlacementDTO {
        PlacementDTO(type: "auto", slotIndex: nil, hour: nil, minute: nil)
    }

    static func inSlot(_ index: Int) -> PlacementDTO {
        PlacementDTO(type: "in_slot", slotIndex: index, hour: nil, minute: nil)
    }

    static func atTime(hour: Int, minute: Int) -> PlacementDTO {
        PlacementDTO(type: "at_time", slotIndex: nil, hour: hour, minute: minute)
    }
}

// MARK: - Apply Changes Response (same as GET studio)

typealias ApplyChangesResponseDTO = DayStudioResponseDTO

// MARK: - POST /places/search

struct PlaceSearchRequestDTO: Codable {
    let query: String
    let city: String
    let limit: Int?

    enum CodingKeys: String, CodingKey {
        case query
        case city
        case limit
    }
}

struct PlaceSearchResponseDTO: Codable {
    let results: [PlaceSearchResultDTO]
}

struct PlaceSearchResultDTO: Codable {
    let placeId: String
    let name: String
    let category: String
    let rating: Double?
    let address: String?
    let photoUrl: String?
    let latitude: Double?
    let longitude: Double?

    enum CodingKeys: String, CodingKey {
        case placeId = "place_id"
        case name
        case category
        case rating
        case address
        case photoUrl = "photo_url"
        case latitude
        case longitude
    }
}

// MARK: - Mapping Extensions

extension DayStudioResponseDTO {
    func toStudioState() -> DayStudioState {
        let dateFormatter = DateFormatter()
        dateFormatter.dateFormat = "HH:mm"

        let startTime = dateFormatter.date(from: settings.startTime) ??
            Calendar.current.date(bySettingHour: 8, minute: 0, second: 0, of: Date())!
        let endTime = dateFormatter.date(from: settings.endTime) ??
            Calendar.current.date(bySettingHour: 18, minute: 0, second: 0, of: Date())!

        return DayStudioState(
            places: day.places.map { $0.toStudioPlace() },
            tempo: StudioTempo(rawValue: settings.tempo) ?? .medium,
            startTime: startTime,
            endTime: endTime,
            budget: StudioBudget(rawValue: settings.budget) ?? .medium,
            preset: preset.flatMap { DayPreset(rawValue: $0) },
            aiSummary: aiSummary,
            metrics: metrics.toDayMetrics(),
            wishes: day.wishes.map { $0.toWishMessage() },
            revision: revision
        )
    }
}

extension StudioPlaceDTO {
    func toStudioPlace() -> StudioPlace {
        StudioPlace(
            id: id,
            name: name,
            latitude: latitude,
            longitude: longitude,
            timeStart: timeStart,
            timeEnd: timeEnd,
            category: category,
            rating: rating,
            priceLevel: priceLevel,
            photoURL: photoUrl.flatMap { URL(string: $0) },
            address: address
        )
    }
}

extension DayMetricsDTO {
    func toDayMetrics() -> DayMetrics {
        DayMetrics(
            distanceKm: distanceKm,
            stepsEstimate: stepsEstimate,
            placesCount: placesCount,
            walkingTimeMinutes: walkingTimeMinutes
        )
    }
}

extension WishMessageDTO {
    func toWishMessage() -> WishMessage {
        let dateFormatter = ISO8601DateFormatter()
        let createdDate = dateFormatter.date(from: createdAt) ?? Date()

        return WishMessage(
            id: UUID(uuidString: id) ?? UUID(),
            role: role == "assistant" ? .assistant : .user,
            text: text,
            createdAt: createdDate
        )
    }
}

extension PlaceSearchResultDTO {
    func toSearchResult() -> StudioSearchResult {
        StudioSearchResult(
            id: placeId,
            name: name,
            category: category,
            rating: rating,
            address: address,
            photoURL: photoUrl.flatMap { URL(string: $0) }
        )
    }
}
