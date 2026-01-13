//
//  AIStudioViewModel.swift
//  Travell Buddy
//
//  ViewModel for AI Studio day editing with pending changes tracking.
//

import Foundation
import Combine

// MARK: - Domain Models

enum StudioTempo: String, CaseIterable, Identifiable {
    case low = "low"
    case medium = "medium"
    case high = "high"

    var id: String { rawValue }

    var title: String {
        switch self {
        case .low: return "Низкий"
        case .medium: return "Средний"
        case .high: return "Высокий"
        }
    }

    var icon: String {
        switch self {
        case .low: return "tortoise"
        case .medium: return "figure.walk"
        case .high: return "hare"
        }
    }
}

enum StudioBudget: String, CaseIterable, Identifiable {
    case low = "low"
    case medium = "medium"
    case high = "high"

    var id: String { rawValue }

    var title: String {
        switch self {
        case .low: return "$"
        case .medium: return "$$"
        case .high: return "$$$"
        }
    }
}

enum DayPreset: String, CaseIterable, Identifiable {
    case overview = "overview"
    case food = "food"
    case walks = "walks"
    case avoidCrowds = "avoid_crowds"
    case art = "art"
    case architecture = "architecture"
    case cozy = "cozy"
    case nightlife = "nightlife"

    var id: String { rawValue }

    var title: String {
        switch self {
        case .overview: return "Обзорно"
        case .food: return "Еда"
        case .walks: return "Прогулки"
        case .avoidCrowds: return "Без толп"
        case .art: return "Искусство"
        case .architecture: return "Архитектура"
        case .cozy: return "Уютно"
        case .nightlife: return "Ночная"
        }
    }

    var icon: String {
        switch self {
        case .overview: return "binoculars"
        case .food: return "fork.knife"
        case .walks: return "figure.walk"
        case .avoidCrowds: return "person.2.slash"
        case .art: return "paintpalette"
        case .architecture: return "building.columns"
        case .cozy: return "cup.and.saucer"
        case .nightlife: return "moon.stars"
        }
    }
}

// MARK: - Pending Change Types

enum PendingChangeType: Equatable, Hashable {
    case updateSettings
    case setPreset(DayPreset?)
    case addPlace(placeId: String, placement: PlacePlacement)
    case replacePlace(fromPlaceId: String, toPlaceId: String)
    case removePlace(placeId: String)
    case addWishMessage(text: String)
}

enum PlacePlacement: Equatable, Hashable {
    case auto
    case inSlot(slotIndex: Int)
    case atTime(hour: Int, minute: Int)
}

struct PendingChange: Identifiable, Equatable, Hashable {
    let id: UUID
    let type: PendingChangeType
    let createdAt: Date

    init(type: PendingChangeType) {
        self.id = UUID()
        self.type = type
        self.createdAt = Date()
    }
}

// MARK: - Place Models

struct StudioPlace: Identifiable, Equatable {
    let id: String
    let name: String
    let latitude: Double
    let longitude: Double
    let timeStart: String
    let timeEnd: String
    let category: String
    let rating: Double?
    let priceLevel: Int?
    let photoURL: URL?
    let address: String?
}

struct StudioSearchResult: Identifiable, Equatable {
    let id: String
    let name: String
    let category: String
    let rating: Double?
    let address: String?
    let photoURL: URL?
}

struct WishMessage: Identifiable, Equatable {
    let id: UUID
    let role: MessageRole
    let text: String
    let createdAt: Date

    enum MessageRole: String {
        case user
        case assistant
    }
}

struct DayMetrics: Equatable {
    let distanceKm: Double
    let stepsEstimate: Int
    let placesCount: Int
    let walkingTimeMinutes: Int

    var formattedDistance: String {
        String(format: "%.1f км", distanceKm)
    }

    var formattedSteps: String {
        let formatter = NumberFormatter()
        formatter.numberStyle = .decimal
        formatter.groupingSeparator = " "
        return "\(formatter.string(from: NSNumber(value: stepsEstimate)) ?? "\(stepsEstimate)") шагов"
    }

    var formattedPlaces: String {
        "\(placesCount) мест"
    }
}

// MARK: - Server State

struct DayStudioState: Equatable {
    var places: [StudioPlace]
    var tempo: StudioTempo
    var startTime: Date
    var endTime: Date
    var budget: StudioBudget
    var preset: DayPreset?
    var aiSummary: String
    var metrics: DayMetrics
    var wishes: [WishMessage]
    var revision: Int

    static var empty: DayStudioState {
        DayStudioState(
            places: [],
            tempo: .medium,
            startTime: Calendar.current.date(bySettingHour: 8, minute: 0, second: 0, of: Date()) ?? Date(),
            endTime: Calendar.current.date(bySettingHour: 18, minute: 0, second: 0, of: Date()) ?? Date(),
            budget: .medium,
            preset: nil,
            aiSummary: "",
            metrics: DayMetrics(distanceKm: 0, stepsEstimate: 0, placesCount: 0, walkingTimeMinutes: 0),
            wishes: [],
            revision: 0
        )
    }
}

// MARK: - ViewModel

