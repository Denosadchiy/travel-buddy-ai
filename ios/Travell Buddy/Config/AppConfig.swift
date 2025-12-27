//
//  AppConfig.swift
//  Travell Buddy
//
//  Application configuration and environment management.
//

import Foundation

enum APIEnvironment {
    case development
    case staging
    case production

    var baseURL: URL {
        switch self {
        case .development:
            // FastAPI dev server running locally
            return URL(string: "http://localhost:8000/api")!
        case .staging:
            return URL(string: "https://staging-api.travelbuddy.com/api")!
        case .production:
            return URL(string: "https://api.travelbuddy.com/api")!
        }
    }
}

struct AppConfig {
    /// Current environment (hardcoded to development for now)
    static let environment: APIEnvironment = .development

    /// Base URL for API requests
    static var baseURL: URL { environment.baseURL }

    /// Request timeout in seconds
    static let requestTimeout: TimeInterval = 30
}
