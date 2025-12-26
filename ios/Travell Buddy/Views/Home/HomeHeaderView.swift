//
//  HomeHeaderView.swift
//  Travell Buddy
//
//  Header for home screen.
//

import SwiftUI

struct HomeHeaderView: View {
    var body: some View {
        HStack {
            Text("Travel Buddy")
                .font(.system(size: 15, weight: .medium, design: .rounded))
                .foregroundColor(Color(.secondaryLabel))
            
            Spacer()
            
            ZStack {
                Circle()
                    .fill(
                        LinearGradient(
                            colors: [
                                Color(red: 1.0, green: 0.69, blue: 0.55),
                                Color(red: 0.86, green: 0.52, blue: 0.97)
                            ],
                            startPoint: .topLeading,
                            endPoint: .bottomTrailing
                        )
                    )
                    .frame(width: 36, height: 36)
                
                Text("AH")
                    .font(.system(size: 14, weight: .semibold, design: .rounded))
                    .foregroundColor(.white)
            }
        }
    }
}

