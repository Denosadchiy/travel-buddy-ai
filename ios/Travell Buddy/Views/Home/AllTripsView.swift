//
//  AllTripsView.swift
//  Travell Buddy
//
//  Full list of all saved trips with pull-to-refresh.
//

import SwiftUI

struct AllTripsView: View {
    let showsBackButton: Bool

    @StateObject private var savedTripsManager = SavedTripsManager.shared
    @StateObject private var tripPlanViewModel = TripPlanViewModel()
    @State private var selectedTripId: UUID?
    @State private var isLoadingTrip = false
    @State private var showTripPlan = false
    @Environment(\.dismiss) private var dismiss

    init(showsBackButton: Bool = true) {
        self.showsBackButton = showsBackButton
    }

    var body: some View {
        ZStack {
            // Background
            backgroundLayer
                .ignoresSafeArea()

            VStack(spacing: 0) {
                // Header
                headerView

                // Content
                if savedTripsManager.isLoading && savedTripsManager.allTrips.isEmpty {
                    loadingView
                } else if savedTripsManager.allTrips.isEmpty {
                    emptyStateView
                } else {
                    tripsList
                }
            }
        }
        .navigationBarHidden(true)
        .modifier(ConditionalHideTabBarModifier(shouldHide: showsBackButton))
        .task {
            await savedTripsManager.refreshAll()
        }
    }

    // MARK: - Components

    private var backgroundLayer: some View {
        LinearGradient(
            colors: [
                Color(red: 0.14, green: 0.08, blue: 0.06),
                Color(red: 0.10, green: 0.06, blue: 0.04)
            ],
            startPoint: .top,
            endPoint: .bottom
        )
    }

    private var headerView: some View {
        HStack {
            if showsBackButton {
                Button(action: { dismiss() }) {
                    Image(systemName: "chevron.left")
                        .font(.system(size: 16, weight: .semibold))
                        .foregroundColor(.white)
                        .frame(width: 40, height: 40)
                        .background(Color.black.opacity(0.3), in: Circle())
                        .overlay(
                            Circle()
                                .stroke(Color.white.opacity(0.12), lineWidth: 1)
                        )
                }
                .buttonStyle(.plain)
            } else {
                Color.clear
                    .frame(width: 40, height: 40)
            }

            Spacer()

            Text("Мои поездки")
                .font(.system(size: 18, weight: .semibold))
                .foregroundColor(.white)

            Spacer()

            // Placeholder for symmetry
            Color.clear
                .frame(width: 40, height: 40)
        }
        .padding(.horizontal, 16)
        .padding(.top, 16)
        .padding(.bottom, 12)
    }

    private var loadingView: some View {
        VStack {
            Spacer()
            ProgressView()
                .tint(.white)
                .scaleEffect(1.2)
            Text("Загрузка...")
                .font(.system(size: 14, weight: .medium))
                .foregroundColor(.white.opacity(0.7))
                .padding(.top, 12)
            Spacer()
        }
    }

    private var emptyStateView: some View {
        VStack(spacing: 16) {
            Spacer()

            Image(systemName: "bookmark")
                .font(.system(size: 48, weight: .light))
                .foregroundColor(.white.opacity(0.4))

            Text("Нет сохранённых маршрутов")
                .font(.system(size: 18, weight: .semibold))
                .foregroundColor(.white)

            Text("Создайте и сохраните маршрут,\nчтобы он появился здесь")
                .font(.system(size: 14, weight: .regular))
                .foregroundColor(.white.opacity(0.6))
                .multilineTextAlignment(.center)

            Spacer()
        }
        .padding(.horizontal, 24)
    }

