//
//  MonthCalendarView.swift
//  Travell Buddy
//
//  Calendar grid for a single month.
//

import SwiftUI

struct MonthCalendarView: View {
    let month: Date
    @Binding var departureDate: Date?
    @Binding var returnDate: Date?
    let minDate: Date
    let maxDate: Date
    let onDateTap: (Date) -> Void

    private var calendar: Calendar { Calendar.current }
    private let warmWhite = Color(red: 0.95, green: 0.94, blue: 0.92)
    private let mutedWarmGray = Color(red: 0.70, green: 0.67, blue: 0.63)

    private var monthName: String {
        let formatter = DateFormatter()
        formatter.locale = Locale(identifier: "ru_RU")
        formatter.dateFormat = "MMMM yyyy"
        let name = formatter.string(from: month).lowercased()
        return name.prefix(1).uppercased() + name.dropFirst()
    }

    private var daysInMonth: [Date?] {
        let startOfMonth = calendar.date(from: calendar.dateComponents([.year, .month], from: month)) ?? month
        let firstWeekday = calendar.component(.weekday, from: startOfMonth)
        let daysCount = calendar.range(of: .day, in: .month, for: month)?.count ?? 0

        var days: [Date?] = []

        // Пустые ячейки до первого дня месяца
        for _ in 1..<firstWeekday {
            days.append(nil)
        }

        // Дни месяца
        for day in 1...daysCount {
            if let date = calendar.date(byAdding: .day, value: day - 1, to: startOfMonth) {
                days.append(date)
            }
        }

        return days
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            // Название месяца
            Text(monthName)
                .font(.system(size: 20, weight: .bold, design: .rounded))
                .foregroundColor(warmWhite)
                .padding(.horizontal, 4)

            // Дни недели
            HStack(spacing: 0) {
                ForEach(["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"], id: \.self) { day in
                    Text(day)
                        .font(.system(size: 13, weight: .medium))
                        .foregroundColor(mutedWarmGray)
                        .frame(maxWidth: .infinity)
                }
            }

            // Календарная сетка
            LazyVGrid(columns: Array(repeating: GridItem(.flexible(), spacing: 0), count: 7), spacing: 0) {
                ForEach(0..<daysInMonth.count, id: \.self) { index in
                    if let date = daysInMonth[index] {
                        DayCell(
                            date: date,
                            departureDate: departureDate,
                            returnDate: returnDate,
                            minDate: minDate,
                            maxDate: maxDate,
                            onTap: { onDateTap(date) }
                        )
                    } else {
                        Color.clear
                            .frame(height: 44)
                    }
                }
            }
        }
    }
}
