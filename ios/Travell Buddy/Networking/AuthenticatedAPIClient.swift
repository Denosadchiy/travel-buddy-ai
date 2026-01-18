//
//  AuthenticatedAPIClient.swift
//  Travell Buddy
//
//  API client wrapper with automatic token refresh on 401.
//  Prevents infinite refresh loops and handles concurrent refresh requests.
//

import Foundation

actor AuthenticatedAPIClient {
    static let shared = AuthenticatedAPIClient()

    private let session: URLSession
    private let requestBuilder: RequestBuilder
    private let authClient: AuthAPIClient

    // Prevent concurrent refresh attempts
    private var isRefreshing = false
    private var refreshContinuations: [CheckedContinuation<Bool, Never>] = []

    private init() {
        self.session = .shared
        self.requestBuilder = RequestBuilder()
        self.authClient = AuthAPIClient()
    }

    // MARK: - Public API

    /// Execute a request with automatic 401 handling and token refresh
    func execute<T: Decodable>(
        path: String,
        method: HTTPMethod,
        queryItems: [URLQueryItem]? = nil,
        body: Data? = nil,
        timeout: TimeInterval? = nil
    ) async throws -> T {
        // Build and execute initial request
        let result = try await executeOnce(
            path: path,
            method: method,
            queryItems: queryItems,
            body: body,
            timeout: timeout
        )

        switch result {
        case .success(let data):
            return try decodeResponse(data)

        case .unauthorized:
            // Try to refresh token once
            let refreshSuccess = await refreshTokenIfNeeded()

            if refreshSuccess {
                // Retry request with new token
                let retryResult = try await executeOnce(
                    path: path,
                    method: method,
                    queryItems: queryItems,
                    body: body,
                    timeout: timeout
                )

                switch retryResult {
                case .success(let data):
                    return try decodeResponse(data)
                case .unauthorized:
                    // Still unauthorized after refresh - logout
                    await performLogout()
                    throw APIError.unauthorized
                case .error(let error):
                    throw error
                }
            } else {
                // Refresh failed - already logged out
                throw APIError.unauthorized
            }

        case .error(let error):
            throw error
        }
    }

    /// Execute a request without response body (e.g., DELETE)
    func executeVoid(
        path: String,
        method: HTTPMethod,
        queryItems: [URLQueryItem]? = nil,
        body: Data? = nil,
        timeout: TimeInterval? = nil
    ) async throws {
        let result = try await executeOnce(
            path: path,
            method: method,
            queryItems: queryItems,
            body: body,
            timeout: timeout
        )

        switch result {
        case .success:
            return

        case .unauthorized:
            let refreshSuccess = await refreshTokenIfNeeded()

            if refreshSuccess {
                let retryResult = try await executeOnce(
                    path: path,
                    method: method,
                    queryItems: queryItems,
                    body: body,
                    timeout: timeout
                )

                switch retryResult {
                case .success:
                    return
                case .unauthorized:
                    await performLogout()
                    throw APIError.unauthorized
                case .error(let error):
                    throw error
                }
            } else {
                throw APIError.unauthorized
            }

        case .error(let error):
            throw error
        }
    }

    // MARK: - Private Helpers

    private enum RequestResult {
        case success(Data)
        case unauthorized
        case error(APIError)
    }

    private func executeOnce(
        path: String,
        method: HTTPMethod,
        queryItems: [URLQueryItem]?,
        body: Data?,
        timeout: TimeInterval?
    ) async throws -> RequestResult {
        let builder = timeout.map { RequestBuilder(timeout: $0) } ?? requestBuilder

        let urlRequest = try builder.buildRequest(
            path: path,
            method: method,
            queryItems: queryItems,
            body: body
        )

        do {
            let (data, response) = try await session.data(for: urlRequest)

            guard let httpResponse = response as? HTTPURLResponse else {
                return .error(.networkError(NSError(domain: "Invalid response", code: -1)))
            }

            switch httpResponse.statusCode {
            case 200..<300:
                return .success(data)

            case 401:
                return .unauthorized

            case 402:
                if let body = String(data: data, encoding: .utf8), !body.isEmpty {
                    print("[API] 402 response body: \(body)")
                }
                return .error(.paywallRequired)

            default:
                let message = String(data: data, encoding: .utf8)
                if let message, !message.isEmpty {
                    print("[API] \(httpResponse.statusCode) response body: \(message)")
                }
                return .error(.httpError(statusCode: httpResponse.statusCode, message: message))
            }
        } catch let error as URLError {
            if error.code == .timedOut {
                return .error(.timeout)
            }
            return .error(.networkError(error))
        } catch {
            return .error(.networkError(error))
        }
    }

    private func decodeResponse<T: Decodable>(_ data: Data) throws -> T {
        do {
            let decoder = JSONDecoder()
            return try decoder.decode(T.self, from: data)
        } catch {
            throw APIError.decodingError(error)
        }
    }

    // MARK: - Token Refresh

    /// Refresh token with deduplication. Returns true if refresh succeeded.
    private func refreshTokenIfNeeded() async -> Bool {
        // If already refreshing, wait for the result
        if isRefreshing {
            return await withCheckedContinuation { continuation in
                refreshContinuations.append(continuation)
            }
        }

        // Start refresh
        isRefreshing = true

        let success = await performRefresh()

        // Notify all waiting continuations
        let continuations = refreshContinuations
        refreshContinuations = []
        isRefreshing = false

        for continuation in continuations {
            continuation.resume(returning: success)
        }

        return success
    }

    private func performRefresh() async -> Bool {
        guard let refreshToken = AuthSessionStore.shared.refreshToken else {
            await performLogout()
            return false
        }

        do {
            let session = try await authClient.refreshSession(refreshToken: refreshToken)
            AuthSessionStore.shared.accessToken = session.accessToken
            AuthSessionStore.shared.refreshToken = session.refreshToken
            print("[Auth] Token refreshed successfully")
            return true
        } catch {
            print("[Auth] Token refresh failed: \(error)")
            await performLogout()
            return false
        }
    }

    @MainActor
    private func performLogout() {
        AuthManager.shared.logout()
    }
}
