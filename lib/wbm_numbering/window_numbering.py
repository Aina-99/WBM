# -*- coding: utf-8 -*-
"""Numerotation generique des fenetres (parametre "Mark") d'une vue.

Convention WBM : "{Prefixe}.{Niveau}.{NNN}" (ex. "T.EG00.001").

A la difference des portes (regroupees par piece via FromRoom/ToRoom,
voir wbm_numbering.door_numbering), les fenetres ne bordent pas de
piece exploitable de la meme facon. L'ordre suit donc un simple
balayage dans le sens horaire autour du centre du batiment dans la vue
active (bounding box des murs visibles), en repartant du meme repere
d'entree que pour la numerotation des portes : la fenetre 001 part
ainsi du meme point de depart que la porte 001.
"""

from Autodesk.Revit.DB import (
    BuiltInCategory,
    BuiltInParameter,
    FilteredElementCollector,
    Transaction,
)

from wbm_numbering.door_numbering import clockwise_angle
from wbm_numbering.revit_context import SwallowWarnings


class WindowInfo(object):
    """Une fenetre candidate a la numerotation, avec son rang/mark calcules."""

    def __init__(self, element, location):
        self.element = element
        self.location = location  # tuple (x, y), ou None
        self.mark = None  # rempli par assign_marks()


def window_location(window):
    loc = window.Location
    if loc is not None and hasattr(loc, "Point") and loc.Point:
        return (loc.Point.X, loc.Point.Y)
    bbox = window.get_BoundingBox(None)
    if bbox:
        return ((bbox.Min.X + bbox.Max.X) / 2.0, (bbox.Min.Y + bbox.Max.Y) / 2.0)
    return None


def collect_windows(doc, view):
    """Fenetres visibles dans `view`."""
    collector = (
        FilteredElementCollector(doc, view.Id)
        .OfCategory(BuiltInCategory.OST_Windows)
        .WhereElementIsNotElementType()
    )
    return [WindowInfo(w, window_location(w)) for w in collector]


def building_center(doc, view):
    """Centre (x, y) du batiment dans la vue active : bounding box des
    murs visibles dans la vue, sinon repli sur le CropBox de la vue."""
    collector = (
        FilteredElementCollector(doc, view.Id)
        .OfCategory(BuiltInCategory.OST_Walls)
        .WhereElementIsNotElementType()
    )
    min_x = min_y = max_x = max_y = None
    for wall in collector:
        bbox = wall.get_BoundingBox(view)
        if not bbox:
            continue
        min_x = bbox.Min.X if min_x is None else min(min_x, bbox.Min.X)
        min_y = bbox.Min.Y if min_y is None else min(min_y, bbox.Min.Y)
        max_x = bbox.Max.X if max_x is None else max(max_x, bbox.Max.X)
        max_y = bbox.Max.Y if max_y is None else max(max_y, bbox.Max.Y)

    if min_x is None:
        crop_box = view.CropBox
        if crop_box:
            return (
                (crop_box.Min.X + crop_box.Max.X) / 2.0,
                (crop_box.Min.Y + crop_box.Max.Y) / 2.0,
            )
        return None

    return ((min_x + max_x) / 2.0, (min_y + max_y) / 2.0)


def build_order(windows, pivot, entry_point):
    """Retourne les fenetres de `windows` (avec position connue) triees
    dans le sens horaire autour de `pivot`, en repartant de
    `entry_point` (meme repere que pour les portes) pour la fenetre
    001. Si `entry_point` est absent, le depart est pris au nord."""
    remaining = [w for w in windows if w.location is not None]
    if pivot is None:
        return remaining

    ref_angle = clockwise_angle(entry_point, pivot) if entry_point is not None else 0.0
    remaining.sort(
        key=lambda w: (clockwise_angle(w.location, pivot) - ref_angle) % 360.0
    )
    return remaining


def assign_marks(ordered_windows, prefix, level_name, digits=3, start=1):
    """Calcule et affecte window.mark pour chaque fenetre de
    `ordered_windows` (ne modifie pas encore le modele, voir
    apply_marks)."""
    for i, window in enumerate(ordered_windows):
        window.mark = "{}.{}.{}".format(prefix, level_name, str(i + start).zfill(digits))
    return ordered_windows


def apply_marks(doc, ordered_windows, transaction_name="Window Mark numbering"):
    """Ecrit window.mark dans le parametre Mark de chaque fenetre, dans
    une transaction unique.

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
        for window in ordered_windows:
            param = window.element.get_Parameter(BuiltInParameter.ALL_MODEL_MARK)
            if param and not param.IsReadOnly:
                param.Set(window.mark)
    except Exception:
        t.RollBack()
        raise
    else:
        t.Commit()
