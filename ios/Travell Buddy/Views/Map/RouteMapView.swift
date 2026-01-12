//
//  RouteMapView.swift
//  Travell Buddy
//
//  Map view displaying POI annotations and route polylines for a trip day.
//  Uses MKMapView via UIViewRepresentable to support overlay rendering.
//  Supports annotation clustering to prevent POI overlap at far zoom levels.
//
//  Discovery note: Existing LiveGuideView uses SwiftUI Map for user location tracking.
//  This is a different use case requiring polyline overlays, so we use MKMapView directly.
//

import SwiftUI
import MapKit

/// A map view that displays POI pins and route polylines for trip activities.
/// Includes clustering support for dense POI areas.
struct RouteMapView: UIViewRepresentable {
    let activities: [TripActivity]

    func makeUIView(context: Context) -> MKMapView {
        let mapView = MKMapView()
        mapView.delegate = context.coordinator
        mapView.showsUserLocation = false
        mapView.mapType = .standard

        // Register annotation views for clustering
        mapView.register(
            ClusteredPOIAnnotationView.self,
            forAnnotationViewWithReuseIdentifier: MKMapViewDefaultAnnotationViewReuseIdentifier
        )
        mapView.register(
            POIClusterAnnotationView.self,
            forAnnotationViewWithReuseIdentifier: MKMapViewDefaultClusterAnnotationViewReuseIdentifier
        )

        return mapView
    }

    func updateUIView(_ mapView: MKMapView, context: Context) {
        // Clear existing annotations and overlays
        mapView.removeAnnotations(mapView.annotations)
        mapView.removeOverlays(mapView.overlays)

        // Add POI annotations
        var coordinates: [CLLocationCoordinate2D] = []
        for (index, activity) in activities.enumerated() {
            guard let coordinate = activity.coordinate else { continue }

            let annotation = POIAnnotation(
                coordinate: coordinate,
                title: activity.title,
                subtitle: activity.time,
                index: index
            )
            mapView.addAnnotation(annotation)
            coordinates.append(coordinate)

            // Add polyline from previous activity if available
            if let polylineString = activity.travelPolyline,
               !polylineString.isEmpty {
                let polylineCoords = PolylineDecoder.decode(polylineString)
                if polylineCoords.count >= 2 {
                    let polyline = MKPolyline(coordinates: polylineCoords, count: polylineCoords.count)
                    mapView.addOverlay(polyline)
                }
            }
        }

        // Fit map to show all annotations and overlays
        fitMapToContent(mapView, coordinates: coordinates)
    }

    func makeCoordinator() -> Coordinator {
        Coordinator()
    }

    /// Adjusts the map region to fit all coordinates with padding.
    private func fitMapToContent(_ mapView: MKMapView, coordinates: [CLLocationCoordinate2D]) {
        guard !coordinates.isEmpty else { return }

        if coordinates.count == 1 {
            // Single point - center with reasonable zoom
            let region = MKCoordinateRegion(
                center: coordinates[0],
                span: MKCoordinateSpan(latitudeDelta: 0.02, longitudeDelta: 0.02)
            )
            mapView.setRegion(region, animated: false)
            return
        }

        // Calculate bounding box for all coordinates
        var minLat = coordinates[0].latitude
        var maxLat = coordinates[0].latitude
        var minLon = coordinates[0].longitude
        var maxLon = coordinates[0].longitude

        for coord in coordinates {
            minLat = min(minLat, coord.latitude)
            maxLat = max(maxLat, coord.latitude)
            minLon = min(minLon, coord.longitude)
            maxLon = max(maxLon, coord.longitude)
        }

        // Also include polyline coordinates
        for overlay in mapView.overlays {
            if let polyline = overlay as? MKPolyline {
                let rect = polyline.boundingMapRect
                let topLeft = MKMapPoint(x: rect.minX, y: rect.minY)
                let bottomRight = MKMapPoint(x: rect.maxX, y: rect.maxY)
                let topLeftCoord = topLeft.coordinate
                let bottomRightCoord = bottomRight.coordinate

                minLat = min(minLat, topLeftCoord.latitude, bottomRightCoord.latitude)
                maxLat = max(maxLat, topLeftCoord.latitude, bottomRightCoord.latitude)
                minLon = min(minLon, topLeftCoord.longitude, bottomRightCoord.longitude)
                maxLon = max(maxLon, topLeftCoord.longitude, bottomRightCoord.longitude)
            }
        }

        // Add padding
        let latPadding = (maxLat - minLat) * 0.2
        let lonPadding = (maxLon - minLon) * 0.2

        let region = MKCoordinateRegion(
            center: CLLocationCoordinate2D(
                latitude: (minLat + maxLat) / 2,
                longitude: (minLon + maxLon) / 2
            ),
            span: MKCoordinateSpan(
                latitudeDelta: max((maxLat - minLat) + latPadding, 0.01),
                longitudeDelta: max((maxLon - minLon) + lonPadding, 0.01)
            )
        )
        mapView.setRegion(region, animated: false)
    }

    // MARK: - Coordinator

    class Coordinator: NSObject, MKMapViewDelegate {

        func mapView(_ mapView: MKMapView, rendererFor overlay: MKOverlay) -> MKOverlayRenderer {
            if let polyline = overlay as? MKPolyline {
                let renderer = MKPolylineRenderer(polyline: polyline)
                renderer.strokeColor = UIColor(Color.travelBuddyOrange)
                renderer.lineWidth = 4
                renderer.lineCap = .round
                renderer.lineJoin = .round
                return renderer
            }
            return MKOverlayRenderer(overlay: overlay)
        }

