//
//  TripPlan.swift
//  Travell Buddy
//
//  Data model describing a generated travel plan.
//

import Foundation

struct TripPlan {
    let tripId: UUID
    let destinationCity: String
    let startDate: Date
    let endDate: Date
    let days: [TripDay]
    let travellersCount: Int
    let comfortLevel: String
    let interestsSummary: String
}
