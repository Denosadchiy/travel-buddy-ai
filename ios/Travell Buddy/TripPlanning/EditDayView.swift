import SwiftUI

struct EditDayView: View {
    @StateObject var viewModel: EditDayViewModel
    @State private var isShowingStartPicker = false
    @State private var isShowingEndPicker = false
    @State private var activityForStatusChange: TripActivity?
    @State private var isShowingStatusDialog: Bool = false
    @State private var activityForPreferenceChange: TripActivity?
    @State private var isAddingRequiredPlace: Bool = false
    @State private var isAddingBannedPlace: Bool = false
    @State private var newManualPlaceName: String = ""

    init(viewModel: EditDayViewModel) {
        _viewModel = StateObject(wrappedValue: viewModel)
    }

    var body: some View {
        ScrollView(.vertical, showsIndicators: false) {
            VStack(spacing: 16) {
                dayHeaderCard
                changeReasonsSection
                paceAndTimeSection
                budgetSection
                accentsSection
                placesSection
                feedbackSection
            }
            .padding(.horizontal, 16)
            .padding(.top, 8)
            .padding(.bottom, 120)
        }
        .background(
            LinearGradient.travelBuddyBackgroundAlt.ignoresSafeArea()
        )
        .navigationTitle("Настроить день")
        .navigationBarTitleDisplayMode(.inline)
        .toolbar {
            ToolbarItem(placement: .navigationBarTrailing) {
                Button {
                    viewModel.reset()
                } label: {
                    Image(systemName: "arrow.clockwise")
                        .font(.system(size: 16, weight: .semibold))
                        .foregroundColor(.travelBuddyOrange)
                }
            }
        }
        .safeAreaInset(edge: .bottom, spacing: 0) {
            bottomActions
        }
        .sheet(isPresented: $isShowingStartPicker) {
            timePickerSheet(title: "Начало дня", date: $viewModel.startTime)
        }
        .sheet(isPresented: $isShowingEndPicker) {
            timePickerSheet(title: "Окончание дня", date: $viewModel.endTime)
        }
        .sheet(isPresented: $isAddingRequiredPlace) {
            manualPlaceInputSheet(
                title: "Добавить обязательное место",
                placeholder: "Например, кафе Van Kahvalti",
                onSave: {
                    let trimmed = newManualPlaceName.trimmingCharacters(in: .whitespacesAndNewlines)
                    guard !trimmed.isEmpty else { return }
                    viewModel.addManualPlace(trimmed, status: .mustKeep)
                    newManualPlaceName = ""
                    isAddingRequiredPlace = false
                },
                onCancel: {
                    newManualPlaceName = ""
                    isAddingRequiredPlace = false
                }
            )
        }
        .sheet(isPresented: $isAddingBannedPlace) {
            manualPlaceInputSheet(
                title: "Добавить нежелательное место",
                placeholder: "Например, туристический ресторан",
                onSave: {
                    let trimmed = newManualPlaceName.trimmingCharacters(in: .whitespacesAndNewlines)
                    guard !trimmed.isEmpty else { return }
                    viewModel.addManualPlace(trimmed, status: .banned)
                    newManualPlaceName = ""
                    isAddingBannedPlace = false
                },
                onCancel: {
                    newManualPlaceName = ""
                    isAddingBannedPlace = false
                }
            )
        }
        .confirmationDialog(
            "Что сделать с этим местом?",
            isPresented: $isShowingStatusDialog,
            titleVisibility: .visible,
            presenting: activityForStatusChange,
            actions: { activity in
                Button("Оставить как есть") {
                    viewModel.updateStatus(for: activity, status: .keep)
                }
                Button("Заменить на другое место") {
                    viewModel.updateStatus(for: activity, status: .replace)
                }
                Button("Убрать из дня", role: .destructive) {
                    viewModel.updateStatus(for: activity, status: .remove)
                }
            },
            message: { _ in
                Text("Выбери действие для Travel Buddy.")
            }
        )
        .confirmationDialog(
            "Настройки для места",
            isPresented: Binding(
                get: { activityForPreferenceChange != nil },
                set: { if !$0 { activityForPreferenceChange = nil } }
            ),
            titleVisibility: .visible,
            presenting: activityForPreferenceChange,
            actions: { activity in
                Button("Сделать обязательным местом") {
                    viewModel.updatePreference(for: activity, status: .mustKeep)
                }
                Button("Больше не предлагать подобные места") {
                    viewModel.updatePreference(for: activity, status: .banned)
                }
                Button("Обычное место") {
                    viewModel.updatePreference(for: activity, status: .none)
                }
                Button("Отмена", role: .cancel) { }
            },
            message: { activity in
                Text(activity.title)
            }
        )
    }

