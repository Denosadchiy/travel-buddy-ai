//
//  AIStudioView.swift
//  Travell Buddy
//
//  AI Studio screen for editing a single day's route.
//  Premium dark glass UI with pending changes tracking.
//

import SwiftUI

struct AIStudioView: View {
    @StateObject var viewModel: AIStudioViewModel
    @Environment(\.dismiss) private var dismiss

    @State private var isShowingStartTimePicker = false
    @State private var isShowingEndTimePicker = false
    @State private var isShowingFullChat = false

    var body: some View {
        ZStack {
            backgroundGradient.ignoresSafeArea()

            if viewModel.isLoading {
                loadingView
            } else if let error = viewModel.errorMessage {
                errorView(error)
            } else {
                mainContent
            }
        }
        .navigationBarHidden(true)
        .task {
            await viewModel.loadStudioData()
        }
        .sheet(isPresented: $isShowingStartTimePicker) {
            timePickerSheet(title: "Начало дня", time: Binding(
                get: { viewModel.startTime },
                set: { viewModel.updateStartTime($0) }
            ))
        }
        .sheet(isPresented: $isShowingEndTimePicker) {
            timePickerSheet(title: "Конец дня", time: Binding(
                get: { viewModel.endTime },
                set: { viewModel.updateEndTime($0) }
            ))
        }
    }

    // MARK: - Background

    private var backgroundGradient: some View {
        ZStack {
            LinearGradient(
                colors: [
                    Color(red: 0.10, green: 0.08, blue: 0.06),
                    Color(red: 0.06, green: 0.04, blue: 0.03)
                ],
                startPoint: .top,
                endPoint: .bottom
            )
            Image("noise")
                .resizable(resizingMode: .tile)
                .opacity(0.04)
                .blendMode(.softLight)
        }
    }

    // MARK: - Loading / Error

    private var loadingView: some View {
        VStack(spacing: 16) {
            ProgressView()
                .scaleEffect(1.4)
                .tint(.orange)
            Text("Загружаю AI-Студию...")
                .font(.system(size: 15, weight: .medium))
                .foregroundColor(.white.opacity(0.7))
        }
    }

    private func errorView(_ message: String) -> some View {
        VStack(spacing: 16) {
            Image(systemName: "exclamationmark.triangle.fill")
                .font(.system(size: 44))
                .foregroundColor(.orange)
            Text("Ошибка")
                .font(.system(size: 20, weight: .semibold))
                .foregroundColor(.white)
            Text(message)
                .font(.system(size: 13))
                .foregroundColor(.white.opacity(0.7))
                .multilineTextAlignment(.center)
                .padding(.horizontal, 40)
            Button("Повторить") {
                Task {
                    await viewModel.loadStudioData()
                }
            }
            .buttonStyle(StudioPrimaryButtonStyle())
        }
    }

    // MARK: - Main Content

    private var mainContent: some View {
        VStack(spacing: 0) {
            headerBar

            ScrollView(.vertical, showsIndicators: false) {
                VStack(spacing: 16) {
                    dayCard
                    metricsRow
                    dayParametersSection
                    presetsSection
                    wishesSection
                    placeManagementSection
                }
                .padding(.horizontal, 16)
                .padding(.top, 8)
                .padding(.bottom, 120)
            }

            Spacer(minLength: 0)
        }
        .safeAreaInset(edge: .bottom, spacing: 0) {
            bottomCTA
        }
    }

    // MARK: - Header

    private var headerBar: some View {
        HStack(spacing: 12) {
            Button {
                dismiss()
            } label: {
                Image(systemName: "chevron.left")
                    .font(.system(size: 16, weight: .semibold))
                    .foregroundColor(.white)
                    .frame(width: 40, height: 40)
                    .background(Color.white.opacity(0.1), in: Circle())
            }

            Text("AI-Студия")
                .font(.system(size: 20, weight: .bold, design: .rounded))
                .foregroundColor(.white)

            Spacer()

            Menu {
                Button("Сбросить все", role: .destructive) {
                    viewModel.resetChanges()
                }
            } label: {
                Image(systemName: "ellipsis")
                    .font(.system(size: 16, weight: .semibold))
                    .foregroundColor(.white)
                    .frame(width: 40, height: 40)
                    .background(Color.white.opacity(0.1), in: Circle())
            }
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 12)
    }

