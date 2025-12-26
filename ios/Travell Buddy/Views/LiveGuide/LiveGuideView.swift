//
//  LiveGuideView.swift
//  Travell Buddy
//
//  Live guide view with map.
//

import SwiftUI
import MapKit

struct LiveGuideView: View {
    @StateObject private var viewModel = LiveGuideViewModel()
    @StateObject private var locationManager = LocationManager()
    
    var body: some View {
        ZStack(alignment: .top) {
            Map(
                coordinateRegion: $locationManager.region,
                interactionModes: .all,
                showsUserLocation: true,
                userTrackingMode: .constant(.follow)
            )
            .ignoresSafeArea()
            
            if let firstPoint = viewModel.points.first {
                Text(firstPoint.name)
                    .font(.headline)
                    .padding(8)
                    .background(.thinMaterial, in: Capsule())
                    .padding()
            }
        }
        .onAppear {
            locationManager.start()
        }
        .onDisappear {
            locationManager.stop()
        }
        .navigationTitle("Я уже в путешествии")
        .navigationBarTitleDisplayMode(.inline)
    }
}

