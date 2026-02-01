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
    @Published private(set) var isAnimationComplete: Bool = false  // Signals when to enable full rendering

    // MARK: - Private Properties

    private var tripId: UUID?  // Made optional - will be set after trip creation
    @Published var cityCoordinate: CLLocationCoordinate2D  // Made @Published to update map when backend returns coordinates
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

    // Minimum animation duration in seconds (removed - not needed)
    // private let minimumAnimationDuration: TimeInterval = 1.0

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

        // Start subtitle rotation immediately (shows loading text)
        startSubtitleRotation()

        // Get correct coordinates from backend FIRST, then start animation
        apiTask = Task { @MainActor in
            // Create trip first to get correct city coordinates
            if tripId == nil {
                do {
                    print("📡 Backend: Creating trip to get correct coordinates...")
                    let createdTripId = try await createTrip()
                    tripId = createdTripId
                    print("✅ Backend: Trip created, coordinates updated")
                } catch {
                    print("❌ Backend: Failed to create trip: \(error)")
                    state = .failed
                    return
                }
            }

            // Now start animation with correct coordinates
            print("🗺️ Starting animation with correct city coordinates")
            startPOIAnimation()

            // Generate full route in parallel with animation
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
        isAnimationComplete = false

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
            print("✅ createTrip: demo POIs regenerated around correct coordinates")
        } else {
            print("⚠️ createTrip: backend did not return city coordinates, using fallback")
        }

        print("✅ createTrip: trip created with ID \(tripId)")
        return tripId
    }

    private func fetchRoute() async {
        do {
            // Trip should already be created in startRouteGeneration
            guard let tripId = tripId else {
                throw APIError.networkError(NSError(domain: "No trip ID available", code: -1))
            }

            print("📡 fetchRoute: calling full plan API for trip \(tripId)")

            // Use full plan endpoint with agentic POI Curator + Route Engineer for maximum personalization
            let itinerary = try await apiClient.generatePlan(tripId: tripId)
            print("✅ fetchRoute: received itinerary with \(itinerary.days.count) days")
            self.itineraryResult = itinerary

            // ANIMATION FIX (2026-01-31): Wait for natural animation completion
            // Figure stays active until animation completes
            await waitForAnimationToComplete()

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

    private func waitForAnimationToComplete() async {
        // CRITICAL (2026-01-31): Animation runs INDEPENDENTLY of backend
        // This function waits for animation to finish beautifully
        // Backend already completed (this is called from fetchRoute after generatePlan)

        // Wait until all POIs are shown by the main animation timer
        print("⏳ Waiting for animation to complete (backend already done)...")
        while currentPOIIndex < demoPOIs.count {
            try? await Task.sleep(nanoseconds: 100_000_000) // Check every 0.1s
        }

        print("✅ All 8 POIs shown, keeping figure active for visual appreciation")

        // Give a moment for the last POI animation to settle
        try? await Task.sleep(nanoseconds: 500_000_000) // 0.5s

        // Keep the figure ALIVE and beautiful
        // Timers keep running: dash animation continues, last POI keeps pulsing
        // User sees a complete, active route before transition

        // Show "finalizing" message
        subtitleTimer?.invalidate()
        currentSubtitle = finalizingSubtitle

        // Minimum wait: let user appreciate the beautiful full route
        try? await Task.sleep(nanoseconds: 2_000_000_000) // 2s

        print("🎬 Animation complete, backend ready, transitioning to trip screen")

        // Signal completion and enable full rendering
        isAnimationComplete = true
        animationTimer?.invalidate()
    }

    private func startPOIAnimation() {
        // Add first POI immediately
        addNextPOI()

        // ANIMATION FIX (2026-01-31): SLOW and SMOOTH interval
        // 1.5s between POIs = ~10.5s total for 8 POIs
        // Very smooth, gives camera time to move gracefully
        animationTimer = Timer.scheduledTimer(withTimeInterval: 1.5, repeats: true) { [weak self] _ in
            Task { @MainActor in
                self?.addNextPOI()
            }
        }
    }

    private func addNextPOI() {
        guard currentPOIIndex < demoPOIs.count else {
            // ANIMATION FIX (2026-01-31): Stop timer when all POIs shown
            animationTimer?.invalidate()
            print("✅ All POIs shown (\(demoPOIs.count)), animation timer stopped")
            return
        }

        // PERFORMANCE FIX (2026-01-31): Batch updates to prevent multiple re-renders
        let poi = demoPOIs[currentPOIIndex]

        // Create copies to batch update
        var newVisiblePOIs = visiblePOIs
        newVisiblePOIs.append(poi)

        var newRouteCoordinates = routeCoordinates
        newRouteCoordinates.append(poi.coordinate)

        // Single batched update (triggers one updateUIView instead of three)
        visiblePOIs = newVisiblePOIs
        routeCoordinates = newRouteCoordinates
        latestPOIIndex = currentPOIIndex

        currentPOIIndex += 1

        print("📍 Added POI \(currentPOIIndex)/\(demoPOIs.count): \(poi.name)")
    }

    private func startSubtitleRotation() {
        // ANIMATION FIX (2026-01-31): Slower subtitle rotation for smooth experience
        // 3.0s interval matches the slower, more graceful POI animation (1.5s interval)
        subtitleTimer = Timer.scheduledTimer(withTimeInterval: 3.0, repeats: true) { [weak self] _ in
            Task { @MainActor in
                self?.rotateSubtitle()
            }
        }
    }

    private func rotateSubtitle() {
        // ANIMATION FIX (2026-01-31): Show finalizing after 15s
        // Animation is slow and smooth now (~12s total), so give it more time
        if let startTime = animationStartTime,
           Date().timeIntervalSince(startTime) > 15 {
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
