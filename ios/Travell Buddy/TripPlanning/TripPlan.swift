//
//  TripPlan.swift
//  Travell Buddy
//
//  Data model describing a generated travel plan.
//

import Foundation
import CoreLocation

struct TripPlan {
    let tripId: UUID
    let destinationCity: String
    let startDate: Date
    let endDate: Date
    let days: [TripDay]
    let travellersCount: Int
    let comfortLevel: String
    let interestsSummary: String

    /// Returns the coordinate of the first activity with valid coordinates, or nil if none found.
    var cityCoordinate: CLLocationCoordinate2D? {
        for day in days {
            for activity in day.activities {
                if let coord = activity.coordinate {
                    return coord
                }
            }
        }
        return nil
    }
}
