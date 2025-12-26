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

    @Published var plan: TripPlan?
    @Published var selectedTab: TripPlanTab = .route
    @Published var selectedDayIndex: Int = 0
    @Published var isLoading: Bool = false
    @Published var errorMessage: String?

    private let apiClient: TripPlanningAPIClient

    init(apiClient: TripPlanningAPIClient = .shared) {
        self.apiClient = apiClient
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
        isLoading = true
        errorMessage = nil

        print("🚀 Starting trip plan generation for \(destinationCity)")

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

            isLoading = false
            print("🎉 Trip plan successfully generated!")

        } catch {
            self.errorMessage = (error as? LocalizedError)?.errorDescription ?? error.localizedDescription
            isLoading = false
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

    // MARK: - Mock Generation (Fallback)

    /// Generate mock trip plan (for testing/fallback)
    func generateMockPlan(
        destinationCity: String,
        startDate: Date,
        endDate: Date,
        selectedInterests: [String],
        budgetLevel: String,
        travellersCount: Int
    ) {
        let normalizedInterests = TripPlanViewModel.interestsSummary(from: selectedInterests)
        plan = TripPlan(
            tripId: UUID(), // Generate random UUID for mock plan
            destinationCity: destinationCity,
            startDate: startDate,
            endDate: endDate,
            days: TripPlanViewModel.generateDays(
                startDate: startDate,
                endDate: endDate,
                destinationCity: destinationCity,
                interests: normalizedInterests
            ),
            travellersCount: max(travellersCount, 1),
            comfortLevel: budgetLevel,
            interestsSummary: normalizedInterests
        )
    }
    
    private static func interestsSummary(from interests: [String]) -> String {
        guard !interests.isEmpty else { return "классика, прогулки" }
        return interests
            .map { $0.lowercased() }
            .joined(separator: ", ")
    }
    
    private static func generateDays(startDate: Date, endDate: Date, destinationCity: String, interests: String) -> [TripDay] {
        let calendar = Calendar.current
        let daysCount = max(calendar.dateComponents([.day], from: startDate, to: endDate).day ?? 0, 0) + 1
        return (0..<daysCount).map { index -> TripDay in
            let date = calendar.date(byAdding: .day, value: index, to: startDate) ?? startDate
            return TripDay(
                index: index + 1,
                date: date,
                title: dayTitle(for: index + 1, city: destinationCity),
                summary: daySummary(for: index + 1, interests: interests),
                activities: dayActivities(for: index + 1, city: destinationCity)
            )
        }
    }
    
    private static func dayTitle(for index: Int, city: String) -> String {
        switch index % 3 {
        case 1: return "Знакомство с \(city)"
        case 2: return "Ритм локальных районов"
        default: return "Лучшие виды и вечер"
        }
    }
    
    private static func daySummary(for index: Int, interests: String) -> String {
        "Фокус на интересы: \(interests). День №\(index)."
    }
    
    private static func dayActivities(for index: Int, city: String) -> [TripActivity] {
        let templates: [(String, String, String, TripActivityCategory)] = [
            ("10:00", "Завтрак в Van Kahvalti", "Уютное кафе с лучшими завтраками недалеко от центра.", .food),
            ("11:30", "Прогулка по Галатскому мосту", "Собираем атмосферные виды на Золотой Рог.", .walk),
            ("14:00", "Собор Святой Ирины", "Историческое место с мягким светом и камерной атмосферой.", .museum),
            ("17:30", "Чай в Çinaraltı", "Перерыв на чай у Босфора.", .food),
            ("19:30", "Rooftop-бар Mikla", "Закатный вид на \(city) и авторские коктейли.", .nightlife)
        ]
        return templates.enumerated().map { offset, item in
            TripActivity(
                id: UUID(),
                time: item.0,
                title: item.1,
                description: item.2,
                category: item.3,
                address: nil,
                note: offset == templates.count - 1 ? "Рекомендуется бронирование" : nil
            )
        }
    }
}
