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
    let startDate: String
    let endDate: String
    let numTravelers: Int
    let pace: String
    let budget: String
    let interests: [String]
    let dailyRoutine: DailyRoutineResponseDTO?
    let hotelLocation: String?
    let additionalPreferences: [String: String]?
    let createdAt: String
    let updatedAt: String

    enum CodingKeys: String, CodingKey {
        case id
        case city
        case startDate = "start_date"
        case endDate = "end_date"
        case numTravelers = "num_travelers"
        case pace
        case budget
        case interests
        case dailyRoutine = "daily_routine"
        case hotelLocation = "hotel_location"
        case additionalPreferences = "additional_preferences"
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
