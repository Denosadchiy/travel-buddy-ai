//
//  NewTripView.swift
//  Travell Buddy
//
//  Screen for planning a new trip.
//

import SwiftUI
import MapKit

// MARK: - Route Building Data

struct RouteBuildingData: Identifiable {
    let id = UUID()
    let tripRequest: TripCreateRequestDTO
    let cityName: String
    let coordinate: CLLocationCoordinate2D
}

// MARK: - NewTripView

struct NewTripView: View {
    let prefilledTicket: FlightTicket?
    let isRootView: Bool

    @Environment(\.dismiss) private var dismiss

    @State private var selectedCity: String
    @State private var startDate: Date
    @State private var endDate: Date
    @State private var showDatePicker: Bool = false
    @State private var adultsCount: Int = 2
    @State private var childrenCount: Int = 0
    @State private var showTravelersPicker: Bool = false
    @State private var travelersSheetDetent: PresentationDetent = .height(520)
    @State private var selectedInterests: Set<String> = ["Гастро", "Искусство"]
    @State private var selectedCityCoordinate: CLLocationCoordinate2D?  // Coordinates from autocomplete

    // Route building state - using Identifiable item for fullScreenCover
    @State private var routeBuildingData: RouteBuildingData?
    @State private var pendingRouteBuildingData: RouteBuildingData?
    @State private var showPaywall: Bool = false
    @State private var paywallError: String?
    @State private var pendingTripPlanPresentation: Bool = false
    
    // Форматированная строка путешественников
    private var travelersText: String {
        var parts: [String] = []
        if adultsCount > 0 {
            let adultWord = adultsCount == 1 ? "взрослый" : adultsCount < 5 ? "взрослых" : "взрослых"
            parts.append("\(adultsCount) \(adultWord)")
        }
        if childrenCount > 0 {
            let childWord = childrenCount == 1 ? "ребёнок" : childrenCount < 5 ? "ребёнка" : "детей"
            parts.append("\(childrenCount) \(childWord)")
        }
        return parts.isEmpty ? "Выберите количество" : parts.joined(separator: ", ")
    }
    @State private var selectedBudget: String = "Комфорт"

    // NEW: Unified preferences draft
    @State private var preferencesDraft = PreferencesDraft()
    @State private var messageText: String = ""
    @FocusState private var isTextFieldFocused: Bool
    @State private var isShowingTripPlan: Bool = false
    @StateObject private var tripPlanViewModel = TripPlanViewModel()
    @State private var isGeneratingPlan: Bool = false
    @State private var planGenerationError: String?
    @State private var showErrorAlert: Bool = false

    private let warmWhite = Color(red: 0.95, green: 0.94, blue: 0.92)
    private let mutedWarmGray = Color(red: 0.70, green: 0.67, blue: 0.63)
    private let glassFill = Color.white.opacity(0.08)
    private let glassBorder = Color.white.opacity(0.14)
    private var isPreview: Bool {
        ProcessInfo.processInfo.environment["XCODE_RUNNING_FOR_PREVIEWS"] == "1"
    }

    let popularCities = ["Париж", "Рим", "Дубай", "Москва", "Лондон", "Барселона", "Пекин"]

    // MARK: - Init

    init(prefilledTicket: FlightTicket? = nil, isRootView: Bool = false) {
        self.prefilledTicket = prefilledTicket
        self.isRootView = isRootView

        // Всегда инициализируем с дефолтными значениями
        // Реальные значения из билета установятся в .onAppear
        let calendar = Calendar.current
        let defaultStart = calendar.date(byAdding: .day, value: 1, to: Date()) ?? Date()
        let defaultEnd = calendar.date(byAdding: .day, value: 6, to: defaultStart) ?? Date()

        _selectedCity = State(initialValue: "Париж")
        _startDate = State(initialValue: defaultStart)
        _endDate = State(initialValue: defaultEnd)
    }

