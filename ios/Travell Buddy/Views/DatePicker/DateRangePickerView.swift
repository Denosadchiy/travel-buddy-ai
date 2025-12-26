//
//  DateRangePickerView.swift
//  Travell Buddy
//
//  Aviasales-style date range picker with calendar grid.
//

import SwiftUI


/// Переиспользуемый компонент выбора диапазона дат в стиле Aviasales
/// 
/// Улучшения UX по сравнению с предыдущей версией:
/// 1. Единый календарь вместо двух переключающихся
/// 2. Визуализация диапазона между датами (заливка + выделение границ)
/// 3. Умная логика: тап раньше первой даты = новая дата вылета
/// 4. Фиксированная панель с информацией о выбранных датах и количестве ночей
/// 5. Быстрые пресеты (выходные, неделя, ±3 дня)
/// 6. Кнопка "Готово" активна только при выборе обеих дат
/// 7. Haptic feedback при выборе дат
/// 8. Поддержка accessibility (VoiceOver)
/// 
/// Всегда требует выбора обеих дат (вылет и возврат) - режима "one way" нет

struct DateRangePickerView: View {
    @Binding var departureDate: Date?
    @Binding var returnDate: Date?
    @Binding var isPresented: Bool
    
    @State private var selectedDeparture: Date?
    @State private var selectedReturn: Date?
    @State private var currentMonth: Date   // старт месяца, показанного в шапке / скролле
    
    private let minDate: Date
    private let maxDate: Date   // уже приведён к "не дальше чем год вперёд"
    
    init(
        departureDate: Binding<Date?>,
        returnDate: Binding<Date?>,
        isPresented: Binding<Bool>,
        minDate: Date = Date(),
        maxDate: Date? = nil
    ) {
        self._departureDate = departureDate
        self._returnDate = returnDate
        self._isPresented = isPresented
        
        let calendar = Calendar.current
        let today = calendar.startOfDay(for: Date())
        
        // minDate не раньше сегодняшнего дня
        let resolvedMin = max(calendar.startOfDay(for: minDate), today)
        
        // maxDate не дальше чем на год вперёд
        let oneYearAhead = calendar.date(byAdding: .year, value: 1, to: today)!
        let resolvedRawMax = (maxDate.map { calendar.startOfDay(for: $0) }) ?? oneYearAhead
        let resolvedMax = min(resolvedRawMax, oneYearAhead)
        
        self.minDate = resolvedMin
        self.maxDate = resolvedMax
        
        // Инициализация выбранных дат — только если они попадают в допустимый диапазон
        let initialDeparture = departureDate.wrappedValue
        let initialReturn = returnDate.wrappedValue
        
        if let dep = initialDeparture, dep >= resolvedMin, dep <= resolvedMax {
            self._selectedDeparture = State(initialValue: dep)
        } else {
            self._selectedDeparture = State(initialValue: nil)
        }
        
        if let ret = initialReturn, ret >= resolvedMin, ret <= resolvedMax {
            self._selectedReturn = State(initialValue: ret)
        } else {
            self._selectedReturn = State(initialValue: nil)
        }
        
        // Текущий месяц — месяц minDate
        let startOfMinMonth = calendar.date(
            from: calendar.dateComponents([.year, .month], from: resolvedMin)
        ) ?? resolvedMin
        
        self._currentMonth = State(initialValue: startOfMinMonth)
    }
    
