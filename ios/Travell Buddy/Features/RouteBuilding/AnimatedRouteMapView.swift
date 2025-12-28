//
//  AnimatedRouteMapView.swift
//  Travell Buddy
//
//  UIViewRepresentable wrapper for MKMapView with animated route drawing.
//  Features: 3D buildings, gradual zoom out, animated route line.
//

import SwiftUI
import MapKit

// MARK: - SwiftUI Wrapper

struct AnimatedRouteMapView: UIViewRepresentable {
    let centerCoordinate: CLLocationCoordinate2D
    let visiblePOIs: [DemoPOI]
    let routeCoordinates: [CLLocationCoordinate2D]
    let latestPOIIndex: Int

    // Zoom levels: start close, gradually zoom out
    private static let initialSpan: Double = 0.015
    private static let maxSpan: Double = 0.06
    private static let spanIncrementPerPOI: Double = 0.006

    // 3D camera settings
    private static let cameraPitch: Double = 45 // Tilt angle for 3D effect
    private static let cameraAltitude: Double = 800 // Initial altitude in meters

    func makeUIView(context: Context) -> MKMapView {
        let mapView = MKMapView()
        mapView.delegate = context.coordinator

        // Configure map appearance with 3D buildings
        configureMapAppearance(mapView)

        // Set initial 3D camera
        let camera = MKMapCamera(
            lookingAtCenter: centerCoordinate,
            fromDistance: Self.cameraAltitude,
            pitch: Self.cameraPitch,
            heading: 0
        )
        mapView.setCamera(camera, animated: false)

        // Store initial state in coordinator
        context.coordinator.lastPOICount = 0
        context.coordinator.currentHeading = 0

        return mapView
    }

    func updateUIView(_ mapView: MKMapView, context: Context) {
        // Update POI annotations
        updateAnnotations(mapView, context: context)

        // Update route polyline
        updatePolyline(mapView, context: context)

        // Animate camera when new POIs added
        animateCameraIfNeeded(mapView, context: context)
    }

    func makeCoordinator() -> Coordinator {
        Coordinator(self)
    }

    // MARK: - Map Configuration

    private func configureMapAppearance(_ mapView: MKMapView) {
        // Use realistic elevation for 3D buildings
        if #available(iOS 16.0, *) {
            let config = MKStandardMapConfiguration(elevationStyle: .realistic)
            config.pointOfInterestFilter = .excludingAll
            config.showsTraffic = false
            mapView.preferredConfiguration = config
        } else {
            mapView.mapType = .mutedStandard
            mapView.pointOfInterestFilter = .excludingAll
            mapView.showsTraffic = false
        }

        // Enable 3D buildings
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

    // MARK: - Camera Animation

    private func animateCameraIfNeeded(_ mapView: MKMapView, context: Context) {
        let currentCount = visiblePOIs.count

        // Only animate when new POIs are added
        guard currentCount > context.coordinator.lastPOICount else { return }
        context.coordinator.lastPOICount = currentCount

        // Calculate new camera distance based on POI count
        // Start close, gradually zoom out
        let baseAltitude: Double = 600
        let altitudeIncrement: Double = 150
        let maxAltitude: Double = 2500
        let newAltitude = min(baseAltitude + Double(currentCount) * altitudeIncrement, maxAltitude)

        // Slowly rotate camera heading for dynamic effect
        context.coordinator.currentHeading += 8
        if context.coordinator.currentHeading >= 360 {
            context.coordinator.currentHeading = 0
        }

        // Calculate center point: either latest POI or center of all POIs
        let targetCenter: CLLocationCoordinate2D
        if let latestPOI = visiblePOIs.last {
            // Weighted center: 70% original center, 30% latest POI
            targetCenter = CLLocationCoordinate2D(
                latitude: centerCoordinate.latitude * 0.7 + latestPOI.coordinate.latitude * 0.3,
                longitude: centerCoordinate.longitude * 0.7 + latestPOI.coordinate.longitude * 0.3
            )
        } else {
            targetCenter = centerCoordinate
        }

        // Create new camera with updated parameters
        let newCamera = MKMapCamera(
            lookingAtCenter: targetCenter,
            fromDistance: newAltitude,
            pitch: Self.cameraPitch,
            heading: context.coordinator.currentHeading
        )

        // Animate camera smoothly
        UIView.animate(withDuration: 0.8, delay: 0, options: [.curveEaseInOut]) {
            mapView.setCamera(newCamera, animated: false)
        }
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

        // Camera animation state
        var lastPOICount: Int = 0
        var currentHeading: Double = 0

        // Route animation state
        var displayedRouteSegments: Int = 0

        // Dash animation
        private var dashAnimationTimer: Timer?
        private var currentDashPhase: CGFloat = 0
        private weak var currentRenderer: AnimatedPolylineRenderer?
        private weak var mapViewRef: MKMapView?

        init(_ parent: AnimatedRouteMapView) {
            self.parent = parent
            super.init()
        }

        deinit {
            stopDashAnimation()
        }

        // MARK: - Dash Animation

        func startDashAnimation(for renderer: AnimatedPolylineRenderer, mapView: MKMapView) {
            self.currentRenderer = renderer
            self.mapViewRef = mapView

            // Stop any existing animation
            stopDashAnimation()

            // Start new animation timer
            dashAnimationTimer = Timer.scheduledTimer(withTimeInterval: 0.05, repeats: true) { [weak self] _ in
                guard let self = self,
                      let renderer = self.currentRenderer else { return }

                // Update dash phase for "running dots" effect
                self.currentDashPhase += 2.0
                if self.currentDashPhase > 100 {
                    self.currentDashPhase = 0
                }

                renderer.dashPhase = self.currentDashPhase

                // Request redraw
                renderer.setNeedsDisplay()
            }
        }

        func stopDashAnimation() {
            dashAnimationTimer?.invalidate()
            dashAnimationTimer = nil
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
                renderer.animateDashes = true

                // Start dash animation
                startDashAnimation(for: renderer, mapView: mapView)

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
