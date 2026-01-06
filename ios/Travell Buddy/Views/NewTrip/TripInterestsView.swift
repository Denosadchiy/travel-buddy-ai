//
//  TripInterestsView.swift
//  Travell Buddy
//
//  Premium dark interests selection screen.
//

import SwiftUI

private struct InterestCategory: Identifiable {
    let id = UUID()
    let title: String
    let icon: String
}

struct TripInterestsView: View {
    @State private var selectedInterests: Set<String> = []

    private let maxSelection = 3
    private let warmWhite = Color(red: 0.95, green: 0.94, blue: 0.92)
    private let mutedWarmGray = Color(red: 0.70, green: 0.67, blue: 0.63)
    private let backgroundTop = Color(red: 0.12, green: 0.11, blue: 0.11)
    private let backgroundBottom = Color(red: 0.08, green: 0.07, blue: 0.07)
    private let glassFill = Color.white.opacity(0.08)
    private let glassBorder = Color.white.opacity(0.14)

    private let categories: [InterestCategory] = [
        InterestCategory(title: "Гастро", icon: "fork.knife"),
        InterestCategory(title: "Музеи", icon: "building.columns"),
        InterestCategory(title: "Природа", icon: "leaf"),
        InterestCategory(title: "Ночная жизнь", icon: "sparkles"),
        InterestCategory(title: "Шопинг", icon: "bag"),
        InterestCategory(title: "Кофе", icon: "cup.and.saucer"),
        InterestCategory(title: "Виды", icon: "binoculars"),
        InterestCategory(title: "Релакс", icon: "heart"),
        InterestCategory(title: "Активности", icon: "figure.walk")
    ]

    private let columns = [
        GridItem(.flexible(), spacing: 14),
        GridItem(.flexible(), spacing: 14),
        GridItem(.flexible(), spacing: 14)
    ]

    var body: some View {
        ZStack {
            LinearGradient(
                colors: [backgroundTop, backgroundBottom],
                startPoint: .top,
                endPoint: .bottom
            )
            .ignoresSafeArea()

            NoiseLayer()
                .opacity(0.03)
                .ignoresSafeArea()

            ScrollView(showsIndicators: false) {
                VStack(alignment: .leading, spacing: 20) {
                    headerSection

                    LazyVGrid(columns: columns, spacing: 14) {
                        ForEach(categories) { category in
                            let isSelected = selectedInterests.contains(category.title)
                            let canSelect = isSelected || selectedInterests.count < maxSelection
                            InterestTile(
                                title: category.title,
                                icon: category.icon,
                                isSelected: isSelected,
                                isEnabled: canSelect,
                                warmWhite: warmWhite,
                                mutedWarmGray: mutedWarmGray,
                                glassFill: glassFill,
                                glassBorder: glassBorder
                            ) {
                                toggleSelection(for: category.title)
                            }
                        }
                    }
                }
                .padding(.horizontal, 20)
                .padding(.top, 20)
                .padding(.bottom, 24)
            }
        }
        .safeAreaInset(edge: .bottom) {
            bottomActions
        }
        .navigationBarHidden(true)
    }

    private var headerSection: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text("Выберите интересы")
                .font(.system(size: 30, weight: .bold, design: .rounded))
                .foregroundColor(warmWhite)