    // MARK: - Day Header

    private var dayHeaderCard: some View {
        VStack(alignment: .leading, spacing: 16) {
            VStack(alignment: .leading, spacing: 8) {
                Text("День \(viewModel.originalDay.index)")
                    .font(.system(size: 28, weight: .bold, design: .rounded))
                    .foregroundColor(.travelBuddyOrange)

                Text(fullDateText(viewModel.originalDay.date))
                    .font(.system(size: 16, weight: .medium))
                    .foregroundColor(Color(.label))

                Text("\(viewModel.destinationCity) · \(viewModel.interestsSummary)")
                    .font(.system(size: 14))
                    .foregroundColor(Color(.secondaryLabel))
            }

            HStack(spacing: 12) {
                InfoPill(
                    icon: "figure.walk",
                    text: paceLabel(for: viewModel.pace),
                    color: .travelBuddyOrange
                )
                InfoPill(
                    icon: "mappin.circle.fill",
                    text: "\(viewModel.originalDay.activities.count) точек",
                    color: .travelBuddyTeal
                )
            }
        }
        .padding(20)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(
            RoundedRectangle(cornerRadius: 20, style: .continuous)
                .fill(Color(.systemBackground))
                .cardShadow()
        )
    }

    // MARK: - Change Reasons

    private var changeReasonsSection: some View {
        SectionCard(title: "Что хочешь изменить?") {
            LazyVGrid(columns: [GridItem(.flexible()), GridItem(.flexible())], spacing: 10) {
                ForEach(ChangeReason.allCases) { reason in
                    let isSelected = viewModel.selectedReasons.contains(reason)
                    SelectableChip(
                        title: reason.title,
                        icon: iconForReason(reason),
                        isSelected: isSelected,
                        color: colorForReason(reason)
                    ) {
                        viewModel.toggle(reason: reason)
                    }
                }
            }
        }
    }

    // MARK: - Pace and Time

    private var paceAndTimeSection: some View {
        SectionCard(title: "Темп и время") {
            VStack(spacing: 16) {
                // Темп
                VStack(alignment: .leading, spacing: 10) {
                    Label("Темп дня", systemImage: "gauge.with.dots.needle.bottom.50percent")
                        .font(.system(size: 14, weight: .semibold))
                        .foregroundColor(Color(.secondaryLabel))

                    HStack(spacing: 8) {
                        ForEach(DayPace.allCases) { pace in
                            let isSelected = viewModel.pace == pace
                            CompactChip(
                                title: pace.title,
                                isSelected: isSelected,
                                color: .travelBuddyOrange
                            ) {
                                viewModel.select(pace: pace)
                            }
                        }
                    }
                }

                Divider()

                // Время
                VStack(alignment: .leading, spacing: 10) {
                    Label("Активное время", systemImage: "clock")
                        .font(.system(size: 14, weight: .semibold))
                        .foregroundColor(Color(.secondaryLabel))

                    HStack(spacing: 10) {
                        TimeButton(title: "Начать", time: viewModel.startTime) {
                            isShowingStartPicker = true
                        }
                        TimeButton(title: "Завершить", time: viewModel.endTime) {
                            isShowingEndPicker = true
                        }
                    }
                }
            }
        }
    }

    // MARK: - Budget

