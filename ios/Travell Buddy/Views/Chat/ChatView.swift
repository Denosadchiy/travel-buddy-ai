//
//  ChatView.swift
//  Travell Buddy
//
//  Full-screen chat with AI assistant.
//

import SwiftUI

// MARK: - Chat Tab View

/// Обёртка для таба "Чат" с собственным состоянием сообщений
/// Note: This is a placeholder - real chat needs a trip ID
struct ChatTabView: View {
    @StateObject private var viewModel: ChatViewModel

    init() {
        // Placeholder: use a dummy UUID until we have a real trip
        // In production, this should be passed from the parent view
        _viewModel = StateObject(wrappedValue: ChatViewModel(
            tripId: UUID(),
            initialMessages: [ChatMessage.welcomeMessage]
        ))
    }

    var body: some View {
        ChatView(viewModel: viewModel)
    }
}

// MARK: - Full Chat View

/// Полноэкранный чат с AI‑агентом (открывается из чат-бара или таба "Чат").
struct ChatView: View {
    @StateObject var viewModel: ChatViewModel
    @State private var messageText: String = ""
    @FocusState private var isTextFieldFocused: Bool
    @Environment(\.dismiss) private var dismiss

    init(viewModel: ChatViewModel) {
        _viewModel = StateObject(wrappedValue: viewModel)
    }

    var body: some View {
        ZStack {
            // Фон
            LinearGradient(
                colors: [
                    Color.white,
                    Color(red: 0.98, green: 0.99, blue: 1.0)
                ],
                startPoint: .top,
                endPoint: .bottom
            )
            .ignoresSafeArea()

            VStack(spacing: 0) {
                // Заголовок чата
                chatHeaderView

                Divider()

                // Область сообщений
                ScrollViewReader { proxy in
                    ScrollView {
                        VStack(alignment: .leading, spacing: 16) {
                            ForEach(viewModel.messages) { message in
                                ChatBubbleView(message: message)
                                    .id(message.id)
                            }

                            // Show typing indicator when sending
                            if viewModel.isSending {
                                HStack(spacing: 8) {
                                    ProgressView()
                                        .scaleEffect(0.8)
                                    Text("Печатает...")
                                        .font(.system(size: 13))
                                        .foregroundColor(.secondary)
                                }
                                .padding(.horizontal, 16)
                                .padding(.vertical, 8)
                            }
                        }
                        .padding(.horizontal, 16)
                        .padding(.vertical, 16)
                    }
                    .onChange(of: viewModel.messages.count) { _ in
                        if let lastMessage = viewModel.messages.last {
                            withAnimation {
                                proxy.scrollTo(lastMessage.id, anchor: .bottom)
                            }
                        }
                    }
                }

                Divider()

                // Retry banner when send failed
                if viewModel.lastSendFailed {
                    retryBanner
                }

                // Поле ввода
                chatInputView
            }
        }
        .navigationBarHidden(true)
    }

    // MARK: Retry Banner

    private var retryBanner: some View {
        HStack(spacing: 8) {
            Image(systemName: "exclamationmark.triangle.fill")
                .font(.system(size: 14))
                .foregroundColor(.orange)

            Text("Сообщение не отправлено")
                .font(.system(size: 13, weight: .medium))
                .foregroundColor(Color(.label))

            Spacer()

            Button(action: { retrySend() }) {
                Text("Повторить")
                    .font(.system(size: 13, weight: .semibold))
                    .foregroundColor(.travelBuddyOrange)
            }
            .buttonStyle(.plain)
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 10)
        .background(Color(.systemGray6))
    }

    // MARK: Chat Header

