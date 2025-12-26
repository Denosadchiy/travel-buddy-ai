//
//  TravelerCountRow.swift
//  Travell Buddy
//
//  Counter row for travelers picker.
//

import SwiftUI

struct TravelerCountRow: View {
    let title: String
    let subtitle: String
    let icon: String
    let iconColor: Color
    @Binding var count: Int
    let minValue: Int
    
    var body: some View {
        HStack(spacing: 16) {
            // Иконка
            ZStack {
                Circle()
                    .fill(iconColor.opacity(0.15))
                    .frame(width: 50, height: 50)
                
                Image(systemName: icon)
                    .font(.system(size: 24, weight: .semibold))
                    .foregroundColor(iconColor)
            }
            
            // Текст
            VStack(alignment: .leading, spacing: 4) {
                Text(title)
                    .font(.system(size: 17, weight: .semibold, design: .rounded))
                    .foregroundColor(Color(.label))
                
                Text(subtitle)
                    .font(.system(size: 14))
                    .foregroundColor(Color(.secondaryLabel))
            }
            
            Spacer()
            
            // Кнопки +/-
            HStack(spacing: 16) {
                // Кнопка минус
                Button(action: {
                    if count > minValue {
                        withAnimation {
                            count -= 1
                        }
                    }
                }) {
                    ZStack {
                        Circle()
                            .fill(count > minValue ? Color(.systemGray5) : Color(.systemGray6))
                            .frame(width: 44, height: 44)
                        
                        Image(systemName: "minus")
                            .font(.system(size: 18, weight: .semibold))
                            .foregroundColor(count > minValue ? Color(.label) : Color(.tertiaryLabel))
                    }
                }
                .buttonStyle(.plain)
                .disabled(count <= minValue)
                
                // Счётчик
                Text("\(count)")
                    .font(.system(size: 24, weight: .bold, design: .rounded))
                    .foregroundColor(Color(.label))
                    .frame(minWidth: 40)
                
                // Кнопка плюс
                Button(action: {
                    withAnimation {
                        count += 1
                    }
                }) {
                    ZStack {
                        Circle()
                            .fill(Color(red: 0.2, green: 0.6, blue: 1.0))
                            .frame(width: 44, height: 44)
                        
                        Image(systemName: "plus")
                            .font(.system(size: 18, weight: .semibold))
                            .foregroundColor(.white)
                    }
                }
                .buttonStyle(.plain)
            }
        }
        .padding(16)
        .background(
            RoundedRectangle(cornerRadius: 18, style: .continuous)
                .fill(Color.white)
        )
        .shadow(color: Color.black.opacity(0.05), radius: 8, x: 0, y: 4)
    }
}

