# -*- coding: utf-8 -*-
"""Controle : verifie que les pieces delimitees ont bien une largeur et
une profondeur calculees par le script Dynamo
GET_GEOMETRY_ROOMS_1.0.dyn.

Meme limite que les autres controles Dynamo : pas d'horodatage natif
disponible dans le modele, detection basee sur la presence/absence de
valeur (voir rule_dynamo_facade_area.py pour le detail).
"""

from Autodesk.Revit.DB import BuiltInCategory, FilteredElementCollector

from wbm_qc.models import QCIssue, SEVERITY_WARNING
from wbm_qc.registry import QCRule, register_rule

_PARAM_WIDTH = "WBM_Raumbreite"
_PARAM_DEPTH = u"WBM_Raumhöhe"
_DYNAMO_SCRIPT = "GET_GEOMETRY_ROOMS_1.0.dyn"


@register_rule
class DynamoRoomGeometryFreshnessRule(QCRule):
    rule_id = "dynamo_room_geometry_freshness"
    name = "Geometrie des pieces a jour"
    category = "Donnees Dynamo"
    severity = SEVERITY_WARNING
    description = (
        "Detecte les pieces delimitees dont la largeur ou la profondeur "
        "('{}' / '{}') n'est pas renseignee : relancer "
        "'{}'.".format(_PARAM_WIDTH, _PARAM_DEPTH, _DYNAMO_SCRIPT)
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
            area = getattr(room, "Area", 0.0) or 0.0
            if area <= 0.0:
                # deja couvert par un controle dedie aux pieces non delimitees
                continue

            width_param = room.LookupParameter(_PARAM_WIDTH)
            depth_param = room.LookupParameter(_PARAM_DEPTH)

            missing = []
            if width_param is None or not width_param.HasValue or width_param.AsDouble() <= 0:
                missing.append(_PARAM_WIDTH)
            if depth_param is None or not depth_param.HasValue or depth_param.AsDouble() <= 0:
                missing.append(_PARAM_DEPTH)

            if not missing:
                continue

            number = room.Number if room.Number else "?"
            issues.append(
                QCIssue(
                    element_id=room.Id,
                    category=self.category,
                    rule_name=self.name,
                    severity=self.severity,
                    description=(
                        "Relancer '{}' : {} manquant (piece '{}', Id "
                        "{}).".format(
                            _DYNAMO_SCRIPT,
                            " / ".join(missing),
                            number,
                            room.Id.IntegerValue,
                        )
                    ),
                )
            )

        return issues
