//
//  TripPlanView.swift
//  Travell Buddy
//
//  Renders the detailed day-by-day route following the premium dark design.
//

import SwiftUI

struct TripPlanView: View {
    @ObservedObject var viewModel: TripPlanViewModel
    @StateObject private var replaceManager = ReplacePlaceManager()
    @StateObject private var gatingManager = AuthGatingManager.shared
    @State private var isShowingGuide: Bool = false
    @State private var isShowingEditDay: Bool = false
    @State private var isShowingAIStudio: Bool = false
    @State private var isShowingChat: Bool = false
    @State private var editViewModel: EditDayViewModel?
    @State private var aiStudioViewModel: AIStudioViewModel?
    @State private var chatViewModel: ChatViewModel?
    @State private var selectedPlace: Place?
    @State private var showPaywall: Bool = false
    @State private var paywallError: String?
    @State private var isMapInteracting: Bool = false
    @State private var replaceSheetActivity: TripActivity?
    @State private var showSaveToast: Bool = false
    @State private var saveToastMessage: String = ""
    @State private var isTripAlreadySaved: Bool = false
    @State private var isSaving: Bool = false
    @StateObject private var savedTripsManager = SavedTripsManager.shared
    @Environment(\.dismiss) private var dismiss
    private let ctaHeight: CGFloat = 72

    var body: some View {
        Group {
            if let plan = viewModel.plan {
                ZStack {
                    backgroundLayer
                    ScrollView(showsIndicators: false) {
                        VStack(alignment: .leading, spacing: 14) {
                            Text("Маршрут поездки")
                                .font(.system(size: 18, weight: .semibold))
                                .foregroundColor(.white.opacity(0.8))
                            heroSection(plan: plan)
                            tabSwitcher
                            summaryStatsRow(summary: plan.summary)
                            tabContent(plan: plan)
                        }
                        .padding(.top, 12)
                        .padding(.horizontal, 16)
                        .padding(.bottom, 16)
                    }
                    .scrollDisabled(isMapInteracting)
                }
                .onAppear {
                    print("📱 TripPlanView appeared with plan for city: \(plan.destinationCity)")
                    print("📱 Days count: \(plan.days.count)")
                    print("📱 City Photo Reference: \(plan.cityPhotoReference ?? "nil")")
                    print("📱 Photo URL: \(String(describing: cityPhotoURL(for: plan)))")
                    print("📱 Selected tab: \(viewModel.selectedTab)")
                }
                .safeAreaInset(edge: .bottom, spacing: 0) {
                    // Show save button only if:
                    // 1. Trip is newly generated (not loaded from saved trips), OR
                    // 2. Trip was loaded from saved trips AND has unsaved changes
                    if !viewModel.isLoadedFromSavedTrip || viewModel.hasUnsavedChanges {
                        guideCTA(height: ctaHeight)
                    }
                }
                .background(editDayNavigationLink)
                .background(aiStudioNavigationLink)
                .background(guideNavigationLink)
            } else if viewModel.isLoading {
                VStack(spacing: 16) {
                    ProgressView()
                        .scaleEffect(1.4)
                    Text("Генерирую маршрут...")
                        .font(.system(size: 15, weight: .medium))
                        .foregroundColor(.white.opacity(0.7))
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity)
                .background(backgroundLayer)
                .onAppear {
                    print("📱 TripPlanView showing LOADING state")
                }
            } else if let error = viewModel.errorMessage {
                VStack(spacing: 16) {
                    Image(systemName: "exclamationmark.triangle.fill")
                        .font(.system(size: 44))
                        .foregroundColor(.orange)
                    Text("Ошибка")
                        .font(.system(size: 20, weight: .semibold))
                        .foregroundColor(.white)
                    Text(error)
                        .font(.system(size: 13))
                        .foregroundColor(.white.opacity(0.7))
                        .multilineTextAlignment(.center)
                        .padding(.horizontal, 40)
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity)
                .background(backgroundLayer)
                .onAppear {
                    print("📱 TripPlanView showing ERROR state: \(error)")
                }
            } else {
                VStack(spacing: 16) {
                    Image(systemName: "map.fill")
                        .font(.system(size: 42))
                        .foregroundColor(.white.opacity(0.5))
                    Text("Нет данных о маршруте")
                        .font(.system(size: 15, weight: .medium))
                        .foregroundColor(.white.opacity(0.7))
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity)
                .background(backgroundLayer)
                .onAppear {
                    print("📱 TripPlanView showing NO DATA state (plan=nil, isLoading=false, error=nil)")
                }
            }
        }
        .overlay(alignment: .top) {
            if showSaveToast {
                SaveToastView(message: saveToastMessage)
                    .transition(.move(edge: .top).combined(with: .opacity))
                    .zIndex(100)
            }
        }
        .background(backgroundLayer.ignoresSafeArea())
        .navigationBarHidden(true)
        .hideTabBar()
        .background(chatNavigationLink)
        .onChange(of: viewModel.isShowingPaywall) { newValue in
            showPaywall = newValue
        }
        .onChange(of: showPaywall) { newValue in
            if !newValue {
                viewModel.isShowingPaywall = false
            }
        }
        .sheet(isPresented: $showPaywall) {
            PaywallView(
                subtitle: paywallError,
                onAuthSuccess: {
                    handleAuthSuccess()
                }
            )
        }
        .sheet(item: $selectedPlace) { place in
            if let placeId = place.googlePlaceId {
                PlaceDetailsView(placeId: placeId, fallbackPlace: place)
                    .presentationDetents([.medium, .large])
                    .presentationDragIndicator(.visible)
                    .presentationCornerRadius(28)
                    .presentationBackground(
                        LinearGradient(
                            colors: [
                                Color(red: 0.14, green: 0.08, blue: 0.06),
                                Color(red: 0.10, green: 0.06, blue: 0.04)
                            ],
                            startPoint: .top,
                            endPoint: .bottom
                        )
                    )
            } else {
                MissingPlaceIdView(placeName: place.name)
                    .presentationDetents([.medium])
                    .presentationDragIndicator(.visible)
                    .presentationCornerRadius(28)
            }
        }
        .sheet(item: $replaceSheetActivity) { activity in
            ReplaceOptionsBottomSheet(
                currentActivityTitle: activity.title,
                dayIndex: viewModel.selectedDayIndex,
                stopIndex: findStopIndex(for: activity),
                options: replaceManager.currentOptions,
                onSelect: { option in
                    replaceManager.selectOption(option) { activityId, selectedOption in
                        replaceActivity(activityId: activityId, with: selectedOption)
                    }
                    replaceSheetActivity = nil
                },
                onCancel: {
                    replaceManager.cancel()
                    replaceSheetActivity = nil
                }
            )
            .presentationDetents([.fraction(0.85), .large])
            .presentationDragIndicator(.hidden)
            .presentationCornerRadius(28)
            .presentationBackground(
                LinearGradient(
                    colors: [
                        Color(red: 0.14, green: 0.08, blue: 0.06),
                        Color(red: 0.10, green: 0.06, blue: 0.04)
                    ],
                    startPoint: .top,
                    endPoint: .bottom
                )
            )
        }
        .onChange(of: replaceManager.state) { newState in
            // When state transitions to selecting, show the sheet
            if case .selecting(let activityId, _) = newState {
                if let activity = findActivity(by: activityId) {
                    replaceSheetActivity = activity
                }
            }
        }
        .onChange(of: isShowingEditDay) { newValue in
            if !newValue {
                editViewModel = nil
            }
        }
        .onChange(of: isShowingAIStudio) { newValue in
            if !newValue {
                aiStudioViewModel = nil
            }
        }
        .onChange(of: isShowingChat) { newValue in
            if !newValue {
                chatViewModel = nil
            }
        }
        // Auth gating modal for locked features (Map, Days 2+)
        .sheet(isPresented: $gatingManager.isAuthModalPresented) {
            PaywallView(
                subtitle: gatingManager.gatingMessage,
                dayNumber: gatingManager.pendingAction?.dayNumber,
                onAuthSuccess: {
                    gatingManager.handleAuthSuccess()
                }
            )
            .interactiveDismissDisabled(false)
            .onDisappear {
                // If modal dismissed without auth, cancel pending action
                if !AuthManager.shared.isAuthenticated {
                    gatingManager.cancelPendingAction()
                }
            }
        }
    }

