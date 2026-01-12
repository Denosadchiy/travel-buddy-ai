//
//  PlaceDetailsView.swift
//  Travell Buddy
//

import SwiftUI
import MapKit

struct PlaceDetailsView: View {
    @Environment(\.dismiss) private var dismiss
    @Environment(\.openURL) private var openURL
    @StateObject private var viewModel: PlaceDetailsViewModel
    @StateObject private var locationManager = LocationManager()
    @State private var selectedPhotoIndex: Int = 0
    @State private var showingNoteEditor: Bool = false
    @State private var isShowingAllDescription: Bool = false
    @State private var descriptionNeedsExpand: Bool = false

    private let ctaHeight: CGFloat = 64

    /// Hero image height - capped at 380pt but scales down on smaller screens
    private var heroHeight: CGFloat {
        min(380, UIScreen.main.bounds.height * 0.42)
    }

    init(placeId: String, fallbackPlace: Place? = nil) {
        _viewModel = StateObject(wrappedValue: PlaceDetailsViewModel(placeId: placeId, fallbackPlace: fallbackPlace))
    }

    var body: some View {
        ZStack {
            backgroundLayer
            ScrollView(showsIndicators: false) {
                VStack(spacing: 12) {
                    heroSection
                    contentSection
                }
                .frame(maxWidth: .infinity, alignment: .leading)
            }
        }
        .safeAreaInset(edge: .bottom) {
            bottomBar
        }
        .ignoresSafeArea(edges: .top)
        .task {
            viewModel.loadDetails()
            locationManager.start()
        }
        .onReceive(locationManager.$lastLocation) { location in
            viewModel.updateDistance(from: location)
        }
        .sheet(isPresented: $showingNoteEditor) {
            NoteEditorSheet(noteText: $viewModel.noteText)
        }
    }

    private var backgroundLayer: some View {
        LinearGradient(
            colors: [
                Color(red: 0.14, green: 0.08, blue: 0.06),
                Color(red: 0.10, green: 0.06, blue: 0.04)
            ],
            startPoint: .top,
            endPoint: .bottom
        )
        .ignoresSafeArea()
    }

    private var heroSection: some View {
        let photos = viewModel.details?.photos ?? []
        let heroImageURL = photos.first?.url

        return GeometryReader { proxy in
            let width = proxy.size.width

            ZStack(alignment: .topLeading) {
                // Hero container: image + gradient + overlay
                ZStack(alignment: .bottomLeading) {
                    // Image layer
                    AsyncImage(url: heroImageURL) { phase in
                        switch phase {
                        case .success(let image):
                            image
                                .resizable()
                                .scaledToFill()
                        case .failure:
                            placeholderGradient
                        case .empty:
                            placeholderGradient
                                .overlay(ProgressView().tint(.white.opacity(0.6)))
                        @unknown default:
                            placeholderGradient
                        }
                    }
                    .frame(width: width, height: heroHeight)
                    .clipped()

                    // Bottom gradient layer (aligned to bottom)
                    LinearGradient(
                        colors: [
                            Color.clear,
                            Color.black.opacity(0.2),
                            Color.black.opacity(0.5),
                            Color(red: 0.14, green: 0.08, blue: 0.06).opacity(0.95)
                        ],
                        startPoint: .top,
                        endPoint: .bottom
                    )
                    .frame(width: width, height: heroHeight * 0.6)

                    // Overlay content - chips + title + metadata
                    VStack(alignment: .leading, spacing: 10) {
                        heroChips
                        heroTitleText
                        heroMetadataRow
                    }
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .padding(.horizontal, 20)
                    .padding(.bottom, 16)
                    .frame(width: width, alignment: .leading)
                }
                .frame(width: width, height: heroHeight)
                // Single clipShape on the outer container - clips image AND overlay uniformly
                .clipShape(
                    UnevenRoundedRectangle(
                        topLeadingRadius: 0,
                        bottomLeadingRadius: 28,
                        bottomTrailingRadius: 28,
                        topTrailingRadius: 0,
                        style: .continuous
                    )
                )

                heroTopNav
                    .frame(width: width, alignment: .topLeading)
            }
            .frame(width: width, height: heroHeight, alignment: .topLeading)
        }
        .frame(height: heroHeight)
    }