    // MARK: - Day Card

    private var dayCard: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack {
                VStack(alignment: .leading, spacing: 4) {
                    Text("\(viewModel.cityName) · День \(viewModel.dayId)")
                        .font(.system(size: 22, weight: .bold, design: .rounded))
                        .foregroundColor(.white)

                    Text("\(viewModel.dayDateFormatted) · \(viewModel.timeWindowText)")
                        .font(.system(size: 13, weight: .medium))
                        .foregroundColor(.white.opacity(0.6))
                }
                Spacer()
            }

            if !viewModel.serverState.aiSummary.isEmpty {
                Text(viewModel.serverState.aiSummary)
                    .font(.system(size: 14))
                    .foregroundColor(.white.opacity(0.8))
                    .lineLimit(4)
                    .padding(.top, 4)
            }
        }
        .padding(18)
        .background(glassCard)
    }

    // MARK: - Metrics Row

    private var metricsRow: some View {
        HStack(spacing: 10) {
            metricPill(icon: "map", text: viewModel.serverState.metrics.formattedDistance)
            metricPill(icon: "figure.walk", text: viewModel.serverState.metrics.formattedSteps)
            metricPill(icon: "mappin.circle", text: viewModel.serverState.metrics.formattedPlaces)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    private func metricPill(icon: String, text: String) -> some View {
        HStack(spacing: 6) {
            Image(systemName: icon)
                .font(.system(size: 12, weight: .semibold))
                .foregroundColor(.orange)
            Text(text)
                .font(.system(size: 12, weight: .semibold))
                .foregroundColor(.white.opacity(0.9))
        }
        .padding(.horizontal, 12)
        .padding(.vertical, 8)
        .background(
            Capsule()
                .fill(Color.white.opacity(0.08))
                .background(.ultraThinMaterial, in: Capsule())
        )
    }

    // MARK: - Day Parameters

    private var dayParametersSection: some View {
        StudioSectionCard(title: "Параметры дня") {
            VStack(spacing: 16) {
                // Tempo
                VStack(alignment: .leading, spacing: 10) {
                    Text("Темп")
                        .font(.system(size: 13, weight: .semibold))
                        .foregroundColor(.white.opacity(0.6))

                    HStack(spacing: 8) {
                        ForEach(StudioTempo.allCases) { tempo in
                            StudioChip(
                                title: tempo.title,
                                icon: tempo.icon,
                                isSelected: viewModel.tempo == tempo
                            ) {
                                viewModel.updateTempo(tempo)
                            }
                        }
                    }
                }

                Divider().background(Color.white.opacity(0.1))

                // Time
                VStack(alignment: .leading, spacing: 10) {
                    Text("Время")
                        .font(.system(size: 13, weight: .semibold))
                        .foregroundColor(.white.opacity(0.6))

                    HStack(spacing: 12) {
                        StudioTimeButton(
                            label: "Начало",
                            time: viewModel.startTime
                        ) {
                            isShowingStartTimePicker = true
                        }

                        StudioTimeButton(
                            label: "Конец",
                            time: viewModel.endTime
                        ) {
                            isShowingEndTimePicker = true
                        }
                    }
                }

                Divider().background(Color.white.opacity(0.1))

                // Budget
                VStack(alignment: .leading, spacing: 10) {
                    Text("Бюджет")
                        .font(.system(size: 13, weight: .semibold))
                        .foregroundColor(.white.opacity(0.6))

                    HStack(spacing: 8) {
                        ForEach(StudioBudget.allCases) { budget in
                            StudioChip(
                                title: budget.title,
                                isSelected: viewModel.budget == budget
                            ) {
                                viewModel.updateBudget(budget)
                            }
                        }
                    }
                }
            }
        }
    }

    // MARK: - Presets

    private var presetsSection: some View {
        StudioSectionCard(title: "Сделай день таким") {
            LazyVGrid(columns: [
                GridItem(.flexible()),
                GridItem(.flexible()),
                GridItem(.flexible()),
                GridItem(.flexible())
            ], spacing: 10) {
                ForEach(DayPreset.allCases) { preset in
                    StudioPresetButton(
                        preset: preset,
                        isSelected: viewModel.selectedPreset == preset
                    ) {
                        if viewModel.selectedPreset == preset {
                            viewModel.selectPreset(nil)
                        } else {
                            viewModel.selectPreset(preset)
                        }
                    }
                }
            }
        }
    }

    // MARK: - Wishes Chat

    private var wishesSection: some View {
        StudioSectionCard(title: "Чат пожеланий") {
            VStack(spacing: 12) {
                // Recent messages
                if !viewModel.wishesThread.isEmpty {
                    VStack(alignment: .leading, spacing: 8) {
                        ForEach(viewModel.wishesThread.suffix(3)) { message in
                            WishBubble(message: message)
                        }
                    }
                }

                // Input
                HStack(spacing: 10) {
                    TextField("Хочу больше кафе...", text: $viewModel.wishInputText)
                        .font(.system(size: 14))
                        .foregroundColor(.white)
                        .padding(.horizontal, 14)
                        .padding(.vertical, 12)
                        .background(
                            RoundedRectangle(cornerRadius: 12, style: .continuous)
                                .fill(Color.white.opacity(0.08))
                        )
                        .tint(.orange)

                    Button {
                        viewModel.sendWish()
                    } label: {
                        Image(systemName: "arrow.up.circle.fill")
                            .font(.system(size: 32))
                            .foregroundColor(viewModel.wishInputText.isEmpty ? .white.opacity(0.3) : .orange)
                    }
                    .disabled(viewModel.wishInputText.isEmpty)
                }

                // Full chat button
                Button {
                    isShowingFullChat = true
                } label: {
                    Text("Открыть чат полностью")
                        .font(.system(size: 13, weight: .medium))
                        .foregroundColor(.orange)
                }
            }
        }
    }

    // MARK: - Place Management

    private var placeManagementSection: some View {
        VStack(spacing: 16) {
            // Add Place
            StudioSectionCard(title: "Добавить место") {
                VStack(spacing: 12) {
                    // Search input
                    HStack(spacing: 10) {
                        Image(systemName: "magnifyingglass")
                            .font(.system(size: 14, weight: .medium))
                            .foregroundColor(.white.opacity(0.5))

                        TextField("Поиск мест...", text: $viewModel.searchQuery)
                            .font(.system(size: 14))
                            .foregroundColor(.white)
                            .tint(.orange)
                            .onSubmit {
                                Task {
                                    await viewModel.searchPlaces()
                                }
                            }
                    }
                    .padding(.horizontal, 14)
                    .padding(.vertical, 12)
                    .background(
                        RoundedRectangle(cornerRadius: 12, style: .continuous)
                            .fill(Color.white.opacity(0.08))
                    )

                    // Search results
                    if viewModel.isSearching {
                        ProgressView()
                            .tint(.orange)
                            .padding(.vertical, 8)
                    } else if !viewModel.searchResults.isEmpty {
                        VStack(spacing: 8) {
                            ForEach(viewModel.searchResults) { result in
                                SearchResultCard(result: result) { placement in
                                    viewModel.addPlace(result, placement: placement)
                                }
                            }
                        }
                    }
                }
            }

            // Replace Place
            StudioSectionCard(title: "Заменить место") {
                VStack(spacing: 10) {
                    ForEach(viewModel.serverState.places) { place in
                        PlaceReplaceCard(
                            place: place,
                            isPendingRemoval: viewModel.isPlacePendingRemoval(place.id),
                            isPendingReplacement: viewModel.isPlacePendingReplacement(place.id),
                            isExpanded: viewModel.expandedReplacementPlaceId == place.id,
                            alternatives: viewModel.replacementAlternatives[place.id] ?? [],
                            onToggleExpand: {
                                viewModel.toggleReplacement(for: place.id)
                            },
                            onReplace: { newId in
                                viewModel.replacePlace(from: place.id, to: newId)
                            },
                            onRemove: {
                                viewModel.removePlace(place.id)
                            }
                        )
                    }
                }
            }
        }
    }

    // MARK: - Bottom CTA

    private var bottomCTA: some View {
        VStack(spacing: 12) {
            Button {
                Task {
                    await viewModel.applyChanges()
                }
            } label: {
                HStack(spacing: 8) {
                    if viewModel.isApplying {
                        ProgressView()
                            .tint(.white)
                            .scaleEffect(0.8)
                    } else {
                        Image(systemName: "sparkles")
                            .font(.system(size: 16, weight: .semibold))
                    }

                    Text(viewModel.hasChanges ? "Применить изменения (\(viewModel.dirtyCount))" : "Применить изменения")
                        .font(.system(size: 16, weight: .semibold))
                }
                .foregroundColor(.white)
                .frame(maxWidth: .infinity)
                .padding(.vertical, 16)
                .background(
                    LinearGradient(
                        colors: viewModel.hasChanges ? [Color.orange, Color(red: 1.0, green: 0.4, blue: 0.2)] : [Color.gray.opacity(0.5), Color.gray.opacity(0.3)],
                        startPoint: .leading,
                        endPoint: .trailing
                    )
                )
                .cornerRadius(14)
            }
            .disabled(!viewModel.hasChanges || viewModel.isApplying)

            if viewModel.hasChanges {
                Button {
                    viewModel.resetChanges()
                } label: {
                    Text("Сбросить изменения")
                        .font(.system(size: 14, weight: .medium))
                        .foregroundColor(.white.opacity(0.6))
                }
            }
        }
        .padding(16)
        .background(
            LinearGradient(
                colors: [
                    Color(red: 0.06, green: 0.04, blue: 0.03).opacity(0.0),
                    Color(red: 0.06, green: 0.04, blue: 0.03)
                ],
                startPoint: .top,
                endPoint: .bottom
            )
        )
    }

    // MARK: - Helpers

    private var glassCard: some View {
        RoundedRectangle(cornerRadius: 20, style: .continuous)
            .fill(Color.white.opacity(0.06))
            .background(.ultraThinMaterial, in: RoundedRectangle(cornerRadius: 20, style: .continuous))
            .shadow(color: Color.black.opacity(0.3), radius: 12, x: 0, y: 6)
    }

    private func timePickerSheet(title: String, time: Binding<Date>) -> some View {
        NavigationStack {
            VStack {
                DatePicker("", selection: time, displayedComponents: .hourAndMinute)
                    .datePickerStyle(.wheel)
                    .labelsHidden()
                Spacer()
            }
            .padding()
            .navigationTitle(title)
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .confirmationAction) {
                    Button("Готово") {
                        isShowingStartTimePicker = false
                        isShowingEndTimePicker = false
                    }
                }
            }
        }
        .presentationDetents([.medium])
        .presentationBackground(Color(red: 0.12, green: 0.10, blue: 0.08))
    }
}

