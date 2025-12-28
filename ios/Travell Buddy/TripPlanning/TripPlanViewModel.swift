//
//  TripPlanViewModel.swift
//  Travell Buddy
//
//  Manages trip plan state and communicates with backend API.
//

import Foundation

final class TripPlanViewModel: ObservableObject {
    enum TripPlanTab {
        case route
        case map
    }

    /// Result of last plan update attempt (for chat rebuild)
    enum UpdateResult {
        case none
        case success
        case failure(String)
    }

    @Published var plan: TripPlan?
    @Published var selectedTab: TripPlanTab = .route
    @Published var selectedDayIndex: Int = 0
    @Published var isLoading: Bool = false
    @Published var errorMessage: String?
    @Published var lastUpdateResult: UpdateResult = .none

    private let apiClient: TripPlanningAPIClient

    // Store last generation parameters for retry
    private var lastGenerationParams: GenerationParams?

    struct GenerationParams {
        let destinationCity: String
        let startDate: Date
        let endDate: Date
        let selectedInterests: [String]
        let budgetLevel: String
        let travellersCount: Int
        let pace: String
    }

    init(apiClient: TripPlanningAPIClient = .shared) {
        self.apiClient = apiClient
    }

    /// Whether an error is currently displayed
    var hasError: Bool {
        errorMessage != nil
    }

    /// Clear current error
    func clearError() {
        errorMessage = nil
    }

    /// Retry last failed generation
    @MainActor
    func retryLastGeneration() async {
        guard let params = lastGenerationParams else { return }
        await generatePlan(
            destinationCity: params.destinationCity,
            startDate: params.startDate,
            endDate: params.endDate,
            selectedInterests: params.selectedInterests,
            budgetLevel: params.budgetLevel,
            travellersCount: params.travellersCount,
            pace: params.pace
        )
    }

    // MARK: - Computed Properties

    /// Currently selected day from the plan
    var currentDay: TripDay? {
        guard let plan = plan,
              selectedDayIndex >= 0,
              selectedDayIndex < plan.days.count else { return nil }
        return plan.days[selectedDayIndex]
    }

    /// Activities for the currently selected day
    var currentDayActivities: [TripActivity] {
        currentDay?.activities ?? []
    }

    /// Activities with valid coordinates for the currently selected day
    var currentDayActivitiesWithCoordinates: [TripActivity] {
        currentDayActivities.filter { $0.hasCoordinates }
    }

    // MARK: - Backend Integration

    /// Generate trip plan using backend API
    @MainActor
    func generatePlan(
        destinationCity: String,
        startDate: Date,
        endDate: Date,
        selectedInterests: [String],
        budgetLevel: String,
        travellersCount: Int,
        pace: String = "medium"
    ) async {
        // Store parameters for potential retry
        lastGenerationParams = GenerationParams(
            destinationCity: destinationCity,
            startDate: startDate,
            endDate: endDate,
            selectedInterests: selectedInterests,
            budgetLevel: budgetLevel,
            travellersCount: travellersCount,
            pace: pace
        )

        isLoading = true
        errorMessage = nil

        defer { isLoading = false }

        print("🚀 Starting trip plan generation for \(destinationCity)")
        print("🔧 API Client: \(type(of: apiClient))")
        print("🔧 Base URL: \(AppConfig.baseURL)")

        do {
            // 1. Create trip request DTO
            let tripRequest = buildTripRequest(
                city: destinationCity,
                startDate: startDate,
                endDate: endDate,
                travelers: travellersCount,
                interests: selectedInterests,
                budget: budgetLevel,
                pace: pace
            )

            // 2. Create trip
            print("📝 Creating trip...")
            let tripResponse = try await apiClient.createTrip(tripRequest)
            print("✅ Trip created with ID: \(tripResponse.id)")

            // 3. Generate plan
            print("🗺️ Generating itinerary...")
            let itinerary = try await apiClient.planTrip(tripId: tripResponse.id)
            print("✅ Plan generated with \(itinerary.days.count) days")

            // 4. Fetch complete itinerary
            print("📋 Fetching complete itinerary...")
            let fullItinerary = try await apiClient.getItinerary(tripId: tripResponse.id)
            print("✅ Full itinerary fetched")

            // 5. Convert to TripPlan
            self.plan = fullItinerary.toTripPlan(
                destinationCity: destinationCity,
                budget: budgetLevel,
                interests: selectedInterests,
                travelersCount: travellersCount
            )

            print("🎉 Trip plan successfully generated!")

        } catch {
            print("❌ Raw error: \(error)")
            print("❌ Error type: \(type(of: error))")
            if let apiError = error as? APIError {
                print("❌ APIError details: \(apiError)")
            }
            self.errorMessage = (error as? LocalizedError)?.errorDescription
                ?? "Что-то пошло не так. Попробуйте ещё раз."
            print("❌ Error generating plan: \(self.errorMessage ?? "Unknown error")")
        }
    }

