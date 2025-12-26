//
//  ColorPalette.swift
//  Travell Buddy
//
//  Centralized color palette and gradients for the app.
//

import SwiftUI

// MARK: - Brand Colors

extension Color {
    /// Primary orange color - используется для акцентов
    static let travelBuddyOrange = Color(red: 1.0, green: 0.55, blue: 0.30)

    /// Secondary teal color - используется в градиентах
    static let travelBuddyTeal = Color(red: 0.05, green: 0.78, blue: 0.78)

    /// Light orange for gradients
    static let travelBuddyOrangeLight = Color(red: 1.0, green: 0.65, blue: 0.40)

    /// Dark orange for gradients
    static let travelBuddyOrangeDark = Color(red: 1.0, green: 0.45, blue: 0.35)

    /// Accent blue color
    static let travelBuddyBlue = Color(red: 0.2, green: 0.6, blue: 1.0)

    /// Purple gradient color
    static let travelBuddyPurple = Color(red: 0.86, green: 0.52, blue: 0.97)

    /// Peach color for avatars
    static let travelBuddyPeach = Color(red: 1.0, green: 0.69, blue: 0.55)
}

// MARK: - Gradients

extension LinearGradient {
    /// Основной градиент приложения (оранжевый)
    /// Используется в: Splash, кнопках, карточках
    static var travelBuddyPrimary: LinearGradient {
        LinearGradient(
            colors: [
                Color.travelBuddyOrangeLight,
                Color.travelBuddyOrangeDark
            ],
            startPoint: .topLeading,
            endPoint: .bottomTrailing
        )
    }

    /// Горизонтальный вариант основного градиента
    /// Используется в: кнопка "Сгенерировать маршрут"
    static var travelBuddyPrimaryHorizontal: LinearGradient {
        LinearGradient(
            colors: [
                Color.travelBuddyOrangeLight,
                Color.travelBuddyOrangeDark
            ],
            startPoint: .leading,
            endPoint: .trailing
        )
    }

    /// Градиент для Splash screen (оранжевый → бирюзовый)
    static var travelBuddySplash: LinearGradient {
        LinearGradient(
            colors: [
                Color(red: 1.0, green: 0.60, blue: 0.35),
                Color.travelBuddyTeal
            ],
            startPoint: .topLeading,
            endPoint: .bottomTrailing
        )
    }

    /// Градиент для аватара пользователя (персиковый → фиолетовый)
    static var travelBuddyAvatar: LinearGradient {
        LinearGradient(
            colors: [
                Color.travelBuddyPeach,
                Color.travelBuddyPurple
            ],
            startPoint: .topLeading,
            endPoint: .bottomTrailing
        )
    }

    /// Светлый градиент для фона экранов
    static var travelBuddyBackground: LinearGradient {
        LinearGradient(
            colors: [
                Color.white,
                Color(red: 0.98, green: 0.99, blue: 1.0)
            ],
            startPoint: .top,
            endPoint: .bottom
        )
    }

    /// Альтернативный светлый градиент (для HomeView)
    static var travelBuddyBackgroundAlt: LinearGradient {
        LinearGradient(
            colors: [
                Color.white,
                Color(red: 0.95, green: 0.98, blue: 1.0)
            ],
            startPoint: .top,
            endPoint: .bottom
        )
    }
}

// MARK: - Shadow Styles

extension View {
    /// Стандартная тень для карточек
    func cardShadow() -> some View {
        self.shadow(color: Color.black.opacity(0.08), radius: 10, x: 0, y: 6)
    }

    /// Лёгкая тень для элементов
    func lightShadow() -> some View {
        self.shadow(color: Color.black.opacity(0.05), radius: 8, x: 0, y: 4)
    }

    /// Тень для кнопок
    func buttonShadow() -> some View {
        self.shadow(color: Color.travelBuddyOrangeDark.opacity(0.3), radius: 12, x: 0, y: 6)
    }
}
