//
//  TravelersPickerSheet.swift
//  Travell Buddy
//
//  Modal sheet for selecting number of travelers.
//

import SwiftUI

struct TravelersPickerSheet: View {
    @Binding var adultsCount: Int
    @Binding var childrenCount: Int
    @Binding var isPresented: Bool
    
    var body: some View {
        NavigationStack {
            ZStack {
                Color(.systemBackground)
                    .ignoresSafeArea()
                
                VStack(spacing: 0) {
                    // Заголовок
                    VStack(alignment: .leading, spacing: 8) {
                        Text("Количество путешественников")
                            .font(.system(size: 24, weight: .bold, design: .rounded))
                            .foregroundColor(Color(.label))
                        
                        Text("Выберите количество взрослых и детей")
                            .font(.system(size: 16))
                            .foregroundColor(Color(.secondaryLabel))
                    }
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .padding(.horizontal, 20)
                    .padding(.top, 20)
                    .padding(.bottom, 16)
                    
                    Divider()
                    
                    ScrollView {
                        VStack(spacing: 24) {
                            // Взрослые
                            TravelerCountRow(
                                title: "Взрослые",
                                subtitle: "От 18 лет",
                                icon: "person.fill",
                                iconColor: Color(red: 0.6, green: 0.4, blue: 0.8),
                                count: $adultsCount,
                                minValue: 1
                            )
                            
                            Divider()
                            
                            // Дети
                            TravelerCountRow(
                                title: "Дети",
                                subtitle: "До 18 лет",
                                icon: "figure.child",
                                iconColor: Color(red: 1.0, green: 0.65, blue: 0.40),
                                count: $childrenCount,
                                minValue: 0
                            )
                            
                            // Итого
                            VStack(spacing: 8) {
                                Divider()
                                
                                HStack {
                                    Text("Всего путешественников")
                                        .font(.system(size: 17, weight: .semibold, design: .rounded))
                                        .foregroundColor(Color(.label))
                                    
                                    Spacer()
                                    
                                    Text("\(adultsCount + childrenCount)")
                                        .font(.system(size: 24, weight: .bold, design: .rounded))
                                        .foregroundColor(Color(red: 0.6, green: 0.4, blue: 0.8))
                                }
                                .padding(.horizontal, 20)
                                .padding(.vertical, 16)
                                .background(
                                    RoundedRectangle(cornerRadius: 16, style: .continuous)
                                        .fill(Color(.systemGray6))
                                )
                            }
                            .padding(.top, 8)
                        }
                        .padding(.horizontal, 20)
                        .padding(.vertical, 24)
                    }
                }
            }
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .navigationBarLeading) {
                    Button("Отмена") {
                        isPresented = false
                    }
                    .foregroundColor(Color(.label))
                }
                
                ToolbarItem(placement: .navigationBarTrailing) {
                    Button("Готово") {
                        isPresented = false
                    }
                    .font(.system(size: 17, weight: .semibold))
                    .foregroundColor(Color(red: 0.2, green: 0.6, blue: 1.0))
                }
            }
        }
        .presentationDetents([.medium, .large])
    }
}
