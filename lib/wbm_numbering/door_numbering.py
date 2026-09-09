# -*- coding: utf-8 -*-
"""Numerotation generique des portes (parametre "Mark") d'une vue.

Convention WBM : "{Prefixe}.{Niveau}.{NNN}" (ex. "T.EG00.001").

L'ordre suit trois regles, deduites de l'analyse d'un cas reel (voir
Numbering.panel/Door Numbering (Beta).pushbutton) :

1. Les portes ayant une piece FromRoom sont regroupees par piece et
   ordonnees selon le Number de cette piece (croissant) : la
   numerotation des portes suit ainsi l'ordre de circulation deja
   encode par la numerotation des pieces, sans avoir a le redeviner.
2. Quand plusieurs portes partent de la meme piece, l'egalite est
   departagee en balayant le sens horaire autour du centre de CETTE
   piece, en repartant de la porte precedemment numerotee (et non d'un
   angle absolu depuis un point unique) : un pivot global deforme le
   sens horaire par effet de perspective pour les pieces eloignees.
3. Les portes sans FromRoom (portes exterieures) sont inserees juste
   avant le groupe de portes de leur ToRoom, puisqu'elles jouent le
   meme role qu'une porte "depuis" cette piece.

Pour les pieces sans porte entrante identifiable (aucune, ou plusieurs
candidates pas encore numerotees), il n'existe pas de reference
geometrique fiable : la regle 2 retombe alors sur la continuation de
la sequence globale (le dernier point numerote), qui reste deterministe
mais peut ne pas correspondre a l'intuition visuelle. Verifiez toujours
la previsualisation avant d'appliquer, en particulier sur ces pieces.
"""

import math
import re

from Autodesk.Revit.DB import (
    BuiltInCategory,
    BuiltInParameter,
    FilteredElementCollector,
    Transaction,
)

_TRAILING_DIGITS = re.compile(r"(\d+)\s*$")


class DoorInfo(object):
    """Une porte candidate a la numerotation, avec son rang/mark calcules."""

    def __init__(self, element, location, from_room, to_room):
        self.element = element
        self.location = location  # tuple (x, y), ou None
        self.from_room = from_room  # element Room, ou None
        self.to_room = to_room  # element Room, ou None
        self.mark = None  # rempli par assign_marks()


def room_number_key(room):
    """Cle de tri numerique extraite du Number d'une piece.

    Les pieces dont le Number ne contient aucun chiffre final sont
    placees en dernier plutot que de faire planter le tri.
    """
    if room is None:
        return float("inf")
    match = _TRAILING_DIGITS.search(room.Number or "")
    return int(match.group(1)) if match else float("inf")


def room_center(room):
    """Centre (x, y) d'une piece : son point d'implantation, sinon le
    centre de sa bounding box."""
    if room is None:
        return None
    loc = room.Location
    if loc is not None and hasattr(loc, "Point") and loc.Point:
        return (loc.Point.X, loc.Point.Y)
    bbox = room.get_BoundingBox(None)
    if bbox:
        return ((bbox.Min.X + bbox.Max.X) / 2.0, (bbox.Min.Y + bbox.Max.Y) / 2.0)
    return None


def door_location(door):
    loc = door.Location
    if loc is not None and hasattr(loc, "Point") and loc.Point:
        return (loc.Point.X, loc.Point.Y)
    return None


def clockwise_angle(point, center):
    """Angle en degres de `point` autour de `center`, sens horaire depuis
    le nord, en vue en plan (0-360)."""
    dx = point[0] - center[0]
    dy = point[1] - center[1]
    angle = math.degrees(math.atan2(dx, dy))
    return angle + 360.0 if angle < 0 else angle


