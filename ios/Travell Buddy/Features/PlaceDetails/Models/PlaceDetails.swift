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

// MARK: - Mock Data for Development

extension PlaceDetails {
    static func mock(for place: Place) -> PlaceDetails {
        PlaceDetails(
            id: place.id,
            name: place.name,
            category: place.category,
            coordinate: place.coordinate,
            photos: [
                PlacePhoto(
                    id: "1",
                    url: URL(string: "https://images.unsplash.com/photo-1552832230-c0197dd311b5?w=800")!,
                    width: 800,
                    height: 600,
                    attribution: "Unsplash"
                ),
                PlacePhoto(
                    id: "2",
                    url: URL(string: "https://images.unsplash.com/photo-1515542622106-78bda8ba0e5b?w=800")!,
                    width: 800,
                    height: 600,
                    attribution: "Unsplash"
                )
            ],
            rating: 4.5,
            reviewsCount: 1284,
            priceLevel: .moderate,
            openingHours: [
                "Пн: 10:00–22:00",
                "Вт: 10:00–22:00",
                "Ср: 10:00–22:00",
                "Чт: 10:00–22:00",
                "Пт: 10:00–23:00",
                "Сб: 10:00–23:00",
                "Вс: 11:00–21:00"
            ],
            isOpenNow: true,
            closingTime: "22:00",
            address: "Via del Corso, 123, 00186 Roma RM, Италия",
            website: URL(string: "https://example.com"),
            phone: "+39 06 1234 5678",
            aiWhyRecommended: "Это место идеально подходит для вашего интереса к истории и архитектуре. Здесь вы сможете увидеть уникальные фрески эпохи Возрождения.",
            tips: [
                "Лучше приходить утром до 10:00",
                "Возьмите аудиогид на русском языке"
            ],
            suggestedDuration: 90 * 60, // 1.5 hours
            bestVisitTime: "Утро",
            travelTimeFromPrevious: 15 * 60, // 15 min
            travelDistanceFromPrevious: 1.2, // km
            travelMode: .walking
        )
    }
}