    private var backgroundLayer: some View {
        ZStack {
            LinearGradient(
                colors: [
                    Color(red: 0.14, green: 0.08, blue: 0.06),
                    Color(red: 0.10, green: 0.06, blue: 0.04)
                ],
                startPoint: .top,
                endPoint: .bottom
            )
            .ignoresSafeArea()
            Image("noise")
                .resizable(resizingMode: .tile)
                .opacity(0.05)
                .blendMode(.softLight)
                .ignoresSafeArea()
        }
    }

    private func heroSection(plan: TripPlan) -> some View {
        let heroHeight: CGFloat = max(280, UIScreen.main.bounds.height * 0.42)
        let imageURL = cityPhotoURL(for: plan)

        return ZStack(alignment: .top) {
            ZStack(alignment: .bottomLeading) {
                if let imageURL {
                    RemoteImageView(url: imageURL)
                        .frame(maxWidth: .infinity)
                        .frame(height: heroHeight)
                } else {
                    LinearGradient(
                        colors: [
                            Color(red: 0.18, green: 0.20, blue: 0.24),
                            Color(red: 0.08, green: 0.09, blue: 0.12)
                        ],
                        startPoint: .topLeading,
                        endPoint: .bottomTrailing
                    )
                    .frame(maxWidth: .infinity)
                    .frame(height: heroHeight)
                }

                LinearGradient(
                    colors: [
                        Color.black.opacity(0.45),
                        Color.black.opacity(0.15),
                        Color(red: 0.10, green: 0.10, blue: 0.12)
                    ],
                    startPoint: .top,
                    endPoint: .bottom
                )
                .frame(maxWidth: .infinity)
                .frame(height: heroHeight)

                VStack(alignment: .leading, spacing: 6) {
                    Text(plan.destinationCity)
                        .font(.system(size: 28, weight: .semibold, design: .rounded))
                        .foregroundColor(.white)
                        .lineLimit(1)
                    Text("\(dateRangeText(start: plan.startDate, end: plan.endDate))  •  \(plan.travellersCount) путешественника")
                        .font(.system(size: 12, weight: .medium))
                        .foregroundColor(.white.opacity(0.65))
                }
                .padding(.horizontal, 16)
                .padding(.bottom, 14)
            }
            .clipShape(RoundedRectangle(cornerRadius: 26, style: .continuous))

            VStack(spacing: 0) {
                HStack(spacing: 10) {
                    glassIconButton(systemName: "chevron.left") {
                        dismiss()
                    }
                    Spacer()
                    glassIconButton(systemName: "square.and.arrow.up") {
                    }
                    glassIconButton(systemName: "bubble.left.fill") {
                        openChat()
                    }
                }
                .padding(.horizontal, 16)
                .padding(.top, 28)
                Spacer()
            }
        }
        .frame(height: heroHeight)
    }

