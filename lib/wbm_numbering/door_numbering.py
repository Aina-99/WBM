# -*- coding: utf-8 -*-
"""Numerotation generique des portes (parametre "Mark") d'une vue.

Convention WBM : "{Prefixe}.{Niveau}.{NNN}" (ex. "T.EG00.001").

L'ordre suit quatre regles, deduites de l'analyse d'un cas reel (voir
Numbering.panel/Door Numbering (Beta).pushbutton) :

0. La porte la plus proche (a vol d'oiseau) du repere d'entree devient
   toujours le rang 1, quelle que soit la position que les regles
   suivantes lui auraient donnee : c'est la porte qu'on franchit en
   premier en entrant dans le batiment.
1. Les portes ayant une piece ToRoom sont regroupees par piece et
   ordonnees selon le Number de cette piece (croissant) : la
   numerotation des portes suit ainsi l'ordre de circulation deja
   encode par la numerotation des pieces, sans avoir a le redeviner.
   ToRoom prime sur FromRoom : une porte est rattachee a la piece vers
   laquelle elle mene, pas a celle dont elle part.
2. Quand plusieurs portes menent vers la meme piece, l'egalite est
   departagee en balayant le sens horaire autour du centre de CETTE
   piece, en repartant d'une reference de sortie de la piece : la
   porte par laquelle on en ressort reellement (FromRoom == cette
   piece) quand elle est unique dans tout le jeu de portes -- la
   reference la plus fiable, independante de l'ordre de traitement des
   groupes -- sinon le point d'entree choisi par l'utilisateur (voir
   regle 3).
3. Les portes sans ToRoom (portes menant vers l'exterieur) sont
   inserees juste avant le groupe de portes de leur FromRoom,
   puisqu'elles jouent le meme role qu'une porte "vers" cette piece.

Le point d'entree choisi par l'utilisateur (voir
preview_window.on_pick_entry_click) ne sert donc que de repli pour la
regle 2, et seulement pour les pieces sans porte de sortie identifiable
de façon unique -- typiquement une piece a plusieurs sorties possibles,
ou aucune porte n'en ressort explicitement dans les donnees. Pour les
autres pieces (l'immense majorite), le repere choisi n'a aucun effet
visible : c'est attendu, la reference physique reelle prime toujours
sur un point choisi a la main. Verifiez toujours la previsualisation
avant d'appliquer (et reordonnez manuellement au besoin, par
glisser-deposer dans le tableau) sur les pieces concernees.
"""

import math
import re

from Autodesk.Revit.DB import (
    BuiltInCategory,
    BuiltInParameter,
    FilteredElementCollector,
    Transaction,
)

from wbm_numbering.revit_context import SwallowWarnings

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


def element_point(element):
    """Position (x, y) representative d'un element quelconque : son point
    d'implantation, sinon le milieu de sa courbe d'implantation, sinon le
    centre de sa bounding box.

    Generique a dessein : sert aussi bien aux portes qu'a l'element
    repere d'entree choisi par l'utilisateur (une annotation, mais aussi
    potentiellement un mur, une porte, une pièce...).
    """
    loc = getattr(element, "Location", None)
    if loc is not None and hasattr(loc, "Point") and loc.Point:
        return (loc.Point.X, loc.Point.Y)
    if loc is not None and hasattr(loc, "Curve") and loc.Curve:
        mid = loc.Curve.Evaluate(0.5, True)
        return (mid.X, mid.Y)
    bbox = element.get_BoundingBox(None)
    if bbox:
        return ((bbox.Min.X + bbox.Max.X) / 2.0, (bbox.Min.Y + bbox.Max.Y) / 2.0)
    return None


def _distance(point_a, point_b):
    return math.hypot(point_a[0] - point_b[0], point_a[1] - point_b[1])


def clockwise_angle(point, center):
    """Angle en degres de `point` autour de `center`, sens horaire depuis
    le nord, en vue en plan (0-360)."""
    dx = point[0] - center[0]
    dy = point[1] - center[1]
    angle = math.degrees(math.atan2(dx, dy))
    return angle + 360.0 if angle < 0 else angle


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
        doors.append(DoorInfo(door, element_point(door), from_room, to_room))
    return doors


def _exit_reference(room_id, all_doors, entry_point):
    """Reference de sortie de la piece `room_id` : la porte par laquelle
    on en ressort reellement (FromRoom == room_id), quand elle est
    unique -- la direction physiquement correcte. Repli sur
    `entry_point` quand aucune porte n'en ressort, ou que plusieurs s'y
    pretent (impossible de trancher sans ambiguite a partir des seules
    donnees FromRoom/ToRoom).
    """
    outbound = [
        d for d in all_doors
        if d.from_room is not None and d.from_room.Id.IntegerValue == room_id
    ]
    if len(outbound) == 1:
        return outbound[0].location
    return entry_point


def _sweep_clockwise(group, pivot, start_point):
    """Ordonne `group` (portes partageant un meme ToRoom) en sautant,
    a chaque etape, vers la porte restante la plus proche dans le sens
    horaire autour de `pivot`, en repartant de `start_point` (la
    reference de sortie de la piece, voir _exit_reference)."""
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
    docstring du module). ToRoom prime sur FromRoom (voir regle 1)."""
    with_room = [d for d in doors if d.to_room is not None]
    without_room = [d for d in doors if d.to_room is None]

    groups = {}
    for d in with_room:
        groups.setdefault(d.to_room.Id.IntegerValue, []).append(d)

    group_order = sorted(
        groups.keys(), key=lambda rid: room_number_key(groups[rid][0].to_room)
    )

    ordered = []
    for room_id in group_order:
        group = groups[room_id]
        pivot = room_center(group[0].to_room) or group[0].location
        reference = _exit_reference(room_id, doors, entry_point) or pivot
        placed = _sweep_clockwise(group, pivot, reference)
        ordered.extend(placed)

    for door in without_room:
        target_number = room_number_key(door.from_room)
        insert_at = len(ordered)
        for i, placed_door in enumerate(ordered):
            # Les portes deja inserees sans ToRoom ont une cle infinie : les
            # comparer ferait remonter chaque nouvelle porte exterieure juste
            # devant la precedente, donc en tete de liste.
            if placed_door.to_room is None:
                continue
            if room_number_key(placed_door.to_room) >= target_number:
                insert_at = i
                break
        ordered.insert(insert_at, door)

    candidates = [d for d in ordered if d.location is not None]
    if entry_point is not None and candidates:
        closest = min(candidates, key=lambda d: _distance(d.location, entry_point))
        if ordered[0] is not closest:
            ordered.remove(closest)
            ordered.insert(0, closest)

    return ordered


def assign_marks(ordered_doors, prefix, level_name, digits=3, start=1):
    """Calcule et affecte door.mark pour chaque porte de `ordered_doors`
    (ne modifie pas encore le modele, voir apply_marks)."""
    for i, door in enumerate(ordered_doors):
        door.mark = "{}.{}.{}".format(prefix, level_name, str(i + start).zfill(digits))
    return ordered_doors


def apply_marks(doc, ordered_doors, transaction_name="Door Mark numbering"):
    """Ecrit door.mark dans le parametre Mark de chaque porte, dans une
    transaction unique.

    A n'appeler que depuis un contexte API Revit valide : depuis une
    fenetre non modale, passer par wbm_numbering.revit_context.
    """
    t = Transaction(doc, transaction_name)
    t.Start()
    options = t.GetFailureHandlingOptions()
    options.SetFailuresPreprocessor(SwallowWarnings())
    options.SetForcedModalHandling(False)
    t.SetFailureHandlingOptions(options)
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