def find_entry_point(doc, view, name_contains="M360_Entry"):
    """Cherche, parmi les elements visibles dans `view`, une annotation
    dont le Name contient `name_contains`, et retourne sa position
    (x, y).

    Retourne None si aucune instance implantee ne correspond ; les
    appelants doivent alors se rabattre sur un comportement degrade
    (voir build_order).
    """
    collector = FilteredElementCollector(doc, view.Id).WhereElementIsNotElementType()
    candidates = []
    for element in collector:
        try:
            name = element.Name
        except Exception:
            continue
        if not name or name_contains not in name:
            continue
        loc = element.Location
        if loc is not None and hasattr(loc, "Point") and loc.Point:
            candidates.append((element, (loc.Point.X, loc.Point.Y)))
    if not candidates:
        return None
    # Si plusieurs correspondances (ex. "M360_Entry" et "M360_Entry 2"),
    # on privilegie le nom le plus specifique (le plus long).
    candidates.sort(key=lambda c: len(c[0].Name))
    return candidates[-1][1]


def collect_doors(doc, view):
    """Portes visibles dans `view`, avec leur FromRoom/ToRoom pour la
    phase associee a cette vue."""
    phase_param = view.get_Parameter(BuiltInParameter.VIEW_PHASE)
    phase_id = phase_param.AsElementId() if phase_param else None
    phase = doc.GetElement(phase_id) if phase_id else None

    collector = (
        FilteredElementCollector(doc, view.Id)
        .OfCategory(BuiltInCategory.OST_Doors)
        .WhereElementIsNotElementType()
    )

    doors = []
    for door in collector:
        from_room = door.FromRoom[phase] if phase else None
        to_room = door.ToRoom[phase] if phase else None
        doors.append(DoorInfo(door, door_location(door), from_room, to_room))
    return doors


def _sweep_clockwise(group, pivot, start_point):
    """Ordonne `group` (portes partageant un meme FromRoom) en sautant,
    a chaque etape, vers la porte restante la plus proche dans le sens
    horaire autour de `pivot`, en repartant de `start_point` (la
    derniere porte numerotee, ou le point d'entree pour le tout premier
    groupe)."""
    remaining = list(group)
    ordered = []
    reference = start_point
    while remaining:
        ref_angle = clockwise_angle(reference, pivot)
        remaining.sort(
            key=lambda d: (clockwise_angle(d.location, pivot) - ref_angle) % 360.0
        )
        nxt = remaining.pop(0)
        ordered.append(nxt)
        reference = nxt.location
    return ordered


def build_order(doors, entry_point):
    """Retourne `doors` reordonnees selon la convention WBM (voir le
    docstring du module)."""
    with_room = [d for d in doors if d.from_room is not None]
    without_room = [d for d in doors if d.from_room is None]

    groups = {}
    for d in with_room:
        groups.setdefault(d.from_room.Id.IntegerValue, []).append(d)

    group_order = sorted(
        groups.keys(), key=lambda rid: room_number_key(groups[rid][0].from_room)
    )

    ordered = []
    reference_point = entry_point
    for room_id in group_order:
        group = groups[room_id]
        pivot = room_center(group[0].from_room) or reference_point or group[0].location
        if reference_point is None:
            reference_point = pivot
        placed = _sweep_clockwise(group, pivot, reference_point)
        ordered.extend(placed)
        reference_point = placed[-1].location or reference_point

    for door in without_room:
        target_number = room_number_key(door.to_room)
        insert_at = len(ordered)
        for i, placed_door in enumerate(ordered):
            if room_number_key(placed_door.from_room) >= target_number:
                insert_at = i
                break
        ordered.insert(insert_at, door)

    return ordered


def assign_marks(ordered_doors, prefix, level_name, digits=3, start=1):
    """Calcule et affecte door.mark pour chaque porte de `ordered_doors`
    (ne modifie pas encore le modele, voir apply_marks)."""
    for i, door in enumerate(ordered_doors):
        door.mark = "{}.{}.{}".format(prefix, level_name, str(i + start).zfill(digits))
    return ordered_doors


def apply_marks(doc, ordered_doors, transaction_name="Door Mark numbering"):
    """Ecrit door.mark dans le parametre Mark de chaque porte, dans une
    transaction unique."""
    t = Transaction(doc, transaction_name)
    t.Start()
    try:
        for door in ordered_doors:
            param = door.element.get_Parameter(BuiltInParameter.ALL_MODEL_MARK)
            if param and not param.IsReadOnly:
                param.Set(door.mark)
    except Exception:
        t.RollBack()
        raise
    else:
        t.Commit()