    private var chatHeaderView: some View {
        HStack(spacing: 12) {
            // Кнопка назад
            Button(action: { dismiss() }) {
                Image(systemName: "chevron.left")
                    .font(.system(size: 17, weight: .semibold))
                    .foregroundColor(.travelBuddyOrange)
                    .frame(width: 32, height: 32)
            }
            .buttonStyle(.plain)

            // Иконка Travel Buddy
            ZStack {
                Circle()
                    .fill(LinearGradient.travelBuddyPrimary)
                    .frame(width: 36, height: 36)

                Image(systemName: "mappin.circle.fill")
                    .font(.system(size: 18, weight: .semibold))
                    .foregroundColor(.white)
            }

            // Название чата
            VStack(alignment: .leading, spacing: 2) {
                Text("Travel Buddy")
                    .font(.system(size: 16, weight: .semibold, design: .rounded))
                    .foregroundColor(Color(.label))

                HStack(spacing: 4) {
                    Circle()
                        .fill(Color.green)
                        .frame(width: 6, height: 6)

                    Text("Онлайн")
                        .font(.system(size: 12, weight: .medium))
                        .foregroundColor(Color(.secondaryLabel))
                }
            }

            Spacer()

            // Update plan button
            Button(action: { updatePlan() }) {
                if viewModel.isUpdatingPlan {
                    ProgressView()
                        .scaleEffect(0.8)
                        .frame(width: 32, height: 32)
                } else {
                    Image(systemName: "arrow.triangle.2.circlepath")
                        .font(.system(size: 17, weight: .semibold))
                        .foregroundColor(.travelBuddyOrange)
                        .frame(width: 32, height: 32)
                }
            }
            .buttonStyle(.plain)
            .disabled(viewModel.isUpdatingPlan || viewModel.isSending)
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 12)
        .background(
            Color(.systemBackground)
                .shadow(color: Color.black.opacity(0.05), radius: 8, x: 0, y: 2)
        )
    }

    // MARK: Chat Input

    private var chatInputView: some View {
        HStack(spacing: 10) {
            TextField("Напиши свои пожелания к маршруту", text: $messageText, axis: .vertical)
                .font(.system(size: 15))
                .padding(.horizontal, 14)
                .padding(.vertical, 10)
                .background(
                    RoundedRectangle(cornerRadius: 20, style: .continuous)
                        .fill(Color(.systemGray6))
                )
                .focused($isTextFieldFocused)
                .lineLimit(1...3)

            // Микрофон
            Button(action: {
                // Placeholder для голосового ввода
            }) {
                Image(systemName: "mic.fill")
                    .font(.system(size: 16, weight: .medium))
                    .foregroundColor(Color(.secondaryLabel))
                    .frame(width: 36, height: 36)
            }
            .buttonStyle(.plain)

            // Кнопка отправки
            Button {
                sendMessage()
            } label: {
                if viewModel.isSending {
                    ProgressView()
                        .progressViewStyle(CircularProgressViewStyle(tint: .white))
                        .scaleEffect(0.8)
                        .frame(width: 36, height: 36)
                        .background(
                            Circle()
                                .fill(Color(red: 1.0, green: 0.55, blue: 0.30))
                        )
                } else {
                    Image(systemName: "paperplane.fill")
                        .font(.system(size: 16, weight: .semibold))
                        .foregroundColor(.white)
                        .frame(width: 36, height: 36)
                        .background(
                            Circle()
                                .fill(Color(red: 1.0, green: 0.55, blue: 0.30))
                        )
                }
            }
            .buttonStyle(.plain)
            .disabled(messageText.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty || viewModel.isSending)
        }
        .padding(.horizontal, 12)
        .padding(.vertical, 12)
        .background(Color(.systemBackground))
    }

    // MARK: Send Message

    private func sendMessage() {
        let trimmedText = messageText.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmedText.isEmpty else { return }

        // Clear input field immediately
        let textToSend = trimmedText
        messageText = ""
        isTextFieldFocused = false

        // Send message via ViewModel (async)
        Task {
            await viewModel.sendMessage(textToSend)
        }
    }

    // MARK: Update Plan

    private func updatePlan() {
        Task {
            await viewModel.requestPlanUpdate()
        }
    }

    // MARK: Retry Send

    private func retrySend() {
        Task {
            await viewModel.retrySendMessage()
        }
    }
}

