//
//  HomeView.swift
//  Travell Buddy
//
//  Home screen with fixed layout - no clipping, consistent spacing.
//

import SwiftUI

struct HomeView: View {
    @State private var showAccountSheet: Bool = false
    @State private var showAuthSheet: Bool = false

    var body: some View {
        GeometryReader { proxy in
            let screenHeight = proxy.size.height
            let heroHeight = max(320, screenHeight * HomeStyle.Layout.heroHeightRatio)
            let safeTopInset = proxy.safeAreaInsets.top
            let safeBottomInset = proxy.safeAreaInsets.bottom

            ZStack(alignment: .bottom) {
                // Warm premium gradient background
                ZStack {
                    // Base gradient: warm brown/amber at top → deep charcoal at bottom
                    LinearGradient(
                        colors: [
                            Color(red: 45/255, green: 35/255, blue: 25/255),  // Warm brown
                            Color(red: 30/255, green: 25/255, blue: 20/255),  // Dark warm
                            HomeStyle.Colors.background,                       // #0f0f11
                            HomeStyle.Colors.background
                        ],
                        startPoint: .top,
                        endPoint: .bottom
                    )

                    // Subtle warm radial glow at top
                    RadialGradient(
                        colors: [
                            Color(red: 80/255, green: 50/255, blue: 20/255).opacity(0.3),
                            Color.clear
                        ],
                        center: .top,
                        startRadius: 0,
                        endRadius: screenHeight * 0.5
                    )
                }
                .ignoresSafeArea()

                // Main scrollable content
                ScrollView(showsIndicators: false) {
                    VStack(spacing: 0) {
                        // Hero section
                        HeroView(
                            height: heroHeight,
                            topInset: safeTopInset,
                            onAccountTap: handleAccountTap
                        )

                        // Main content sections with consistent spacing
                        VStack(spacing: HomeStyle.Layout.sectionSpacing) {
                            ActionPanelView()
                            TripsCarouselView()
                            DestinationsListView()
                        }
                        .padding(.horizontal, HomeStyle.Layout.horizontalPadding)
                        .padding(.top, HomeStyle.Layout.sectionSpacing)
                        .padding(.bottom, HomeStyle.Layout.tabBarClearance + safeBottomInset)
                    }
                }
                .ignoresSafeArea(.container, edges: .top)

                // Fixed bottom tab bar
                BottomTabBarView()
            }
        }
        .navigationBarHidden(true)
        .toolbar(.hidden, for: .tabBar)
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

    private func handleAccountTap() {
        if AuthSessionStore.shared.accessToken == nil {
            showAuthSheet = true
        } else {
            showAccountSheet = true
        }
    }
}

// MARK: - Hero View

private struct HeroView: View {
    let height: CGFloat
    let topInset: CGFloat
    let onAccountTap: () -> Void

    private let heroImageURL = URL(string: "https://lh3.googleusercontent.com/aida-public/AB6AXuBxNfel8xNT-ZR2RRsVRURBCmK8WrzCMlPDU5L8h9ejzHyqB0EGrHYBqeyn565jzBO32mtwRg_7BYuy9UwWwUWvpz29cU2MAi7FV5x5JvAAI8uoSmpZk1E_5KVOwaxckQN2EigBu6k01FP_k4mj3lL4uwGbckr5iB--bJ9bIBoBlExdNz4LJedRxh6vvC1p0XYK65OQDbe0I1pkVAwaxtsFf63raFSgtIveLltDGdP7IxS6GgVW3yh8UjPrEuRXX9P4wVejoWcVegg")

    private let avatarImageURL = URL(string: "https://lh3.googleusercontent.com/aida-public/AB6AXuDG3dTyr_v70D8AUUz8w2caF22yxaJu77ioninoTXYznSgT3UlgKUi7Lc-aBNqAmO0sp_ynibl_4Q1cTs8jZki_355EejPj_q42xQOdbHMUM6Ppf-QMghheHD5juoATwS02TXzsdSHOJfO2hyM8tnwUhJ0zO5T1vFGz2hl_y4GpttGukXAMIq_YssKqb6J0Pzb32KNe8riEihLwH1Wg_fbS2ZHHPr_fxDzdE5jPOlrBJ1tS_pnIAjBfBJf8xHWlB4qIpJt_aH2ZXns")

