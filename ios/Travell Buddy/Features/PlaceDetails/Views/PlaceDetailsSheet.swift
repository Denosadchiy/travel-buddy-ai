//
//  PlaceDetailsSheet.swift
//  Travell Buddy
//
//  Premium Apple Maps-like bottom sheet for place details.
//

import SwiftUI
import MapKit

// MARK: - Main Sheet View

struct PlaceDetailsSheet: View {
    @StateObject private var viewModel: PlaceDetailsViewModel
    @Environment(\.dismiss) private var dismiss

    let place: Place

    init(place: Place, service: PlaceDetailsServiceProtocol = PlaceDetailsService.shared) {
        self.place = place
        _viewModel = StateObject(wrappedValue: PlaceDetailsViewModel(place: place, service: service))
    }

    var body: some View {
        NavigationView {
            ScrollView {
                VStack(spacing: 0) {
                    // Header
                    headerSection

                    // Content based on state
                    switch viewModel.state {
                    case .idle, .loading:
                        skeletonContent
                    case .loaded(let details):
                        loadedContent(details)
                    case .error(let message):
                        errorContent(message)
                    }
                }
            }
            .background(Color(UIColor.systemGroupedBackground))
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .navigationBarTrailing) {
                    Button(action: { dismiss() }) {
                        Image(systemName: "xmark.circle.fill")
                            .font(.system(size: 28))
                            .foregroundStyle(.gray, Color(UIColor.systemGray5))
                    }
                }
            }
        }
        .onAppear {
            viewModel.loadDetails()
        }
    }

    // MARK: - Header Section

    private var headerSection: some View {
        VStack(spacing: 12) {
            // Category icon
            ZStack {
                Circle()
                    .fill(place.category.color.opacity(0.15))
                    .frame(width: 56, height: 56)

                Image(systemName: place.category.iconName)
                    .font(.system(size: 24))
                    .foregroundColor(place.category.color)
            }

            // Place name
            Text(place.name)
                .font(.system(size: 24, weight: .bold))
                .multilineTextAlignment(.center)

            // Category label
            Text(place.category.displayName)
                .font(.system(size: 15))
                .foregroundColor(.secondary)

            // Scheduled time if available
            if let time = place.scheduledTime {
                HStack(spacing: 4) {
                    Image(systemName: "clock")
                        .font(.system(size: 13))
                    Text(time)
                        .font(.system(size: 14, weight: .medium))
                }
                .foregroundColor(.blue)
                .padding(.horizontal, 12)
                .padding(.vertical, 6)
                .background(Color.blue.opacity(0.1))
                .cornerRadius(16)
            }
        }
        .padding(.vertical, 20)
        .padding(.horizontal, 16)
        .frame(maxWidth: .infinity)
        .background(Color(UIColor.systemBackground))
    }

    // MARK: - Loaded Content

    @ViewBuilder
    private func loadedContent(_ details: PlaceDetails) -> some View {
        VStack(spacing: 16) {
            // Photos carousel
            if !details.photos.isEmpty {
                photosCarousel(details.photos)
                    .transition(.opacity.combined(with: .move(edge: .top)))
            }

            // Key facts row
            keyFactsSection(details)
                .transition(.opacity)

            // Address section
            if let address = details.address {
                addressSection(address: address, coordinate: details.coordinate)
                    .transition(.opacity)
            }

            // Travel info (if available)
            if details.travelTimeFromPrevious != nil || details.travelDistanceFromPrevious != nil {
                travelInfoSection(details)
                    .transition(.opacity)
            }

            // AI explanation
            if let explanation = details.aiWhyRecommended {
                aiExplanationSection(explanation)
                    .transition(.opacity)
            }

            // Tips
            if let tips = details.tips, !tips.isEmpty {
                tipsSection(tips)
                    .transition(.opacity)
            }

            // Quick actions
            quickActionsSection
                .transition(.opacity)

            // Bottom spacing
            Spacer().frame(height: 32)
        }
        .padding(.top, 8)
        .animation(.easeInOut(duration: 0.3), value: viewModel.state)
    }

    // MARK: - Photos Carousel

    private func photosCarousel(_ photos: [PlacePhoto]) -> some View {
        ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: 12) {
                ForEach(photos) { photo in
                    AsyncImage(url: photo.url) { phase in
                        switch phase {
                        case .empty:
                            Rectangle()
                                .fill(Color(UIColor.systemGray5))
                                .overlay(
                                    ProgressView()
                                        .tint(.gray)
                                )
                        case .success(let image):
                            image
                                .resizable()
                                .aspectRatio(contentMode: .fill)
                        case .failure:
                            Rectangle()
                                .fill(Color(UIColor.systemGray5))
                                .overlay(
                                    Image(systemName: "photo")
                                        .font(.system(size: 24))
                                        .foregroundColor(.gray)
                                )
                        @unknown default:
                            EmptyView()
                        }
                    }
                    .frame(width: 260, height: 180)
                    .clipShape(RoundedRectangle(cornerRadius: 16))
                }
            }
            .padding(.horizontal, 16)
        }
    }

    // MARK: - Key Facts Section

    private func keyFactsSection(_ details: PlaceDetails) -> some View {
        HStack(spacing: 0) {
            // Rating
            if let rating = details.rating {
                keyFactItem(
                    icon: "star.fill",
                    iconColor: .orange,
                    value: String(format: "%.1f", rating),
                    label: details.reviewsCount.map { "\($0) отзывов" } ?? "Рейтинг"
                )
            }

            // Price level
            if let priceLevel = details.priceLevel {
                Divider()
                    .frame(height: 40)
                keyFactItem(
                    icon: "dollarsign.circle.fill",
                    iconColor: .green,
                    value: priceLevel.dollarSigns,
                    label: "Цены"
                )
            }

            // Open status
            if let isOpen = details.isOpenNow {
                Divider()
                    .frame(height: 40)
                keyFactItem(
                    icon: isOpen ? "checkmark.circle.fill" : "xmark.circle.fill",
                    iconColor: isOpen ? .green : .red,
                    value: isOpen ? "Открыто" : "Закрыто",
                    label: details.closingTime ?? ""
                )
            }

            // Duration
            if let duration = details.suggestedDuration {
                Divider()
                    .frame(height: 40)
                keyFactItem(
                    icon: "clock.fill",
                    iconColor: .blue,
                    value: formatDuration(duration),
                    label: "Визит"
                )
            }
        }
        .padding(.vertical, 16)
        .background(Color(UIColor.systemBackground))
        .cornerRadius(16)
        .padding(.horizontal, 16)
    }

    private func keyFactItem(icon: String, iconColor: Color, value: String, label: String) -> some View {
        VStack(spacing: 6) {
            Image(systemName: icon)
                .font(.system(size: 18))
                .foregroundColor(iconColor)

            Text(value)
                .font(.system(size: 15, weight: .semibold))

            if !label.isEmpty {
                Text(label)
                    .font(.system(size: 12))
                    .foregroundColor(.secondary)
            }
        }
        .frame(maxWidth: .infinity)
    }

    // MARK: - Address Section

    private func addressSection(address: String, coordinate: CLLocationCoordinate2D) -> some View {
        VStack(alignment: .leading, spacing: 12) {
            sectionHeader("Адрес")

            Button(action: { viewModel.openInMaps() }) {
                HStack(spacing: 12) {
                    // Mini map preview
                    Map(coordinateRegion: .constant(MKCoordinateRegion(
                        center: coordinate,
                        span: MKCoordinateSpan(latitudeDelta: 0.005, longitudeDelta: 0.005)
                    )), annotationItems: [MapPin(coordinate: coordinate)]) { pin in
                        MapMarker(coordinate: pin.coordinate, tint: .red)
                    }
                    .frame(width: 80, height: 80)
                    .cornerRadius(12)
                    .disabled(true)

                    VStack(alignment: .leading, spacing: 4) {
                        Text(address)
                            .font(.system(size: 15))
                            .foregroundColor(.primary)
                            .multilineTextAlignment(.leading)

                        Text("Открыть в Картах")
                            .font(.system(size: 13))
                            .foregroundColor(.blue)
                    }

                    Spacer()

                    Image(systemName: "chevron.right")
                        .font(.system(size: 14, weight: .semibold))
                        .foregroundColor(.secondary)
                }
                .padding(12)
                .background(Color(UIColor.systemBackground))
                .cornerRadius(16)
            }
            .buttonStyle(PlainButtonStyle())
        }
        .padding(.horizontal, 16)
    }

    // MARK: - Travel Info Section

    private func travelInfoSection(_ details: PlaceDetails) -> some View {
        VStack(alignment: .leading, spacing: 12) {
            sectionHeader("Как добраться")

            HStack(spacing: 16) {
                if let mode = details.travelMode {
                    HStack(spacing: 6) {
                        Image(systemName: mode.icon)
                            .font(.system(size: 16))
                            .foregroundColor(.blue)
                        Text(mode.displayName)
                            .font(.system(size: 14))
                    }
                }

                if let time = details.travelTimeFromPrevious {
                    HStack(spacing: 6) {
                        Image(systemName: "clock")
                            .font(.system(size: 14))
                            .foregroundColor(.secondary)
                        Text(formatDuration(time))
                            .font(.system(size: 14))
                    }
                }

                if let distance = details.travelDistanceFromPrevious {
                    HStack(spacing: 6) {
                        Image(systemName: "arrow.left.and.right")
                            .font(.system(size: 14))
                            .foregroundColor(.secondary)
                        Text(String(format: "%.1f км", distance))
                            .font(.system(size: 14))
                    }
                }

                Spacer()
            }
            .padding(16)
            .background(Color(UIColor.systemBackground))
            .cornerRadius(16)
        }
        .padding(.horizontal, 16)
    }

    // MARK: - AI Explanation Section

    private func aiExplanationSection(_ explanation: String) -> some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack(spacing: 8) {
                Image(systemName: "sparkles")
                    .font(.system(size: 16))
                    .foregroundColor(.purple)
                Text("Почему это место")
                    .font(.system(size: 15, weight: .semibold))
            }

            Text(explanation)
                .font(.system(size: 15))
                .foregroundColor(.secondary)
                .lineSpacing(4)
        }
        .padding(16)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(
            LinearGradient(
                colors: [Color.purple.opacity(0.1), Color.blue.opacity(0.05)],
                startPoint: .topLeading,
                endPoint: .bottomTrailing
            )
        )
        .cornerRadius(16)
        .padding(.horizontal, 16)
    }

    // MARK: - Tips Section

    private func tipsSection(_ tips: [String]) -> some View {
        VStack(alignment: .leading, spacing: 12) {
            sectionHeader("Советы")

            VStack(spacing: 8) {
                ForEach(tips, id: \.self) { tip in
                    HStack(alignment: .top, spacing: 12) {
                        Image(systemName: "lightbulb.fill")
                            .font(.system(size: 14))
                            .foregroundColor(.yellow)
                            .frame(width: 20)

                        Text(tip)
                            .font(.system(size: 14))
                            .foregroundColor(.primary)

                        Spacer()
                    }
                }
            }
            .padding(16)
            .background(Color(UIColor.systemBackground))
            .cornerRadius(16)
        }
        .padding(.horizontal, 16)
    }

    // MARK: - Quick Actions Section

    private var quickActionsSection: some View {
        VStack(alignment: .leading, spacing: 12) {
            sectionHeader("Действия")

            VStack(spacing: 0) {
                // Save
                quickActionRow(
                    icon: viewModel.isSaved ? "bookmark.fill" : "bookmark",
                    iconColor: viewModel.isSaved ? .blue : .gray,
                    title: viewModel.isSaved ? "Сохранено" : "Сохранить",
                    action: { viewModel.toggleSave() }
                )

                Divider().padding(.leading, 52)

                // Mark as mandatory
                quickActionRow(
                    icon: viewModel.isMandatory ? "star.fill" : "star",
                    iconColor: viewModel.isMandatory ? .orange : .gray,
                    title: viewModel.isMandatory ? "Обязательно к посещению" : "Отметить обязательным",
                    action: { viewModel.toggleMandatory() }
                )

                Divider().padding(.leading, 52)

                // Mark as avoided
                quickActionRow(
                    icon: viewModel.isAvoided ? "hand.raised.fill" : "hand.raised",
                    iconColor: viewModel.isAvoided ? .red : .gray,
                    title: viewModel.isAvoided ? "Исключено из маршрута" : "Исключить из маршрута",
                    action: { viewModel.toggleAvoided() }
                )

                Divider().padding(.leading, 52)

                // Contact actions
                if let details = viewModel.details {
                    if details.phone != nil {
                        quickActionRow(
                            icon: "phone.fill",
                            iconColor: .green,
                            title: "Позвонить",
                            action: { viewModel.callPhone() }
                        )
                        Divider().padding(.leading, 52)
                    }

                    if details.website != nil {
                        quickActionRow(
                            icon: "safari.fill",
                            iconColor: .blue,
                            title: "Открыть сайт",
                            action: { viewModel.openWebsite() }
                        )
                    }
                }
            }
            .background(Color(UIColor.systemBackground))
            .cornerRadius(16)
        }
        .padding(.horizontal, 16)
    }

    private func quickActionRow(icon: String, iconColor: Color, title: String, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            HStack(spacing: 16) {
                Image(systemName: icon)
                    .font(.system(size: 18))
                    .foregroundColor(iconColor)
                    .frame(width: 24)

                Text(title)
                    .font(.system(size: 16))
                    .foregroundColor(.primary)

                Spacer()
            }
            .padding(.horizontal, 16)
            .padding(.vertical, 14)
        }
        .buttonStyle(PlainButtonStyle())
    }

    // MARK: - Error Content

    private func errorContent(_ message: String) -> some View {
        VStack(spacing: 16) {
            Spacer().frame(height: 40)

            Image(systemName: "exclamationmark.triangle.fill")
                .font(.system(size: 48))
                .foregroundColor(.orange)

            Text("Не удалось загрузить")
                .font(.system(size: 18, weight: .semibold))

            Text(message)
                .font(.system(size: 14))
                .foregroundColor(.secondary)
                .multilineTextAlignment(.center)

            Button(action: { viewModel.retry() }) {
                Text("Повторить")
                    .font(.system(size: 16, weight: .medium))
                    .foregroundColor(.white)
                    .padding(.horizontal, 32)
                    .padding(.vertical, 12)
                    .background(Color.blue)
                    .cornerRadius(24)
            }

            Spacer().frame(height: 40)
        }
        .padding(.horizontal, 16)
    }

    // MARK: - Skeleton Content

    private var skeletonContent: some View {
        VStack(spacing: 16) {
            // Photos skeleton
            ScrollView(.horizontal, showsIndicators: false) {
                HStack(spacing: 12) {
                    ForEach(0..<3, id: \.self) { _ in
                        SkeletonView()
                            .frame(width: 260, height: 180)
                            .cornerRadius(16)
                    }
                }
                .padding(.horizontal, 16)
            }

            // Key facts skeleton
            HStack(spacing: 0) {
                ForEach(0..<4, id: \.self) { index in
                    if index > 0 {
                        Divider().frame(height: 40)
                    }
                    VStack(spacing: 8) {
                        SkeletonView()
                            .frame(width: 24, height: 24)
                            .cornerRadius(12)
                        SkeletonView()
                            .frame(width: 40, height: 16)
                            .cornerRadius(4)
                        SkeletonView()
                            .frame(width: 60, height: 12)
                            .cornerRadius(4)
                    }
                    .frame(maxWidth: .infinity)
                }
            }
            .padding(.vertical, 16)
            .background(Color(UIColor.systemBackground))
            .cornerRadius(16)
            .padding(.horizontal, 16)

            // Address skeleton
            VStack(alignment: .leading, spacing: 12) {
                SkeletonView()
                    .frame(width: 60, height: 14)
                    .cornerRadius(4)

                HStack(spacing: 12) {
                    SkeletonView()
                        .frame(width: 80, height: 80)
                        .cornerRadius(12)

                    VStack(alignment: .leading, spacing: 8) {
                        SkeletonView()
                            .frame(height: 14)
                            .cornerRadius(4)
                        SkeletonView()
                            .frame(width: 150, height: 14)
                            .cornerRadius(4)
                        SkeletonView()
                            .frame(width: 100, height: 12)
                            .cornerRadius(4)
                    }

                    Spacer()
                }
                .padding(12)
                .background(Color(UIColor.systemBackground))
                .cornerRadius(16)
            }
            .padding(.horizontal, 16)

            // AI explanation skeleton
            VStack(alignment: .leading, spacing: 12) {
                HStack(spacing: 8) {
                    SkeletonView()
                        .frame(width: 20, height: 20)
                        .cornerRadius(10)
                    SkeletonView()
                        .frame(width: 120, height: 16)
                        .cornerRadius(4)
                }

                VStack(spacing: 8) {
                    SkeletonView()
                        .frame(height: 14)
                        .cornerRadius(4)
                    SkeletonView()
                        .frame(height: 14)
                        .cornerRadius(4)
                    SkeletonView()
                        .frame(width: 200, height: 14)
                        .cornerRadius(4)
                }
            }
            .padding(16)
            .background(Color(UIColor.systemGray6))
            .cornerRadius(16)
            .padding(.horizontal, 16)

            Spacer().frame(height: 32)
        }
        .padding(.top, 8)
    }

    // MARK: - Helpers

    private func sectionHeader(_ title: String) -> some View {
        Text(title)
            .font(.system(size: 13, weight: .semibold))
            .foregroundColor(.secondary)
            .textCase(.uppercase)
    }

    private func formatDuration(_ interval: TimeInterval) -> String {
        let minutes = Int(interval) / 60
        if minutes >= 60 {
            let hours = minutes / 60
            let remainingMinutes = minutes % 60
            if remainingMinutes == 0 {
                return "\(hours) ч"
            }
            return "\(hours) ч \(remainingMinutes) мин"
        }
        return "\(minutes) мин"
    }
}

