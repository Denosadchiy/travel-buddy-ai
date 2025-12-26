//
//  APIError.swift
//  Travell Buddy
//
//  API error types with localized descriptions.
//

import Foundation

enum APIError: Error, LocalizedError {
    case invalidURL
    case networkError(Error)
    case httpError(statusCode: Int, message: String?)
    case decodingError(Error)
    case serverError(message: String)
    case tripNotFound
    case unauthorized

    var errorDescription: String? {
        switch self {
        case .invalidURL:
            return "Неверный URL запроса"
        case .networkError(let error):
            return "Проблема с подключением к интернету: \(error.localizedDescription)"
        case .httpError(let code, let message):
            if let message = message {
                return message
            }
            return "Ошибка сервера (\(code))"
        case .decodingError(let error):
            return "Ошибка обработки данных: \(error.localizedDescription)"
        case .serverError(let message):
            return "Ошибка сервера: \(message)"
        case .tripNotFound:
            return "Поездка не найдена"
        case .unauthorized:
            return "Необходима авторизация"
        }
    }
}
