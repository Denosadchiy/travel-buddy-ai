//
//  APIError.swift
//  Travell Buddy
//
//  API error types with localized descriptions.
//  All user-facing messages are in Russian for consistency.
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
    case timeout

    /// User-friendly error message in Russian.
    /// This is the only place where error messages are defined for API errors.
    var errorDescription: String? {
        switch self {
        case .invalidURL:
            return "Что-то пошло не так. Попробуйте ещё раз."

        case .networkError(let error):
            // Check for specific network errors
            let nsError = error as NSError
            if nsError.domain == NSURLErrorDomain {
                switch nsError.code {
                case NSURLErrorNotConnectedToInternet, NSURLErrorNetworkConnectionLost:
                    return "Нет подключения к интернету. Проверьте соединение."
                case NSURLErrorTimedOut:
                    return "Превышено время ожидания. Попробуйте ещё раз."
                case NSURLErrorCannotFindHost, NSURLErrorCannotConnectToHost:
                    return "Сервер недоступен. Попробуйте позже."
                default:
                    return "Проблема с подключением. Проверьте интернет."
                }
            }
            return "Проблема с подключением. Проверьте интернет."

        case .httpError(let code, _):
            // Map HTTP status codes to user-friendly messages
            switch code {
            case 400..<500:
                return "Ошибка запроса. Попробуйте изменить параметры."
            case 500..<600:
                return "На сервере произошла ошибка. Попробуйте позже."
            default:
                return "Что-то пошло не так. Попробуйте ещё раз."
            }

        case .decodingError:
            return "Ошибка обработки данных. Попробуйте ещё раз."

        case .serverError:
            return "На сервере произошла ошибка. Попробуйте позже."

        case .tripNotFound:
            return "Поездка не найдена. Создайте новую поездку."

        case .unauthorized:
            return "Необходима авторизация."

        case .timeout:
            return "Превышено время ожидания. Попробуйте ещё раз."
        }
    }

    /// Short title for error alerts
    var alertTitle: String {
        switch self {
        case .networkError, .timeout:
            return "Ошибка соединения"
        case .httpError(let code, _) where code >= 500:
            return "Ошибка сервера"
        case .tripNotFound:
            return "Поездка не найдена"
        case .unauthorized:
            return "Требуется авторизация"
        default:
            return "Ошибка"
        }
    }

    /// Whether this error is retryable
    var isRetryable: Bool {
        switch self {
        case .networkError, .timeout:
            return true
        case .httpError(let code, _) where code >= 500:
            return true
        case .decodingError, .serverError:
            return true
        default:
            return false
        }
    }
}
