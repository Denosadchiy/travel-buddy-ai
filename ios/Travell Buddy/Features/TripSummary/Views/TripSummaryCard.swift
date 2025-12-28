//
//  TripSummaryCard.swift
//  Travell Buddy
//
//  Compact card showing overall trip statistics.
//

import SwiftUI

struct TripSummaryCard: View {
    let summary: TripSummary

    var body: some View {
        VStack(spacing: 16) {
            // Header
            HStack {
                VStack(alignment: .leading, spacing: 4) {
                    Text("Сводка поездки")
                        .font(.system(size: 18, weight: .bold))

                    Text("\(summary.daysCount) дней • \(summary.travelersCount) путешественников")
                        .font(.system(size: 14))
                        .foregroundColor(.secondary)
                }

                Spacer()

                // Intensity badge
                intensityBadge
            }

            // Main stats grid
            LazyVGrid(columns: [
                GridItem(.flexible()),
                GridItem(.flexible()),
                GridItem(.flexible())
            ], spacing: 16) {
                statItem(
                    icon: "figure.walk",
                    value: summary.formattedTotalSteps,
                    label: "Шагов",
                    color: .blue
                )

                statItem(
                    icon: "map",
                    value: summary.formattedTotalDistance,
                    label: "Пешком",
                    color: .green
                )

                statItem(
                    icon: "creditcard",
                    value: summary.formattedTotalCostRange,
                    label: "Бюджет",
                    color: .orange
                )
            }

            Divider()

            // Activity breakdown
            HStack(spacing: 20) {
                activityCount(
                    icon: "mappin.circle.fill",
                    count: summary.totalActivities,
                    label: "Мест"
                )

                activityCount(
                    icon: "fork.knife",
                    count: summary.totalMeals,
                    label: "Приёмов пищи"
                )

                activityCount(
                    icon: "star.fill",
                    count: summary.totalAttractions,
                    label: "Достопримеч."
                )

                Spacer()
            }
        }
        .padding(16)
        .background(Color(UIColor.systemBackground))
        .cornerRadius(20)
        .shadow(color: Color.black.opacity(0.05), radius: 10, x: 0, y: 4)
    }

    // MARK: - Components

    private var intensityBadge: some View {
        HStack(spacing: 4) {
            Image(systemName: summary.overallIntensity.icon)
                .font(.system(size: 12))

            Text(summary.overallIntensity.displayName)
                .font(.system(size: 12, weight: .medium))
        }
        .foregroundColor(intensityColor)
        .padding(.horizontal, 10)
        .padding(.vertical, 6)
        .background(intensityColor.opacity(0.15))
        .cornerRadius(12)
    }

    private var intensityColor: Color {
        switch summary.overallIntensity {
        case .light: return .green
        case .moderate: return .orange
        case .high: return .red
        }
    }

    private func statItem(icon: String, value: String, label: String, color: Color) -> some View {
        VStack(spacing: 8) {
            ZStack {
                Circle()
                    .fill(color.opacity(0.1))
                    .frame(width: 44, height: 44)

                Image(systemName: icon)
                    .font(.system(size: 18))
                    .foregroundColor(color)
            }

            Text(value)
                .font(.system(size: 15, weight: .semibold))
                .lineLimit(1)
                .minimumScaleFactor(0.7)

            Text(label)
                .font(.system(size: 11))
                .foregroundColor(.secondary)
        }
    }

    private func activityCount(icon: String, count: Int, label: String) -> some View {
        HStack(spacing: 6) {
            Image(systemName: icon)
                .font(.system(size: 14))
                .foregroundColor(.secondary)

            Text("\(count)")
                .font(.system(size: 14, weight: .semibold))

            Text(label)
                .font(.system(size: 12))
                .foregroundColor(.secondary)
        }
    }
}
