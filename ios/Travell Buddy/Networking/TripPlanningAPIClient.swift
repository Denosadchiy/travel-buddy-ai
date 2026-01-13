//
//  TripPlanningAPIClient.swift
//  Travell Buddy
//
//  API client for trip planning backend endpoints.
//

import Foundation

// MARK: - Protocol

protocol TripPlanningAPIClientProtocol {
    func createTrip(_ request: TripCreateRequestDTO) async throws -> TripResponseDTO
    func generatePlan(tripId: UUID) async throws -> ItineraryResponseDTO
    func generateFastDraft(tripId: UUID) async throws -> ItineraryResponseDTO
    func planTrip(tripId: String) async throws -> ItineraryResponseDTO
    func getItinerary(tripId: String) async throws -> ItineraryResponseDTO
    func sendChatMessage(tripId: UUID, message: String) async throws -> TripChatResponseDTO

    // AI Studio endpoints
    func getDayStudio(tripId: UUID, dayId: Int) async throws -> DayStudioResponseDTO
    func applyDayChanges(tripId: UUID, dayId: Int, request: ApplyChangesRequestDTO) async throws -> ApplyChangesResponseDTO
    func searchPlaces(request: PlaceSearchRequestDTO) async throws -> PlaceSearchResponseDTO
}

// MARK: - Implementation

final class TripPlanningAPIClient: TripPlanningAPIClientProtocol {
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

        case 402:
            throw APIError.paywallRequired

