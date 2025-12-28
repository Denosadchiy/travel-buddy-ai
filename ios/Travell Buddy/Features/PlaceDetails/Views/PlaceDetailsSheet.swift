//
//  PlaceDetailsSheet.swift
//  Travell Buddy
//
//  Premium Apple Maps-like bottom sheet for place details.
//  Works with local data from Place model.
//

import SwiftUI
import MapKit

// MARK: - Main Sheet View

struct PlaceDetailsSheet: View {
    @Environment(\.dismiss) private var dismiss
    @State private var isSaved: Bool = false
    @State private var isMandatory: Bool = false
    @State private var isAvoided: Bool = false

    let place: Place

    var body: some View {
        NavigationView {
            ScrollView {
                VStack(spacing: 0) {
                    headerSection
                    contentSection
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
                .padding(.horizontal, 16)

            // Category label
            Text(place.category.displayName)
                .font(.system(size: 15))
                .foregroundColor(.secondary)

            // Scheduled time
            if let time = place.scheduledTime {
                HStack(spacing: 8) {
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

                    if let duration = place.durationMinutes {
                        HStack(spacing: 4) {
                            Image(systemName: "hourglass")
                                .font(.system(size: 13))
                            Text(formatMinutes(duration))
                                .font(.system(size: 14, weight: .medium))
                        }
                        .foregroundColor(.purple)
                        .padding(.horizontal, 12)
                        .padding(.vertical, 6)
                        .background(Color.purple.opacity(0.1))
                        .cornerRadius(16)
                    }
                }
            }

            // Tags
            if let tags = place.tags, !tags.isEmpty {
                ScrollView(.horizontal, showsIndicators: false) {
                    HStack(spacing: 8) {
                        ForEach(tags.prefix(5), id: \.self) { tag in
                            Text(tag)
                                .font(.system(size: 12, weight: .medium))
                                .foregroundColor(.secondary)
                                .padding(.horizontal, 10)
                                .padding(.vertical, 5)
                                .background(Color(UIColor.systemGray5))
                                .cornerRadius(12)
                        }
                    }
                    .padding(.horizontal, 16)
                }
            }
        }
        .padding(.vertical, 20)
        .frame(maxWidth: .infinity)
        .background(Color(UIColor.systemBackground))
    }

    // MARK: - Content Section

    private var contentSection: some View {
        VStack(spacing: 16) {
            // Key facts row
            keyFactsSection
                .padding(.top, 8)

            // Description
            if let description = place.shortDescription, !description.isEmpty {
                descriptionSection(description)
            }

            // Address section
            if let address = place.address, !address.isEmpty {
                addressSection(address: address)
            }

            // Travel info from previous stop
            if place.travelTimeMinutes != nil || place.travelDistanceMeters != nil {
                travelInfoSection
            }

            // Note from itinerary
            if let note = place.note, !note.isEmpty {
                noteSection(note)
            }

            // Quick actions
            quickActionsSection

            // Bottom spacing
            Spacer().frame(height: 32)
        }
    }

    // MARK: - Key Facts Section

    private var keyFactsSection: some View {
        HStack(spacing: 0) {
            // Rating
            if let rating = place.rating {
                keyFactItem(
                    icon: "star.fill",
                    iconColor: .orange,
                    value: String(format: "%.1f", rating),
                    label: "Рейтинг"
                )
            }

            // Duration
            if let duration = place.durationMinutes {
                if place.rating != nil {
                    Divider().frame(height: 40)
                }
                keyFactItem(
                    icon: "clock.fill",
                    iconColor: .blue,
                    value: formatMinutes(duration),
                    label: "Визит"
                )
            }

            // Category
            if place.rating != nil || place.durationMinutes != nil {
                Divider().frame(height: 40)
            }
            keyFactItem(
                icon: place.category.iconName,
                iconColor: place.category.color,
                value: place.category.displayName,
                label: "Категория"
            )
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
                .font(.system(size: 14, weight: .semibold))
                .lineLimit(1)
                .minimumScaleFactor(0.8)

            Text(label)
                .font(.system(size: 11))
                .foregroundColor(.secondary)
        }
        .frame(maxWidth: .infinity)
    }

    // MARK: - Description Section

    private func descriptionSection(_ description: String) -> some View {
        VStack(alignment: .leading, spacing: 12) {
            sectionHeader("Описание")

            Text(description)
                .font(.system(size: 15))
                .foregroundColor(.primary)
                .lineSpacing(4)
                .padding(16)
                .frame(maxWidth: .infinity, alignment: .leading)
                .background(Color(UIColor.systemBackground))
                .cornerRadius(16)
        }
        .padding(.horizontal, 16)
    }

    // MARK: - Address Section

    private func addressSection(address: String) -> some View {
        VStack(alignment: .leading, spacing: 12) {
            sectionHeader("Адрес")

            Button(action: { openInMaps() }) {
                HStack(spacing: 12) {
                    // Mini map preview
                    Map(coordinateRegion: .constant(MKCoordinateRegion(
                        center: place.coordinate,
                        span: MKCoordinateSpan(latitudeDelta: 0.005, longitudeDelta: 0.005)
                    )), annotationItems: [MapPin(coordinate: place.coordinate)]) { pin in
                        MapMarker(coordinate: pin.coordinate, tint: place.category.color)
                    }
                    .frame(width: 80, height: 80)
                    .cornerRadius(12)
                    .disabled(true)

                    VStack(alignment: .leading, spacing: 4) {
                        Text(address)
                            .font(.system(size: 15))
                            .foregroundColor(.primary)
                            .multilineTextAlignment(.leading)
                            .lineLimit(3)

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

    private var travelInfoSection: some View {
        VStack(alignment: .leading, spacing: 12) {
            sectionHeader("Как добраться")

            HStack(spacing: 16) {
                // Walking icon (default mode)
                HStack(spacing: 6) {
                    Image(systemName: "figure.walk")
                        .font(.system(size: 16))
                        .foregroundColor(.blue)
                    Text("Пешком")
                        .font(.system(size: 14))
                }

                if let time = place.travelTimeMinutes {
                    HStack(spacing: 6) {
                        Image(systemName: "clock")
                            .font(.system(size: 14))
                            .foregroundColor(.secondary)
                        Text(formatMinutes(time))
                            .font(.system(size: 14))
                    }
                }

                if let distance = place.travelDistanceMeters {
                    HStack(spacing: 6) {
                        Image(systemName: "arrow.left.and.right")
                            .font(.system(size: 14))
                            .foregroundColor(.secondary)
                        Text(formatDistance(distance))
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

    // MARK: - Note Section

    private func noteSection(_ note: String) -> some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack(spacing: 8) {
                Image(systemName: "sparkles")
                    .font(.system(size: 16))
                    .foregroundColor(.purple)
                Text("Совет")
                    .font(.system(size: 15, weight: .semibold))
            }

            Text(note)
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

    // MARK: - Quick Actions Section

    private var quickActionsSection: some View {
        VStack(alignment: .leading, spacing: 12) {
            sectionHeader("Действия")

            VStack(spacing: 0) {
                // Save
                quickActionRow(
                    icon: isSaved ? "bookmark.fill" : "bookmark",
                    iconColor: isSaved ? .blue : .gray,
                    title: isSaved ? "Сохранено" : "Сохранить",
                    action: {
                        isSaved.toggle()
                        hapticFeedback()
                    }
                )

                Divider().padding(.leading, 52)

                // Mark as mandatory
                quickActionRow(
                    icon: isMandatory ? "star.fill" : "star",
                    iconColor: isMandatory ? .orange : .gray,
                    title: isMandatory ? "Обязательно к посещению" : "Отметить обязательным",
                    action: {
                        isMandatory.toggle()
                        if isMandatory { isAvoided = false }
                        hapticFeedback()
                    }
                )

                Divider().padding(.leading, 52)

                // Mark as avoided
                quickActionRow(
                    icon: isAvoided ? "hand.raised.fill" : "hand.raised",
                    iconColor: isAvoided ? .red : .gray,
                    title: isAvoided ? "Исключено из маршрута" : "Исключить из маршрута",
                    action: {
                        isAvoided.toggle()
                        if isAvoided { isMandatory = false }
                        hapticFeedback()
                    }
                )

                Divider().padding(.leading, 52)

                // Open in Maps
                quickActionRow(
                    icon: "map.fill",
                    iconColor: .green,
                    title: "Открыть в Картах",
                    action: { openInMaps() }
                )
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

    // MARK: - Helpers

    private func sectionHeader(_ title: String) -> some View {
        Text(title)
            .font(.system(size: 13, weight: .semibold))
            .foregroundColor(.secondary)
            .textCase(.uppercase)
    }

    private func formatMinutes(_ minutes: Int) -> String {
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

    private func formatDistance(_ meters: Int) -> String {
        if meters >= 1000 {
            let km = Double(meters) / 1000.0
            return String(format: "%.1f км", km)
        }
        return "\(meters) м"
    }

    private func openInMaps() {
        let placemark = MKPlacemark(coordinate: place.coordinate)
        let mapItem = MKMapItem(placemark: placemark)
        mapItem.name = place.name

        mapItem.openInMaps(launchOptions: [
            MKLaunchOptionsDirectionsModeKey: MKLaunchOptionsDirectionsModeWalking
        ])

        hapticFeedback()
    }

    private func hapticFeedback() {
        let generator = UIImpactFeedbackGenerator(style: .light)
        generator.impactOccurred()
    }
}

// MARK: - Map Pin Helper

private struct MapPin: Identifiable {
    let id = UUID()
    let coordinate: CLLocationCoordinate2D
}