    private var placeholderGradient: some View {
        LinearGradient(
            colors: [
                Color(red: 0.20, green: 0.15, blue: 0.12),
                Color(red: 0.14, green: 0.10, blue: 0.08)
            ],
            startPoint: .topLeading,
            endPoint: .bottomTrailing
        )
    }

    private var heroTopNav: some View {
        HStack(spacing: 12) {
            glassIconButton(systemName: "arrow.backward") {
                dismiss()
            }
            Spacer()
            if let shareURL = viewModel.details?.googleMapsURL {
                ShareLink(item: shareURL) {
                    glassIcon(systemName: "square.and.arrow.up")
                }
            } else {
                glassIconButton(systemName: "square.and.arrow.up") {}
            }
            glassIconButton(systemName: viewModel.isSaved ? "heart.fill" : "heart") {
                viewModel.isSaved.toggle()
            }
        }
        .padding(.horizontal, 20)
        .padding(.top, 20)
    }

    private var heroChips: some View {
        let chips = [viewModel.details?.categoryLabel]
            .compactMap { $0 }
            + viewModel.highlightChips()

        return Group {
            if !chips.isEmpty {
                ScrollView(.horizontal, showsIndicators: false) {
                    HStack(spacing: 8) {
                        ForEach(Array(chips.enumerated()), id: \.offset) { index, chip in
                            Text(chip)
                                .font(.system(size: 11, weight: .semibold))
                                .foregroundColor(index == 0 ? .white : Color.white.opacity(0.9))
                                .padding(.horizontal, 14)
                                .padding(.vertical, 8)
                                .lineLimit(1)
                                .background(
                                    Capsule()
                                        .fill(index == 0 ? Color.travelBuddyOrange.opacity(0.9) : Color.white.opacity(0.12))
                                        .background(.ultraThinMaterial, in: Capsule())
                                )
                        }
                    }
                    .padding(.vertical, 2)
                }
                .frame(maxWidth: .infinity, alignment: .leading)
            }
        }
    }

    private var heroTitleText: some View {
        let details = viewModel.details

        // Simple VStack - alignment handled by parent, no nested frames
        return Text(details?.name ?? viewModel.fallbackPlace?.name ?? "Место")
            .font(.system(size: 28, weight: .bold))
            .foregroundColor(.white)
            .lineLimit(3)
            .minimumScaleFactor(0.85)
            .truncationMode(.tail)
    }

    @ViewBuilder
    private var heroMetadataRow: some View {
        let details = viewModel.details
        let ratingText = details?.rating.map { String(format: "%.1f", $0) }
        let reviewsCount = details?.reviewsCount
        let price = details?.priceLevel?.displayText
        let distanceText = viewModel.distanceKm.map { String(format: "%.1f км", $0) }

        let hasMetadata = ratingText != nil || reviewsCount != nil || price != nil || distanceText != nil

        if hasMetadata {
            HStack(spacing: 8) {
                if let ratingText {
                    HStack(spacing: 5) {
                        Image(systemName: "star.fill")
                            .font(.system(size: 12, weight: .semibold))
                            .foregroundColor(Color.travelBuddyOrange)
                        Text(ratingText)
                            .font(.system(size: 14, weight: .bold))
                            .foregroundColor(.white)
                    }
                    .padding(.horizontal, 10)
                    .padding(.vertical, 6)
                    .background(
                        RoundedRectangle(cornerRadius: 10, style: .continuous)
                            .fill(Color.white.opacity(0.15))
                    )
                }

                if let reviewsCount {
                    Text("\(reviewsCount) отзывов")
                        .font(.system(size: 12, weight: .medium))
                        .foregroundColor(Color.white.opacity(0.75))
                        .padding(.horizontal, 8)
                        .padding(.vertical, 6)
                        .background(
                            RoundedRectangle(cornerRadius: 10, style: .continuous)
                                .fill(Color.white.opacity(0.08))
                        )
                }

                if let price {
                    Text(price)
                        .font(.system(size: 12, weight: .semibold))
                        .foregroundColor(.white.opacity(0.9))
                        .padding(.horizontal, 8)
                        .padding(.vertical, 6)
                        .background(
                            RoundedRectangle(cornerRadius: 10, style: .continuous)
                                .fill(Color.white.opacity(0.08))
                        )
                }

                if let distanceText {
                    HStack(spacing: 4) {
                        Image(systemName: "location.fill")
                            .font(.system(size: 10, weight: .semibold))
                        Text(distanceText)
                            .font(.system(size: 12, weight: .medium))
                    }
                    .foregroundColor(.white.opacity(0.75))
                    .padding(.horizontal, 8)
                    .padding(.vertical, 6)
                    .background(
                        RoundedRectangle(cornerRadius: 10, style: .continuous)
                            .fill(Color.white.opacity(0.08))
                    )
                }
            }
        }
    }