    private var budgetSection: some View {
        SectionCard(title: "Бюджет на день") {
            HStack(spacing: 8) {
                ForEach(DayBudgetLevel.allCases) { level in
                    let isSelected = viewModel.dayBudgetLevel == level
                    CompactChip(
                        title: level.title,
                        isSelected: isSelected,
                        color: Color(red: 0.3, green: 0.7, blue: 0.4)
                    ) {
                        viewModel.dayBudgetLevel = level
                    }
                }
            }
        }
    }

    // MARK: - Accents

    private var accentsSection: some View {
        SectionCard(title: "Акценты дня", subtitle: "Сделай день гастрономическим или культурным") {
            LazyVGrid(columns: [GridItem(.flexible()), GridItem(.flexible())], spacing: 10) {
                ForEach(DayAccent.allCases) { accent in
                    let isSelected = viewModel.selectedAccents.contains(accent)
                    SelectableChip(
                        title: accent.title,
                        icon: iconForAccent(accent),
                        isSelected: isSelected,
                        color: accentColor(accent)
                    ) {
                        viewModel.toggle(accent: accent)
                    }
                }
            }
        }
    }

    // MARK: - Places

    private var placesSection: some View {
        SectionCard(title: "Места в маршруте") {
            VStack(spacing: 12) {
                ForEach(viewModel.originalDay.activities) { activity in
                    PlaceCard(
                        activity: activity,
                        status: viewModel.status(for: activity),
                        preference: viewModel.preference(for: activity),
                        onStatusTap: {
                            activityForStatusChange = activity
                            isShowingStatusDialog = true
                        },
                        onPreferenceTap: {
                            activityForPreferenceChange = activity
                        }
                    )
                }
            }
        }
    }

    // MARK: - Feedback

    private var feedbackSection: some View {
        SectionCard(title: "Пожелания", subtitle: "Расскажи, что важно для этого дня") {
            VStack(spacing: 12) {
                TextEditor(text: $viewModel.feedbackText)
                    .font(.system(size: 15))
                    .frame(minHeight: 100)
                    .padding(12)
                    .scrollContentBackground(.hidden)
                    .background(
                        RoundedRectangle(cornerRadius: 12, style: .continuous)
                            .fill(Color(.tertiarySystemBackground))
                    )
                    .overlay(alignment: .topLeading) {
                        if viewModel.feedbackText.isEmpty {
                            Text("Например: \"Хочу больше времени для фото\" или \"Избегать толп\"")
                                .font(.system(size: 15))
                                .foregroundColor(Color(.tertiaryLabel))
                                .padding(18)
                                .allowsHitTesting(false)
                        }
                    }
            }
        }
    }

    // MARK: - Bottom Actions

    private var bottomActions: some View {
        VStack(spacing: 12) {
            Button {
                let request = viewModel.buildEditRequest()
                print("Edit day request: \(request)")
            } label: {
                HStack {
                    Image(systemName: "sparkles")
                        .font(.system(size: 16, weight: .semibold))
                    Text("Пересобрать день")
                        .font(.system(size: 17, weight: .semibold))
                }
                .foregroundColor(.white)
                .frame(maxWidth: .infinity)
                .padding(.vertical, 16)
                .background(LinearGradient.travelBuddyPrimaryHorizontal)
                .cornerRadius(14)
                .buttonShadow()
            }
            .buttonStyle(.plain)

            Button {
                viewModel.reset()
            } label: {
                Text("Сбросить изменения")
                    .font(.system(size: 15, weight: .medium))
                    .foregroundColor(Color(.secondaryLabel))
            }
        }
        .padding(16)
        .background(
            Color(.systemBackground)
                .shadow(color: Color.black.opacity(0.08), radius: 20, x: 0, y: -4)
        )
    }

    // MARK: - Helper Views

