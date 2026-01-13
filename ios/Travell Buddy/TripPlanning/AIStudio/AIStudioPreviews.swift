//
//  AIStudioPreviews.swift
//  Travell Buddy
//
//  Preview cases for AI Studio screen demonstrating different states.
//

import SwiftUI

// MARK: - Preview View Models

extension AIStudioViewModel {
    /// Creates a preview ViewModel with mock data loaded
    @MainActor
    static func makePreview(
        places: [StudioPlace] = AIStudioPreviewData.mockPlaces,
        tempo: StudioTempo = .medium,
        budget: StudioBudget = .medium,
        preset: DayPreset? = nil,
        pendingChanges: [PendingChange] = [],
        wishes: [WishMessage] = []
    ) -> AIStudioViewModel {
        let vm = AIStudioViewModel(
            tripId: UUID(),
            dayId: 1,
            cityName: "Париж",
            dayDate: Date()
        )

        // Set server state via internal method
        vm.setPreviewState(
            places: places,
            tempo: tempo,
            budget: budget,
            preset: preset,
            wishes: wishes,
            pendingChanges: pendingChanges
        )

        return vm
    }

    /// Internal method for setting preview state
    @MainActor
    func setPreviewState(
        places: [StudioPlace],
        tempo: StudioTempo,
        budget: StudioBudget,
        preset: DayPreset?,
        wishes: [WishMessage],
        pendingChanges: [PendingChange]
    ) {
        self.serverState = DayStudioState(
            places: places,
            tempo: tempo,
            startTime: Calendar.current.date(bySettingHour: 8, minute: 0, second: 0, of: Date())!,
            endTime: Calendar.current.date(bySettingHour: 18, minute: 0, second: 0, of: Date())!,
            budget: budget,
            preset: preset,
            aiSummary: AIStudioPreviewData.mockSummary,
            metrics: DayMetrics(distanceKm: 8.4, stepsEstimate: 12500, placesCount: places.count, walkingTimeMinutes: 95),
            wishes: wishes,
            revision: 1
        )

        self.tempo = tempo
        self.budget = budget
        self.selectedPreset = preset
        self.wishesThread = wishes
        self.pendingChanges = pendingChanges
    }
}

// MARK: - Preview Data

enum AIStudioPreviewData {
    static let mockPlaces: [StudioPlace] = [
        StudioPlace(
            id: "place_1",
            name: "Café de Flore",
            latitude: 48.8540,
            longitude: 2.3325,
            timeStart: "08:00",
            timeEnd: "09:30",
            category: "cafe",
            rating: 4.3,
            priceLevel: 2,
            photoURL: nil,
            address: "172 Boulevard Saint-Germain"
        ),
        StudioPlace(
            id: "place_2",
            name: "Musée du Louvre",
            latitude: 48.8606,
            longitude: 2.3376,
            timeStart: "10:00",
            timeEnd: "13:00",
            category: "museum",
            rating: 4.8,
            priceLevel: 2,
            photoURL: nil,
            address: "Rue de Rivoli"
        ),
        StudioPlace(
            id: "place_3",
            name: "Le Comptoir du Panthéon",
            latitude: 48.8462,
            longitude: 2.3461,
            timeStart: "13:30",
            timeEnd: "15:00",
            category: "restaurant",
            rating: 4.5,
            priceLevel: 2,
            photoURL: nil,
            address: "1 Rue Soufflot"
        ),
        StudioPlace(
            id: "place_4",
            name: "Jardin du Luxembourg",
            latitude: 48.8462,
            longitude: 2.3371,
            timeStart: "15:30",
            timeEnd: "17:00",
            category: "park",
            rating: 4.7,
            priceLevel: 0,
            photoURL: nil,
            address: "6th arrondissement"
        )
    ]

    static let mockSummary = "Добрый утренний кофе в классическом Café de Flore, затем погружение в мировое искусство в Лувре. После обеда в уютном Le Comptoir — неспешная прогулка по Люксембургскому саду. Сбалансированный день с акцентом на культуру."

    static let mockWishes: [WishMessage] = [
        WishMessage(id: UUID(), role: .user, text: "Хочу больше кафе с видом", createdAt: Date()),
        WishMessage(id: UUID(), role: .assistant, text: "Учту ваше пожелание при пересборке маршрута.", createdAt: Date())
    ]
}

// MARK: - Preview Cases

#Preview("1. No Changes (N=0)") {
    NavigationStack {
        AIStudioView(
            viewModel: .makePreview()
        )
    }
}

#Preview("2. Settings Changed") {
    NavigationStack {
        AIStudioView(
            viewModel: .makePreview(
                tempo: .low,
                budget: .high,
                pendingChanges: [
                    PendingChange(type: .updateSettings)
                ]
            )
        )
    }
}

#Preview("3. Preset Selected") {
    NavigationStack {
        AIStudioView(
            viewModel: .makePreview(
                preset: .food,
                pendingChanges: [
                    PendingChange(type: .setPreset(.food))
                ]
            )
        )
    }
}

