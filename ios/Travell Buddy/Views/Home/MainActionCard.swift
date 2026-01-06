//
//  MainActionCard.swift
//  Travell Buddy
//
//  Main action card with gradient background.
//

import SwiftUI

struct MainActionCard: View {
    let title: String
    let subtitle: String
    let ctaText: String
    let leadingSystemImage: String
    let trailingSystemImage: String

    private let warmWhite = Color(red: 0.96, green: 0.95, blue: 0.93)
    private let mutedWarmGray = Color(red: 0.72, green: 0.69, blue: 0.64)

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            HStack {
                ZStack {
                    Circle()
                        .fill(Color.travelBuddyOrange.opacity(0.95))
                        .frame(width: 42, height: 42)

                    Image(systemName: leadingSystemImage)
                        .font(.system(size: 18, weight: .semibold))
                        .foregroundColor(.white)
                }

                Spacer()

                Circle()
                    .fill(Color.white.opacity(0.10))
                    .frame(width: 34, height: 34)
                    .overlay(
                        Image(systemName: trailingSystemImage)
                            .font(.system(size: 14, weight: .semibold))
                            .foregroundColor(warmWhite.opacity(0.9))
                    )
            }

            VStack(alignment: .leading, spacing: 6) {
                Text(title)
                    .font(.system(size: 20, weight: .semibold, design: .rounded))
                    .foregroundColor(warmWhite)
                    .fixedSize(horizontal: false, vertical: true)

                Text(subtitle)
                    .font(.system(size: 14, weight: .regular))
                    .foregroundColor(mutedWarmGray)
                    .fixedSize(horizontal: false, vertical: true)
            }

            HStack {
                Spacer()

                Text(ctaText)
                    .font(.system(size: 14, weight: .semibold, design: .rounded))
                    .foregroundColor(.white)
                    .padding(.horizontal, 18)
                    .padding(.vertical, 10)
                    .background(
                        Capsule()
                            .fill(Color.travelBuddyOrange)
                    )
            }
        }
        .padding(18)
        .frame(maxWidth: .infinity, minHeight: 150, alignment: .leading)
        .background(
            RoundedRectangle(cornerRadius: 24, style: .continuous)
                .fill(Color.white.opacity(0.08))
                .overlay(
                    RoundedRectangle(cornerRadius: 24, style: .continuous)
                        .stroke(Color.white.opacity(0.14), lineWidth: 1)
                )
                .shadow(color: Color(red: 0.05, green: 0.04, blue: 0.04).opacity(0.25), radius: 14, x: 0, y: 10)
        )
    }
}