    var body: some View {
        ZStack {
            // Background image
            AsyncImage(url: heroImageURL) { phase in
                if let image = phase.image {
                    image
                        .resizable()
                        .scaledToFill()
                } else {
                    Color.black.opacity(0.25)
                }
            }
            .frame(height: height)
            .frame(maxWidth: .infinity)
            .clipped()

            // Gradient overlay
            LinearGradient(
                colors: [
                    Color.black.opacity(0.3),
                    Color.clear,
                    HomeStyle.Colors.background.opacity(0.8),
                    HomeStyle.Colors.background
                ],
                startPoint: .top,
                endPoint: .bottom
            )

            // Content overlay
            VStack(spacing: 0) {
                // Header row
                HeaderRow(
                    avatarURL: avatarImageURL,
                    onAccountTap: onAccountTap
                )
                .padding(.horizontal, HomeStyle.Layout.horizontalPadding)
                .padding(.top, topInset + HomeStyle.Layout.headerTopPadding)

                Spacer()

                // CTA block centered
                CTASection()
                    .padding(.bottom, 20)
            }
        }
        .frame(height: height)
        .clipShape(RoundedCornerShape(radius: HomeStyle.Radius.heroBottom, corners: [.bottomLeft, .bottomRight]))
    }
}

// MARK: - Header Row

private struct HeaderRow: View {
    let avatarURL: URL?
    let onAccountTap: () -> Void

    var body: some View {
        HStack {
            // Profile avatar button
            Button(action: onAccountTap) {
                ZStack {
                    Circle()
                        .fill(Color.white.opacity(0.1))
                        .overlay(
                            Circle()
                                .stroke(HomeStyle.Colors.glassBorder, lineWidth: 1)
                        )

                    AsyncImage(url: avatarURL) { phase in
                        if let image = phase.image {
                            image
                                .resizable()
                                .scaledToFill()
                        } else {
                            Color.white.opacity(0.08)
                        }
                    }
                    .frame(width: HomeStyle.Layout.avatarInnerSize, height: HomeStyle.Layout.avatarInnerSize)
                    .clipShape(Circle())
                }
                .frame(width: HomeStyle.Layout.avatarSize, height: HomeStyle.Layout.avatarSize)
            }
            .buttonStyle(.plain)

            Spacer()

            // Chat button
            Button(action: {}) {
                ZStack(alignment: .topTrailing) {
                    Circle()
                        .fill(Color.white.opacity(0.05))
                        .background(.ultraThinMaterial)
                        .clipShape(Circle())
                        .overlay(
                            Circle()
                                .stroke(HomeStyle.Colors.glassBorder, lineWidth: 1)
                        )
                        .frame(width: HomeStyle.Layout.avatarSize, height: HomeStyle.Layout.avatarSize)

                    Image(systemName: "bubble.left.fill")
                        .font(.system(size: 20, weight: .regular))
                        .foregroundColor(.white)
                        .frame(width: HomeStyle.Layout.avatarSize, height: HomeStyle.Layout.avatarSize)

                    Circle()
                        .fill(HomeStyle.Colors.primary)
                        .frame(width: 8, height: 8)
                        .overlay(
                            Circle()
                                .stroke(HomeStyle.Colors.badgeBorder, lineWidth: 1)
                        )
                        .offset(x: -8, y: 8)
                }
            }
            .buttonStyle(.plain)
        }
    }
}

// MARK: - CTA Section

private struct CTASection: View {
    var body: some View {
        VStack(spacing: HomeStyle.Layout.ctaIndicatorSpacing) {
            // Main CTA button
            NavigationLink(destination: NewTripView()) {
                HStack(spacing: 8) {
                    Image(systemName: "sparkles")
                        .font(.system(size: 16, weight: .semibold))
                    Text("Сгенерировать маршрут")
                        .font(.system(size: 14, weight: .bold))
                }
                .foregroundColor(.white)
                .frame(height: HomeStyle.Layout.ctaHeight)
                .padding(.horizontal, HomeStyle.Layout.ctaHorizontalPadding)
                .background(
                    Capsule()
                        .fill(HomeStyle.Colors.primary)
                        .shadow(color: HomeStyle.Shadows.primaryGlowLight, radius: 10, x: 0, y: 4)
                )
            }
            .buttonStyle(.plain)

            // Page indicators
            HStack(spacing: 6) {
                RoundedRectangle(cornerRadius: 3, style: .continuous)
                    .fill(Color.white)
                    .frame(width: 20, height: 5)

                Circle()
                    .fill(Color.white.opacity(0.3))
                    .frame(width: 5, height: 5)
                Circle()
                    .fill(Color.white.opacity(0.3))
                    .frame(width: 5, height: 5)
            }
        }
    }
}

// MARK: - Action Panel View

private struct ActionPanelView: View {
    var body: some View {
        VStack(spacing: HomeStyle.Layout.actionPanelGap) {
            // Top grid
            HStack(alignment: .top, spacing: HomeStyle.Layout.actionPanelGap) {
                // Left: Hotel card
                NavigationLink(destination: NewTripView()) {
                    HotelCard()
                }
                .buttonStyle(.plain)

                // Right: Route + Live Guide stacked
                VStack(spacing: HomeStyle.Layout.actionPanelGap) {
                    NavigationLink(destination: NewTripView()) {
                        ActionRowCard(
                            title: "Маршрут",
                            subtitle: "Построить\nумный путь",
                            systemImage: "map.fill"
                        )
                    }
                    .buttonStyle(.plain)

                    NavigationLink(destination: LiveGuideView()) {
                        ActionRowCard(
                            title: "Live-гид",
                            subtitle: "Аудио гид\nпо местам",
                            systemImage: "mic.fill"
                        )
                    }
                    .buttonStyle(.plain)
                }
            }

            // Bottom: Flight ticket button
            NavigationLink(destination: FlightTicketInputView()) {
                FlightTicketButton()
            }
            .buttonStyle(.plain)
        }
        .padding(HomeStyle.Layout.actionPanelPadding)
        .glassPanel(
            cornerRadius: HomeStyle.Radius.panel,
            blur: 24,
            fill: HomeStyle.Colors.panelFill,
            border: HomeStyle.Colors.glassBorder
        )
        .shadow(color: Color.black.opacity(0.25), radius: 16, x: 0, y: 8)
    }
}

// MARK: - Hotel Card

private struct HotelCard: View {
    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            // Icon badge
            Circle()
                .fill(HomeStyle.Colors.primary)
                .frame(width: HomeStyle.Layout.iconBadgeSizeLarge, height: HomeStyle.Layout.iconBadgeSizeLarge)
                .shadow(color: HomeStyle.Shadows.primaryGlow, radius: 6, x: 0, y: 3)
                .overlay(
                    Image(systemName: "bed.double.fill")
                        .font(.system(size: 18, weight: .semibold))
                        .foregroundColor(.white)
                )