@MainActor
final class AIStudioViewModel: ObservableObject {
    // MARK: - Published State

    // Server state (source of truth from backend)
    @Published var serverState: DayStudioState = .empty

    // Local editing state
    @Published var tempo: StudioTempo = .medium
    @Published var startTime: Date = Calendar.current.date(bySettingHour: 8, minute: 0, second: 0, of: Date()) ?? Date()
    @Published var endTime: Date = Calendar.current.date(bySettingHour: 18, minute: 0, second: 0, of: Date()) ?? Date()
    @Published var budget: StudioBudget = .medium
    @Published var selectedPreset: DayPreset?

    // Wishes chat
    @Published var wishesThread: [WishMessage] = []
    @Published var wishInputText: String = ""

    // Place management
    @Published var searchQuery: String = ""
    @Published var searchResults: [StudioSearchResult] = []
    @Published var isSearching: Bool = false
    @Published var replacementAlternatives: [String: [StudioSearchResult]] = [:]
    @Published var expandedReplacementPlaceId: String?

    // Pending changes
    @Published var pendingChanges: [PendingChange] = []

    // UI State
    @Published var isLoading: Bool = false
    @Published var isApplying: Bool = false
    @Published var errorMessage: String?

    // MARK: - Properties

    let tripId: UUID
    let dayId: Int
    let cityName: String
    let dayDate: Date

    var dirtyCount: Int {
        pendingChanges.count
    }

    var hasChanges: Bool {
        !pendingChanges.isEmpty
    }

    var timeWindowText: String {
        let formatter = DateFormatter()
        formatter.dateFormat = "HH:mm"
        return "\(formatter.string(from: startTime))–\(formatter.string(from: endTime))"
    }

    var dayDateFormatted: String {
        let formatter = DateFormatter()
        formatter.locale = Locale(identifier: "ru_RU")
        formatter.dateFormat = "d MMMM, EEEE"
        return formatter.string(from: dayDate)
    }

    // MARK: - Init

    init(tripId: UUID, dayId: Int, cityName: String, dayDate: Date) {
        self.tripId = tripId
        self.dayId = dayId
        self.cityName = cityName
        self.dayDate = dayDate
    }

    // MARK: - Load Data

    func loadStudioData() async {
        isLoading = true
        errorMessage = nil

        do {
            let state = try await fetchStudioState()
            serverState = state
            syncLocalStateFromServer()
        } catch {
            errorMessage = "Не удалось загрузить данные: \(error.localizedDescription)"
        }

        isLoading = false
    }

    private func syncLocalStateFromServer() {
        tempo = serverState.tempo
        startTime = serverState.startTime
        endTime = serverState.endTime
        budget = serverState.budget
        selectedPreset = serverState.preset
        wishesThread = serverState.wishes
    }

    // MARK: - Settings Changes

    func updateTempo(_ newTempo: StudioTempo) {
        guard newTempo != tempo else { return }
        tempo = newTempo
        addSettingsChangeIfNeeded()
    }

    func updateStartTime(_ newTime: Date) {
        guard newTime != startTime else { return }
        startTime = newTime
        addSettingsChangeIfNeeded()
    }

    func updateEndTime(_ newTime: Date) {
        guard newTime != endTime else { return }
        endTime = newTime
        addSettingsChangeIfNeeded()
    }

    func updateBudget(_ newBudget: StudioBudget) {
        guard newBudget != budget else { return }
        budget = newBudget
        addSettingsChangeIfNeeded()
    }

    private func addSettingsChangeIfNeeded() {
        // Remove existing settings change and add new one
        pendingChanges.removeAll { change in
            if case .updateSettings = change.type { return true }
            return false
        }

        // Only add if different from server state
        if tempo != serverState.tempo ||
           startTime != serverState.startTime ||
           endTime != serverState.endTime ||
           budget != serverState.budget {
            pendingChanges.append(PendingChange(type: .updateSettings))
        }
    }

    // MARK: - Preset Changes

    func selectPreset(_ preset: DayPreset?) {
        guard preset != selectedPreset else { return }
        selectedPreset = preset

        // Remove existing preset change
        pendingChanges.removeAll { change in
            if case .setPreset = change.type { return true }
            return false
        }

        // Only add if different from server state
        if preset != serverState.preset {
            pendingChanges.append(PendingChange(type: .setPreset(preset)))
        }
    }

    // MARK: - Wishes Chat

    func sendWish() {
        let text = wishInputText.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !text.isEmpty else { return }

        let message = WishMessage(
            id: UUID(),
            role: .user,
            text: text,
            createdAt: Date()
        )
        wishesThread.append(message)
        wishInputText = ""

        pendingChanges.append(PendingChange(type: .addWishMessage(text: text)))
    }

    // MARK: - Place Management

    func searchPlaces() async {
        let query = searchQuery.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !query.isEmpty else {
            searchResults = []
            return
        }

        isSearching = true

        do {
            searchResults = try await performPlaceSearch(query: query)
        } catch {
            searchResults = []
        }

        isSearching = false
    }

    func addPlace(_ result: StudioSearchResult, placement: PlacePlacement) {
        pendingChanges.append(PendingChange(type: .addPlace(placeId: result.id, placement: placement)))
        searchQuery = ""
        searchResults = []
    }