    private func timePickerSheet(title: String, date: Binding<Date>) -> some View {
        NavigationStack {
            VStack {
                DatePicker("", selection: date, displayedComponents: .hourAndMinute)
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
                        isShowingStartPicker = false
                        isShowingEndPicker = false
                    }
                }
            }
        }
        .presentationDetents([.medium])
    }

    private func manualPlaceInputSheet(title: String, placeholder: String, onSave: @escaping () -> Void, onCancel: @escaping () -> Void) -> some View {
        NavigationStack {
            VStack(spacing: 16) {
                TextField(placeholder, text: $newManualPlaceName)
                    .textFieldStyle(.roundedBorder)
                    .padding(.top, 16)
                Spacer()
            }
            .padding(.horizontal, 16)
            .navigationTitle(title)
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Отмена") { onCancel() }
                }
                ToolbarItem(placement: .confirmationAction) {
                    Button("Сохранить") { onSave() }
                        .disabled(newManualPlaceName.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
                }
            }
        }
        .presentationDetents([.medium])
    }

    // MARK: - Helper Functions

    private func iconForReason(_ reason: ChangeReason) -> String {
        switch reason {
        case .pace: return "figure.walk"
        case .timing: return "clock"
        case .tooMuchWalk: return "figure.walk.departure"
        case .shiftFocus: return "scope"
        case .replacePlaces: return "arrow.triangle.2.circlepath"
        case .avoidQueues: return "person.3"
        }
    }

    private func colorForReason(_ reason: ChangeReason) -> Color {
        switch reason {
        case .pace: return Color(red: 1.0, green: 0.55, blue: 0.30)
        case .timing: return Color(red: 0.2, green: 0.6, blue: 1.0)
        case .tooMuchWalk: return Color(red: 0.4, green: 0.7, blue: 0.3)
        case .shiftFocus: return Color(red: 0.7, green: 0.4, blue: 0.9)
        case .replacePlaces: return Color(red: 1.0, green: 0.6, blue: 0.2)
        case .avoidQueues: return Color(red: 0.5, green: 0.5, blue: 0.5)
        }
    }

    private func iconForAccent(_ accent: DayAccent) -> String {
        switch accent {
        case .food: return "fork.knife"
        case .walks: return "figure.walk"
        case .culture: return "building.columns"
        case .shopping: return "bag"
        case .nightlife: return "moon.stars"
        case .relax: return "leaf"
        }
    }

    private func accentColor(_ accent: DayAccent) -> Color {
        switch accent {
        case .food: return Color(red: 1.0, green: 0.45, blue: 0.35)
        case .walks: return Color(red: 0.26, green: 0.68, blue: 0.53)
        case .culture: return Color(red: 0.52, green: 0.43, blue: 0.91)
        case .shopping: return Color(red: 0.96, green: 0.62, blue: 0.20)
        case .nightlife: return Color(red: 0.83, green: 0.32, blue: 0.51)
        case .relax: return Color(red: 0.29, green: 0.62, blue: 0.94)
        }
    }

    private func paceLabel(for pace: DayPace) -> String {
        switch pace {
        case .calm: return "Спокойный"
        case .medium: return "Средний"
        case .intense: return "Насыщенный"
        }
    }

    private func fullDateText(_ date: Date) -> String {
        let formatter = DateFormatter()
        formatter.locale = Locale(identifier: "ru_RU")
        formatter.dateFormat = "d MMMM, EEEE"
        return formatter.string(from: date)
    }
}

// MARK: - Reusable Components

struct SectionCard<Content: View>: View {
    let title: String
    var subtitle: String?
    @ViewBuilder let content: Content

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            VStack(alignment: .leading, spacing: 4) {
                Text(title)
                    .font(.system(size: 18, weight: .bold, design: .rounded))
                    .foregroundColor(Color(.label))

                if let subtitle = subtitle {
                    Text(subtitle)
                        .font(.system(size: 13))
                        .foregroundColor(Color(.secondaryLabel))
                }
            }

            content
        }
        .padding(18)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(
            RoundedRectangle(cornerRadius: 18, style: .continuous)
                .fill(Color(.systemBackground))
                .lightShadow()
        )
    }
}

