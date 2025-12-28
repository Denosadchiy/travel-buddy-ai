//
//  TripActivity.swift
//  Travell Buddy
//
//  One concrete activity within a trip day.
//

import Foundation
import CoreLocation

struct TripActivity: Identifiable {
    let id: UUID
    let time: String
    let endTime: String?
    let title: String
    let description: String
    let category: TripActivityCategory
    let address: String?
    let note: String?

    // Map-related fields
    let latitude: Double?
    let longitude: Double?
    let travelPolyline: String?  // Encoded polyline from previous activity

    // POI details
    let rating: Double?
    let tags: [String]?
    let poiId: String?

    // Travel info from previous
    let travelTimeMinutes: Int?
    let travelDistanceMeters: Int?

    /// Returns coordinate if both lat/lon are available
    var coordinate: CLLocationCoordinate2D? {
        guard let lat = latitude, let lon = longitude else { return nil }
        return CLLocationCoordinate2D(latitude: lat, longitude: lon)
    }

    /// Returns true if this activity has valid map coordinates
    var hasCoordinates: Bool {
        latitude != nil && longitude != nil
    }

    /// Calculated duration in minutes based on start/end time
    var durationMinutes: Int? {
        guard let endTime = endTime else { return nil }
        let timeComponents = time.split(separator: ":")
        let endComponents = endTime.split(separator: ":")
        guard timeComponents.count >= 2, endComponents.count >= 2,
              let startHour = Int(timeComponents[0]),
              let startMin = Int(timeComponents[1]),
              let endHour = Int(endComponents[0]),
              let endMin = Int(endComponents[1]) else {
            return nil
        }
        let startTotal = startHour * 60 + startMin
        let endTotal = endHour * 60 + endMin
        return endTotal - startTotal
    }
}

enum TripActivityCategory: CaseIterable {
    case food
    case walk
    case museum
    case viewpoint
    case nightlife
    case other
}
