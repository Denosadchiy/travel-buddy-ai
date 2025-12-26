//
//  LiveGuidePoint.swift
//  Travell Buddy
//
//  Created as a simple data template for LiveGuideView.
//

import Foundation

/// Represents a single point in the user's live guide route for the current day.
struct LiveGuidePoint: Identifiable {
    let id: UUID
    let name: String
    let shortDescription: String
    let latitude: Double
    let longitude: Double
    let status: LiveGuidePointStatus
}

/// Describes the state of a live guide point.
enum LiveGuidePointStatus {
    case completed
    case current
    case next
    case upcoming
}
