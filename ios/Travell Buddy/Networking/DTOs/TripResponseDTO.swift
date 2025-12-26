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
    let hotelLocation: String?
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
        case hotelLocation = "hotel_location"
        case createdAt = "created_at"
        case updatedAt = "updated_at"
    }
}
