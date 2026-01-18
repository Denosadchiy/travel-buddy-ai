//
//  ContentView.swift
//  Travell Buddy
//
//  Created by Gleb Konkin on 01.12.2025.
//

import SwiftUI

// MARK: - Splash Screen

/// Стартовый экран с брендингом Travel Buddy, который автоматически
/// переключается на основное приложение через пару секунд.
struct SplashView: View {
    /// Callback, вызываемый по завершении анимации/задержки.
    let onFinished: () -> Void

    private let delay: TimeInterval = 3.2
    private let accentOrange = Color(red: 1.0, green: 0.478, blue: 0.184)

    var body: some View {
        ZStack {
            AnimatedMapBackground()
            MapOverlay()
            RouteAnimationLayer(accent: accentOrange)
            SplashContent(accent: accentOrange, duration: delay)
        }
        .onAppear {
            DispatchQueue.main.asyncAfter(deadline: .now() + delay) {
                onFinished()
            }
        }
    }
}

private struct SplashContent: View {
    let accent: Color
    let duration: TimeInterval

    var body: some View {
        VStack {
            Spacer()

            VStack(spacing: 22) {
                GlassLogo(accent: accent)

                VStack(spacing: 10) {
                    Text("Travel Buddy")
                        .font(.system(size: 40, weight: .heavy, design: .rounded))
                        .foregroundColor(.white)
                        .shadow(color: Color.black.opacity(0.35), radius: 8, x: 0, y: 6)

                    Text("Твой умный тревел-приятель")
                        .font(.system(size: 18, weight: .medium, design: .rounded))
                        .foregroundColor(.white.opacity(0.75))
                        .shadow(color: Color.black.opacity(0.35), radius: 6, x: 0, y: 4)
                }
                .multilineTextAlignment(.center)
            }

            Spacer()

            VStack(alignment: .leading, spacing: 12) {
                Text("Планируем ваше следующее путешествие…")
                    .font(.system(size: 15, weight: .medium))
                    .foregroundColor(.white.opacity(0.85))
                    .shadow(color: Color.black.opacity(0.35), radius: 6, x: 0, y: 4)

                SplashProgressBar(accent: accent, duration: duration)
            }
            .padding(.horizontal, 32)
            .padding(.bottom, 32)
        }
    }
}

private struct GlassLogo: View {
    let accent: Color

    var body: some View {
        ZStack {
            Circle()
                .fill(.ultraThinMaterial)
                .overlay(
                    Circle()
                        .stroke(Color.white.opacity(0.12), lineWidth: 1)
                )
                .frame(width: 120, height: 120)
                .shadow(color: Color.black.opacity(0.25), radius: 18, x: 0, y: 12)

            Image(systemName: "mappin.circle.fill")
                .symbolRenderingMode(.hierarchical)
                .font(.system(size: 52, weight: .bold))
                .foregroundColor(accent)
        }
    }
}

private struct SplashProgressBar: View {
    let accent: Color
    let duration: TimeInterval
    @State private var progress: CGFloat = 0

    var body: some View {
        GeometryReader { proxy in
            ZStack(alignment: .leading) {
                Capsule()
                    .fill(Color.white.opacity(0.15))

                Capsule()
                    .fill(accent)
                    .frame(width: proxy.size.width * progress)
            }
        }
        .frame(height: 5)
        .onAppear {
            progress = 0
            withAnimation(.linear(duration: duration)) {
                progress = 1
            }
        }
    }
}

private struct AnimatedMapBackground: View {
    @State private var animate = false

    private let baseScale: CGFloat = 1.05
    private let targetScale: CGFloat = 1.1
    private let baseOffset = CGSize(width: -20, height: 30)
    private let targetOffset = CGSize(width: 20, height: -30)

    var body: some View {
        GeometryReader { proxy in
            Image("launch_map_dark_paris")
                .resizable()
                .scaledToFill()
                .frame(width: proxy.size.width, height: proxy.size.height)
                .scaleEffect(animate ? targetScale : baseScale)
                .offset(animate ? targetOffset : baseOffset)
                .clipped()
                .animation(.easeInOut(duration: 16).repeatForever(autoreverses: true), value: animate)
        }
        .ignoresSafeArea()
        .onAppear {
            animate = true
        }
    }
}