    private var contentSection: some View {
        VStack(alignment: .leading, spacing: 16) {
            quickStats
            descriptionCard
            gallerySection
            amenitiesSection
            locationSection
            reviewsSection
            if viewModel.isLoading {
                loadingCard
            }
            if let error = viewModel.errorMessage {
                errorCard(message: error)
            }
        }
        .padding(.horizontal, 16)
    }

    @ViewBuilder
    private var quickStats: some View {
        let details = viewModel.details

        // Build stats array with only meaningful data
        let stats = buildQuickStats(details: details)

        // If no stats and still loading, show nothing (loading indicator is elsewhere)
        // If no stats and not loading, hide completely
        if !stats.isEmpty {
            ScrollView(.horizontal, showsIndicators: false) {
                HStack(spacing: 10) {
                    ForEach(stats) { stat in
                        quickStatCard(stat: stat)
                    }
                }
                .padding(.vertical, 2) // Prevent clipping
            }
        }
    }

    private func buildQuickStats(details: PlaceDetailsViewData?) -> [QuickStat] {
        var stats: [QuickStat] = []

        // Opening status - only show if we have actual data
        if let isOpen = details?.isOpenNow {
            stats.append(QuickStat(
                title: isOpen ? "Открыто" : "Закрыто",
                subtitle: details?.nextCloseTime ?? "",
                icon: "clock",
                isPrimary: isOpen
            ))
        }

        // ETA - show if available
        if let eta = viewModel.etaMinutes {
            stats.append(QuickStat(
                title: "Маршрут",
                subtitle: "\(eta) мин",
                icon: "location.north.line",
                isPrimary: false
            ))
        }

        // Phone - only show if available
        if let phone = details?.phone, !phone.isEmpty {
            stats.append(QuickStat(
                title: "Телефон",
                subtitle: "Позвонить",
                icon: "phone",
                isPrimary: false
            ))
        }

        return stats
    }

    private func quickStatCard(stat: QuickStat) -> some View {
        VStack(spacing: 6) {
            Circle()
                .fill(Color.white.opacity(0.08))
                .frame(width: 28, height: 28)
                .overlay(
                    Image(systemName: stat.icon)
                        .font(.system(size: 12, weight: .semibold))
                        .foregroundColor(stat.isPrimary ? Color.green : Color.travelBuddyOrange)
                )
            VStack(spacing: 2) {
                Text(stat.title.uppercased())
                    .font(.system(size: 9, weight: .bold))
                    .foregroundColor(Color.white.opacity(0.55))
                    .lineLimit(1)
                if !stat.subtitle.isEmpty {
                    Text(stat.subtitle)
                        .font(.system(size: 12, weight: .bold))
                        .foregroundColor(.white)
                        .lineLimit(1)
                        .minimumScaleFactor(0.8)
                }
            }
        }
        .frame(minWidth: 80) // Adaptive width, no maxWidth constraint
        .padding(.vertical, 12)
        .padding(.horizontal, 12)
        .background(glassCard)
    }

    private var descriptionCard: some View {
        let text = descriptionText
        let needsExpand = text.count > 200 // Approximate threshold for 4 lines

        return VStack(alignment: .leading, spacing: 12) {
            Text("О месте")
                .font(.system(size: 18, weight: .bold))
                .foregroundColor(.white)
            Text(text)
                .font(.system(size: 14))
                .foregroundColor(Color.white.opacity(0.75))
                .lineSpacing(3)
                .lineLimit(isShowingAllDescription ? nil : 4)
                .fixedSize(horizontal: false, vertical: isShowingAllDescription)

            if needsExpand {
                Button {
                    withAnimation(.easeInOut(duration: 0.25)) {
                        isShowingAllDescription.toggle()
                    }
                } label: {
                    HStack(spacing: 4) {
                        Text(isShowingAllDescription ? "Свернуть" : "Читать далее")
                            .font(.system(size: 12, weight: .bold))
                        Image(systemName: isShowingAllDescription ? "chevron.up" : "chevron.down")
                            .font(.system(size: 10, weight: .semibold))
                    }
                    .foregroundColor(Color.travelBuddyOrange)
                    .padding(.horizontal, 12)
                    .padding(.vertical, 6)
                    .background(
                        Capsule()
                            .fill(Color.travelBuddyOrange.opacity(0.15))
                    )
                }
            }
        }
        .padding(16)
        .background(glassCard)
    }

