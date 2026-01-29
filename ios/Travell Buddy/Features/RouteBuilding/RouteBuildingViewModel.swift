//
//  RouteBuildingViewModel.swift
//  Travell Buddy
//
//  ViewModel managing route building animation and API calls.
//

import Foundation
import MapKit
import Combine

// MARK: - State

enum RouteBuildingState: Equatable {
    case idle
    case loading
    case animating
    case completed(ItineraryResponseDTO)
    case paywallRequired
    case failed

    static func == (lhs: RouteBuildingState, rhs: RouteBuildingState) -> Bool {
        switch (lhs, rhs) {
        case (.idle, .idle), (.loading, .loading), (.animating, .animating), (.paywallRequired, .paywallRequired), (.failed, .failed):
            return true
        case (.completed(let a), .completed(let b)):
            return a.tripId == b.tripId
        default:
            return false
        }
    }
}

// MARK: - Demo POI for Animation

struct DemoPOI: Identifiable {
    let id = UUID()
    let coordinate: CLLocationCoordinate2D
    let name: String
    let category: POICategory

    enum POICategory {
        case restaurant
        case attraction
        case hotel
        case activity

        var color: String {
            switch self {
            case .restaurant: return "orange"
            case .attraction: return "purple"
            case .hotel: return "blue"
            case .activity: return "green"
            }
        }

        var icon: String {
            switch self {
            case .restaurant: return "fork.knife"
            case .attraction: return "star.fill"
            case .hotel: return "bed.double.fill"
            case .activity: return "figure.walk"
            }
        }
    }
}

// MARK: - ViewModel

@MainActor
final class RouteBuildingViewModel: ObservableObject {
    // MARK: - Published Properties

    @Published private(set) var state: RouteBuildingState = .idle
    @Published private(set) var visiblePOIs: [DemoPOI] = []
    @Published private(set) var routeCoordinates: [CLLocationCoordinate2D] = []
    @Published private(set) var latestPOIIndex: Int = -1
    @Published private(set) var currentSubtitle: String = ""

    // MARK: - Private Properties

    private var tripId: UUID?  // Made optional - will be set after trip creation
    private var cityCoordinate: CLLocationCoordinate2D  // Made mutable to update from backend
    private let apiClient: TripPlanningAPIClientProtocol
    private let tripRequest: TripCreateRequestDTO?  // Parameters for creating trip

    private var demoPOIs: [DemoPOI] = []
    private var animationTimer: Timer?
    private var subtitleTimer: Timer?
    private var currentPOIIndex = 0
    private var subtitleIndex = 0
    private var apiTask: Task<Void, Never>?
    private var itineraryResult: ItineraryResponseDTO?
    private var animationStartTime: Date?

    // Minimum animation duration in seconds
    private let minimumAnimationDuration: TimeInterval = 1.0

    private let subtitles = [
        "Анализируем ваши интересы",
        "Подбираем персонализированные места",
        "Группируем POI по районам",
        "Оптимизируем маршрут",
        "Проверяем расписание работы"
    ]

    private let finalizingSubtitle = "Завершаем построение маршрута…"

    // MARK: - Init

    init(
        tripId: UUID? = nil,
        tripRequest: TripCreateRequestDTO? = nil,
        cityCoordinate: CLLocationCoordinate2D,
        apiClient: TripPlanningAPIClientProtocol
    ) {
        self.tripId = tripId
        self.tripRequest = tripRequest
        self.cityCoordinate = cityCoordinate
        self.apiClient = apiClient

        // Generate demo POIs around the city center
        self.demoPOIs = Self.generateDemoPOIs(around: cityCoordinate)
        self.currentSubtitle = subtitles[0]
    }

    deinit {
        animationTimer?.invalidate()
        subtitleTimer?.invalidate()
        apiTask?.cancel()
    }

    // MARK: - Public Methods

    func startRouteGeneration() {
        guard state == .idle else {
            print("⚠️ startRouteGeneration: state is not idle, current state: \(state)")
            return
        }

        print("🚀 Starting route generation for trip: \(tripId)")
        state = .loading
        animationStartTime = Date()

        // Start animations
        startPOIAnimation()
        startSubtitleRotation()

        // Start API call
        apiTask = Task {
            await fetchRoute()
        }
    }

    func retry() {
        state = .idle
        visiblePOIs = []
        routeCoordinates = []
        latestPOIIndex = -1
        currentPOIIndex = 0
        subtitleIndex = 0
        itineraryResult = nil

        startRouteGeneration()
    }

    // MARK: - Private Methods