// MARK: - Supporting Views

struct StudioSectionCard<Content: View>: View {
    let title: String
    @ViewBuilder let content: Content

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            Text(title)
                .font(.system(size: 16, weight: .bold, design: .rounded))
                .foregroundColor(.white)

            content
        }
        .padding(18)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(
            RoundedRectangle(cornerRadius: 20, style: .continuous)
                .fill(Color.white.opacity(0.06))
                .background(.ultraThinMaterial, in: RoundedRectangle(cornerRadius: 20, style: .continuous))
                .shadow(color: Color.black.opacity(0.25), radius: 10, x: 0, y: 5)
        )
    }
}

struct StudioChip: View {
    let title: String
    var icon: String? = nil
    let isSelected: Bool
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            HStack(spacing: 6) {
                if let icon {
                    Image(systemName: icon)
                        .font(.system(size: 12, weight: .semibold))
                }
                Text(title)
                    .font(.system(size: 13, weight: .semibold))
            }
            .foregroundColor(isSelected ? .white : .white.opacity(0.7))
            .padding(.horizontal, 14)
            .padding(.vertical, 10)
            .background(
                Capsule()
                    .fill(isSelected ? Color.orange : Color.white.opacity(0.1))
            )
        }
        .buttonStyle(.plain)
    }
}

