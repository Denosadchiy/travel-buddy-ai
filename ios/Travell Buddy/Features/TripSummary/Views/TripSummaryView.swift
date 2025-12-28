//
//  TripSummaryView.swift
//  Travell Buddy
//
//  Full trip summary view with overall stats and daily breakdown.
//

import SwiftUI
import CoreLocation

struct TripSummaryView: View {
    @StateObject private var viewModel: TripSummaryViewModel
    @State private var expandedDayIndex: Int? = nil

    private var summary: TripSummary { viewModel.summary }

    private let dateFormatter: DateFormatter = {
        let formatter = DateFormatter()
        formatter.locale = Locale(identifier: "ru_RU")
        formatter.dateFormat = "d MMM"
        return formatter
    }()

    init(summary: TripSummary, coordinate: CLLocationCoordinate2D? = nil) {
        _viewModel = StateObject(wrappedValue: TripSummaryViewModel(summary: summary, coordinate: coordinate))
    }

    var body: some View {
        ScrollView {
            VStack(spacing: 20) {
                // Header
                headerSection

                // Overall stats card
                TripSummaryCard(summary: summary)
                    .padding(.horizontal, 16)

                // Weather loading indicator
                if viewModel.isLoadingWeather {
                    HStack(spacing: 8) {
                        ProgressView()
                            .scaleEffect(0.8)
                        Text("Загрузка прогноза погоды...")
                            .font(.system(size: 13))
                            .foregroundColor(.secondary)
                    }
                    .padding(.horizontal, 16)
                }

                // Daily breakdown
                dailyBreakdownSection

                // Weather tips section (if weather available)
                if viewModel.daySummaries.contains(where: { $0.weather != nil }) {
                    weatherTipsSection
                }

                // Tips section
                tipsSection

                Spacer().frame(height: 20)
            }
        }
        .background(Color(UIColor.systemGroupedBackground))
        .navigationTitle("Сводка поездки")
        .navigationBarTitleDisplayMode(.large)
        .task {
            await viewModel.loadWeather()
        }
    }

    // MARK: - Header

    private var headerSection: some View {
        VStack(spacing: 8) {
            Text(summary.city)
                .font(.system(size: 28, weight: .bold))

            Text("\(dateFormatter.string(from: summary.startDate)) – \(dateFormatter.string(from: summary.endDate))")
                .font(.system(size: 16))
                .foregroundColor(.secondary)
        }
        .padding(.top, 8)
    }

    // MARK: - Daily Breakdown

    private var dailyBreakdownSection: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("По дням")
                .font(.system(size: 13, weight: .semibold))
                .foregroundColor(.secondary)
                .textCase(.uppercase)
                .padding(.horizontal, 16)

