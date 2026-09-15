# -*- coding: utf-8 -*-
"""Controle : WBM_Raumbreite / WBM_Raumhöhe doivent correspondre a une
geometrie recalculee en direct (meme algorithme que
GET_GEOMETRY_ROOMS_1.0.dyn : rectangle englobant de surface minimale,
voir wbm_qc.geometry).

L'objectif n'est pas de verifier que largeur x profondeur == surface
Revit (invalide des qu'une piece n'est pas rectangulaire, ex. formes
en L), mais de detecter si le script Dynamo a bien ete relance apres
une modification de la geometrie de la piece."""

from Autodesk.Revit.DB import BuiltInCategory, FilteredElementCollector

from wbm_qc.geometry import compute_room_obb_dimensions
from wbm_qc.models import QCIssue, SEVERITY_WARNING
from wbm_qc.registry import QCRule, register_rule

_PARAM_WIDTH = "WBM_Raumbreite"
_PARAM_DEPTH = u"WBM_Raumhöhe"
_DYNAMO_SCRIPT = "GET_GEOMETRY_ROOMS_1.0.dyn"

_FT_TO_M = 0.3048
_TOLERANCE_M = 0.1


@register_rule
class RoomAreaConsistencyRule(QCRule):
    rule_id = "room_area_consistency"
    name = "Geometrie des pieces a jour (largeur/profondeur)"
    category = "Pieces"
    severity = SEVERITY_WARNING
    description = (
        "WBM_Raumbreite/Raumhöhe doivent correspondre a la geometrie "
        "actuelle : relancer '{}' sinon.".format(_DYNAMO_SCRIPT)
    )

    def check(self, doc):
        issues = []
        rooms = (
            FilteredElementCollector(doc)
            .OfCategory(BuiltInCategory.OST_Rooms)
            .WhereElementIsNotElementType()
            .ToElements()
        )

        for room in rooms:
            area_ft2 = getattr(room, "Area", 0.0) or 0.0
            if area_ft2 <= 0.0:
                # deja couvert par le controle des pieces non delimitees
                continue

            width_param = room.LookupParameter(_PARAM_WIDTH)
            depth_param = room.LookupParameter(_PARAM_DEPTH)
            has_params = (
                width_param is not None
                and width_param.HasValue
                and width_param.AsDouble() > 0
                and depth_param is not None
                and depth_param.HasValue
                and depth_param.AsDouble() > 0
            )

            if not has_params:
                # deja signale par rule_dynamo_room_geometry (valeur manquante)
                continue

            width_ft, depth_ft = compute_room_obb_dimensions(room)
            if width_ft is None or depth_ft is None:
                continue

            stored_width_m = width_param.AsDouble() * _FT_TO_M
            stored_depth_m = depth_param.AsDouble() * _FT_TO_M
            current_width_m = width_ft * _FT_TO_M
            current_depth_m = depth_ft * _FT_TO_M

            if (
                abs(stored_width_m - current_width_m) <= _TOLERANCE_M
                and abs(stored_depth_m - current_depth_m) <= _TOLERANCE_M
            ):
                continue

            number = room.Number if room.Number else "?"
            issues.append(
                QCIssue(
                    element_id=room.Id,
                    category=self.category,
                    rule_name=self.name,
                    severity=self.severity,
                    description=(
                        "Relancer '{}' : geometrie de la piece '{}' (Id "
                        "{}) obsolete ({:.1f}x{:.1f} m stocke vs "
                        "{:.1f}x{:.1f} m actuel).".format(
                            _DYNAMO_SCRIPT,
                            number,
                            room.Id.IntegerValue,
                            stored_width_m,
                            stored_depth_m,
                            current_width_m,
                            current_depth_m,
                        )
                    ),
                )
            )

        return issues