struct StudioTimeButton: View {
    let label: String
    let time: Date
    let action: () -> Void

    private var timeText: String {
        let formatter = DateFormatter()
        formatter.dateFormat = "HH:mm"
        return formatter.string(from: time)
    }

    var body: some View {
        Button(action: action) {
            VStack(alignment: .leading, spacing: 4) {
                Text(label)
                    .font(.system(size: 11, weight: .medium))
                    .foregroundColor(.white.opacity(0.5))
                Text(timeText)
                    .font(.system(size: 18, weight: .bold, design: .rounded))
                    .foregroundColor(.white)
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            .padding(12)
            .background(
                RoundedRectangle(cornerRadius: 12, style: .continuous)
                    .fill(Color.white.opacity(0.08))
            )
        }
        .buttonStyle(.plain)
    }
}

struct StudioPresetButton: View {
    let preset: DayPreset
    let isSelected: Bool
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            VStack(spacing: 6) {
                Image(systemName: preset.icon)
                    .font(.system(size: 18, weight: .medium))
                    .foregroundColor(isSelected ? .orange : .white.opacity(0.6))
                Text(preset.title)
                    .font(.system(size: 10, weight: .medium))
                    .foregroundColor(isSelected ? .white : .white.opacity(0.6))
                    .lineLimit(1)
            }
            .frame(maxWidth: .infinity)
            .padding(.vertical, 12)
            .background(
                RoundedRectangle(cornerRadius: 12, style: .continuous)
                    .fill(isSelected ? Color.orange.opacity(0.2) : Color.white.opacity(0.06))
                    .overlay(
                        RoundedRectangle(cornerRadius: 12, style: .continuous)
                            .stroke(isSelected ? Color.orange : Color.clear, lineWidth: 1.5)
                    )
            )
        }
        .buttonStyle(.plain)
    }
}

