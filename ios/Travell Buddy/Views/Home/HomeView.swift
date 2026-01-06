//
//  HomeView.swift
//  Travell Buddy
//
//  Main home screen.
//

import SwiftUI

struct HomeView: View {
    @State private var showAccountSheet: Bool = false
    @State private var showAuthSheet: Bool = false

    private let warmWhite = Color(red: 0.96, green: 0.95, blue: 0.93)
    private let mutedWarmGray = Color(red: 0.72, green: 0.69, blue: 0.64)
    private let backgroundTop = Color(red: 0.43, green: 0.42, blue: 0.40)
    private let backgroundMid = Color(red: 0.29, green: 0.28, blue: 0.26)
    private let backgroundBottom = Color(red: 0.14, green: 0.13, blue: 0.12)

    var body: some View {
        ZStack {
            LinearGradient(
                colors: [backgroundTop, backgroundMid, backgroundBottom],
                startPoint: .top,
                endPoint: .bottom
            )
            .ignoresSafeArea()

            GeometryReader { proxy in
                Image("mountains")
                    .resizable()
                    .scaledToFill()
                    .frame(width: proxy.size.width, height: proxy.size.height)
                    .clipped()
                    .scaleEffect(1.02)
                    .offset(y: proxy.size.height * 0.03)
                    .opacity(0.95)
                    .blur(radius: 1.2)
                    .mask(
                        LinearGradient(
                            colors: [
                                Color.black.opacity(0.0),
                                Color.black.opacity(0.08),
                                Color.black.opacity(0.28),
                                Color.black.opacity(0.7)
                            ],
                            startPoint: .top,
                            endPoint: .bottom
                        )
                    )
            }
            .ignoresSafeArea()

            LinearGradient(
                colors: [
                    Color.clear,
                    Color.black.opacity(0.08)
                ],
                startPoint: .top,
                endPoint: .bottom
            )
            .ignoresSafeArea()

            Image("noise")
                .resizable(resizingMode: .tile)
                .opacity(0.025)
                .blendMode(.softLight)
                .ignoresSafeArea()

            ScrollView(showsIndicators: false) {
                VStack(alignment: .leading, spacing: 22) {
                    HomeHeaderView(
                        greeting: "Добрый день",
                        name: "Александр",
                        onAccountTap: {
                            if AuthSessionStore.shared.accessToken == nil {
                                showAuthSheet = true
                            } else {
                                showAccountSheet = true
                            }
                        }
                    )
                    .padding(.top, 12)

                    heroSection

                    NavigationLink(destination: NewTripView()) {
                        MainActionCard(
                            title: "Спланировать поездку",
                            subtitle: "Создайте маршрут своей мечты",
                            ctaText: "Начать →",
                            leadingSystemImage: "airplane",
                            trailingSystemImage: "map.fill"
                        )
                    }
                    .buttonStyle(.plain)

                    HStack(spacing: 14) {
                        NavigationLink(destination: LiveGuideView()) {
                            SecondaryActionCard(
                                title: "Я уже в путешествии",
                                systemImageName: "location.fill",
                                trailingSystemImage: "chevron.right"
                            )
                        }
                        .buttonStyle(.plain)

                        NavigationLink(destination: FlightTicketInputView()) {
                            SecondaryActionCard(
                                title: "Добавить билет",
                                systemImageName: "ticket.fill",
                                trailingSystemImage: "plus"
                            )
                        }
                        .buttonStyle(.plain)
                    }

                    myTripsSection
                }
                .padding(.horizontal, 20)
                .padding(.bottom, 28)
            }
        }
        .navigationBarHidden(true)
        .sheet(isPresented: $showAccountSheet) {
            AccountSheet()
        }
        .sheet(isPresented: $showAuthSheet) {
            PaywallView(
                errorMessage: "Войдите, чтобы открыть личный кабинет",
                onAuthSuccess: {
                    showAuthSheet = false
                    showAccountSheet = true
                }
            )
        }
    }

    // MARK: Hero

    private var heroSection: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("Новые горизонты")
                .font(.system(size: 34, weight: .bold, design: .rounded))
                .foregroundColor(warmWhite)
                .fixedSize(horizontal: false, vertical: true)

            Text("Откройте для себя мир с комфортом и новыми впечатлениями")
                .font(.system(size: 15, weight: .regular))
                .foregroundColor(mutedWarmGray)
                .lineSpacing(2)
                .fixedSize(horizontal: false, vertical: true)
        }
    }

    // MARK: My trips

    private var myTripsSection: some View {
        VStack(alignment: .leading, spacing: 14) {
            HStack {
                Text("Мои поездки")
                    .font(.system(size: 18, weight: .semibold, design: .rounded))
                    .foregroundColor(warmWhite)

                Spacer()

                Button(action: {}) {
                    Text("Все")
                        .font(.system(size: 14, weight: .semibold))
                        .foregroundColor(Color.travelBuddyOrange)
                }
                .buttonStyle(.plain)
            }

            ScrollView(.horizontal, showsIndicators: false) {
                HStack(spacing: 16) {
                    TripCard(
                        city: "Париж",
                        country: "Франция",
                        dateText: "12 Окт",
                        gradient: LinearGradient(
                            colors: [
                                Color(red: 0.25, green: 0.42, blue: 0.56),
                                Color(red: 0.12, green: 0.18, blue: 0.28)
                            ],
                            startPoint: .topLeading,
                            endPoint: .bottomTrailing
                        ),
                        symbolName: "building.columns.fill",
                        photoURL: photoURL(for: "Париж")
                    )

                    TripCard(
                        city: "Цюрих",
                        country: "Швейцария",
                        dateText: "24 Дек",
                        gradient: LinearGradient(
                            colors: [
                                Color(red: 0.16, green: 0.36, blue: 0.44),
                                Color(red: 0.08, green: 0.16, blue: 0.22)
                            ],
                            startPoint: .topLeading,
                            endPoint: .bottomTrailing
                        ),
                        symbolName: "mountain.2.fill",
                        photoURL: photoURL(for: "Цюрих")
                    )
                }
                .padding(.vertical, 4)
            }
        }
        .padding(.top, 6)
    }

    private func photoURL(for city: String) -> URL? {
        let mapped: [String: String] = [
            "Париж": "https://images.unsplash.com/photo-1502602898657-3e91760cbb34?fit=crop&w=1200&q=80&fm=jpg",
            "Paris": "https://images.unsplash.com/photo-1502602898657-3e91760cbb34?fit=crop&w=1200&q=80&fm=jpg",
            "Цюрих": "https://images.unsplash.com/photo-1469474968028-56623f02e42e?fit=crop&w=1200&q=80&fm=jpg",
            "Zurich": "https://images.unsplash.com/photo-1469474968028-56623f02e42e?fit=crop&w=1200&q=80&fm=jpg",
            "Бали": "https://images.unsplash.com/photo-1537996194471-e657df975ab4?fit=crop&w=1200&q=80&fm=jpg",
            "Bali": "https://images.unsplash.com/photo-1537996194471-e657df975ab4?fit=crop&w=1200&q=80&fm=jpg",
            "Нью-Йорк": "https://images.unsplash.com/photo-1549924231-f129b911e442?fit=crop&w=1200&q=80&fm=jpg",
            "New York": "https://images.unsplash.com/photo-1549924231-f129b911e442?fit=crop&w=1200&q=80&fm=jpg"
        ]

        guard let urlString = mapped[city] else {
            return nil
        }

        return URL(string: urlString)
    }

}
