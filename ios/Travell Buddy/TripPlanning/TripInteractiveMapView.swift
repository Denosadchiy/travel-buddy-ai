//
//  TripInteractiveMapView.swift
//  Travell Buddy
//
//  Interactive map with zoom, locate, and fit controls for trip day POIs.
//  Uses MKMapView via UIViewRepresentable for annotation clustering support.
//

import SwiftUI
import MapKit
import CoreLocation

struct TripInteractiveMapView: View {
    let activities: [TripActivity]
    let fallbackCoordinate: CLLocationCoordinate2D?
    @Binding var isInteracting: Bool

    @StateObject private var locationManager = MapLocationManager()

    var body: some View {
        ZStack(alignment: .topTrailing) {
            ClusteredInteractiveMapView(
                activities: activities,
                fallbackCoordinate: fallbackCoordinate,
                isInteracting: $isInteracting,
                locationManager: locationManager
            )

            mapControls
                .padding(12)
        }
    }

    private var mapControls: some View {
        VStack(spacing: 10) {
            mapControlButton(systemName: "plus") {
                NotificationCenter.default.post(name: .mapZoomIn, object: nil)
            }
            mapControlButton(systemName: "minus") {
                NotificationCenter.default.post(name: .mapZoomOut, object: nil)
            }
            mapControlButton(systemName: "location") {
                NotificationCenter.default.post(
                    name: .mapCenterOnUser,
                    object: locationManager
                )
            }
            mapControlButton(systemName: "arrow.up.left.and.arrow.down.right") {
                NotificationCenter.default.post(name: .mapFitAll, object: nil)
            }
        }
    }

    private func mapControlButton(systemName: String, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            Image(systemName: systemName)
                .font(.system(size: 16, weight: .semibold))
                .foregroundColor(.white)
                .frame(width: 44, height: 44)
                .background(
                    Circle()
                        .fill(Color.black.opacity(0.35))
                        .background(.ultraThinMaterial, in: Circle())
                )
                .overlay(
                    Circle()
                        .stroke(Color.white.opacity(0.12), lineWidth: 1)
                )
        }
        .buttonStyle(.plain)
    }
}

// MARK: - Notification Names for Map Controls

extension Notification.Name {
    static let mapZoomIn = Notification.Name("mapZoomIn")
    static let mapZoomOut = Notification.Name("mapZoomOut")
    static let mapCenterOnUser = Notification.Name("mapCenterOnUser")
    static let mapFitAll = Notification.Name("mapFitAll")
}

// MARK: - Clustered Interactive Map View (MKMapView)

/// UIViewRepresentable wrapper for MKMapView with clustering support.
private struct ClusteredInteractiveMapView: UIViewRepresentable {
    let activities: [TripActivity]
    let fallbackCoordinate: CLLocationCoordinate2D?
    @Binding var isInteracting: Bool
    let locationManager: MapLocationManager

    func makeUIView(context: Context) -> MKMapView {
        let mapView = MKMapView()
        mapView.delegate = context.coordinator
        mapView.showsUserLocation = false
        mapView.mapType = .standard
        mapView.isZoomEnabled = true
        mapView.isScrollEnabled = true
        mapView.isRotateEnabled = false
        mapView.isPitchEnabled = false

        // Register annotation views for clustering
        mapView.register(
            InteractivePOIAnnotationView.self,
            forAnnotationViewWithReuseIdentifier: MKMapViewDefaultAnnotationViewReuseIdentifier
        )
        mapView.register(
            InteractivePOIClusterView.self,
            forAnnotationViewWithReuseIdentifier: MKMapViewDefaultClusterAnnotationViewReuseIdentifier
        )

        // Subscribe to control notifications
        context.coordinator.subscribeToNotifications(mapView: mapView)

        // Set initial region
        let initialCenter = fallbackCoordinate ?? CLLocationCoordinate2D(latitude: 0, longitude: 0)
        let region = MKCoordinateRegion(
            center: initialCenter,
            span: MKCoordinateSpan(latitudeDelta: 0.08, longitudeDelta: 0.08)
        )
        mapView.setRegion(region, animated: false)

        return mapView
    }