            Spacer(minLength: 4)

            // Title
            Text("Подобрать\nотель")
                .font(.system(size: 14, weight: .semibold))
                .foregroundColor(.white)
                .lineSpacing(2)

            // Subtitle
            Text("Выгодные цены")
                .font(.system(size: 11, weight: .medium))
                .foregroundColor(HomeStyle.Colors.textMuted)
        }
        .padding(12)
        .frame(maxWidth: .infinity, alignment: .leading)
        .frame(height: HomeStyle.Layout.hotelCardHeight)
        .background(
            RoundedRectangle(cornerRadius: HomeStyle.Radius.card, style: .continuous)
                .fill(HomeStyle.Colors.panelFillStrong)
                .overlay(
                    RoundedRectangle(cornerRadius: HomeStyle.Radius.card, style: .continuous)
                        .stroke(HomeStyle.Colors.glassBorder, lineWidth: 1)
                )
        )
    }
}

// MARK: - Action Row Card

private struct ActionRowCard: View {
    let title: String
    let subtitle: String
    let systemImage: String

    var body: some View {
        HStack(spacing: 10) {
            Circle()
                .fill(HomeStyle.Colors.primary)
                .frame(width: HomeStyle.Layout.iconBadgeSizeSmall, height: HomeStyle.Layout.iconBadgeSizeSmall)
                .shadow(color: HomeStyle.Shadows.primaryGlow, radius: 6, x: 0, y: 3)
                .overlay(
                    Image(systemName: systemImage)
                        .font(.system(size: 14, weight: .semibold))
                        .foregroundColor(.white)
                )

            VStack(alignment: .leading, spacing: 1) {
                Text(title)
                    .font(.system(size: 13, weight: .semibold))
                    .foregroundColor(.white)
                Text(subtitle)
                    .font(.system(size: 9, weight: .medium))
                    .foregroundColor(HomeStyle.Colors.textMuted)
                    .lineSpacing(1)
            }

            Spacer(minLength: 0)
        }
        .padding(.horizontal, 12)
        .padding(.vertical, 10)
        .frame(maxWidth: .infinity)
        .background(
            RoundedRectangle(cornerRadius: HomeStyle.Radius.card, style: .continuous)
                .fill(HomeStyle.Colors.panelFillStrong)
                .overlay(
                    RoundedRectangle(cornerRadius: HomeStyle.Radius.card, style: .continuous)
                        .stroke(HomeStyle.Colors.glassBorder, lineWidth: 1)
                )
        )
    }
}

