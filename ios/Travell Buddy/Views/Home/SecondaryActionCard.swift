//
//  SecondaryActionCard.swift
//  Travell Buddy
//
//  Secondary glass action cards for Home screen.
//

import SwiftUI

struct SecondaryActionCard: View {
    let title: String
    let systemImageName: String
    let trailingSystemImage: String

    private let warmWhite = Color(red: 0.96, green: 0.95, blue: 0.93)
    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack {
                ZStack {
                    Circle()
                        .fill(Color.white.opacity(0.12))
                        .frame(width: 36, height: 36)

                    Image(systemName: systemImageName)
                        .font(.system(size: 14, weight: .semibold))
                        .foregroundColor(Color.travelBuddyOrange)
                }

                Spacer()

                Image(systemName: trailingSystemImage)
                    .font(.system(size: 14, weight: .semibold))
                    .foregroundColor(warmWhite.opacity(0.7))
            }

            Spacer(minLength: 8)

            Text(title)
                .font(.system(size: 16, weight: .semibold, design: .rounded))
                .foregroundColor(warmWhite)
                .fixedSize(horizontal: false, vertical: true)
        }
        .padding(16)
        .frame(maxWidth: .infinity, minHeight: 120, alignment: .leading)
        .background(
            RoundedRectangle(cornerRadius: 24, style: .continuous)
                .fill(Color.white.opacity(0.08))
                .overlay(
                    RoundedRectangle(cornerRadius: 24, style: .continuous)
                        .stroke(Color.white.opacity(0.14), lineWidth: 1)
                )
                .shadow(color: Color(red: 0.05, green: 0.04, blue: 0.04).opacity(0.22), radius: 12, x: 0, y: 8)
        )
    }
}
