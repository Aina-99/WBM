# -*- coding: utf-8 -*-
"""Controle : les categories de tags (pieces, portes, fenetres) doivent
etre visibles dans toutes les vues dont le nom contient "Grundriss".

Limite connue : ce controle verifie la visibilite au niveau de la
categorie dans la vue (View.GetCategoryHidden), pas element par
element."""

from Autodesk.Revit.DB import FilteredElementCollector, View

from wbm_qc.models import QCIssue, SEVERITY_ERROR
from wbm_qc.registry import QCRule, register_rule
from wbm_qc.tags import TAG_TYPES

_VIEW_NAME_FILTER = "Grundriss"


@register_rule
class TagVisibilityGrundrissRule(QCRule):
    rule_id = "tag_visibility_grundriss"
    name = "Visibilite des tags (Grundriss)"
    category = "Tags"
    severity = SEVERITY_ERROR
    description = "Afficher les categories de tags masquees dans les vues Grundriss."

    def check(self, doc):
        issues = []
        categories = doc.Settings.Categories

        views = FilteredElementCollector(doc).OfClass(View).ToElements()
        for view in views:
            if view.IsTemplate:
                continue
            if _VIEW_NAME_FILTER not in (view.Name or ""):
                continue

            for tag_type in TAG_TYPES:
                tag_category = categories.get_Item(tag_type.tag_category)
                if tag_category is None:
                    continue

                try:
                    hidden = view.GetCategoryHidden(tag_category.Id)
                except Exception:
                    continue

                if not hidden:
                    continue

                issues.append(
                    QCIssue(
                        element_id=view.Id,
                        category=self.category,
                        rule_name=self.name,
                        severity=self.severity,
                        description=(
                            "Afficher les tags {} dans la vue "
                            "'{}'.".format(tag_type.label, view.Name)
                        ),
                    )
                )

        return issues