    // Форматированная строка дат
    private var formattedDates: String {
        let formatter = DateFormatter()
        formatter.locale = Locale(identifier: "ru_RU")
        formatter.dateFormat = "d MMMM yyyy"
        
        let startDay = Calendar.current.component(.day, from: startDate)
        let endDay = Calendar.current.component(.day, from: endDate)
        let startMonth = Calendar.current.component(.month, from: startDate)
        let endMonth = Calendar.current.component(.month, from: endDate)
        let year = Calendar.current.component(.year, from: startDate)
        
        if Calendar.current.isDate(startDate, equalTo: endDate, toGranularity: .month) {
            let monthName = formatter.monthSymbols[startMonth - 1].lowercased()
            let capitalizedMonth = monthName.prefix(1).uppercased() + monthName.dropFirst()
            return "\(startDay)–\(endDay) \(capitalizedMonth) \(year)"
        } else if Calendar.current.isDate(startDate, equalTo: endDate, toGranularity: .year) {
            let startMonthName = formatter.monthSymbols[startMonth - 1].lowercased()
            let endMonthName = formatter.monthSymbols[endMonth - 1].lowercased()
            let capitalizedStartMonth = startMonthName.prefix(1).uppercased() + startMonthName.dropFirst()
            let capitalizedEndMonth = endMonthName.prefix(1).uppercased() + endMonthName.dropFirst()
            return "\(startDay) \(capitalizedStartMonth) – \(endDay) \(capitalizedEndMonth) \(year)"
        } else {
            let startFormatted = formatter.string(from: startDate)
            let endFormatted = formatter.string(from: endDate)
            return "\(startFormatted) – \(endFormatted)"
        }
    }
    
    var body: some View {
        ZStack {
            SmokyBackgroundView()

            ScrollViewReader { scrollProxy in
                ScrollView {
                    VStack(alignment: .leading, spacing: 22) {
                        headerSection

                        // Секция: Город / Направление
                        citySection

                        // Секция: Даты поездки + Путешественники
                        datesTravelersSection

                        // Секция: Интересы
                        interestsSection

                        // Секция: Уровень бюджета
                        budgetSection

                        // Секция: Пожелания к поездке
                        wishesCard

                        // Кнопка "Спланировать поездку"
                        planTripButton
                            .padding(.top, 8)
                    }
                    .padding(.horizontal, 20)
                    .padding(.top, 14)
                    .padding(.bottom, isRootView ? 28 + HomeStyle.Layout.tabBarHeight : 28)
                }
                .onChange(of: isTextFieldFocused) { focused in
                    if focused {
                        // Scroll to wishes card when it's focused/expanded
                        // Delay to allow expansion animation to start
                        DispatchQueue.main.asyncAfter(deadline: .now() + 0.15) {
                            withAnimation(.spring(response: 0.5, dampingFraction: 0.85)) {
                                // Use center anchor for more natural scroll position
                                scrollProxy.scrollTo("wishes-card", anchor: .center)
                            }
                        }
                    }
                }
            }
        }
        .modifier(ConditionalHideTabBarModifier(shouldHide: !isRootView))
        .fullScreenCover(isPresented: $isShowingTripPlan) {
            if isPreview {
                EmptyView()
            } else {
                NavigationStack {
                    TripPlanView(viewModel: tripPlanViewModel)
                }
            }
        }
        .background(NavigationPopEnabler())
        .navigationBarHidden(true)
        .onAppear {
            // Предзаполнить данные из билета при первом появлении view
            if let ticket = prefilledTicket {
                let planning = ticket.tripPlanningData
                selectedCity = planning.destinationCity
                startDate = planning.startDate
                endDate = planning.endDate
            }
        }
        .onChange(of: selectedInterests) { newInterests in
            // Sync interests to preferences draft
            preferencesDraft.selectedTags = newInterests
        }
        .onChange(of: messageText) { newText in
            // Sync unsent message text to freeText
            preferencesDraft.freeText = newText
        }
        .fullScreenCover(item: $routeBuildingData, onDismiss: {
            guard pendingTripPlanPresentation else { return }
            pendingTripPlanPresentation = false
            isShowingTripPlan = true
        }) { data in
            RouteBuildingView(
                cityName: data.cityName,
                cityCoordinate: data.coordinate,
                tripRequest: data.tripRequest,
                onRouteReady: { itinerary in
                    Task { @MainActor in
                        // Создаём TripPlan из itinerary
                        tripPlanViewModel.plan = itinerary.toTripPlan(
                            destinationCity: data.cityName,
                            budget: selectedBudget,
                            interests: Array(selectedInterests).sorted(),
                            travelersCount: adultsCount + childrenCount,
                            expectedStartDate: startDate,
                            expectedEndDate: endDate
                        )

                        // Показываем экран плана после закрытия cover
                        pendingTripPlanPresentation = true
                        // Закрываем экран загрузки
                        routeBuildingData = nil
                    }
                },
                onRetry: {
                    Task { @MainActor in
                        // Закрываем и показываем ошибку
                        routeBuildingData = nil
                        planGenerationError = "Не удалось сгенерировать маршрут. Попробуйте ещё раз."
                        showErrorAlert = true
                    }
                },
                onPaywallRequired: {
                    Task { @MainActor in
                        pendingRouteBuildingData = data
                        routeBuildingData = nil
                        paywallError = "Второе построение доступно после входа"
                        showPaywall = true
                    }
                }
            )
        }
        .sheet(isPresented: $showPaywall) {
            PaywallView(
                subtitle: paywallError,
                onAuthSuccess: {
                    showPaywall = false
                    if let pendingRouteBuildingData {
                        routeBuildingData = pendingRouteBuildingData
                        self.pendingRouteBuildingData = nil
                    }
                }
            )
        }
    }

