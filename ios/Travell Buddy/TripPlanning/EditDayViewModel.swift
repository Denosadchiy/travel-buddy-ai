//
//  EditDayViewModel.swift
//  Travell Buddy
//
//  Holds editing state for adjusting a trip day before regenerating it.
//

import Foundation

enum DayPace: String, CaseIterable, Identifiable {
    case calm
    case medium
    case intense
    
    var id: String { rawValue }
    
    var title: String {
        switch self {
        case .calm: return "Спокойный"
        case .medium: return "Средний"
        case .intense: return "Насыщенный"
        }
    }
}

enum DayAccent: String, CaseIterable, Identifiable {
    case food
    case walks
    case culture
    case shopping
    case nightlife
    case relax
    
    var id: String { rawValue }
    
    var title: String {
        switch self {
        case .food: return "Гастрономия"
        case .walks: return "Прогулки и виды"
        case .culture: return "История и музеи"
        case .shopping: return "Шопинг"
        case .nightlife: return "Ночная жизнь"
        case .relax: return "Спокойный отдых"
        }
    }
}

enum ChangeReason: String, CaseIterable, Identifiable {
    case pace
    case timing
    case tooMuchWalk
    case shiftFocus
    case replacePlaces
    case avoidQueues
    
    var id: String { rawValue }
    
    var title: String {
        switch self {
        case .pace: return "Темп дня"
        case .timing: return "Время начала/окончания"
        case .tooMuchWalk: return "Слишком много ходьбы"
        case .shiftFocus: return "Сместить акценты"
        case .replacePlaces: return "Заменить места"
        case .avoidQueues: return "Убрать очереди"
        }
    }
}

enum EditPlaceStatus: String {
    case keep
    case replace
    case remove
}

enum DayBudgetLevel: String, CaseIterable, Identifiable {
    case low
    case medium
    case high
    
    var id: String { rawValue }
    
    var title: String {
        switch self {
        case .low: return "Экономно"
        case .medium: return "Средне"
        case .high: return "Можно потратить больше"
        }
    }
}

enum PlacePreferenceStatus: String {
    case none
    case mustKeep
    case banned
}

struct EditDayRequest {
    let dayIndex: Int
    let newPace: DayPace
    let startTime: Date
    let endTime: Date
    let accents: [DayAccent]
    let changeReasons: [ChangeReason]
    let replacements: [TripActivity]
    let removals: [TripActivity]
    let requiredPlaceIds: [UUID]
    let bannedPlaceIds: [UUID]
    let budgetLevel: DayBudgetLevel
    let manualMustKeepPlaces: [String]
    let manualBannedPlaces: [String]
    let feedback: String
}

final class EditDayViewModel: ObservableObject {
    let originalDay: TripDay
    let destinationCity: String
    let interestsSummary: String
    
    @Published var pace: DayPace
    @Published var startTime: Date
    @Published var endTime: Date
    @Published var selectedAccents: Set<DayAccent>
    @Published var selectedReasons: Set<ChangeReason> = []
    @Published var placeStatuses: [UUID: EditPlaceStatus]
    @Published var feedbackText: String = ""
    @Published var dayBudgetLevel: DayBudgetLevel
    @Published var placePreferences: [UUID: PlacePreferenceStatus]
    @Published var manualMustKeepPlaces: [String] = []
    @Published var manualBannedPlaces: [String] = []
    
    private let originalPace: DayPace
    private let originalStartTime: Date
    private let originalEndTime: Date
    private let originalAccents: Set<DayAccent>
    private let originalStatuses: [UUID: EditPlaceStatus]
    private let originalBudgetLevel: DayBudgetLevel
    private let originalPreferences: [UUID: PlacePreferenceStatus]
    private let originalManualMustKeep: [String]
    private let originalManualBanned: [String]
    
    init(day: TripDay, destinationCity: String, interestsSummary: String) {
        self.originalDay = day
        self.destinationCity = destinationCity
        self.interestsSummary = interestsSummary
        let defaultPace: DayPace = .medium
        let initialStart = EditDayViewModel.time(from: day.activities.first?.time) ?? EditDayViewModel.defaultStartTime()
        let initialEnd = EditDayViewModel.time(from: day.activities.last?.time) ?? EditDayViewModel.defaultEndTime()
        let defaultAccents: Set<DayAccent> = [.walks]
        let statuses = Dictionary(uniqueKeysWithValues: day.activities.map { ($0.id, EditPlaceStatus.keep) })
        let preferences = Dictionary(uniqueKeysWithValues: day.activities.map { ($0.id, PlacePreferenceStatus.none) })
        self.pace = defaultPace
        self.startTime = initialStart
        self.endTime = initialEnd
        self.selectedAccents = defaultAccents
        self.placeStatuses = statuses
        self.dayBudgetLevel = .medium
        self.placePreferences = preferences
        self.manualMustKeepPlaces = []
        self.manualBannedPlaces = []
        self.originalPace = defaultPace
        self.originalStartTime = initialStart
        self.originalEndTime = initialEnd
        self.originalAccents = defaultAccents
        self.originalStatuses = statuses
        self.originalBudgetLevel = .medium
        self.originalPreferences = preferences
        self.originalManualMustKeep = []
        self.originalManualBanned = []
    }
    
