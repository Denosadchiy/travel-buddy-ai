//
//  SavedTripsManager.swift
//  Travell Buddy
//
//  Manager for saved trips (bookmarks) with server sync.
//

import Foundation
import Combine

@MainActor
final class SavedTripsManager: ObservableObject {

    static let shared = SavedTripsManager()

    // MARK: - Published State

    /// Top 5 trips for Home screen
    @Published private(set) var topTrips: [SavedTripCard] = []

    /// All saved trips (for AllTripsView)
    @Published private(set) var allTrips: [SavedTripCard] = []

    /// Total count of saved trips
    @Published private(set) var totalCount: Int = 0

    /// Loading state
    @Published private(set) var isLoading: Bool = false

    /// Error message (auto-cleared)
    @Published var errorMessage: String?

    // MARK: - Private

    private let apiClient = AuthenticatedAPIClient.shared
    private var cancellables = Set<AnyCancellable>()

    private init() {
        // Listen to auth state changes to refresh data
        AuthManager.shared.$state
            .sink { [weak self] state in
                Task { @MainActor in
                    switch state {
                    case .loggedIn:
                        await self?.refreshTop5()
                    case .loggedOut, .error:
                        self?.clearAll()
                    default:
                        break
                    }
                }
            }
            .store(in: &cancellables)
    }

    // MARK: - Public API

    /// Refresh top 5 trips (for Home screen)
    func refreshTop5() async {
        guard AuthManager.shared.isAuthenticated else {
            clearAll()
            return
        }

        isLoading = true
        defer { isLoading = false }

        do {
            let response: SavedTripsListResponseDTO = try await apiClient.execute(
                path: "/saved_trips",
                method: .get,
                queryItems: [URLQueryItem(name: "limit", value: "5")]
            )

            topTrips = response.trips.compactMap { SavedTripCard.fromDTO($0) }
            totalCount = response.total
            errorMessage = nil

        } catch {
            print("[SavedTrips] Failed to fetch top 5: \(error)")
            errorMessage = "Не удалось загрузить поездки"
        }
    }

    /// Refresh all trips (for AllTripsView)
    func refreshAll() async {
        guard AuthManager.shared.isAuthenticated else {
            clearAll()
            return
        }

        isLoading = true
        defer { isLoading = false }

        do {
            let response: SavedTripsListResponseDTO = try await apiClient.execute(
                path: "/saved_trips",
                method: .get
            )

            allTrips = response.trips.compactMap { SavedTripCard.fromDTO($0) }
            totalCount = response.total
            errorMessage = nil

        } catch {
            print("[SavedTrips] Failed to fetch all: \(error)")
            errorMessage = "Не удалось загрузить поездки"
        }
    }

    /// Save a trip
    /// - Returns: SavedTripCard on success, nil on failure
    @discardableResult
    func saveTrip(
        tripId: UUID,
        cityName: String,
        startDate: Date,
        endDate: Date,
        heroImageUrl: String?
    ) async -> SavedTripCard? {
        guard AuthManager.shared.isAuthenticated else {
            errorMessage = "Требуется авторизация"
            return nil
        }

        let dateFormatter = DateFormatter()
        dateFormatter.dateFormat = "yyyy-MM-dd"

        let request = SaveTripRequestDTO(
            tripId: tripId.uuidString,
            cityName: cityName,
            startDate: dateFormatter.string(from: startDate),
            endDate: dateFormatter.string(from: endDate),
            heroImageUrl: heroImageUrl,
            routeSnapshot: nil
        )

        do {
            let body = try JSONEncoder().encode(request)

            let response: SavedTripResponseDTO = try await apiClient.execute(
                path: "/saved_trips",
                method: .post,
                body: body
            )

            let card = SavedTripCard.fromDTO(response)

            // Refresh top 5 after saving
            await refreshTop5()

            errorMessage = nil
            return card

        } catch {
            print("[SavedTrips] Failed to save: \(error)")
            errorMessage = "Не удалось сохранить маршрут"
            return nil
        }
    }

    /// Check if a trip is saved
    func isTripSaved(tripId: UUID) async -> Bool {
        guard AuthManager.shared.isAuthenticated else { return false }

        do {
            let _: SavedTripResponseDTO = try await apiClient.execute(
                path: "/saved_trips/check/\(tripId.uuidString)",
                method: .get
            )
            return true
        } catch {
            return false
        }
    }

    /// Get detailed information about a saved trip including full itinerary
    func getSavedTripDetail(id: UUID) async -> SavedTripDetailResponseDTO? {
        guard AuthManager.shared.isAuthenticated else {
            errorMessage = "Требуется авторизация"
            return nil
        }

        do {
            let detail: SavedTripDetailResponseDTO = try await apiClient.execute(
                path: "/saved_trips/\(id.uuidString)/detail",
                method: .get
            )

            errorMessage = nil
            return detail

        } catch {
            print("[SavedTrips] Failed to fetch detail: \(error)")
            errorMessage = "Не удалось загрузить детали поездки"
            return nil
        }
    }

    /// Get detailed information about a saved trip and convert it to TripPlan
    func getSavedTripAsPlan(id: UUID) async -> TripPlan? {
        guard let detail = await getSavedTripDetail(id: id) else {
            return nil
        }

        return detail.toTripPlan()
    }

    /// Delete a saved trip
    func deleteSavedTrip(id: UUID) async -> Bool {
        guard AuthManager.shared.isAuthenticated else {
            errorMessage = "Требуется авторизация"
            return false
        }

        do {
            try await apiClient.executeVoid(
                path: "/saved_trips/\(id.uuidString)",
                method: .delete
            )

            // Remove from local cache
            topTrips.removeAll { $0.id == id }
            allTrips.removeAll { $0.id == id }
            totalCount = max(0, totalCount - 1)

            errorMessage = nil
            return true

        } catch {
            print("[SavedTrips] Failed to delete: \(error)")
            errorMessage = "Не удалось удалить поездку"
            return false
        }
    }

    // MARK: - Private

    private func clearAll() {
        topTrips = []
        allTrips = []
        totalCount = 0
        errorMessage = nil
    }
}
