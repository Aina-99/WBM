# -*- coding: utf-8 -*-
"""Configuration et helpers partages par les regles de controle des tags
(pieces, portes, fenetres).

Convention WBM :
    Piece   : Number = "{Niveau}.NNN"      (ex : "EG.001")
    Porte   : Mark   = "T.{Niveau}.NNN"    (ex : "T.EG.001")
    Fenetre : Mark   = "F.{Niveau}.NNN"    (ex : "F.EG.001")
    NNN = increment sur 3 chiffres, unique et reinitialise a 1 par niveau.
"""

import re

from Autodesk.Revit.DB import BuiltInCategory, BuiltInParameter, ElementId


class TagTypeConfig(object):
    def __init__(self, key, label, element_category, tag_category, prefix, value_param):
        self.key = key
        self.label = label
        self.element_category = element_category
        self.tag_category = tag_category
        self.prefix = prefix
        self.value_param = value_param


TAG_TYPES = [
    TagTypeConfig(
        key="room",
        label="Piece",
        element_category=BuiltInCategory.OST_Rooms,
        tag_category=BuiltInCategory.OST_RoomTags,
        prefix="",
        value_param=BuiltInParameter.ROOM_NUMBER,
    ),
    TagTypeConfig(
        key="door",
        label="Porte",
        element_category=BuiltInCategory.OST_Doors,
        tag_category=BuiltInCategory.OST_DoorTags,
        prefix="T.",
        value_param=BuiltInParameter.ALL_MODEL_MARK,
    ),
    TagTypeConfig(
        key="window",
        label="Fenetre",
        element_category=BuiltInCategory.OST_Windows,
        tag_category=BuiltInCategory.OST_WindowTags,
        prefix="F.",
        value_param=BuiltInParameter.ALL_MODEL_MARK,
    ),
]

_SUFFIX_LENGTH = 3
_SUFFIX_PATTERN = re.compile(r"(\d{%d})$" % _SUFFIX_LENGTH)


def get_element_level(doc, element):
    """Retourne le Level associe a l'element (Room.Level ou LevelId
    generique), ou None si aucun niveau n'est assigne."""
    level = getattr(element, "Level", None)
    if level is not None:
        return level

    level_id = getattr(element, "LevelId", None)
    if level_id is not None and level_id != ElementId.InvalidElementId:
        return doc.GetElement(level_id)

    return None


def get_value(element, value_param):
    param = element.get_Parameter(value_param)
    return (param.AsString() or "").strip() if param else ""


def build_tag_pattern(prefix, level_name):
    return re.compile(
        r"^{}{}\.\d{{{}}}$".format(re.escape(prefix), re.escape(level_name), _SUFFIX_LENGTH)
    )


def extract_suffix(value):
    """Extrait l'entier des 3 derniers chiffres de la valeur, ou None."""
    match = _SUFFIX_PATTERN.search(value)
    return int(match.group(1)) if match else None


def get_tagged_element_ids(tag):
    """Retourne la liste des ElementId des elements references par un
    tag, quelle que soit la version de l'API Revit (RoomTag.Room,
    IndependentTag.GetTaggedLocalElementIds, ou l'ancien
    TaggedLocalElementId)."""
    room = getattr(tag, "Room", None)
    if room is not None:
        return [room.Id]

    get_ids = getattr(tag, "GetTaggedLocalElementIds", None)
    if get_ids is not None:
        try:
            return list(get_ids())
        except Exception:
            pass

    single = getattr(tag, "TaggedLocalElementId", None)
    if single is not None and single != ElementId.InvalidElementId:
        return [single]

    return []
