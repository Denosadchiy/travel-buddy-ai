//
//  Travell_BuddyApp.swift
//  Travell Buddy
//
//  Created by Gleb Konkin on 01.12.2025.
//

import SwiftUI
import GoogleSignIn
import UIKit

/// Главная точка входа в приложение Travel Buddy.
/// Показывает splash-экран, затем RootView с auth-gate.
@main
struct Travell_BuddyApp: App {
    @State private var showSplash: Bool = true

    init() {
        configureTabBarAppearance()
    }

    var body: some Scene {
        WindowGroup {
            Group {
                if showSplash {
                    SplashView {
                        withAnimation(.easeInOut(duration: 0.35)) {
                            showSplash = false
                        }
                    }
                } else {
                    RootView()
                }
            }
            .onOpenURL { url in
                GIDSignIn.sharedInstance.handle(url)
            }
        }
    }

    private func configureTabBarAppearance() {
        let tabBarAppearance = UITabBarAppearance()
        tabBarAppearance.configureWithOpaqueBackground()
        tabBarAppearance.backgroundColor = UIColor(red: 0.14, green: 0.14, blue: 0.13, alpha: 1.0)
        tabBarAppearance.shadowColor = .clear

        let itemAppearance = UITabBarItemAppearance()
        itemAppearance.normal.iconColor = UIColor(white: 0.70, alpha: 1.0)
        itemAppearance.normal.titleTextAttributes = [.foregroundColor: UIColor(white: 0.70, alpha: 1.0)]
        itemAppearance.selected.iconColor = UIColor(red: 1.0, green: 0.46, blue: 0.21, alpha: 1.0)
        itemAppearance.selected.titleTextAttributes = [.foregroundColor: UIColor(red: 1.0, green: 0.46, blue: 0.21, alpha: 1.0)]

        tabBarAppearance.stackedLayoutAppearance = itemAppearance
        tabBarAppearance.inlineLayoutAppearance = itemAppearance
        tabBarAppearance.compactInlineLayoutAppearance = itemAppearance

        UITabBar.appearance().standardAppearance = tabBarAppearance
        UITabBar.appearance().scrollEdgeAppearance = tabBarAppearance
    }
}
