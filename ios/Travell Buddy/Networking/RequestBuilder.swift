//
//  RequestBuilder.swift
//  Travell Buddy
//
//  Utility for building URLRequests with consistent configuration.
//

import Foundation

struct RequestBuilder {
    private let baseURL: URL
    private let timeout: TimeInterval

    init(
        baseURL: URL = AppConfig.baseURL,
        timeout: TimeInterval = AppConfig.requestTimeout
    ) {
        self.baseURL = baseURL
        self.timeout = timeout
    }

    /// Build a URLRequest for the given path and method
    func buildRequest(
        path: String,
        method: HTTPMethod,
        queryItems: [URLQueryItem]? = nil,
        body: Data? = nil
    ) throws -> URLRequest {
        // Construct full URL
        var urlComponents = URLComponents(url: baseURL, resolvingAgainstBaseURL: false)

        // Append path (remove leading slash if present to avoid double slashes)
        let cleanPath = path.hasPrefix("/") ? String(path.dropFirst()) : path
        urlComponents?.path += "/\(cleanPath)"

        // Add query items if provided
        if let queryItems = queryItems, !queryItems.isEmpty {
            urlComponents?.queryItems = queryItems
        }

        guard let url = urlComponents?.url else {
            throw APIError.invalidURL
        }

        print("🔗 Building request: \(method.rawValue) \(url.absoluteString)")

        // Create request
        var request = URLRequest(url: url)
        request.httpMethod = method.rawValue
        request.timeoutInterval = timeout
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.setValue("application/json", forHTTPHeaderField: "Accept")

        // Set body if provided
        if let body = body {
            request.httpBody = body
        }

        return request
    }
}
