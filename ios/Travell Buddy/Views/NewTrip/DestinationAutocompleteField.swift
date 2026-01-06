//
//  DestinationAutocompleteField.swift
//  Travell Buddy
//
//  Text field with city autocomplete using Apple MapKit.
//  Worldwide coverage, completely free.
//

import SwiftUI
import MapKit

struct DestinationAutocompleteField: View {
    @Binding var cityName: String
    var placeholder: String = "Введите город"
    var onCitySelected: ((CitySearchResult) -> Void)?

    @StateObject private var searchService = CitySearchService()
    @State private var isShowingSuggestions: Bool = false
    @FocusState private var isFocused: Bool

    var body: some View {
        ZStack(alignment: .top) {
            // Text field
            inputField

            // Dropdown with suggestions
            if isShowingSuggestions && !searchService.suggestions.isEmpty {
                suggestionsDropdown
                    .offset(y: 56)
                    .zIndex(100)
            }
        }
    }

    // MARK: - Input Field

    private var inputField: some View {
        HStack(spacing: 12) {
            TextField(placeholder, text: $cityName)
                .font(.system(size: 17, weight: .medium))
                .foregroundColor(Color(red: 0.20, green: 0.18, blue: 0.16))
                .focused($isFocused)
                .onChange(of: cityName) { newValue in
                    searchService.search(query: newValue)
                    updateSuggestionsVisibility()
                }
                .onChange(of: isFocused) { focused in
                    if focused {
                        searchService.search(query: cityName)
                        updateSuggestionsVisibility()
                    } else {
                        // Delay to allow tap on suggestion
                        DispatchQueue.main.asyncAfter(deadline: .now() + 0.25) {
                            isShowingSuggestions = false
                        }
                    }
                }

            // Loading indicator
            if case .searching = searchService.state {
                ProgressView()
                    .scaleEffect(0.8)
            }

            // Clear button
            if !cityName.isEmpty && searchService.state != .searching {
                Button {
                    cityName = ""
                    searchService.clear()
                    isShowingSuggestions = false
                } label: {
                    Image(systemName: "xmark.circle.fill")
                        .font(.system(size: 16))
                        .foregroundColor(Color.black.opacity(0.35))
                }
                .buttonStyle(.plain)
            }
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 14)
        .background(
            RoundedRectangle(cornerRadius: 16, style: .continuous)
                .fill(Color.white)
        )
        .overlay(
            RoundedRectangle(cornerRadius: 16, style: .continuous)
                .stroke(Color.white.opacity(0.4), lineWidth: 1)
        )
        .onChange(of: searchService.suggestions) { _ in
            updateSuggestionsVisibility()
        }
    }

    // MARK: - Suggestions Dropdown

    private var suggestionsDropdown: some View {
        VStack(spacing: 0) {
            ForEach(searchService.suggestions.prefix(5)) { result in
                Button {
                    selectCity(result)
                } label: {
                    suggestionRow(result)
                }
                .buttonStyle(.plain)

                if result.id != searchService.suggestions.prefix(5).last?.id {
                    Divider()
                        .padding(.leading, 60)
                }
            }
        }
        .background(
            RoundedRectangle(cornerRadius: 16, style: .continuous)
                .fill(Color(red: 0.18, green: 0.17, blue: 0.16))
                .shadow(color: Color.black.opacity(0.35), radius: 16, x: 0, y: 8)
        )
        .clipShape(RoundedRectangle(cornerRadius: 16, style: .continuous))
    }

    private func suggestionRow(_ result: CitySearchResult) -> some View {
        HStack(spacing: 12) {
            ZStack {
                Circle()
                    .fill(Color.white.opacity(0.08))
                    .frame(width: 40, height: 40)

                Image(systemName: "mappin.circle.fill")
                    .font(.system(size: 18))
                    .foregroundColor(Color.travelBuddyOrange)
            }

            VStack(alignment: .leading, spacing: 3) {
                Text(result.name)
                    .font(.system(size: 16, weight: .medium))
                    .foregroundColor(Color.white)
                    .lineLimit(1)

                if !result.country.isEmpty {
                    Text(result.country)
                        .font(.system(size: 13))
                        .foregroundColor(Color.white.opacity(0.6))
                        .lineLimit(1)
                }
            }

            Spacer()

            Image(systemName: "arrow.up.left")
                .font(.system(size: 12, weight: .medium))
                .foregroundColor(Color.white.opacity(0.4))
        }
        .padding(.horizontal, 14)
        .padding(.vertical, 12)
        .contentShape(Rectangle())
    }

    // MARK: - Private Methods

    private func updateSuggestionsVisibility() {
        let hasResults = !searchService.suggestions.isEmpty
        let isSearching = searchService.state == .searching
        isShowingSuggestions = (hasResults || isSearching) && isFocused && cityName.count >= 1
    }

    private func selectCity(_ result: CitySearchResult) {
        cityName = result.name
        isShowingSuggestions = false
        isFocused = false
        searchService.clear()

        // Resolve coordinates in background
        Task {
            if let resolved = await searchService.resolveCity(result) {
                onCitySelected?(resolved)
            } else {
                onCitySelected?(result)
            }
        }
    }
}

// MARK: - Empty State View

private struct EmptyStateView: View {
    var body: some View {
        HStack(spacing: 12) {
            Image(systemName: "magnifyingglass")
                .font(.system(size: 16))
                .foregroundColor(Color.white.opacity(0.5))

            Text("Город не найден")
                .font(.system(size: 14))
                .foregroundColor(Color.white.opacity(0.6))
        }
        .frame(maxWidth: .infinity)
        .padding(.vertical, 16)
    }
}
