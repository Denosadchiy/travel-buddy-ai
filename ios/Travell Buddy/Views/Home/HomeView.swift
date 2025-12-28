//
//  HomeView.swift
//  Travell Buddy
//
//  Main home screen.
//

import SwiftUI

struct HomeView: View {
    @State private var chatMessages: [ChatMessage] = [ChatMessage.welcomeMessage]
    @State private var savedTicket: FlightTicket?
    @State private var navigateToTicketInput: Bool = false
    @State private var ticketForPlanning: FlightTicket?

    var body: some View {
        ZStack {
            // Светлый градиентный фон
            LinearGradient(
                colors: [
                    Color.white,
                    Color(red: 0.95, green: 0.98, blue: 1.0)
                ],
                startPoint: .top,
                endPoint: .bottom
            )
            .ignoresSafeArea()

            ScrollView {
                VStack(alignment: .leading, spacing: 24) {
                    // Компактный чат-бар (открывается при нажатии)
                    NavigationLink(destination: ChatView(viewModel: ChatViewModel(tripId: UUID(), initialMessages: chatMessages))) {
                        ChatBarView(messages: chatMessages)
                    }
                    .buttonStyle(.plain)
                    .padding(.top, 8)

                    HomeHeaderView()

                    greetingSection

                    // Виджет билета
                    flightTicketWidget

                    mainActionCardsSection

                    myTripsSection
                }
                .padding(.horizontal, 20)
                .padding(.bottom, 24)
            }
        }
        .navigationBarHidden(true)
        .onAppear {
            savedTicket = FlightTicketStorage.shared.load()
        }
        .background(
            Group {
                NavigationLink(
                    destination: FlightTicketInputView(),
                    isActive: $navigateToTicketInput
                ) {
                    EmptyView()
                }

                if let ticket = ticketForPlanning {
                    NavigationLink(
                        destination: NewTripView(prefilledTicket: ticket),
                        isActive: Binding(
                            get: { ticketForPlanning != nil },
                            set: { if !$0 { ticketForPlanning = nil } }
                        )
                    ) {
                        EmptyView()
                    }
                }
            }
            .hidden()
        )
    }
    
    // MARK: Flight Ticket Widget

    private var flightTicketWidget: some View {
        FlightTicketWidget(
            savedTicket: savedTicket,
            onAddTicket: {
                navigateToTicketInput = true
            },
            onUseTicket: { ticket in
                ticketForPlanning = ticket
            }
        )
    }

    // MARK: Greeting

    private var greetingSection: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack(alignment: .top, spacing: 8) {
                Text("Привет! Куда отправимся дальше?")
                    .font(.system(size: 30, weight: .bold, design: .rounded))
                    .foregroundColor(Color(.label))
                    .fixedSize(horizontal: false, vertical: true)
                
                Text("✈️")
                    .font(.system(size: 26))
                    .padding(.top, 4)
            }
            
            Text("Соберу для тебя идеальный маршрут и помогу в пути.")
                .font(.system(size: 16))
                .foregroundColor(Color(.secondaryLabel))
                .fixedSize(horizontal: false, vertical: true)
        }
    }
    
    // MARK: Main cards
    
    private var mainActionCardsSection: some View {
        VStack(spacing: 16) {
            NavigationLink(destination: NewTripView()) {
                MainActionCard(
                    title: "Спланировать поездку",
                    subtitle: "Выбери город, даты и интересы — я соберу маршрут.",
                    gradient: Gradient(colors: [
                        Color(red: 1.0, green: 0.65, blue: 0.40),
                        Color(red: 1.0, green: 0.45, blue: 0.35)
                    ]),
                    systemImageName: "bag.fill"
                )
            }
            .buttonStyle(.plain)
            
            NavigationLink(destination: LiveGuideView()) {
                MainActionCard(
                    title: "Я уже в путешествии",
                    subtitle: "Включить гида рядом: места поблизости, подсказки и советы.",
                    gradient: Gradient(colors: [
                        Color(red: 0.05, green: 0.78, blue: 0.78),
                        Color(red: 0.00, green: 0.60, blue: 0.80)
                    ]),
                    systemImageName: "location.fill"
                )
            }
            .buttonStyle(.plain)
        }
    }
    
    // MARK: My trips
    
    private var myTripsSection: some View {
        VStack(alignment: .leading, spacing: 16) {
            HStack {
                Text("Мои поездки")
                    .font(.system(size: 18, weight: .semibold, design: .rounded))
                    .foregroundColor(Color(.label))
                
                Spacer()
                
                Button(action: {}) {
                    Text("Все")
                        .font(.system(size: 15, weight: .semibold))
                        .foregroundColor(Color(red: 1.0, green: 0.55, blue: 0.30))
                }
                .buttonStyle(.plain)
            }
            
            ScrollView(.horizontal, showsIndicators: false) {
                HStack(spacing: 16) {
                    TripCard(
                        cityAndMonth: "Стамбул, март",
                        dateRange: "12–18 марта 2026",
                        statusText: "Запланировано"
                    )
                    
                    TripCard(
                        cityAndMonth: "Барселона, июнь",
                        dateRange: "3–9 июня 2026",
                        statusText: "Запланировано"
                    )
                }
                .padding(.vertical, 4)
            }
        }
        .padding(.top, 8)
    }
}