private struct MapOverlay: View {
    var body: some View {
        LinearGradient(
            colors: [
                Color.black.opacity(0.55),
                Color.black.opacity(0.18),
                Color.black.opacity(0.5)
            ],
            startPoint: .top,
            endPoint: .bottom
        )
        .ignoresSafeArea()
                .overlay(Color.black.opacity(0.16).ignoresSafeArea())
    }
}

private struct RouteAnimationLayer: View {
    let accent: Color
    @State private var routeTrim: CGFloat = 0
    @State private var routeOpacity: Double = 0

    var body: some View {
        GeometryReader { proxy in
            let rect = proxy.frame(in: .local)
            ZStack {
                RouteShape()
                    .trim(from: 0, to: routeTrim)
                    .stroke(
                        accent,
                        style: StrokeStyle(
                            lineWidth: 2,
                            lineCap: .round,
                            lineJoin: .round
                        )
                    )
                    .opacity(routeOpacity)

                RouteDots(progress: routeTrim, opacity: routeOpacity, accent: accent, rect: rect)
            }
            .frame(width: rect.width, height: rect.height)
        }
        .ignoresSafeArea()
        .task {
            await animateRoute()
        }
    }

    @MainActor
    private func animateRoute() async {
        while !Task.isCancelled {
            routeTrim = 0
            routeOpacity = 0
            try? await Task.sleep(for: .milliseconds(250))

            routeOpacity = 0.65
            withAnimation(.easeInOut(duration: 2.0)) {
                routeTrim = 1
            }
            try? await Task.sleep(for: .milliseconds(2100))

            withAnimation(.easeOut(duration: 0.7)) {
                routeOpacity = 0
            }
            try? await Task.sleep(for: .milliseconds(4200))
        }
    }
}

private struct RouteDots: View {
    let progress: CGFloat
    let opacity: Double
    let accent: Color
    let rect: CGRect

    var body: some View {
        let leadPoint = RoutePathModel.point(at: progress, in: rect)
        let trailPoint = RoutePathModel.point(at: progress - 0.12, in: rect)
        let trailOpacity = progress > 0.12 ? opacity * 0.7 : 0

        Circle()
            .fill(accent)
            .frame(width: 4, height: 4)
            .position(leadPoint)
            .opacity(opacity)

        Circle()
            .fill(accent)
            .frame(width: 3, height: 3)
            .position(trailPoint)
            .opacity(trailOpacity)
    }
}

private struct RouteShape: Shape {
    func path(in rect: CGRect) -> Path {
        var path = Path()
        let segments = RoutePathModel.segments(in: rect)
        guard let first = segments.first else { return path }
        path.move(to: first.start)
        for segment in segments {
            path.addCurve(
                to: segment.end,
                control1: segment.control1,
                control2: segment.control2
            )
        }
        return path
    }
}

private struct RoutePathModel {
    struct Segment {
        let start: CGPoint
        let control1: CGPoint
        let control2: CGPoint
        let end: CGPoint
    }

    static func segments(in rect: CGRect) -> [Segment] {
        let w = rect.width
        let h = rect.height

        let p0 = CGPoint(x: 0.14 * w, y: 0.22 * h)
        let p1 = CGPoint(x: 0.28 * w, y: 0.08 * h)
        let p2 = CGPoint(x: 0.36 * w, y: 0.36 * h)
        let p3 = CGPoint(x: 0.48 * w, y: 0.3 * h)

        let p4 = CGPoint(x: 0.58 * w, y: 0.24 * h)
        let p5 = CGPoint(x: 0.7 * w, y: 0.52 * h)
        let p6 = CGPoint(x: 0.78 * w, y: 0.46 * h)

        let p7 = CGPoint(x: 0.88 * w, y: 0.4 * h)
        let p8 = CGPoint(x: 0.86 * w, y: 0.7 * h)
        let p9 = CGPoint(x: 0.64 * w, y: 0.78 * h)

        let p10 = CGPoint(x: 0.52 * w, y: 0.88 * h)
        let p11 = CGPoint(x: 0.3 * w, y: 0.86 * h)
        let p12 = CGPoint(x: 0.2 * w, y: 0.72 * h)

        return [
            Segment(start: p0, control1: p1, control2: p2, end: p3),
            Segment(start: p3, control1: p4, control2: p5, end: p6),
            Segment(start: p6, control1: p7, control2: p8, end: p9),
            Segment(start: p9, control1: p10, control2: p11, end: p12)
        ]
    }

