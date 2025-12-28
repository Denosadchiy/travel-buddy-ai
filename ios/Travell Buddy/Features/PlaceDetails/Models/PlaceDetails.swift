//
//  PlaceDetails.swift
//  Travell Buddy
//
//  Full place details loaded on demand.
//

import Foundation
import CoreLocation

struct PlaceDetails: Identifiable {
    let id: String
    let name: String
    let category: PlaceCategory
    let coordinate: CLLocationCoordinate2D

    // Photos
    let photos: [PlacePhoto]

    // Ratings & Reviews
    let rating: Double?
    let reviewsCount: Int?
    let priceLevel: PriceLevel?

    // Opening hours
    let openingHours: [String]?
    let isOpenNow: Bool?
    let closingTime: String?

    // Contact & Location
    let address: String?
    let website: URL?
    let phone: String?

    // AI-generated content
    let aiWhyRecommended: String?
    let tips: [String]?

    // Visit info
    let suggestedDuration: TimeInterval?
    let bestVisitTime: String?

    // Travel from previous stop (optional, context-dependent)
    let travelTimeFromPrevious: TimeInterval?
    let travelDistanceFromPrevious: Double?
    let travelMode: TravelMode?
}

struct PlacePhoto: Identifiable {
    let id: String
    let url: URL
    let width: Int?
    let height: Int?
    let attribution: String?
}

enum PriceLevel: Int, CaseIterable {
    case free = 0
    case cheap = 1
    case moderate = 2
    case expensive = 3
    case veryExpensive = 4

    var displayText: String {
        switch self {
        case .free: return "Бесплатно"
        case .cheap: return "$"
        case .moderate: return "$$"
        case .expensive: return "$$$"
        case .veryExpensive: return "$$$$"
        }
    }

    var dollarSigns: String {
        switch self {
        case .free: return "Бесплатно"
        case .cheap: return "$"
        case .moderate: return "$$"
        case .expensive: return "$$$"
        case .veryExpensive: return "$$$$"
        }
    }
}

enum TravelMode: String, CaseIterable {
    case walking
    case driving
    case transit
    case cycling

    var icon: String {
        switch self {
        case .walking: return "figure.walk"
        case .driving: return "car.fill"
        case .transit: return "bus.fill"
        case .cycling: return "bicycle"
        }
    }

    var displayName: String {
        switch self {
        case .walking: return "Пешком"
        case .driving: return "На машине"
        case .transit: return "Транспорт"
        case .cycling: return "Велосипед"
        }
    }
}