    private var tabSwitcher: some View {
        HStack(spacing: 6) {
            segmentButton(title: "Обзор", isSelected: viewModel.selectedTab == .overview, isLocked: false) {
                withAnimation(.easeInOut(duration: 0.2)) {
                    viewModel.selectedTab = .overview
                }
            }
            segmentButton(title: "Маршрут", isSelected: viewModel.selectedTab == .route, isLocked: false) {
                withAnimation(.easeInOut(duration: 0.2)) {
                    viewModel.selectedTab = .route
                }
            }
            segmentButton(title: "Карта", isSelected: viewModel.selectedTab == .map, isLocked: gatingManager.isMapLocked()) {
                gatingManager.requireAuth(for: .viewMap) {
                    withAnimation(.easeInOut(duration: 0.2)) {
                        viewModel.selectedTab = .map
                    }
                }
            }
        }
        .padding(6)
        .background(
            Capsule()
                .fill(Color(red: 0.17, green: 0.17, blue: 0.18).opacity(0.7))
                .background(.ultraThinMaterial, in: Capsule())
        )
        .frame(maxWidth: 340)
        .frame(maxWidth: .infinity, alignment: .center)
        .shadow(color: Color.black.opacity(0.25), radius: 8, x: 0, y: 6)
    }

    private func tabContent(plan: TripPlan) -> some View {
        Group {
            switch viewModel.selectedTab {
            case .overview:
                TripOverviewContentView(trip: plan, viewModel: viewModel)
            case .route:
                TripRouteContentView {
                    routeContent(plan: plan)
                }
            case .map:
                TripMapContentView {
                    mapContent(plan: plan)
                }
            }
        }
    }

    private func routeContent(plan: TripPlan) -> some View {
        VStack(alignment: .leading, spacing: 18) {
            daySelector(plan: plan)
            if let day = plan.days[safe: viewModel.selectedDayIndex] ?? plan.days.first {
                dayHeader(day: day)
                activityTimeline(activities: day.activities)
            }
        }
    }

    private func mapContent(plan: TripPlan) -> some View {
        VStack(spacing: 14) {
            daySelector(plan: plan)

            if gatingManager.isMapLocked() {
                LockedMapView {
                    gatingManager.requireAuth(for: .viewMap) {
                        // Map will be shown after auth success
                    }
                }
                .frame(height: 360)
                .clipShape(RoundedRectangle(cornerRadius: 22, style: .continuous))
            } else if !viewModel.currentDayActivitiesWithCoordinates.isEmpty {
                TripInteractiveMapView(
                    activities: viewModel.currentDayActivitiesWithCoordinates,
                    fallbackCoordinate: plan.cityCoordinate,
                    isInteracting: $isMapInteracting
                )
                    .frame(height: 360)
                    .clipShape(RoundedRectangle(cornerRadius: 22, style: .continuous))
            } else {
                NoMapDataView()
                    .frame(height: 360)
                    .clipShape(RoundedRectangle(cornerRadius: 22, style: .continuous))
            }
        }
    }

