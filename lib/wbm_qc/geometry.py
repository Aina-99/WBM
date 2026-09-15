# -*- coding: utf-8 -*-
"""Geometrie utilitaire pour les regles de controle qualite.

compute_room_obb_dimensions() reproduit fidelement l'algorithme du
script Dynamo GET_GEOMETRY_ROOMS_1.0.dyn (rectangle englobant de
surface minimale, calcule par rotating calipers sur l'enveloppe
convexe du contour de la piece) afin de pouvoir comparer la geometrie
reelle a la valeur stockee par ce script sans dependre de lui."""

import math

from Autodesk.Revit.DB import SpatialElementBoundaryLocation, SpatialElementBoundaryOptions

_TOL = 1e-7


def _to_2d(point):
    return (point.X, point.Y)


def _cross(o, a, b):
    return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])


def _unique_points(points, tol=_TOL):
    seen = set()
    out = []
    for x, y in points:
        key = (round(x / tol), round(y / tol))
        if key not in seen:
            seen.add(key)
            out.append((x, y))
    return out


def _convex_hull(points):
    pts = sorted(points)
    if len(pts) <= 1:
        return pts

    lower = []
    for p in pts:
        while len(lower) >= 2 and _cross(lower[-2], lower[-1], p) <= 0:
            lower.pop()
        lower.append(p)

    upper = []
    for p in reversed(pts):
        while len(upper) >= 2 and _cross(upper[-2], upper[-1], p) <= 0:
            upper.pop()
        upper.append(p)

    return lower[:-1] + upper[:-1]


def _rotate(point, angle):
    c = math.cos(angle)
    s = math.sin(angle)
    x, y = point
    return (x * c - y * s, x * s + y * c)


def _min_area_obb(points):
    hull = _convex_hull(points)
    n = len(hull)

    if n == 0:
        return None
    if n == 1:
        return 0.0, 0.0
    if n == 2:
        (x1, y1), (x2, y2) = hull
        return math.hypot(x2 - x1, y2 - y1), 0.0

    best = None
    for i in range(n):
        p1 = hull[i]
        p2 = hull[(i + 1) % n]
        dx = p2[0] - p1[0]
        dy = p2[1] - p1[1]
        if abs(dx) < _TOL and abs(dy) < _TOL:
            continue

        angle = -math.atan2(dy, dx)
        rotated = [_rotate(p, angle) for p in hull]
        xs = [p[0] for p in rotated]
        ys = [p[1] for p in rotated]
        width = max(xs) - min(xs)
        depth = max(ys) - min(ys)
        area = width * depth

        if best is None or area < best[0]:
            best = (area, width, depth)

    _, width, depth = best
    if depth > width:
        width, depth = depth, width

    return width, depth


def compute_room_obb_dimensions(room):
    """Retourne (largeur_ft, profondeur_ft) du rectangle englobant de
    surface minimale du contour de la piece, ou (None, None) si le
    contour est indisponible."""
    options = SpatialElementBoundaryOptions()
    options.SpatialElementBoundaryLocation = SpatialElementBoundaryLocation.Finish

    try:
        boundaries = room.GetBoundarySegments(options)
    except Exception:
        return None, None

    if not boundaries:
        return None, None

    points = []
    for loop in boundaries:
        for segment in loop:
            curve = segment.GetCurve()
            points.append(_to_2d(curve.GetEndPoint(0)))
            points.append(_to_2d(curve.GetEndPoint(1)))

    points = _unique_points(points)
    if len(points) < 2:
        return None, None

    result = _min_area_obb(points)
    return result if result else (None, None)
