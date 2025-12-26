//
//  FlightBookingService.swift
//  Travell Buddy
//
//  Service for fetching flight booking data from Amadeus API.
//

import Foundation

enum BookingError: Error, LocalizedError {
    case invalidBookingCode
    case bookingNotFound
    case networkError
    case authenticationError
    case decodingError
    case unknown

    var errorDescription: String? {
        switch self {
        case .invalidBookingCode:
            return "Проверьте формат кода бронирования"
        case .bookingNotFound:
            return "К сожалению, билет не был найден"
        case .networkError:
            return "Проблема с подключением к интернету"
        case .authenticationError:
            return "Ошибка авторизации с API"
        case .decodingError:
            return "Ошибка обработки данных"
        case .unknown:
            return "Произошла неизвестная ошибка"
        }
    }
}

// MARK: - Amadeus API Models

struct AmadeusTokenResponse: Codable {
    let accessToken: String
    let expiresIn: Int

    enum CodingKeys: String, CodingKey {
        case accessToken = "access_token"
        case expiresIn = "expires_in"
    }
}

struct AmadeusFlightStatusResponse: Codable {
    let data: [FlightStatusData]

    struct FlightStatusData: Codable {
        let flightDesignator: FlightDesignator
        let flightDate: String
        let flightPoints: [FlightPoint]

        struct FlightDesignator: Codable {
            let carrierCode: String
            let flightNumber: String
        }

        struct FlightPoint: Codable {
            let iataCode: String
            let departure: FlightTiming?
            let arrival: FlightTiming?

            struct FlightTiming: Codable {
                let timings: [Timing]

                struct Timing: Codable {
                    let qualifier: String
                    let value: String
                }
            }
        }
    }
}

struct AmadeusFlightOrder: Codable {
    let data: FlightOrderData

    struct FlightOrderData: Codable {
        let flightOffers: [FlightOffer]

        struct FlightOffer: Codable {
            let itineraries: [Itinerary]
            let validatingAirlineCodes: [String]?

            struct Itinerary: Codable {
                let segments: [Segment]

                struct Segment: Codable {
                    let departure: Location
                    let arrival: Location
                    let carrierCode: String?
                    let number: String?

                    struct Location: Codable {
                        let iataCode: String
                        let at: String // ISO 8601 datetime
                    }
                }
            }
        }
    }
}

// MARK: - Flight Booking Service

class FlightBookingService {
    static let shared = FlightBookingService()

    private let apiKey = "eor1ufAunYsVadKCRgB8VV0aA1QME63S"
    private let apiSecret = "qmw1X7AIRsoDPye3"
    private let baseURL = "https://test.api.amadeus.com/v1"

    private var cachedToken: String?
    private var tokenExpirationDate: Date?

    private init() {}

    // MARK: - Public Methods

    /// Fetch flight ticket by flight number and date
    func fetchFlightByNumber(flightNumber: String, date: Date) async throws -> FlightTicket {
        print("✈️ Fetching flight: \(flightNumber) on \(date)")

        // Validate flight number format (at least 3 characters)
        guard flightNumber.count >= 3 else {
            print("❌ Invalid flight number format")
            throw BookingError.invalidBookingCode
        }

        print("✅ Flight number format valid")

        // Get access token
        let token = try await getAccessToken()
        print("✅ Access token obtained")

        // Fetch flight data
        let flightData = try await fetchFlightStatus(flightNumber: flightNumber, date: date, token: token)
        print("✅ Flight data fetched")

        // Convert to FlightTicket
        do {
            let ticket = try convertFlightDataToTicket(flightData: flightData)
            print("✅ Ticket conversion successful")
            return ticket
        } catch {
            print("❌ Ticket conversion failed: \(error)")
            throw error
        }
    }

    // MARK: - Private Methods

    private func getAccessToken() async throws -> String {
        // Return cached token if valid
        if let token = cachedToken,
           let expiration = tokenExpirationDate,
           expiration > Date() {
            return token
        }

        // Request new token
        guard let url = URL(string: "\(baseURL)/security/oauth2/token") else {
            throw BookingError.networkError
        }

        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/x-www-form-urlencoded", forHTTPHeaderField: "Content-Type")

        let body = "grant_type=client_credentials&client_id=\(apiKey)&client_secret=\(apiSecret)"
        request.httpBody = body.data(using: .utf8)

        let (data, response) = try await URLSession.shared.data(for: request)

        guard let httpResponse = response as? HTTPURLResponse,
              (200...299).contains(httpResponse.statusCode) else {
            throw BookingError.authenticationError
        }

        let tokenResponse = try JSONDecoder().decode(AmadeusTokenResponse.self, from: data)

        // Cache token
        cachedToken = tokenResponse.accessToken
        tokenExpirationDate = Date().addingTimeInterval(TimeInterval(tokenResponse.expiresIn - 60))

        return tokenResponse.accessToken
    }