    private var gallerySection: some View {
        guard let photos = viewModel.details?.photos, !photos.isEmpty else {
            return AnyView(EmptyView())
        }

        return AnyView(
            VStack(alignment: .leading, spacing: 12) {
                HStack {
                    Text("Фотографии")
                        .font(.system(size: 18, weight: .bold))
                        .foregroundColor(.white)
                    Spacer()
                    Text("Все (\(photos.count))")
                        .font(.system(size: 13, weight: .semibold))
                        .foregroundColor(Color.travelBuddyOrange)
                }
                ScrollView(.horizontal, showsIndicators: false) {
                    HStack(spacing: 12) {
                        ForEach(photos) { photo in
                            AsyncImage(url: photo.url) { phase in
                                switch phase {
                                case .success(let image):
                                    image
                                        .resizable()
                                        .scaledToFill()
                                case .failure:
                                    Color.white.opacity(0.1)
                                case .empty:
                                    Color.white.opacity(0.08)
                                @unknown default:
                                    Color.white.opacity(0.08)
                                }
                            }
                            .frame(width: 140, height: 190)
                            .clipShape(RoundedRectangle(cornerRadius: 20, style: .continuous))
                            .overlay(
                                RoundedRectangle(cornerRadius: 20, style: .continuous)
                                    .stroke(Color.white.opacity(0.1), lineWidth: 1)
                            )
                        }
                    }
                }
            }
        )
    }

    private var amenitiesSection: some View {
        guard let amenities = viewModel.details?.amenities, !amenities.isEmpty else {
            return AnyView(EmptyView())
        }

        let shownAmenities = Array(amenities.prefix(4))

        return AnyView(
            VStack(alignment: .leading, spacing: 16) {
                Text("Удобства")
                    .font(.system(size: 20, weight: .bold))
                    .foregroundColor(.white)
                LazyVGrid(columns: Array(repeating: GridItem(.flexible(), spacing: 12), count: 2), spacing: 16) {
                    ForEach(shownAmenities, id: \.self) { amenity in
                        HStack(spacing: 12) {
                            Circle()
                                .fill(Color.white.opacity(0.08))
                                .frame(width: 40, height: 40)
                                .overlay(
                                    Image(systemName: "checkmark")
                                        .font(.system(size: 16, weight: .bold))
                                        .foregroundColor(Color.travelBuddyOrange)
                                )
                            Text(amenity)
                                .font(.system(size: 14, weight: .medium))
                                .foregroundColor(Color.white.opacity(0.85))
                            Spacer()
                        }
                    }
                }
            }
            .padding(20)
            .background(glassCard)
        )
    }

