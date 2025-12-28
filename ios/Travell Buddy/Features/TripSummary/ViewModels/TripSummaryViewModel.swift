//
//  TripSummaryViewModel.swift
//  Travell Buddy
//
//  ViewModel for TripSummaryView that handles weather loading.
//

import Foundation
import CoreLocation

@MainActor
final class TripSummaryViewModel: ObservableObject {

    // MARK: - Published

    @Published var daySummaries: [DaySummary]
    @Published var isLoadingWeather: Bool = false
    @Published var weatherError: String?

    // MARK: - Properties

    let summary: TripSummary
    private let coordinate: CLLocationCoordinate2D?
    private let weatherService: WeatherServiceProtocol

    // MARK: - Init

    init(
        summary: TripSummary,
        coordinate: CLLocationCoordinate2D?,
        weatherService: WeatherServiceProtocol = WeatherService.shared
    ) {
        self.summary = summary
        self.coordinate = coordinate
        self.weatherService = weatherService
        self.daySummaries = summary.daySummaries
    }

    // MARK: - Public Methods

    func loadWeather() async {
        guard let coordinate = coordinate else {
            weatherError = nil
            return
        }

        guard !isLoadingWeather else { return }

        isLoadingWeather = true
        weatherError = nil

        do {
            let dates = daySummaries.map { $0.date }
            let weather = try await weatherService.fetchWeather(for: coordinate, dates: dates)

            // Match weather to day summaries
            let calendar = Calendar.current
            var updatedSummaries = daySummaries

            for (index, daySummary) in updatedSummaries.enumerated() {
                if let dayWeather = weather.first(where: { calendar.isDate($0.date, inSameDayAs: daySummary.date) }) {
                    updatedSummaries[index].weather = dayWeather
                }
            }

            daySummaries = updatedSummaries

        } catch {
            weatherError = error.localizedDescription
        }

        isLoadingWeather = false
    }
}
