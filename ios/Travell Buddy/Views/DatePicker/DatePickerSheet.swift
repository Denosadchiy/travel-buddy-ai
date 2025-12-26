//
//  DatePickerSheet.swift
//  Travell Buddy
//
//  Legacy wrapper for DateRangePickerView compatibility.
//

import SwiftUI

struct DatePickerSheet: View {
    @Binding var startDate: Date
    @Binding var endDate: Date
    @Binding var isPresented: Bool

    @State private var departureDate: Date?
    @State private var returnDate: Date?

    var body: some View {
        DateRangePickerView(
            departureDate: $departureDate,
            returnDate: $returnDate,
            isPresented: $isPresented
        )
        .onAppear {
            departureDate = startDate
            returnDate = endDate
        }
        .onChange(of: departureDate) { newValue in
            if let date = newValue {
                startDate = date
            }
        }
        .onChange(of: returnDate) { newValue in
            if let date = newValue {
                endDate = date
            }
        }
    }
}
