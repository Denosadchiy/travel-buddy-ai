//
//  FlightTicketInputView.swift
//  Travell Buddy
//
//  Screen for adding flight ticket by flight number and date.
//

import SwiftUI

struct FlightTicketInputView: View {
    @Environment(\.dismiss) private var dismiss

    // Outbound flight (туда)
    @State private var outboundFlightNumber: String = ""
    @State private var outboundDate: Date = Calendar.current.date(byAdding: .day, value: 7, to: Date()) ?? Date()

    // Return flight (обратно) - optional
    @State private var hasReturnFlight: Bool = false
    @State private var returnFlightNumber: String = ""
    @State private var returnDate: Date = Calendar.current.date(byAdding: .day, value: 14, to: Date()) ?? Date()

    @State private var isLoading: Bool = false
    @State private var errorMessage: String?
    @State private var foundTicket: FlightTicket?
    @State private var navigateToPlanner: Bool = false

    @FocusState private var isOutboundFieldFocused: Bool
    @FocusState private var isReturnFieldFocused: Bool

    var body: some View {
        ZStack {
            LinearGradient.travelBuddyBackgroundAlt
                .ignoresSafeArea()

            ScrollView {
                VStack(spacing: 24) {
                    headerSection

                    if foundTicket == nil {
                        flightInputSection
                    } else {
                        ticketPreviewSection
                    }
                }
                .padding(.horizontal, 20)
                .padding(.top, 16)
                .padding(.bottom, 120)
            }
        }
        .navigationTitle("Добавить билет")
        .navigationBarTitleDisplayMode(.inline)
        .safeAreaInset(edge: .bottom) {
            bottomButton
        }
        .background(
            NavigationLink(
                destination: NewTripView(prefilledTicket: foundTicket),
                isActive: $navigateToPlanner
            ) {
                EmptyView()
            }
            .hidden()
        )
    }

    // MARK: - Header

    private var headerSection: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text(foundTicket == nil ? "Введи данные рейса" : "Билет найден")
                .font(.system(size: 24, weight: .bold, design: .rounded))
                .foregroundColor(Color(.label))

            Text(foundTicket == nil ? "Укажи номер рейса и дату вылета" : "Проверь данные перед добавлением")
                .font(.system(size: 15))
                .foregroundColor(Color(.secondaryLabel))
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    // MARK: - Flight Input Section