            VStack(spacing: 8) {
                ForEach(viewModel.daySummaries) { daySummary in
                    DaySummaryRow(
                        summary: daySummary,
                        isExpanded: expandedDayIndex == daySummary.dayIndex,
                        onTap: {
                            withAnimation {
                                if expandedDayIndex == daySummary.dayIndex {
                                    expandedDayIndex = nil
                                } else {
                                    expandedDayIndex = daySummary.dayIndex
                                }
                            }
                        }
                    )
                }
            }
            .padding(.horizontal, 16)
        }
    }

    // MARK: - Weather Tips Section

    private var weatherTipsSection: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("Погода")
                .font(.system(size: 13, weight: .semibold))
                .foregroundColor(.secondary)
                .textCase(.uppercase)
                .padding(.horizontal, 16)

            VStack(spacing: 12) {
                // Temperature range
                if let tempRange = temperatureRange {
                    tipCard(
                        icon: "thermometer.medium",
                        iconColor: .orange,
                        title: "Температура",
                        description: "Ожидается от \(Int(tempRange.low))° до \(Int(tempRange.high))°C"
                    )
                }

                // Rain recommendation
                if let maxPrecip = maxPrecipitationProbability, maxPrecip > 30 {
                    tipCard(
                        icon: "umbrella.fill",
                        iconColor: .blue,
                        title: "Дождь",
                        description: maxPrecip > 60
                            ? "Высокая вероятность дождя (\(maxPrecip)%), возьмите зонт"
                            : "Возможен дождь (\(maxPrecip)%), рекомендуем взять зонт"
                    )
                }

                // Clothing recommendation based on average temperature
                if let avgTemp = averageTemperature {
                    tipCard(
                        icon: "tshirt.fill",
                        iconColor: .purple,
                        title: "Одежда",
                        description: clothingRecommendation(for: avgTemp)
                    )
                }

                // UV recommendation
                if let maxUV = maxUVIndex, maxUV >= 6 {
                    tipCard(
                        icon: "sun.max.fill",
                        iconColor: .yellow,
                        title: "Солнце",
                        description: maxUV >= 8
                            ? "Очень высокий УФ-индекс! Обязательны солнцезащитный крем и головной убор"
                            : "Высокий УФ-индекс. Используйте солнцезащитный крем"
                    )
                }
            }
            .padding(.horizontal, 16)
        }
    }

    // MARK: - Weather Computed Properties

    private var temperatureRange: (low: Double, high: Double)? {
        let weatherDays = viewModel.daySummaries.compactMap { $0.weather }
        guard !weatherDays.isEmpty else { return nil }

        let minTemp = weatherDays.map { $0.temperatureLow }.min() ?? 0
        let maxTemp = weatherDays.map { $0.temperatureHigh }.max() ?? 0

        return (minTemp, maxTemp)
    }

    private var averageTemperature: Double? {
        let weatherDays = viewModel.daySummaries.compactMap { $0.weather }
        guard !weatherDays.isEmpty else { return nil }

        let avgHigh = weatherDays.map { $0.temperatureHigh }.reduce(0, +) / Double(weatherDays.count)
        let avgLow = weatherDays.map { $0.temperatureLow }.reduce(0, +) / Double(weatherDays.count)

        return (avgHigh + avgLow) / 2
    }

    private var maxPrecipitationProbability: Int? {
        let weatherDays = viewModel.daySummaries.compactMap { $0.weather }
        guard !weatherDays.isEmpty else { return nil }

        return weatherDays.map { $0.precipitationProbability }.max()
    }

    private var maxUVIndex: Int? {
        let weatherDays = viewModel.daySummaries.compactMap { $0.weather }
        guard !weatherDays.isEmpty else { return nil }

        return weatherDays.map { $0.uvIndex }.max()
    }

    private func clothingRecommendation(for temperature: Double) -> String {
        if temperature < 5 {
            return "Тёплая зимняя куртка, шапка, перчатки, тёплая обувь"
        } else if temperature < 10 {
            return "Тёплая куртка или пальто, шарф, закрытая обувь"
        } else if temperature < 18 {
            return "Куртка или кофта, лёгкий шарф, кроссовки"
        } else if temperature < 25 {
            return "Лёгкая одежда, кофта на вечер, удобная обувь"
        } else {
            return "Очень лёгкая одежда, головной убор, сандалии или кроссовки"
        }
    }

    // MARK: - Tips Section

    private var tipsSection: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("Рекомендации")
                .font(.system(size: 13, weight: .semibold))
                .foregroundColor(.secondary)
                .textCase(.uppercase)
                .padding(.horizontal, 16)

            VStack(spacing: 12) {
                // Footwear tip
                tipCard(
                    icon: "shoe.fill",
                    iconColor: .brown,
                    title: "Удобная обувь",
                    description: footwearRecommendation
                )

                // Hydration tip
                tipCard(
                    icon: "drop.fill",
                    iconColor: .blue,
                    title: "Вода",
                    description: hydrationRecommendation
                )

                // Budget tip
                tipCard(
                    icon: "banknote.fill",
                    iconColor: .green,
                    title: "Наличные",
                    description: cashRecommendation
                )

                // Phone tip
                tipCard(
                    icon: "battery.100.bolt",
                    iconColor: .yellow,
                    title: "Зарядка телефона",
                    description: "При активных прогулках рекомендуем взять повербанк"
                )
            }
            .padding(.horizontal, 16)
        }
    }

    private func tipCard(icon: String, iconColor: Color, title: String, description: String) -> some View {
        HStack(spacing: 12) {
            ZStack {
                Circle()
                    .fill(iconColor.opacity(0.15))
                    .frame(width: 40, height: 40)

                Image(systemName: icon)
                    .font(.system(size: 16))
                    .foregroundColor(iconColor)
            }

            VStack(alignment: .leading, spacing: 2) {
                Text(title)
                    .font(.system(size: 14, weight: .semibold))

                Text(description)
                    .font(.system(size: 13))
                    .foregroundColor(.secondary)
                    .lineLimit(2)
            }

            Spacer()
        }
        .padding(12)
        .background(Color(UIColor.systemBackground))
        .cornerRadius(12)
    }

    // MARK: - Computed Recommendations

    private var footwearRecommendation: String {
        let avgDaily = summary.totalDistanceMeters / max(summary.daysCount, 1)
        if avgDaily > 10000 {
            return "Много ходьбы! Обязательно возьмите очень удобную обувь"
        } else if avgDaily > 5000 {
            return "Планируются долгие прогулки, нужна комфортная обувь"
        }
        return "Прогулки умеренные, подойдёт любая удобная обувь"
    }

    private var hydrationRecommendation: String {
        let avgSteps = summary.averageStepsPerDay
        if avgSteps > 12000 {
            return "Берите минимум 1.5л воды в день, особенно летом"
        } else if avgSteps > 8000 {
            return "Рекомендуем носить с собой бутылку воды 0.5-1л"
        }
        return "Достаточно небольшой бутылки воды"
    }

    private var cashRecommendation: String {
        let avgCost = (summary.averageDailyCostLow + summary.averageDailyCostHigh) / 2
        let cashNeeded = avgCost * 0.3 // Assume 30% in cash

        let formatter = NumberFormatter()
        formatter.numberStyle = .currency
        formatter.currencyCode = summary.currency
        formatter.maximumFractionDigits = 0

        let cashStr = formatter.string(from: NSNumber(value: cashNeeded * Double(summary.daysCount))) ?? "\(Int(cashNeeded * Double(summary.daysCount)))"

        return "Рекомендуем иметь \(cashStr) наличными на мелкие расходы"
    }
}