    private func createTrip() async throws -> UUID {
        guard let tripRequest = tripRequest else {
            throw APIError.networkError(NSError(domain: "No trip request provided", code: -1))
        }

        print("🚀 createTrip: creating trip for city \(tripRequest.city)")
        let tripResponse = try await apiClient.createTrip(tripRequest)

        guard let tripId = UUID(uuidString: tripResponse.id) else {
            throw APIError.decodingError(NSError(domain: "Invalid trip ID", code: -1))
        }

        // Update city coordinates from backend if available
        if let lat = tripResponse.cityCenterLat, let lon = tripResponse.cityCenterLon {
            let newCoordinate = CLLocationCoordinate2D(latitude: lat, longitude: lon)
            print("✅ createTrip: updating city coordinate from backend: \(lat), \(lon)")
            self.cityCoordinate = newCoordinate

            // Regenerate demo POIs around correct coordinates
            self.demoPOIs = Self.generateDemoPOIs(around: newCoordinate)

            // Reset animation state to show new POIs
            self.visiblePOIs = []
            self.routeCoordinates = []
            self.currentPOIIndex = 0
        } else {
            print("⚠️ createTrip: backend did not return city coordinates, using fallback")
        }

        print("✅ createTrip: trip created with ID \(tripId)")
        return tripId
    }

    private func fetchRoute() async {
        do {
            // If we don't have a tripId yet, create the trip first
            if tripId == nil {
                print("📡 fetchRoute: creating trip first")
                let createdTripId = try await createTrip()
                self.tripId = createdTripId
            }

            guard let tripId = tripId else {
                throw APIError.networkError(NSError(domain: "No trip ID available", code: -1))
            }

            print("📡 fetchRoute: calling full plan API for trip \(tripId)")

            // Use full plan endpoint with agentic POI Curator + Route Engineer for maximum personalization
            let itinerary = try await apiClient.generatePlan(tripId: tripId)
            print("✅ fetchRoute: received itinerary with \(itinerary.days.count) days")
            self.itineraryResult = itinerary

            // Ensure minimum animation time has passed
            await ensureMinimumAnimationTime()

            // Complete all animations quickly
            await completeAnimations()

            print("🎉 fetchRoute: setting state to completed")
            state = .completed(itinerary)
        } catch {
            print("❌ Route generation failed: \(error)")
            print("❌ Error type: \(type(of: error))")

            // Stop animations
            animationTimer?.invalidate()
            subtitleTimer?.invalidate()

            if let apiError = error as? APIError, case .paywallRequired = apiError {
                state = .paywallRequired
            } else {
                state = .failed
            }
        }
    }

    private func ensureMinimumAnimationTime() async {
        guard let startTime = animationStartTime else { return }

        let elapsed = Date().timeIntervalSince(startTime)
        if elapsed < minimumAnimationDuration {
            let remaining = minimumAnimationDuration - elapsed
            try? await Task.sleep(nanoseconds: UInt64(remaining * 1_000_000_000))
        }
    }

    private func completeAnimations() async {
        // Show remaining POIs quickly
        while currentPOIIndex < demoPOIs.count {
            addNextPOI()
            try? await Task.sleep(nanoseconds: 30_000_000) // 0.03s
        }

        animationTimer?.invalidate()
        subtitleTimer?.invalidate()
    }

    private func startPOIAnimation() {
        // Add first POI immediately
        addNextPOI()

        // Continue adding POIs every 0.8 seconds
        animationTimer = Timer.scheduledTimer(withTimeInterval: 0.8, repeats: true) { [weak self] _ in
            Task { @MainActor in
                self?.addNextPOI()
            }
        }
    }

    private func addNextPOI() {
        guard currentPOIIndex < demoPOIs.count else {
            animationTimer?.invalidate()
            return
        }

        let poi = demoPOIs[currentPOIIndex]
        visiblePOIs.append(poi)
        latestPOIIndex = currentPOIIndex

        // Add coordinate to route
        routeCoordinates.append(poi.coordinate)

        currentPOIIndex += 1
    }

    private func startSubtitleRotation() {
        subtitleTimer = Timer.scheduledTimer(withTimeInterval: 2.5, repeats: true) { [weak self] _ in
            Task { @MainActor in
                self?.rotateSubtitle()
            }
        }
    }

    private func rotateSubtitle() {
        // Check if we've been loading for too long (>12s)
        if let startTime = animationStartTime,
           Date().timeIntervalSince(startTime) > 12 {
            currentSubtitle = finalizingSubtitle
            return
        }

        subtitleIndex = (subtitleIndex + 1) % subtitles.count
        currentSubtitle = subtitles[subtitleIndex]
    }

    // MARK: - Demo POI Generation

    private static func generateDemoPOIs(around center: CLLocationCoordinate2D) -> [DemoPOI] {
        // Generate realistic-looking POIs around the city center
        let offsets: [(lat: Double, lon: Double, name: String, category: DemoPOI.POICategory)] = [
            (0.008, 0.005, "Historic Center", .attraction),
            (0.003, -0.007, "Local Restaurant", .restaurant),
            (-0.005, 0.010, "City Museum", .attraction),
            (0.012, 0.002, "Gardens", .activity),
            (-0.008, -0.004, "Traditional Cafe", .restaurant),
            (0.001, 0.015, "Main Square", .attraction),
            (-0.010, 0.008, "Art Gallery", .activity),
            (0.006, -0.012, "Evening Dining", .restaurant),
        ]

        return offsets.map { offset in
            DemoPOI(
                coordinate: CLLocationCoordinate2D(
                    latitude: center.latitude + offset.lat,
                    longitude: center.longitude + offset.lon
                ),
                name: offset.name,
                category: offset.category
            )
        }
    }
}