            HStack(alignment: .firstTextBaseline) {
                Text("Выберите до 3, чтобы маршрут был точнее")
                    .font(.system(size: 15, weight: .regular))
                    .foregroundColor(mutedWarmGray)

                Spacer()

                Text("\(selectedInterests.count)/\(maxSelection)")
                    .font(.system(size: 14, weight: .semibold, design: .rounded))
                    .foregroundColor(Color.travelBuddyOrange)
            }
        }
    }

    private var bottomActions: some View {
        VStack(spacing: 12) {
            Button(action: {}) {
                Text("Пропустить")
                    .font(.system(size: 14, weight: .semibold, design: .rounded))
                    .foregroundColor(mutedWarmGray)
                    .frame(maxWidth: .infinity)
            }
            .buttonStyle(.plain)

            Button(action: {}) {
                Text("Продолжить")
                    .font(.system(size: 17, weight: .semibold, design: .rounded))
                    .foregroundColor(.white)
                    .frame(maxWidth: .infinity)
                    .padding(.vertical, 16)
                    .background(Color.travelBuddyOrange)
                    .clipShape(Capsule())
                    .shadow(color: Color.travelBuddyOrange.opacity(0.35), radius: 12, x: 0, y: 6)
            }
            .buttonStyle(.plain)
        }
        .padding(.horizontal, 20)
        .padding(.top, 12)
        .padding(.bottom, 20)
        .background(
            LinearGradient(
                colors: [
                    backgroundBottom.opacity(0.2),
                    backgroundBottom.opacity(0.95)
                ],
                startPoint: .top,
                endPoint: .bottom
            )
            .ignoresSafeArea()
        )
    }

    private func toggleSelection(for title: String) {
        if selectedInterests.contains(title) {
            selectedInterests.remove(title)
            return
        }

        if selectedInterests.count < maxSelection {
            selectedInterests.insert(title)
        }
    }
}

private struct InterestTile: View {
    let title: String
    let icon: String
    let isSelected: Bool
    let isEnabled: Bool
    let warmWhite: Color
    let mutedWarmGray: Color
    let glassFill: Color
    let glassBorder: Color
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            VStack(spacing: 8) {
                Image(systemName: icon)
                    .font(.system(size: 20, weight: .semibold))
                    .foregroundColor(isSelected ? Color.travelBuddyOrange : mutedWarmGray.opacity(0.8))

                Text(title)
                    .font(.system(size: 12, weight: .semibold, design: .rounded))
                    .foregroundColor(isSelected ? warmWhite : mutedWarmGray)
                    .multilineTextAlignment(.center)
            }
            .frame(maxWidth: .infinity, minHeight: 88)
            .padding(.vertical, 12)
            .background(tileBackground)
            .overlay(tileBorder)
            .overlay(selectionHighlight)
            .overlay(alignment: .topTrailing) {
                if isSelected {
                    ZStack {
                        Circle()
                            .fill(Color.travelBuddyOrange)
                        Image(systemName: "checkmark")
                            .font(.system(size: 10, weight: .bold))
                            .foregroundColor(.white)
                    }
                    .frame(width: 20, height: 20)
                    .offset(x: 6, y: -6)
                }
            }
        }
        .buttonStyle(.plain)
        .disabled(!isEnabled)
        .opacity(isEnabled ? 1.0 : 0.45)
    }

    private var tileBackground: some View {
        RoundedRectangle(cornerRadius: 18, style: .continuous)
            .fill(glassFill)
    }

    private var tileBorder: some View {
        RoundedRectangle(cornerRadius: 18, style: .continuous)
            .stroke(glassBorder, lineWidth: 1)
    }

    private var selectionHighlight: some View {
        RoundedRectangle(cornerRadius: 18, style: .continuous)
            .fill(
                LinearGradient(
                    colors: [
                        Color.travelBuddyOrange.opacity(0.2),
                        Color.travelBuddyOrange.opacity(0.08)
                    ],
                    startPoint: .topLeading,
                    endPoint: .bottomTrailing
                )
            )
            .overlay(
                RoundedRectangle(cornerRadius: 18, style: .continuous)
                    .stroke(Color.travelBuddyOrange.opacity(0.9), lineWidth: 1)
            )
            .opacity(isSelected ? 1 : 0)
    }
}

private struct NoiseLayer: View {
    private let seed: UInt64 = 124_897

    var body: some View {
        Canvas { context, size in
            var generator = SeededGenerator(seed: seed)
            let count = Int((size.width * size.height) / 350)
            for _ in 0..<count {
                let x = CGFloat.random(in: 0...size.width, using: &generator)
                let y = CGFloat.random(in: 0...size.height, using: &generator)
                let rect = CGRect(x: x, y: y, width: 1, height: 1)
                context.fill(Path(rect), with: .color(Color.white.opacity(0.25)))
            }
        }
    }
}

private struct SeededGenerator: RandomNumberGenerator {
    private var state: UInt64

    init(seed: UInt64) {
        self.state = seed
    }

    mutating func next() -> UInt64 {
        state = state &* 6364136223846793005 &+ 1
        return state
    }
}
