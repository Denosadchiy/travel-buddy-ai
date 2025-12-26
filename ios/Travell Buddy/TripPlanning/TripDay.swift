//
//  TripDay.swift
//  Travell Buddy
//
//  Represents itinerary details for a single day.
//

import Foundation

struct TripDay: Identifiable {
    let index: Int
    let date: Date
    let title: String?
    let summary: String?
    let activities: [TripActivity]
    
    var id: Int { index }
}