    private var tripsList: some View {
        ZStack {
            ScrollView(showsIndicators: false) {
                LazyVStack(spacing: 16) {
                    ForEach(savedTripsManager.allTrips) { trip in
                        Button(action: {
                            loadAndShowTrip(tripId: trip.id)
                        }) {
                            AllTripCardView(trip: trip)
                        }
                        .buttonStyle(.plain)
                    }
                }
                .padding(.horizontal, 16)
                .padding(.top, 8)
                .padding(.bottom, showsBackButton ? 32 : 32 + HomeStyle.Layout.tabBarHeight)
            }
            .refreshable {
                await savedTripsManager.refreshAll()
            }

            // Loading overlay
            if isLoadingTrip {
                Color.black.opacity(0.4)
                    .ignoresSafeArea()
                VStack(spacing: 16) {
                    ProgressView()
                        .tint(.white)
                        .scaleEffect(1.4)
                    Text("Загрузка маршрута...")
                        .font(.system(size: 15, weight: .medium))
                        .foregroundColor(.white)
                }
            }
        }
        .fullScreenCover(isPresented: $showTripPlan) {
            if tripPlanViewModel.plan != nil {
                NavigationStack {
                    TripPlanView(viewModel: tripPlanViewModel)
                }
            }
        }
    }

    private func loadAndShowTrip(tripId: UUID) {
        isLoadingTrip = true

        Task {
            // Load the trip plan from the saved trip
            if let tripPlan = await savedTripsManager.getSavedTripAsPlan(id: tripId) {
                await MainActor.run {
                    tripPlanViewModel.plan = tripPlan
                    tripPlanViewModel.isLoadedFromSavedTrip = true
                    tripPlanViewModel.hasUnsavedChanges = false
                    isLoadingTrip = false
                    showTripPlan = true
                }
            } else {
                await MainActor.run {
                    isLoadingTrip = false
                    // TODO: Show error alert if needed
                }
            }
        }
    }
}

// MARK: - All Trip Card View

private struct AllTripCardView: View {
    let trip: SavedTripCard

    var body: some View {
        HStack(spacing: 16) {
            // Thumbnail
            if let imageUrlString = trip.heroImageUrl, let url = URL(string: imageUrlString) {
                RemoteImageView(url: url)
                    .frame(width: 80, height: 80)
                    .clipShape(RoundedRectangle(cornerRadius: 16, style: .continuous))
            } else {
                RoundedRectangle(cornerRadius: 16, style: .continuous)
                    .fill(
                        LinearGradient(
                            colors: [
                                Color(red: 0.3, green: 0.25, blue: 0.2),
                                Color(red: 0.15, green: 0.12, blue: 0.1)
                            ],
                            startPoint: .topLeading,
                            endPoint: .bottomTrailing
                        )
                    )
                    .frame(width: 80, height: 80)
                    .overlay(
                        Image(systemName: "map.fill")
                            .font(.system(size: 24, weight: .medium))
                            .foregroundColor(.white.opacity(0.4))
                    )
            }

            // Info
            VStack(alignment: .leading, spacing: 6) {
                Text(trip.cityName)
                    .font(.system(size: 17, weight: .semibold))
                    .foregroundColor(.white)
                    .lineLimit(1)

                Text(trip.dateRangeFormatted)
                    .font(.system(size: 13, weight: .medium))
                    .foregroundColor(.white.opacity(0.6))

                // Days count
                let days = Calendar.current.dateComponents([.day], from: trip.startDate, to: trip.endDate).day ?? 0
                Text("\(days + 1) дней")
                    .font(.system(size: 12, weight: .medium))
                    .foregroundColor(Color.travelBuddyOrange)
                    .padding(.horizontal, 8)
                    .padding(.vertical, 4)
                    .background(
                        Capsule()
                            .fill(Color.travelBuddyOrange.opacity(0.15))
                    )
            }

            Spacer()

            // Arrow
            Image(systemName: "chevron.right")
                .font(.system(size: 14, weight: .semibold))
                .foregroundColor(.white.opacity(0.4))
        }
        .padding(14)
        .background(
            RoundedRectangle(cornerRadius: 20, style: .continuous)
                .fill(Color(red: 0.18, green: 0.18, blue: 0.20).opacity(0.7))
                .background(.ultraThinMaterial, in: RoundedRectangle(cornerRadius: 20, style: .continuous))
                .shadow(color: Color.black.opacity(0.25), radius: 12, x: 0, y: 8)
        )
        .overlay(
            RoundedRectangle(cornerRadius: 20, style: .continuous)
                .stroke(Color.white.opacity(0.08), lineWidth: 1)
        )
    }
}

#Preview {
    AllTripsView()
}
