//
//  PresetButton.swift
//  Travell Buddy
//
//  Quick date range preset button.
//

import SwiftUI

struct PresetButton: View {
    let title: String
    let action: () -> Void
    private let warmWhite = Color(red: 0.95, green: 0.94, blue: 0.92)

    var body: some View {
        Button(action: action) {
            Text(title)
                .font(.system(size: 15, weight: .medium, design: .rounded))
                .foregroundColor(warmWhite)
                .padding(.horizontal, 16)
                .padding(.vertical, 10)
                .background(
                    Capsule()
                        .fill(Color.white.opacity(0.08))
                )
                .overlay(
                    Capsule()
                        .stroke(Color.white.opacity(0.14), lineWidth: 1)
                )
        }
        .buttonStyle(.plain)
    }
}
