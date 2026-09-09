# -*- coding: utf-8 -*-
"""Controle : les cartouches (titleblocks) places sur les feuilles
doivent appartenir a une famille dont le nom commence par "WBM".

Les feuilles ne portant aucune vue (feuille vide / placeholder) sont
ignorees par ce controle."""

from Autodesk.Revit.DB import BuiltInCategory, ElementId, FilteredElementCollector

from wbm_qc.models import QCIssue, SEVERITY_ERROR
from wbm_qc.registry import QCRule, register_rule

_REQUIRED_PREFIX = "WBM"


@register_rule
class TitleBlockNamingRule(QCRule):
    rule_id = "titleblock_naming"
    name = "Nommage des cartouches"
    category = "Feuilles"
    severity = SEVERITY_ERROR
    description = (
        "Verifie que tous les cartouches places sur des feuilles "
        "appartiennent a une famille dont le nom commence par "
        "'{}'.".format(_REQUIRED_PREFIX)
    )

    def check(self, doc):
        issues = []
        titleblocks = (
            FilteredElementCollector(doc)
            .OfCategory(BuiltInCategory.OST_TitleBlocks)
            .WhereElementIsNotElementType()
            .ToElements()
        )

        for titleblock in titleblocks:
            owner_id = titleblock.OwnerViewId
            host_sheet = (
                doc.GetElement(owner_id)
                if owner_id and owner_id != ElementId.InvalidElementId
                else None
            )

            if host_sheet is not None:
                placed_views = host_sheet.GetAllPlacedViews()
                if placed_views is None or placed_views.Count == 0:
                    # feuille sans aucune vue liee : on ne controle pas son cartouche
                    continue

            symbol = titleblock.Symbol
            family_name = symbol.Family.Name if symbol and symbol.Family else ""

            if family_name.startswith(_REQUIRED_PREFIX):
                continue

            sheet_number = host_sheet.SheetNumber if host_sheet else "?"

            issues.append(
                QCIssue(
                    element_id=titleblock.Id,
                    category=self.category,
                    rule_name=self.name,
                    severity=self.severity,
                    description=(
                        "Renommer la famille '{}' avec le prefixe '{}' "
                        "(feuille {}).".format(
                            family_name or "?", _REQUIRED_PREFIX, sheet_number
                        )
                    ),
                )
            )

        return issues