    func updateUIView(_ mapView: MKMapView, context: Context) {
        // Track current activity IDs to detect changes
        let newActivityIDs = Set(activities.map { $0.id })
        let oldActivityIDs = context.coordinator.currentActivityIDs

        // Only update if activities changed
        guard newActivityIDs != oldActivityIDs else { return }
        context.coordinator.currentActivityIDs = newActivityIDs

        // Remove old annotations (except user location)
        let oldAnnotations = mapView.annotations.filter { !($0 is MKUserLocation) }
        mapView.removeAnnotations(oldAnnotations)

        // Add new POI annotations
        var coordinates: [CLLocationCoordinate2D] = []
        for (index, activity) in activities.enumerated() {
            guard let coordinate = activity.coordinate else { continue }

            let annotation = InteractivePOIAnnotation(
                id: activity.id,
                coordinate: coordinate,
                title: activity.title,
                index: index + 1
            )
            mapView.addAnnotation(annotation)
            coordinates.append(coordinate)
        }

        // Store coordinates for fit-all
        context.coordinator.allCoordinates = coordinates

        // Fit to show all points
        if !coordinates.isEmpty {
            context.coordinator.fitAllPoints(mapView: mapView, animated: true)
        }
    }

    func makeCoordinator() -> Coordinator {
        Coordinator(isInteracting: $isInteracting, locationManager: locationManager)
    }

    // MARK: - Coordinator

    class Coordinator: NSObject, MKMapViewDelegate {
        @Binding var isInteracting: Bool
        let locationManager: MapLocationManager
        var currentActivityIDs: Set<UUID> = []
        var allCoordinates: [CLLocationCoordinate2D] = []
        private var notificationObservers: [NSObjectProtocol] = []

        init(isInteracting: Binding<Bool>, locationManager: MapLocationManager) {
            self._isInteracting = isInteracting
            self.locationManager = locationManager
            super.init()
        }

        deinit {
            notificationObservers.forEach { NotificationCenter.default.removeObserver($0) }
        }

        func subscribeToNotifications(mapView: MKMapView) {
            let zoomIn = NotificationCenter.default.addObserver(
                forName: .mapZoomIn, object: nil, queue: .main
            ) { [weak mapView] _ in
                guard let mapView = mapView else { return }
                var region = mapView.region
                region.span.latitudeDelta = max(region.span.latitudeDelta * 0.7, 0.002)
                region.span.longitudeDelta = max(region.span.longitudeDelta * 0.7, 0.002)
                mapView.setRegion(region, animated: true)
            }

            let zoomOut = NotificationCenter.default.addObserver(
                forName: .mapZoomOut, object: nil, queue: .main
            ) { [weak mapView] _ in
                guard let mapView = mapView else { return }
                var region = mapView.region
                region.span.latitudeDelta = min(region.span.latitudeDelta * 1.3, 60)
                region.span.longitudeDelta = min(region.span.longitudeDelta * 1.3, 60)
                mapView.setRegion(region, animated: true)
            }

            let centerOnUser = NotificationCenter.default.addObserver(
                forName: .mapCenterOnUser, object: nil, queue: .main
            ) { [weak mapView, weak self] notification in
                guard let mapView = mapView,
                      let locationManager = notification.object as? MapLocationManager else { return }

                if locationManager.authorizationStatus == .notDetermined {
                    locationManager.requestAuthorization()
                }

                if locationManager.isAuthorized, locationManager.lastLocation == nil {
                    locationManager.requestLocation()
                }

                guard let location = locationManager.lastLocation else { return }
                let region = MKCoordinateRegion(
                    center: location.coordinate,
                    span: MKCoordinateSpan(latitudeDelta: 0.02, longitudeDelta: 0.02)
                )
                mapView.setRegion(region, animated: true)
            }

            let fitAll = NotificationCenter.default.addObserver(
                forName: .mapFitAll, object: nil, queue: .main
            ) { [weak mapView, weak self] _ in
                guard let mapView = mapView, let self = self else { return }
                self.fitAllPoints(mapView: mapView, animated: true)
            }

            notificationObservers = [zoomIn, zoomOut, centerOnUser, fitAll]
        }

