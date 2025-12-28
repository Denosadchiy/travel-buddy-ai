//
//  PlaceDetailsViewModel.swift
//  Travell Buddy
//
//  ViewModel for managing place details loading and state.
//

import Foundation
import SwiftUI
import MapKit

// MARK: - State

enum PlaceDetailsState: Equatable {
    case idle
    case loading
    case loaded(PlaceDetails)
    case error(String)

    static func == (lhs: PlaceDetailsState, rhs: PlaceDetailsState) -> Bool {
        switch (lhs, rhs) {
        case (.idle, .idle), (.loading, .loading):
            return true
        case (.loaded(let a), .loaded(let b)):
            return a.id == b.id
        case (.error(let a), .error(let b)):
            return a == b
        default:
            return false
        }
    }
}

// MARK: - ViewModel

@MainActor
final class PlaceDetailsViewModel: ObservableObject {

    // MARK: - Published State

    @Published private(set) var state: PlaceDetailsState = .idle
    @Published private(set) var isSaved: Bool = false
    @Published private(set) var isMandatory: Bool = false
    @Published private(set) var isAvoided: Bool = false

    // MARK: - Properties

    let place: Place
    private let service: PlaceDetailsServiceProtocol
    private var loadTask: Task<Void, Never>?

    // MARK: - Computed Properties

    var details: PlaceDetails? {
        if case .loaded(let details) = state {
            return details
        }
        return nil
    }

    var isLoading: Bool {
        state == .loading
    }

    var errorMessage: String? {
        if case .error(let message) = state {
            return message
        }
        return nil
    }

    // MARK: - Init

    init(
        place: Place,
        service: PlaceDetailsServiceProtocol = PlaceDetailsService.shared
    ) {
        self.place = place
        self.service = service
    }

    deinit {
        loadTask?.cancel()
    }

    // MARK: - Public Methods

    func loadDetails() {
        guard state != .loading else { return }

        loadTask?.cancel()
        state = .loading

        loadTask = Task {
            do {
                let details = try await service.fetchDetails(for: place.id)
                guard !Task.isCancelled else { return }
                state = .loaded(details)
            } catch {
                guard !Task.isCancelled else { return }
                state = .error(error.localizedDescription)
            }
        }
    }

    func retry() {
        loadDetails()
    }

    func cancelLoading() {
        loadTask?.cancel()
        loadTask = nil
    }

    // MARK: - Quick Actions

    func toggleSave() {
        isSaved.toggle()
        // TODO: Persist to backend/local storage
        HapticFeedback.light()
    }

    func toggleMandatory() {
        isMandatory.toggle()
        if isMandatory {
            isAvoided = false
        }
        // TODO: Persist to backend/local storage
        HapticFeedback.light()
    }

    func toggleAvoided() {
        isAvoided.toggle()
        if isAvoided {
            isMandatory = false
        }
        // TODO: Persist to backend/local storage
        HapticFeedback.light()
    }

    func requestReplace() {
        // TODO: Open replace flow
        HapticFeedback.medium()
    }

    // MARK: - Navigation Actions

    func openInMaps() {
        guard let details = details else { return }

        let placemark = MKPlacemark(coordinate: details.coordinate)
        let mapItem = MKMapItem(placemark: placemark)
        mapItem.name = details.name

        mapItem.openInMaps(launchOptions: [
            MKLaunchOptionsDirectionsModeKey: MKLaunchOptionsDirectionsModeWalking
        ])

        HapticFeedback.light()
    }

    func callPhone() {
        guard let details = details,
              let phone = details.phone,
              let url = URL(string: "tel://\(phone.replacingOccurrences(of: " ", with: ""))") else {
            return
        }

        UIApplication.shared.open(url)
        HapticFeedback.light()
    }

    func openWebsite() {
        guard let details = details, let url = details.website else { return }
        UIApplication.shared.open(url)
        HapticFeedback.light()
    }
}

// MARK: - Haptic Feedback Helper

private enum HapticFeedback {
    static func light() {
        let generator = UIImpactFeedbackGenerator(style: .light)
        generator.impactOccurred()
    }

    static func medium() {
        let generator = UIImpactFeedbackGenerator(style: .medium)
        generator.impactOccurred()
    }
}
