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
    let gradient: Gradient
    let systemImageName: String
    
    var body: some View {
        ZStack(alignment: .topTrailing) {
            // Цветной фон, похожий на макет
            RoundedRectangle(cornerRadius: 26, style: .continuous)
                .fill(
                    LinearGradient(
                        gradient: gradient,
                        startPoint: .topLeading,
                        endPoint: .bottomTrailing
                    )
                )
                .shadow(color: Color.black.opacity(0.10), radius: 12, x: 0, y: 8)
            
            HStack(alignment: .top, spacing: 16) {
                VStack(alignment: .leading, spacing: 10) {
                    Text(title)
                        .font(.system(size: 20, weight: .semibold, design: .rounded))
                        .foregroundColor(.white)
                        .fixedSize(horizontal: false, vertical: true)
                    
                    Text(subtitle)
                        .font(.system(size: 14, weight: .regular))
                        .foregroundColor(.white.opacity(0.9))
                        .fixedSize(horizontal: false, vertical: true)
                }
                
                Spacer()
                
                ZStack {
                    RoundedRectangle(cornerRadius: 18, style: .continuous)
                        .fill(Color.white.opacity(0.25))
                        .frame(width: 42, height: 48)
                    
                    Image(systemName: systemImageName)
                        .font(.system(size: 20, weight: .semibold))
                        .foregroundColor(.white)
                }
            }
            .padding(18)
        }
        .frame(maxWidth: .infinity)
    }
}