    private func segmentButton(title: String, isSelected: Bool, isLocked: Bool = false, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            HStack(spacing: 4) {
                Text(title)
                    .font(.system(size: 13, weight: .semibold))
                    .foregroundColor(isSelected ? .white : Color.white.opacity(0.55))
                if isLocked {
                    Image(systemName: "lock.fill")
                        .font(.system(size: 9, weight: .semibold))
                        .foregroundColor(isSelected ? .white.opacity(0.7) : Color.white.opacity(0.4))
                }
            }
            .frame(maxWidth: .infinity)
            .padding(.vertical, 8)
            .background(
                Capsule()
                    .fill(isSelected ? Color.travelBuddyOrange : Color.clear)
            )
        }
        .buttonStyle(.plain)
    }

    private func summaryStatsRow(summary: TripSummary) -> some View {
        HStack(spacing: 10) {
            metricChip(icon: "map", text: summary.formattedTotalDistance)
            metricChip(icon: "figure.walk", text: summary.formattedTotalSteps)
            metricChip(icon: "creditcard", text: summary.formattedTotalCostRange)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    private func metricChip(icon: String, text: String) -> some View {
        HStack(spacing: 6) {
            Image(systemName: icon)
                .font(.system(size: 12, weight: .semibold))
                .foregroundColor(Color.travelBuddyOrange)
            Text(text)
                .font(.system(size: 12, weight: .semibold))
                .foregroundColor(.white.opacity(0.9))
        }
        .padding(.horizontal, 12)
        .padding(.vertical, 8)
        .background(
            Capsule()
                .fill(Color(red: 0.20, green: 0.20, blue: 0.22).opacity(0.7))
                .background(.ultraThinMaterial, in: Capsule())
        )
    }

    private func daySelector(plan: TripPlan) -> some View {
        struct DayTabItem: Identifiable {
            let id: Int
            let date: Date
            let isLocked: Bool
        }

        let totalDays = Calendar.current.dateComponents([.day], from: plan.startDate, to: plan.endDate).day ?? 0
        let daysCount = max(totalDays + 1, plan.days.count)
        let dayTabs: [DayTabItem] = (1...daysCount).compactMap { dayNumber in
            guard let date = Calendar.current.date(byAdding: .day, value: dayNumber - 1, to: plan.startDate) else {
                return nil
            }
            // Day 1 (dayNumber == 1) is always unlocked, Days 2+ require auth for guests
            let isLocked = gatingManager.isDayLocked(dayIndex: dayNumber - 1)
            return DayTabItem(id: dayNumber, date: date, isLocked: isLocked)
        }

        return ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: 10) {
                ForEach(dayTabs) { day in
                    let isSelected = day.id - 1 == viewModel.selectedDayIndex
                    Button {
                        let dayIndex = day.id - 1
                        if day.isLocked {
                            // Use gating manager for Day 2+
                            gatingManager.requireAuth(for: .viewDay(dayIndex: dayIndex)) {
                                viewModel.selectedDayIndex = dayIndex
                            }
                        } else {
                            viewModel.selectedDayIndex = dayIndex
                        }
                    } label: {
                        HStack(spacing: 4) {
                            Text("День \(day.id)")
                                .font(.system(size: 12, weight: .semibold))
                                .foregroundColor(isSelected ? Color.travelBuddyOrange : Color.white.opacity(0.6))
                            if day.isLocked {
                                Image(systemName: "lock.fill")
                                    .font(.system(size: 8, weight: .semibold))
                                    .foregroundColor(isSelected ? Color.travelBuddyOrange.opacity(0.7) : Color.white.opacity(0.4))
                            }
                        }
                        .padding(.horizontal, 14)
                        .padding(.vertical, 10)
                        .background(
                            Capsule()
                                .fill(isSelected ? Color.travelBuddyOrange.opacity(0.15) : Color(red: 0.20, green: 0.20, blue: 0.22).opacity(0.7))
                                .overlay(
                                    Capsule()
                                        .stroke(isSelected ? Color.travelBuddyOrange : Color.clear, lineWidth: 1.2)
                                )
                        )
                    }
                    .buttonStyle(.plain)
                }
            }
        }
    }

    private func dayHeader(day: TripDay) -> some View {
        HStack(alignment: .center) {
            VStack(alignment: .leading, spacing: 6) {
                Text(fullDateText(day.date))
                    .font(.system(size: 18, weight: .semibold))
                    .foregroundColor(.white)
                if let title = day.title {
                    Text(title)
                        .font(.system(size: 13, weight: .medium))
                        .foregroundColor(.white.opacity(0.6))
                        .lineLimit(2)
                }
            }
            Spacer()
            Button(action: {
                openEdit(for: day)
            }) {
                HStack(spacing: 6) {
                    Image(systemName: "slider.horizontal.3")
                        .font(.system(size: 12, weight: .semibold))
                    Text("Настроить")
                        .font(.system(size: 12, weight: .semibold))
                }
                .foregroundColor(Color.travelBuddyOrange)
                .padding(.horizontal, 12)
                .padding(.vertical, 8)
                .background(
                    Capsule()
                        .fill(Color.travelBuddyOrange.opacity(0.15))
                )
            }
            .buttonStyle(.plain)
        }
    }

    private func activityTimeline(activities: [TripActivity]) -> some View {
        VStack(alignment: .leading, spacing: 16) {
            ForEach(Array(activities.enumerated()), id: \.element.id) { index, activity in
                activityRowWithReplace(
                    activity: activity,
                    stopIndex: index,
                    isLast: index == activities.count - 1
                )
            }
        }
    }

    private func activityRow(activity: TripActivity, isLast: Bool) -> some View {
        HStack(alignment: .top, spacing: 12) {
            Text(activity.time)
                .font(.system(size: 13, weight: .semibold))
                .foregroundColor(.white.opacity(0.7))
                .frame(width: 54, alignment: .leading)

            timelineIndicator(isLast: isLast, color: color(for: activity.category))

            activityCard(activity: activity)
        }
    }

    private func timelineIndicator(isLast: Bool, color: Color) -> some View {
        VStack(spacing: 0) {
            Circle()
                .fill(color)
                .frame(width: 10, height: 10)
                .overlay(
                Circle()
                    .stroke(Color(red: 0.10, green: 0.10, blue: 0.12), lineWidth: 4)
            )
            if !isLast {
                Rectangle()
                    .stroke(style: StrokeStyle(lineWidth: 1, dash: [4, 5]))
                    .foregroundColor(Color.white.opacity(0.12))
                    .frame(width: 1)
                    .frame(maxHeight: .infinity)
                    .padding(.top, 6)
            }
        }
        .frame(width: 14)
    }

    private func activityCard(activity: TripActivity) -> some View {
        let showsThumbnail = activity.category == .museum || activity.category == .viewpoint || activity.category == .walk
        let isMustSee = activity.note?.localizedCaseInsensitiveContains("must") == true || activity.category == .museum
        let mealBadge = mealTitle(for: activity)

        return HStack(alignment: .top, spacing: 12) {
            if showsThumbnail {
                thumbnailView(category: activity.category)
            }
            VStack(alignment: .leading, spacing: 6) {
                if let mealBadge {
                    badge(text: mealBadge, tint: Color.white.opacity(0.12), textColor: .white.opacity(0.85))
                } else if isMustSee {
                    badge(text: "MUST SEE", tint: Color.travelBuddyOrange.opacity(0.18), textColor: Color.travelBuddyOrange)
                }
                Text(activity.title)
                    .font(.system(size: 15, weight: .semibold))
                    .foregroundColor(.white)
                    .lineLimit(2)
                Text(activity.description)
                    .font(.system(size: 12))
                    .foregroundColor(.white.opacity(0.65))
                    .lineLimit(2)
                if let note = activity.note {
                    Text(note)
                        .font(.system(size: 11, weight: .semibold))
                        .foregroundColor(Color.travelBuddyOrange)
                }
            }
            Spacer()
            Image(systemName: "mappin.and.ellipse")
                .font(.system(size: 14, weight: .semibold))
                .foregroundColor(.white.opacity(0.5))
        }
        .padding(14)
        .background(
            RoundedRectangle(cornerRadius: 20, style: .continuous)
                .fill(Color(red: 0.18, green: 0.18, blue: 0.20).opacity(0.7))
                .background(.ultraThinMaterial, in: RoundedRectangle(cornerRadius: 20, style: .continuous))
                .shadow(color: Color.black.opacity(0.25), radius: 12, x: 0, y: 8)
        )
    }

    private func thumbnailView(category: TripActivityCategory) -> some View {
        ZStack {
            LinearGradient(
                colors: [
                    color(for: category).opacity(0.9),
                    color(for: category).opacity(0.4)
                ],
                startPoint: .topLeading,
                endPoint: .bottomTrailing
            )
            Image(systemName: icon(for: category))
                .font(.system(size: 18, weight: .semibold))
                .foregroundColor(.white)
        }
        .frame(width: 44, height: 44)
        .clipShape(RoundedRectangle(cornerRadius: 12, style: .continuous))
    }

    private func badge(text: String, tint: Color, textColor: Color) -> some View {
        Text(text)
            .font(.system(size: 10, weight: .semibold))
            .foregroundColor(textColor)
            .padding(.horizontal, 8)
            .padding(.vertical, 4)
            .background(
                Capsule()
                    .fill(tint)
            )
    }

    private func guideCTA(height: CGFloat) -> some View {
        VStack(spacing: 0) {
            Button {
                handleSaveTripTap()
            } label: {
                HStack(spacing: 12) {
                    if isSaving {
                        ProgressView()
                            .tint(.white)
                            .frame(width: 32, height: 32)
                    } else {
                        Image(systemName: isTripAlreadySaved ? "checkmark" : "bookmark.fill")
                            .font(.system(size: 14, weight: .semibold))
                            .foregroundColor(.white)
                            .frame(width: 32, height: 32)
                            .background(
                                Circle()
                                    .fill(Color.white.opacity(0.2))
                            )
                    }
                    Text(isTripAlreadySaved ? "Маршрут сохранён" : "Сохранить маршрут")
                        .font(.system(size: 15, weight: .semibold))
                        .foregroundColor(.white)
                    Spacer()
                    if !isTripAlreadySaved && !isSaving {
                        Image(systemName: "arrow.right")
                            .font(.system(size: 14, weight: .semibold))
                            .foregroundColor(.white)
                            .frame(width: 28, height: 28)
                            .background(
                                Circle()
                                    .fill(Color.white.opacity(0.2))
                            )
                    }
                }
                .padding(.horizontal, 16)
                .frame(maxWidth: .infinity)
                .frame(height: height)
                .background(
                    RoundedRectangle(cornerRadius: 22, style: .continuous)
                        .fill(isTripAlreadySaved ? Color.green.opacity(0.8) : Color.travelBuddyOrange)
                )
            }
            .buttonStyle(.plain)
            .disabled(isSaving || isTripAlreadySaved)
            .padding(.horizontal, 16)
            .padding(.top, 12)
        }
        .background(
            LinearGradient(
                colors: [
                    Color(red: 0.10, green: 0.10, blue: 0.12).opacity(0.0),
                    Color(red: 0.10, green: 0.10, blue: 0.12).opacity(0.85)
                ],
                startPoint: .top,
                endPoint: .bottom
            )
            .ignoresSafeArea(edges: .bottom)
        )
    }

    private func handleSaveTripTap() {
        guard let plan = viewModel.plan else { return }

        let heroImageUrl = cityPhotoURL(for: plan)?.absoluteString

        if AuthManager.shared.isAuthenticated {
            // User is logged in - save directly
            performSaveTrip(plan: plan, heroImageUrl: heroImageUrl)
        } else {
            // Guest - show auth modal with pending action
            gatingManager.requireAuth(
                for: .saveTrip(
                    tripId: plan.tripId,
                    cityName: plan.destinationCity,
                    startDate: plan.startDate,
                    endDate: plan.endDate,
                    heroImageUrl: heroImageUrl
                )
            ) { [self] in
                // This callback is executed after successful auth
                performSaveTrip(plan: plan, heroImageUrl: heroImageUrl)
            }
        }
    }

    private func performSaveTrip(plan: TripPlan, heroImageUrl: String?) {
        isSaving = true

        Task {
            let result = await savedTripsManager.saveTrip(
                tripId: plan.tripId,
                cityName: plan.destinationCity,
                startDate: plan.startDate,
                endDate: plan.endDate,
                heroImageUrl: heroImageUrl
            )

            await MainActor.run {
                isSaving = false

                if let card = result {
                    isTripAlreadySaved = true
                    if card.alreadySaved {
                        saveToastMessage = "Маршрут уже сохранён"
                    } else {
                        saveToastMessage = "Маршрут успешно сохранён"
                    }
                    showToast()
                } else {
                    saveToastMessage = "Не удалось сохранить маршрут"
                    showToast()
                }
            }
        }
    }

    private func showToast() {
        withAnimation(.spring(response: 0.3, dampingFraction: 0.7)) {
            showSaveToast = true
        }

        // Auto-dismiss after 1.8s
        DispatchQueue.main.asyncAfter(deadline: .now() + 1.8) {
            withAnimation(.easeOut(duration: 0.3)) {
                showSaveToast = false
            }
        }
    }

    private func glassIconButton(systemName: String, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            Image(systemName: systemName)
                .font(.system(size: 14, weight: .semibold))
                .foregroundColor(.white)
                .frame(width: 40, height: 40)
                .background(Color.black.opacity(0.3), in: Circle())
                .overlay(
                    Circle()
                        .stroke(Color.white.opacity(0.12), lineWidth: 1)
                )
        }
        .buttonStyle(.plain)
    }

    private func dateRangeText(start: Date, end: Date) -> String {
        let formatter = DateFormatter()
        formatter.locale = Locale(identifier: "ru_RU")
        formatter.dateFormat = "d MMM"
        let yearFormatter = DateFormatter()
        yearFormatter.locale = Locale(identifier: "ru_RU")
        yearFormatter.dateFormat = "yyyy"
        return "\(formatter.string(from: start)) – \(formatter.string(from: end)) \(yearFormatter.string(from: end))"
    }

    private func fullDateText(_ date: Date) -> String {
        let formatter = DateFormatter()
        formatter.locale = Locale(identifier: "ru_RU")
        formatter.dateFormat = "EEEE, d MMM"
        return formatter.string(from: date).capitalized
    }

    private func mealTitle(for activity: TripActivity) -> String? {
        guard activity.category == .food else { return nil }
        let hour = Int(activity.time.prefix(2)) ?? 12
        switch hour {
        case 5..<11:
            return "Завтрак"
        case 11..<16:
            return "Обед"
        case 16..<22:
            return "Ужин"
        default:
            return "Еда"
        }
    }

    private func icon(for category: TripActivityCategory) -> String {
        switch category {
        case .food: return "fork.knife"
        case .walk: return "figure.walk"
        case .museum: return "building.columns"
        case .viewpoint: return "binoculars"
        case .nightlife: return "moon.stars.fill"
        case .other: return "star.fill"
        }
    }

    private func color(for category: TripActivityCategory) -> Color {
        switch category {
        case .food: return Color(red: 1.0, green: 0.55, blue: 0.30)
        case .walk: return Color(red: 0.26, green: 0.66, blue: 0.45)
        case .museum: return Color(red: 0.42, green: 0.48, blue: 0.95)
        case .viewpoint: return Color(red: 0.15, green: 0.6, blue: 0.9)
        case .nightlife: return Color(red: 0.7, green: 0.4, blue: 0.9)
        case .other: return Color(.systemGray)
        }
    }

    private func cityPhotoURL(for plan: TripPlan) -> URL? {
        // Priority 1: Use city photo reference from backend (Google Places)
        if let photoRef = plan.cityPhotoReference, !photoRef.isEmpty {
            // URL-encode the photo reference to handle special characters
            let encodedRef = photoRef.addingPercentEncoding(withAllowedCharacters: .urlPathAllowed) ?? photoRef
            let urlString = "\(AppConfig.baseURL)/places/photos/\(encodedRef)?max_width=1200"
            print("📸 Using backend city photo: \(urlString)")
            return URL(string: urlString)
        }

        // Priority 2: Fallback to hardcoded Unsplash photos for known cities
        return fallbackPhotoURL(for: plan.destinationCity)
    }

    private func fallbackPhotoURL(for city: String) -> URL? {
        let mapped: [String: String] = [
            "Париж": "https://images.unsplash.com/photo-1502602898657-3e91760cbb34?fit=crop&w=1200&q=80&fm=jpg",
            "Paris": "https://images.unsplash.com/photo-1502602898657-3e91760cbb34?fit=crop&w=1200&q=80&fm=jpg",
            "Стамбул": "https://images.unsplash.com/photo-1543946207-39bd91e70ca7?fit=crop&w=1200&q=80&fm=jpg",
            "Istanbul": "https://images.unsplash.com/photo-1543946207-39bd91e70ca7?fit=crop&w=1200&q=80&fm=jpg",
            "Цюрих": "https://images.unsplash.com/photo-1469474968028-56623f02e42e?fit=crop&w=1200&q=80&fm=jpg",
            "Zurich": "https://images.unsplash.com/photo-1469474968028-56623f02e42e?fit=crop&w=1200&q=80&fm=jpg",
            "Бали": "https://images.unsplash.com/photo-1537996194471-e657df975ab4?fit=crop&w=1200&q=80&fm=jpg",
            "Bali": "https://images.unsplash.com/photo-1537996194471-e657df975ab4?fit=crop&w=1200&q=80&fm=jpg",
            "Нью-Йорк": "https://images.unsplash.com/photo-1549924231-f129b911e442?fit=crop&w=1200&q=80&fm=jpg",
            "New York": "https://images.unsplash.com/photo-1549924231-f129b911e442?fit=crop&w=1200&q=80&fm=jpg"
        ]

        // Try exact match first
        if let urlString = mapped[city] {
            return URL(string: urlString)
        }

        // Extract clean city name (first part before comma) and try again
        let cleanCity = city.components(separatedBy: ",").first?.trimmingCharacters(in: .whitespaces) ?? city
        if let urlString = mapped[cleanCity] {
            return URL(string: urlString)
        }

        return nil
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

    private var aiStudioNavigationLink: some View {
        NavigationLink(isActive: $isShowingAIStudio) {
            Group {
                if let aiStudioViewModel {
                    AIStudioView(viewModel: aiStudioViewModel)
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

private struct TripRouteContentView<Content: View>: View {
    let content: Content

    init(@ViewBuilder content: () -> Content) {
        self.content = content()
    }

    var body: some View {
        content
    }
}

private struct TripMapContentView<Content: View>: View {
    let content: Content

    init(@ViewBuilder content: () -> Content) {
        self.content = content()
    }

    var body: some View {
        content
    }
}

private struct LockedMapView: View {
    let onUnlock: () -> Void

    var body: some View {
        VStack(spacing: 12) {
            Image(systemName: "lock.fill")
                .font(.system(size: 28, weight: .semibold))
                .foregroundColor(.orange)
            Text("Карта доступна после входа")
                .font(.system(size: 15, weight: .semibold))
                .foregroundColor(.white)
            Text("Авторизуйтесь, чтобы увидеть все точки маршрута на карте.")
                .font(.system(size: 13))
                .foregroundColor(.white.opacity(0.7))
                .multilineTextAlignment(.center)
                .padding(.horizontal, 24)
            Button(action: onUnlock) {
                Text("Разблокировать")
                    .font(.system(size: 14, weight: .semibold))
                    .foregroundColor(.white)
                    .padding(.horizontal, 18)
                    .padding(.vertical, 10)
                    .background(
                        Capsule()
                            .fill(Color.travelBuddyOrange)
                    )
            }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .background(Color.white.opacity(0.06))
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

        // Open AI Studio instead of legacy EditDayView
        let studioViewModel = AIStudioViewModel(
            tripId: plan.tripId,
            dayId: day.index,
            cityName: plan.destinationCity,
            dayDate: day.date
        )

        // Set callback to refresh itinerary when changes are applied
        studioViewModel.onChangesApplied = { [weak viewModel] in
            print("🔄 AI Studio changes applied - refreshing itinerary")
            _ = await viewModel?.refreshItinerary()
        }

        aiStudioViewModel = studioViewModel
        isShowingAIStudio = true
    }

    private func openLegacyEdit(for day: TripDay) {
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
        chatViewModel = ChatViewModel(
            tripId: plan.tripId,
            onPlanUpdateRequested: { [weak viewModel] in
                await viewModel?.updatePlanFromChat() ?? false
            }
        )
        isShowingChat = true
    }

    private func handleAuthSuccess() {
        showPaywall = false
        viewModel.isShowingPaywall = false
        guard let intent = viewModel.pendingIntent else { return }
        viewModel.pendingIntent = nil

        switch intent {
        case .generateTrip(let params):
            Task {
                await viewModel.generatePlan(
                    destinationCity: params.destinationCity,
                    startDate: params.startDate,
                    endDate: params.endDate,
                    selectedInterests: params.selectedInterests,
                    budgetLevel: params.budgetLevel,
                    travellersCount: params.travellersCount,
                    pace: params.pace
                )
            }
        case .openDay(let dayNumber):
            Task {
                let refreshed = await viewModel.refreshPlanAfterAuth()
                guard refreshed else { return }
                if let plan = viewModel.plan,
                   let index = plan.days.firstIndex(where: { $0.index == dayNumber }) {
                    viewModel.selectedDayIndex = index
                }
            }
        case .openMap:
            Task {
                let refreshed = await viewModel.refreshPlanAfterAuth()
                guard refreshed else { return }
                withAnimation(.easeInOut(duration: 0.2)) {
                    viewModel.selectedTab = .map
                }
            }
        }
    }

    // MARK: - Replace Place Flow

    private func activityRowWithReplace(activity: TripActivity, stopIndex: Int, isLast: Bool) -> some View {
        HStack(alignment: .top, spacing: 12) {
            Text(activity.time)
                .font(.system(size: 13, weight: .semibold))
                .foregroundColor(.white.opacity(0.7))
                .frame(width: 54, alignment: .leading)

            timelineIndicator(isLast: isLast, color: color(for: activity.category))

            ActivityCardWithReplace(
                activity: activity,
                dayIndex: viewModel.selectedDayIndex,
                stopIndex: stopIndex,
                isFinding: replaceManager.isActivityFinding(activity.id),
                showReplacedBadge: replaceManager.recentlyReplacedActivityId == activity.id,
                onTapCard: {
                    selectedPlace = Place(from: activity)
                },
                onTapReplace: {
                    handleReplaceTap(for: activity, stopIndex: stopIndex)
                }
            )
        }
    }

    private func handleReplaceTap(for activity: TripActivity, stopIndex: Int) {
        // If already finding for this activity, cancel it
        if replaceManager.isActivityFinding(activity.id) {
            replaceManager.cancel()
            return
        }

        // Start the replace flow
        replaceManager.startReplace(
            for: activity,
            dayIndex: viewModel.selectedDayIndex,
            stopIndex: stopIndex
        )
    }

    private func findActivity(by id: UUID) -> TripActivity? {
        guard let plan = viewModel.plan else { return nil }
        for day in plan.days {
            if let activity = day.activities.first(where: { $0.id == id }) {
                return activity
            }
        }
        return nil
    }

    private func findStopIndex(for activity: TripActivity) -> Int? {
        guard let plan = viewModel.plan,
              let day = plan.days[safe: viewModel.selectedDayIndex] else {
            return nil
        }
        return day.activities.firstIndex(where: { $0.id == activity.id })
    }

    private func replaceActivity(activityId: UUID, with option: ReplacementOption) {
        guard let plan = viewModel.plan,
              let dayIndex = plan.days.firstIndex(where: { day in
                  day.activities.contains(where: { $0.id == activityId })
              }),
              let activityIndex = plan.days[dayIndex].activities.firstIndex(where: { $0.id == activityId }) else {
            return
        }

        // Get the original activity to preserve time and travel info
        let original = plan.days[dayIndex].activities[activityIndex]

        // Create the replacement activity
        let replacement = TripActivity(
            id: UUID(), // New ID for the replacement
            time: original.time,
            endTime: original.endTime,
            title: option.title,
            description: option.address ?? option.subtitle,
            category: option.category,
            address: option.address,
            note: nil,
            latitude: option.latitude,
            longitude: option.longitude,
            travelPolyline: original.travelPolyline,
            rating: option.rating,
            tags: option.tags,
            poiId: option.poiId,
            travelTimeMinutes: original.travelTimeMinutes,
            travelDistanceMeters: original.travelDistanceMeters
        )

        // Update the plan with the replacement (with crossfade animation)
        withAnimation(.easeInOut(duration: 0.3)) {
            viewModel.replaceActivity(at: dayIndex, activityIndex: activityIndex, with: replacement)
        }
    }
}

// MARK: - Save Toast View

private struct SaveToastView: View {
    let message: String

    var body: some View {
        HStack(spacing: 10) {
            Image(systemName: "checkmark.circle.fill")
                .font(.system(size: 18, weight: .semibold))
                .foregroundColor(.green)

            Text(message)
                .font(.system(size: 14, weight: .semibold))
                .foregroundColor(.white)
        }
        .padding(.horizontal, 20)
        .padding(.vertical, 14)
        .background(
            Capsule()
                .fill(Color(red: 0.15, green: 0.15, blue: 0.17).opacity(0.95))
                .background(.ultraThinMaterial, in: Capsule())
                .shadow(color: Color.black.opacity(0.3), radius: 12, x: 0, y: 6)
        )
        .padding(.top, 60)
    }
}