struct WishBubble: View {
    let message: WishMessage

    var body: some View {
        HStack {
            if message.role == .user {
                Spacer(minLength: 40)
            }

            Text(message.text)
                .font(.system(size: 13))
                .foregroundColor(message.role == .user ? .white : .white.opacity(0.9))
                .padding(.horizontal, 12)
                .padding(.vertical, 8)
                .background(
                    RoundedRectangle(cornerRadius: 14, style: .continuous)
                        .fill(message.role == .user ? Color.orange.opacity(0.3) : Color.white.opacity(0.1))
                )

            if message.role == .assistant {
                Spacer(minLength: 40)
            }
        }
    }
}

struct SearchResultCard: View {
    let result: StudioSearchResult
    let onAdd: (PlacePlacement) -> Void

    @State private var showPlacementOptions = false

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack {
                VStack(alignment: .leading, spacing: 4) {
                    Text(result.name)
                        .font(.system(size: 14, weight: .semibold))
                        .foregroundColor(.white)

                    if let address = result.address {
                        Text(address)
                            .font(.system(size: 12))
                            .foregroundColor(.white.opacity(0.6))
                            .lineLimit(1)
                    }
                }

                Spacer()

                if let rating = result.rating {
                    HStack(spacing: 4) {
                        Image(systemName: "star.fill")
                            .font(.system(size: 10))
                            .foregroundColor(.orange)
                        Text(String(format: "%.1f", rating))
                            .font(.system(size: 12, weight: .semibold))
                            .foregroundColor(.white.opacity(0.8))
                    }
                }
            }

            if showPlacementOptions {
                HStack(spacing: 8) {
                    PlacementOptionButton(title: "В план", icon: "plus.circle") {
                        onAdd(.auto)
                    }
                    PlacementOptionButton(title: "В слот...", icon: "clock") {
                        // TODO: Show slot picker
                        onAdd(.auto)
                    }
                    PlacementOptionButton(title: "Другое время", icon: "calendar") {
                        // TODO: Show time picker
                        onAdd(.auto)
                    }
                }
            } else {
                Button {
                    withAnimation(.easeInOut(duration: 0.2)) {
                        showPlacementOptions = true
                    }
                } label: {
                    Text("Добавить")
                        .font(.system(size: 12, weight: .semibold))
                        .foregroundColor(.orange)
                        .padding(.horizontal, 12)
                        .padding(.vertical, 6)
                        .background(
                            Capsule()
                                .fill(Color.orange.opacity(0.15))
                        )
                }
            }
        }
        .padding(12)
        .background(
            RoundedRectangle(cornerRadius: 14, style: .continuous)
                .fill(Color.white.opacity(0.05))
        )
    }
}

struct PlacementOptionButton: View {
    let title: String
    let icon: String
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            HStack(spacing: 4) {
                Image(systemName: icon)
                    .font(.system(size: 10, weight: .semibold))
                Text(title)
                    .font(.system(size: 11, weight: .medium))
            }
            .foregroundColor(.white.opacity(0.8))
            .padding(.horizontal, 10)
            .padding(.vertical, 6)
            .background(
                Capsule()
                    .fill(Color.white.opacity(0.1))
            )
        }
        .buttonStyle(.plain)
    }
}

