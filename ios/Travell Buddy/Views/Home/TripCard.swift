//
//  TripCard.swift
//  Travell Buddy
//
//  Card for past/upcoming trip.
//

import SwiftUI

struct TripCard: View {
    let city: String
    let country: String
    let dateText: String
    let gradient: LinearGradient
    let symbolName: String
    let photoURL: URL?

    private let warmWhite = Color(red: 0.96, green: 0.95, blue: 0.93)
    private let mutedWarmGray = Color(red: 0.72, green: 0.69, blue: 0.64)
    private let cardShape = RoundedRectangle(cornerRadius: 24, style: .continuous)

    var body: some View {
        ZStack(alignment: .topLeading) {
            backgroundLayer

            LinearGradient(
                colors: [
                    Color.clear,
                    Color(red: 0.08, green: 0.07, blue: 0.06).opacity(0.45)
                ],
                startPoint: .center,
                endPoint: .bottom
            )

            Text(dateText)
                .font(.system(size: 12, weight: .semibold, design: .rounded))
                .foregroundColor(warmWhite)
                .padding(.horizontal, 10)
                .padding(.vertical, 6)
                .background(
                    Capsule()
                        .fill(Color.white.opacity(0.16))
                )
                .overlay(
                    Capsule()
                        .stroke(Color.white.opacity(0.2), lineWidth: 1)
                )
                .padding(12)

            VStack(alignment: .leading, spacing: 6) {
                Text(city)
                    .font(.system(size: 18, weight: .semibold, design: .rounded))
                    .foregroundColor(warmWhite)

                HStack(spacing: 6) {
                    Image(systemName: "mappin")
                        .font(.system(size: 12, weight: .semibold))
                        .foregroundColor(mutedWarmGray)

                    Text(country)
                        .font(.system(size: 12, weight: .medium))
                        .foregroundColor(mutedWarmGray)
                }
            }
            .padding(16)
            .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .bottomLeading)
        }
        .frame(width: 210, height: 250)
        .clipShape(cardShape)
        .shadow(color: Color(red: 0.05, green: 0.04, blue: 0.04).opacity(0.35), radius: 16, x: 0, y: 10)
    }

    private var backgroundLayer: some View {
        ZStack {
            Rectangle()
                .fill(gradient)

            if let photoURL {
                RemoteImageView(url: photoURL)
            }

            if photoURL == nil {
                Image(systemName: symbolName)
                    .resizable()
                    .scaledToFit()
                    .frame(width: 120)
                    .foregroundColor(Color.white.opacity(0.18))
                    .offset(x: 70, y: 40)
            }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .clipped()
    }
}
