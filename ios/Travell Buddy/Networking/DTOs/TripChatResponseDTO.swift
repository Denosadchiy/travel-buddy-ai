//
//  TripChatResponseDTO.swift
//  Travell Buddy
//
//  Response DTO for chat endpoint with assistant reply and updated trip.
//

import Foundation

struct TripChatResponseDTO: Codable {
    let assistantMessage: String
    let trip: TripResponseDTO

    enum CodingKeys: String, CodingKey {
        case assistantMessage = "assistant_message"
        case trip
    }
}