    func toggleReplacement(for placeId: String) {
        if expandedReplacementPlaceId == placeId {
            expandedReplacementPlaceId = nil
        } else {
            expandedReplacementPlaceId = placeId
            Task {
                await loadReplacementAlternatives(for: placeId)
            }
        }
    }

    func replacePlace(from originalId: String, to newId: String) {
        pendingChanges.append(PendingChange(type: .replacePlace(fromPlaceId: originalId, toPlaceId: newId)))
        expandedReplacementPlaceId = nil
    }

    func removePlace(_ placeId: String) {
        pendingChanges.append(PendingChange(type: .removePlace(placeId: placeId)))
    }

    private func loadReplacementAlternatives(for placeId: String) async {
        guard let place = serverState.places.first(where: { $0.id == placeId }) else { return }

        do {
            let alternatives = try await performPlaceSearch(query: place.category)
            replacementAlternatives[placeId] = alternatives.filter { $0.id != placeId }
        } catch {
            replacementAlternatives[placeId] = []
        }
    }

    // MARK: - Apply / Reset

    func applyChanges() async {
        guard hasChanges else { return }

        isApplying = true
        errorMessage = nil

        do {
            let newState = try await submitChanges()
            serverState = newState
            pendingChanges.removeAll()
            syncLocalStateFromServer()
        } catch {
            errorMessage = "Не удалось применить изменения: \(error.localizedDescription)"
        }

        isApplying = false
    }

    func resetChanges() {
        pendingChanges.removeAll()
        syncLocalStateFromServer()
        searchQuery = ""
        searchResults = []
        expandedReplacementPlaceId = nil
        replacementAlternatives = [:]
    }

    // MARK: - Pending Change Helpers

    func isPlacePendingRemoval(_ placeId: String) -> Bool {
        pendingChanges.contains { change in
            if case .removePlace(let id) = change.type {
                return id == placeId
            }
            return false
        }
    }

    func isPlacePendingReplacement(_ placeId: String) -> Bool {
        pendingChanges.contains { change in
            if case .replacePlace(let fromId, _) = change.type {
                return fromId == placeId
            }
            return false
        }
    }

    func pendingReplacementTarget(for placeId: String) -> String? {
        for change in pendingChanges {
            if case .replacePlace(let fromId, let toId) = change.type, fromId == placeId {
                return toId
            }
        }
        return nil
    }

    // MARK: - API Calls

    private let apiClient = TripPlanningAPIClient.shared

    private func fetchStudioState() async throws -> DayStudioState {
        let response = try await apiClient.getDayStudio(tripId: tripId, dayId: dayId)
        return response.toStudioState()
    }

    private func submitChanges() async throws -> DayStudioState {
        let changes = buildChangeDTOs()
        let request = ApplyChangesRequestDTO(
            baseRevision: serverState.revision,
            changes: changes
        )

        let response = try await apiClient.applyDayChanges(
            tripId: tripId,
            dayId: dayId,
            request: request
        )

        return response.toStudioState()
    }

    private func performPlaceSearch(query: String) async throws -> [StudioSearchResult] {
        let request = PlaceSearchRequestDTO(
            query: query,
            city: cityName,
            limit: 10
        )

        let response = try await apiClient.searchPlaces(request: request)
        return response.results.map { $0.toSearchResult() }
    }

    private func buildChangeDTOs() -> [DayChangeDTO] {
        var changes: [DayChangeDTO] = []

        for change in pendingChanges {
            switch change.type {
            case .updateSettings:
                let formatter = DateFormatter()
                formatter.dateFormat = "HH:mm"

                changes.append(DayChangeDTO(
                    type: "update_settings",
                    data: .updateSettings(
                        tempo: tempo.rawValue,
                        startTime: formatter.string(from: startTime),
                        endTime: formatter.string(from: endTime),
                        budget: budget.rawValue
                    )
                ))

            case .setPreset(let preset):
                changes.append(DayChangeDTO(
                    type: "set_preset",
                    data: .setPreset(preset?.rawValue)
                ))

            case .addPlace(let placeId, let placement):
                let placementDTO: PlacementDTO
                switch placement {
                case .auto:
                    placementDTO = .auto
                case .inSlot(let index):
                    placementDTO = .inSlot(index)
                case .atTime(let hour, let minute):
                    placementDTO = .atTime(hour: hour, minute: minute)
                }

                changes.append(DayChangeDTO(
                    type: "add_place",
                    data: .addPlace(placeId: placeId, placement: placementDTO)
                ))

            case .replacePlace(let fromId, let toId):
                changes.append(DayChangeDTO(
                    type: "replace_place",
                    data: .replacePlace(from: fromId, to: toId)
                ))

            case .removePlace(let placeId):
                changes.append(DayChangeDTO(
                    type: "remove_place",
                    data: .removePlace(placeId)
                ))

            case .addWishMessage(let text):
                changes.append(DayChangeDTO(
                    type: "add_wish_message",
                    data: .addWish(text)
                ))
            }
        }

        return changes
    }
}
