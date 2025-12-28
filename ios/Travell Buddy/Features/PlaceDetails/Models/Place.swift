//
//  Place.swift
//  Travell Buddy
//
//  Lightweight place model used in day plan lists.
//

import Foundation
import CoreLocation
import SwiftUI

struct Place: Identifiable, Hashable {
    let id: String
    let name: String
    let category: PlaceCategory
    let coordinate: CLLocationCoordinate2D
    let shortDescription: String?

    // Optional time info from itinerary
    let scheduledTime: String?
    let endTime: String?
    let duration: TimeInterval?

    // POI details
    let rating: Double?
    let tags: [String]?
    let address: String?
    let note: String?

    // Travel info from previous stop
    let travelTimeMinutes: Int?
    let travelDistanceMeters: Int?

    func hash(into hasher: inout Hasher) {
        hasher.combine(id)
    }

    static func == (lhs: Place, rhs: Place) -> Bool {
        lhs.id == rhs.id
    }

    /// Calculated duration in minutes
    var durationMinutes: Int? {
        if let duration = duration {
            return Int(duration / 60)
        }

        guard let endTime = endTime, let scheduledTime = scheduledTime else { return nil }
        let timeComponents = scheduledTime.split(separator: ":")
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

enum PlaceCategory: String, CaseIterable, Codable {
    case restaurant
    case cafe
    case attraction
    case museum
    case park
    case viewpoint
    case nightlife
    case shopping
    case hotel
    case activity
    case other

    var displayName: String {
        switch self {
        case .restaurant: return "Ресторан"
        case .cafe: return "Кафе"
        case .attraction: return "Достопримечательность"
        case .museum: return "Музей"
        case .park: return "Парк"
        case .viewpoint: return "Смотровая"
        case .nightlife: return "Ночная жизнь"
        case .shopping: return "Шопинг"
        case .hotel: return "Отель"
        case .activity: return "Активность"
        case .other: return "Другое"
        }
    }

    var icon: String {
        switch self {
        case .restaurant: return "fork.knife"
        case .cafe: return "cup.and.saucer.fill"
        case .attraction: return "star.fill"
        case .museum: return "building.columns.fill"
        case .park: return "leaf.fill"
        case .viewpoint: return "binoculars.fill"
        case .nightlife: return "moon.stars.fill"
        case .shopping: return "bag.fill"
        case .hotel: return "bed.double.fill"
        case .activity: return "figure.walk"
        case .other: return "mappin"
        }
    }

    var color: Color {
        switch self {
        case .restaurant: return .orange
        case .cafe: return .brown
        case .attraction: return .purple
        case .museum: return .indigo
        case .park: return .green
        case .viewpoint: return .cyan
        case .nightlife: return .pink
        case .shopping: return .yellow
        case .hotel: return .blue
        case .activity: return .teal
        case .other: return .gray
        }
    }

    var iconName: String {
        icon
    }
}

// MARK: - Conversion from TripActivity

extension Place {
    init(from activity: TripActivity) {
        self.id = activity.id.uuidString
        self.name = activity.title
        self.category = PlaceCategory.from(activityCategory: activity.category)
        self.coordinate = activity.coordinate ?? CLLocationCoordinate2D(latitude: 0, longitude: 0)
        self.shortDescription = activity.description
        self.scheduledTime = activity.time
        self.endTime = activity.endTime
        self.duration = activity.durationMinutes.map { TimeInterval($0 * 60) }
        self.rating = activity.rating
        self.tags = activity.tags
        self.address = activity.address
        self.note = activity.note
        self.travelTimeMinutes = activity.travelTimeMinutes
        self.travelDistanceMeters = activity.travelDistanceMeters
    }
}

extension PlaceCategory {
    static func from(activityCategory: TripActivityCategory) -> PlaceCategory {
        switch activityCategory {
        case .food: return .restaurant
        case .walk: return .activity
        case .museum: return .museum
        case .viewpoint: return .viewpoint
        case .nightlife: return .nightlife
        case .other: return .other
        }
    }
}
