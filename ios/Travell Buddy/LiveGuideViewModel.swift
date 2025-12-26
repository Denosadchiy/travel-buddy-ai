//
//  LiveGuideViewModel.swift
//  Travell Buddy
//
//  Draft view model template for LiveGuideView with mock data.
//

import Combine
import Foundation

/// Temporary data container for the LiveGuideView until API integration is available.
final class LiveGuideViewModel: ObservableObject {
    @Published var points: [LiveGuidePoint]
    @Published var selectedPoint: LiveGuidePoint?
    
    init() {
        points = [
            LiveGuidePoint(
                id: UUID(),
                name: "Hotel Arrival",
                shortDescription: "Check in and drop bags",
                latitude: 55.7558,
                longitude: 37.6173,
                status: .completed
            ),
            LiveGuidePoint(
                id: UUID(),
                name: "City Walk",
                shortDescription: "Guided walk through the center",
                latitude: 55.7600,
                longitude: 37.6200,
                status: .current
            ),
            LiveGuidePoint(
                id: UUID(),
                name: "Rooftop Cafe",
                shortDescription: "Relax with a view",
                latitude: 55.7650,
                longitude: 37.6300,
                status: .next
            ),
            LiveGuidePoint(
                id: UUID(),
                name: "Evening Show",
                shortDescription: "Live performance nearby",
                latitude: 55.7700,
                longitude: 37.6400,
                status: .upcoming
            )
        ]
        selectedPoint = nil
    }
}
