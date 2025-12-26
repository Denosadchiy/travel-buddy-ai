//
//  ChatViewModel.swift
//  Travell Buddy
//
//  ViewModel for managing chat state and backend communication.
//

import Foundation

final class ChatViewModel: ObservableObject {
    @Published var messages: [ChatMessage]
    @Published var isSending: Bool = false
    @Published var errorMessage: String?

    private let tripId: UUID
    private let apiClient: TripPlanningAPIClient

    init(
        tripId: UUID,
        initialMessages: [ChatMessage] = [],
        apiClient: TripPlanningAPIClient = .shared
    ) {
        self.tripId = tripId
        self.apiClient = apiClient
        self.messages = initialMessages

        // Add default welcome message if no initial messages
        if initialMessages.isEmpty {
            self.messages = [
                ChatMessage(
                    id: UUID(),
                    text: "Расскажи мне о своих пожеланиях: любишь ли ты много ходить, хочешь больше музеев или баров, есть ли ограничения?",
                    isFromUser: false,
                    timestamp: Date()
                )
            ]
        }
    }

    // MARK: - Public Methods

    /// Send a chat message to the backend
    @MainActor
    func sendMessage(_ text: String) async {
        // Validate input
        let trimmedText = text.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmedText.isEmpty else { return }

        // Add user message to chat
        let userMessage = ChatMessage(
            id: UUID(),
            text: trimmedText,
            isFromUser: true,
            timestamp: Date()
        )
        messages.append(userMessage)

        // Set loading state
        isSending = true
        errorMessage = nil

        print("💬 Sending message to backend for trip: \(tripId)")

        do {
            // Call backend API
            let response = try await apiClient.sendChatMessage(
                tripId: tripId,
                message: trimmedText
            )

            // Add assistant message to chat
            let assistantMessage = ChatMessage(
                id: UUID(),
                text: response.assistantMessage,
                isFromUser: false,
                timestamp: Date()
            )
            messages.append(assistantMessage)

            print("✅ Chat response received: \(response.assistantMessage.prefix(50))...")

            // Optionally: store updated trip data from response
            // response.trip contains the updated trip preferences
            // You could emit this to another observer if needed

        } catch {
            // Handle error
            let errorDescription = (error as? LocalizedError)?.errorDescription ?? error.localizedDescription
            self.errorMessage = errorDescription
            print("❌ Chat error: \(errorDescription)")

            // Optionally: add an error message to chat
            let errorChatMessage = ChatMessage(
                id: UUID(),
                text: "❌ Произошла ошибка: \(errorDescription)",
                isFromUser: false,
                timestamp: Date()
            )
            messages.append(errorChatMessage)
        }

        isSending = false
    }
}
