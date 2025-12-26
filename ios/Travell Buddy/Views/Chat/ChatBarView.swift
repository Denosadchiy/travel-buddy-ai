//
//  ChatBarView.swift
//  Travell Buddy
//
//  Compact chat bar preview for home screen.
//

import SwiftUI

/// Компактный чат-бар для главного экрана (открывается при нажатии)
struct ChatBarView: View {
    let messages: [ChatMessage]

    var lastMessage: ChatMessage? {
        messages.last
    }

    var body: some View {
        HStack(spacing: 12) {
            // Иконка Travel Buddy
            ZStack {
                Circle()
                    .fill(
                        LinearGradient(
                            colors: [
                                Color(red: 1.0, green: 0.65, blue: 0.40),
                                Color(red: 1.0, green: 0.45, blue: 0.35)
                            ],
                            startPoint: .topLeading,
                            endPoint: .bottomTrailing
                        )
                    )
                    .frame(width: 44, height: 44)

                Image(systemName: "mappin.circle.fill")
                    .font(.system(size: 20, weight: .semibold))
                    .foregroundColor(.white)
            }

            // Информация о чате
            VStack(alignment: .leading, spacing: 4) {
                HStack(spacing: 6) {
                    Text("Чат с Travel Buddy")
                        .font(.system(size: 16, weight: .semibold, design: .rounded))
                        .foregroundColor(Color(.label))

                    // Статус "Онлайн"
                    Circle()
                        .fill(Color.green)
                        .frame(width: 6, height: 6)
                }

                // Последнее сообщение или плейсхолдер
                if let lastMessage = lastMessage {
                    Text(lastMessage.text)
                        .font(.system(size: 14))
                        .foregroundColor(Color(.secondaryLabel))
                        .lineLimit(1)
                } else {
                    Text("Начни диалог с AI‑агентом")
                        .font(.system(size: 14))
                        .foregroundColor(Color(.secondaryLabel))
                        .italic()
                }
            }

            Spacer()

            // Стрелка вправо
            Image(systemName: "chevron.right")
                .font(.system(size: 14, weight: .semibold))
                .foregroundColor(Color(.tertiaryLabel))
        }
        .padding(14)
        .background(
            RoundedRectangle(cornerRadius: 20, style: .continuous)
                .fill(Color.white)
        )
        .shadow(color: Color.black.opacity(0.06), radius: 8, x: 0, y: 4)
    }
}
