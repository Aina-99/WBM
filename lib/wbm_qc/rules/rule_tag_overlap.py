# -*- coding: utf-8 -*-
"""Controle : l'etiquette des tags de piece, porte et fenetre ne doit
chevaucher ni un mur (coupe au plan de coupe de la vue) ni un contour de
piece, dans les vues en plan dont le nom contient "Grundriss".

Seule l'etiquette compte, pas la ligne de rappel : les boites sont lues
leaders retires, dans une transaction toujours annulee. Doit donc
tourner dans un contexte API Revit valide.

Le chevauchement est mesure (part de l'etiquette recouverte par un mur,
longueur de contour traversant l'etiquette) et non par simple contact :
la boite d'un tag depasse legerement ses lettres, donc un contact strict
remonte surtout des frolements invisibles a l'impression.
"""

from Autodesk.Revit.DB import (
    BooleanOperationsUtils,
    BuiltInCategory,
    FilteredElementCollector,
    GeometryInstance,
    Options,
    PlanarFace,
    Plane,
    PlanViewPlane,
    Solid,
    SpatialElementBoundaryLocation,
    SpatialElementBoundaryOptions,
    SpatialElementTag,
    Transaction,
    ViewPlan,
    XYZ,
)

from wbm_qc.models import QCIssue, SEVERITY_ERROR
from wbm_qc.registry import QCRule, register_rule
from wbm_qc.tags import TAG_TYPES, get_tagged_element_ids, get_value

_VIEW_NAME_FILTER = "Grundriss"
_DEFAULT_CUT_OFFSET_FT = 4.0
_EPS = 1e-9

# Part minimale de l'etiquette recouverte par un mur pour signaler le tag.
_MIN_OVERLAP_RATIO = 0.02
# Longueur minimale (mm sur le papier) d'un contour traversant l'etiquette.
_MIN_CONTOUR_MM = 3.0
_MM_PER_FT = 304.8


def _clip_to_rect(poly, rect):
    """Partie du polygone contenue dans le rectangle (Sutherland-Hodgman).
    L'orientation est conservee : les trous restent soustractifs."""
    bounds = ((0, rect[0], True), (0, rect[2], False), (1, rect[1], True), (1, rect[3], False))
    for axis, value, keep_greater in bounds:
        if not poly:
            return []
        clipped = []
        for index in range(len(poly)):
            current = poly[index]
            previous = poly[index - 1]
            current_in = current[axis] >= value if keep_greater else current[axis] <= value
            previous_in = previous[axis] >= value if keep_greater else previous[axis] <= value
            if current_in != previous_in:
                span = current[axis] - previous[axis]
                ratio = (value - previous[axis]) / span if abs(span) > _EPS else 0.0
                clipped.append(
                    (
                        previous[0] + (current[0] - previous[0]) * ratio,
                        previous[1] + (current[1] - previous[1]) * ratio,
                    )
                )
            if current_in:
                clipped.append(current)
        poly = clipped
    return poly


def _signed_area(poly):
    if len(poly) < 3:
        return 0.0
    total = 0.0
    for index in range(len(poly)):
        x1, y1 = poly[index]
        x2, y2 = poly[(index + 1) % len(poly)]
        total += x1 * y2 - x2 * y1
    return total / 2.0


def _overlap_area(rect, loops):
    return abs(sum(_signed_area(_clip_to_rect(poly, rect)) for poly in loops))


def _segment_length_in_rect(p1, p2, rect):
    """Longueur de la portion de segment contenue dans le rectangle
    (decoupage de Liang-Barsky)."""
    dx = p2[0] - p1[0]
    dy = p2[1] - p1[1]
    start, end = 0.0, 1.0
    for direction, distance in (
        (-dx, p1[0] - rect[0]),
        (dx, rect[2] - p1[0]),
        (-dy, p1[1] - rect[1]),
        (dy, rect[3] - p1[1]),
    ):
        if abs(direction) < _EPS:
            if distance < 0:
                return 0.0
            continue
        ratio = distance / direction
        if direction < 0:
            if ratio > end:
                return 0.0
            start = max(start, ratio)
        else:
            if ratio < start:
                return 0.0
            end = min(end, ratio)
    span = end - start
    return ((dx * span) ** 2 + (dy * span) ** 2) ** 0.5


