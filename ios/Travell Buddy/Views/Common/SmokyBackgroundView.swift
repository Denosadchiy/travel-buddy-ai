//
//  SmokyBackgroundView.swift
//  Travell Buddy
//
//  Premium smoky background with haze and grain.
//

import SwiftUI

struct SmokyBackgroundView: View {
    private let topColor = Color(red: 0.25, green: 0.18, blue: 0.16)   // #332E29
    private let midColor = Color(red: 0.2, green: 0.14, blue: 0.12)   // #26231F
    private let bottomColor = Color(red: 0.15, green: 0.09, blue: 0.08) // #191614

    var body: some View {
        ZStack {
            LinearGradient(
                colors: [topColor, midColor, bottomColor],
                startPoint: .top,
                endPoint: .bottom
            )

            RadialGradient(
                colors: [
                    Color.travelBuddyOrange.opacity(0.25),
                    Color.clear
                ],
                center: UnitPoint(x: 0.6, y: 0.05),
                startRadius: 20,
                endRadius: 320
            )
            .blendMode(.screen)

            RadialGradient(
                colors: [
                    Color.clear,
                    Color.black.opacity(0.45)
                ],
                center: .center,
                startRadius: 120,
                endRadius: 520
            )
            .opacity(0.5)

            Image("noise")
                .resizable(resizingMode: .tile)
                .opacity(0.025)
        }
        .ignoresSafeArea()
    }
}