// MARK: - Inline Summary (for TripPlanView header)

struct TripSummaryInline: View {
    let summary: TripSummary

    var body: some View {
        ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: 12) {
                inlineStatChip(
                    icon: "figure.walk",
                    value: summary.formattedTotalSteps,
                    label: "шагов"
                )

                inlineStatChip(
                    icon: "map",
                    value: summary.formattedTotalDistance,
                    label: "пешком"
                )

                inlineStatChip(
                    icon: "creditcard",
                    value: summary.formattedTotalCostRange,
                    label: "бюджет"
                )

                inlineStatChip(
                    icon: summary.overallIntensity.icon,
                    value: summary.overallIntensity.displayName,
                    label: "темп"
                )
            }
            .padding(.horizontal, 16)
        }
    }

    private func inlineStatChip(icon: String, value: String, label: String) -> some View {
        HStack(spacing: 6) {
            Image(systemName: icon)
                .font(.system(size: 12))
                .foregroundColor(.secondary)

            Text(value)
                .font(.system(size: 13, weight: .semibold))

            Text(label)
                .font(.system(size: 11))
                .foregroundColor(.secondary)
        }
        .padding(.horizontal, 12)
        .padding(.vertical, 8)
        .background(Color(UIColor.systemGray6))
        .cornerRadius(16)
    }
}
