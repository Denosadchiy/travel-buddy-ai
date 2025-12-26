//
//  TripActivity.swift
//  Travell Buddy
//
//  One concrete activity within a trip day.
//

import Foundation

struct TripActivity: Identifiable {
    let id: UUID
    let time: String
    let title: String
    let description: String
    let category: TripActivityCategory
    let address: String?
    let note: String?
}

enum TripActivityCategory: CaseIterable {
    case food
    case walk
    case museum
    case viewpoint
    case nightlife
    case other
}
