//
//  CitySearchService.swift
//  Travell Buddy
//
//  City autocomplete service using Apple MapKit (free, worldwide coverage).
//

import Foundation
import MapKit
import Combine

// MARK: - City Result Model

struct CitySearchResult: Identifiable, Equatable {
    let id = UUID()
    let name: String
    let country: String
    let subtitle: String
    let coordinate: CLLocationCoordinate2D?

    // For display
    var displayName: String {
        if country.isEmpty {
            return name
        }
        return "\(name), \(country)"
    }

    static func == (lhs: CitySearchResult, rhs: CitySearchResult) -> Bool {
        lhs.id == rhs.id
    }
}

// MARK: - Search State

enum CitySearchState: Equatable {
    case idle
    case searching
    case results([CitySearchResult])
    case empty
    case error(String)

    static func == (lhs: CitySearchState, rhs: CitySearchState) -> Bool {
        switch (lhs, rhs) {
        case (.idle, .idle), (.searching, .searching), (.empty, .empty):
            return true
        case (.results(let a), .results(let b)):
            return a == b
        case (.error(let a), .error(let b)):
            return a == b
        default:
            return false
        }
    }
}

// MARK: - City Search Service

@MainActor
final class CitySearchService: NSObject, ObservableObject {

    // MARK: - Published

    @Published private(set) var state: CitySearchState = .idle
    @Published private(set) var suggestions: [CitySearchResult] = []

    // MARK: - Private

    private let completer: MKLocalSearchCompleter
    private var searchTask: Task<Void, Never>?
    private var pendingCompletion: MKLocalSearchCompletion?

    // Debounce
    private var debounceTask: Task<Void, Never>?
    private let debounceInterval: TimeInterval = 0.15 // 150ms - быстрее отклик

    // MARK: - Init

    override init() {
        self.completer = MKLocalSearchCompleter()
        super.init()

        completer.delegate = self
        // Filter to cities and addresses only
        completer.resultTypes = .address
        // Search worldwide
        completer.region = MKCoordinateRegion(
            center: CLLocationCoordinate2D(latitude: 0, longitude: 0),
            span: MKCoordinateSpan(latitudeDelta: 180, longitudeDelta: 360)
        )
    }

    // MARK: - Public Methods

    /// Search for cities matching the query
    func search(query: String) {
        let trimmed = query.trimmingCharacters(in: .whitespacesAndNewlines)

        // Cancel previous debounce
        debounceTask?.cancel()

        // Clear if empty
        guard !trimmed.isEmpty else {
            state = .idle
            suggestions = []
            completer.cancel()
            return
        }

        // Require at least 1 character
        guard trimmed.count >= 1 else {
            state = .idle
            suggestions = []
            return
        }

        // Мгновенно показываем результаты из локальной базы
        let localResults = searchOffline(query: trimmed)
        if !localResults.isEmpty {
            suggestions = localResults
            state = .results(localResults)
        } else {
            state = .searching
        }

        // Параллельно запускаем MapKit поиск (без debounce для скорости)
        completer.queryFragment = trimmed
    }

    /// Resolve a search result to get full coordinates
    func resolveCity(_ result: CitySearchResult) async -> CitySearchResult? {
        // If we already have coordinates, return as is
        if result.coordinate != nil {
            return result
        }

        // Use MKLocalSearch to get coordinates
        let request = MKLocalSearch.Request()
        request.naturalLanguageQuery = result.displayName
        request.resultTypes = .address

        let search = MKLocalSearch(request: request)

        do {
            let response = try await search.start()

            guard let mapItem = response.mapItems.first else {
                return result
            }

            let placemark = mapItem.placemark
            let coordinate = placemark.coordinate

            // Extract city and country
            let cityName = placemark.locality ?? placemark.name ?? result.name
            let country = placemark.country ?? result.country

            return CitySearchResult(
                name: cityName,
                country: country,
                subtitle: result.subtitle,
                coordinate: coordinate
            )
        } catch {
            print("Failed to resolve city: \(error)")
            return result
        }
    }

