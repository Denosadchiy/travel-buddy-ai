//
//  TripCard.swift
//  Travell Buddy
//
//  Card for past/upcoming trip.
//

import SwiftUI

struct TripCard: View {
    let cityAndMonth: String
    let dateRange: String
    let statusText: String
    
    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            ZStack(alignment: .topTrailing) {
                // Имитация фото
                RoundedRectangle(cornerRadius: 22, style: .continuous)
                    .fill(
                        LinearGradient(
                            colors: [
                                Color(red: 1.0, green: 0.63, blue: 0.38),
                                Color(red: 0.86, green: 0.35, blue: 0.30)
                            ],
                            startPoint: .topLeading,
                            endPoint: .bottomTrailing
                        )
                    )
                    .frame(width: 220, height: 130)
                    .overlay(
                        Image(systemName: "building.columns.fill")
                            .font(.system(size: 40, weight: .semibold))
                            .foregroundColor(.white.opacity(0.85))
                    )
                
                Text(statusText)
                    .font(.system(size: 12, weight: .semibold, design: .rounded))
                    .padding(.horizontal, 10)
                    .padding(.vertical, 6)
                    .background(
                        Capsule()
                            .fill(Color(red: 1.0, green: 0.64, blue: 0.33))
                    )
                    .foregroundColor(.white)
                    .padding(10)
            }
            
            Text(cityAndMonth)
                .font(.system(size: 16, weight: .semibold, design: .rounded))
                .foregroundColor(Color(.label))
            
            HStack(spacing: 6) {
                Image(systemName: "calendar")
                    .font(.system(size: 13))
                    .foregroundColor(Color(.secondaryLabel))
                
                Text(dateRange)
                    .font(.system(size: 13))
                    .foregroundColor(Color(.secondaryLabel))
            }
        }
        .padding(10)
        .background(
            RoundedRectangle(cornerRadius: 22, style: .continuous)
                .fill(Color.white)
        )
        .shadow(color: Color.black.opacity(0.08), radius: 10, x: 0, y: 6)
    }
}

