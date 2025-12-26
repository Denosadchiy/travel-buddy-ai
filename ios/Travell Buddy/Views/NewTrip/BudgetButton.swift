//
//  BudgetButton.swift
//  Travell Buddy
//
//  Button for selecting budget level.
//

import SwiftUI

struct BudgetButton: View {
    let title: String
    let icon: String
    let isSelected: Bool
    let action: () -> Void
    
    var body: some View {
        Button(action: action) {
            VStack(spacing: 8) {
                Image(systemName: icon)
                    .font(.system(size: 20, weight: .semibold))
                    .foregroundColor(isSelected ? Color(red: 0.2, green: 0.6, blue: 1.0) : Color(.secondaryLabel))
                
                Text(title)
                    .font(.system(size: 13, weight: .medium, design: .rounded))
                    .foregroundColor(isSelected ? Color(red: 0.2, green: 0.6, blue: 1.0) : Color(.label))
            }
            .frame(maxWidth: .infinity)
            .padding(.vertical, 14)
            .background(
                RoundedRectangle(cornerRadius: 16, style: .continuous)
                    .fill(isSelected ? Color(red: 0.2, green: 0.6, blue: 1.0).opacity(0.1) : Color.white)
            )
            .overlay(
                RoundedRectangle(cornerRadius: 16, style: .continuous)
                    .stroke(isSelected ? Color(red: 0.2, green: 0.6, blue: 1.0) : Color.clear, lineWidth: 2)
            )
        }
        .buttonStyle(.plain)
    }
}

