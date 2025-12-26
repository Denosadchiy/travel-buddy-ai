//
//  DesignSystem.swift
//  Travell Buddy
//
//  Centralized design constants for spacing, sizing, fonts, and radii.
//

import SwiftUI

// MARK: - Design System

enum DesignSystem {

    // MARK: - Spacing

    enum Spacing {
        static let xxsmall: CGFloat = 4
        static let xsmall: CGFloat = 8
        static let small: CGFloat = 12
        static let medium: CGFloat = 16
        static let large: CGFloat = 24
        static let xlarge: CGFloat = 32
        static let xxlarge: CGFloat = 44
        static let xxxlarge: CGFloat = 64
    }

    // MARK: - Corner Radius

    enum CornerRadius {
        static let small: CGFloat = 12
        static let medium: CGFloat = 18
        static let large: CGFloat = 24
        static let xlarge: CGFloat = 30
        static let capsule: CGFloat = 999
    }

    // MARK: - Font Size

    enum FontSize {
        static let caption: CGFloat = 13
        static let footnote: CGFloat = 14
        static let body: CGFloat = 15
        static let callout: CGFloat = 16
        static let title3: CGFloat = 17
        static let title2: CGFloat = 20
        static let title: CGFloat = 28
        static let largeTitle: CGFloat = 30
        static let hero: CGFloat = 40
    }

    // MARK: - Icon Size

    enum IconSize {
        static let small: CGFloat = 18
        static let medium: CGFloat = 24
        static let large: CGFloat = 30
        static let xlarge: CGFloat = 50
    }

    // MARK: - Avatar Size

    enum AvatarSize {
        static let small: CGFloat = 36
        static let medium: CGFloat = 56
        static let large: CGFloat = 120
    }

    // MARK: - Shadow

    enum Shadow {
        static let lightRadius: CGFloat = 8
        static let lightY: CGFloat = 4
        static let lightOpacity: Double = 0.05

        static let cardRadius: CGFloat = 10
        static let cardY: CGFloat = 6
        static let cardOpacity: Double = 0.08

        static let buttonRadius: CGFloat = 12
        static let buttonY: CGFloat = 6
        static let buttonOpacity: Double = 0.3

        static let splashRadius: CGFloat = 18
        static let splashY: CGFloat = 12
        static let splashOpacity: Double = 0.18
    }
}

// MARK: - Popular Cities

enum PopularCities {
    static let all = [
        "Париж", "Токио", "Нью-Йорк", "Рим",
        "Лондон", "Барселона", "Стамбул", "Дубай"
    ]
}

// MARK: - Animation Durations

enum AnimationDuration {
    static let fast: Double = 0.2
    static let normal: Double = 0.3
    static let slow: Double = 0.5
    static let splash: Double = 2.5
}