    private func buildTripRequest(
        city: String,
        startDate: Date,
        endDate: Date,
        travelers: Int,
        interests: [String],
        budget: String,
        pace: String
    ) -> TripCreateRequestDTO {
        let dateFormatter = DateFormatter()
        dateFormatter.dateFormat = "yyyy-MM-dd"

        // Map budget level from Russian to backend format
        let backendBudget = mapBudgetToBackend(budget)

        return TripCreateRequestDTO(
            city: city,
            startDate: dateFormatter.string(from: startDate),
            endDate: dateFormatter.string(from: endDate),
            numTravelers: max(travelers, 1),
            pace: pace,
            budget: backendBudget,
            interests: interests,
            dailyRoutine: nil,  // Use backend defaults
            hotelLocation: nil,
            additionalPreferences: nil
        )
    }

    private func mapBudgetToBackend(_ budget: String) -> String {
        switch budget {
        case "Эконом":
            return "low"
        case "Премиум":
            return "high"
        default:
            return "medium"
        }
    }

    /// Update plan from chat (re-run planning pipeline for existing trip)
    /// Returns true if update succeeded, false otherwise
    @MainActor
    func updatePlanFromChat() async -> Bool {
        guard let currentPlan = plan else {
            errorMessage = "Нет активного маршрута для обновления"
            lastUpdateResult = .failure("Нет активного маршрута для обновления")
            return false
        }

        isLoading = true
        errorMessage = nil
        lastUpdateResult = .none

        defer { isLoading = false }

        print("🔄 Updating trip plan for trip: \(currentPlan.tripId)")

        do {
            // 1. Re-run planning pipeline for the same trip
            print("🗺️ Re-generating itinerary...")
            let tripIdString = currentPlan.tripId.uuidString
            let itinerary = try await apiClient.planTrip(tripId: tripIdString)
            print("✅ Plan regenerated with \(itinerary.days.count) days")

            // 2. Fetch complete updated itinerary
            print("📋 Fetching updated itinerary...")
            let fullItinerary = try await apiClient.getItinerary(tripId: tripIdString)
            print("✅ Full itinerary fetched")

            // 3. Convert to TripPlan (preserve existing metadata)
            self.plan = fullItinerary.toTripPlan(
                destinationCity: currentPlan.destinationCity,
                budget: currentPlan.comfortLevel,
                interests: currentPlan.interestsSummary.components(separatedBy: ", "),
                travelersCount: currentPlan.travellersCount
            )

            lastUpdateResult = .success
            print("🎉 Trip plan successfully updated!")
            return true

        } catch {
            let errorMsg = (error as? LocalizedError)?.errorDescription
                ?? "Что-то пошло не так. Попробуйте ещё раз."
            self.errorMessage = errorMsg
            lastUpdateResult = .failure(errorMsg)
            print("❌ Error updating plan: \(errorMsg)")
            return false
        }
    }

}
