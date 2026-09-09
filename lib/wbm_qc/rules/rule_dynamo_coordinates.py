# -*- coding: utf-8 -*-
"""Controle : verifie que les coordonnees inscrites dans Project
Information (WBM_KoordinateX/Y/Z) correspondent toujours a la position
actuelle du Project Base Point.

Contrairement aux autres controles Dynamo, celui-ci detecte une
veritable obsolescence (pas seulement une valeur jamais renseignee) :
la position du Project Base Point est comparee directement a la valeur
stockee, sans necessiter d'horodatage.
"""

import re

from Autodesk.Revit.DB import BuiltInCategory, BuiltInParameter, FilteredElementCollector

from wbm_qc.models import QCIssue, SEVERITY_WARNING
from wbm_qc.registry import QCRule, register_rule

_FEET_TO_METERS = 0.3048
_TOLERANCE_M = 0.05
_DYNAMO_SCRIPT = "GET_COORDINATES.dyn"

_NUMBER_PATTERN = re.compile(r"[-+]?\d+(?:\.\d+)?")

# (parametre Project Information, BuiltInParameter du Project Base Point, libelle)
_AXES = [
    ("WBM_KoordinateX", BuiltInParameter.BASEPOINT_EASTWEST_PARAM, "Est/Ouest"),
    ("WBM_KoordinateY", BuiltInParameter.BASEPOINT_NORTHSOUTH_PARAM, "Nord/Sud"),
    ("WBM_KoordinateZ", BuiltInParameter.BASEPOINT_ELEVATION_PARAM, "Elevation"),
]


def _extract_number(text):
    match = _NUMBER_PATTERN.search(text or "")
    return float(match.group()) if match else None


@register_rule
class DynamoCoordinatesFreshnessRule(QCRule):
    rule_id = "dynamo_coordinates_freshness"
    name = "Coordonnees du point de base a jour"
    category = "Donnees Dynamo"
    severity = SEVERITY_WARNING
    description = (
        "Compare les coordonnees stockees dans Project Information "
        "(WBM_KoordinateX/Y/Z) a la position actuelle du Project Base "
        "Point : relancer '{}' en cas d'ecart.".format(_DYNAMO_SCRIPT)
    )

    def check(self, doc):
        base_points = (
            FilteredElementCollector(doc)
            .OfCategory(BuiltInCategory.OST_ProjectBasePoint)
            .WhereElementIsNotElementType()
            .ToElements()
        )
        base_point = next(iter(base_points), None)
        if base_point is None:
            return []

        info = doc.ProjectInformation
        issues = []

        for param_name, bip, label in _AXES:
            stored_param = info.LookupParameter(param_name)
            if stored_param is None:
                continue

            stored_value = _extract_number(stored_param.AsString())
            if stored_value is None:
                continue

            current_param = base_point.get_Parameter(bip)
            if current_param is None:
                continue

            current_value_m = current_param.AsDouble() * _FEET_TO_METERS

            if abs(current_value_m - stored_value) > _TOLERANCE_M:
                issues.append(
                    QCIssue(
                        element_id=info.Id,
                        category=self.category,
                        rule_name=self.name,
                        severity=self.severity,
                        description=(
                            "Relancer '{}' : {} obsolete ({:.2f} m "
                            "stocke vs {:.2f} m actuel).".format(
                                _DYNAMO_SCRIPT,
                                label,
                                stored_value,
                                current_value_m,
                            )
                        ),
                    )
                )

        return issues