        func mapView(_ mapView: MKMapView, viewFor annotation: MKAnnotation) -> MKAnnotationView? {
            // Don't customize user location
            if annotation is MKUserLocation { return nil }

            // Handle cluster annotation
            if let cluster = annotation as? MKClusterAnnotation {
                let view = mapView.dequeueReusableAnnotationView(
                    withIdentifier: MKMapViewDefaultClusterAnnotationViewReuseIdentifier,
                    for: annotation
                ) as? POIClusterAnnotationView
                view?.configure(with: cluster.memberAnnotations.count)
                return view
            }

            // Handle POI annotation
            guard let poiAnnotation = annotation as? POIAnnotation else { return nil }

            let view = mapView.dequeueReusableAnnotationView(
                withIdentifier: MKMapViewDefaultAnnotationViewReuseIdentifier,
                for: annotation
            ) as? ClusteredPOIAnnotationView
            view?.configure(with: poiAnnotation)
            return view
        }

        // MARK: - Cluster Tap → Auto-Zoom

        func mapView(_ mapView: MKMapView, didSelect view: MKAnnotationView) {
            guard let cluster = view.annotation as? MKClusterAnnotation else { return }

            // Zoom to show all member annotations
            mapView.showAnnotations(cluster.memberAnnotations, animated: true)

            // Deselect after zoom
            mapView.deselectAnnotation(cluster, animated: false)
        }
    }
}

// MARK: - Clustered POI Annotation View

/// Custom annotation view for POI markers with clustering support.
final class ClusteredPOIAnnotationView: MKMarkerAnnotationView {

    static let clusteringIdentifier = "poi"

    override init(annotation: MKAnnotation?, reuseIdentifier: String?) {
        super.init(annotation: annotation, reuseIdentifier: reuseIdentifier)
        clusteringIdentifier = Self.clusteringIdentifier
        displayPriority = .defaultHigh
        canShowCallout = true
    }

    required init?(coder aDecoder: NSCoder) {
        fatalError("init(coder:) has not been implemented")
    }

    func configure(with poiAnnotation: POIAnnotation) {
        annotation = poiAnnotation
        markerTintColor = UIColor(Color.travelBuddyOrange)
        glyphText = "\(poiAnnotation.index + 1)"
    }
}

// MARK: - POI Cluster Annotation View

/// Custom annotation view for POI clusters.
final class POIClusterAnnotationView: MKAnnotationView {

    private let countLabel: UILabel = {
        let label = UILabel()
        label.textAlignment = .center
        label.font = .systemFont(ofSize: 14, weight: .bold)
        label.textColor = .white
        label.translatesAutoresizingMaskIntoConstraints = false
        return label
    }()

    private let backgroundCircle: UIView = {
        let view = UIView()
        view.backgroundColor = UIColor(Color.travelBuddyOrange)
        view.layer.borderColor = UIColor.white.cgColor
        view.layer.borderWidth = 2
        view.translatesAutoresizingMaskIntoConstraints = false
        return view
    }()

    override init(annotation: MKAnnotation?, reuseIdentifier: String?) {
        super.init(annotation: annotation, reuseIdentifier: reuseIdentifier)
        setupView()
    }

    required init?(coder aDecoder: NSCoder) {
        fatalError("init(coder:) has not been implemented")
    }

    private func setupView() {
        displayPriority = .required
        collisionMode = .circle

        addSubview(backgroundCircle)
        addSubview(countLabel)

        let size: CGFloat = 40

        NSLayoutConstraint.activate([
            backgroundCircle.widthAnchor.constraint(equalToConstant: size),
            backgroundCircle.heightAnchor.constraint(equalToConstant: size),
            backgroundCircle.centerXAnchor.constraint(equalTo: centerXAnchor),
            backgroundCircle.centerYAnchor.constraint(equalTo: centerYAnchor),

            countLabel.centerXAnchor.constraint(equalTo: backgroundCircle.centerXAnchor),
            countLabel.centerYAnchor.constraint(equalTo: backgroundCircle.centerYAnchor),
        ])

        backgroundCircle.layer.cornerRadius = size / 2

        frame = CGRect(x: 0, y: 0, width: size, height: size)
        centerOffset = CGPoint(x: 0, y: -size / 2)

        // Add shadow
        layer.shadowColor = UIColor.black.cgColor
        layer.shadowOffset = CGSize(width: 0, height: 2)
        layer.shadowRadius = 4
        layer.shadowOpacity = 0.3
    }

    func configure(with count: Int) {
        countLabel.text = "\(count)"
    }
}

// MARK: - POI Annotation

/// Custom annotation for POI markers.
class POIAnnotation: NSObject, MKAnnotation {
    let coordinate: CLLocationCoordinate2D
    let title: String?
    let subtitle: String?
    let index: Int

    init(coordinate: CLLocationCoordinate2D, title: String?, subtitle: String?, index: Int) {
        self.coordinate = coordinate
        self.title = title
        self.subtitle = subtitle
        self.index = index
    }
}

// MARK: - Empty State View

/// Placeholder view shown when no map data is available.
struct NoMapDataView: View {
    var body: some View {
        VStack(spacing: 12) {
            Image(systemName: "map")
                .font(.system(size: 40))
                .foregroundColor(.secondary)
            Text("Нет данных для карты")
                .font(.system(size: 16, weight: .medium))
                .foregroundColor(.secondary)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .background(Color(.systemGroupedBackground))
    }
}
