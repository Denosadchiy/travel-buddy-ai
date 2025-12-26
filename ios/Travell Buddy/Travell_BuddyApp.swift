//
//  Travell_BuddyApp.swift
//  Travell Buddy
//
//  Created by Gleb Konkin on 01.12.2025.
//

import SwiftUI

/// Главная точка входа в приложение Travel Buddy.
/// Показывает splash-экран, затем основное приложение с таб-баром.
@main
struct Travell_BuddyApp: App {
    @State private var showSplash: Bool = true
    
    var body: some Scene {
        WindowGroup {
            if showSplash {
                SplashView {
                    withAnimation(.easeInOut(duration: 0.35)) {
                        showSplash = false
                    }
                }
            } else {
                MainTabView()
            }
        }
    }
}
