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

    @State private var selectedCity: String
    @State private var startDate: Date
    @State private var endDate: Date
    @State private var showDatePicker: Bool = false
    @State private var adultsCount: Int = 2
    @State private var childrenCount: Int = 0
    @State private var showTravelersPicker: Bool = false
    @State private var selectedInterests: Set<String> = ["Гастрономия", "Ночная жизнь", "Природа и виды"]

    // Route building state - using Identifiable item for fullScreenCover
    @State private var routeBuildingData: RouteBuildingData?
    
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

    let popularCities = ["Стамбул", "Рим", "Бали", "Тбилиси"]

    // MARK: - Init

    init(prefilledTicket: FlightTicket? = nil) {
        self.prefilledTicket = prefilledTicket

        // Всегда инициализируем с дефолтными значениями
        // Реальные значения из билета установятся в .onAppear
        let calendar = Calendar.current
        let defaultStart = calendar.date(byAdding: .day, value: 1, to: Date()) ?? Date()
        let defaultEnd = calendar.date(byAdding: .day, value: 6, to: defaultStart) ?? Date()

        _selectedCity = State(initialValue: "Стамбул")
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
            // Фон
            LinearGradient(
                colors: [
                    Color.white,
                    Color(red: 0.98, green: 0.99, blue: 1.0)
                ],
                startPoint: .top,
                endPoint: .bottom
            )
            .ignoresSafeArea()
            
            ScrollView {
                VStack(alignment: .leading, spacing: 24) {
                    // Секция: Город / Направление
                    citySection
                    
                    // Секция: Даты поездки
                    datesSection
                    
                    // Секция: Путешественники
                    travelersSection
                    
                    // Секция: Интересы
                    interestsSection
                    
                    // Секция: Уровень бюджета
                    budgetSection
                    
                    // Секция: Пожелания к поездке
                    wishesSection
                    
                    // Встроенный чат
                    inlineChatSection
                    
                    // Кнопка "Спланировать поездку"
                    planTripButton
                        .padding(.top, 8)
                }
                .padding(.horizontal, 20)
                .padding(.vertical, 16)
                .padding(.bottom, 24)
            }
        }
        .background(tripPlanNavigationLink)
        .navigationTitle("Новая поездка")
        .navigationBarTitleDisplayMode(.inline)
        .toolbar {
            ToolbarItem(placement: .navigationBarTrailing) {
                Button(action: {
                    // Placeholder для помощи
                }) {
                    Image(systemName: "questionmark.circle")
                        .font(.system(size: 20))
                        .foregroundColor(Color(.label))
                }
            }
        }
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
                        travelersCount: adultsCount + childrenCount
                    )

                    // Показываем экран плана
                    isShowingTripPlan = true
                },
                onRetry: {
                    // Закрываем и показываем ошибку
                    routeBuildingData = nil
                    planGenerationError = "Не удалось сгенерировать маршрут. Попробуйте ещё раз."
                    showErrorAlert = true
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
    
    // MARK: City Section

    private var citySection: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack {
                Text("ГОРОД / НАПРАВЛЕНИЕ")
                    .font(.system(size: 13, weight: .semibold, design: .rounded))
                    .foregroundColor(Color(.secondaryLabel))
                    .textCase(.uppercase)

                if prefilledTicket != nil {
                    Spacer()
                    Label("Из билета", systemImage: "airplane.circle.fill")
                        .font(.system(size: 12, weight: .medium))
                        .foregroundColor(.travelBuddyOrange)
                }
            }

            // Поле ввода города с автодополнением
            DestinationAutocompleteField(cityName: $selectedCity)
                .zIndex(10) // Чтобы dropdown был поверх других элементов

            // Популярные города
            ScrollView(.horizontal, showsIndicators: false) {
                HStack(spacing: 10) {
                    ForEach(popularCities, id: \.self) { city in
                        Button(action: {
                            selectedCity = city
                        }) {
                            Text(city)
                                .font(.system(size: 15, weight: .medium))
                                .foregroundColor(selectedCity == city ? Color(red: 1.0, green: 0.55, blue: 0.30) : Color(.label))
                                .padding(.horizontal, 16)
                                .padding(.vertical, 10)
                                .background(
                                    RoundedRectangle(cornerRadius: 20, style: .continuous)
                                        .fill(selectedCity == city ? Color(red: 1.0, green: 0.55, blue: 0.30).opacity(0.1) : Color(.systemGray6))
                                )
                                .overlay(
                                    RoundedRectangle(cornerRadius: 20, style: .continuous)
                                        .stroke(selectedCity == city ? Color(red: 1.0, green: 0.55, blue: 0.30) : Color.clear, lineWidth: 1.5)
                                )
                        }
                        .buttonStyle(.plain)
                    }
                }
                .padding(.vertical, 4)
            }
        }
    }
    
    // MARK: Dates Section
    
    private var datesSection: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("ДАТЫ ПОЕЗДКИ")
                .font(.system(size: 13, weight: .semibold, design: .rounded))
                .foregroundColor(Color(.secondaryLabel))
                .textCase(.uppercase)
            
            Button(action: {
                showDatePicker = true
            }) {
                HStack(spacing: 14) {
                    ZStack {
                        Circle()
                            .fill(Color(red: 0.4, green: 0.7, blue: 1.0).opacity(0.15))
                            .frame(width: 44, height: 44)
                        
                        Image(systemName: "calendar")
                            .font(.system(size: 20, weight: .semibold))
                            .foregroundColor(Color(red: 0.2, green: 0.6, blue: 1.0))
                    }
                    
                    VStack(alignment: .leading, spacing: 4) {
                        Text(formattedDates)
                            .font(.system(size: 17, weight: .semibold, design: .rounded))
                            .foregroundColor(Color(.label))
                        
                        Text("Можно изменить позже")
                            .font(.system(size: 13))
                            .foregroundColor(Color(.secondaryLabel))
                    }
                    
                    Spacer()
                    
                    Image(systemName: "chevron.right")
                        .font(.system(size: 14, weight: .semibold))
                        .foregroundColor(Color(.tertiaryLabel))
                }
                .padding(16)
                .background(
                    RoundedRectangle(cornerRadius: 18, style: .continuous)
                        .fill(Color.white)
                )
                .shadow(color: Color.black.opacity(0.05), radius: 8, x: 0, y: 4)
            }
            .buttonStyle(.plain)
        }
        .sheet(isPresented: $showDatePicker) {
            DatePickerSheet(
                startDate: $startDate,
                endDate: $endDate,
                isPresented: $showDatePicker
            )
        }
    }
    
    // MARK: Travelers Section
    
    private var travelersSection: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("ПУТЕШЕСТВЕННИКИ")
                .font(.system(size: 13, weight: .semibold, design: .rounded))
                .foregroundColor(Color(.secondaryLabel))
                .textCase(.uppercase)
            
            Button(action: {
                showTravelersPicker = true
            }) {
                HStack(spacing: 14) {
                    ZStack {
                        Circle()
                            .fill(Color(red: 0.7, green: 0.5, blue: 0.9).opacity(0.15))
                            .frame(width: 44, height: 44)
                        
                        Image(systemName: "person.2.fill")
                            .font(.system(size: 20, weight: .semibold))
                            .foregroundColor(Color(red: 0.6, green: 0.4, blue: 0.8))
                    }
                    
                    VStack(alignment: .leading, spacing: 4) {
                        Text(travelersText)
                            .font(.system(size: 17, weight: .semibold, design: .rounded))
                            .foregroundColor(Color(.label))
                        
                        Text("Помогу подобрать комфортный маршрут")
                            .font(.system(size: 13))
                            .foregroundColor(Color(.secondaryLabel))
                    }
                    
                    Spacer()
                    
                    Image(systemName: "chevron.right")
                        .font(.system(size: 14, weight: .semibold))
                        .foregroundColor(Color(.tertiaryLabel))
                }
                .padding(16)
                .background(
                    RoundedRectangle(cornerRadius: 18, style: .continuous)
                        .fill(Color.white)
                )
                .shadow(color: Color.black.opacity(0.05), radius: 8, x: 0, y: 4)
            }
            .buttonStyle(.plain)
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
    @State private var customInterestText: String = ""

    private var interestsSection: some View {
        let baseInterests: [(title: String, icon: String, color: Color)] = [
            ("Гастрономия", "fork.knife", Color(red: 1.0, green: 0.4, blue: 0.4)),
            ("История и музеи", "building.columns", Color(.systemGray)),
            ("Ночная жизнь", "moon.fill", Color(red: 0.7, green: 0.4, blue: 0.9)),
            ("Природа и виды", "mountain.2.fill", Color(red: 0.2, green: 0.7, blue: 0.7)),
            ("Шопинг", "bag.fill", Color(red: 0.95, green: 0.6, blue: 0.2)),
            ("Кофейни и десерты", "cup.and.saucer.fill", Color(red: 0.9, green: 0.5, blue: 0.8)),
            ("Современное искусство", "paintpalette.fill", Color(red: 0.4, green: 0.6, blue: 1.0)),
            ("Архитектура и районы", "building.2.fill", Color(.systemIndigo)),
            ("Пляж / вода", "sun.max.fill", Color(red: 1.0, green: 0.8, blue: 0.3)),
            ("Активности и спорт", "figure.run", Color(red: 0.2, green: 0.7, blue: 0.4))
        ]
        
        let baseTitles = Set(baseInterests.map { $0.title })
        let customInterests = selectedInterests
            .filter { !baseTitles.contains($0) }
            .sorted()
        
        return VStack(alignment: .leading, spacing: 12) {
            Text("ИНТЕРЕСЫ")
                .font(.system(size: 13, weight: .semibold, design: .rounded))
                .foregroundColor(Color(.secondaryLabel))
                .textCase(.uppercase)
            
            Text("Выбери хотя бы 2–3, чтобы маршрут был точнее")
                .font(.system(size: 13))
                .foregroundColor(Color(.secondaryLabel))
            
            // Сетка с интересами (адаптивно, без перегрузки)
            LazyVGrid(
                columns: [
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
            
            // Свои интересы (чипы), если есть
            if !customInterests.isEmpty {
                VStack(alignment: .leading, spacing: 8) {
                    Text("Твои интересы")
                        .font(.system(size: 13, weight: .medium))
                        .foregroundColor(Color(.secondaryLabel))
                    
                    ScrollView(.horizontal, showsIndicators: false) {
                        HStack(spacing: 8) {
                            ForEach(customInterests, id: \.self) { interest in
                                Button {
                                    toggleInterest(interest)
                                } label: {
                                    HStack(spacing: 6) {
                                        Text(interest)
                                            .font(.system(size: 14, weight: .medium))
                                        Image(systemName: "xmark")
                                            .font(.system(size: 11, weight: .bold))
                                    }
                                    .padding(.horizontal, 12)
                                    .padding(.vertical, 7)
                                    .background(
                                        Capsule()
                                            .fill(Color(.systemGray5))
                                    )
                                    .foregroundColor(Color(.label))
                                }
                                .buttonStyle(.plain)
                            }
                        }
                    }
                }
                .padding(.top, 4)
            }
            
            // Поле "свой интерес"
            VStack(alignment: .leading, spacing: 6) {
                Text("Или напиши что-то своё")
                    .font(.system(size: 13))
                    .foregroundColor(Color(.secondaryLabel))
                
                HStack(spacing: 8) {
                    TextField("Например, «винные бары» или «футбол»", text: $customInterestText)
                        .textInputAutocapitalization(.sentences)
                        .disableAutocorrection(false)
                        .padding(.horizontal, 12)
                        .padding(.vertical, 10)
                        .background(
                            RoundedRectangle(cornerRadius: 12)
                                .fill(Color(.secondarySystemBackground))
                        )
                    
                    Button {
                        addCustomInterest()
                    } label: {
                        Image(systemName: "plus.circle.fill")
                            .font(.system(size: 22, weight: .semibold))
                    }
                    .foregroundColor(customInterestTextTrimmed.isEmpty ? Color(.tertiaryLabel) : Color(red: 0.2, green: 0.6, blue: 1.0))
                    .disabled(customInterestTextTrimmed.isEmpty)
                }
            }
            .padding(.top, 4)
        }
    }

    // MARK: - Interests helpers

    private var customInterestTextTrimmed: String {
        customInterestText.trimmingCharacters(in: .whitespacesAndNewlines)
    }

    private func addCustomInterest() {
        let value = customInterestTextTrimmed
        guard !value.isEmpty else { return }
        
        // чтобы не плодить дубли
        if !selectedInterests.contains(value) {
            selectedInterests.insert(value)
        }
        customInterestText = ""
    }

    private func toggleInterest(_ interest: String) {
        if selectedInterests.contains(interest) {
            selectedInterests.remove(interest)
        } else {
            selectedInterests.insert(interest)
        }
    }

    // MARK: Budget Section
    
    private var budgetSection: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("УРОВЕНЬ БЮДЖЕТА")
                .font(.system(size: 13, weight: .semibold, design: .rounded))
                .foregroundColor(Color(.secondaryLabel))
                .textCase(.uppercase)
            
            HStack(spacing: 12) {
                BudgetButton(
                    title: "Эконом",
                    icon: "coloncurrencysign.circle.fill",
                    isSelected: selectedBudget == "Эконом"
                ) {
                    selectedBudget = "Эконом"
                }
                
                BudgetButton(
                    title: "Комфорт",
                    icon: "suitcase.fill",
                    isSelected: selectedBudget == "Комфорт"
                ) {
                    selectedBudget = "Комфорт"
                }
                
                BudgetButton(
                    title: "Премиум",
                    icon: "crown.fill",
                    isSelected: selectedBudget == "Премиум"
                ) {
                    selectedBudget = "Премиум"
                }
            }
        }
    }
    
    // MARK: Wishes Section
    
    private var wishesSection: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("ПОЖЕЛАНИЯ К ПОЕЗДКЕ")
                .font(.system(size: 13, weight: .semibold, design: .rounded))
                .foregroundColor(Color(.secondaryLabel))
                .textCase(.uppercase)
            
            Text("Напиши в чате, что для тебя важно: темп поездки, стиль, ограничения, особые запросы.")
                .font(.system(size: 14))
                .foregroundColor(Color(.secondaryLabel))
                .fixedSize(horizontal: false, vertical: true)
        }
    }
    
    // MARK: Inline Chat Section
    
    private var inlineChatSection: some View {
        VStack(alignment: .leading, spacing: 0) {
            // Заголовок чата
            HStack(spacing: 12) {
                ZStack {
                    Circle()
                        .fill(
                            LinearGradient(
                                colors: [
                                    Color(red: 1.0, green: 0.65, blue: 0.40),
                                    Color(red: 1.0, green: 0.45, blue: 0.35)
                                ],
                                startPoint: .topLeading,
                                endPoint: .bottomTrailing
                            )
                        )
                        .frame(width: 36, height: 36)
                    
                    Image(systemName: "mappin.circle.fill")
                        .font(.system(size: 18, weight: .semibold))
                        .foregroundColor(.white)
                }
                
                Text("Чат с Travel Buddy")
                    .font(.system(size: 17, weight: .semibold, design: .rounded))
                    .foregroundColor(Color(.label))
                
                Spacer()
                
                HStack(spacing: 6) {
                    Circle()
                        .fill(Color.green)
                        .frame(width: 8, height: 8)
                    
                    Text("Онлайн")
                        .font(.system(size: 13, weight: .medium))
                        .foregroundColor(Color(.secondaryLabel))
                }
            }
            .padding(.horizontal, 16)
            .padding(.vertical, 12)
            .background(Color.white)
            
            // Область сообщений
            ScrollViewReader { proxy in
                ScrollView {
                    VStack(alignment: .leading, spacing: 16) {
                        ForEach(chatMessages) { message in
                            ChatBubbleView(message: message)
                                .id(message.id)
                        }
                    }
                    .padding(.horizontal, 16)
                    .padding(.vertical, 16)
                }
                .frame(maxHeight: 200)
                .background(Color.white)
                .onChange(of: chatMessages.count) { _ in
                    if let lastMessage = chatMessages.last {
                        withAnimation {
                            proxy.scrollTo(lastMessage.id, anchor: .bottom)
                        }
                    }
                }
            }
            
            // Поле ввода
            HStack(spacing: 10) {
                TextField("Напиши свои пожелания к маршру", text: $messageText, axis: .vertical)
                    .font(.system(size: 15))
                    .padding(.horizontal, 14)
                    .padding(.vertical, 10)
                    .background(
                        RoundedRectangle(cornerRadius: 20, style: .continuous)
                            .fill(Color(.systemGray6))
                    )
                    .focused($isTextFieldFocused)
                    .lineLimit(1...3)
                
                Button(action: {
                    // Placeholder для голосового ввода
                }) {
                    Image(systemName: "mic.fill")
                        .font(.system(size: 16, weight: .medium))
                        .foregroundColor(Color(.secondaryLabel))
                        .frame(width: 36, height: 36)
                }
                .buttonStyle(.plain)
                
                Button {
                    sendMessage()
                } label: {
                    Image(systemName: "paperplane.fill")
                        .font(.system(size: 16, weight: .semibold))
                        .foregroundColor(.white)
                        .frame(width: 36, height: 36)
                        .background(
                            Circle()
                                .fill(Color(red: 1.0, green: 0.55, blue: 0.30))
                        )
                }
                .buttonStyle(.plain)
                .disabled(messageText.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
            }
            .padding(.horizontal, 12)
            .padding(.vertical, 12)
            .background(Color.white)
        }
        .background(
            RoundedRectangle(cornerRadius: 24, style: .continuous)
                .fill(Color.white)
        )
        .shadow(color: Color.black.opacity(0.08), radius: 12, x: 0, y: 4)
    }
    
    private func sendMessage() {
        let trimmedText = messageText.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmedText.isEmpty else { return }
        
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
        
        // Симуляция ответа AI
        DispatchQueue.main.asyncAfter(deadline: .now() + 1.0) {
            let aiResponse = ChatMessage(
                id: UUID(),
                text: "Понял! Учту твои пожелания при составлении маршрута.",
                isFromUser: false,
                timestamp: Date()
            )
            withAnimation {
                chatMessages.append(aiResponse)
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
            .padding(.vertical, 18)
            .background(
                RoundedRectangle(cornerRadius: 20, style: .continuous)
                    .fill(
                        LinearGradient(
                            colors: [
                                Color(red: 1.0, green: 0.65, blue: 0.40),
                                Color(red: 1.0, green: 0.45, blue: 0.35)
                            ],
                            startPoint: .leading,
                            endPoint: .trailing
                        )
                    )
            )
            .shadow(color: Color(red: 1.0, green: 0.45, blue: 0.35).opacity(0.3), radius: 12, x: 0, y: 6)
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
        ]

        return cityCoordinates[city] ?? CLLocationCoordinate2D(latitude: 41.9028, longitude: 12.4964)
    }

    private func mapBudgetToAPI(_ budget: String) -> String {
        switch budget {
        case "Эконом": return "low"
        case "Комфорт": return "medium"
        case "Премиум": return "high"
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

