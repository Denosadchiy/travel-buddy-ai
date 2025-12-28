//
//  DaySummaryRow.swift
//  Travell Buddy
//
//  Row showing summary for a single day.
//

import SwiftUI

struct DaySummaryRow: View {
    let summary: DaySummary
    let isExpanded: Bool
    let onTap: () -> Void

    private let dateFormatter: DateFormatter = {
        let formatter = DateFormatter()
        formatter.locale = Locale(identifier: "ru_RU")
        formatter.dateFormat = "d MMMM, EEE"
        return formatter
    }()

    var body: some View {
        VStack(spacing: 0) {
            // Main row (always visible)
            Button(action: onTap) {
                HStack(spacing: 12) {
                    // Day number badge
                    dayBadge

                    // Date and stats
                    VStack(alignment: .leading, spacing: 4) {
                        Text(dateFormatter.string(from: summary.date))
                            .font(.system(size: 15, weight: .medium))

                        HStack(spacing: 12) {
                            miniStat(icon: "figure.walk", value: summary.formattedSteps)
                            miniStat(icon: "map", value: summary.formattedDistance)
                            miniStat(icon: "clock", value: summary.formattedWalkingTime)
                        }
                    }

                    Spacer()

                    // Weather or intensity
                    if let weather = summary.weather {
                        weatherBadge(weather)
                    } else {
                        intensityIndicator
                    }

                    // Chevron
                    Image(systemName: isExpanded ? "chevron.up" : "chevron.down")
                        .font(.system(size: 12, weight: .semibold))
                        .foregroundColor(.secondary)
                }
                .padding(.horizontal, 16)
                .padding(.vertical, 14)
            }
            .buttonStyle(PlainButtonStyle())

            // Expanded content
            if isExpanded {
                expandedContent
                    .transition(.opacity.combined(with: .move(edge: .top)))
            }
        }
        .background(Color(UIColor.systemBackground))
        .cornerRadius(16)
        .animation(.easeInOut(duration: 0.2), value: isExpanded)
    }

    // MARK: - Components

    private var dayBadge: some View {
        ZStack {
            Circle()
                .fill(intensityColor.opacity(0.15))
                .frame(width: 40, height: 40)

            Text("\(summary.dayIndex)")
                .font(.system(size: 16, weight: .bold))
                .foregroundColor(intensityColor)
        }
    }

    private var intensityIndicator: some View {
        HStack(spacing: 4) {
            Image(systemName: summary.activityIntensity.icon)
                .font(.system(size: 12))
            Text(summary.activityIntensity.displayName)
                .font(.system(size: 11, weight: .medium))
        }
        .foregroundColor(intensityColor)
        .padding(.horizontal, 8)
        .padding(.vertical, 4)
        .background(intensityColor.opacity(0.1))
        .cornerRadius(8)
    }

    private var intensityColor: Color {
        switch summary.activityIntensity {
        case .light: return .green
        case .moderate: return .orange
        case .high: return .red
        }
    }

    private func weatherBadge(_ weather: DayWeather) -> some View {
        HStack(spacing: 4) {
            Image(systemName: weather.condition.icon)
                .font(.system(size: 14))

            Text(weather.formattedTemperature)
                .font(.system(size: 12, weight: .medium))
        }
        .foregroundColor(.primary)
        .padding(.horizontal, 8)
        .padding(.vertical, 4)
        .background(Color(UIColor.systemGray5))
        .cornerRadius(8)
    }

    private func miniStat(icon: String, value: String) -> some View {
        HStack(spacing: 3) {
            Image(systemName: icon)
                .font(.system(size: 10))
                .foregroundColor(.secondary)

            Text(value)
                .font(.system(size: 11))
                .foregroundColor(.secondary)
        }
    }

    // MARK: - Expanded Content

    private var expandedContent: some View {
        VStack(spacing: 12) {
            Divider()
                .padding(.horizontal, 16)

            // Detailed stats
            HStack(spacing: 0) {
                detailStat(
                    title: "Активностей",
                    value: "\(summary.activitiesCount)",
                    icon: "calendar"
                )

                Divider().frame(height: 40)

                detailStat(
                    title: "Приёмов пищи",
                    value: "\(summary.mealsCount)",
                    icon: "fork.knife"
                )

                Divider().frame(height: 40)

                detailStat(
                    title: "Бюджет",
                    value: summary.formattedCostRange,
                    icon: "creditcard"
                )
            }
            .padding(.horizontal, 16)

            // Time range
            if let firstTime = summary.firstActivityTime, let lastTime = summary.lastActivityTime {
                HStack {
                    Image(systemName: "clock")
                        .font(.system(size: 12))
                        .foregroundColor(.secondary)

                    Text("С \(firstTime) до \(lastTime)")
                        .font(.system(size: 13))
                        .foregroundColor(.secondary)

                    Spacer()

                    Text("~\(summary.totalActivityTimeMinutes / 60) ч активного времени")
                        .font(.system(size: 12))
                        .foregroundColor(.secondary)
                }
                .padding(.horizontal, 16)
            }

            // Weather recommendation (if available)
            if let weather = summary.weather {
                HStack(spacing: 8) {
                    Image(systemName: "tshirt")
                        .font(.system(size: 12))
                        .foregroundColor(.blue)

                    Text(weather.clothingRecommendation)
                        .font(.system(size: 12))
                        .foregroundColor(.secondary)

                    Spacer()
                }
                .padding(.horizontal, 16)
                .padding(.vertical, 8)
                .background(Color.blue.opacity(0.05))
                .cornerRadius(8)
                .padding(.horizontal, 16)
            }

            // Intensity recommendation
            HStack(spacing: 8) {
                Image(systemName: summary.activityIntensity.icon)
                    .font(.system(size: 12))
                    .foregroundColor(intensityColor)

                Text(summary.activityIntensity.description)
                    .font(.system(size: 12))
                    .foregroundColor(.secondary)

                Spacer()
            }
            .padding(.horizontal, 16)
            .padding(.bottom, 12)
        }
    }

    private func detailStat(title: String, value: String, icon: String) -> some View {
        VStack(spacing: 4) {
            Image(systemName: icon)
                .font(.system(size: 14))
                .foregroundColor(.secondary)

            Text(value)
                .font(.system(size: 14, weight: .semibold))
                .lineLimit(1)
                .minimumScaleFactor(0.7)

            Text(title)
                .font(.system(size: 10))
                .foregroundColor(.secondary)
        }
        .frame(maxWidth: .infinity)
    }
}