def _loops_bounds(loops):
    xs = [p[0] for poly in loops for p in poly]
    ys = [p[1] for poly in loops for p in poly]
    return (min(xs), min(ys), max(xs), max(ys))


def _rects_touch(a, b):
    return not (a[2] < b[0] or a[0] > b[2] or a[3] < b[1] or a[1] > b[3])


def _solids(element):
    geometry = element.get_Geometry(Options())
    if geometry is None:
        return []
    solids = []
    for item in geometry:
        candidates = item.GetInstanceGeometry() if isinstance(item, GeometryInstance) else [item]
        solids.extend(g for g in candidates if isinstance(g, Solid) and g.Volume > _EPS)
    return solids


def _face_loops(face):
    loops = []
    for curve_loop in face.GetEdgesAsCurveLoops():
        points = []
        for curve in curve_loop:
            tessellated = curve.Tessellate()
            points.extend((p.X, p.Y) for p in list(tessellated)[:-1])
        if len(points) >= 3:
            loops.append(points)
    return loops


def _is_top_face(face):
    return isinstance(face, PlanarFace) and face.FaceNormal.Z > 0.999


def _wall_section(wall, cut_z):
    """Contour du mur coupe a cut_z ; pour un mur entierement sous le
    plan de coupe, sa face superieure (vue en projection)."""
    plane = Plane.CreateByNormalAndOrigin(XYZ(0, 0, -1), XYZ(0, 0, cut_z))
    loops = []
    for solid in _solids(wall):
        try:
            below = BooleanOperationsUtils.CutWithHalfSpace(solid, plane)
        except Exception:
            below = None

        section = []
        if below is not None and below.Volume > _EPS:
            for face in below.Faces:
                if _is_top_face(face) and abs(face.Origin.Z - cut_z) < 1e-3:
                    section.extend(_face_loops(face))
        if not section:
            for face in solid.Faces:
                if _is_top_face(face) and face.Origin.Z < cut_z:
                    section.extend(_face_loops(face))
        loops.extend(section)
    return loops


def _cut_elevation(doc, view):
    view_range = view.GetViewRange()
    level = doc.GetElement(view_range.GetLevelId(PlanViewPlane.CutPlane))
    if level is not None:
        return level.ProjectElevation + view_range.GetOffset(PlanViewPlane.CutPlane)
    gen_level = view.GenLevel
    return (gen_level.ProjectElevation if gen_level else 0.0) + _DEFAULT_CUT_OFFSET_FT


def _collect_in_view(doc, view, category):
    return (
        FilteredElementCollector(doc, view.Id)
        .OfCategory(category)
        .WhereElementIsNotElementType()
        .ToElements()
    )


def _wall_sections(doc, view, cache):
    cut_z = _cut_elevation(doc, view)
    sections = []
    for wall in _collect_in_view(doc, view, BuiltInCategory.OST_Walls):
        key = (wall.Id.IntegerValue, round(cut_z, 3))
        if key not in cache:
            loops = _wall_section(wall, cut_z)
            cache[key] = (loops, _loops_bounds(loops)) if loops else None
        if cache[key] is not None:
            sections.append((wall.Id,) + cache[key])
    return sections


def _room_contours(doc, view):
    options = SpatialElementBoundaryOptions()
    options.SpatialElementBoundaryLocation = SpatialElementBoundaryLocation.Finish

    segments = []
    for room in _collect_in_view(doc, view, BuiltInCategory.OST_Rooms):
        for loop in room.GetBoundarySegments(options) or []:
            for boundary in loop:
                points = list(boundary.GetCurve().Tessellate())
                for i in range(len(points) - 1):
                    p1 = (points[i].X, points[i].Y)
                    p2 = (points[i + 1].X, points[i + 1].Y)
                    bounds = (
                        min(p1[0], p2[0]), min(p1[1], p2[1]),
                        max(p1[0], p2[0]), max(p1[1], p2[1]),
                    )
                    segments.append((room.Number, p1, p2, bounds))
    return segments