    func toggle(reason: ChangeReason) {
        if selectedReasons.contains(reason) {
            selectedReasons.remove(reason)
        } else {
            selectedReasons.insert(reason)
        }
    }
    
    func select(pace: DayPace) {
        self.pace = pace
    }
    
    func toggle(accent: DayAccent) {
        if selectedAccents.contains(accent) {
            selectedAccents.remove(accent)
        } else {
            selectedAccents.insert(accent)
        }
    }
    
    func status(for activity: TripActivity) -> EditPlaceStatus {
        placeStatuses[activity.id] ?? .keep
    }
    
    func updateStatus(for activity: TripActivity, status: EditPlaceStatus) {
        placeStatuses[activity.id] = status
    }
    
    func preference(for activity: TripActivity) -> PlacePreferenceStatus {
        placePreferences[activity.id] ?? .none
    }
    
    func updatePreference(for activity: TripActivity, status: PlacePreferenceStatus) {
        placePreferences[activity.id] = status
    }
    
    func reset() {
        pace = originalPace
        startTime = originalStartTime
        endTime = originalEndTime
        selectedAccents = originalAccents
        selectedReasons.removeAll()
        placeStatuses = originalStatuses
        feedbackText = ""
        dayBudgetLevel = originalBudgetLevel
        placePreferences = originalPreferences
        manualMustKeepPlaces = originalManualMustKeep
        manualBannedPlaces = originalManualBanned
    }
    
    func buildEditRequest() -> EditDayRequest {
        let replacements = originalDay.activities.filter { status(for: $0) == .replace }
        let removals = originalDay.activities.filter { status(for: $0) == .remove }
        let mustKeep = placePreferences.compactMap { $0.value == .mustKeep ? $0.key : nil }
        let banned = placePreferences.compactMap { $0.value == .banned ? $0.key : nil }
        return EditDayRequest(
            dayIndex: originalDay.index,
            newPace: pace,
            startTime: startTime,
            endTime: endTime,
            accents: Array(selectedAccents),
            changeReasons: Array(selectedReasons),
            replacements: replacements,
            removals: removals,
            requiredPlaceIds: mustKeep,
            bannedPlaceIds: banned,
            budgetLevel: dayBudgetLevel,
            manualMustKeepPlaces: manualMustKeepPlaces,
            manualBannedPlaces: manualBannedPlaces,
            feedback: feedbackText.trimmingCharacters(in: .whitespacesAndNewlines)
        )
    }
    
    func addManualPlace(_ name: String, status: PlacePreferenceStatus) {
        let trimmed = name.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else { return }
        switch status {
        case .mustKeep:
            manualMustKeepPlaces.append(trimmed)
        case .banned:
            manualBannedPlaces.append(trimmed)
        case .none:
            break
        }
    }
    
    func removeManualPlace(at index: Int, status: PlacePreferenceStatus) {
        switch status {
        case .mustKeep:
            guard manualMustKeepPlaces.indices.contains(index) else { return }
            manualMustKeepPlaces.remove(at: index)
        case .banned:
            guard manualBannedPlaces.indices.contains(index) else { return }
            manualBannedPlaces.remove(at: index)
        case .none:
            break
        }
    }
    
    var visiblePlacesCount: Int {
        originalDay.activities.filter { status(for: $0) != .remove }.count
    }
    
    var totalPlacesCount: Int {
        originalDay.activities.count
    }
    
    var dayDurationText: String {
        let formatter = DateFormatter()
        formatter.dateFormat = "HH:mm"
        return "\(formatter.string(from: startTime)) – \(formatter.string(from: endTime))"
    }
    
    var paceText: String {
        pace.title
    }
    
    var budgetText: String {
        dayBudgetLevel.title
    }
    
    private static func time(from string: String?) -> Date? {
        guard let value = string else { return nil }
        let formatter = DateFormatter()
        formatter.locale = Locale(identifier: "ru_RU")
        formatter.dateFormat = "HH:mm"
        return formatter.date(from: value)
    }
    
    private static func defaultStartTime() -> Date {
        Calendar.current.date(bySettingHour: 10, minute: 0, second: 0, of: Date()) ?? Date()
    }
    
    private static func defaultEndTime() -> Date {
        Calendar.current.date(bySettingHour: 22, minute: 0, second: 0, of: Date()) ?? Date()
    }
}