    // MARK: Header

    private var headerSection: some View {
        HStack {
            Button(action: { handleClose() }) {
                Image(systemName: "xmark")
                    .font(.system(size: 16, weight: .semibold))
                    .foregroundColor(mutedWarmGray)
                    .frame(width: 32, height: 32)
            }
            .buttonStyle(.plain)

            Spacer()
        }
        .overlay(
            Text("Новая поездка")
                .font(.system(size: 17, weight: .semibold, design: .rounded))
                .foregroundColor(warmWhite)
        )
        .padding(.top, 6)
    }

    private func handleClose() {
        if isRootView {
            NotificationCenter.default.post(name: .mainTabSelectionRequested, object: MainTab.home)
        } else {
            dismiss()
        }
    }

    // MARK: City Section

    private var citySection: some View {
        VStack(alignment: .leading, spacing: 14) {
            DestinationAutocompleteField(
                cityName: $selectedCity,
                placeholder: "Куда поедем?",
                onCitySelected: { result in
                    // Save coordinates from autocomplete selection
                    if let coordinate = result.coordinate {
                        print("📍 City selected from autocomplete: \(result.name) at \(coordinate.latitude), \(coordinate.longitude)")
                        selectedCityCoordinate = coordinate
                    }
                }
            )
            .zIndex(10)

            ScrollView(.horizontal, showsIndicators: false) {
                HStack(spacing: 10) {
                    ForEach(popularCities, id: \.self) { city in
                        Button(action: {
                            selectedCity = city
                            // Clear autocomplete coordinates when selecting from popular cities
                            // (will use defaultCoordinate fallback)
                            selectedCityCoordinate = nil
                        }) {
                            Text(city)
                                .font(.system(size: 14, weight: .medium, design: .rounded))
                                .foregroundColor(selectedCity == city ? Color.travelBuddyOrange : warmWhite)
                                .padding(.horizontal, 14)
                                .padding(.vertical, 8)
                                .background(
                                    RoundedRectangle(cornerRadius: 18, style: .continuous)
                                        .fill(selectedCity == city ? Color.travelBuddyOrange.opacity(0.12) : glassFill)
                                )
                                .overlay(
                                    RoundedRectangle(cornerRadius: 18, style: .continuous)
                                        .stroke(selectedCity == city ? Color.travelBuddyOrange : glassBorder, lineWidth: 1)
                                )
                        }
                        .buttonStyle(.plain)
                    }
                }
                .padding(.vertical, 2)
            }
        }
    }
    
    // MARK: Dates & Travelers Section

    private var datesTravelersSection: some View {
        HStack(spacing: 14) {
            infoCard(
                title: "ДАТЫ",
                value: formattedDates,
                systemImage: "calendar"
            ) {
                showDatePicker = true
            }

            infoCard(
                title: "ПУТЕШЕСТВЕННИКИ",
                value: travelersText,
                systemImage: "person.2.fill"
            ) {
                showTravelersPicker = true
            }
        }
        .sheet(isPresented: $showDatePicker) {
            DatePickerSheet(
                startDate: $startDate,
                endDate: $endDate,
                isPresented: $showDatePicker
            )
        }
        .sheet(isPresented: $showTravelersPicker) {
            TravelersPickerSheet(
                adultsCount: $adultsCount,
                childrenCount: $childrenCount,
                isPresented: $showTravelersPicker
            )
            .presentationDetents([.height(520), .large], selection: $travelersSheetDetent)
            .presentationDragIndicator(.visible)
        }
    }
    
