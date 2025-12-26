//
//  ChatBubbleView.swift
//  Travell Buddy
//
//  Single chat message bubble (user or AI).
//

import SwiftUI

struct ChatBubbleView: View {
    let message: ChatMessage

    var body: some View {
        if message.isFromUser {
            // Сообщение пользователя (справа)
            HStack(alignment: .top, spacing: 8) {
                Spacer()

                Text(message.text)
                    .font(.system(size: 15))
                    .foregroundColor(.white)
                    .padding(.horizontal, 14)
                    .padding(.vertical, 10)
                    .background(
                        RoundedRectangle(cornerRadius: 18, style: .continuous)
                            .fill(Color(red: 1.0, green: 0.55, blue: 0.30))
                    )

                // Аватар пользователя
                ZStack {
                    Circle()
                        .fill(
                            LinearGradient(
                                colors: [
                                    Color(red: 1.0, green: 0.69, blue: 0.55),
                                    Color(red: 0.86, green: 0.52, blue: 0.97)
                                ],
                                startPoint: .topLeading,
                                endPoint: .bottomTrailing
                            )
                        )
                        .frame(width: 32, height: 32)

                    Text("AH")
                        .font(.system(size: 12, weight: .semibold, design: .rounded))
                        .foregroundColor(.white)
                }
            }
        } else {
            // Сообщение AI (слева)
            HStack(alignment: .top, spacing: 8) {
                // Иконка AI
                ZStack {
                    RoundedRectangle(cornerRadius: 8, style: .continuous)
                        .fill(Color(.systemGray5))
                        .frame(width: 32, height: 32)

                    Image(systemName: "sparkles")
                        .font(.system(size: 16, weight: .medium))
                        .foregroundColor(Color(.secondaryLabel))
                }

                Text(message.text)
                    .font(.system(size: 15))
                    .foregroundColor(Color(.label))
                    .padding(.horizontal, 14)
                    .padding(.vertical, 10)
                    .background(
                        RoundedRectangle(cornerRadius: 18, style: .continuous)
                            .fill(Color(.systemGray6))
                    )

                Spacer()
            }
        }
    }
}
