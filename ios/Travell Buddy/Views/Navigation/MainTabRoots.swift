//
//  MainTabRoots.swift
//  Travell Buddy
//
//  Root views for each main tab.
//

import SwiftUI

struct HomeTabRootView: View {
    var body: some View {
        NavigationStack {
            HomeView()
        }
    }
}

struct NewTripTabRootView: View {
    var body: some View {
        NavigationStack {
            NewTripView(isRootView: true)
        }
    }
}

struct SavedTripsTabRootView: View {
    @StateObject private var authManager = AuthManager.shared
    @StateObject private var savedTripsManager = SavedTripsManager.shared

    var body: some View {
        NavigationStack {
            AllTripsView(showsBackButton: false)
        }
        .task {
            await savedTripsManager.refreshAll()
        }
        .onChange(of: authManager.state) { _, newState in
            if case .loggedIn = newState {
                Task {
                    await savedTripsManager.refreshAll()
                }
            }
        }
    }
}

struct ProfileTabRootView: View {
    var body: some View {
        AccountSheet(title: "Профиль", showsDoneButton: false)
    }
}
