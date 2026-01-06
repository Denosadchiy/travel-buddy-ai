//
//  HomeHeaderView.swift
//  Travell Buddy
//
//  Header for home screen.
//

import SwiftUI

struct HomeHeaderView: View {
    let greeting: String
    let name: String
    let onAccountTap: () -> Void

    private let warmWhite = Color(red: 0.96, green: 0.95, blue: 0.93)
    private let mutedWarmGray = Color(red: 0.72, green: 0.69, blue: 0.65)
    private let avatarBackground = LinearGradient(
        colors: [
            Color(red: 0.98, green: 0.74, blue: 0.58),
            Color(red: 0.85, green: 0.56, blue: 0.45)
        ],
        startPoint: .topLeading,
        endPoint: .bottomTrailing
    )

    var body: some View {
        HStack(alignment: .top) {
            VStack(alignment: .leading, spacing: 6) {
                HStack(spacing: 6) {
                    Image(systemName: "sun.max.fill")
                        .font(.system(size: 12, weight: .semibold))
                        .foregroundColor(mutedWarmGray)

                    Text(greeting)
                        .font(.system(size: 13, weight: .medium, design: .rounded))
                        .foregroundColor(mutedWarmGray)
                }

                Text(name)
                    .font(.system(size: 18, weight: .semibold, design: .rounded))
                    .foregroundColor(warmWhite)
            }

            Spacer()

            Button(action: onAccountTap) {
                ZStack {
                    Circle()
                        .fill(avatarBackground)
                        .frame(width: 42, height: 42)

                    Image(systemName: AuthSessionStore.shared.accessToken == nil ? "person.fill" : "person.crop.circle.fill")
                        .font(.system(size: 16, weight: .semibold))
                        .foregroundColor(.white)
                }
                .overlay(alignment: .topTrailing) {
                    Circle()
                        .fill(Color.travelBuddyOrange)
                        .frame(width: 10, height: 10)
                        .overlay(
                            Circle()
                                .stroke(Color(red: 0.20, green: 0.19, blue: 0.18), lineWidth: 2)
                        )
                        .offset(x: 2, y: -2)
                }
            }
            .buttonStyle(.plain)
        }
    }
}
