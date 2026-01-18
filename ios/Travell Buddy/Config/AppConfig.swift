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
            // FastAPI dev server running locally in Docker
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

    /// Request timeout for fast draft (90s - LLM + POI fetching can take 40-60s)
    static let fastDraftTimeout: TimeInterval = 90

    /// Request timeout for full plan generation (5 min for background enrichment)
    static let fullPlanTimeout: TimeInterval = 300

    /// Default request timeout
    static let requestTimeout: TimeInterval = 30

    /// Google Sign-In client ID
    static let googleClientId: String = "940504529190-ihngs4riauq6g90nmhj3v684fpbj4713.apps.googleusercontent.com"
}