    private func fetchFlightStatus(flightNumber: String, date: Date, token: String) async throws -> AmadeusFlightStatusResponse {
        print("🔍 Searching for flight: \(flightNumber)")

        // Mock данные для популярных рейсов
        if let mockFlight = getMockFlight(for: flightNumber, date: date) {
            return mockFlight
        }

        // Попытка реального запроса к Amadeus Flight Status API
        // Формат: GET /v2/schedule/flights?carrierCode=XX&flightNumber=123&scheduledDepartureDate=2025-03-15
        let dateFormatter = DateFormatter()
        dateFormatter.dateFormat = "yyyy-MM-dd"
        let dateString = dateFormatter.string(from: date)

        // Разбираем номер рейса на код авиакомпании и номер
        let (carrierCode, number) = parseFlightNumber(flightNumber)

        guard let url = URL(string: "\(baseURL)/schedule/flights?carrierCode=\(carrierCode)&flightNumber=\(number)&scheduledDepartureDate=\(dateString)") else {
            throw BookingError.networkError
        }

        var request = URLRequest(url: url)
        request.httpMethod = "GET"
        request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")

        let (data, response) = try await URLSession.shared.data(for: request)

        guard let httpResponse = response as? HTTPURLResponse else {
            throw BookingError.networkError
        }

        if httpResponse.statusCode == 404 {
            throw BookingError.bookingNotFound
        }

        guard (200...299).contains(httpResponse.statusCode) else {
            throw BookingError.networkError
        }

        do {
            return try JSONDecoder().decode(AmadeusFlightStatusResponse.self, from: data)
        } catch {
            print("❌ Decoding error: \(error)")
            throw BookingError.decodingError
        }
    }

    private func parseFlightNumber(_ flightNumber: String) -> (carrierCode: String, number: String) {
        let upper = flightNumber.uppercased()
        var carrierCode = ""
        var number = ""

        for char in upper {
            if char.isLetter {
                carrierCode.append(char)
            } else if char.isNumber {
                number.append(char)
            }
        }

        return (carrierCode, number)
    }

    // MARK: - Mock Data for Testing

    private func getMockFlight(for flightNumber: String, date: Date) -> AmadeusFlightStatusResponse? {
        print("🔍 Checking mock flights for: \(flightNumber.uppercased())")

        let upper = flightNumber.uppercased().replacingOccurrences(of: " ", with: "")
        let dateFormatter = DateFormatter()
        dateFormatter.dateFormat = "yyyy-MM-dd"
        let dateString = dateFormatter.string(from: date)

        // Популярные рейсы с реальными данными
        let mockFlights: [String: (departure: String, arrival: String, depTime: String, arrTime: String, carrier: String, number: String)] = [
            "SU2578": ("SVO", "LHR", "10:30", "13:45", "SU", "2578"),
            "SU2579": ("LHR", "SVO", "15:00", "20:15", "SU", "2579"),
            "TK1984": ("IST", "SVO", "09:15", "14:30", "TK", "1984"),
            "TK2310": ("IST", "AYT", "12:00", "13:15", "TK", "2310"),
            "AF1245": ("CDG", "LED", "11:30", "15:45", "AF", "1245"),
            "LH2135": ("LED", "BER", "08:00", "09:15", "LH", "2135"),
        ]

        guard let flightData = mockFlights[upper] else {
            print("ℹ️ No mock flight for \(upper), will try API")
            return nil
        }

        print("✅ Mock flight found for \(upper)")

        return createMockFlightStatus(
            carrierCode: flightData.carrier,
            flightNumber: flightData.number,
            departureCode: flightData.departure,
            arrivalCode: flightData.arrival,
            flightDate: dateString,
            departureTime: flightData.depTime,
            arrivalTime: flightData.arrTime
        )
    }