// MARK: - Flight Ticket Button

private struct FlightTicketButton: View {
    var body: some View {
        HStack(spacing: 12) {
            Circle()
                .fill(HomeStyle.Colors.primary)
                .frame(width: HomeStyle.Layout.iconBadgeSizeSmall, height: HomeStyle.Layout.iconBadgeSizeSmall)
                .shadow(color: HomeStyle.Shadows.primaryGlow, radius: 6, x: 0, y: 3)
                .overlay(
                    Image(systemName: "airplane")
                        .font(.system(size: 14, weight: .semibold))
                        .foregroundColor(.white)
                )

            Text("Добавить билет на самолет")
                .font(.system(size: 13, weight: .semibold))
                .foregroundColor(.white)

            Spacer()
        }
        .padding(.horizontal, 14)
        .frame(height: HomeStyle.Layout.bottomButtonHeight)
        .background(
            RoundedRectangle(cornerRadius: HomeStyle.Radius.card, style: .continuous)
                .fill(HomeStyle.Colors.panelFillStrong)
                .overlay(
                    RoundedRectangle(cornerRadius: HomeStyle.Radius.card, style: .continuous)
                        .stroke(HomeStyle.Colors.glassBorder, lineWidth: 1)
                )
        )
    }
}

// MARK: - Trips Carousel View

private struct TripsCarouselView: View {
    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            // Header row - same padding as parent
            HStack {
                Text("Мои поездки")
                    .font(.system(size: 17, weight: .semibold))
                    .foregroundColor(.white)
                Spacer()
                Button(action: {}) {
                    Text("Все")
                        .font(.system(size: 13, weight: .semibold))
                        .foregroundColor(HomeStyle.Colors.primary)
                }
            }

            // Horizontal scroll
            ScrollView(.horizontal, showsIndicators: false) {
                HStack(spacing: 12) {
                    TripCardView(
                        city: "Париж",
                        country: "Франция",
                        dates: "12-18 Ноя",
                        imageURL: URL(string: "https://lh3.googleusercontent.com/aida-public/AB6AXuAAcZ7xga_fZsjeYMNZjIX2DlgsqR66RkXtEyKeN6lXqGK2lDxHhizCMlLK1aacJ98mpdz7W16dxuQEAo6r4cPQRy7qtSlPWXOgUaXsdWWKG2xsRI_rRGYarOaYGWF9ylDWe7CSnOlfLL2n1xt9Q4trlkv3rWvTK0T_N88o2QEMYEbbRnagAxOCOzt77y-F7U2AGPv8rk5KT08cMGjuSpwnMag7zKKxAI4HEWJLPBjQI6TbEAQmXyWpPNsM94VGTHwdkeF_MXy6F5E")
                    )
                    TripCardView(
                        city: "Цюрих",
                        country: "Швейцария",
                        dates: "05-10 Дек",
                        imageURL: URL(string: "https://lh3.googleusercontent.com/aida-public/AB6AXuC9NNa-Sr26bIy5-IMAo0JjMzUhxeQuIaSg7IrV3jdJBOk5duymOUGc1vDMEvWF-PT0h-JGfzTPLfgAyHrZspn7KRMZ1iTB8Cb6Qg4wTUaOAS4Yi_s53AmTCSrN8uZkv8r7P7aSfUSpZWcdm7aDpsQ952Q1zBoslc5AtY4s96aYkE2DVQj2rDEC6CALRPAhd4CF8OYGNINGB6LGzLbviULEAPjwFTukN24T9yTQg5mxN8N3OiCgJy0Y2Ytp4zGUQztWKTj0NkrRyvg")
                    )
                }
                .padding(.horizontal, HomeStyle.Layout.horizontalPadding)
            }
            .padding(.horizontal, -HomeStyle.Layout.horizontalPadding)
        }
    }
}

