//
//  ChatMessage.swift
//  Travell Buddy
//
//  Data model for chat messages between user and AI assistant.
//

import Foundation

struct ChatMessage: Identifiable {
    let id: UUID
    let text: String
    let isFromUser: Bool
    let timestamp: Date
}

// MARK: - Default Messages

extension ChatMessage {
    /// Дефолтные демо-сообщения для чата (используются в HomeView и ChatTabView)
    static var defaultMessages: [ChatMessage] {
        [
            ChatMessage(
                id: UUID(),
                text: "Расскажи мне о своих пожеланиях: любишь ли ты много ходить, хочешь больше музеев или баров, есть ли ограничения?",
                isFromUser: false,
                timestamp: Date()
            ),
            ChatMessage(
                id: UUID(),
                text: "Не люблю музеи, хочу больше прогулок по городу и крыши с видом.",
                isFromUser: true,
                timestamp: Date()
            )
        ]
    }
}