        func fitAllPoints(mapView: MKMapView, animated: Bool) {
            guard !allCoordinates.isEmpty else { return }

            var rect = MKMapRect.null
            allCoordinates.forEach { coordinate in
                let point = MKMapPoint(coordinate)
                rect = rect.union(MKMapRect(origin: point, size: MKMapSize(width: 0, height: 0)))
            }

            guard !rect.isNull, !rect.isEmpty else { return }

            let paddingFactor = 0.25
            let paddedRect = rect.insetBy(dx: -rect.size.width * paddingFactor, dy: -rect.size.height * paddingFactor)
            mapView.setVisibleMapRect(paddedRect, animated: animated)
        }

        // MARK: - MKMapViewDelegate

        func mapView(_ mapView: MKMapView, viewFor annotation: MKAnnotation) -> MKAnnotationView? {
            if annotation is MKUserLocation { return nil }

            // Handle cluster annotation
            if let cluster = annotation as? MKClusterAnnotation {
                let view = mapView.dequeueReusableAnnotationView(
                    withIdentifier: MKMapViewDefaultClusterAnnotationViewReuseIdentifier,
                    for: annotation
                ) as? InteractivePOIClusterView
                view?.configure(with: cluster.memberAnnotations.count)
                return view
            }

            // Handle POI annotation
            guard let poiAnnotation = annotation as? InteractivePOIAnnotation else { return nil }

            let view = mapView.dequeueReusableAnnotationView(
                withIdentifier: MKMapViewDefaultAnnotationViewReuseIdentifier,
                for: annotation
            ) as? InteractivePOIAnnotationView
            view?.configure(with: poiAnnotation)
            return view
        }

        // MARK: - Cluster Tap → Auto-Zoom

        func mapView(_ mapView: MKMapView, didSelect view: MKAnnotationView) {
            guard let cluster = view.annotation as? MKClusterAnnotation else { return }

            // Zoom to show all member annotations with padding
            let members = cluster.memberAnnotations
            mapView.showAnnotations(members, animated: true)

            // Deselect after zoom
            mapView.deselectAnnotation(cluster, animated: false)
        }

        // MARK: - Interaction Tracking

        func mapView(_ mapView: MKMapView, regionWillChangeAnimated animated: Bool) {
            isInteracting = true
        }

        func mapView(_ mapView: MKMapView, regionDidChangeAnimated animated: Bool) {
            isInteracting = false
        }
    }
}

// MARK: - Interactive POI Annotation

private class InteractivePOIAnnotation: NSObject, MKAnnotation {
    let id: UUID
    let coordinate: CLLocationCoordinate2D
    let title: String?
    let index: Int

    init(id: UUID, coordinate: CLLocationCoordinate2D, title: String?, index: Int) {
        self.id = id
        self.coordinate = coordinate
        self.title = title
        self.index = index
        super.init()
    }
}

// MARK: - Interactive POI Annotation View

private final class InteractivePOIAnnotationView: MKAnnotationView {

    static let clusteringIdentifier = "interactivePOI"

    private let containerView: UIView = {
        let view = UIView()
        view.backgroundColor = UIColor.black.withAlphaComponent(0.55)
        view.layer.borderColor = UIColor.white.withAlphaComponent(0.2).cgColor
        view.layer.borderWidth = 1
        view.translatesAutoresizingMaskIntoConstraints = false
        return view
    }()

    private let indexLabel: UILabel = {
        let label = UILabel()
        label.textAlignment = .center
        label.font = .systemFont(ofSize: 12, weight: .bold)
        label.textColor = .white
        label.translatesAutoresizingMaskIntoConstraints = false
        return label
    }()

    override init(annotation: MKAnnotation?, reuseIdentifier: String?) {
        super.init(annotation: annotation, reuseIdentifier: reuseIdentifier)
        clusteringIdentifier = Self.clusteringIdentifier
        displayPriority = .defaultHigh
        collisionMode = .circle
        setupView()
    }

    required init?(coder aDecoder: NSCoder) {
        fatalError("init(coder:) has not been implemented")
    }