    private var flightInputSection: some View {
        VStack(alignment: .leading, spacing: 20) {
            // Outbound flight
            VStack(alignment: .leading, spacing: 16) {
                Label("Рейс туда", systemImage: "airplane.departure")
                    .font(.system(size: 16, weight: .semibold))
                    .foregroundColor(Color(.label))

                VStack(spacing: 12) {
                    // Flight number
                    VStack(alignment: .leading, spacing: 8) {
                        Text("Номер рейса")
                            .font(.system(size: 13, weight: .medium))
                            .foregroundColor(Color(.secondaryLabel))

                        TextField("Например: SU2578", text: $outboundFlightNumber)
                            .font(.system(size: 18, weight: .medium, design: .monospaced))
                            .textCase(.uppercase)
                            .autocorrectionDisabled()
                            .keyboardType(.asciiCapable)
                            .focused($isOutboundFieldFocused)
                            .padding(14)
                            .background(
                                RoundedRectangle(cornerRadius: 10, style: .continuous)
                                    .fill(Color(.tertiarySystemBackground))
                            )
                            .overlay(
                                RoundedRectangle(cornerRadius: 10, style: .continuous)
                                    .stroke(isOutboundFieldFocused ? Color.travelBuddyOrange : Color.clear, lineWidth: 2)
                            )
                    }

                    // Date picker
                    VStack(alignment: .leading, spacing: 8) {
                        Text("Дата вылета")
                            .font(.system(size: 13, weight: .medium))
                            .foregroundColor(Color(.secondaryLabel))

                        DatePicker("", selection: $outboundDate, displayedComponents: .date)
                            .datePickerStyle(.compact)
                            .labelsHidden()
                            .padding(10)
                            .background(
                                RoundedRectangle(cornerRadius: 10, style: .continuous)
                                    .fill(Color(.tertiarySystemBackground))
                            )
                    }
                }
            }
            .padding(18)
            .background(
                RoundedRectangle(cornerRadius: 16, style: .continuous)
                    .fill(Color(.systemBackground))
                    .lightShadow()
            )

            // Return flight toggle
            Toggle(isOn: $hasReturnFlight) {
                Label("Добавить обратный рейс", systemImage: "arrow.left.arrow.right")
                    .font(.system(size: 15, weight: .medium))
            }
            .tint(.travelBuddyOrange)
            .padding(.horizontal, 4)

            // Return flight (if enabled)
            if hasReturnFlight {
                VStack(alignment: .leading, spacing: 16) {
                    Label("Рейс обратно", systemImage: "airplane.arrival")
                        .font(.system(size: 16, weight: .semibold))
                        .foregroundColor(Color(.label))

                    VStack(spacing: 12) {
                        // Flight number
                        VStack(alignment: .leading, spacing: 8) {
                            Text("Номер рейса")
                                .font(.system(size: 13, weight: .medium))
                                .foregroundColor(Color(.secondaryLabel))

                            TextField("Например: SU2579", text: $returnFlightNumber)
                                .font(.system(size: 18, weight: .medium, design: .monospaced))
                                .textCase(.uppercase)
                                .autocorrectionDisabled()
                                .keyboardType(.asciiCapable)
                                .focused($isReturnFieldFocused)
                                .padding(14)
                                .background(
                                    RoundedRectangle(cornerRadius: 10, style: .continuous)
                                        .fill(Color(.tertiarySystemBackground))
                                )
                                .overlay(
                                    RoundedRectangle(cornerRadius: 10, style: .continuous)
                                        .stroke(isReturnFieldFocused ? Color.travelBuddyOrange : Color.clear, lineWidth: 2)
                                )
                        }

                        // Date picker
                        VStack(alignment: .leading, spacing: 8) {
                            Text("Дата вылета")
                                .font(.system(size: 13, weight: .medium))
                                .foregroundColor(Color(.secondaryLabel))

                            DatePicker("", selection: $returnDate, displayedComponents: .date)
                                .datePickerStyle(.compact)
                                .labelsHidden()
                                .padding(10)
                                .background(
                                    RoundedRectangle(cornerRadius: 10, style: .continuous)
                                        .fill(Color(.tertiarySystemBackground))
                                )
                        }
                    }
                }
                .padding(18)
                .background(
                    RoundedRectangle(cornerRadius: 16, style: .continuous)
                        .fill(Color(.systemBackground))
                        .lightShadow()
                )
                .transition(.opacity.combined(with: .move(edge: .top)))
            }

            // Error message
            if let error = errorMessage {
                HStack(spacing: 8) {
                    Image(systemName: "exclamationmark.circle.fill")
                        .font(.system(size: 14))
                    Text(error)
                        .font(.system(size: 14))
                }
                .foregroundColor(.red)
                .frame(maxWidth: .infinity, alignment: .leading)
                .padding(.horizontal, 4)
            }

            // Search button
            Button {
                Task {
                    await searchFlights()
                }
            } label: {
                HStack {
                    if isLoading {
                        ProgressView()
                            .progressViewStyle(CircularProgressViewStyle(tint: .white))
                    } else {
                        Image(systemName: "magnifyingglass")
                            .font(.system(size: 16, weight: .semibold))
                    }
                    Text(isLoading ? "Поиск билета..." : "Найти билет")
                        .font(.system(size: 16, weight: .semibold))
                }
                .foregroundColor(.white)
                .frame(maxWidth: .infinity)
                .padding(.vertical, 14)
                .background(LinearGradient.travelBuddyPrimaryHorizontal)
                .cornerRadius(12)
            }
            .buttonStyle(.plain)
            .disabled(!isFormValid || isLoading)
            .opacity(isFormValid && !isLoading ? 1.0 : 0.5)
        }
        .animation(.spring(), value: hasReturnFlight)
        .onAppear {
            isOutboundFieldFocused = true
        }
    }

    // MARK: - Ticket Preview Section