    private var locationSection: some View {
        guard let details = viewModel.details else {
            return AnyView(EmptyView())
        }

        return AnyView(
            VStack(spacing: 12) {
                Map(coordinateRegion: .constant(MKCoordinateRegion(
                    center: details.coordinate,
                    span: MKCoordinateSpan(latitudeDelta: 0.01, longitudeDelta: 0.01)
                )), annotationItems: [details]) { place in
                    MapAnnotation(coordinate: place.coordinate) {
                        VStack(spacing: 0) {
                            Circle()
                                .fill(Color.travelBuddyOrange)
                                .frame(width: 44, height: 44)
                                .overlay(
                                    Image(systemName: "fork.knife")
                                        .font(.system(size: 18, weight: .bold))
                                        .foregroundColor(.white)
                                )
                            Rectangle()
                                .fill(Color.travelBuddyOrange)
                                .frame(width: 10, height: 10)
                                .rotationEffect(.degrees(45))
                                .offset(y: -4)
                        }
                    }
                }
                .frame(height: 180)
                .clipShape(RoundedRectangle(cornerRadius: 24, style: .continuous))
                .overlay(
                    RoundedRectangle(cornerRadius: 24, style: .continuous)
                        .stroke(Color.white.opacity(0.1), lineWidth: 1)
                )

                HStack(alignment: .top, spacing: 12) {
                    VStack(alignment: .leading, spacing: 4) {
                        if let address = details.address, !address.isEmpty {
                            Text(address)
                                .font(.system(size: 14, weight: .semibold))
                                .foregroundColor(.white)
                                .lineLimit(2)
                                .minimumScaleFactor(0.85)
                                .fixedSize(horizontal: false, vertical: true)
                        } else {
                            Text("Адрес не указан")
                                .font(.system(size: 14, weight: .medium))
                                .foregroundColor(.white.opacity(0.6))
                        }
                    }
                    .frame(maxWidth: .infinity, alignment: .leading)

                    Button {
                        if let url = details.googleMapsURL {
                            openURL(url)
                        }
                    } label: {
                        Circle()
                            .fill(Color.travelBuddyOrange.opacity(0.2))
                            .frame(width: 44, height: 44)
                            .overlay(
                                Image(systemName: "paperplane.fill")
                                    .font(.system(size: 16, weight: .semibold))
                                    .foregroundColor(Color.travelBuddyOrange)
                            )
                    }
                }
                .padding(.horizontal, 4)
                .padding(.bottom, 2)
            }
            .padding(14)
            .background(glassCard)
        )
    }

    private var reviewsSection: some View {
        guard let details = viewModel.details, !details.reviews.isEmpty else {
            return AnyView(EmptyView())
        }

        return AnyView(
            VStack(alignment: .leading, spacing: 16) {
                HStack {
                    Text("Отзывы")
                        .font(.system(size: 20, weight: .bold))
                        .foregroundColor(.white)
                    Spacer()
                    Text("Смотреть все")
                        .font(.system(size: 13, weight: .bold))
                        .foregroundColor(Color.travelBuddyOrange)
                }

                if let rating = details.rating, let reviewsCount = details.reviewsCount {
                    HStack(spacing: 16) {
                        VStack(spacing: 6) {
                            Text(String(format: "%.1f", rating))
                                .font(.system(size: 40, weight: .bold))
                                .foregroundColor(.white)
                            HStack(spacing: 2) {
                                ForEach(0..<5) { index in
                                    Image(systemName: index < 4 ? "star.fill" : "star.leadinghalf.filled")
                                        .font(.system(size: 12))
                                        .foregroundColor(Color.travelBuddyOrange)
                                }
                            }
                            Text("\(reviewsCount) оценок")
                                .font(.system(size: 11, weight: .medium))
                                .foregroundColor(Color.white.opacity(0.6))
                        }

                        VStack(spacing: 8) {
                            ratingBar(label: "5", value: 0.85)
                            ratingBar(label: "4", value: 0.1)
                            ratingBar(label: "3", value: 0.03)
                            ratingBar(label: "2", value: 0.01, dimmed: true)
                            ratingBar(label: "1", value: 0.01, dimmed: true)
                        }
                    }
                }

                if let review = details.reviews.first {
                    VStack(alignment: .leading, spacing: 10) {
                        HStack(spacing: 12) {
                            Circle()
                                .fill(Color.white.opacity(0.2))
                                .frame(width: 40, height: 40)
                            VStack(alignment: .leading, spacing: 2) {
                                Text(review.authorName)
                                    .font(.system(size: 14, weight: .bold))
                                    .foregroundColor(.white)
                                Text(review.relativeTime)
                                    .font(.system(size: 11, weight: .medium))
                                    .foregroundColor(Color.white.opacity(0.6))
                            }
                            Spacer()
                            HStack(spacing: 4) {
                                Image(systemName: "star.fill")
                                    .font(.system(size: 12))
                                    .foregroundColor(Color.travelBuddyOrange)
                                Text(String(format: "%.1f", review.rating))
                                    .font(.system(size: 12, weight: .bold))
                                    .foregroundColor(.white)
                            }
                            .padding(.horizontal, 8)
                            .padding(.vertical, 4)
                            .background(
                                RoundedRectangle(cornerRadius: 8, style: .continuous)
                                    .fill(Color.white.opacity(0.1))
                            )
                        }
                        Text(review.text)
                            .font(.system(size: 14))
                            .foregroundColor(Color.white.opacity(0.8))
                    }
                }
            }
            .padding(20)
            .background(glassCard)
        )
    }