    private func createMockFlightStatus(
        carrierCode: String,
        flightNumber: String,
        departureCode: String,
        arrivalCode: String,
        flightDate: String,
        departureTime: String,
        arrivalTime: String
    ) -> AmadeusFlightStatusResponse {
        let departurePoint = AmadeusFlightStatusResponse.FlightStatusData.FlightPoint(
            iataCode: departureCode,
            departure: AmadeusFlightStatusResponse.FlightStatusData.FlightPoint.FlightTiming(
                timings: [
                    AmadeusFlightStatusResponse.FlightStatusData.FlightPoint.FlightTiming.Timing(
                        qualifier: "STD",
                        value: "\(flightDate)T\(departureTime):00"
                    )
                ]
            ),
            arrival: nil
        )

        let arrivalPoint = AmadeusFlightStatusResponse.FlightStatusData.FlightPoint(
            iataCode: arrivalCode,
            departure: nil,
            arrival: AmadeusFlightStatusResponse.FlightStatusData.FlightPoint.FlightTiming(
                timings: [
                    AmadeusFlightStatusResponse.FlightStatusData.FlightPoint.FlightTiming.Timing(
                        qualifier: "STA",
                        value: "\(flightDate)T\(arrivalTime):00"
                    )
                ]
            )
        )

        let flightData = AmadeusFlightStatusResponse.FlightStatusData(
            flightDesignator: AmadeusFlightStatusResponse.FlightStatusData.FlightDesignator(
                carrierCode: carrierCode,
                flightNumber: flightNumber
            ),
            flightDate: flightDate,
            flightPoints: [departurePoint, arrivalPoint]
        )

        return AmadeusFlightStatusResponse(data: [flightData])
    }

    private func createMockOrder(
        departureCode: String,
        departureTime: String,
        arrivalCode: String,
        arrivalTime: String,
        carrierCode: String,
        flightNumber: String
    ) -> AmadeusFlightOrder {
        let segment = AmadeusFlightOrder.FlightOrderData.FlightOffer.Itinerary.Segment(
            departure: AmadeusFlightOrder.FlightOrderData.FlightOffer.Itinerary.Segment.Location(
                iataCode: departureCode,
                at: departureTime
            ),
            arrival: AmadeusFlightOrder.FlightOrderData.FlightOffer.Itinerary.Segment.Location(
                iataCode: arrivalCode,
                at: arrivalTime
            ),
            carrierCode: carrierCode,
            number: flightNumber
        )

        let itinerary = AmadeusFlightOrder.FlightOrderData.FlightOffer.Itinerary(
            segments: [segment]
        )

        let flightOffer = AmadeusFlightOrder.FlightOrderData.FlightOffer(
            itineraries: [itinerary],
            validatingAirlineCodes: [carrierCode]
        )

        let flightOrderData = AmadeusFlightOrder.FlightOrderData(
            flightOffers: [flightOffer]
        )

        return AmadeusFlightOrder(data: flightOrderData)
    }

    private func convertFlightDataToTicket(flightData: AmadeusFlightStatusResponse) throws -> FlightTicket {
        print("🔍 Converting flight data to ticket...")

        guard let flight = flightData.data.first else {
            print("❌ No flight data found")
            throw BookingError.decodingError
        }

        print("Flight: \(flight.flightDesignator.carrierCode)\(flight.flightDesignator.flightNumber)")

        // Находим точки вылета и прилета
        guard flight.flightPoints.count >= 2 else {
            print("❌ Invalid flight points count")
            throw BookingError.decodingError
        }

        let departurePoint = flight.flightPoints[0]
        let arrivalPoint = flight.flightPoints[1]

        print("Route: \(departurePoint.iataCode) → \(arrivalPoint.iataCode)")

        // Получаем время вылета
        guard let depTiming = departurePoint.departure?.timings.first,
              let depTimeString = depTiming.value.split(separator: "T").last else {
            print("❌ No departure time found")
            throw BookingError.decodingError
        }

        // Получаем время прилета
        guard let arrTiming = arrivalPoint.arrival?.timings.first,
              let arrTimeString = arrTiming.value.split(separator: "T").last else {
            print("❌ No arrival time found")
            throw BookingError.decodingError
        }

        // Парсим даты
        let dateFormatter = ISO8601DateFormatter()
        dateFormatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]

        let depDateString = "\(flight.flightDate)T\(depTimeString)"
        let arrDateString = "\(flight.flightDate)T\(arrTimeString)"

        var departureDate = dateFormatter.date(from: depDateString)
        if departureDate == nil {
            let modifiedString = depDateString.hasSuffix("Z") ? depDateString : depDateString + "Z"
            departureDate = dateFormatter.date(from: modifiedString)
        }

        var arrivalDate = dateFormatter.date(from: arrDateString)
        if arrivalDate == nil {
            let modifiedString = arrDateString.hasSuffix("Z") ? arrDateString : arrDateString + "Z"
            arrivalDate = dateFormatter.date(from: modifiedString)
        }

