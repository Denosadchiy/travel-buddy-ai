//
//  DayCell.swift
//  Travell Buddy
//
//  Single day cell in calendar grid.
//

import SwiftUI

struct DayCell: View {
    let date: Date
    let departureDate: Date?
    let returnDate: Date?
    let minDate: Date
    let maxDate: Date
    let onTap: () -> Void

    private var calendar: Calendar { Calendar.current }
    private let warmWhite = Color(red: 0.95, green: 0.94, blue: 0.92)
    private let mutedWarmGray = Color(red: 0.70, green: 0.67, blue: 0.63)

    private var isToday: Bool {
        calendar.isDateInToday(date)
    }

    private var isDisabled: Bool {
        date < minDate || date > maxDate
    }

    private var isDeparture: Bool {
        departureDate != nil && calendar.isDate(date, inSameDayAs: departureDate!)
    }

    private var isReturn: Bool {
        returnDate != nil && calendar.isDate(date, inSameDayAs: returnDate!)
    }

    private var isInRange: Bool {
        guard let departure = departureDate, let returnDate = returnDate else { return false }
        return date >= departure && date <= returnDate
    }

    private var isRangeStart: Bool {
        guard let departure = departureDate else { return false }
        return calendar.isDate(date, inSameDayAs: departure)
    }

    private var isRangeEnd: Bool {
        guard let returnDate = returnDate else { return false }
        return calendar.isDate(date, inSameDayAs: returnDate)
    }

    var body: some View {
        Button(action: onTap) {
            ZStack {
                // Фон диапазона (сплошная линия между днями)
                if isInRange {
                    Rectangle()
                        .fill(Color.travelBuddyOrange.opacity(0.18))
                }

                // Круг для выбранных дат
                if isDeparture || isReturn {
                    Circle()
                        .fill(Color.travelBuddyOrange)
                        .frame(width: 36, height: 36)
                        .shadow(color: Color.travelBuddyOrange.opacity(0.35), radius: 4, x: 0, y: 2)
                }

                // Подсветка сегодняшнего дня (если не выбран)
                if isToday && !isDeparture && !isReturn {
                    Circle()
                        .stroke(Color.travelBuddyOrange, lineWidth: 1.5)
                        .frame(width: 36, height: 36)
                }

                // Текст даты
                Text("\(calendar.component(.day, from: date))")
                    .font(.system(size: 16, weight: isDeparture || isReturn ? .semibold : .regular))
                    .foregroundColor(
                        isDisabled ? mutedWarmGray.opacity(0.45) :
                        isDeparture || isReturn ? .white :
                        isToday ? Color.travelBuddyOrange :
                        warmWhite
                    )
            }
            .frame(height: 44)
        }
        .buttonStyle(.plain)
        .disabled(isDisabled)
        .accessibilityLabel(accessibilityLabel)
        .accessibilityValue(accessibilityValue)
    }

    private var accessibilityLabel: String {
        let formatter = DateFormatter()
        formatter.locale = Locale(identifier: "ru_RU")
        formatter.dateFormat = "d MMMM"
        let dateString = formatter.string(from: date)

        if isDeparture {
            return "Дата вылета: \(dateString)"
        } else if isReturn {
            return "Дата возврата: \(dateString)"
        } else if isInRange {
            return "Дата в диапазоне: \(dateString)"
        } else if isToday {
            return "Сегодня: \(dateString)"
        } else {
            return dateString
        }
    }

    private var accessibilityValue: String {
        if isDeparture {
            return "Выбрана как дата вылета"
        } else if isReturn {
            return "Выбрана как дата возврата"
        } else if isInRange {
            return "Входит в выбранный диапазон"
        } else {
            return ""
        }
    }
}