// MARK: - Trip Card View

private struct TripCardView: View {
    let city: String
    let country: String
    let dates: String
    let imageURL: URL?

    var body: some View {
        ZStack {
            // Background image
            AsyncImage(url: imageURL) { phase in
                if let image = phase.image {
                    image
                        .resizable()
                        .scaledToFill()
                } else {
                    Color.black.opacity(0.3)
                }
            }
            .frame(width: HomeStyle.Layout.tripCardWidth, height: HomeStyle.Layout.tripCardHeight)
            .clipped()

            // Gradient overlay
            LinearGradient(
                colors: [
                    Color.black.opacity(0.85),
                    Color.black.opacity(0.2),
                    Color.clear
                ],
                startPoint: .bottom,
                endPoint: .top
            )

            // Date chip
            VStack {
                HStack {
                    Spacer()
                    Text(dates)
                        .font(.system(size: 10, weight: .bold))
                        .foregroundColor(.white.opacity(0.9))
                        .padding(.horizontal, 8)
                        .padding(.vertical, 4)
                        .background(
                            Capsule()
                                .fill(Color.white.opacity(0.1))
                                .background(.ultraThinMaterial)
                                .clipShape(Capsule())
                        )
                        .overlay(
                            Capsule()
                                .stroke(HomeStyle.Colors.glassBorder, lineWidth: 1)
                        )
                        .clipShape(Capsule())
                }
                .padding(.top, 12)
                .padding(.trailing, 12)

                Spacer()
            }

            // City and country
            VStack {
                Spacer()
                HStack {
                    VStack(alignment: .leading, spacing: 2) {
                        Text(city)
                            .font(.system(size: 18, weight: .bold))
                            .foregroundColor(.white)
                        Text(country)
                            .font(.system(size: 11, weight: .medium))
                            .foregroundColor(HomeStyle.Colors.textMutedSoft)
                    }
                    Spacer()
                }
                .padding(.leading, 16)
                .padding(.bottom, 16)
            }
        }
        .frame(width: HomeStyle.Layout.tripCardWidth, height: HomeStyle.Layout.tripCardHeight)
        .clipShape(RoundedRectangle(cornerRadius: HomeStyle.Radius.card, style: .continuous))
        .overlay(
            RoundedRectangle(cornerRadius: HomeStyle.Radius.card, style: .continuous)
                .stroke(HomeStyle.Colors.glassBorder, lineWidth: 1)
        )
    }
}

// MARK: - Destinations List View

private struct DestinationsListView: View {
    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("Исследуй")
                .font(.system(size: 17, weight: .semibold))
                .foregroundColor(.white)

            VStack(spacing: 10) {
                DestinationRowView(
                    title: "Швейцария",
                    rating: "4.9",
                    tags: ["Природа", "Отдых"],
                    imageURL: URL(string: "https://lh3.googleusercontent.com/aida-public/AB6AXuD4nCbCMMA7yrtC6mQn7rmEqRqwJr2kHzgfwFowh5u37kIGzLO6_4uhpBD8sIJfWlRTSCAV9A9PhCuFZBOc1GVga1BEKCkexTVnDTu1u4fyKFiSHFUkReLkziodIoCFNzjmsramSMW5pqz2mRD7j7-9LgPqX7GLn10gz9jS-aSFMwhzyDj2dYS6aQEoLp23NMqkywR8rYAidmFlTIvXRU5QHx8cWWcha5w6xvS0H0tUcmiPZWt6_4-nly2jD6UmdhuuvCVnIs03A1w")
                )
                DestinationRowView(
                    title: "Париж",
                    rating: "4.8",
                    tags: ["Еда", "История"],
                    imageURL: URL(string: "https://lh3.googleusercontent.com/aida-public/AB6AXuDTrAkDILjO_rGFjkIkrhXldkvXTPfDJJ7sbdpzdCySsb7oY-kZEz59AXEclMDUhuFI3N1LuVdd8dRVJo_aVdh8oZABrGOcQ4JCLNAholPd-vJGoMlBgWv_-Yp4huY7X4QVS3nWdHfqVxa7ribXQ8qT28o26w-ygkF30gOCo6-EfdXjhU8qnqvtIqYNsSv0hZz-_3p5-d3pqeL9pABIs4E_Rlunfp3YUrK2eIjgsJKBsjy29Yt01JCelWM2Vo2GdBsgTgs50fNxdQs")
                )
            }
        }
    }
}