    var body: some View {
        NavigationStack {
            ZStack {
                Color(.systemBackground)
                    .ignoresSafeArea()
                
                VStack(spacing: 0) {
                    // Фиксированная панель с информацией о выбранных датах
                    dateInfoPanel
                        .padding(.horizontal, 20)
                        .padding(.vertical, 16)
                        .background(Color(.systemBackground))
                    
                    Divider()
                    
                    // Быстрые пресеты
                    presetsSection
                        .padding(.horizontal, 20)
                        .padding(.vertical, 12)
                        .background(Color(.systemBackground))
                    
                    Divider()
                    
                    // Шапка с выбором месяца/года
                    monthHeader
                    
                    // Календарь с возможностью скролла к нужному месяцу
                    ScrollViewReader { proxy in
                        ScrollView {
                            calendarView
                                .padding(.horizontal, 20)
                                .padding(.vertical, 16)
                        }
                        .onAppear {
                            scrollToMonth(currentMonth, proxy: proxy, animated: false)
                        }
                        .onChange(of: currentMonth) { newValue in
                            scrollToMonth(newValue, proxy: proxy, animated: true)
                        }
                    }
                }
            }
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .navigationBarLeading) {
                    Button("Отмена") {
                        isPresented = false
                    }
                    .foregroundColor(Color(.label))
                }
                
                ToolbarItem(placement: .navigationBarTrailing) {
                    Button("Готово") {
                        departureDate = selectedDeparture
                        returnDate = selectedReturn
                        isPresented = false
                    }
                    .font(.system(size: 17, weight: .semibold))
                    .foregroundColor(isBothDatesSelected ? Color(red: 0.2, green: 0.6, blue: 1.0) : Color(.tertiaryLabel))
                    .disabled(!isBothDatesSelected)
                }
            }
        }
        .presentationDetents([.large])
    }
    
    // MARK: - Date Info Panel
    
    private var dateInfoPanel: some View {
        VStack(alignment: .leading, spacing: 8) {
            if let departure = selectedDeparture, let returnDate = selectedReturn {
                HStack(spacing: 4) {
                    Text("Вы летите")
                        .font(.system(size: 16, weight: .medium))
                        .foregroundColor(Color(.secondaryLabel))
                    
                    Text(formatDate(departure))
                        .font(.system(size: 16, weight: .semibold))
                        .foregroundColor(Color(.label))
                    
                    Text("—")
                        .font(.system(size: 16, weight: .medium))
                        .foregroundColor(Color(.secondaryLabel))
                    
                    Text(formatDate(returnDate))
                        .font(.system(size: 16, weight: .semibold))
                        .foregroundColor(Color(.label))
                    
                    Text("·")
                        .font(.system(size: 16, weight: .medium))
                        .foregroundColor(Color(.secondaryLabel))
                    
                    Text(nightsCount(departure: departure, return: returnDate))
                        .font(.system(size: 16, weight: .semibold))
                        .foregroundColor(Color(red: 0.2, green: 0.6, blue: 1.0))
                }
            } else if let departure = selectedDeparture {
                HStack(spacing: 4) {
                    Text("Вылет:")
                        .font(.system(size: 16, weight: .medium))
                        .foregroundColor(Color(.secondaryLabel))
                    
                    Text(formatDate(departure))
                        .font(.system(size: 16, weight: .semibold))
                        .foregroundColor(Color(.label))
                    
                    Text("· Выберите дату возврата")
                        .font(.system(size: 16, weight: .medium))
                        .foregroundColor(Color(.secondaryLabel))
                }
            } else {
                Text("Выберите дату вылета")
                    .font(.system(size: 16, weight: .medium))
                    .foregroundColor(Color(.secondaryLabel))
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }
    
    // MARK: - Presets Section
    
    private var presetsSection: some View {
        ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: 12) {
                PresetButton(
                    title: "На выходные",
                    action: { applyWeekendPreset() }
                )
                
                PresetButton(
                    title: "На неделю",
                    action: { applyWeekPreset() }
                )
                
                PresetButton(
                    title: "±3 дня",
                    action: { applyFlexiblePreset() }
                )
            }
        }
    }
    
    // MARK: - Month Header (месяц/год + стрелки)
    
    private var monthHeader: some View {
        HStack {
            Button(action: goToPreviousMonth) {
                Image(systemName: "chevron.left")
                    .font(.system(size: 17, weight: .semibold))
            }
            .foregroundColor(canGoToPreviousMonth ? Color(.label) : Color(.tertiaryLabel))
            .disabled(!canGoToPreviousMonth)
            
            Spacer()
            
            Menu {
                ForEach(availableYears, id: \.self) { year in
                    Section("\(year)") {
                        ForEach(availableMonths(for: year), id: \.self) { monthDate in
                            Button {
                                withAnimation(.spring(response: 0.3)) {
                                    currentMonth = monthDate
                                }
                            } label: {
                                Text(monthTitle(for: monthDate))
                            }
                        }
                    }
                }
            } label: {
                HStack(spacing: 4) {
                    Text(monthYearTitle(for: currentMonth))
                        .font(.system(size: 17, weight: .semibold, design: .rounded))
                    Image(systemName: "chevron.down")
                        .font(.system(size: 13, weight: .semibold))
                }
                .foregroundColor(Color(.label))
            }
            
            Spacer()
            
            Button(action: goToNextMonth) {
                Image(systemName: "chevron.right")
                    .font(.system(size: 17, weight: .semibold))
            }
            .foregroundColor(canGoToNextMonth ? Color(.label) : Color(.tertiaryLabel))
            .disabled(!canGoToNextMonth)
        }
        .padding(.horizontal, 20)
        .padding(.top, 8)
        .padding(.bottom, 4)
    }
    
    // MARK: - Calendar View
    
    private var calendarView: some View {
        VStack(spacing: 24) {
            ForEach(months, id: \.self) { monthDate in
                MonthCalendarView(
                    month: monthDate,
                    departureDate: $selectedDeparture,
                    returnDate: $selectedReturn,
                    minDate: minDate,
                    maxDate: maxDate,
                    onDateTap: handleDateTap
                )
                .id(monthDate)
            }
        }
    }
    
    // MARK: - Helpers: месяцы / навигация
    
    /// Все месяцы от minDate до maxDate (включительно)
    private var months: [Date] {
        var result: [Date] = []
        let calendar = Calendar.current
        var current = startOfMonth(for: minDate)
        let last = startOfMonth(for: maxDate)
        
        while current <= last {
            result.append(current)
            guard let next = calendar.date(byAdding: .month, value: 1, to: current) else { break }
            current = next
        }
        return result
    }
    
    private var availableYears: [Int] {
        let calendar = Calendar.current
        let startYear = calendar.component(.year, from: minDate)
        let endYear = calendar.component(.year, from: maxDate)
        return Array(startYear...endYear)
    }
    
    private func availableMonths(for year: Int) -> [Date] {
        let calendar = Calendar.current
        var result: [Date] = []
        for month in 1...12 {
            var comps = DateComponents()
            comps.year = year
            comps.month = month
            comps.day = 1
            if let date = calendar.date(from: comps) {
                let start = startOfMonth(for: date)
                if start < startOfMonth(for: minDate) { continue }
                if start > startOfMonth(for: maxDate) { continue }
                result.append(start)
            }
        }
        return result
    }
    
    private func startOfMonth(for date: Date) -> Date {
        let calendar = Calendar.current
        return calendar.date(from: calendar.dateComponents([.year, .month], from: date)) ?? date
    }
    
    private var canGoToPreviousMonth: Bool {
        startOfMonth(for: currentMonth) > startOfMonth(for: minDate)
    }
    
    private var canGoToNextMonth: Bool {
        startOfMonth(for: currentMonth) < startOfMonth(for: maxDate)
    }
    
    private func goToPreviousMonth() {
        guard canGoToPreviousMonth else { return }
        let calendar = Calendar.current
        if let prev = calendar.date(byAdding: .month, value: -1, to: startOfMonth(for: currentMonth)) {
            currentMonth = max(startOfMonth(for: prev), startOfMonth(for: minDate))
        }
    }
    
    private func goToNextMonth() {
        guard canGoToNextMonth else { return }
        let calendar = Calendar.current
        if let next = calendar.date(byAdding: .month, value: 1, to: startOfMonth(for: currentMonth)) {
            let capped = min(next, startOfMonth(for: maxDate))
            currentMonth = capped
        }
    }
    
    private func scrollToMonth(_ month: Date, proxy: ScrollViewProxy, animated: Bool) {
        let target = startOfMonth(for: month)
        if animated {
            withAnimation {
                proxy.scrollTo(target, anchor: .top)
            }
        } else {
            DispatchQueue.main.async {
                proxy.scrollTo(target, anchor: .top)
            }
        }
    }
    
    private var isBothDatesSelected: Bool {
        selectedDeparture != nil && selectedReturn != nil
    }
    
    // MARK: - Date tap logic
    
    private func handleDateTap(_ date: Date) {
        // Нельзя выбрать дату вне диапазона
        guard date >= minDate, date <= maxDate else { return }
        
        // Haptic feedback
        let impactFeedback = UIImpactFeedbackGenerator(style: .light)
        impactFeedback.impactOccurred()
        
        if let departure = selectedDeparture, let returnDate = selectedReturn {
            // Если обе даты выбраны, новая дата становится новой датой вылета / сбрасывает диапазон
            if date < departure {
                withAnimation(.spring(response: 0.3)) {
                    selectedDeparture = date
                    selectedReturn = nil
                }
            } else if date == departure {
                withAnimation(.spring(response: 0.3)) {
                    selectedDeparture = nil
                    selectedReturn = nil
                }
            } else if date == returnDate {
                withAnimation(.spring(response: 0.3)) {
                    selectedReturn = nil
                }
            } else {
                withAnimation(.spring(response: 0.3)) {
                    selectedDeparture = date
                    selectedReturn = nil
                }
            }
        } else if let departure = selectedDeparture {
            // Выбрана только дата вылета
            if date < departure {
                withAnimation(.spring(response: 0.3)) {
                    selectedDeparture = date
                }
            } else if date == departure {
                withAnimation(.spring(response: 0.3)) {
                    selectedDeparture = nil
                }
            } else {
                withAnimation(.spring(response: 0.3)) {
                    selectedReturn = date
                    let successFeedback = UINotificationFeedbackGenerator()
                    successFeedback.notificationOccurred(.success)
                }
            }
        } else {
            // Ничего не выбрано - первая дата = вылет
            withAnimation(.spring(response: 0.3)) {
                selectedDeparture = date
            }
        }
    }
    
    // MARK: - Presets (учитывают ограничения min/max)
    
    private func applyWeekendPreset() {
        let calendar = Calendar.current
        let today = calendar.startOfDay(for: Date())
        
        var friday = today
        // Пятница = 6 (при стандартной локали: 1 — воскресенье)
        while calendar.component(.weekday, from: friday) != 6 {
            guard let next = calendar.date(byAdding: .day, value: 1, to: friday) else { break }
            friday = next
        }
        
        let departure = max(friday, minDate)
        if departure > maxDate { return } // выходные вне диапазона
        
        var sunday = calendar.date(byAdding: .day, value: 2, to: departure) ?? departure
        if sunday > maxDate { sunday = maxDate }
        
        withAnimation {
            selectedDeparture = departure
            selectedReturn = sunday
        }
    }
    
    private func applyWeekPreset() {
        let calendar = Calendar.current
        let today = calendar.startOfDay(for: Date())
        
        var start = selectedDeparture ?? max(today, minDate)
        if start > maxDate { start = maxDate }
        
        var end = calendar.date(byAdding: .day, value: 7, to: start) ?? start
        if end > maxDate { end = maxDate }
        
        withAnimation {
            selectedDeparture = start
            selectedReturn = end
        }
    }
    
    private func applyFlexiblePreset() {
        let calendar = Calendar.current
        let today = calendar.startOfDay(for: Date())
        
        var start = selectedDeparture ?? max(today, minDate)
        if start > maxDate { start = maxDate }
        
        var end = calendar.date(byAdding: .day, value: 3, to: start) ?? start
        if end > maxDate { end = maxDate }
        
        withAnimation {
            selectedDeparture = start
            selectedReturn = end
        }
    }
    
    // MARK: - Formatting
    
    private func formatDate(_ date: Date) -> String {
        let formatter = DateFormatter()
        formatter.locale = Locale(identifier: "ru_RU")
        formatter.dateFormat = "d MMM"
        return formatter.string(from: date)
    }
    
    private func monthYearTitle(for date: Date) -> String {
        let formatter = DateFormatter()
        formatter.locale = Locale(identifier: "ru_RU")
        formatter.dateFormat = "LLLL yyyy"
        let base = formatter.string(from: date)
        return base.prefix(1).uppercased() + base.dropFirst()
    }
    
    private func monthTitle(for date: Date) -> String {
        let formatter = DateFormatter()
        formatter.locale = Locale(identifier: "ru_RU")
        formatter.dateFormat = "LLLL"
        let base = formatter.string(from: date)
        return base.prefix(1).uppercased() + base.dropFirst()
    }
    
    private func nightsCount(departure: Date, return: Date) -> String {
        let calendar = Calendar.current
        let days = calendar.dateComponents([.day], from: departure, to: `return`).day ?? 0
        
        if days == 0 {
            return "0 ночей"
        } else if days == 1 {
            return "1 ночь"
        } else if days < 5 {
            return "\(days) ночи"
        } else {
            return "\(days) ночей"
        }
    }
}