        guard let departureDate = departureDate, let arrivalDate = arrivalDate else {
            print("❌ Failed to parse dates")
            throw BookingError.decodingError
        }

        print("✅ Dates parsed successfully")

        // Получаем названия городов
        let departureCity = AirportDatabase.shared.findCity(byAirportCode: departurePoint.iataCode)?.cityName ?? departurePoint.iataCode
        let arrivalCity = AirportDatabase.shared.findCity(byAirportCode: arrivalPoint.iataCode)?.cityName ?? arrivalPoint.iataCode

        print("Cities: \(departureCity) → \(arrivalCity)")

        let airline = flight.flightDesignator.carrierCode
        let flightNumber = flight.flightDesignator.flightNumber

        print("✅ Ticket created successfully")

        return FlightTicket(
            departureAirport: departurePoint.iataCode,
            arrivalAirport: arrivalPoint.iataCode,
            departureCity: departureCity,
            arrivalCity: arrivalCity,
            departureDate: departureDate,
            arrivalDate: arrivalDate,
            airline: airline,
            flightNumber: flightNumber
        )
    }

    private func convertToFlightTicket(flightOrder: AmadeusFlightOrder, bookingCode: String) throws -> FlightTicket {
        print("🔍 Converting flight order to ticket...")
        print("Flight offers count: \(flightOrder.data.flightOffers.count)")

        guard let firstOffer = flightOrder.data.flightOffers.first else {
            print("❌ No flight offers found")
            throw BookingError.decodingError
        }

        print("Itineraries count: \(firstOffer.itineraries.count)")

        guard let firstItinerary = firstOffer.itineraries.first else {
            print("❌ No itineraries found")
            throw BookingError.decodingError
        }

        print("Segments count: \(firstItinerary.segments.count)")

        guard let firstSegment = firstItinerary.segments.first,
              let lastSegment = firstItinerary.segments.last else {
            print("❌ No segments found")
            throw BookingError.decodingError
        }

        print("Departure: \(firstSegment.departure.iataCode) at \(firstSegment.departure.at)")
        print("Arrival: \(lastSegment.arrival.iataCode) at \(lastSegment.arrival.at)")

        // Parse dates
        let dateFormatter = ISO8601DateFormatter()
        dateFormatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]

        // Сначала попытка парсинга с оригинальным форматом
        var departureDate = dateFormatter.date(from: firstSegment.departure.at)

        // Если не получилось, добавляем Z (UTC) к строке
        if departureDate == nil {
            let modifiedString = firstSegment.departure.at.hasSuffix("Z") ? firstSegment.departure.at : firstSegment.departure.at + "Z"
            departureDate = dateFormatter.date(from: modifiedString)
        }

        guard let departureDate = departureDate else {
            print("❌ Failed to parse departure date: \(firstSegment.departure.at)")
            throw BookingError.decodingError
        }

        // То же самое для даты прилета
        var arrivalDate = dateFormatter.date(from: lastSegment.arrival.at)

        if arrivalDate == nil {
            let modifiedString = lastSegment.arrival.at.hasSuffix("Z") ? lastSegment.arrival.at : lastSegment.arrival.at + "Z"
            arrivalDate = dateFormatter.date(from: modifiedString)
        }

        guard let arrivalDate = arrivalDate else {
            print("❌ Failed to parse arrival date: \(lastSegment.arrival.at)")
            throw BookingError.decodingError
        }

        print("✅ Dates parsed successfully")

        // Get city names from airport codes
        let departureCity = AirportDatabase.shared.findCity(byAirportCode: firstSegment.departure.iataCode)?.cityName ?? firstSegment.departure.iataCode
        let arrivalCity = AirportDatabase.shared.findCity(byAirportCode: lastSegment.arrival.iataCode)?.cityName ?? lastSegment.arrival.iataCode

        print("Cities: \(departureCity) → \(arrivalCity)")

        // Get airline info
        let airline = firstSegment.carrierCode
        let flightNumber = firstSegment.number

        print("✅ Ticket created successfully")

        return FlightTicket(
            departureAirport: firstSegment.departure.iataCode,
            arrivalAirport: lastSegment.arrival.iataCode,
            departureCity: departureCity,
            arrivalCity: arrivalCity,
            departureDate: departureDate,
            arrivalDate: arrivalDate,
            airline: airline,
            flightNumber: flightNumber
        )
    }
}

// MARK: - AirportDatabase Extension

extension AirportDatabase {
    func findCity(byAirportCode code: String) -> CityAirport? {
        return cities.first { city in
            city.airports.contains { $0.code == code }
        }
    }
}
