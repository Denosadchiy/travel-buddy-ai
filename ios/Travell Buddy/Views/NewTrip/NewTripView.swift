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
    let tripId: UUID
    let cityName: String
    let coordinate: CLLocationCoordinate2D
}

// MARK: - NewTripView

struct NewTripView: View {
    let prefilledTicket: FlightTicket?

    @Environment(\.dismiss) private var dismiss

    @State private var selectedCity: String
    @State private var startDate: Date
    @State private var endDate: Date
    @State private var showDatePicker: Bool = false
    @State private var adultsCount: Int = 1
    @State private var childrenCount: Int = 0
    @State private var showTravelersPicker: Bool = false
    @State private var selectedInterests: Set<String> = ["Гастро", "Искусство"]

    // Route building state - using Identifiable item for fullScreenCover
    @State private var routeBuildingData: RouteBuildingData?
    @State private var pendingRouteBuildingData: RouteBuildingData?
    @State private var showPaywall: Bool = false
    @State private var paywallError: String?
    
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
    @State private var chatMessages: [ChatMessage] = [
        ChatMessage(
            id: UUID(),
            text: "Расскажи мне о своих пожеланиях: любишь ли ты много ходить, хочешь больше музеев или баров, есть ли ограничения?",
            isFromUser: false,
            timestamp: Date()
        )
    ]
    @State private var messageText: String = ""
    @FocusState private var isTextFieldFocused: Bool
    @State private var isShowingTripPlan: Bool = false
    @State private var tripPlanViewModel: TripPlanViewModel?
    @State private var isGeneratingPlan: Bool = false
    @State private var planGenerationError: String?
    @State private var showErrorAlert: Bool = false
    @State private var currentTripId: UUID?  // Хранит ID созданной поездки для чата

    private let warmWhite = Color(red: 0.95, green: 0.94, blue: 0.92)
    private let mutedWarmGray = Color(red: 0.70, green: 0.67, blue: 0.63)
    private let glassFill = Color.white.opacity(0.08)
    private let glassBorder = Color.white.opacity(0.14)

    let popularCities = ["Париж", "Бали", "Нью-Йорк"]

    // MARK: - Init