    // MARK: Interests Section

    private var interestsSection: some View {
        let baseInterests: [(title: String, icon: String, color: Color)] = [
            ("Гастро", "fork.knife", Color(red: 1.0, green: 0.4, blue: 0.4)),
            ("Пляж", "sun.max.fill", Color(red: 1.0, green: 0.8, blue: 0.3)),
            ("Искусство", "paintpalette.fill", Color(red: 0.4, green: 0.6, blue: 1.0)),
            ("Шопинг", "bag.fill", Color(red: 0.95, green: 0.6, blue: 0.2)),
            ("История", "building.columns", Color(.systemGray)),
            ("Спорт", "figure.run", Color(red: 0.2, green: 0.7, blue: 0.4)),
            ("Природа", "leaf.fill", Color(red: 0.2, green: 0.7, blue: 0.7)),
            ("Горы", "mountain.2.fill", Color(.systemIndigo)),
            ("Тусовки", "sparkles", Color(red: 0.7, green: 0.4, blue: 0.9))
        ]

        return VStack(alignment: .leading, spacing: 14) {
            Text("Что вам интересно?")
                .font(.system(size: 18, weight: .semibold, design: .rounded))
                .foregroundColor(warmWhite)

            // Сетка с интересами (адаптивно, без перегрузки)
            LazyVGrid(
                columns: [
                    GridItem(.flexible(), spacing: 12),
                    GridItem(.flexible(), spacing: 12),
                    GridItem(.flexible(), spacing: 12)
                ],
                spacing: 12
            ) {
                ForEach(baseInterests, id: \.title) { item in
                    InterestButton(
                        title: item.title,
                        icon: item.icon,
                        color: item.color,
                        isSelected: selectedInterests.contains(item.title)
                    ) {
                        toggleInterest(item.title)
                    }
                }
            }
        }
    }

    private func toggleInterest(_ interest: String) {
        if selectedInterests.contains(interest) {
            selectedInterests.remove(interest)
        } else {
            selectedInterests.insert(interest)
        }
    }

    // MARK: Info Card

