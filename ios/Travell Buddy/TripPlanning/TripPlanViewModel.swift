//
//  TripPlanViewModel.swift
//  Travell Buddy
//
//  Manages trip plan state and communicates with backend API.
//

import Foundation

final class TripPlanViewModel: ObservableObject {
    enum TripPlanTab {
        case overview
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
    @Published var isShowingPaywall: Bool = false
    @Published var pendingIntent: PendingIntent?

    /// Indicates if this trip was loaded from saved trips
    @Published var isLoadedFromSavedTrip: Bool = false

    /// Indicates if the trip has been modified since loading
    @Published var hasUnsavedChanges: Bool = false

    private let apiClient: TripPlanningAPIClient

    // Store last generation parameters for retry
    private var lastGenerationParams: TripGenerationParams?

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

    /// Refresh itinerary after authentication to unlock full content.
    @MainActor
    func refreshPlanAfterAuth() async -> Bool {
        return await refreshItinerary()
    }

    /// Refresh itinerary from backend (e.g., after day editing in AI Studio).
    @MainActor
    func refreshItinerary() async -> Bool {
        guard let existingPlan = plan else { return false }

        print("🔄 Refreshing itinerary for trip \(existingPlan.tripId)")

        isLoading = true
        defer { isLoading = false }

        do {
            let itinerary = try await apiClient.getItinerary(tripId: existingPlan.tripId.uuidString.lowercased())
            self.plan = itinerary.toTripPlan(using: existingPlan)

            // Mark as having unsaved changes if loaded from saved trip
            if isLoadedFromSavedTrip {
                self.hasUnsavedChanges = true
            }

            print("✅ Itinerary refreshed successfully")
            return true
        } catch {
            print("❌ Failed to refresh itinerary: \(error)")
            self.errorMessage = (error as? LocalizedError)?.errorDescription
                ?? "Не удалось обновить маршрут. Попробуйте ещё раз."
            return false
        }
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
        lastGenerationParams = TripGenerationParams(
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
                travelersCount: travellersCount,
                expectedStartDate: startDate,
                expectedEndDate: endDate
            )

            print("🎉 Trip plan successfully generated!")

        } catch {
            print("❌ Raw error: \(error)")
            print("❌ Error type: \(type(of: error))")
            if let apiError = error as? APIError {
                print("❌ APIError details: \(apiError)")
            }
            if let apiError = error as? APIError, case .paywallRequired = apiError {
                if let params = lastGenerationParams ?? buildParamsFromPlan() {
                    pendingIntent = .generateTrip(params)
                }
                isShowingPaywall = true
            } else {
                self.errorMessage = (error as? LocalizedError)?.errorDescription
                    ?? "Что-то пошло не так. Попробуйте ещё раз."
                print("❌ Error generating plan: \(self.errorMessage ?? "Unknown error")")
            }
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
            self.plan = fullItinerary.toTripPlan(using: currentPlan)

            lastUpdateResult = .success
            print("🎉 Trip plan successfully updated!")
            return true

        } catch {
            let errorMsg = (error as? LocalizedError)?.errorDescription
                ?? "Что-то пошло не так. Попробуйте ещё раз."
            if let apiError = error as? APIError, case .paywallRequired = apiError {
                if let params = lastGenerationParams ?? buildParamsFromPlan() {
                    pendingIntent = .generateTrip(params)
                }
                isShowingPaywall = true
                lastUpdateResult = .failure(errorMsg)
                return false
            } else {
                self.errorMessage = errorMsg
                lastUpdateResult = .failure(errorMsg)
                print("❌ Error updating plan: \(errorMsg)")
                return false
            }
        }
    }

    private func buildParamsFromPlan() -> TripGenerationParams? {
        guard let plan = plan else { return nil }
        let interests = plan.interestsSummary
            .split(separator: ",")
            .map { $0.trimmingCharacters(in: .whitespaces) }
        return TripGenerationParams(
            destinationCity: plan.destinationCity,
            startDate: plan.startDate,
            endDate: plan.endDate,
            selectedInterests: interests,
            budgetLevel: mapComfortToBudget(plan.comfortLevel),
            travellersCount: plan.travellersCount,
            pace: "medium"
        )
    }

    private func mapComfortToBudget(_ comfort: String) -> String {
        switch comfort.lowercased() {
        case "эконом":
            return "low"
        case "премиум":
            return "high"
        default:
            return "medium"
        }
    }

    // MARK: - Local Activity Replacement (UX-only, no backend)

    /// Replace an activity at a specific position with a new one.
    /// This is a local-only operation for the "Replace place" UX flow.
    @MainActor
    func replaceActivity(at dayIndex: Int, activityIndex: Int, with newActivity: TripActivity) {
        guard var currentPlan = plan,
              dayIndex >= 0,
              dayIndex < currentPlan.days.count,
              activityIndex >= 0,
              activityIndex < currentPlan.days[dayIndex].activities.count else {
            return
        }

        // Create a mutable copy of the day's activities
        var updatedActivities = currentPlan.days[dayIndex].activities
        updatedActivities[activityIndex] = newActivity

        // Create a new TripDay with the updated activities
        let updatedDay = TripDay(
            index: currentPlan.days[dayIndex].index,
            date: currentPlan.days[dayIndex].date,
            title: currentPlan.days[dayIndex].title,
            summary: currentPlan.days[dayIndex].summary,
            activities: updatedActivities
        )

        // Create a mutable copy of the days array
        var updatedDays = currentPlan.days
        updatedDays[dayIndex] = updatedDay

        // Create a new TripPlan with the updated days
        let updatedPlan = TripPlan(
            tripId: currentPlan.tripId,
            destinationCity: currentPlan.destinationCity,
            startDate: currentPlan.startDate,
            endDate: currentPlan.endDate,
            days: updatedDays,
            travellersCount: currentPlan.travellersCount,
            comfortLevel: currentPlan.comfortLevel,
            interestsSummary: currentPlan.interestsSummary,
            tripSummary: currentPlan.tripSummary,
            isLocked: currentPlan.isLocked,
            cityPhotoReference: currentPlan.cityPhotoReference
        )

        // Update the plan
        self.plan = updatedPlan

        // Mark as having unsaved changes
        self.hasUnsavedChanges = true

        print("🔄 Activity replaced at day \(dayIndex), position \(activityIndex): \(newActivity.title)")
    }

}
