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
    case failed

    static func == (lhs: RouteBuildingState, rhs: RouteBuildingState) -> Bool {
        switch (lhs, rhs) {
        case (.idle, .idle), (.loading, .loading), (.animating, .animating), (.failed, .failed):
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

    private let tripId: UUID
    private let cityCoordinate: CLLocationCoordinate2D
    private let apiClient: TripPlanningAPIClientProtocol

    private var demoPOIs: [DemoPOI] = []
    private var animationTimer: Timer?
    private var subtitleTimer: Timer?
    private var currentPOIIndex = 0
    private var subtitleIndex = 0
    private var apiTask: Task<Void, Never>?
    private var itineraryResult: ItineraryResponseDTO?
    private var animationStartTime: Date?

    // Minimum animation duration in seconds
    private let minimumAnimationDuration: TimeInterval = 3.0

    private let subtitles = [
        "Анализируем ваши интересы",
        "Подбираем лучшие районы",
        "Оптимизируем маршрут",
        "Добавляем локальные места"
    ]

    private let finalizingSubtitle = "Завершаем построение маршрута…"

    // MARK: - Init

    init(
        tripId: UUID,
        cityCoordinate: CLLocationCoordinate2D,
        apiClient: TripPlanningAPIClientProtocol
    ) {
        self.tripId = tripId
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

    private func fetchRoute() async {
        print("📡 fetchRoute: calling fast-draft API for trip \(tripId)")
        do {
            // Use fast-draft endpoint for p95 < 20s response
            let itinerary = try await apiClient.generateFastDraft(tripId: tripId)
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

            state = .failed
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
            try? await Task.sleep(nanoseconds: 100_000_000) // 0.1s
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