    init(prefilledTicket: FlightTicket? = nil) {
        self.prefilledTicket = prefilledTicket

        // Всегда инициализируем с дефолтными значениями
        // Реальные значения из билета установятся в .onAppear
        let calendar = Calendar.current
        let defaultStart = calendar.date(byAdding: .day, value: 1, to: Date()) ?? Date()
        let defaultEnd = calendar.date(byAdding: .day, value: 6, to: defaultStart) ?? Date()

        _selectedCity = State(initialValue: "Бали")
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
                .padding(.bottom, 28)
            }
        }
        .background(tripPlanNavigationLink)
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
        .fullScreenCover(item: $routeBuildingData) { data in
            RouteBuildingView(
                cityName: data.cityName,
                cityCoordinate: data.coordinate,
                tripId: data.tripId,
                onRouteReady: { itinerary in
                    // Закрываем экран загрузки
                    routeBuildingData = nil

                    // Создаём TripPlan из itinerary
                    if tripPlanViewModel == nil {
                        tripPlanViewModel = TripPlanViewModel()
                    }

                    tripPlanViewModel?.plan = itinerary.toTripPlan(
                        destinationCity: data.cityName,
                        budget: selectedBudget,
                        interests: Array(selectedInterests).sorted(),
                        travelersCount: adultsCount + childrenCount,
                        expectedStartDate: startDate,
                        expectedEndDate: endDate
                    )

                    // Показываем экран плана
                    isShowingTripPlan = true
                },
                onRetry: {
                    // Закрываем и показываем ошибку
                    routeBuildingData = nil
                    planGenerationError = "Не удалось сгенерировать маршрут. Попробуйте ещё раз."
                    showErrorAlert = true
                },
                onPaywallRequired: {
                    pendingRouteBuildingData = data
                    routeBuildingData = nil
                    paywallError = "Второе построение доступно после входа"
                    showPaywall = true
                }
            )
        }
        .sheet(isPresented: $showPaywall) {
            PaywallView(
                errorMessage: paywallError,
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

    private var tripPlanNavigationLink: some View {
        NavigationLink(isActive: $isShowingTripPlan) {
            if let viewModel = tripPlanViewModel {
                TripPlanView(viewModel: viewModel)
            } else {
                EmptyView()
            }
        } label: {
            EmptyView()
        }
        .hidden()
    }

    // MARK: Header

    private var headerSection: some View {
        HStack {
            Button(action: { dismiss() }) {
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
    
    // MARK: City Section

    private var citySection: some View {
        VStack(alignment: .leading, spacing: 14) {
            DestinationAutocompleteField(cityName: $selectedCity, placeholder: "Куда поедем?")
                .zIndex(10)

            ScrollView(.horizontal, showsIndicators: false) {
                HStack(spacing: 10) {
                    ForEach(popularCities, id: \.self) { city in
                        Button(action: {
                            selectedCity = city
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
                title: "ГОСТИ",
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
        VStack(alignment: .leading, spacing: 12) {
            HStack(spacing: 10) {
                ZStack {
                    Circle()
                        .fill(Color.travelBuddyOrange)
                        .frame(width: 28, height: 28)

                    Image(systemName: "sparkles")
                        .font(.system(size: 14, weight: .semibold))
                        .foregroundColor(.white)
                }

                Text("Пожелания")
                    .font(.system(size: 16, weight: .semibold, design: .rounded))
                    .foregroundColor(warmWhite)
            }

            Text("Опишите идеальное путешествие, и я подберу маршрут специально для вас.")
                .font(.system(size: 13))
                .foregroundColor(mutedWarmGray)
                .fixedSize(horizontal: false, vertical: true)

            HStack(spacing: 10) {
                TextField("Хочу спокойный отдых...", text: $messageText, axis: .vertical)
                    .font(.system(size: 14))
                    .foregroundColor(warmWhite)
                    .padding(.horizontal, 12)
                    .padding(.vertical, 10)
                    .background(
                        RoundedRectangle(cornerRadius: 14, style: .continuous)
                            .fill(Color.white.opacity(0.06))
                    )
                    .overlay(
                        RoundedRectangle(cornerRadius: 14, style: .continuous)
                            .stroke(Color.white.opacity(0.12), lineWidth: 1)
                    )
                    .focused($isTextFieldFocused)
                    .lineLimit(1...3)

                Button {
                    sendMessage()
                } label: {
                    Image(systemName: "arrow.up")
                        .font(.system(size: 14, weight: .bold))
                        .foregroundColor(.white)
                        .frame(width: 36, height: 36)
                        .background(
                            Circle()
                                .fill(Color.travelBuddyOrange)
                        )
                }
                .buttonStyle(.plain)
                .disabled(messageText.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
            }

            HStack(spacing: 8) {
                ForEach(["Спокойный темп", "Без перелетов"], id: \.self) { tag in
                    Button(action: {}) {
                        Text(tag)
                            .font(.system(size: 12, weight: .medium, design: .rounded))
                            .foregroundColor(mutedWarmGray)
                            .padding(.horizontal, 10)
                            .padding(.vertical, 6)
                            .background(
                                Capsule()
                                    .fill(Color.white.opacity(0.06))
                            )
                            .overlay(
                                Capsule()
                                    .stroke(Color.white.opacity(0.12), lineWidth: 1)
                            )
                    }
                    .buttonStyle(.plain)
                }
            }
        }
        .padding(16)
        .background(
            RoundedRectangle(cornerRadius: 22, style: .continuous)
                .fill(glassFill)
        )
        .overlay(
            RoundedRectangle(cornerRadius: 22, style: .continuous)
                .stroke(glassBorder, lineWidth: 1)
        )
    }
    
    private func sendMessage() {
        let trimmedText = messageText.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmedText.isEmpty else { return }

        // Add user message to chat
        let newMessage = ChatMessage(
            id: UUID(),
            text: trimmedText,
            isFromUser: true,
            timestamp: Date()
        )

        withAnimation {
            chatMessages.append(newMessage)
        }

        messageText = ""
        isTextFieldFocused = false

        // Send message to backend API
        Task {
            do {
                // Create trip if it doesn't exist yet
                if currentTripId == nil {
                    let apiClient = TripPlanningAPIClient()

                    // Format dates
                    let dateFormatter = DateFormatter()
                    dateFormatter.dateFormat = "yyyy-MM-dd"
                    let startDateString = dateFormatter.string(from: self.startDate)
                    let endDateString = dateFormatter.string(from: self.endDate)

                    // Create trip with current parameters
                    let tripRequest = TripCreateRequestDTO(
                        city: self.selectedCity,
                        startDate: startDateString,
                        endDate: endDateString,
                        numTravelers: self.adultsCount + self.childrenCount,
                        pace: "medium",
                        budget: self.mapBudgetToAPI(self.selectedBudget),
                        interests: Array(self.selectedInterests).sorted(),
                        dailyRoutine: nil,
                        hotelLocation: nil,
                        additionalPreferences: nil
                    )

                    let tripResponse = try await apiClient.createTrip(tripRequest)

                    guard let tripId = UUID(uuidString: tripResponse.id) else {
                        throw APIError.decodingError(NSError(domain: "Invalid trip ID", code: -1))
                    }

                    await MainActor.run {
                        self.currentTripId = tripId
                        print("✅ Trip created for chat: \(tripId)")
                    }
                }

                // Send chat message
                guard let tripId = currentTripId else {
                    throw APIError.networkError(NSError(domain: "No trip ID available", code: -1))
                }

                let apiClient = TripPlanningAPIClient()
                let chatResponse = try await apiClient.sendChatMessage(tripId: tripId, message: trimmedText)

                // Add AI response to chat
                await MainActor.run {
                    let aiMessage = ChatMessage(
                        id: UUID(),
                        text: chatResponse.assistantMessage,
                        isFromUser: false,
                        timestamp: Date()
                    )
                    withAnimation {
                        chatMessages.append(aiMessage)
                    }

                    // Update local state with potentially changed trip parameters
                    // (interests might have been updated by chat)
                    if !chatResponse.trip.interests.isEmpty {
                        // Convert English interests back to Russian for UI display
                        // This is a simplified version - you might want a reverse mapping
                        self.selectedInterests = Set(chatResponse.trip.interests)
                    }
                }

            } catch {
                // Show error message in chat
                await MainActor.run {
                    let errorMessage = ChatMessage(
                        id: UUID(),
                        text: "Ошибка: не удалось отправить сообщение. \(error.localizedDescription)",
                        isFromUser: false,
                        timestamp: Date()
                    )
                    withAnimation {
                        chatMessages.append(errorMessage)
                    }
                }
                print("❌ Chat error: \(error)")
            }
        }
    }
    
    // MARK: Plan Trip Button

    private var planTripButton: some View {
        Button(action: {
            openTripPlan()
        }) {
            HStack(spacing: 12) {
                if tripPlanViewModel?.isLoading == true {
                    ProgressView()
                        .progressViewStyle(CircularProgressViewStyle(tint: .white))
                        .scaleEffect(0.9)
                } else {
                    Image(systemName: "sparkles")
                        .font(.system(size: 20, weight: .semibold))
                        .foregroundColor(.white)
                }

                Text(tripPlanViewModel?.isLoading == true ? "Генерирую маршрут..." : "Сгенерировать маршрут")
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
        .disabled(tripPlanViewModel?.isLoading == true)
        .opacity(tripPlanViewModel?.isLoading == true ? 0.7 : 1.0)
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

        // Geocode city to get coordinates
        let geocoder = CLGeocoder()
        geocoder.geocodeAddressString(selectedCity) { placemarks, error in
            print("📍 Geocoding result: \(placemarks?.count ?? 0) placemarks, error: \(String(describing: error))")
            let coordinate: CLLocationCoordinate2D

            if let placemark = placemarks?.first,
               let location = placemark.location {
                coordinate = location.coordinate
            } else {
                // Default coordinates for common cities
                coordinate = Self.defaultCoordinate(for: selectedCity)
            }

            // Create trip first
            Task {
                do {
                    let apiClient = TripPlanningAPIClient()

                    // Format dates as YYYY-MM-DD
                    let dateFormatter = DateFormatter()
                    dateFormatter.dateFormat = "yyyy-MM-dd"
                    let startDateString = dateFormatter.string(from: self.startDate)
                    let endDateString = dateFormatter.string(from: self.endDate)

                    // Build trip request
                    let tripRequest = TripCreateRequestDTO(
                        city: self.selectedCity,
                        startDate: startDateString,
                        endDate: endDateString,
                        numTravelers: self.adultsCount + self.childrenCount,
                        pace: "medium",
                        budget: self.mapBudgetToAPI(self.selectedBudget),
                        interests: Array(self.selectedInterests).sorted(),
                        dailyRoutine: nil,
                        hotelLocation: nil,
                        additionalPreferences: nil
                    )

                    // Create trip
                    let tripResponse = try await apiClient.createTrip(tripRequest)

                    // Parse trip ID
                    guard let tripId = UUID(uuidString: tripResponse.id) else {
                        throw APIError.decodingError(NSError(domain: "Invalid trip ID", code: -1))
                    }

                    await MainActor.run {
                        print("✅ Trip created successfully, showing route building view")
                        print("✅ tripId: \(tripId)")
                        print("✅ coordinate: \(coordinate.latitude), \(coordinate.longitude)")

                        // Save trip ID for chat functionality
                        self.currentTripId = tripId

                        // Create data object and show cover
                        self.routeBuildingData = RouteBuildingData(
                            tripId: tripId,
                            cityName: self.selectedCity,
                            coordinate: coordinate
                        )
                    }
                } catch {
                    await MainActor.run {
                        self.planGenerationError = "Не удалось создать поездку: \(error.localizedDescription)"
                        self.showErrorAlert = true
                    }
                }
            }
        }
    }

    private static func defaultCoordinate(for city: String) -> CLLocationCoordinate2D {
        // Common city coordinates
        let cityCoordinates: [String: CLLocationCoordinate2D] = [
            "Рим": CLLocationCoordinate2D(latitude: 41.9028, longitude: 12.4964),
            "Rome": CLLocationCoordinate2D(latitude: 41.9028, longitude: 12.4964),
            "Стамбул": CLLocationCoordinate2D(latitude: 41.0082, longitude: 28.9784),
            "Istanbul": CLLocationCoordinate2D(latitude: 41.0082, longitude: 28.9784),
            "Бали": CLLocationCoordinate2D(latitude: -8.3405, longitude: 115.0920),
            "Bali": CLLocationCoordinate2D(latitude: -8.3405, longitude: 115.0920),
            "Тбилиси": CLLocationCoordinate2D(latitude: 41.7151, longitude: 44.8271),
            "Tbilisi": CLLocationCoordinate2D(latitude: 41.7151, longitude: 44.8271),
            "Париж": CLLocationCoordinate2D(latitude: 48.8566, longitude: 2.3522),
            "Paris": CLLocationCoordinate2D(latitude: 48.8566, longitude: 2.3522),
            "Барселона": CLLocationCoordinate2D(latitude: 41.3851, longitude: 2.1734),
            "Barcelona": CLLocationCoordinate2D(latitude: 41.3851, longitude: 2.1734),
            "Нью-Йорк": CLLocationCoordinate2D(latitude: 40.7128, longitude: -74.0060),
            "New York": CLLocationCoordinate2D(latitude: 40.7128, longitude: -74.0060),
        ]

        return cityCoordinates[city] ?? CLLocationCoordinate2D(latitude: 41.9028, longitude: 12.4964)
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
        guard let viewModel = tripPlanViewModel else {
            // If no viewModel exists, call openTripPlan to create one
            openTripPlan()
            return
        }

        // Retry using stored parameters
        Task {
            await viewModel.retryLastGeneration()

            await MainActor.run {
                if viewModel.plan != nil {
                    isShowingTripPlan = true
                } else if let error = viewModel.errorMessage {
                    planGenerationError = error
                    showErrorAlert = true
                }
            }
        }
    }
}
