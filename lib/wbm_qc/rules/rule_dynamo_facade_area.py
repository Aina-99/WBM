# -*- coding: utf-8 -*-
"""Controle : verifie que les elements de facade (portes, fenetres,
murs, panneaux de mur-rideau) ont bien une surface calculee par le
script Dynamo FASSADE_AREA_SCHEDULE_2.0.dyn.

Limite connue : ce script Dynamo n'ecrit aucun horodatage ni compteur
d'execution dans le modele. Ce controle ne peut donc pas detecter une
donnee "perimee" au sens strict (ex : un mur redimensionne apres le
dernier passage du script) : il detecte uniquement les elements dont
le parametre n'a jamais ete rempli, ce qui couvre le cas le plus
frequent (elements crees depuis le dernier passage du script).
"""

from Autodesk.Revit.DB import BuiltInCategory, FilteredElementCollector

from wbm_qc.models import QCIssue, SEVERITY_WARNING
from wbm_qc.registry import QCRule, register_rule

_PARAM_AREA = "WBM_FacadeArea_Area"
_CATEGORIES = [
    BuiltInCategory.OST_Doors,
    BuiltInCategory.OST_Windows,
    BuiltInCategory.OST_Walls,
    BuiltInCategory.OST_CurtainWallPanels,
]
_DYNAMO_SCRIPT = "FASSADE_AREA_SCHEDULE_2.0.dyn"


@register_rule
class DynamoFacadeAreaFreshnessRule(QCRule):
    rule_id = "dynamo_facade_area_freshness"
    name = "Surfaces de facade a jour"
    category = "Donnees Dynamo"
    severity = SEVERITY_WARNING
    description = (
        "Detecte les elements de facade dont le parametre '{}' n'est "
        "pas renseigne : relancer '{}'.".format(_PARAM_AREA, _DYNAMO_SCRIPT)
    )

    def check(self, doc):
        issues = []

        for category in _CATEGORIES:
            elements = (
                FilteredElementCollector(doc)
                .OfCategory(category)
                .WhereElementIsNotElementType()
                .ToElements()
            )

            for element in elements:
                param = element.LookupParameter(_PARAM_AREA)
                if param is None:
                    continue
                if param.HasValue and param.AsDouble() > 0:
                    continue

                issues.append(
                    QCIssue(
                        element_id=element.Id,
                        category=self.category,
                        rule_name=self.name,
                        severity=self.severity,
                        description=(
                            "Relancer '{}' : surface manquante ({}, Id "
                            "{}).".format(
                                _DYNAMO_SCRIPT,
                                element.Category.Name if element.Category else "?",
                                element.Id.IntegerValue,
                            )
                        ),
                    )
                )

        return issues
