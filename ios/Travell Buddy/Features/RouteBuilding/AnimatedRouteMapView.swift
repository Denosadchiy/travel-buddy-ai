//
//  AnimatedRouteMapView.swift
//  Travell Buddy
//
//  UIViewRepresentable wrapper for MKMapView with animated route drawing.
//

import SwiftUI
import MapKit

// MARK: - SwiftUI Wrapper

struct AnimatedRouteMapView: UIViewRepresentable {
    let centerCoordinate: CLLocationCoordinate2D
    let visiblePOIs: [DemoPOI]
    let routeCoordinates: [CLLocationCoordinate2D]
    let latestPOIIndex: Int

    func makeUIView(context: Context) -> MKMapView {
        let mapView = MKMapView()
        mapView.delegate = context.coordinator

        // Configure map appearance
        configureMapAppearance(mapView)

        // Set initial region
        let region = MKCoordinateRegion(
            center: centerCoordinate,
            span: MKCoordinateSpan(latitudeDelta: 0.04, longitudeDelta: 0.04)
        )
        mapView.setRegion(region, animated: false)

        return mapView
    }

    func updateUIView(_ mapView: MKMapView, context: Context) {
        // Update POI annotations
        updateAnnotations(mapView, context: context)

        // Update route polyline
        updatePolyline(mapView, context: context)
    }

    func makeCoordinator() -> Coordinator {
        Coordinator(self)
    }

    // MARK: - Map Configuration

    private func configureMapAppearance(_ mapView: MKMapView) {
        // Use muted standard for a cleaner, more premium look
        if #available(iOS 16.0, *) {
            let config = MKStandardMapConfiguration(elevationStyle: .flat)
            config.pointOfInterestFilter = .excludingAll
            config.showsTraffic = false
            mapView.preferredConfiguration = config
        } else {
            mapView.mapType = .mutedStandard
            mapView.pointOfInterestFilter = .excludingAll
            mapView.showsTraffic = false
        }

        // Hide UI elements for cleaner look
        mapView.showsBuildings = true
        mapView.showsCompass = false
        mapView.showsScale = false

        // Disable user interaction during loading
        mapView.isUserInteractionEnabled = false

        // Set background color
        mapView.backgroundColor = UIColor(red: 0.12, green: 0.12, blue: 0.15, alpha: 1.0)

        // Apply dark overlay effect via overrideUserInterfaceStyle
        mapView.overrideUserInterfaceStyle = .dark
    }

    // MARK: - Annotations Update

    private func updateAnnotations(_ mapView: MKMapView, context: Context) {
        let existingAnnotations = mapView.annotations.compactMap { $0 as? RouteBuildingPOIAnnotation }
        let existingIDs = Set(existingAnnotations.map { $0.poi.id })

        // Add new POIs
        for (index, poi) in visiblePOIs.enumerated() {
            if !existingIDs.contains(poi.id) {
                let annotation = RouteBuildingPOIAnnotation(poi: poi, index: index)
                mapView.addAnnotation(annotation)

                // Animate the annotation view after it's added
                DispatchQueue.main.asyncAfter(deadline: .now() + 0.05) {
                    if let view = mapView.view(for: annotation) as? POIAnnotationView {
                        view.animateAppearance()

                        // Start pulse if this is the latest POI
                        if index == self.latestPOIIndex {
                            view.startPulse()
                        }
                    }
                }
            }
        }

        // Update pulse state on annotations
        for annotation in existingAnnotations {
            if let view = mapView.view(for: annotation) as? POIAnnotationView {
                if annotation.index == latestPOIIndex {
                    view.startPulse()
                } else {
                    view.stopPulse()
                }
            }
        }
    }

    // MARK: - Polyline Update

    private func updatePolyline(_ mapView: MKMapView, context: Context) {
        // Remove existing overlays
        mapView.removeOverlays(mapView.overlays)

        guard routeCoordinates.count >= 2 else { return }

        // Create animated polyline
        let polyline = AnimatedPolyline(
            coordinates: routeCoordinates,
            count: routeCoordinates.count
        )
        polyline.isAnimating = true

        mapView.addOverlay(polyline)
    }

    // MARK: - Coordinator

    class Coordinator: NSObject, MKMapViewDelegate {
        var parent: AnimatedRouteMapView

        init(_ parent: AnimatedRouteMapView) {
            self.parent = parent
        }

        // MARK: - Annotation View

        func mapView(_ mapView: MKMapView, viewFor annotation: MKAnnotation) -> MKAnnotationView? {
            guard let poiAnnotation = annotation as? RouteBuildingPOIAnnotation else {
                return nil
            }

            let identifier = "POIAnnotation"
            let annotationView: POIAnnotationView

            if let reusedView = mapView.dequeueReusableAnnotationView(withIdentifier: identifier) as? POIAnnotationView {
                reusedView.annotation = annotation
                reusedView.configure(with: poiAnnotation.poi, index: poiAnnotation.index)
                annotationView = reusedView
            } else {
                annotationView = POIAnnotationView(annotation: annotation, reuseIdentifier: identifier)
                annotationView.configure(with: poiAnnotation.poi, index: poiAnnotation.index)
            }

            // Start hidden for animation
            annotationView.alpha = 0
            annotationView.transform = CGAffineTransform(scaleX: 0.1, y: 0.1)

            return annotationView
        }

        // MARK: - Overlay Renderer

        func mapView(_ mapView: MKMapView, rendererFor overlay: MKOverlay) -> MKOverlayRenderer {
            if let polyline = overlay as? AnimatedPolyline {
                let renderer = AnimatedPolylineRenderer(polyline: polyline)
                // Bright cyan/teal color for better visibility on dark map
                renderer.strokeColor = UIColor(red: 0.2, green: 0.85, blue: 0.9, alpha: 1.0)
                renderer.lineWidth = 5
                renderer.lineCap = .round
                renderer.lineJoin = .round
                renderer.useGradient = true

                return renderer
            }

            return MKOverlayRenderer(overlay: overlay)
        }
    }
}

// MARK: - Route Building POI Annotation

class RouteBuildingPOIAnnotation: NSObject, MKAnnotation {
    let poi: DemoPOI
    let index: Int

    var coordinate: CLLocationCoordinate2D {
        poi.coordinate
    }

    var title: String? {
        poi.name
    }

    init(poi: DemoPOI, index: Int) {
        self.poi = poi
        self.index = index
        super.init()
    }
}

// MARK: - Animated Polyline

class AnimatedPolyline: MKPolyline {
    var isAnimating: Bool = false
}