struct SelectableChip: View {
    let title: String
    let icon: String
    let isSelected: Bool
    let color: Color
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            HStack(spacing: 8) {
                Image(systemName: icon)
                    .font(.system(size: 14, weight: .semibold))
                Text(title)
                    .font(.system(size: 14, weight: .medium))
                    .lineLimit(1)
            }
            .foregroundColor(isSelected ? .white : Color(.label))
            .padding(.horizontal, 14)
            .padding(.vertical, 12)
            .frame(maxWidth: .infinity)
            .background(
                RoundedRectangle(cornerRadius: 12, style: .continuous)
                    .fill(isSelected ? color : Color(.tertiarySystemBackground))
            )
        }
        .buttonStyle(.plain)
    }
}

struct CompactChip: View {
    let title: String
    let isSelected: Bool
    let color: Color
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            Text(title)
                .font(.system(size: 14, weight: .medium))
                .foregroundColor(isSelected ? .white : Color(.secondaryLabel))
                .padding(.horizontal, 16)
                .padding(.vertical, 10)
                .frame(maxWidth: .infinity)
                .background(
                    RoundedRectangle(cornerRadius: 10, style: .continuous)
                        .fill(isSelected ? color : Color(.tertiarySystemBackground))
                )
        }
        .buttonStyle(.plain)
    }
}

struct InfoPill: View {
    let icon: String
    let text: String
    let color: Color

    var body: some View {
        HStack(spacing: 6) {
            Image(systemName: icon)
                .font(.system(size: 13, weight: .semibold))
            Text(text)
                .font(.system(size: 13, weight: .medium))
        }
        .foregroundColor(color)
        .padding(.horizontal, 12)
        .padding(.vertical, 7)
        .background(
            Capsule().fill(color.opacity(0.12))
        )
    }
}

struct TimeButton: View {
    let title: String
    let time: Date
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            VStack(alignment: .leading, spacing: 4) {
                Text(title)
                    .font(.system(size: 12, weight: .medium))
                    .foregroundColor(Color(.secondaryLabel))
                Text(timeString(from: time))
                    .font(.system(size: 17, weight: .semibold))
                    .foregroundColor(Color(.label))
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            .padding(12)
            .background(
                RoundedRectangle(cornerRadius: 12, style: .continuous)
                    .fill(Color(.tertiarySystemBackground))
            )
        }
        .buttonStyle(.plain)
    }

    private func timeString(from date: Date) -> String {
        let formatter = DateFormatter()
        formatter.dateFormat = "HH:mm"
        return formatter.string(from: date)
    }
}

struct PlaceCard: View {
    let activity: TripActivity
    let status: EditPlaceStatus
    let preference: PlacePreferenceStatus
    let onStatusTap: () -> Void
    let onPreferenceTap: () -> Void

    var body: some View {
        HStack(alignment: .top, spacing: 12) {
            // Time
            Text(activity.time)
                .font(.system(size: 15, weight: .bold))
                .foregroundColor(.travelBuddyOrange)
                .frame(width: 50, alignment: .leading)

            // Content
            VStack(alignment: .leading, spacing: 8) {
                HStack(alignment: .top) {
                    VStack(alignment: .leading, spacing: 6) {
                        Text(activity.title)
                            .font(.system(size: 16, weight: .semibold))
                            .foregroundColor(status == .remove ? Color(.tertiaryLabel) : Color(.label))
                            .strikethrough(status == .remove)

                        Text(activity.description)
                            .font(.system(size: 13))
                            .foregroundColor(Color(.secondaryLabel))
                            .lineLimit(2)

                        CategoryBadge(category: activity.category)
                    }

                    Spacer()

                    StatusBadge(status: status)
                }

                HStack(spacing: 8) {
                    Spacer()

                    Button(action: onStatusTap) {
                        Image(systemName: "ellipsis")
                            .font(.system(size: 14, weight: .semibold))
                            .foregroundColor(Color(.secondaryLabel))
                            .frame(width: 32, height: 32)
                            .background(Circle().fill(Color(.tertiarySystemBackground)))
                    }
                    .buttonStyle(.plain)

                    Button(action: onPreferenceTap) {
                        Image(systemName: preferenceIcon(for: preference))
                            .font(.system(size: 14, weight: .semibold))
                            .foregroundColor(preferenceTint(for: preference))
                            .frame(width: 32, height: 32)
                            .background(Circle().fill(Color(.tertiarySystemBackground)))
                    }
                    .buttonStyle(.plain)
                }
            }
            .padding(14)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(placeBackground(for: status))
            .overlay(
                RoundedRectangle(cornerRadius: 14, style: .continuous)
                    .stroke(borderColor(for: status), lineWidth: status == .keep ? 0 : 2)
            )
            .cornerRadius(14)
        }
    }

