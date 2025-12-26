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

    var body: some View {
        Button(action: action) {
            Text(title)
                .font(.system(size: 15, weight: .medium, design: .rounded))
                .foregroundColor(Color(red: 0.2, green: 0.6, blue: 1.0))
                .padding(.horizontal, 16)
                .padding(.vertical, 10)
                .background(
                    Capsule()
                        .fill(Color(red: 0.2, green: 0.6, blue: 1.0).opacity(0.1))
                )
        }
        .buttonStyle(.plain)
    }
}
