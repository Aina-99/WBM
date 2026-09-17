# -*- coding: utf-8 -*-
"""Controle : l'etiquette des tags de piece, porte et fenetre ne doit
chevaucher ni un mur (coupe au plan de coupe de la vue) ni un contour de
piece, dans les vues en plan dont le nom contient "Grundriss".

Seule l'etiquette compte, pas la ligne de rappel : les boites sont lues
leaders retires, dans une transaction toujours annulee. Doit donc
tourner dans un contexte API Revit valide.
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


def _cross(o, a, b):
    return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])


def _segments_cross(p1, p2, p3, p4):
    d1 = _cross(p3, p4, p1)
    d2 = _cross(p3, p4, p2)
    d3 = _cross(p1, p2, p3)
    d4 = _cross(p1, p2, p4)
    return ((d1 > 0 > d2) or (d1 < 0 < d2)) and ((d3 > 0 > d4) or (d3 < 0 < d4))


def _point_in_rect(p, rect):
    return rect[0] <= p[0] <= rect[2] and rect[1] <= p[1] <= rect[3]


def _segment_hits_rect(p1, p2, rect):
    if _point_in_rect(p1, rect) or _point_in_rect(p2, rect):
        return True
    corners = [(rect[0], rect[1]), (rect[2], rect[1]), (rect[2], rect[3]), (rect[0], rect[3])]
    return any(_segments_cross(p1, p2, corners[i], corners[(i + 1) % 4]) for i in range(4))


def _point_in_loops(point, loops):
    x, y = point
    inside = False
    for poly in loops:
        j = len(poly) - 1
        for i in range(len(poly)):
            xi, yi = poly[i]
            xj, yj = poly[j]
            if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / (yj - yi) + xi:
                inside = not inside
            j = i
    return inside


def _rect_hits_loops(rect, loops):
    for poly in loops:
        for i in range(len(poly)):
            if _segment_hits_rect(poly[i], poly[(i + 1) % len(poly)], rect):
                return True
    center = ((rect[0] + rect[2]) / 2.0, (rect[1] + rect[3]) / 2.0)
    return _point_in_loops(center, loops)


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
                    segments.append(
                        (room.Number, (points[i].X, points[i].Y), (points[i + 1].X, points[i + 1].Y))
                    )
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

            for index, (tag_view, tag_type, tag) in enumerate(entries):
                box = boxes[index]
                if box is None or tag_view.Id != view.Id:
                    continue

                wall_count = sum(
                    1 for _, loops, bounds in walls
                    if _rects_touch(box, bounds) and _rect_hits_loops(box, loops)
                )
                room_numbers = []
                for number, p1, p2 in contours:
                    if number not in room_numbers and _segment_hits_rect(p1, p2, box):
                        room_numbers.append(number)

                if not wall_count and not room_numbers:
                    continue

                overlaps = []
                if wall_count:
                    overlaps.append("{} mur(s)".format(wall_count))
                if room_numbers:
                    overlaps.append("contour {}".format(", ".join(room_numbers)))

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
                            ", ".join(overlaps),
                        ),
                    )
                )

        return issues
