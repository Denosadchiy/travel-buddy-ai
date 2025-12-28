//
//  POIAnnotationView.swift
//  Travell Buddy
//
//  Custom annotation view for POI markers with pulse and fade animations.
//

import UIKit
import MapKit

// MARK: - POI Annotation View

final class POIAnnotationView: MKAnnotationView {

    // MARK: - UI Elements

    private let containerView: UIView = {
        let view = UIView()
        view.backgroundColor = .white
        view.layer.cornerRadius = 24
        view.layer.shadowColor = UIColor.black.cgColor
        view.layer.shadowOffset = CGSize(width: 0, height: 4)
        view.layer.shadowRadius = 8
        view.layer.shadowOpacity = 0.35
        return view
    }()

    private let iconView: UIImageView = {
        let imageView = UIImageView()
        imageView.contentMode = .scaleAspectFit
        imageView.tintColor = .white
        return imageView
    }()

    private let numberLabel: UILabel = {
        let label = UILabel()
        label.font = .systemFont(ofSize: 12, weight: .bold)
        label.textColor = .white
        label.textAlignment = .center
        label.backgroundColor = UIColor.black.withAlphaComponent(0.6)
        label.layer.cornerRadius = 10
        label.clipsToBounds = true
        return label
    }()

    private let pulseView: UIView = {
        let view = UIView()
        view.layer.cornerRadius = 36
        view.alpha = 0
        return view
    }()

    private let glowView: UIView = {
        let view = UIView()
        view.layer.cornerRadius = 28
        view.alpha = 0
        return view
    }()

    // MARK: - Properties

    private var isPulsing = false
    private var poiIndex: Int = 0

    // MARK: - Init

    override init(annotation: MKAnnotation?, reuseIdentifier: String?) {
        super.init(annotation: annotation, reuseIdentifier: reuseIdentifier)
        setupViews()
    }

    required init?(coder aDecoder: NSCoder) {
        super.init(coder: aDecoder)
        setupViews()
    }

    // MARK: - Setup

    private func setupViews() {
        frame = CGRect(x: 0, y: 0, width: 48, height: 48)
        centerOffset = CGPoint(x: 0, y: -24)
        canShowCallout = false

        // Add pulse view (behind everything)
        addSubview(pulseView)
        pulseView.frame = CGRect(x: -12, y: -12, width: 72, height: 72)

        // Add glow view
        addSubview(glowView)
        glowView.frame = CGRect(x: -4, y: -4, width: 56, height: 56)

        // Add container
        addSubview(containerView)
        containerView.frame = bounds

        // Add icon
        containerView.addSubview(iconView)
        iconView.frame = CGRect(x: 10, y: 10, width: 28, height: 28)

        // Add number badge
        addSubview(numberLabel)
        numberLabel.frame = CGRect(x: 30, y: -4, width: 20, height: 20)
    }

    // MARK: - Configuration

    func configure(with poi: DemoPOI, index: Int = 0) {
        self.poiIndex = index

        // Set icon based on category
        let iconName = poi.category.icon
        iconView.image = UIImage(systemName: iconName)?.withConfiguration(
            UIImage.SymbolConfiguration(weight: .medium)
        )

        // Set color based on category
        let color = categoryColor(for: poi.category)
        containerView.backgroundColor = color
        iconView.tintColor = .white

        // Set glow and pulse colors
        pulseView.backgroundColor = color.withAlphaComponent(0.3)
        glowView.backgroundColor = color.withAlphaComponent(0.4)

        // Set number badge
        numberLabel.text = "\(index + 1)"
        numberLabel.isHidden = false
    }

    func configure(with poi: DemoPOI) {
        configure(with: poi, index: poiIndex)
    }

    private func categoryColor(for category: DemoPOI.POICategory) -> UIColor {
        switch category {
        case .restaurant:
            // Vibrant orange
            return UIColor(red: 1.0, green: 0.45, blue: 0.2, alpha: 1.0)
        case .attraction:
            // Vibrant purple
            return UIColor(red: 0.6, green: 0.3, blue: 0.9, alpha: 1.0)
        case .hotel:
            // Vibrant blue
            return UIColor(red: 0.2, green: 0.5, blue: 1.0, alpha: 1.0)
        case .activity:
            // Vibrant green
            return UIColor(red: 0.2, green: 0.8, blue: 0.4, alpha: 1.0)
        }
    }

    // MARK: - Animations

    func animateAppearance() {
        // Start from small and transparent
        self.transform = CGAffineTransform(scaleX: 0.1, y: 0.1)
        self.alpha = 0

        // Spring animation for bouncy appearance
        UIView.animate(
            withDuration: 0.5,
            delay: 0,
            usingSpringWithDamping: 0.5,
            initialSpringVelocity: 1.0,
            options: [.curveEaseOut]
        ) {
            self.alpha = 1
            self.transform = .identity
        }

        // Add glow effect on appear
        glowView.alpha = 0.8
        glowView.transform = CGAffineTransform(scaleX: 0.8, y: 0.8)

        UIView.animate(
            withDuration: 0.6,
            delay: 0.1,
            options: [.curveEaseOut]
        ) {
            self.glowView.transform = CGAffineTransform(scaleX: 1.3, y: 1.3)
            self.glowView.alpha = 0
        }
    }

    func startPulse() {
        guard !isPulsing else { return }
        isPulsing = true

        pulseView.alpha = 0.8
        pulseView.transform = CGAffineTransform(scaleX: 0.6, y: 0.6)

        animatePulse()
    }

    private func animatePulse() {
        guard isPulsing else { return }

        UIView.animate(
            withDuration: 1.0,
            delay: 0,
            options: [.curveEaseOut]
        ) {
            self.pulseView.transform = CGAffineTransform(scaleX: 1.8, y: 1.8)
            self.pulseView.alpha = 0
        } completion: { _ in
            guard self.isPulsing else { return }

            // Reset and repeat
            self.pulseView.transform = CGAffineTransform(scaleX: 0.6, y: 0.6)
            self.pulseView.alpha = 0.8

            // Continue pulsing
            DispatchQueue.main.asyncAfter(deadline: .now() + 0.15) {
                self.animatePulse()
            }
        }
    }

    func stopPulse() {
        isPulsing = false

        UIView.animate(withDuration: 0.3) {
            self.pulseView.alpha = 0
        }
    }

    // MARK: - Prepare for Reuse

    override func prepareForReuse() {
        super.prepareForReuse()
        stopPulse()
        alpha = 0
        transform = CGAffineTransform(scaleX: 0.1, y: 0.1)
        glowView.alpha = 0
        poiIndex = 0
    }
}