    private var loadingCard: some View {
        HStack(spacing: 12) {
            ProgressView()
            Text("Загружаем детали места…")
                .font(.system(size: 14, weight: .medium))
                .foregroundColor(.white.opacity(0.7))
        }
        .padding(16)
        .background(glassCard)
    }

    private func errorCard(message: String) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("Ошибка")
                .font(.system(size: 16, weight: .bold))
                .foregroundColor(.white)
            Text(message)
                .font(.system(size: 13))
                .foregroundColor(.white.opacity(0.7))
            Button("Повторить") {
                viewModel.retry()
            }
            .font(.system(size: 13, weight: .bold))
            .foregroundColor(Color.travelBuddyOrange)
        }
        .padding(16)
        .background(glassCard)
    }

    private var bottomBar: some View {
        VStack(spacing: 0) {
            // Gradient fade at top
            LinearGradient(
                colors: [
                    Color(red: 0.14, green: 0.08, blue: 0.06).opacity(0.0),
                    Color(red: 0.14, green: 0.08, blue: 0.06)
                ],
                startPoint: .top,
                endPoint: .bottom
            )
            .frame(height: 20)

            // Content area with solid background
            HStack(spacing: 12) {
                Button {
                    if let url = viewModel.details?.website ?? viewModel.details?.googleMapsURL {
                        openURL(url)
                    }
                } label: {
                    HStack(spacing: 8) {
                        Image(systemName: "calendar")
                            .font(.system(size: 15, weight: .semibold))
                        Text("Сайт")
                            .font(.system(size: 15, weight: .bold))
                    }
                    .foregroundColor(.white)
                    .frame(maxWidth: .infinity)
                    .frame(height: ctaHeight)
                    .background(
                        Capsule()
                            .fill(Color.travelBuddyOrange)
                    )
                }

                Button {
                    showingNoteEditor = true
                } label: {
                    Circle()
                        .fill(Color.white.opacity(0.12))
                        .frame(width: ctaHeight, height: ctaHeight)
                        .overlay(
                            Image(systemName: "message.fill")
                                .font(.system(size: 18, weight: .semibold))
                                .foregroundColor(.white)
                        )
                }
            }
            .padding(.horizontal, 16)
            .padding(.top, 4)
            .background(Color(red: 0.14, green: 0.08, blue: 0.06))
        }
    }

    private var glassCard: some View {
        RoundedRectangle(cornerRadius: 28, style: .continuous)
            .fill(Color(red: 0.14, green: 0.10, blue: 0.08).opacity(0.6))
            .background(.ultraThinMaterial, in: RoundedRectangle(cornerRadius: 28, style: .continuous))
            .overlay(
                RoundedRectangle(cornerRadius: 28, style: .continuous)
                    .stroke(Color.white.opacity(0.08), lineWidth: 1)
            )
    }

    private func ratingBar(label: String, value: CGFloat, dimmed: Bool = false) -> some View {
        HStack(spacing: 8) {
            Text(label)
                .font(.system(size: 11, weight: .bold))
                .foregroundColor(dimmed ? Color.white.opacity(0.4) : .white)
                .frame(width: 10)
            GeometryReader { proxy in
                ZStack(alignment: .leading) {
                    Capsule()
                        .fill(Color.white.opacity(0.08))
                    Capsule()
                        .fill(Color.travelBuddyOrange.opacity(dimmed ? 0.4 : 1.0))
                        .frame(width: proxy.size.width * value)
                }
            }
            .frame(height: 6)
        }
        .frame(height: 8)
    }

    private func glassIcon(systemName: String) -> some View {
        Image(systemName: systemName)
            .font(.system(size: 16, weight: .semibold))
            .foregroundColor(.white)
            .frame(width: 48, height: 48)
            .background(Color.black.opacity(0.25), in: Circle())
            .overlay(
                Circle()
                    .stroke(Color.white.opacity(0.08), lineWidth: 1)
            )
    }

    private func glassIconButton(systemName: String, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            glassIcon(systemName: systemName)
        }
        .buttonStyle(.plain)
    }

    private var descriptionText: String {
        if let editorial = viewModel.details?.editorialSummary, !editorial.isEmpty {
            return editorial
        }
        let category = viewModel.details?.categoryLabel
        let types = viewModel.details?.types ?? []
        let address = viewModel.details?.address
        let rating = viewModel.details?.rating
        let reviewsCount = viewModel.details?.reviewsCount
        let priceLevel = viewModel.details?.priceLevel?.displayText

        let template = descriptionTemplate(types: types, category: category)
        var sentence1 = template
        if let address, !address.isEmpty {
            sentence1 += " Адрес: \(address)."
        }

        var sentence2Parts: [String] = []
        if let rating {
            let ratingText = String(format: "%.1f", rating)
            if let reviewsCount {
                sentence2Parts.append("Средний рейтинг \(ratingText) по \(reviewsCount) отзывам")
            } else {
                sentence2Parts.append("Средний рейтинг \(ratingText)")
            }
        }
        if let priceLevel, !priceLevel.isEmpty {
            sentence2Parts.append("уровень цен \(priceLevel)")
        }

        if !sentence2Parts.isEmpty {
            let sentence2 = sentence2Parts.joined(separator: ", ") + "."
            return "\(sentence1) \(sentence2)"
        }

        return sentence1
    }

    private func descriptionTemplate(types: [String], category: String?) -> String {
        let typeSet = Set(types)

        if typeSet.contains("cafe") || typeSet.contains("coffee_shop") {
            return "Уютное место, чтобы выпить кофе и перекусить. Подходит для короткой остановки или встречи."
        }
        if typeSet.contains("restaurant") || typeSet.contains("food") {
            return "Заведение с кухней и атмосферой для спокойного обеда или ужина. Подходит для приятного отдыха в городе."
        }
        if typeSet.contains("bar") || typeSet.contains("night_club") {
            return "Место для вечернего отдыха и общения. Хороший вариант для завершения насыщенного дня."
        }
        if typeSet.contains("museum") || typeSet.contains("art_gallery") {
            return "Музейное пространство для знакомства с культурой и экспозициями. Подходит для спокойного визита и впечатлений."
        }
        if typeSet.contains("park") || typeSet.contains("tourist_attraction") {
            return "Пространство для прогулки и отдыха. Хорошее место, чтобы сделать паузу и насладиться атмосферой."
        }
        if typeSet.contains("shopping_mall") || typeSet.contains("store") {
            return "Место для покупок и короткого перерыва. Удобно, если хотите совместить прогулку и шопинг."
        }

        if let category, !category.isEmpty {
            return "Место категории «\(category)» — хороший выбор для знакомства с районом и атмосферы города."
        }

        return "Информация о месте пока недоступна."
    }
}

