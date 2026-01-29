//
//  TripResponseDTO.swift
//  Travell Buddy
//
//  Response DTO for trip data.
//

import Foundation

struct TripResponseDTO: Codable {
    let id: String
    let city: String
    let cityCenterLat: Double?
    let cityCenterLon: Double?
    let startDate: String
    let endDate: String
    let numTravelers: Int
    let pace: String
    let budget: String
    let interests: [String]
    let dailyRoutine: DailyRoutineResponseDTO?
    let hotelLocation: String?
    let hotelLat: Double?
    let hotelLon: Double?
    let additionalPreferences: [String: String]?
    let cityPhotoReference: String?
    let createdAt: String
    let updatedAt: String

    enum CodingKeys: String, CodingKey {
        case id
        case city
        case cityCenterLat = "city_center_lat"
        case cityCenterLon = "city_center_lon"
        case startDate = "start_date"
        case endDate = "end_date"
        case numTravelers = "num_travelers"
        case pace
        case budget
        case interests
        case dailyRoutine = "daily_routine"
        case hotelLocation = "hotel_location"
        case hotelLat = "hotel_lat"
        case hotelLon = "hotel_lon"
        case additionalPreferences = "additional_preferences"
        case cityPhotoReference = "city_photo_reference"
        case createdAt = "created_at"
        case updatedAt = "updated_at"
    }
}

struct DailyRoutineResponseDTO: Codable {
    let wakeTime: String
    let sleepTime: String
    let breakfastWindow: [String]
    let lunchWindow: [String]
    let dinnerWindow: [String]

    enum CodingKeys: String, CodingKey {
        case wakeTime = "wake_time"
        case sleepTime = "sleep_time"
        case breakfastWindow = "breakfast_window"
        case lunchWindow = "lunch_window"
        case dinnerWindow = "dinner_window"
    }
}