    private var ticketPreviewSection: some View {
        Group {
            if let ticket = foundTicket {
                VStack(alignment: .leading, spacing: 16) {
                    Label("Данные билета", systemImage: "checkmark.circle.fill")
                        .font(.system(size: 16, weight: .semibold))
                        .foregroundColor(.green)

                    VStack(spacing: 14) {
                        // Route
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

                        // Dates
                        HStack {
                            VStack(alignment: .leading, spacing: 4) {
                                Text("Вылет")
                                    .font(.system(size: 12, weight: .medium))
                                    .foregroundColor(Color(.secondaryLabel))

                                Text(ticket.formattedDepartureDate)
                                    .font(.system(size: 14, weight: .medium))
                                    .foregroundColor(Color(.label))
                            }

                            Spacer()

                            VStack(alignment: .trailing, spacing: 4) {
                                Text("Прилет")
                                    .font(.system(size: 12, weight: .medium))
                                    .foregroundColor(Color(.secondaryLabel))

                                Text(ticket.formattedArrivalDate)
                                    .font(.system(size: 14, weight: .medium))
                                    .foregroundColor(Color(.label))
                            }
                        }

                        // Flight info (if available)
                        if let airline = ticket.airline {
                            Divider()

                            HStack {
                                VStack(alignment: .leading, spacing: 4) {
                                    Text("Авиакомпания")
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

                                Spacer()
                            }
                        }
                    }
                    .padding(14)
                    .background(
                        RoundedRectangle(cornerRadius: 12, style: .continuous)
                            .fill(Color(.tertiarySystemBackground))
                    )

                    // Change button
                    Button {
                        foundTicket = nil
                        errorMessage = nil
                        outboundFlightNumber = ""
                        returnFlightNumber = ""
                    } label: {
                        HStack {
                            Image(systemName: "arrow.clockwise")
                                .font(.system(size: 14))
                            Text("Ввести другой рейс")
                                .font(.system(size: 15, weight: .medium))
                        }
                        .foregroundColor(.travelBuddyOrange)
                    }
                    .buttonStyle(.plain)
                }
                .padding(18)
                .background(
                    RoundedRectangle(cornerRadius: 16, style: .continuous)
                        .fill(Color(.systemBackground))
                        .lightShadow()
                )
            }
        }
    }

    // MARK: - Bottom Button

    private var bottomButton: some View {
        Button {
            saveAndProceed()
        } label: {
            HStack {
                Image(systemName: "checkmark.circle.fill")
                    .font(.system(size: 18, weight: .semibold))
                Text("Сохранить и перейти к маршруту")
                    .font(.system(size: 17, weight: .semibold))
            }
            .foregroundColor(.white)
            .frame(maxWidth: .infinity)
            .padding(.vertical, 16)
            .background(LinearGradient.travelBuddyPrimaryHorizontal)
            .cornerRadius(14)
            .buttonShadow()
        }
        .buttonStyle(.plain)
        .padding(.horizontal, 20)
        .padding(.vertical, 16)
        .background(
            Color(.systemBackground)
                .shadow(color: Color.black.opacity(0.08), radius: 20, x: 0, y: -4)
        )
        .disabled(foundTicket == nil)
        .opacity(foundTicket != nil ? 1.0 : 0.5)
    }

    // MARK: - Helpers

    private var isFormValid: Bool {
        !outboundFlightNumber.isEmpty && (!hasReturnFlight || !returnFlightNumber.isEmpty)
    }

    private func searchFlights() async {
        isLoading = true
        errorMessage = nil

        do {
            // Search for outbound flight
            let ticket = try await FlightBookingService.shared.fetchFlightByNumber(
                flightNumber: outboundFlightNumber,
                date: outboundDate
            )
            foundTicket = ticket
        } catch let error as BookingError {
            errorMessage = error.errorDescription
        } catch {
            errorMessage = "Произошла неизвестная ошибка"
        }

        isLoading = false
    }

    private func saveAndProceed() {
        guard let ticket = foundTicket else { return }

        FlightTicketStorage.shared.save(ticket)
        navigateToPlanner = true
    }
}