    static func point(at t: CGFloat, in rect: CGRect) -> CGPoint {
        let segments = segments(in: rect)
        guard !segments.isEmpty else { return .zero }
        let clamped = min(max(t, 0), 1)
        let segmentLength = 1 / CGFloat(segments.count)
        let index = min(Int(clamped / segmentLength), segments.count - 1)
        let localT = (clamped - (segmentLength * CGFloat(index))) / segmentLength
        let segment = segments[index]
        return cubicBezier(
            t: localT,
            p0: segment.start,
            p1: segment.control1,
            p2: segment.control2,
            p3: segment.end
        )
    }

    private static func cubicBezier(t: CGFloat, p0: CGPoint, p1: CGPoint, p2: CGPoint, p3: CGPoint) -> CGPoint {
        let mt = 1 - t
        let mt2 = mt * mt
        let mt3 = mt2 * mt
        let t2 = t * t
        let t3 = t2 * t

        let x = (mt3 * p0.x) + (3 * mt2 * t * p1.x) + (3 * mt * t2 * p2.x) + (t3 * p3.x)
        let y = (mt3 * p0.y) + (3 * mt2 * t * p1.y) + (3 * mt * t2 * p2.y) + (t3 * p3.y)
        return CGPoint(x: x, y: y)
    }
}

// MARK: - Main Tab Bar & Home

/// Основной TabView приложения (показывается после Splash).
struct MainTabView: View {
    @State private var selectedTab: MainTab = .home
    @State private var pendingDestinationTab: MainTab?
    @StateObject private var gatingManager = AuthGatingManager.shared

    var body: some View {
        TabView(selection: $selectedTab) {
            HomeTabRootView()
                .tabItem {
                    Label(MainTab.home.title, systemImage: MainTab.home.systemImage)
                }
                .tag(MainTab.home)

            NewTripTabRootView()
                .tabItem {
                    Label(MainTab.newTrip.title, systemImage: MainTab.newTrip.systemImage)
                }
                .tag(MainTab.newTrip)

            SavedTripsTabRootView()
                .tabItem {
                    Label(MainTab.savedTrips.title, systemImage: MainTab.savedTrips.systemImage)
                }
                .tag(MainTab.savedTrips)

            ProfileTabRootView()
                .tabItem {
                    Label(MainTab.profile.title, systemImage: MainTab.profile.systemImage)
                }
                .tag(MainTab.profile)
        }
        .tint(Color.travelBuddyOrange)
        .sheet(isPresented: $gatingManager.isAuthModalPresented) {
            PaywallView(
                subtitle: gatingManager.gatingMessage,
                dayNumber: gatingManager.pendingAction?.dayNumber,
                onAuthSuccess: {
                    gatingManager.handleAuthSuccess()
                }
            )
            .interactiveDismissDisabled(false)
            .onDisappear {
                if !AuthManager.shared.isAuthenticated {
                    gatingManager.cancelPendingAction()
                    pendingDestinationTab = nil
                }
            }
        }
        .onReceive(NotificationCenter.default.publisher(for: .mainTabSelectionRequested)) { notification in
            guard let tab = notification.object as? MainTab else { return }
            handleTabSelection(tab)
        }
    }

    private func handleTabSelection(_ tab: MainTab) {
        guard let protectedAction = tab.protectedAction else {
            selectedTab = tab
            pendingDestinationTab = nil
            return
        }

        if AuthManager.shared.isAuthenticated {
            selectedTab = tab
            pendingDestinationTab = nil
            return
        }

        pendingDestinationTab = tab
        gatingManager.requireAuth(for: protectedAction) {
            guard let pendingTab = pendingDestinationTab else { return }
            selectedTab = pendingTab
            pendingDestinationTab = nil
        }
    }
}

#Preview {
    NavigationStack {
        HomeView()
    }
}
