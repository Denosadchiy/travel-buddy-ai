//
//  FlightTicket.swift
//  Travell Buddy
//
//  Model for flight ticket data with helper methods for trip planning.
//

import Foundation

struct FlightTicket: Identifiable, Codable {
    let id: UUID
    var departureAirport: String
    var arrivalAirport: String
    var departureCity: String
    var arrivalCity: String
    var departureDate: Date
    var arrivalDate: Date
    var airline: String?
    var flightNumber: String?

    init(
        id: UUID = UUID(),
        departureAirport: String,
        arrivalAirport: String,
        departureCity: String,
        arrivalCity: String,
        departureDate: Date,
        arrivalDate: Date,
        airline: String? = nil,
        flightNumber: String? = nil
    ) {
        self.id = id
        self.departureAirport = departureAirport
        self.arrivalAirport = arrivalAirport
        self.departureCity = departureCity
        self.arrivalCity = arrivalCity
        self.departureDate = departureDate
        self.arrivalDate = arrivalDate
        self.airline = airline
        self.flightNumber = flightNumber
    }
}

// MARK: - Trip Planning Helpers

extension FlightTicket {
    /// Возвращает данные для предзаполнения планировщика поездки
    var tripPlanningData: TripPlanningData {
        // Считаем длительность поездки (от вылета до возврата)
        let calendar = Calendar.current
        let components = calendar.dateComponents([.day], from: departureDate, to: arrivalDate)
        let tripDays = max((components.day ?? 0) + 1, 1)

        return TripPlanningData(
            destinationCity: arrivalCity,
            startDate: departureDate,
            endDate: arrivalDate,
            numberOfDays: tripDays
        )
    }

    /// Форматированная строка с информацией о билете
    var formattedSummary: String {
        let formatter = DateFormatter()
        formatter.locale = Locale(identifier: "ru_RU")
        formatter.dateFormat = "d MMM"

        let depDate = formatter.string(from: departureDate)
        let arrDate = formatter.string(from: arrivalDate)

        var summary = "\(departureCity) → \(arrivalCity), \(depDate)–\(arrDate)"

        if let airline = airline, let flightNumber = flightNumber {
            summary += " · \(airline) \(flightNumber)"
        } else if let airline = airline {
            summary += " · \(airline)"
        }

        return summary
    }

    /// Форматированная строка даты вылета
    var formattedDepartureDate: String {
        let formatter = DateFormatter()
        formatter.locale = Locale(identifier: "ru_RU")
        formatter.dateFormat = "d MMMM, HH:mm"
        return formatter.string(from: departureDate)
    }

    /// Форматированная строка даты прилета
    var formattedArrivalDate: String {
        let formatter = DateFormatter()
        formatter.locale = Locale(identifier: "ru_RU")
        formatter.dateFormat = "d MMMM, HH:mm"
        return formatter.string(from: arrivalDate)
    }
}

// MARK: - Trip Planning Data

struct TripPlanningData {
    let destinationCity: String
    let startDate: Date
    let endDate: Date
    let numberOfDays: Int
}

// MARK: - Storage

class FlightTicketStorage {
    static let shared = FlightTicketStorage()

    private let userDefaultsKey = "saved_flight_ticket"

    private init() {}

    /// Сохранить билет
    func save(_ ticket: FlightTicket) {
        if let encoded = try? JSONEncoder().encode(ticket) {
            UserDefaults.standard.set(encoded, forKey: userDefaultsKey)
        }
    }

    /// Загрузить последний сохраненный билет
    func load() -> FlightTicket? {
        guard let data = UserDefaults.standard.data(forKey: userDefaultsKey),
              let ticket = try? JSONDecoder().decode(FlightTicket.self, from: data) else {
            return nil
        }
        return ticket
    }

    /// Удалить сохраненный билет
    func delete() {
        UserDefaults.standard.removeObject(forKey: userDefaultsKey)
    }
}
