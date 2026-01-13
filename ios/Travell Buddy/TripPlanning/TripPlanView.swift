//
//  TripPlanView.swift
//  Travell Buddy
//
//  Renders the detailed day-by-day route following the premium dark design.
//

import SwiftUI

struct TripPlanView: View {
    @ObservedObject var viewModel: TripPlanViewModel
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
                        .padding(.bottom, ctaHeight + 16)
                    }
                    .scrollDisabled(isMapInteracting)
                }
                .onAppear {
                    print("📱 TripPlanView appeared with plan for city: \(plan.destinationCity)")
                    print("📱 Days count: \(plan.days.count)")
                    print("📱 Photo URL: \(String(describing: photoURL(for: plan.destinationCity)))")
                    print("📱 Selected tab: \(viewModel.selectedTab)")
                }
                .safeAreaInset(edge: .bottom) {
                    guideCTA(height: ctaHeight)
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
        .background(backgroundLayer.ignoresSafeArea())
        .navigationBarHidden(true)
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
                errorMessage: paywallError,
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
        let imageURL = photoURL(for: plan.destinationCity)

        return ZStack(alignment: .top) {
            ZStack(alignment: .bottomLeading) {
                if let imageURL {
                    RemoteImageView(url: imageURL)
                        .frame(maxWidth: .infinity)
                        .frame(height: heroHeight)
                        .clipped()
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
                    glassIconButton(systemName: "ellipsis") {
                        openChat()
                    }
                }
                .padding(.horizontal, 16)
                .padding(.top, 28)
                Spacer()
            }
        }
        .frame(height: heroHeight)
        .clipped()
    }

    private var tabSwitcher: some View {
        HStack(spacing: 6) {
            segmentButton(title: "Обзор", isSelected: viewModel.selectedTab == .overview) {
                withAnimation(.easeInOut(duration: 0.2)) {
                    viewModel.selectedTab = .overview
                }
            }
            segmentButton(title: "Маршрут", isSelected: viewModel.selectedTab == .route) {
                withAnimation(.easeInOut(duration: 0.2)) {
                    viewModel.selectedTab = .route
                }
            }
            segmentButton(title: "Карта", isSelected: viewModel.selectedTab == .map) {
                if viewModel.plan?.isLocked == true {
                    paywallError = "Карта доступна после входа"
                    viewModel.pendingIntent = .openMap
                    viewModel.isShowingPaywall = true
                } else {
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

            if plan.isLocked {
                LockedMapView {
                    paywallError = "Карта доступна после входа"
                    viewModel.pendingIntent = .openMap
                    viewModel.isShowingPaywall = true
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

    private func segmentButton(title: String, isSelected: Bool, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            Text(title)
                .font(.system(size: 13, weight: .semibold))
                .foregroundColor(isSelected ? .white : Color.white.opacity(0.55))
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
            let isLocked = plan.isLocked && dayNumber > 1
            return DayTabItem(id: dayNumber, date: date, isLocked: isLocked)
        }

        return ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: 10) {
                ForEach(dayTabs) { day in
                    let isSelected = day.id - 1 == viewModel.selectedDayIndex
                    Button {
                        if day.isLocked {
                            paywallError = "Полные дни доступны после входа"
                            viewModel.pendingIntent = .openDay(day.id)
                            viewModel.isShowingPaywall = true
                        } else {
                            viewModel.selectedDayIndex = day.id - 1
                        }
                    } label: {
                        Text("День \(day.id)")
                            .font(.system(size: 12, weight: .semibold))
                            .foregroundColor(isSelected ? Color.travelBuddyOrange : Color.white.opacity(0.6))
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
                Button {
                    selectedPlace = Place(from: activity)
                } label: {
                    activityRow(activity: activity, isLast: index == activities.count - 1)
                }
                .buttonStyle(.plain)
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
        ZStack {
            LinearGradient(
                colors: [
                    Color(red: 0.10, green: 0.10, blue: 0.12).opacity(0.0),
                    Color(red: 0.10, green: 0.10, blue: 0.12).opacity(0.85)
                ],
                startPoint: .top,
                endPoint: .bottom
            )
            Button {
                isShowingGuide = true
            } label: {
                HStack(spacing: 12) {
                    Image(systemName: "location.north.fill")
                        .font(.system(size: 14, weight: .semibold))
                        .foregroundColor(.white)
                        .frame(width: 32, height: 32)
                        .background(
                            Circle()
                                .fill(Color.white.opacity(0.2))
                        )
                    Text("Начать путешествие с гидом")
                        .font(.system(size: 15, weight: .semibold))
                        .foregroundColor(.white)
                    Spacer()
                    Image(systemName: "arrow.right")
                        .font(.system(size: 14, weight: .semibold))
                        .foregroundColor(.white)
                        .frame(width: 28, height: 28)
                        .background(
                            Circle()
                                .fill(Color.white.opacity(0.2))
                        )
                }
                .padding(.horizontal, 16)
                .frame(maxWidth: .infinity)
                .frame(height: height)
                .background(
                    RoundedRectangle(cornerRadius: 22, style: .continuous)
                        .fill(Color.travelBuddyOrange)
                )
            }
            .buttonStyle(.plain)
            .padding(.horizontal, 16)
        }
        .frame(height: height)
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

    private func photoURL(for city: String) -> URL? {
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
        aiStudioViewModel = AIStudioViewModel(
            tripId: plan.tripId,
            dayId: day.index,
            cityName: plan.destinationCity,
            dayDate: day.date
        )
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
}
