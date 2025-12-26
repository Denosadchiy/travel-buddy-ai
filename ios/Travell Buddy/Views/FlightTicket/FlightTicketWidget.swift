//
//  FlightTicketWidget.swift
//  Travell Buddy
//
//  Widget for displaying saved flight ticket on home screen.
//

import SwiftUI

struct FlightTicketWidget: View {
    let savedTicket: FlightTicket?
    let onAddTicket: () -> Void
    let onUseTicket: (FlightTicket) -> Void

    var body: some View {
        Group {
            if let ticket = savedTicket {
                savedTicketView(ticket)
            } else {
                emptyTicketView
            }
        }
    }

    // MARK: - Empty State

    private var emptyTicketView: some View {
        Button(action: onAddTicket) {
            HStack(spacing: 16) {
                // Иконка
                ZStack {
                    Circle()
                        .fill(
                            LinearGradient(
                                colors: [
                                    Color(red: 0.4, green: 0.6, blue: 1.0),
                                    Color(red: 0.2, green: 0.4, blue: 0.9)
                                ],
                                startPoint: .topLeading,
                                endPoint: .bottomTrailing
                            )
                        )
                        .frame(width: 56, height: 56)

                    Image(systemName: "airplane.circle.fill")
                        .font(.system(size: 28, weight: .semibold))
                        .foregroundColor(.white)
                }

                // Текст
                VStack(alignment: .leading, spacing: 6) {
                    Text("У меня уже есть билет")
                        .font(.system(size: 17, weight: .semibold, design: .rounded))
                        .foregroundColor(Color(.label))

                    Text("Загрузи авиабилет, и я соберу маршрут по этой поездке")
                        .font(.system(size: 14))
                        .foregroundColor(Color(.secondaryLabel))
                        .fixedSize(horizontal: false, vertical: true)
                }

                Spacer()

                // Chevron
                Image(systemName: "chevron.right")
                    .font(.system(size: 14, weight: .semibold))
                    .foregroundColor(Color(.tertiaryLabel))
            }
            .padding(18)
            .frame(maxWidth: .infinity)
            .background(
                RoundedRectangle(cornerRadius: 18, style: .continuous)
                    .fill(Color(.secondarySystemBackground))
            )
            .overlay(
                RoundedRectangle(cornerRadius: 18, style: .continuous)
                    .stroke(
                        Color(red: 0.4, green: 0.6, blue: 1.0).opacity(0.2),
                        lineWidth: 1.5
                    )
            )
        }
        .buttonStyle(.plain)
    }

    // MARK: - Saved Ticket View

    private func savedTicketView(_ ticket: FlightTicket) -> some View {
        Button {
            onUseTicket(ticket)
        } label: {
            VStack(alignment: .leading, spacing: 16) {
                // Заголовок
                HStack {
                    Label("Мой авиабилет", systemImage: "airplane")
                        .font(.system(size: 15, weight: .semibold))
                        .foregroundColor(Color(red: 0.3, green: 0.5, blue: 0.9))

                    Spacer()

                    Button {
                        onAddTicket()
                    } label: {
                        Text("Изменить")
                            .font(.system(size: 14, weight: .medium))
                            .foregroundColor(.travelBuddyOrange)
                    }
                    .buttonStyle(.plain)
                }

                // Информация о билете
                VStack(spacing: 14) {
                    // Маршрут
                    HStack(alignment: .center, spacing: 12) {
                        VStack(alignment: .leading, spacing: 4) {
                            Text(ticket.departureCity)
                                .font(.system(size: 20, weight: .bold, design: .rounded))
                                .foregroundColor(Color(.label))

                            Text(ticket.departureAirport)
                                .font(.system(size: 13))
                                .foregroundColor(Color(.secondaryLabel))
                        }

                        Spacer()

                        Image(systemName: "arrow.right")
                            .font(.system(size: 16, weight: .semibold))
                            .foregroundColor(.travelBuddyOrange)

                        Spacer()

                        VStack(alignment: .trailing, spacing: 4) {
                            Text(ticket.arrivalCity)
                                .font(.system(size: 20, weight: .bold, design: .rounded))
                                .foregroundColor(Color(.label))

                            Text(ticket.arrivalAirport)
                                .font(.system(size: 13))
                                .foregroundColor(Color(.secondaryLabel))
                        }
                    }

                    Divider()

                    // Даты и авиакомпания
                    HStack {
                        VStack(alignment: .leading, spacing: 4) {
                            Text("Даты")
                                .font(.system(size: 12, weight: .medium))
                                .foregroundColor(Color(.secondaryLabel))

                            Text(formattedDateRange(ticket))
                                .font(.system(size: 14, weight: .medium))
                                .foregroundColor(Color(.label))
                        }

                        Spacer()

                        if let airline = ticket.airline {
                            VStack(alignment: .trailing, spacing: 4) {
                                Text("Рейс")
                                    .font(.system(size: 12, weight: .medium))
                                    .foregroundColor(Color(.secondaryLabel))

                                HStack(spacing: 4) {
                                    Text(airline)
                                        .font(.system(size: 14, weight: .medium))
                                        .foregroundColor(Color(.label))

                                    if let flightNumber = ticket.flightNumber {
                                        Text(flightNumber)
                                            .font(.system(size: 14, weight: .medium))
                                            .foregroundColor(Color(.label))
                                    }
                                }
                            }
                        }
                    }
                }
                .padding(14)
                .background(
                    RoundedRectangle(cornerRadius: 12, style: .continuous)
                        .fill(Color(.tertiarySystemBackground))
                )

                // CTA
                HStack {
                    Image(systemName: "sparkles")
                        .font(.system(size: 14, weight: .semibold))
                    Text("Создать маршрут для этой поездки")
                        .font(.system(size: 15, weight: .semibold))
                }
                .foregroundColor(.white)
                .frame(maxWidth: .infinity)
                .padding(.vertical, 14)
                .background(LinearGradient.travelBuddyPrimaryHorizontal)
                .cornerRadius(12)
            }
            .padding(18)
            .frame(maxWidth: .infinity)
            .background(
                RoundedRectangle(cornerRadius: 18, style: .continuous)
                    .fill(Color(.secondarySystemBackground))
                    .cardShadow()
            )
        }
        .buttonStyle(.plain)
    }

    // MARK: - Helpers

    private func formattedDateRange(_ ticket: FlightTicket) -> String {
        let formatter = DateFormatter()
        formatter.locale = Locale(identifier: "ru_RU")
        formatter.dateFormat = "d MMM"

        let start = formatter.string(from: ticket.departureDate)
        let end = formatter.string(from: ticket.arrivalDate)

        return "\(start) – \(end)"
    }
}