    private func setupView() {
        let size: CGFloat = 30

        addSubview(containerView)
        containerView.addSubview(indexLabel)

        NSLayoutConstraint.activate([
            containerView.widthAnchor.constraint(equalToConstant: size),
            containerView.heightAnchor.constraint(equalToConstant: size),
            containerView.centerXAnchor.constraint(equalTo: centerXAnchor),
            containerView.centerYAnchor.constraint(equalTo: centerYAnchor),

            indexLabel.centerXAnchor.constraint(equalTo: containerView.centerXAnchor),
            indexLabel.centerYAnchor.constraint(equalTo: containerView.centerYAnchor),
        ])

        containerView.layer.cornerRadius = size / 2

        frame = CGRect(x: 0, y: 0, width: size, height: size)
        centerOffset = CGPoint(x: 0, y: -size / 2)

        // Shadow
        layer.shadowColor = UIColor.black.cgColor
        layer.shadowOffset = CGSize(width: 0, height: 4)
        layer.shadowRadius = 6
        layer.shadowOpacity = 0.35
    }

    func configure(with annotation: InteractivePOIAnnotation) {
        self.annotation = annotation
        indexLabel.text = "\(annotation.index)"
    }
}

// MARK: - Interactive POI Cluster View

private final class InteractivePOIClusterView: MKAnnotationView {

    private let containerView: UIView = {
        let view = UIView()
        view.backgroundColor = UIColor(Color.travelBuddyOrange)
        view.layer.borderColor = UIColor.white.cgColor
        view.layer.borderWidth = 2
        view.translatesAutoresizingMaskIntoConstraints = false
        return view
    }()

    private let countLabel: UILabel = {
        let label = UILabel()
        label.textAlignment = .center
        label.font = .systemFont(ofSize: 14, weight: .bold)
        label.textColor = .white
        label.translatesAutoresizingMaskIntoConstraints = false
        return label
    }()

    override init(annotation: MKAnnotation?, reuseIdentifier: String?) {
        super.init(annotation: annotation, reuseIdentifier: reuseIdentifier)
        displayPriority = .required
        collisionMode = .circle
        setupView()
    }

    required init?(coder aDecoder: NSCoder) {
        fatalError("init(coder:) has not been implemented")
    }

    private func setupView() {
        let size: CGFloat = 40

        addSubview(containerView)
        containerView.addSubview(countLabel)

        NSLayoutConstraint.activate([
            containerView.widthAnchor.constraint(equalToConstant: size),
            containerView.heightAnchor.constraint(equalToConstant: size),
            containerView.centerXAnchor.constraint(equalTo: centerXAnchor),
            containerView.centerYAnchor.constraint(equalTo: centerYAnchor),

            countLabel.centerXAnchor.constraint(equalTo: containerView.centerXAnchor),
            countLabel.centerYAnchor.constraint(equalTo: containerView.centerYAnchor),
        ])

        containerView.layer.cornerRadius = size / 2

        frame = CGRect(x: 0, y: 0, width: size, height: size)
        centerOffset = CGPoint(x: 0, y: -size / 2)

        // Shadow
        layer.shadowColor = UIColor.black.cgColor
        layer.shadowOffset = CGSize(width: 0, height: 2)
        layer.shadowRadius = 4
        layer.shadowOpacity = 0.3
    }

    func configure(with count: Int) {
        countLabel.text = "\(count)"
    }
}

final class MapLocationManager: NSObject, ObservableObject, CLLocationManagerDelegate {
    @Published private(set) var authorizationStatus: CLAuthorizationStatus = .notDetermined
    @Published private(set) var lastLocation: CLLocation?

    private let manager = CLLocationManager()

    override init() {
        super.init()
        manager.delegate = self
        manager.desiredAccuracy = kCLLocationAccuracyBest
    }

    func requestAuthorization() {
        manager.requestWhenInUseAuthorization()
        manager.requestLocation()
    }

    func requestLocation() {
        manager.requestLocation()
    }

    var isAuthorized: Bool {
        authorizationStatus == .authorizedWhenInUse || authorizationStatus == .authorizedAlways
    }

    func locationManager(_ manager: CLLocationManager, didChangeAuthorization status: CLAuthorizationStatus) {
        authorizationStatus = status
        if status == .authorizedWhenInUse || status == .authorizedAlways {
            manager.requestLocation()
        }
    }

    func locationManager(_ manager: CLLocationManager, didUpdateLocations locations: [CLLocation]) {
        lastLocation = locations.last
    }

    func locationManager(_ manager: CLLocationManager, didFailWithError error: Error) {
        print("📍 Location error: \(error.localizedDescription)")
    }
}
