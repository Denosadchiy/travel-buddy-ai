//
//  RouteBuildingView.swift
//  Travell Buddy
//
//  Premium loading screen that shows route being built on a live map.
//

import SwiftUI
import MapKit

// MARK: - Main View

struct RouteBuildingView: View {
    @StateObject private var viewModel: RouteBuildingViewModel
    @Environment(\.dismiss) private var dismiss

    let cityName: String
    let cityCoordinate: CLLocationCoordinate2D
    let onRouteReady: (ItineraryResponseDTO) -> Void
    let onRetry: () -> Void
    let onPaywallRequired: () -> Void

    init(
        cityName: String,
        cityCoordinate: CLLocationCoordinate2D,
        tripId: UUID? = nil,
        tripRequest: TripCreateRequestDTO? = nil,
        apiClient: TripPlanningAPIClientProtocol = TripPlanningAPIClient(),
        onRouteReady: @escaping (ItineraryResponseDTO) -> Void,
        onRetry: @escaping () -> Void,
        onPaywallRequired: @escaping () -> Void
    ) {
        self.cityName = cityName
        self.cityCoordinate = cityCoordinate
        self.onRouteReady = onRouteReady
        self.onRetry = onRetry
        self.onPaywallRequired = onPaywallRequired

        _viewModel = StateObject(wrappedValue: RouteBuildingViewModel(
            tripId: tripId,
            tripRequest: tripRequest,
            cityCoordinate: cityCoordinate,
            apiClient: apiClient
        ))
    }

    var body: some View {
        ZStack {
            // MARK: - Background Color (fallback)
            Color.black
                .ignoresSafeArea()

            // MARK: - Live Map Background
            AnimatedRouteMapView(
                centerCoordinate: viewModel.cityCoordinate,
                visiblePOIs: viewModel.visiblePOIs,
                routeCoordinates: viewModel.routeCoordinates,
                latestPOIIndex: viewModel.latestPOIIndex,
                isAnimationComplete: viewModel.isAnimationComplete
            )
            .ignoresSafeArea()

            // MARK: - Gradient Overlay (vignette effect)
            RadialGradient(
                gradient: Gradient(colors: [
                    Color.black.opacity(0.1),
                    Color.black.opacity(0.4)
                ]),
                center: .center,
                startRadius: 100,
                endRadius: 500
            )
            .ignoresSafeArea()

            // Top and bottom fade for text readability
            VStack(spacing: 0) {
                LinearGradient(
                    gradient: Gradient(colors: [
                        Color.black.opacity(0.6),
                        Color.black.opacity(0.0)
                    ]),
                    startPoint: .top,
                    endPoint: .bottom
                )
                .frame(height: 200)

                Spacer()

                LinearGradient(
                    gradient: Gradient(colors: [
                        Color.black.opacity(0.0),
                        Color.black.opacity(0.6)
                    ]),
                    startPoint: .top,
                    endPoint: .bottom
                )
                .frame(height: 200)
            }
            .ignoresSafeArea()

            // MARK: - Content Overlay
            VStack(spacing: 0) {
                // Top text area
                VStack(spacing: 16) {
                    Text("Строим маршрут")
                        .font(.system(size: 20, weight: .semibold))
                        .foregroundColor(.white)
                        .shadow(color: .black.opacity(0.5), radius: 4, x: 0, y: 2)

                    Text(cityName)
                        .font(.system(size: 38, weight: .bold))
                        .foregroundColor(.white)
                        .shadow(color: .black.opacity(0.6), radius: 6, x: 0, y: 3)
                }
                .padding(.top, 80)

                Spacer()

                // Bottom status area
                VStack(spacing: 24) {
                    if viewModel.state == .failed {
                        // Error state
                        errorView
                    } else {
                        // Loading subtitle
                        Text(viewModel.currentSubtitle)
                            .font(.system(size: 18, weight: .medium))
                            .foregroundColor(.white)
                            .shadow(color: .black.opacity(0.5), radius: 4, x: 0, y: 2)
                            .animation(.easeInOut(duration: 0.3), value: viewModel.currentSubtitle)
                            .multilineTextAlignment(.center)
                    }
                }
                .padding(.bottom, 60)
            }
            .padding(.horizontal, 32)
        }
        .onAppear {
            print("🗺️ RouteBuildingView appeared")
            print("🗺️ City: \(cityName)")
            print("🗺️ Coordinate: \(cityCoordinate.latitude), \(cityCoordinate.longitude)")
            viewModel.startRouteGeneration()
        }
        .onChange(of: viewModel.state) { newState in
            print("🔄 RouteBuildingView state changed to: \(newState)")
            switch newState {
            case .completed(let itinerary):
                print("✅ Route completed! Days: \(itinerary.days.count)")
                onRouteReady(itinerary)
            case .paywallRequired:
                onPaywallRequired()
            case .failed:
                // Show error view and let user decide to retry or close
                // Don't automatically dismiss - let user see the error and choose
                print("❌ Route generation failed, showing error view")
            default:
                break
            }
        }
    }

    // MARK: - Error View

    private var errorView: some View {
        VStack(spacing: 20) {
            Text("Не удалось построить маршрут")
                .font(.system(size: 18, weight: .medium))
                .foregroundColor(.white)
                .shadow(color: .black.opacity(0.5), radius: 4, x: 0, y: 2)
                .multilineTextAlignment(.center)

            HStack(spacing: 16) {
                // Close button
                Button(action: {
                    onRetry()  // Dismisses view and shows error alert
                }) {
                    Text("Закрыть")
                        .font(.system(size: 17, weight: .semibold))
                        .foregroundColor(.white)
                        .frame(width: 120, height: 48)
                        .background(Color.white.opacity(0.2))
                        .cornerRadius(24)
                        .overlay(
                            RoundedRectangle(cornerRadius: 24)
                                .stroke(Color.white.opacity(0.4), lineWidth: 1)
                        )
                }

                // Retry button
                Button(action: {
                    viewModel.retry()  // Retry within the same view
                }) {
                    Text("Повторить")
                        .font(.system(size: 17, weight: .semibold))
                        .foregroundColor(.black)
                        .frame(width: 140, height: 48)
                        .background(Color.white)
                        .cornerRadius(24)
                }
            }
        }
    }
}
