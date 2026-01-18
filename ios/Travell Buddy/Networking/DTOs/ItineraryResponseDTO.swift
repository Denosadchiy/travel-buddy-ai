//
//  ItineraryResponseDTO.swift
//  Travell Buddy
//
//  Response DTO for trip itinerary with POIs and blocks.
//

import Foundation

struct ItineraryResponseDTO: Codable {
    let tripId: String
    let days: [TripItineraryDayDTO]
    let createdAt: String
    let tripSummary: String?  // Brief overview of the entire trip
    let isLocked: Bool?
    let cityPhotoReference: String?  // Google Places photo reference for the destination city

    enum CodingKeys: String, CodingKey {
        case tripId = "trip_id"
        case days
        case createdAt = "created_at"
        case tripSummary = "trip_summary"
        case isLocked = "is_locked"
        case cityPhotoReference = "city_photo_reference"
    }
}

struct TripItineraryDayDTO: Codable {
    let dayNumber: Int
    let date: String  // "YYYY-MM-DD"
    let theme: String?
    let summary: String?  // Brief description of what to expect this day
    let blocks: [ItineraryBlockDTO]

    enum CodingKeys: String, CodingKey {
        case dayNumber = "day_number"
        case date
        case theme
        case summary
        case blocks
    }
}

struct ItineraryBlockDTO: Codable {
    let blockType: String  // "meal" | "activity" | "rest" | "nightlife"
    let startTime: String  // "HH:MM:SS"
    let endTime: String    // "HH:MM:SS"
    let poi: POICandidateDTO?
    let travelTimeFromPrev: Int?  // minutes
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

struct POICandidateDTO: Codable {
    let poiId: String?
    let name: String
    let category: String?
    let tags: [String]?
    let rating: Double?
    let location: String?
    let lat: Double?
    let lon: Double?
    let rankScore: Double?

    enum CodingKeys: String, CodingKey {
        case poiId = "poi_id"
        case name
        case category
        case tags
        case rating
        case location
        case lat
        case lon
        case rankScore = "rank_score"
    }
}
