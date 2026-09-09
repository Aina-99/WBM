# -*- coding: utf-8 -*-
"""Controle : nom de feuille = "TypeDeVue - Libre" et coherence avec
les vues effectivement placees sur la feuille.

Types de vue autorises : Grundriss, Vermietungsgrundriss, Ansichten,
Schnitt.

- Pour "Schnitt" : la partie "Libre" liste les identifiants separes
  par "_" (ex : "Schnitt - A-A_B-B").
- Pour les autres types : la partie "Libre" liste les identifiants
  separes par "," (ex : "Grundriss - EG,OG1").

Chaque identifiant de "Libre" doit se retrouver dans le nom d'au moins
une vue liee a la feuille, et chaque vue liee (hors vues dont le nom
contient "Lageplan", exclues du controle) doit contenir au moins un de
ces identifiants.

Exception "Ansichten" : si aucune vue liee ne contient "Ansichten"
dans son nom, la feuille n'est pas controlee (ces vues ne suivent pas
toujours cette convention de nommage).

Les feuilles dont le nom contient "Vorlage" (gabarit / modele de
feuille) sont entierement exclues de ce controle.
"""

from Autodesk.Revit.DB import FilteredElementCollector, ViewSheet

from wbm_qc.models import QCIssue, SEVERITY_ERROR
from wbm_qc.registry import QCRule, register_rule

_ALLOWED_VIEW_TYPES = ["Grundriss", "Vermietungsgrundriss", "Ansichten", "Schnitt", "JPG"]
_SCHNITT_TYPE = "Schnitt"
_ANSICHTEN_TYPE = "Ansichten"
_EXCLUDED_VIEW_NAME = "Lageplan"
_EXCLUDED_SHEET_NAME = "Vorlage"


@register_rule
class SheetNamingRule(QCRule):
    rule_id = "sheet_naming_convention"
    name = "Nommage et liaison des feuilles"
    category = "Feuilles"
    severity = SEVERITY_ERROR
    description = "Nom de feuille = 'TypeDeVue - Libre', coherent avec les vues liees."

    def check(self, doc):
        issues = []
        sheets = FilteredElementCollector(doc).OfClass(ViewSheet).ToElements()

        for sheet in sheets:
            name = sheet.Name or ""

            if _EXCLUDED_SHEET_NAME in name:
                continue

            if " - " not in name:
                issues.append(
                    QCIssue(
                        element_id=sheet.Id,
                        category=self.category,
                        rule_name=self.name,
                        severity=self.severity,
                        description=(
                            "Renommer la feuille {} : format 'TypeDeVue - "
                            "Libre'.".format(sheet.SheetNumber)
                        ),
                    )
                )
                continue

            view_type_part, _, niveau_part = name.partition(" - ")

            if view_type_part not in _ALLOWED_VIEW_TYPES:
                issues.append(
                    QCIssue(
                        element_id=sheet.Id,
                        category=self.category,
                        rule_name=self.name,
                        severity=self.severity,
                        description=(
                            "Corriger le type '{}' (feuille {}) : parmi "
                            "{}.".format(
                                view_type_part,
                                sheet.SheetNumber,
                                ", ".join(_ALLOWED_VIEW_TYPES),
                            )
                        ),
                    )
                )
                continue

            separator = "_" if view_type_part == _SCHNITT_TYPE else ","
            tokens = [t.strip() for t in niveau_part.split(separator) if t.strip()]

            placed_view_ids = sheet.GetAllPlacedViews()
            placed_views = [
                v for v in (doc.GetElement(vid) for vid in placed_view_ids) if v is not None
            ]
            checked_views = [
                v for v in placed_views if _EXCLUDED_VIEW_NAME not in (v.Name or "")
            ]

            if not checked_views:
                issues.append(
                    QCIssue(
                        element_id=sheet.Id,
                        category=self.category,
                        rule_name=self.name,
                        severity=self.severity,
                        description=(
                            "Lier une vue a la feuille {}.".format(sheet.SheetNumber)
                        ),
                    )
                )
                continue

            if view_type_part == _ANSICHTEN_TYPE and not any(
                _ANSICHTEN_TYPE in (v.Name or "") for v in checked_views
            ):
                # exception : pas de vue "Ansichten" liee, on ne controle pas cette feuille
                continue

            for view in checked_views:
                view_name = view.Name or ""
                if tokens and not any(token in view_name for token in tokens):
                    issues.append(
                        QCIssue(
                            element_id=view.Id,
                            category=self.category,
                            rule_name=self.name,
                            severity=self.severity,
                            description=(
                                "Renommer la vue '{}' : doit contenir un "
                                "de [{}] (feuille {}).".format(
                                    view_name, ", ".join(tokens), sheet.SheetNumber
                                )
                            ),
                        )
                    )

            for token in tokens:
                if not any(token in (v.Name or "") for v in checked_views):
                    issues.append(
                        QCIssue(
                            element_id=sheet.Id,
                            category=self.category,
                            rule_name=self.name,
                            severity=self.severity,
                            description=(
                                "Lier une vue contenant '{}' a la feuille "
                                "{}.".format(token, sheet.SheetNumber)
                            ),
                        )
                    )

        return issues
