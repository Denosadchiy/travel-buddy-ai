//
//  TripCreateRequestDTO.swift
//  Travell Buddy
//
//  Request DTO for creating a new trip.
//

import Foundation

struct TripCreateRequestDTO: Codable {
    let city: String
    let startDate: String  // "YYYY-MM-DD"
    let endDate: String    // "YYYY-MM-DD"
    let numTravelers: Int
    let pace: String       // "slow" | "medium" | "fast"
    let budget: String     // "low" | "medium" | "high"
    let interests: [String]
    let dailyRoutine: DailyRoutineDTO?
    let hotelLocation: String?
    let additionalPreferences: [String: String]?

    enum CodingKeys: String, CodingKey {
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
    }
}

struct DailyRoutineDTO: Codable {
    let wakeTime: String       // "HH:MM:SS"
    let sleepTime: String      // "HH:MM:SS"
    let breakfastWindow: [String]  // ["HH:MM:SS", "HH:MM:SS"]
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
