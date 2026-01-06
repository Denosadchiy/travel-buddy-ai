//
//  ContentView.swift
//  Travell Buddy
//
//  Created by Gleb Konkin on 01.12.2025.
//

import SwiftUI
import MapKit

// MARK: - Splash Screen

/// Стартовый экран с брендингом Travel Buddy, который автоматически
/// переключается на основное приложение через пару секунд.
struct SplashView: View {
    /// Callback, вызываемый по завершении анимации/задержки.
    let onFinished: () -> Void

    private let delay: TimeInterval = 2.5

    var body: some View {
        ZStack {
            // Фоновый градиент, близкий к макету: тёплый оранжевый → бирюзовый
            LinearGradient(
                colors: [
                    Color(red: 1.0, green: 0.60, blue: 0.35),
                    Color(red: 0.05, green: 0.78, blue: 0.78)
                ],
                startPoint: .topLeading,
                endPoint: .bottomTrailing
            )
            .ignoresSafeArea()

        VStack {
                Spacer()

                // Центральный блок с иконкой и логотипом
                VStack(spacing: 28) {
                    // Иконка в белом круге
                    ZStack {
                        Circle()
                            .fill(Color.white)
                            .frame(width: 120, height: 120)
                            .shadow(color: Color.black.opacity(0.18), radius: 18, x: 0, y: 12)

                        Image(systemName: "mappin.circle.fill")
                            .symbolRenderingMode(.hierarchical)
                            .font(.system(size: 50, weight: .bold))
                            .foregroundColor(Color(red: 1.0, green: 0.55, blue: 0.25))
                    }

                    // Текстовый логотип
                    VStack(spacing: 10) {
                        Text("Travel Buddy")
                            .font(.system(size: 40, weight: .heavy, design: .rounded))
                            .foregroundColor(.white)
                            .shadow(color: Color.black.opacity(0.15), radius: 10, x: 0, y: 6)

                        Text("Твой умный тревел-приятель")
                            .font(.system(size: 18, weight: .medium, design: .rounded))
                            .foregroundColor(.white.opacity(0.96))
                    }
                    .multilineTextAlignment(.center)
                }

                Spacer()

                // Нижний текст с индикатором прогресса
                VStack(alignment: .leading, spacing: 12) {
                    Text("Планируем ваше следующее путешествие…")
                        .font(.system(size: 15, weight: .medium))
                        .foregroundColor(.white.opacity(0.96))

                    ProgressView()
                        .progressViewStyle(.linear)
                        .tint(.white)
                        .frame(maxWidth: .infinity)
                        .padding(.vertical, 2)
                        .background(Color.white.opacity(0.08))
                        .cornerRadius(999)
                }
                .padding(.horizontal, 32)
                .padding(.bottom, 44)
            }
        }
        .onAppear {
            DispatchQueue.main.asyncAfter(deadline: .now() + delay) {
                onFinished()
            }
        }
    }
}

// MARK: - Main Tab Bar & Home

/// Основной TabView приложения (показывается после Splash).
struct MainTabView: View {
    var body: some View {
        TabView {
            NavigationStack {
                HomeView()
            }
            .tabItem {
                Image(systemName: "house.fill")
                Text("Главная")
            }

            NavigationStack {
                Text("Поиск")
                    .font(.system(.title3, design: .rounded))
                    .foregroundColor(.primary)
                    .navigationTitle("Поиск")
                    .navigationBarTitleDisplayMode(.inline)
            }
            .tabItem {
                Image(systemName: "magnifyingglass")
                Text("Поиск")
            }

            NavigationStack {
                Text("Сохранено")
                    .font(.system(.title3, design: .rounded))
                    .foregroundColor(.primary)
                    .navigationTitle("Сохранено")
                    .navigationBarTitleDisplayMode(.inline)
            }
            .tabItem {
                Image(systemName: "bookmark.fill")
                Text("Сохранено")
            }

            NavigationStack {
                Text("Профиль")
                    .font(.system(.title3, design: .rounded))
                    .foregroundColor(.primary)
                    .navigationTitle("Профиль")
                    .navigationBarTitleDisplayMode(.inline)
            }
            .tabItem {
                Image(systemName: "person.crop.circle")
                Text("Профиль")
            }
        }
        .tint(Color.travelBuddyOrange)
        .toolbarBackground(Color(red: 0.14, green: 0.14, blue: 0.13), for: .tabBar)
        .toolbarBackground(.visible, for: .tabBar)
        .toolbarColorScheme(.dark, for: .tabBar)
    }
}

#Preview {
    NavigationStack {
        HomeView()
    }
}