// MARK: - Destination Row View

private struct DestinationRowView: View {
    let title: String
    let rating: String
    let tags: [String]
    let imageURL: URL?

    var body: some View {
        HStack(spacing: 12) {
            // Thumbnail
            AsyncImage(url: imageURL) { phase in
                if let image = phase.image {
                    image
                        .resizable()
                        .scaledToFill()
                } else {
                    Color.white.opacity(0.08)
                }
            }
            .frame(width: HomeStyle.Layout.destinationThumbSize, height: HomeStyle.Layout.destinationThumbSize)
            .clipShape(RoundedRectangle(cornerRadius: 14, style: .continuous))
            .overlay(
                RoundedRectangle(cornerRadius: 14, style: .continuous)
                    .stroke(HomeStyle.Colors.glassBorder, lineWidth: 1)
            )

            // Content
            VStack(alignment: .leading, spacing: 6) {
                HStack {
                    Text(title)
                        .font(.system(size: 15, weight: .bold))
                        .foregroundColor(.white)
                        .lineLimit(1)
                    Spacer()
                    HStack(spacing: 3) {
                        Image(systemName: "star.fill")
                            .font(.system(size: 12, weight: .bold))
                            .foregroundColor(HomeStyle.Colors.primary)
                        Text(rating)
                            .font(.system(size: 12, weight: .bold))
                            .foregroundColor(HomeStyle.Colors.primary)
                    }
                }

                HStack(spacing: 6) {
                    ForEach(tags, id: \.self) { tag in
                        Text(tag)
                            .font(.system(size: 10, weight: .medium))
                            .foregroundColor(HomeStyle.Colors.textMutedSoft)
                            .padding(.horizontal, 8)
                            .padding(.vertical, 3)
                            .background(
                                Capsule()
                                    .fill(Color.white.opacity(0.08))
                                    .overlay(
                                        Capsule()
                                            .stroke(Color.white.opacity(0.08), lineWidth: 1)
                                    )
                            )
                    }
                }
            }
        }
        .padding(12)
        .glassPanel(
            cornerRadius: 20,
            blur: 24,
            fill: HomeStyle.Colors.panelFill,
            border: HomeStyle.Colors.glassBorder
        )
        .shadow(color: Color.black.opacity(0.15), radius: 8, x: 0, y: 4)
    }
}

// MARK: - Bottom Tab Bar View

private struct BottomTabBarView: View {
    var body: some View {
        HStack {
            TabBarItem(title: "Главная", systemImage: "house.fill", isActive: true)
            TabBarItem(title: "Поиск", systemImage: "magnifyingglass", isActive: false)
            TabBarItem(title: "Сохранено", systemImage: "bookmark", isActive: false)
            TabBarItem(title: "Профиль", systemImage: "person", isActive: false)
        }
        .padding(.horizontal, HomeStyle.Layout.tabBarHorizontalPadding)
        .padding(.top, HomeStyle.Layout.tabBarTopPadding)
        .padding(.bottom, HomeStyle.Layout.tabBarBottomPadding)
        .frame(maxWidth: .infinity)
        .background(
            ZStack {
                HomeStyle.Colors.tabBarFill
                    .background(.ultraThinMaterial)
            }
            .clipShape(TopRoundedRectangle(radius: HomeStyle.Radius.tabBar))
            .overlay(
                TopRoundedRectangle(radius: HomeStyle.Radius.tabBar)
                    .stroke(HomeStyle.Colors.tabBarBorder, lineWidth: 1)
            )
        )
        .ignoresSafeArea(.container, edges: .bottom)
    }
}

// MARK: - Tab Bar Item

private struct TabBarItem: View {
    let title: String
    let systemImage: String
    let isActive: Bool

    var body: some View {
        VStack(spacing: 4) {
            Image(systemName: systemImage)
                .font(.system(size: HomeStyle.Layout.tabIconSize, weight: isActive ? .semibold : .regular))
                .symbolVariant(isActive ? .fill : .none)
            Text(title)
                .font(.system(size: 10, weight: .medium))
        }
        .foregroundColor(isActive ? HomeStyle.Colors.primary : HomeStyle.Colors.textMuted)
        .frame(maxWidth: .infinity)
        .frame(minHeight: 44) // Minimum tap target
    }
}