private struct QuickStat: Identifiable {
    let id = UUID()
    let title: String
    let subtitle: String
    let icon: String
    let isPrimary: Bool
}

struct MissingPlaceIdView: View {
    let placeName: String

    var body: some View {
        VStack(spacing: 16) {
            Image(systemName: "exclamationmark.triangle.fill")
                .font(.system(size: 36))
                .foregroundColor(.orange)
            Text(placeName)
                .font(.headline)
                .lineLimit(2)
                .minimumScaleFactor(0.8)
            Text("Не удалось загрузить детали места. В маршруте нет Google Place ID.")
                .font(.subheadline)
                .foregroundColor(.secondary)
                .multilineTextAlignment(.center)
        }
        .padding(24)
    }
}

// MARK: - Edge Case Previews for Layout Testing

#if DEBUG
extension Place {
    /// Preview helper initializer for testing edge cases
    static func preview(
        id: String = UUID().uuidString,
        name: String,
        category: PlaceCategory = .other,
        googlePlaceId: String? = nil,
        coordinate: CLLocationCoordinate2D = .init(latitude: 55.7558, longitude: 37.6173),
        tags: [String]? = nil,
        address: String? = nil,
        note: String? = nil
    ) -> Place {
        Place(
            id: id,
            name: name,
            category: category,
            coordinate: coordinate,
            shortDescription: nil,
            googlePlaceId: googlePlaceId,
            scheduledTime: nil,
            endTime: nil,
            duration: nil,
            rating: nil,
            tags: tags,
            address: address,
            note: note,
            travelTimeMinutes: nil,
            travelDistanceMeters: nil
        )
    }
}