    private func infoCard(title: String, value: String, systemImage: String, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            VStack(alignment: .leading, spacing: 10) {
                HStack(spacing: 8) {
                    Image(systemName: systemImage)
                        .font(.system(size: 14, weight: .semibold))
                        .foregroundColor(mutedWarmGray)

                    Text(title)
                        .font(.system(size: 12, weight: .semibold, design: .rounded))
                        .foregroundColor(mutedWarmGray)
                        .textCase(.uppercase)
                }

                Text(value)
                    .font(.system(size: 15, weight: .semibold, design: .rounded))
                    .foregroundColor(warmWhite)
                    .lineLimit(2)
            }
            .frame(maxWidth: .infinity, minHeight: 86, alignment: .leading)
            .padding(14)
            .background(
                RoundedRectangle(cornerRadius: 20, style: .continuous)
                    .fill(glassFill)
            )
            .overlay(
                RoundedRectangle(cornerRadius: 20, style: .continuous)
                    .stroke(glassBorder, lineWidth: 1)
            )
        }
        .buttonStyle(.plain)
    }

    // MARK: Budget Section
    
    private var budgetSection: some View {
        let budgets = ["Эконом", "Комфорт", "Люкс"]

        return VStack(alignment: .leading, spacing: 12) {
            Text("Бюджет")
                .font(.system(size: 18, weight: .semibold, design: .rounded))
                .foregroundColor(warmWhite)

            HStack(spacing: 6) {
                ForEach(budgets, id: \.self) { budget in
                    let isSelected = selectedBudget == budget
                    Button {
                        selectedBudget = budget
                    } label: {
                        Text(budget)
                            .font(.system(size: 14, weight: .semibold, design: .rounded))
                            .foregroundColor(isSelected ? warmWhite : mutedWarmGray)
                            .frame(maxWidth: .infinity)
                            .padding(.vertical, 8)
                            .background(
                                Capsule()
                                    .fill(Color.white.opacity(0.06))
                                    .overlay(
                                        Capsule()
                                            .fill(
                                                LinearGradient(
                                                    colors: [
                                                        Color.travelBuddyOrange.opacity(0.22),
                                                        Color.travelBuddyOrange.opacity(0.08)
                                                    ],
                                                    startPoint: .topLeading,
                                                    endPoint: .bottomTrailing
                                                )
                                            )
                                            .opacity(isSelected ? 1 : 0)
                                    )
                            )
                            .overlay(
                                Capsule()
                                    .stroke(isSelected ? Color.travelBuddyOrange : Color.white.opacity(0.14), lineWidth: 1)
                            )
                    }
                    .buttonStyle(.plain)
                }
            }
            .padding(6)
            .background(
                RoundedRectangle(cornerRadius: 20, style: .continuous)
                    .fill(glassFill)
            )
            .overlay(
                RoundedRectangle(cornerRadius: 20, style: .continuous)
                    .stroke(glassBorder, lineWidth: 1)
            )
        }
    }
    
    // MARK: Wishes Card

    private var wishesCard: some View {
        ExpandableWishesCard(
            messageText: $messageText,
            preferencesDraft: $preferencesDraft,
            isTextFieldFocused: $isTextFieldFocused,
            tripId: nil  // Demo mode - no backend required
        )
    }
    
    // MARK: Plan Trip Button

    private var planTripButton: some View {
        Button(action: {
            print("🟢 PlanTrip button tapped")
            openTripPlan()
        }) {
            HStack(spacing: 12) {
                if tripPlanViewModel.isLoading {
                    ProgressView()
                        .progressViewStyle(CircularProgressViewStyle(tint: .white))
                        .scaleEffect(0.9)
                } else {
                    Image(systemName: "sparkles")
                        .font(.system(size: 20, weight: .semibold))
                        .foregroundColor(.white)
                }

                Text(tripPlanViewModel.isLoading ? "Генерирую маршрут..." : "Сгенерировать маршрут")
                    .font(.system(size: 18, weight: .semibold, design: .rounded))
                    .foregroundColor(.white)
            }
            .frame(maxWidth: .infinity)
            .padding(.vertical, 16)
            .background(
                Capsule()
                    .fill(Color.travelBuddyOrange)
            )
            .shadow(color: Color.travelBuddyOrange.opacity(0.35), radius: 12, x: 0, y: 6)
        }
        .buttonStyle(.plain)
        .disabled(tripPlanViewModel.isLoading)
        .opacity(tripPlanViewModel.isLoading ? 0.7 : 1.0)
        .alert("Ошибка создания маршрута", isPresented: $showErrorAlert) {
            Button("Повторить") {
                retryPlanGeneration()
            }
            Button("Закрыть", role: .cancel) {
                showErrorAlert = false
            }
        } message: {
            Text(planGenerationError ?? "Произошла неизвестная ошибка")
        }
    }

    private func openTripPlan() {
        print("🚀 openTripPlan called for city: \(selectedCity)")
        print("🧭 Params: start=\(startDate) end=\(endDate) travelers=\(adultsCount + childrenCount) budget=\(selectedBudget) interests=\(Array(selectedInterests).sorted())")

        // Use coordinates from autocomplete if available, otherwise fallback to default
        let coordinate: CLLocationCoordinate2D
        if let autocompleteCoordinate = selectedCityCoordinate {
            coordinate = autocompleteCoordinate
            print("📍 Using autocomplete coordinate: \(coordinate.latitude), \(coordinate.longitude)")
        } else {
            coordinate = Self.defaultCoordinate(for: selectedCity)
            print("📍 Using default coordinate: \(coordinate.latitude), \(coordinate.longitude)")
        }

        // Format dates as YYYY-MM-DD
        let dateFormatter = DateFormatter()
        dateFormatter.dateFormat = "yyyy-MM-dd"
        let startDateString = dateFormatter.string(from: startDate)
        let endDateString = dateFormatter.string(from: endDate)

        // Build combined wishes text from all sources
        let wishesPayload = preferencesDraft.buildWishesPayload()
        print("📝 Wishes payload:")
        print("   - Free text: '\(preferencesDraft.freeText)'")
        print("   - Chat messages: \(preferencesDraft.chatMessages.count)")
        print("   - Selected tags: \(preferencesDraft.selectedTags)")
        print("   - Combined payload: '\(wishesPayload)'")

        // Build trip request
        let tripRequest = TripCreateRequestDTO(
            city: selectedCity,
            startDate: startDateString,
            endDate: endDateString,
            numTravelers: adultsCount + childrenCount,
            pace: "medium",
            budget: mapBudgetToAPI(selectedBudget),
            interests: Array(selectedInterests).sorted(),
            dailyRoutine: nil,
            hotelLocation: nil,
            additionalPreferences: wishesPayload.isEmpty ? nil : ["wishes": wishesPayload]
        )

        // Show RouteBuildingView IMMEDIATELY with tripRequest
        // Trip creation will happen inside RouteBuildingViewModel
        self.routeBuildingData = RouteBuildingData(
            tripRequest: tripRequest,
            cityName: selectedCity,
            coordinate: coordinate
        )

        print("✅ Showing route building view immediately")
    }

    private static func defaultCoordinate(for city: String) -> CLLocationCoordinate2D {
        // Common city coordinates - MUST include all popularCities!
        let cityCoordinates: [String: CLLocationCoordinate2D] = [
            // Popular cities (from popularCities array)
            "Париж": CLLocationCoordinate2D(latitude: 48.8566, longitude: 2.3522),
            "Рим": CLLocationCoordinate2D(latitude: 41.9028, longitude: 12.4964),
            "Дубай": CLLocationCoordinate2D(latitude: 25.2048, longitude: 55.2708),
            "Москва": CLLocationCoordinate2D(latitude: 55.7558, longitude: 37.6173),
            "Лондон": CLLocationCoordinate2D(latitude: 51.5074, longitude: -0.1278),
            "Барселона": CLLocationCoordinate2D(latitude: 41.3851, longitude: 2.1734),
            "Пекин": CLLocationCoordinate2D(latitude: 39.9042, longitude: 116.4074),
            // English names
            "Paris": CLLocationCoordinate2D(latitude: 48.8566, longitude: 2.3522),
            "Rome": CLLocationCoordinate2D(latitude: 41.9028, longitude: 12.4964),
            "Dubai": CLLocationCoordinate2D(latitude: 25.2048, longitude: 55.2708),
            "Moscow": CLLocationCoordinate2D(latitude: 55.7558, longitude: 37.6173),
            "London": CLLocationCoordinate2D(latitude: 51.5074, longitude: -0.1278),
            "Barcelona": CLLocationCoordinate2D(latitude: 41.3851, longitude: 2.1734),
            "Beijing": CLLocationCoordinate2D(latitude: 39.9042, longitude: 116.4074),
            // Other common cities
            "Стамбул": CLLocationCoordinate2D(latitude: 41.0082, longitude: 28.9784),
            "Istanbul": CLLocationCoordinate2D(latitude: 41.0082, longitude: 28.9784),
            "Бали": CLLocationCoordinate2D(latitude: -8.3405, longitude: 115.0920),
            "Bali": CLLocationCoordinate2D(latitude: -8.3405, longitude: 115.0920),
            "Тбилиси": CLLocationCoordinate2D(latitude: 41.7151, longitude: 44.8271),
            "Tbilisi": CLLocationCoordinate2D(latitude: 41.7151, longitude: 44.8271),
            "Нью-Йорк": CLLocationCoordinate2D(latitude: 40.7128, longitude: -74.0060),
            "New York": CLLocationCoordinate2D(latitude: 40.7128, longitude: -74.0060),
        ]

        if let coordinate = cityCoordinates[city] {
            print("📍 defaultCoordinate: found mapping for '\(city)' -> \(coordinate.latitude), \(coordinate.longitude)")
            return coordinate
        } else {
            print("⚠️ defaultCoordinate: NO MAPPING for '\(city)', using Paris as default")
            // Use Paris as default (more central in Europe than Rome)
            return CLLocationCoordinate2D(latitude: 48.8566, longitude: 2.3522)
        }
    }

    private func mapBudgetToAPI(_ budget: String) -> String {
        switch budget {
        case "Эконом": return "low"
        case "Комфорт": return "medium"
        case "Премиум", "Люкс": return "high"
        default: return "medium"
        }
    }

    private func retryPlanGeneration() {
        // Retry using stored parameters
        Task {
            await tripPlanViewModel.retryLastGeneration()

            await MainActor.run {
                if tripPlanViewModel.plan != nil {
                    isShowingTripPlan = true
                } else if let error = tripPlanViewModel.errorMessage {
                    planGenerationError = error
                    showErrorAlert = true
                }
            }
        }
    }
}
