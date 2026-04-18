"""
GPS Processor — pure stateless functions for GPS calculations.

No I/O, no DB, no async. All functions operate on plain Python values.
Target: < 1ms per call even for large ring buffers.
"""
from __future__ import annotations

import math
from typing import Optional


# ---------------------------------------------------------------------------
# Core geometry
# ---------------------------------------------------------------------------

def haversine_m(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """
    Great-circle distance between two WGS-84 coordinates in metres.
    Uses the haversine formula; accurate to < 0.3% for distances < 200 km.
    """
    R = 6_371_000.0  # Earth radius in metres
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lng2 - lng1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


def bearing_between(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """
    Initial bearing from point A to point B, in degrees [0, 360).
    0° = North, 90° = East, 180° = South, 270° = West.
    """
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dlam = math.radians(lng2 - lng1)
    x = math.sin(dlam) * math.cos(phi2)
    y = math.cos(phi1) * math.sin(phi2) - math.sin(phi1) * math.cos(phi2) * math.cos(dlam)
    bearing = math.degrees(math.atan2(x, y))
    return (bearing + 360.0) % 360.0


def angular_diff(a: float, b: float) -> float:
    """
    Smallest angular difference between two bearings [0, 180].
    E.g. angular_diff(350, 10) == 20, angular_diff(90, 270) == 180.
    """
    diff = abs(a - b) % 360.0
    return diff if diff <= 180.0 else 360.0 - diff


# ---------------------------------------------------------------------------
# GPS track analysis
# ---------------------------------------------------------------------------

# GPS point type: (lat, lng, heading_deg_or_None, unix_timestamp)
GpsPoint = tuple[float, float, Optional[float], float]


def compute_bearing_from_track(gps_points: list[GpsPoint]) -> Optional[float]:
    """
    Estimate current movement bearing from a GPS ring buffer.

    Algorithm:
      - If the last point has a device heading (compass reading), prefer that.
      - Otherwise compute bearing from the last 3+ track points using a
        weighted average (later legs count more).
      - Returns None if there are fewer than 2 usable points.
    """
    if not gps_points:
        return None

    # Prefer device heading from the most recent point
    last_heading = gps_points[-1][2]
    if last_heading is not None:
        return float(last_heading)

    if len(gps_points) < 2:
        return None

    # Compute bearing for each consecutive segment
    segments: list[tuple[float, float]] = []  # (bearing, distance_m)
    for i in range(len(gps_points) - 1):
        lat1, lng1, _, _ = gps_points[i]
        lat2, lng2, _, _ = gps_points[i + 1]
        dist = haversine_m(lat1, lng1, lat2, lng2)
        if dist < 0.5:  # ignore sub-metre jitter
            continue
        b = bearing_between(lat1, lng1, lat2, lng2)
        segments.append((b, dist))

    if not segments:
        return None

    if len(segments) == 1:
        return segments[0][0]

    # Weighted average — later segments count twice as much
    # Use circular mean to handle wrap-around at 0°/360°
    weights = [1.0 + (i / (len(segments) - 1)) for i in range(len(segments))]
    total_weight = sum(weights)
    sin_sum = sum(math.sin(math.radians(b)) * w for (b, _), w in zip(segments, weights))
    cos_sum = sum(math.cos(math.radians(b)) * w for (b, _), w in zip(segments, weights))
    avg = math.degrees(math.atan2(sin_sum / total_weight, cos_sum / total_weight))
    return (avg + 360.0) % 360.0


def compute_speed_mps(gps_points: list[GpsPoint]) -> float:
    """
    Estimate current speed in m/s from a GPS ring buffer.

    Uses the distance and time difference between the last two points.
    Returns 0.0 if fewer than 2 points are available or time delta is zero.
    """
    if len(gps_points) < 2:
        return 0.0
    lat1, lng1, _, t1 = gps_points[-2]
    lat2, lng2, _, t2 = gps_points[-1]
    dt = t2 - t1
    if dt <= 0:
        return 0.0
    dist = haversine_m(lat1, lng1, lat2, lng2)
    return dist / dt


def is_gps_anomaly(
    prev_lat: float,
    prev_lng: float,
    new_lat: float,
    new_lng: float,
    time_delta_s: float,
    max_speed_mps: float = 16.7,
) -> bool:
    """
    True if the implied speed between two GPS samples exceeds max_speed_mps.

    Default 16.7 m/s ≈ 60 km/h — impossible for a pedestrian.
    Ignores anomalies when time_delta_s ≤ 0 (clocks not yet synced).
    """
    if time_delta_s <= 0:
        return False
    dist = haversine_m(prev_lat, prev_lng, new_lat, new_lng)
    return (dist / time_delta_s) > max_speed_mps
