//
//  TripPlanningAPIClient.swift
//  Travell Buddy
//
//  API client for trip planning backend endpoints.
//

import Foundation

final class TripPlanningAPIClient {
    static let shared = TripPlanningAPIClient()

    private let session: URLSession
    private let requestBuilder: RequestBuilder

    init(
        session: URLSession = .shared,
        requestBuilder: RequestBuilder = RequestBuilder()
    ) {
        self.session = session
        self.requestBuilder = requestBuilder
    }

    // MARK: - Public Methods

    /// Create a new trip
    /// POST /trips
    func createTrip(_ request: TripCreateRequestDTO) async throws -> TripResponseDTO {
        print("🌍 Creating trip: \(request.city)")

        // Encode request body
        let encoder = JSONEncoder()
        encoder.keyEncodingStrategy = .convertToSnakeCase
        let bodyData = try encoder.encode(request)

        // Build request
        let urlRequest = try requestBuilder.buildRequest(
            path: "trips",
            method: .post,
            body: bodyData
        )

        // Execute request
        let (data, response) = try await session.data(for: urlRequest)

        // Handle response
        guard let httpResponse = response as? HTTPURLResponse else {
            throw APIError.networkError(NSError(domain: "Invalid response", code: -1))
        }

        print("📡 Response status: \(httpResponse.statusCode)")

        switch httpResponse.statusCode {
        case 200, 201:
            // Success - decode response
            let decoder = JSONDecoder()
            // Don't use convertFromSnakeCase - CodingKeys handle snake_case mapping
            do {
                let tripResponse = try decoder.decode(TripResponseDTO.self, from: data)
                print("✅ Trip created: \(tripResponse.id)")
                return tripResponse
            } catch {
                print("❌ Decoding error: \(error)")
                if let jsonString = String(data: data, encoding: .utf8) {
                    print("📄 Response JSON: \(jsonString.prefix(500))")
                }
                throw APIError.decodingError(error)
            }

        case 404:
            throw APIError.tripNotFound

        case 401:
            throw APIError.unauthorized

        default:
            let message = String(data: data, encoding: .utf8)
            print("❌ HTTP error: \(httpResponse.statusCode), message: \(message ?? "none")")
            throw APIError.httpError(statusCode: httpResponse.statusCode, message: message)
        }
    }

    /// Generate trip plan (macro + POI + route optimization)
    /// POST /trips/{trip_id}/plan
    func planTrip(tripId: String) async throws -> ItineraryResponseDTO {
        print("🗺️ Planning trip: \(tripId)")

        // Build request
        let urlRequest = try requestBuilder.buildRequest(
            path: "trips/\(tripId)/plan",
            method: .post
        )

        // Execute request
        let (data, response) = try await session.data(for: urlRequest)

        // Handle response
        guard let httpResponse = response as? HTTPURLResponse else {
            throw APIError.networkError(NSError(domain: "Invalid response", code: -1))
        }

        print("📡 Response status: \(httpResponse.statusCode)")

        switch httpResponse.statusCode {
        case 201:
            // Success - decode itinerary
            let decoder = JSONDecoder()
            // CodingKeys handle snake_case mapping
            do {
                let itinerary = try decoder.decode(ItineraryResponseDTO.self, from: data)
                print("✅ Plan generated with \(itinerary.days.count) days")
                return itinerary
            } catch {
                print("❌ Decoding error: \(error)")
                throw APIError.decodingError(error)
            }

        case 404:
            throw APIError.tripNotFound

        case 401:
            throw APIError.unauthorized

        default:
            let message = String(data: data, encoding: .utf8)
            print("❌ HTTP error: \(httpResponse.statusCode), message: \(message ?? "none")")
            throw APIError.httpError(statusCode: httpResponse.statusCode, message: message)
        }
    }

    /// Get trip itinerary
    /// GET /trips/{trip_id}/itinerary
    func getItinerary(tripId: String) async throws -> ItineraryResponseDTO {
        print("📋 Fetching itinerary: \(tripId)")

        // Build request
        let urlRequest = try requestBuilder.buildRequest(
            path: "trips/\(tripId)/itinerary",
            method: .get
        )

        // Execute request
        let (data, response) = try await session.data(for: urlRequest)

        // Handle response
        guard let httpResponse = response as? HTTPURLResponse else {
            throw APIError.networkError(NSError(domain: "Invalid response", code: -1))
        }

        print("📡 Response status: \(httpResponse.statusCode)")

        switch httpResponse.statusCode {
        case 200:
            // Success - decode itinerary
            let decoder = JSONDecoder()
            // CodingKeys handle snake_case mapping
            do {
                let itinerary = try decoder.decode(ItineraryResponseDTO.self, from: data)
                print("✅ Itinerary fetched with \(itinerary.days.count) days")
                return itinerary
            } catch {
                print("❌ Decoding error: \(error)")
                if let jsonString = String(data: data, encoding: .utf8) {
                    print("📄 Response JSON: \(jsonString.prefix(500))")
                }
                throw APIError.decodingError(error)
            }

        case 404:
            throw APIError.tripNotFound

        case 401:
            throw APIError.unauthorized

        default:
            let message = String(data: data, encoding: .utf8)
            print("❌ HTTP error: \(httpResponse.statusCode), message: \(message ?? "none")")
            throw APIError.httpError(statusCode: httpResponse.statusCode, message: message)
        }
    }

    /// Send chat message to trip
    /// POST /trips/{trip_id}/chat
    func sendChatMessage(tripId: UUID, message: String) async throws -> TripChatResponseDTO {
        print("💬 Sending chat message for trip: \(tripId)")

        // Encode request body
        let chatRequest = TripChatRequestDTO(message: message)
        let encoder = JSONEncoder()
        let bodyData = try encoder.encode(chatRequest)

        // Build request
        let urlRequest = try requestBuilder.buildRequest(
            path: "trips/\(tripId.uuidString)/chat",
            method: .post,
            body: bodyData
        )

        // Execute request
        let (data, response) = try await session.data(for: urlRequest)

        // Handle response
        guard let httpResponse = response as? HTTPURLResponse else {
            throw APIError.networkError(NSError(domain: "Invalid response", code: -1))
        }

        print("📡 Response status: \(httpResponse.statusCode)")

        switch httpResponse.statusCode {
        case 200:
            // Success - decode chat response
            let decoder = JSONDecoder()
            // CodingKeys handle snake_case mapping
            do {
                let chatResponse = try decoder.decode(TripChatResponseDTO.self, from: data)
                print("✅ Chat message sent, assistant replied: \(chatResponse.assistantMessage.prefix(50))...")
                return chatResponse
            } catch {
                print("❌ Decoding error: \(error)")
                if let jsonString = String(data: data, encoding: .utf8) {
                    print("📄 Response JSON: \(jsonString.prefix(500))")
                }
                throw APIError.decodingError(error)
            }

        case 404:
            throw APIError.tripNotFound

        case 401:
            throw APIError.unauthorized

        default:
            let message = String(data: data, encoding: .utf8)
            print("❌ HTTP error: \(httpResponse.statusCode), message: \(message ?? "none")")
            throw APIError.httpError(statusCode: httpResponse.statusCode, message: message)
        }
    }
}
