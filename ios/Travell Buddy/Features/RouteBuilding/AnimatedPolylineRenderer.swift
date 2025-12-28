//
//  AnimatedPolylineRenderer.swift
//  Travell Buddy
//
//  Custom polyline renderer with gradient effect and dash animation for route visualization.
//

import UIKit
import MapKit

// MARK: - Animated Polyline Renderer

final class AnimatedPolylineRenderer: MKPolylineRenderer {

    // MARK: - Properties

    /// Whether to use gradient coloring
    var useGradient: Bool = true

    /// Whether to animate dashes (running dots effect)
    var animateDashes: Bool = true

    /// Current dash phase for animation
    var dashPhase: CGFloat = 0

    /// Gradient colors (cyan to purple)
    private let gradientColors: [UIColor] = [
        UIColor(red: 0.2, green: 0.85, blue: 0.9, alpha: 1.0),   // Cyan
        UIColor(red: 0.4, green: 0.6, blue: 0.95, alpha: 1.0),  // Blue
        UIColor(red: 0.65, green: 0.4, blue: 0.95, alpha: 1.0)  // Purple
    ]

    /// Secondary glow color
    private let glowColor = UIColor(red: 0.3, green: 0.9, blue: 1.0, alpha: 0.5)

    /// Shadow properties for depth effect
    private let shadowColor = UIColor.black.withAlphaComponent(0.4)
    private let shadowOffset = CGSize(width: 0, height: 3)

    /// Dash pattern for animated dots
    private let dashPattern: [CGFloat] = [12, 8]

    // MARK: - Drawing

    override func draw(_ mapRect: MKMapRect, zoomScale: MKZoomScale, in context: CGContext) {
        guard let polyline = overlay as? MKPolyline else {
            super.draw(mapRect, zoomScale: zoomScale, in: context)
            return
        }

        let path = createPath(for: polyline, zoomScale: zoomScale)

        // Draw glow effect
        drawGlow(path: path, in: context, zoomScale: zoomScale)

        // Draw shadow
        drawShadow(path: path, in: context, zoomScale: zoomScale)

        // Draw main stroke with gradient
        if useGradient {
            drawGradientStroke(path: path, in: context, zoomScale: zoomScale)
        } else {
            drawSolidStroke(path: path, in: context, zoomScale: zoomScale)
        }

        // Draw animated dashes on top
        if animateDashes {
            drawAnimatedDashes(path: path, in: context, zoomScale: zoomScale)
        }
    }

    // MARK: - Path Creation

    private func createPath(for polyline: MKPolyline, zoomScale: MKZoomScale) -> CGPath {
        let path = CGMutablePath()

        let pointCount = polyline.pointCount
        guard pointCount > 0 else { return path }

        // Get MKMapPoints directly from polyline
        let mapPoints = polyline.points()

        // Convert to renderer points
        var cgPoints: [CGPoint] = []
        for i in 0..<pointCount {
            let mapPoint = mapPoints[i]
            cgPoints.append(self.point(for: mapPoint))
        }

        guard !cgPoints.isEmpty else { return path }

        // Move to first point
        path.move(to: cgPoints[0])

        // Draw straight lines from point to point
        for i in 1..<cgPoints.count {
            path.addLine(to: cgPoints[i])
        }

        return path
    }

    // MARK: - Drawing Helpers

    private func drawGlow(path: CGPath, in context: CGContext, zoomScale: MKZoomScale) {
        context.saveGState()

        let adjustedWidth = (lineWidth / zoomScale) * 3

        context.setLineWidth(adjustedWidth)
        context.setLineCap(.round)
        context.setLineJoin(.round)
        context.setStrokeColor(gradientColors[0].withAlphaComponent(0.3).cgColor)

        context.addPath(path)
        context.strokePath()

        context.restoreGState()
    }

    private func drawShadow(path: CGPath, in context: CGContext, zoomScale: MKZoomScale) {
        context.saveGState()

        let adjustedWidth = lineWidth / zoomScale

        context.setLineWidth(adjustedWidth + 2)
        context.setLineCap(.round)
        context.setLineJoin(.round)
        context.setStrokeColor(shadowColor.cgColor)

        // Offset for shadow
        context.translateBy(
            x: shadowOffset.width / zoomScale,
            y: shadowOffset.height / zoomScale
        )

        context.addPath(path)
        context.strokePath()

        context.restoreGState()
    }

    private func drawGradientStroke(path: CGPath, in context: CGContext, zoomScale: MKZoomScale) {
        context.saveGState()

        let adjustedWidth = lineWidth / zoomScale

        context.setLineWidth(adjustedWidth)
        context.setLineCap(.round)
        context.setLineJoin(.round)

        // Create gradient
        let cgColors = gradientColors.map { $0.cgColor } as CFArray
        guard let gradient = CGGradient(
            colorsSpace: CGColorSpaceCreateDeviceRGB(),
            colors: cgColors,
            locations: [0.0, 0.5, 1.0]
        ) else {
            drawSolidStroke(path: path, in: context, zoomScale: zoomScale)
            context.restoreGState()
            return
        }

        // Clip to path and draw gradient
        context.addPath(path)
        context.replacePathWithStrokedPath()
        context.clip()

        let bounds = path.boundingBox
        context.drawLinearGradient(
            gradient,
            start: CGPoint(x: bounds.minX, y: bounds.minY),
            end: CGPoint(x: bounds.maxX, y: bounds.maxY),
            options: [.drawsBeforeStartLocation, .drawsAfterEndLocation]
        )

        context.restoreGState()
    }

    private func drawSolidStroke(path: CGPath, in context: CGContext, zoomScale: MKZoomScale) {
        context.saveGState()

        let adjustedWidth = lineWidth / zoomScale

        context.setLineWidth(adjustedWidth)
        context.setLineCap(.round)
        context.setLineJoin(.round)
        context.setStrokeColor((strokeColor ?? gradientColors[0]).cgColor)

        context.addPath(path)
        context.strokePath()

        context.restoreGState()
    }

    /// Draw animated dashes on top of the route line (running dots effect)
    private func drawAnimatedDashes(path: CGPath, in context: CGContext, zoomScale: MKZoomScale) {
        context.saveGState()

        let adjustedWidth = (lineWidth / zoomScale) * 0.4

        context.setLineWidth(adjustedWidth)
        context.setLineCap(.round)
        context.setLineJoin(.round)

        // Bright white/cyan color for the moving dots
        context.setStrokeColor(UIColor.white.withAlphaComponent(0.9).cgColor)

        // Set dash pattern with animated phase
        let scaledPattern = dashPattern.map { $0 / zoomScale }
        context.setLineDash(phase: dashPhase / zoomScale, lengths: scaledPattern)

        context.addPath(path)
        context.strokePath()

        context.restoreGState()
    }
}
