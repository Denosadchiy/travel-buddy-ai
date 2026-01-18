//
//  SavedTripDetailView.swift
//  Travell Buddy
//
//  Detail view for a saved trip showing full itinerary.
//

import SwiftUI

struct SavedTripDetailView: View {
    let savedTripId: UUID

    @StateObject private var savedTripsManager = SavedTripsManager.shared
    @State private var tripDetail: SavedTripDetailResponseDTO?
    @State private var isLoading = true
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        ZStack {
            // Background
            backgroundLayer
                .ignoresSafeArea()

            VStack(spacing: 0) {
                // Header
                headerView

                // Content
                if isLoading {
                    loadingView
                } else if let detail = tripDetail {
                    detailContent(detail: detail)
                } else {
                    errorView
                }
            }
        }
        .navigationBarHidden(true)
        .task {
            await loadTripDetail()
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

            Spacer()

            Text(tripDetail?.cityName ?? "Загрузка...")
                .font(.system(size: 18, weight: .semibold))
                .foregroundColor(.white)

            Spacer()

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
            Text("Загрузка маршрута...")
                .font(.system(size: 14, weight: .medium))
                .foregroundColor(.white.opacity(0.7))
                .padding(.top, 12)
            Spacer()
        }
    }

    private var errorView: some View {
        VStack(spacing: 16) {
            Spacer()

            Image(systemName: "exclamationmark.triangle")
                .font(.system(size: 48, weight: .light))
                .foregroundColor(.white.opacity(0.4))

            Text("Ошибка загрузки")
                .font(.system(size: 18, weight: .semibold))
                .foregroundColor(.white)

            Text("Не удалось загрузить детали поездки")
                .font(.system(size: 14, weight: .regular))
                .foregroundColor(.white.opacity(0.6))

            Button("Попробовать снова") {
                Task { await loadTripDetail() }
            }
            .buttonStyle(.borderedProminent)
            .tint(Color.travelBuddyOrange)
            .padding(.top, 8)

            Spacer()
        }
        .padding(.horizontal, 24)
    }

    @ViewBuilder
    private func detailContent(detail: SavedTripDetailResponseDTO) -> some View {
        ScrollView(showsIndicators: false) {
            VStack(spacing: 24) {
                // Hero image
                if let imageUrlString = detail.heroImageUrl, let url = URL(string: imageUrlString) {
                    RemoteImageView(url: url)
                        .frame(height: 200)
                        .clipShape(RoundedRectangle(cornerRadius: 24, style: .continuous))
                        .shadow(color: Color.black.opacity(0.3), radius: 16, x: 0, y: 8)
                }

                // Trip info card
                tripInfoCard(detail: detail)

                // Itinerary
                if let itinerary = detail.itinerary, !itinerary.isEmpty {
                    itinerarySection(days: itinerary)
                } else {
                    noItineraryView
                }
            }
            .padding(.horizontal, 16)
            .padding(.top, 8)
            .padding(.bottom, 32)
        }
    }

    private func tripInfoCard(detail: SavedTripDetailResponseDTO) -> some View {
        VStack(alignment: .leading, spacing: 16) {
            // City name
            Text(detail.cityName)
                .font(.system(size: 28, weight: .bold))
                .foregroundColor(.white)

            // Dates and travelers
            HStack(spacing: 20) {
                // Dates
                VStack(alignment: .leading, spacing: 4) {
                    Label {
                        Text("Даты")
                            .font(.system(size: 12, weight: .medium))
                            .foregroundColor(.white.opacity(0.6))
                    } icon: {
                        Image(systemName: "calendar")
                            .font(.system(size: 12))
                    }

                    Text(formatDateRange(start: detail.startDate, end: detail.endDate))
                        .font(.system(size: 15, weight: .semibold))
                        .foregroundColor(.white)
                }

                // Travelers
                VStack(alignment: .leading, spacing: 4) {
                    Label {
                        Text("Путешественники")
                            .font(.system(size: 12, weight: .medium))
                            .foregroundColor(.white.opacity(0.6))
                    } icon: {
                        Image(systemName: "person.2")
                            .font(.system(size: 12))
                    }

                    Text("\(detail.numTravelers) чел.")
                        .font(.system(size: 15, weight: .semibold))
                        .foregroundColor(.white)
                }
            }
            .foregroundColor(.white.opacity(0.6))
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(20)
        .background(
            RoundedRectangle(cornerRadius: 24, style: .continuous)
                .fill(Color(red: 0.18, green: 0.18, blue: 0.20).opacity(0.7))
                .background(.ultraThinMaterial, in: RoundedRectangle(cornerRadius: 24, style: .continuous))
        )
        .overlay(
            RoundedRectangle(cornerRadius: 24, style: .continuous)
                .stroke(Color.white.opacity(0.08), lineWidth: 1)
        )
    }

    private func itinerarySection(days: [SavedItineraryDayDTO]) -> some View {
        VStack(alignment: .leading, spacing: 16) {
            Text("Маршрут по дням")
                .font(.system(size: 22, weight: .bold))
                .foregroundColor(.white)
                .padding(.horizontal, 4)

            ForEach(Array(days.enumerated()), id: \.offset) { index, day in
                dayCard(day: day, index: index)
            }
        }
    }

    private func dayCard(day: SavedItineraryDayDTO, index: Int) -> some View {
        VStack(alignment: .leading, spacing: 12) {
            // Day header
            HStack {
                Text("День \(day.dayNumber)")
                    .font(.system(size: 18, weight: .bold))
                    .foregroundColor(.white)

                if let theme = day.theme {
                    Text("• \(theme)")
                        .font(.system(size: 14, weight: .medium))
                        .foregroundColor(.white.opacity(0.6))
                }

                Spacer()

                Text(formatDate(day.date))
                    .font(.system(size: 13, weight: .medium))
                    .foregroundColor(.white.opacity(0.5))
            }

            // Blocks
            VStack(spacing: 8) {
                ForEach(Array(day.blocks.enumerated()), id: \.offset) { blockIndex, block in
                    if let poi = block.poi {
                        poiBlockView(block: block, poi: poi)
                    } else {
                        simpleBlockView(block: block)
                    }
                }
            }
        }
        .padding(16)
        .background(
            RoundedRectangle(cornerRadius: 20, style: .continuous)
                .fill(Color(red: 0.18, green: 0.18, blue: 0.20).opacity(0.6))
                .background(.ultraThinMaterial, in: RoundedRectangle(cornerRadius: 20, style: .continuous))
        )
        .overlay(
            RoundedRectangle(cornerRadius: 20, style: .continuous)
                .stroke(Color.white.opacity(0.06), lineWidth: 1)
        )
    }

    private func poiBlockView(block: SavedItineraryBlockDTO, poi: SavedPOIDTO) -> some View {
        HStack(spacing: 12) {
            // Time
            VStack(alignment: .leading, spacing: 2) {
                Text(formatTime(block.startTime))
                    .font(.system(size: 13, weight: .semibold))
                    .foregroundColor(Color.travelBuddyOrange)
                Text(formatTime(block.endTime))
                    .font(.system(size: 11, weight: .medium))
                    .foregroundColor(.white.opacity(0.4))
            }
            .frame(width: 50, alignment: .leading)

            // POI info
            VStack(alignment: .leading, spacing: 4) {
                Text(poi.name)
                    .font(.system(size: 15, weight: .semibold))
                    .foregroundColor(.white)
                    .lineLimit(2)

                if let address = poi.address {
                    Text(address)
                        .font(.system(size: 12, weight: .regular))
                        .foregroundColor(.white.opacity(0.5))
                        .lineLimit(1)
                }

                // Rating
                if let rating = poi.rating {
                    HStack(spacing: 4) {
                        Image(systemName: "star.fill")
                            .font(.system(size: 10))
                            .foregroundColor(.yellow)
                        Text(String(format: "%.1f", rating))
                            .font(.system(size: 12, weight: .medium))
                            .foregroundColor(.white.opacity(0.7))
                    }
                }
            }

            Spacer()
        }
        .padding(12)
        .background(
            RoundedRectangle(cornerRadius: 14, style: .continuous)
                .fill(Color.black.opacity(0.2))
        )
    }

    private func simpleBlockView(block: SavedItineraryBlockDTO) -> some View {
        HStack(spacing: 12) {
            // Time
            Text(formatTime(block.startTime))
                .font(.system(size: 13, weight: .semibold))
                .foregroundColor(Color.travelBuddyOrange)
                .frame(width: 50, alignment: .leading)

            // Block type
            Text(localizeBlockType(block.blockType))
                .font(.system(size: 14, weight: .medium))
                .foregroundColor(.white.opacity(0.7))

            Spacer()
        }
        .padding(12)
        .background(
            RoundedRectangle(cornerRadius: 14, style: .continuous)
                .fill(Color.black.opacity(0.15))
        )
    }

    private var noItineraryView: some View {
        VStack(spacing: 12) {
            Image(systemName: "map")
                .font(.system(size: 36, weight: .light))
                .foregroundColor(.white.opacity(0.4))

            Text("Маршрут недоступен")
                .font(.system(size: 16, weight: .semibold))
                .foregroundColor(.white)

            Text("Детальный маршрут для этой поездки не сохранён")
                .font(.system(size: 13, weight: .regular))
                .foregroundColor(.white.opacity(0.6))
                .multilineTextAlignment(.center)
        }
        .frame(maxWidth: .infinity)
        .padding(.vertical, 40)
    }

    // MARK: - Helpers

    private func loadTripDetail() async {
        isLoading = true
        tripDetail = await savedTripsManager.getSavedTripDetail(id: savedTripId)
        isLoading = false
    }

    private func formatDateRange(start: String, end: String) -> String {
        let formatter = DateFormatter()
        formatter.dateFormat = "yyyy-MM-dd"

        guard let startDate = formatter.date(from: start),
              let endDate = formatter.date(from: end) else {
            return "\(start) - \(end)"
        }

        let displayFormatter = DateFormatter()
        displayFormatter.locale = Locale(identifier: "ru_RU")
        displayFormatter.dateFormat = "d MMM"

        return "\(displayFormatter.string(from: startDate)) - \(displayFormatter.string(from: endDate))"
    }

    private func formatDate(_ dateString: String) -> String {
        let formatter = DateFormatter()
        formatter.dateFormat = "yyyy-MM-dd"

        guard let date = formatter.date(from: dateString) else {
            return dateString
        }

        let displayFormatter = DateFormatter()
        displayFormatter.locale = Locale(identifier: "ru_RU")
        displayFormatter.dateFormat = "d MMMM, EEEE"

        return displayFormatter.string(from: date)
    }

    private func formatTime(_ timeString: String) -> String {
        let components = timeString.split(separator: ":")
        if components.count >= 2 {
            return "\(components[0]):\(components[1])"
        }
        return timeString
    }

    private func localizeBlockType(_ type: String) -> String {
        switch type {
        case "meal": return "Прием пищи"
        case "activity": return "Активность"
        case "transport": return "Транспорт"
        case "free_time": return "Свободное время"
        default: return type
        }
    }
}

#Preview {
    SavedTripDetailView(savedTripId: UUID())
}