        default:
            let message = String(data: data, encoding: .utf8)
            print("❌ HTTP error: \(httpResponse.statusCode), message: \(message ?? "none")")
            throw APIError.httpError(statusCode: httpResponse.statusCode, message: message)
        }
    }

    /// Generate trip plan (macro + POI + route optimization)
    /// POST /trips/{trip_id}/plan
    func generatePlan(tripId: UUID) async throws -> ItineraryResponseDTO {
        try await planTrip(tripId: tripId.uuidString.lowercased())
    }

    /// Generate fast draft itinerary (optimized for p95 < 20s)
    /// POST /trips/{trip_id}/fast-draft
    func generateFastDraft(tripId: UUID) async throws -> ItineraryResponseDTO {
        print("⚡ Generating fast draft: \(tripId)")

        // Build request with extended timeout for new cities (external POI fetching can take 40-60s)
        let fastDraftBuilder = RequestBuilder(timeout: AppConfig.fastDraftTimeout)
        let urlRequest = try fastDraftBuilder.buildRequest(
            path: "trips/\(tripId.uuidString.lowercased())/fast-draft",
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
        case 200, 201:
            // Success - decode itinerary
            let decoder = JSONDecoder()
            do {
                let itinerary = try decoder.decode(ItineraryResponseDTO.self, from: data)
                print("✅ Fast draft generated with \(itinerary.days.count) days")
                return itinerary
            } catch {
                print("❌ Decoding error: \(error)")
                if let jsonString = String(data: data, encoding: .utf8) {
                    print("📄 Response JSON (first 1000 chars): \(jsonString.prefix(1000))")
                }
                throw APIError.decodingError(error)
            }

        case 404:
            throw APIError.tripNotFound

        case 401:
            throw APIError.unauthorized

        case 402:
            throw APIError.paywallRequired

        default:
            let message = String(data: data, encoding: .utf8)
            print("❌ HTTP error: \(httpResponse.statusCode), message: \(message ?? "none")")
            throw APIError.httpError(statusCode: httpResponse.statusCode, message: message)
        }
    }

    /// Generate trip plan (macro + POI + route optimization) with String tripId
    /// POST /trips/{trip_id}/plan
    func planTrip(tripId: String) async throws -> ItineraryResponseDTO {
        print("🗺️ Planning trip: \(tripId)")

        // Build request with extended timeout (full plan can take 2-5 minutes)
        let fullPlanBuilder = RequestBuilder(timeout: AppConfig.fullPlanTimeout)
        let urlRequest = try fullPlanBuilder.buildRequest(
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
        case 200, 201:
            // Success - decode itinerary
            let decoder = JSONDecoder()
            // CodingKeys handle snake_case mapping
            do {
                let itinerary = try decoder.decode(ItineraryResponseDTO.self, from: data)
                print("✅ Plan generated with \(itinerary.days.count) days")
                return itinerary
            } catch {
                print("❌ Decoding error: \(error)")
                if let jsonString = String(data: data, encoding: .utf8) {
                    print("📄 Response JSON (first 1000 chars): \(jsonString.prefix(1000))")
                }
                throw APIError.decodingError(error)
            }

        case 404:
            throw APIError.tripNotFound

        case 401:
            throw APIError.unauthorized

        case 402:
            throw APIError.paywallRequired

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

        case 402:
            throw APIError.paywallRequired

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

        case 402:
            throw APIError.paywallRequired

        default:
            let message = String(data: data, encoding: .utf8)
            print("❌ HTTP error: \(httpResponse.statusCode), message: \(message ?? "none")")
            throw APIError.httpError(statusCode: httpResponse.statusCode, message: message)
        }
    }

    // MARK: - AI Studio Methods

    /// Get day studio data
    /// GET /trips/{trip_id}/day/{day_id}/studio
    func getDayStudio(tripId: UUID, dayId: Int) async throws -> DayStudioResponseDTO {
        print("🎨 Fetching day studio: trip=\(tripId), day=\(dayId)")

        let urlRequest = try requestBuilder.buildRequest(
            path: "trips/\(tripId.uuidString.lowercased())/day/\(dayId)/studio",
            method: .get
        )

        let (data, response) = try await session.data(for: urlRequest)

        guard let httpResponse = response as? HTTPURLResponse else {
            throw APIError.networkError(NSError(domain: "Invalid response", code: -1))
        }

        print("📡 Response status: \(httpResponse.statusCode)")

        switch httpResponse.statusCode {
        case 200:
            let decoder = JSONDecoder()
            do {
                let studioResponse = try decoder.decode(DayStudioResponseDTO.self, from: data)
                print("✅ Day studio fetched: \(studioResponse.day.places.count) places")
                return studioResponse
            } catch {
                print("❌ Decoding error: \(error)")
                if let jsonString = String(data: data, encoding: .utf8) {
                    print("📄 Response JSON: \(jsonString.prefix(500))")
                }
                throw APIError.decodingError(error)
            }

        case 404:
            // Parse detail message from FastAPI error response
            if let detailMessage = parseDetailMessage(from: data) {
                print("📄 404 detail: \(detailMessage)")
                throw APIError.serverError(message: detailMessage)
            }
            throw APIError.tripNotFound

        case 401:
            throw APIError.unauthorized

        case 402:
            throw APIError.paywallRequired

        default:
            let message = String(data: data, encoding: .utf8)
            print("❌ HTTP error: \(httpResponse.statusCode), message: \(message ?? "none")")
            throw APIError.httpError(statusCode: httpResponse.statusCode, message: message)
        }
    }

    /// Parse FastAPI's {"detail": "..."} error response
    private func parseDetailMessage(from data: Data) -> String? {
        struct DetailResponse: Decodable {
            let detail: String
        }
        return try? JSONDecoder().decode(DetailResponse.self, from: data).detail
    }

    /// Apply day changes
    /// POST /trips/{trip_id}/day/{day_id}/apply_changes
    func applyDayChanges(tripId: UUID, dayId: Int, request: ApplyChangesRequestDTO) async throws -> ApplyChangesResponseDTO {
        print("✨ Applying day changes: trip=\(tripId), day=\(dayId), changes=\(request.changes.count)")

        let encoder = JSONEncoder()
        encoder.keyEncodingStrategy = .convertToSnakeCase
        let bodyData = try encoder.encode(request)

        let urlRequest = try requestBuilder.buildRequest(
            path: "trips/\(tripId.uuidString.lowercased())/day/\(dayId)/apply_changes",
            method: .post,
            body: bodyData
        )

        let (data, response) = try await session.data(for: urlRequest)

        guard let httpResponse = response as? HTTPURLResponse else {
            throw APIError.networkError(NSError(domain: "Invalid response", code: -1))
        }

        print("📡 Response status: \(httpResponse.statusCode)")

        switch httpResponse.statusCode {
        case 200, 201:
            let decoder = JSONDecoder()
            do {
                let applyResponse = try decoder.decode(ApplyChangesResponseDTO.self, from: data)
                print("✅ Changes applied, new revision: \(applyResponse.revision)")
                return applyResponse
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

        case 409:
            // Conflict - revision mismatch
            throw APIError.httpError(statusCode: 409, message: "Revision conflict - please refresh and retry")

        default:
            let message = String(data: data, encoding: .utf8)
            print("❌ HTTP error: \(httpResponse.statusCode), message: \(message ?? "none")")
            throw APIError.httpError(statusCode: httpResponse.statusCode, message: message)
        }
    }

    /// Search for places
    /// POST /places/search
    func searchPlaces(request: PlaceSearchRequestDTO) async throws -> PlaceSearchResponseDTO {
        print("🔍 Searching places: query=\(request.query), city=\(request.city)")

        let encoder = JSONEncoder()
        encoder.keyEncodingStrategy = .convertToSnakeCase
        let bodyData = try encoder.encode(request)

        let urlRequest = try requestBuilder.buildRequest(
            path: "places/search",
            method: .post,
            body: bodyData
        )

        let (data, response) = try await session.data(for: urlRequest)

        guard let httpResponse = response as? HTTPURLResponse else {
            throw APIError.networkError(NSError(domain: "Invalid response", code: -1))
        }

        print("📡 Response status: \(httpResponse.statusCode)")

        switch httpResponse.statusCode {
        case 200:
            let decoder = JSONDecoder()
            do {
                let searchResponse = try decoder.decode(PlaceSearchResponseDTO.self, from: data)
                print("✅ Found \(searchResponse.results.count) places")
                return searchResponse
            } catch {
                print("❌ Decoding error: \(error)")
                if let jsonString = String(data: data, encoding: .utf8) {
                    print("📄 Response JSON: \(jsonString.prefix(500))")
                }
                throw APIError.decodingError(error)
            }

        default:
            let message = String(data: data, encoding: .utf8)
            print("❌ HTTP error: \(httpResponse.statusCode), message: \(message ?? "none")")
            throw APIError.httpError(statusCode: httpResponse.statusCode, message: message)
        }
    }
}