    private func placeBackground(for status: EditPlaceStatus) -> some View {
        let color: Color
        switch status {
        case .keep:
            color = Color(.secondarySystemBackground)
        case .replace:
            color = Color(red: 1.0, green: 0.97, blue: 0.90)
        case .remove:
            color = Color(red: 1.0, green: 0.93, blue: 0.93)
        }
        return RoundedRectangle(cornerRadius: 14, style: .continuous).fill(color)
    }

    private func borderColor(for status: EditPlaceStatus) -> Color {
        switch status {
        case .keep: return .clear
        case .replace: return Color(red: 1.0, green: 0.7, blue: 0.3)
        case .remove: return Color(red: 0.95, green: 0.4, blue: 0.4)
        }
    }

    private func preferenceIcon(for status: PlacePreferenceStatus) -> String {
        switch status {
        case .none: return "star"
        case .mustKeep: return "star.fill"
        case .banned: return "nosign"
        }
    }

    private func preferenceTint(for status: PlacePreferenceStatus) -> Color {
        switch status {
        case .none: return Color(.tertiaryLabel)
        case .mustKeep: return Color(red: 1.0, green: 0.7, blue: 0.0)
        case .banned: return Color(red: 0.9, green: 0.3, blue: 0.3)
        }
    }
}

struct StatusBadge: View {
    let status: EditPlaceStatus

    var body: some View {
        let config = statusConfig(for: status)

        if status != .keep {
            Image(systemName: config.icon)
                .font(.system(size: 12, weight: .bold))
                .foregroundColor(config.color)
                .frame(width: 28, height: 28)
                .background(Circle().fill(config.background))
        }
    }

    private func statusConfig(for status: EditPlaceStatus) -> (icon: String, color: Color, background: Color) {
        switch status {
        case .keep:
            return ("checkmark", .green, Color.green.opacity(0.15))
        case .replace:
            return ("arrow.triangle.2.circlepath", Color(red: 1.0, green: 0.6, blue: 0.0), Color(red: 1.0, green: 0.93, blue: 0.80))
        case .remove:
            return ("xmark", Color(red: 0.9, green: 0.3, blue: 0.3), Color(red: 1.0, green: 0.88, blue: 0.88))
        }
    }
}

struct CategoryBadge: View {
    let category: TripActivityCategory

    var body: some View {
        Text(categoryTitle(for: category))
            .font(.system(size: 11, weight: .semibold))
            .foregroundColor(categoryColor(for: category))
            .padding(.horizontal, 8)
            .padding(.vertical, 4)
            .background(
                Capsule().fill(categoryColor(for: category).opacity(0.12))
            )
    }

    private func categoryTitle(for category: TripActivityCategory) -> String {
        switch category {
        case .food: return "Еда"
        case .walk: return "Прогулка"
        case .museum: return "История"
        case .viewpoint: return "Вид"
        case .nightlife: return "Вечер"
        case .other: return "Другое"
        }
    }

    private func categoryColor(for category: TripActivityCategory) -> Color {
        switch category {
        case .food: return Color(red: 1.0, green: 0.55, blue: 0.30)
        case .walk: return Color(red: 0.26, green: 0.66, blue: 0.45)
        case .museum: return Color(.systemIndigo)
        case .viewpoint: return Color(red: 0.15, green: 0.6, blue: 0.9)
        case .nightlife: return Color(red: 0.7, green: 0.4, blue: 0.9)
        case .other: return Color(.systemGray)
        }
    }
}