struct PlaceReplaceCard: View {
    let place: StudioPlace
    let isPendingRemoval: Bool
    let isPendingReplacement: Bool
    let isExpanded: Bool
    let alternatives: [StudioSearchResult]
    let onToggleExpand: () -> Void
    let onReplace: (String) -> Void
    let onRemove: () -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack {
                VStack(alignment: .leading, spacing: 4) {
                    Text(place.name)
                        .font(.system(size: 14, weight: .semibold))
                        .foregroundColor(isPendingRemoval ? .white.opacity(0.4) : .white)
                        .strikethrough(isPendingRemoval)

                    Text("\(place.timeStart)–\(place.timeEnd)")
                        .font(.system(size: 12))
                        .foregroundColor(.white.opacity(0.5))
                }

                Spacer()

                if isPendingReplacement {
                    Text("Замена")
                        .font(.system(size: 10, weight: .semibold))
                        .foregroundColor(.orange)
                        .padding(.horizontal, 8)
                        .padding(.vertical, 4)
                        .background(Capsule().fill(Color.orange.opacity(0.2)))
                } else if isPendingRemoval {
                    Text("Удалено")
                        .font(.system(size: 10, weight: .semibold))
                        .foregroundColor(.red.opacity(0.8))
                        .padding(.horizontal, 8)
                        .padding(.vertical, 4)
                        .background(Capsule().fill(Color.red.opacity(0.2)))
                } else {
                    HStack(spacing: 8) {
                        Button(action: onToggleExpand) {
                            Text("Заменить")
                                .font(.system(size: 12, weight: .semibold))
                                .foregroundColor(.orange)
                        }

                        Button(action: onRemove) {
                            Image(systemName: "xmark")
                                .font(.system(size: 12, weight: .semibold))
                                .foregroundColor(.white.opacity(0.5))
                        }
                    }
                }
            }

            // Alternatives
            if isExpanded && !alternatives.isEmpty {
                VStack(spacing: 8) {
                    ForEach(alternatives.prefix(3)) { alt in
                        Button {
                            onReplace(alt.id)
                        } label: {
                            HStack {
                                VStack(alignment: .leading, spacing: 2) {
                                    Text(alt.name)
                                        .font(.system(size: 13, weight: .medium))
                                        .foregroundColor(.white)
                                    if let address = alt.address {
                                        Text(address)
                                            .font(.system(size: 11))
                                            .foregroundColor(.white.opacity(0.5))
                                            .lineLimit(1)
                                    }
                                }
                                Spacer()
                                if let rating = alt.rating {
                                    HStack(spacing: 2) {
                                        Image(systemName: "star.fill")
                                            .font(.system(size: 9))
                                            .foregroundColor(.orange)
                                        Text(String(format: "%.1f", rating))
                                            .font(.system(size: 11, weight: .semibold))
                                            .foregroundColor(.white.opacity(0.7))
                                    }
                                }
                            }
                            .padding(10)
                            .background(
                                RoundedRectangle(cornerRadius: 10, style: .continuous)
                                    .fill(Color.orange.opacity(0.1))
                            )
                        }
                        .buttonStyle(.plain)
                    }
                }
                .padding(.top, 4)
            }
        }
        .padding(12)
        .background(
            RoundedRectangle(cornerRadius: 14, style: .continuous)
                .fill(Color.white.opacity(0.05))
                .overlay(
                    RoundedRectangle(cornerRadius: 14, style: .continuous)
                        .stroke(
                            isPendingRemoval ? Color.red.opacity(0.3) :
                            isPendingReplacement ? Color.orange.opacity(0.3) :
                            Color.clear,
                            lineWidth: 1.5
                        )
                )
        )
    }
}

struct StudioPrimaryButtonStyle: ButtonStyle {
    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .font(.system(size: 15, weight: .semibold))
            .foregroundColor(.white)
            .padding(.horizontal, 24)
            .padding(.vertical, 12)
            .background(
                Capsule()
                    .fill(Color.orange)
            )
            .scaleEffect(configuration.isPressed ? 0.96 : 1.0)
    }
}

// MARK: - Preview

#Preview("Default State") {
    NavigationStack {
        AIStudioView(
            viewModel: AIStudioViewModel(
                tripId: UUID(),
                dayId: 1,
                cityName: "Париж",
                dayDate: Date()
            )
        )
    }
}
