//
//  TripPlanView.swift
//  Travell Buddy
//
//  Renders the detailed day-by-day route following the draft design.
//

import SwiftUI

struct TripPlanView: View {
    @StateObject var viewModel: TripPlanViewModel
    @State private var isShowingGuide: Bool = false
    @State private var isShowingEditDay: Bool = false
    @State private var isShowingChat: Bool = false
    @State private var isShowingSummary: Bool = false
    @State private var editViewModel: EditDayViewModel?
    @State private var chatViewModel: ChatViewModel?
    @State private var selectedPlace: Place?

    init(viewModel: TripPlanViewModel) {
        _viewModel = StateObject(wrappedValue: viewModel)
    }
    
    var body: some View {
        Group {
            if let plan = viewModel.plan {
                // Show trip plan
                ScrollView {
                    VStack(alignment: .leading, spacing: 16) {
                        headerCard(plan: plan)
                        tabSwitcher
                        tabContent
                            .padding(.top, 4)
                    }
                    .padding(.horizontal, 16)
                    .padding(.top, 12)
                    .padding(.bottom, 120)
                }
                .background(Color(.systemBackground).ignoresSafeArea())
                .safeAreaInset(edge: .bottom) {
                    guideCTA
                }
                .background(editDayNavigationLink)
                .background(guideNavigationLink)
            } else if viewModel.isLoading {
                // Show loading state
                VStack(spacing: 20) {
                    ProgressView()
                        .scaleEffect(1.5)
                    Text("Генерирую маршрут...")
                        .font(.system(size: 16, weight: .medium))
                        .foregroundColor(.secondary)
                }
            } else if let error = viewModel.errorMessage {
                // Show error state
                VStack(spacing: 20) {
                    Image(systemName: "exclamationmark.triangle")
                        .font(.system(size: 48))
                        .foregroundColor(.orange)
                    Text("Ошибка")
                        .font(.system(size: 20, weight: .semibold))
                    Text(error)
                        .font(.system(size: 14))
                        .foregroundColor(.secondary)
                        .multilineTextAlignment(.center)
                        .padding(.horizontal, 40)
                }
            } else {
                // Empty state (shouldn't normally happen)
                VStack(spacing: 20) {
                    Image(systemName: "map")
                        .font(.system(size: 48))
                        .foregroundColor(.gray)
                    Text("Нет данных о маршруте")
                        .font(.system(size: 16, weight: .medium))
                        .foregroundColor(.secondary)
                }
            }
        }
        .navigationTitle("Маршрут поездки")
        .navigationBarTitleDisplayMode(.inline)
        .toolbar {
            ToolbarItem(placement: .navigationBarTrailing) {
                Button(action: { openChat() }) {
                    Image(systemName: "message.fill")
                        .font(.system(size: 16, weight: .semibold))
                        .foregroundColor(.travelBuddyOrange)
                }
            }
        }
        .background(chatNavigationLink)
        .sheet(item: $selectedPlace) { place in
            PlaceDetailsSheet(place: place)
                .presentationDetents([.medium, .large])
                .presentationDragIndicator(.visible)
        }
        .onChange(of: isShowingEditDay) { newValue in
            if !newValue {
                editViewModel = nil
            }
        }
        .onChange(of: isShowingChat) { newValue in
            if !newValue {
                chatViewModel = nil
            }
        }
    }
    
    private var tabContent: some View {
        Group {
            switch viewModel.selectedTab {
            case .route:
                routeContent
            case .map:
                mapPlaceholder
            }
        }
    }
    
    private func headerCard(plan: TripPlan) -> some View {
        let summary = plan.summary

        return VStack(alignment: .leading, spacing: 14) {
            HStack(alignment: .top, spacing: 12) {
                VStack(alignment: .leading, spacing: 6) {
                    Text("\(plan.destinationCity), \(dateRangeText(start: plan.startDate, end: plan.endDate))")
                        .font(.system(size: 21, weight: .semibold, design: .rounded))
                        .foregroundColor(Color(.label))
                        .lineLimit(2)
                        .truncationMode(.tail)
                    Text("\(plan.travellersCount) взрослых · \(plan.comfortLevel) · \(plan.interestsSummary)")
                        .font(.system(size: 13))
                        .foregroundColor(Color(.secondaryLabel))
                        .lineLimit(2)
                        .truncationMode(.tail)
                }
                Spacer()
                Button(action: { isShowingSummary = true }) {
                    Image(systemName: "chart.bar.fill")
                        .font(.system(size: 16, weight: .semibold))
                        .foregroundColor(Color(.label))
                        .frame(width: 28, height: 28)
                        .background(
                            Circle()
                                .fill(Color(.systemGray5))
                        )
                }
                .buttonStyle(.plain)
            }

            // Summary stats row
            summaryStatsRow(summary: summary)
        }
        .padding(16)
        .background(
            RoundedRectangle(cornerRadius: 24, style: .continuous)
                .fill(Color(.secondarySystemBackground))
        )
        .sheet(isPresented: $isShowingSummary) {
            NavigationView {
                TripSummaryView(summary: summary, coordinate: plan.cityCoordinate)
                    .toolbar {
                        ToolbarItem(placement: .navigationBarTrailing) {
                            Button("Готово") {
                                isShowingSummary = false
                            }
                        }
                    }
            }
        }
    }