def _label_boxes(doc, entries):
    """Boite (xmin, ymin, xmax, ymax) de l'etiquette seule de chaque tag,
    sans sa ligne de rappel. Le modele n'est jamais modifie."""
    before = []
    for _, _, tag in entries:
        location = getattr(tag.Location, "Point", None) if tag.Location is not None else None
        before.append((tag.HasLeader, tag.TagHeadPosition, location))

    boxes = [None] * len(entries)
    transaction = Transaction(doc, "WBM QC - lecture des etiquettes (annulee)")
    transaction.Start()
    try:
        for _, _, tag in entries:
            if tag.HasLeader:
                try:
                    tag.HasLeader = False
                except Exception:
                    pass
        doc.Regenerate()

        for index, (view, _, tag) in enumerate(entries):
            bbox = tag.get_BoundingBox(view)
            if bbox is None:
                continue
            had_leader, head, location = before[index]
            dx = dy = 0.0
            # Sans leader, Revit ramene un tag de piece sur le point de sa
            # piece : on recale la boite a la position affichee.
            if had_leader and isinstance(tag, SpatialElementTag) and location is not None:
                dx = head.X - location.X
                dy = head.Y - location.Y
            boxes[index] = (bbox.Min.X + dx, bbox.Min.Y + dy, bbox.Max.X + dx, bbox.Max.Y + dy)
    finally:
        transaction.RollBack()
    return boxes


def _tag_value(doc, tag, tag_type):
    for element_id in get_tagged_element_ids(tag):
        element = doc.GetElement(element_id)
        value = get_value(element, tag_type.value_param) if element is not None else ""
        if value:
            return value
    return str(tag.Id.IntegerValue)


@register_rule
class TagOverlapRule(QCRule):
    rule_id = "tag_overlap_walls_rooms"
    name = "Chevauchement des tags"
    category = "Tags"
    severity = SEVERITY_ERROR
    description = "Les etiquettes de tags ne doivent chevaucher ni mur ni contour de piece (vues Grundriss)."

    def check(self, doc):
        views = [
            view
            for view in FilteredElementCollector(doc).OfClass(ViewPlan).ToElements()
            if not view.IsTemplate and _VIEW_NAME_FILTER in (view.Name or "")
        ]

        entries = []
        for view in views:
            for tag_type in TAG_TYPES:
                for tag in _collect_in_view(doc, view, tag_type.tag_category):
                    entries.append((view, tag_type, tag))
        if not entries:
            return []

        boxes = _label_boxes(doc, entries)

        issues = []
        section_cache = {}
        for view in views:
            walls = _wall_sections(doc, view, section_cache)
            contours = _room_contours(doc, view)
            min_contour_ft = _MIN_CONTOUR_MM * view.Scale / _MM_PER_FT

            for index, (tag_view, tag_type, tag) in enumerate(entries):
                box = boxes[index]
                if box is None or tag_view.Id != view.Id:
                    continue

                box_area = (box[2] - box[0]) * (box[3] - box[1])
                if box_area <= _EPS:
                    continue

                overlap = sum(
                    _overlap_area(box, loops)
                    for _, loops, bounds in walls
                    if _rects_touch(box, bounds)
                )
                ratio = overlap / box_area

                room_numbers = []
                for number, p1, p2, bounds in contours:
                    if number in room_numbers or not _rects_touch(box, bounds):
                        continue
                    if _segment_length_in_rect(p1, p2, box) >= min_contour_ft:
                        room_numbers.append(number)

                if ratio < _MIN_OVERLAP_RATIO and not room_numbers:
                    continue

                overlaps = []
                if ratio >= _MIN_OVERLAP_RATIO:
                    overlaps.append("un mur sur {:.0f}% de l'etiquette".format(ratio * 100))
                if room_numbers:
                    overlaps.append("le contour de {}".format(", ".join(sorted(room_numbers))))

                issues.append(
                    QCIssue(
                        element_id=tag.Id,
                        category=self.category,
                        rule_name=self.name,
                        severity=self.severity,
                        description="Deplacer le tag {} '{}' ({}) : chevauche {}.".format(
                            tag_type.label,
                            _tag_value(doc, tag, tag_type),
                            view.Name,
                            " et ".join(overlaps),
                        ),
                    )
                )

        return issues