#Preview("4. Multiple Changes") {
    NavigationStack {
        AIStudioView(
            viewModel: .makePreview(
                tempo: .high,
                budget: .low,
                preset: .walks,
                pendingChanges: [
                    PendingChange(type: .updateSettings),
                    PendingChange(type: .setPreset(.walks)),
                    PendingChange(type: .addWishMessage(text: "Больше парков"))
                ],
                wishes: [
                    WishMessage(id: UUID(), role: .user, text: "Больше парков", createdAt: Date())
                ]
            )
        )
    }
}

#Preview("5. Place Pending Add") {
    NavigationStack {
        AIStudioView(
            viewModel: .makePreview(
                pendingChanges: [
                    PendingChange(type: .addPlace(placeId: "new_place", placement: .auto))
                ]
            )
        )
    }
}

#Preview("6. Place Pending Replace") {
    NavigationStack {
        AIStudioView(
            viewModel: .makePreview(
                pendingChanges: [
                    PendingChange(type: .replacePlace(fromPlaceId: "place_1", toPlaceId: "alt_1"))
                ]
            )
        )
    }
}

#Preview("7. With Wishes Chat") {
    NavigationStack {
        AIStudioView(
            viewModel: .makePreview(
                pendingChanges: [],
                wishes: AIStudioPreviewData.mockWishes
            )
        )
    }
}

#Preview("8. Complex State") {
    NavigationStack {
        AIStudioView(
            viewModel: .makePreview(
                tempo: .low,
                budget: .high,
                preset: .cozy,
                pendingChanges: [
                    PendingChange(type: .updateSettings),
                    PendingChange(type: .setPreset(.cozy)),
                    PendingChange(type: .removePlace(placeId: "place_2"))
                ],
                wishes: [
                    WishMessage(id: UUID(), role: .user, text: "Без толп пожалуйста", createdAt: Date()),
                    WishMessage(id: UUID(), role: .user, text: "И побольше кофеен", createdAt: Date())
                ]
            )
        )
    }
}

// MARK: - Component Previews

#Preview("Component: Tempo Chips") {
    HStack(spacing: 8) {
        ForEach(StudioTempo.allCases) { tempo in
            StudioChip(
                title: tempo.title,
                icon: tempo.icon,
                isSelected: tempo == .medium
            ) {}
        }
    }
    .padding()
    .background(Color(red: 0.10, green: 0.08, blue: 0.06))
}

#Preview("Component: Preset Buttons") {
    LazyVGrid(columns: [
        GridItem(.flexible()),
        GridItem(.flexible()),
        GridItem(.flexible()),
        GridItem(.flexible())
    ], spacing: 10) {
        ForEach(DayPreset.allCases) { preset in
            StudioPresetButton(
                preset: preset,
                isSelected: preset == .food
            ) {}
        }
    }
    .padding()
    .background(Color(red: 0.10, green: 0.08, blue: 0.06))
}

#Preview("Component: Wish Bubble") {
    VStack(spacing: 8) {
        WishBubble(message: WishMessage(id: UUID(), role: .user, text: "Хочу больше кафе с видом на реку", createdAt: Date()))
        WishBubble(message: WishMessage(id: UUID(), role: .assistant, text: "Учту ваше пожелание при формировании маршрута.", createdAt: Date()))
    }
    .padding()
    .background(Color(red: 0.10, green: 0.08, blue: 0.06))
}

#Preview("Component: Place Card") {
    PlaceReplaceCard(
        place: AIStudioPreviewData.mockPlaces[0],
        isPendingRemoval: false,
        isPendingReplacement: false,
        isExpanded: false,
        alternatives: [],
        onToggleExpand: {},
        onReplace: { _ in },
        onRemove: {}
    )
    .padding()
    .background(Color(red: 0.10, green: 0.08, blue: 0.06))
}

#Preview("Component: Place Card (Expanded)") {
    PlaceReplaceCard(
        place: AIStudioPreviewData.mockPlaces[0],
        isPendingRemoval: false,
        isPendingReplacement: false,
        isExpanded: true,
        alternatives: [
            StudioSearchResult(id: "alt_1", name: "Les Deux Magots", category: "cafe", rating: 4.2, address: "6 Place Saint-Germain", photoURL: nil),
            StudioSearchResult(id: "alt_2", name: "Café de la Paix", category: "cafe", rating: 4.4, address: "5 Place de l'Opéra", photoURL: nil)
        ],
        onToggleExpand: {},
        onReplace: { _ in },
        onRemove: {}
    )
    .padding()
    .background(Color(red: 0.10, green: 0.08, blue: 0.06))
}

#Preview("Component: Place Card (Pending Removal)") {
    PlaceReplaceCard(
        place: AIStudioPreviewData.mockPlaces[0],
        isPendingRemoval: true,
        isPendingReplacement: false,
        isExpanded: false,
        alternatives: [],
        onToggleExpand: {},
        onReplace: { _ in },
        onRemove: {}
    )
    .padding()
    .background(Color(red: 0.10, green: 0.08, blue: 0.06))
}

#Preview("Component: Place Card (Pending Replace)") {
    PlaceReplaceCard(
        place: AIStudioPreviewData.mockPlaces[0],
        isPendingRemoval: false,
        isPendingReplacement: true,
        isExpanded: false,
        alternatives: [],
        onToggleExpand: {},
        onReplace: { _ in },
        onRemove: {}
    )
    .padding()
    .background(Color(red: 0.10, green: 0.08, blue: 0.06))
}
