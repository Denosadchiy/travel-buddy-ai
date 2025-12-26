//
//  CityAutocompleteField.swift
//  Travell Buddy
//
//  Text field with city autocomplete suggestions.
//

import SwiftUI

struct CityAutocompleteField: View {
    let title: String
    let placeholder: String
    @Binding var cityName: String
    @Binding var airportCode: String
    var onCitySelected: ((CityAirport) -> Void)?

    @State private var isShowingSuggestions: Bool = false
    @State private var suggestions: [CityAirport] = []
    @FocusState private var isFocused: Bool

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text(title)
                .font(.system(size: 13, weight: .medium))
                .foregroundColor(Color(.secondaryLabel))

            ZStack(alignment: .topLeading) {
                TextField(placeholder, text: $cityName)
                    .font(.system(size: 16))
                    .padding(12)
                    .background(
                        RoundedRectangle(cornerRadius: 10, style: .continuous)
                            .fill(Color(.tertiarySystemBackground))
                    )
                    .focused($isFocused)
                    .onChange(of: cityName) { newValue in
                        updateSuggestions(for: newValue)
                    }
                    .onChange(of: isFocused) { focused in
                        if focused {
                            updateSuggestions(for: cityName)
                        } else {
                            // Задержка для обработки тапа по suggestion
                            DispatchQueue.main.asyncAfter(deadline: .now() + 0.2) {
                                isShowingSuggestions = false
                            }
                        }
                    }

                // Dropdown с suggestions
                if isShowingSuggestions && !suggestions.isEmpty {
                    VStack(alignment: .leading, spacing: 0) {
                        // Пустое пространство под текстовым полем
                        Color.clear
                            .frame(height: 44)

                        // Список suggestions
                        VStack(spacing: 0) {
                            ForEach(suggestions.prefix(5)) { city in
                                Button {
                                    selectCity(city)
                                } label: {
                                    HStack(spacing: 12) {
                                        Image(systemName: "airplane.circle.fill")
                                            .font(.system(size: 16))
                                            .foregroundColor(.travelBuddyOrange)

                                        VStack(alignment: .leading, spacing: 2) {
                                            Text(city.cityName)
                                                .font(.system(size: 15, weight: .medium))
                                                .foregroundColor(Color(.label))

                                            Text("\(city.countryName) · \(city.primaryAirport.code)")
                                                .font(.system(size: 12))
                                                .foregroundColor(Color(.secondaryLabel))
                                        }

                                        Spacer()
                                    }
                                    .padding(.horizontal, 12)
                                    .padding(.vertical, 10)
                                    .background(Color(.tertiarySystemBackground))
                                }
                                .buttonStyle(.plain)

                                if city.id != suggestions.prefix(5).last?.id {
                                    Divider()
                                        .padding(.leading, 40)
                                }
                            }
                        }
                        .background(
                            RoundedRectangle(cornerRadius: 10, style: .continuous)
                                .fill(Color(.tertiarySystemBackground))
                                .shadow(color: Color.black.opacity(0.1), radius: 8, x: 0, y: 4)
                        )
                    }
                }
            }
        }
    }

    private func updateSuggestions(for query: String) {
        if query.isEmpty {
            suggestions = []
            isShowingSuggestions = false
            return
        }

        suggestions = AirportDatabase.shared.searchCities(query: query)
        isShowingSuggestions = !suggestions.isEmpty
    }

    private func selectCity(_ city: CityAirport) {
        cityName = city.cityName
        airportCode = city.primaryAirport.code
        isShowingSuggestions = false
        isFocused = false
        onCitySelected?(city)
    }
}

// MARK: - Airport Selector

struct AirportSelectorField: View {
    let title: String
    let city: CityAirport?
    @Binding var selectedAirport: String
    @State private var isShowingPicker: Bool = false

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text(title)
                .font(.system(size: 13, weight: .medium))
                .foregroundColor(Color(.secondaryLabel))

            if let city = city, city.airports.count > 1 {
                // Несколько аэропортов - показываем picker
                Button {
                    isShowingPicker = true
                } label: {
                    HStack {
                        VStack(alignment: .leading, spacing: 2) {
                            Text(selectedAirportName)
                                .font(.system(size: 16, weight: .medium))
                                .foregroundColor(Color(.label))

                            Text(selectedAirport)
                                .font(.system(size: 13))
                                .foregroundColor(Color(.secondaryLabel))
                        }

                        Spacer()

                        Image(systemName: "chevron.down")
                            .font(.system(size: 12, weight: .semibold))
                            .foregroundColor(Color(.tertiaryLabel))
                    }
                    .padding(12)
                    .background(
                        RoundedRectangle(cornerRadius: 10, style: .continuous)
                            .fill(Color(.tertiarySystemBackground))
                    )
                }
                .buttonStyle(.plain)
                .sheet(isPresented: $isShowingPicker) {
                    airportPickerSheet(city: city)
                }
            } else {
                // Один аэропорт или город не выбран
                HStack {
                    VStack(alignment: .leading, spacing: 2) {
                        Text(selectedAirportName)
                            .font(.system(size: 16, weight: .medium))
                            .foregroundColor(city == nil ? Color(.tertiaryLabel) : Color(.label))

                        if !selectedAirport.isEmpty {
                            Text(selectedAirport)
                                .font(.system(size: 13))
                                .foregroundColor(Color(.secondaryLabel))
                        }
                    }

                    Spacer()
                }
                .padding(12)
                .background(
                    RoundedRectangle(cornerRadius: 10, style: .continuous)
                        .fill(Color(.tertiarySystemBackground))
                )
            }
        }
    }

    private var selectedAirportName: String {
        guard let city = city else {
            return "Сначала выберите город"
        }

        if let airport = city.airports.first(where: { $0.code == selectedAirport }) {
            return airport.name
        }

        return city.primaryAirport.name
    }

    private func airportPickerSheet(city: CityAirport) -> some View {
        NavigationStack {
            List {
                ForEach(city.airports) { airport in
                    Button {
                        selectedAirport = airport.code
                        isShowingPicker = false
                    } label: {
                        HStack {
                            VStack(alignment: .leading, spacing: 4) {
                                Text(airport.name)
                                    .font(.system(size: 16, weight: .medium))
                                    .foregroundColor(Color(.label))

                                Text(airport.code)
                                    .font(.system(size: 13))
                                    .foregroundColor(Color(.secondaryLabel))
                            }

                            Spacer()

                            if airport.code == selectedAirport {
                                Image(systemName: "checkmark")
                                    .font(.system(size: 16, weight: .semibold))
                                    .foregroundColor(.travelBuddyOrange)
                            }
                        }
                        .contentShape(Rectangle())
                    }
                    .buttonStyle(.plain)
                }
            }
            .navigationTitle("Выберите аэропорт")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Закрыть") {
                        isShowingPicker = false
                    }
                }
            }
        }
        .presentationDetents([.medium])
    }
}