    /// Resolve an MKLocalSearchCompletion to get coordinates
    func resolveCompletion(_ completion: MKLocalSearchCompletion) async -> CitySearchResult? {
        let request = MKLocalSearch.Request(completion: completion)
        request.resultTypes = .address

        let search = MKLocalSearch(request: request)

        do {
            let response = try await search.start()

            guard let mapItem = response.mapItems.first else {
                return nil
            }

            let placemark = mapItem.placemark

            // Extract city name - prefer locality, then name
            let cityName = placemark.locality ?? placemark.name ?? completion.title
            let country = placemark.country ?? ""

            return CitySearchResult(
                name: cityName,
                country: country,
                subtitle: completion.subtitle,
                coordinate: placemark.coordinate
            )
        } catch {
            print("Failed to resolve completion: \(error)")
            return nil
        }
    }

    /// Clear search state
    func clear() {
        debounceTask?.cancel()
        searchTask?.cancel()
        completer.cancel()
        state = .idle
        suggestions = []
    }
}

// MARK: - MKLocalSearchCompleterDelegate

extension CitySearchService: MKLocalSearchCompleterDelegate {

    nonisolated func completerDidUpdateResults(_ completer: MKLocalSearchCompleter) {
        Task { @MainActor in
            let results = completer.results

            // Filter to likely cities (not specific addresses)
            let cityResults = results.filter { completion in
                // Skip results that look like specific addresses (contain numbers)
                let hasNumbers = completion.title.contains(where: { $0.isNumber })
                if hasNumbers { return false }

                // Skip results with very long titles (likely addresses)
                if completion.title.count > 50 { return false }

                return true
            }

            // Convert to CitySearchResult
            let mapped: [CitySearchResult] = cityResults.prefix(8).map { completion in
                // Parse title and subtitle
                // Title is usually the city name
                // Subtitle is usually "Country" or "Region, Country"

                let name = completion.title
                let subtitle = completion.subtitle

                // Try to extract country from subtitle
                let country = extractCountry(from: subtitle)

                return CitySearchResult(
                    name: name,
                    country: country,
                    subtitle: subtitle,
                    coordinate: nil // Will be resolved on selection
                )
            }

            if mapped.isEmpty {
                state = .empty
                suggestions = []
            } else {
                state = .results(mapped)
                suggestions = mapped
            }
        }
    }

    nonisolated func completer(_ completer: MKLocalSearchCompleter, didFailWithError error: Error) {
        Task { @MainActor in
            // Check if it's a cancellation
            if (error as NSError).code == MKError.Code.placemarkNotFound.rawValue {
                state = .empty
            } else {
                state = .error("Не удалось выполнить поиск")
            }
            suggestions = []
        }
    }

    // MARK: - Helpers

    private func extractCountry(from subtitle: String) -> String {
        // Subtitle format is usually "Region, Country" or just "Country"
        let components = subtitle.components(separatedBy: ", ")

        // Last component is usually the country
        if let last = components.last, !last.isEmpty {
            return last
        }

        return subtitle
    }
}

// MARK: - Offline Fallback Database

extension CitySearchService {

    /// Search in local database as fallback
    func searchOffline(query: String) -> [CitySearchResult] {
        let trimmed = query.lowercased().trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else { return [] }

        // Use AirportDatabase as fallback (it has major cities)
        let cities = AirportDatabase.shared.searchCities(query: trimmed)

        return cities.prefix(5).map { city in
            CitySearchResult(
                name: city.cityName,
                country: city.countryName,
                subtitle: city.countryName,
                coordinate: nil
            )
        }
    }

    /// Combined search: MapKit + offline fallback
    func searchWithFallback(query: String) {
        // Start MapKit search
        search(query: query)

        // If no results after timeout, use offline
        Task {
            try? await Task.sleep(nanoseconds: 2_000_000_000) // 2 seconds

            await MainActor.run { [weak self] in
                guard let self = self else { return }

                if case .empty = self.state {
                    let offlineResults = self.searchOffline(query: query)
                    if !offlineResults.isEmpty {
                        self.suggestions = offlineResults
                        self.state = .results(offlineResults)
                    }
                }
            }
        }
    }
}