    private func summaryStatsRow(summary: TripSummary) -> some View {
        ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: 10) {
                summaryChip(
                    icon: "figure.walk",
                    text: summary.formattedTotalSteps,
                    subtitle: "шагов"
                )
                summaryChip(
                    icon: "map",
                    text: summary.formattedTotalDistance,
                    subtitle: nil
                )
                summaryChip(
                    icon: "creditcard",
                    text: summary.formattedTotalCostRange,
                    subtitle: nil
                )
                summaryChip(
                    icon: summary.overallIntensity.icon,
                    text: summary.overallIntensity.displayName,
                    subtitle: "темп"
                )
            }
            .padding(.vertical, 2)
        }
    }

    private func summaryChip(icon: String, text: String, subtitle: String?) -> some View {
        HStack(spacing: 6) {
            Image(systemName: icon)
                .font(.system(size: 11))
                .foregroundColor(Color(red: 0.90, green: 0.35, blue: 0.20))

            Text(text)
                .font(.system(size: 12, weight: .semibold))
                .foregroundColor(Color(red: 0.90, green: 0.35, blue: 0.20))

            if let subtitle = subtitle {
                Text(subtitle)
                    .font(.system(size: 11))
                    .foregroundColor(Color(red: 0.90, green: 0.35, blue: 0.20).opacity(0.8))
            }
        }
        .padding(.horizontal, 12)
        .padding(.vertical, 6)
        .background(
            Capsule()
                .fill(Color(red: 1.0, green: 0.93, blue: 0.89))
        )
    }
    
    private func chipView(text: String) -> some View {
        Text(text)
            .font(.system(size: 12, weight: .medium))
            .padding(.horizontal, 14)
            .padding(.vertical, 6)
            .background(
                Capsule()
                    .fill(Color(red: 1.0, green: 0.93, blue: 0.89))
            )
            .foregroundColor(Color(red: 0.90, green: 0.35, blue: 0.20))
    }
    
    private var tabSwitcher: some View {
        HStack(spacing: 0) {
            tabButton(title: "Маршрут", isSelected: viewModel.selectedTab == .route) {
                viewModel.selectedTab = .route
            }
            tabButton(title: "Карта", isSelected: viewModel.selectedTab == .map) {
                viewModel.selectedTab = .map
            }
        }
        .frame(height: 38)
        .background(
            RoundedRectangle(cornerRadius: 18, style: .continuous)
                .fill(Color(.secondarySystemBackground))
        )
    }
    
    private func tabButton(title: String, isSelected: Bool, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            Text(title)
                .font(.system(size: 14, weight: .semibold))
                .foregroundColor(isSelected ? .white : Color(.secondaryLabel))
                .frame(maxWidth: .infinity)
                .padding(.vertical, 8)
                .background(
                    RoundedRectangle(cornerRadius: 14, style: .continuous)
                        .fill(isSelected ? Color(red: 1.0, green: 0.45, blue: 0.35) : Color.clear)
                )
        }
        .buttonStyle(.plain)
    }
    
    private var routeContent: some View {
        VStack(alignment: .leading, spacing: 12) {
            if let plan = viewModel.plan {
                daySelector(plan: plan)
                let day = plan.days[safe: viewModel.selectedDayIndex] ?? plan.days.first
                if let day {
                    dayHeader(day: day)
                        .padding(.top, 4)
                    activityTimeline(activities: day.activities)
                }
            }
        }
    }

    private func daySelector(plan: TripPlan) -> some View {
        ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: 8) {
                ForEach(plan.days) { day in
                    let isSelected = day.index - 1 == viewModel.selectedDayIndex
                    Button {
                        viewModel.selectedDayIndex = day.index - 1
                    } label: {
                        VStack(alignment: .leading, spacing: 2) {
                            Text("День \(day.index)")
                                .font(.system(size: 13, weight: .semibold))
                            Text(dayDateText(day.date))
                                .font(.system(size: 12))
                                .foregroundColor(isSelected ? .white.opacity(0.9) : Color(.secondaryLabel))
                        }
                        .padding(.horizontal, 12)
                        .padding(.vertical, 10)
                        .background(
                            RoundedRectangle(cornerRadius: 14, style: .continuous)
                                .fill(isSelected ? Color(red: 1.0, green: 0.45, blue: 0.35) : Color(.secondarySystemBackground))
                        )
                        .foregroundColor(isSelected ? .white : Color(.label))
                    }
                    .buttonStyle(.plain)
                }
            }
        }
    }
    
    private func dayHeader(day: TripDay) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack(alignment: .center) {
                VStack(alignment: .leading, spacing: 4) {
                    Text("День \(day.index)")
                        .font(.system(size: 18, weight: .semibold))
                    Text(fullDateText(day.date))
                        .font(.system(size: 13))
                        .foregroundColor(Color(.secondaryLabel))
                }
                Spacer()
                Button(action: {
                    openEdit(for: day)
                }) {
                    Text("Настроить")
                        .font(.system(size: 13, weight: .medium))
                        .padding(.horizontal, 14)
                        .padding(.vertical, 6)
                        .background(
                            Capsule()
                                .stroke(Color(.systemGray4), lineWidth: 1)
                        )
                }
                .buttonStyle(.plain)
            }
            if let title = day.title {
                Text(title)
                    .font(.system(size: 14, weight: .medium))
                    .foregroundColor(Color(.label))
                    .lineLimit(2)
            }
            if let summary = day.summary {
                Text(summary)
                    .font(.system(size: 13))
                    .foregroundColor(Color(.secondaryLabel))
                    .lineLimit(3)
            }
        }
    }
    
    private func activityTimeline(activities: [TripActivity]) -> some View {
        VStack(spacing: 12) {
            ForEach(Array(activities.enumerated()), id: \.element.id) { index, activity in
                Button {
                    selectedPlace = Place(from: activity)
                } label: {
                    activityRow(activity: activity, isLast: index == activities.count - 1)
                }
                .buttonStyle(PlainButtonStyle())
            }
        }
        .padding(14)
        .background(
            RoundedRectangle(cornerRadius: 20, style: .continuous)
                .fill(Color(.secondarySystemBackground))
        )
    }
    
    private func activityRow(activity: TripActivity, isLast: Bool) -> some View {
        HStack(alignment: .top, spacing: 12) {
            Text(activity.time)
                .font(.system(size: 14))
                .foregroundColor(Color(.secondaryLabel))
                .frame(width: 52, alignment: .leading)
            VStack {
                Circle()
                    .fill(color(for: activity.category))
                    .frame(width: 10, height: 10)
                    .overlay(
                        Circle()
                            .stroke(Color.white, lineWidth: 2)
                    )
                if !isLast {
                    Rectangle()
                        .fill(Color(.systemGray4))
                        .frame(width: 2)
                        .frame(maxHeight: .infinity)
                        .padding(.top, 2)
                }
            }
            .frame(width: 16)
            VStack(alignment: .leading, spacing: 6) {
                HStack(alignment: .top, spacing: 8) {
                    VStack(alignment: .leading, spacing: 4) {
                        Text(activity.title)
                            .font(.system(size: 15, weight: .semibold))
                            .foregroundColor(Color(.label))
                            .lineLimit(2)
                        Text(activity.description)
                            .font(.system(size: 13))
                            .foregroundColor(Color(.secondaryLabel))
                            .lineLimit(2)
                        if let note = activity.note {
                            Text(note)
                                .font(.system(size: 12, weight: .semibold))
                                .foregroundColor(Color(red: 1.0, green: 0.45, blue: 0.35))
                        }
                    }
                    Spacer()
                    VStack(alignment: .trailing, spacing: 8) {
                        categoryBadge(for: activity.category)
                        Image(systemName: "mappin.and.ellipse")
                            .font(.system(size: 15, weight: .semibold))
                            .foregroundColor(Color(.secondaryLabel))
                    }
                }
            }
        }
    }
    
    private var mapPlaceholder: some View {
        VStack(spacing: 0) {
            // Day selector for the map (same as route view)
            if let plan = viewModel.plan {
                daySelector(plan: plan)
                    .padding(.bottom, 12)
            }

            // Map or empty state
            if !viewModel.currentDayActivitiesWithCoordinates.isEmpty {
                RouteMapView(activities: viewModel.currentDayActivities)
                    .frame(height: 400)
                    .clipShape(RoundedRectangle(cornerRadius: 20, style: .continuous))
            } else {
                NoMapDataView()
                    .frame(height: 400)
                    .clipShape(RoundedRectangle(cornerRadius: 20, style: .continuous))
            }
        }
    }
    
    private var guideCTA: some View {
        VStack(spacing: 10) {
            Button {
                isShowingGuide = true
            } label: {
                Text("Начать путешествие с гидом")
                    .font(.system(size: 16, weight: .semibold))
                    .foregroundColor(.white)
                    .frame(maxWidth: .infinity)
                    .padding(.vertical, 16)
                    .background(
                        RoundedRectangle(cornerRadius: 16, style: .continuous)
                            .fill(
                                LinearGradient(
                                    colors: [
                                        Color(red: 1.0, green: 0.55, blue: 0.32),
                                        Color(red: 1.0, green: 0.38, blue: 0.32)
                                    ],
                                    startPoint: .leading,
                                    endPoint: .trailing
                                )
                            )
                    )
            }
            .buttonStyle(.plain)
            
            Text("Travel Buddy будет подсказывать места по плану и рядом с тобой.")
                .font(.system(size: 12))
                .foregroundColor(Color(.secondaryLabel))
                .multilineTextAlignment(.center)
        }
        .padding(.horizontal, 16)
        .padding(.top, 12)
        .padding(.bottom, 16)
        .background(
            Color(.systemBackground)
                .shadow(color: Color.black.opacity(0.08), radius: 12, x: 0, y: -2)
        )
    }
    
    private func categoryBadge(for category: TripActivityCategory) -> some View {
        Text(categoryTitle(for: category))
            .font(.system(size: 12, weight: .semibold))
            .padding(.horizontal, 10)
            .padding(.vertical, 4)
            .background(
                Capsule()
                    .fill(color(for: category).opacity(0.15))
            )
            .foregroundColor(color(for: category))
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
    
    private func color(for category: TripActivityCategory) -> Color {
        switch category {
        case .food: return Color(red: 1.0, green: 0.55, blue: 0.30)
        case .walk: return Color(red: 0.26, green: 0.66, blue: 0.45)
        case .museum: return Color(.systemIndigo)
        case .viewpoint: return Color(red: 0.15, green: 0.6, blue: 0.9)
        case .nightlife: return Color(red: 0.7, green: 0.4, blue: 0.9)
        case .other: return Color(.systemGray)
        }
    }
    
    private func dateRangeText(start: Date, end: Date) -> String {
        let formatter = DateFormatter()
        formatter.locale = Locale(identifier: "ru_RU")
        formatter.dateFormat = "d MMMM yyyy"
        return "\(formatter.string(from: start)) – \(formatter.string(from: end))"
    }
    
    private func dayDateText(_ date: Date) -> String {
        let formatter = DateFormatter()
        formatter.locale = Locale(identifier: "ru_RU")
        formatter.dateFormat = "d MMM"
        return formatter.string(from: date)
    }
    
    private func fullDateText(_ date: Date) -> String {
        let formatter = DateFormatter()
        formatter.locale = Locale(identifier: "ru_RU")
        formatter.dateFormat = "d MMMM, EEEE"
        return formatter.string(from: date)
    }
    
    private var guideNavigationLink: some View {
        NavigationLink(isActive: $isShowingGuide) {
            LiveGuideView()
        } label: {
            EmptyView()
        }
        .hidden()
    }
    
    private var editDayNavigationLink: some View {
        NavigationLink(isActive: $isShowingEditDay) {
            Group {
                if let editViewModel {
                    EditDayView(viewModel: editViewModel)
                } else {
                    EmptyView()
                }
            }
        } label: {
            EmptyView()
        }
        .hidden()
    }

    private var chatNavigationLink: some View {
        NavigationLink(isActive: $isShowingChat) {
            Group {
                if let chatViewModel {
                    ChatView(viewModel: chatViewModel)
                } else {
                    EmptyView()
                }
            }
        } label: {
            EmptyView()
        }
        .hidden()
    }
}

private extension Array {
    subscript(safe index: Index) -> Element? {
        indices.contains(index) ? self[index] : nil
    }
}

extension TripPlanView {
    private func openEdit(for day: TripDay) {
        guard let plan = viewModel.plan else { return }
        editViewModel = EditDayViewModel(
            day: day,
            destinationCity: plan.destinationCity,
            interestsSummary: plan.interestsSummary
        )
        isShowingEditDay = true
    }

    private func openChat() {
        guard let plan = viewModel.plan else { return }

        // Create ChatViewModel with the trip ID and plan update callback
        chatViewModel = ChatViewModel(
            tripId: plan.tripId,
            onPlanUpdateRequested: { [weak viewModel] in
                await viewModel?.updatePlanFromChat() ?? false
            }
        )
        isShowingChat = true
    }
}