struct PlaceDetailsView_Previews: PreviewProvider {
    @ViewBuilder
    static var previews: some View {
            // MARK: - Stress Tests for Layout Stability

            // 1. Very long Russian name (60+ chars) - tests 2-line title with scaling
            PlaceDetailsView(
                placeId: "test-long-name-ru",
                fallbackPlace: .preview(
                    name: "Государственный Исторический Музей Архитектуры и Декоративно-Прикладного Искусства имени Щусева",
                    category: .museum,
                    googlePlaceId: "test-long-name-ru",
                    tags: ["museum", "tourist_attraction"]
                )
            )
            .previewDisplayName("Long Name RU")

            // 2. Very long English name - tests international text
            PlaceDetailsView(
                placeId: "test-long-name-en",
                fallbackPlace: .preview(
                    name: "The Metropolitan Museum of Art - Ancient Egyptian Wing & Special Exhibitions Gallery",
                    category: .museum,
                    googlePlaceId: "test-long-name-en",
                    tags: ["museum", "art_gallery", "tourist_attraction"]
                )
            )
            .previewDisplayName("Long Name EN")

            // 3. Minimal data - no rating, no phone, no tags, no address
            PlaceDetailsView(
                placeId: "test-minimal",
                fallbackPlace: .preview(
                    name: "Кафе",
                    category: .cafe,
                    googlePlaceId: "test-minimal",
                    tags: nil
                )
            )
            .previewDisplayName("Minimal Data")

            // 3a. First-letter check: Piazza Mercanti
            PlaceDetailsView(
                placeId: "test-piazza-mercanti",
                fallbackPlace: .preview(
                    name: "Piazza Mercanti",
                    category: .other,
                    googlePlaceId: "test-piazza-mercanti",
                    tags: nil
                )
            )
            .previewDisplayName("First Letter Piazza")

            // 3b. First-letter check: Square Jean XXIII
            PlaceDetailsView(
                placeId: "test-square-jean-xxiii",
                fallbackPlace: .preview(
                    name: "Square Jean XXIII",
                    category: .other,
                    googlePlaceId: "test-square-jean-xxiii",
                    tags: nil
                )
            )
            .previewDisplayName("First Letter Square")

            // 4. Maximum tags (10+) - tests horizontal scroll
            PlaceDetailsView(
                placeId: "test-many-tags",
                fallbackPlace: .preview(
                    name: "Популярное место с множеством категорий",
                    category: .restaurant,
                    googlePlaceId: "test-many-tags",
                    tags: [
                        "restaurant", "cafe", "bar", "food", "point_of_interest",
                        "establishment", "bakery", "meal_takeaway", "meal_delivery",
                        "tourist_attraction", "night_club", "shopping_mall"
                    ]
                )
            )
            .previewDisplayName("10+ Tags")

            // 5. Very long address - tests location section
            PlaceDetailsView(
                placeId: "test-long-address",
                fallbackPlace: .preview(
                    name: "Ресторан «Белый кролик»",
                    category: .restaurant,
                    googlePlaceId: "test-long-address",
                    tags: ["restaurant"],
                    address: "улица Большая Ордынка, дом 123, корпус 4, строение 5, подъезд 2, этаж 15, офис 301, Москва, Россия, 115184"
                )
            )
            .previewDisplayName("Long Address")

            // 6. No Google Place ID - tests fallback state
            PlaceDetailsView(
                placeId: "",
                fallbackPlace: .preview(
                    name: "Место без Google Place ID",
                    category: .other,
                    googlePlaceId: nil,
                    tags: ["point_of_interest"]
                )
            )
            .previewDisplayName("No PlaceID")

            // 7. Short name with no tags - tests empty chips section
            PlaceDetailsView(
                placeId: "test-short",
                fallbackPlace: .preview(
                    name: "Bar",
                    category: .nightlife,
                    googlePlaceId: "test-short",
                    tags: nil
                )
            )
            .previewDisplayName("Short Name No Tags")

            // 8. Edge case: emoji in name (some places have this)
            PlaceDetailsView(
                placeId: "test-emoji",
                fallbackPlace: .preview(
                    name: "Кофейня ☕ Coffee House 🏠",
                    category: .cafe,
                    googlePlaceId: "test-emoji",
                    tags: ["cafe", "coffee_shop"]
                )
            )
            .previewDisplayName("Name with Emoji")
    }
}
#endif