// MARK: - Map Pin Helper

private struct MapPin: Identifiable {
    let id = UUID()
    let coordinate: CLLocationCoordinate2D
}

// MARK: - Skeleton View

struct SkeletonView: View {
    @State private var isAnimating = false

    var body: some View {
        Rectangle()
            .fill(
                LinearGradient(
                    gradient: Gradient(colors: [
                        Color(UIColor.systemGray5),
                        Color(UIColor.systemGray4),
                        Color(UIColor.systemGray5)
                    ]),
                    startPoint: isAnimating ? .leading : .trailing,
                    endPoint: isAnimating ? .trailing : .leading
                )
            )
            .onAppear {
                withAnimation(.linear(duration: 1.5).repeatForever(autoreverses: false)) {
                    isAnimating = true
                }
            }
    }
}

// MARK: - Preview

#if DEBUG
struct PlaceDetailsSheet_Previews: PreviewProvider {
    static var previews: some View {
        PlaceDetailsSheet(
            place: Place(
                id: "1",
                name: "Колизей",
                category: .attraction,
                coordinate: CLLocationCoordinate2D(latitude: 41.8902, longitude: 12.4922),
                shortDescription: "Древний римский амфитеатр",
                scheduledTime: "10:00",
                duration: 90 * 60
            ),
            service: MockPlaceDetailsService()
        )
    }
}
#endif
