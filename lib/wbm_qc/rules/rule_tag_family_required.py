# -*- coding: utf-8 -*-
"""Controle : les tags de porte et de fenetre doivent imperativement
utiliser une famille de tag dediee (nom exact).

Un seul avertissement agrege est remonte par type de tag (pas un par
instance non conforme)."""

from Autodesk.Revit.DB import BuiltInCategory, FilteredElementCollector

from wbm_qc.models import QCIssue, SEVERITY_ERROR
from wbm_qc.registry import QCRule, register_rule

_REQUIRED_FAMILIES = [
    (BuiltInCategory.OST_DoorTags, "Porte", "M360_DoorTagV2"),
    (BuiltInCategory.OST_WindowTags, "Fenetre", "M360_Window tag V2"),
]


def _get_family_name(doc, tag):
    tag_type = doc.GetElement(tag.GetTypeId())
    family = getattr(tag_type, "Family", None)
    return family.Name if family else ""


@register_rule
class TagFamilyRequiredRule(QCRule):
    rule_id = "tag_family_required"
    name = "Famille de tag imposee"
    category = "Tags"
    severity = SEVERITY_ERROR
    description = "Les tags de porte/fenetre doivent utiliser la famille imposee."

    def check(self, doc):
        issues = []

        for tag_category, label, required_family in _REQUIRED_FAMILIES:
            tags = (
                FilteredElementCollector(doc)
                .OfCategory(tag_category)
                .WhereElementIsNotElementType()
                .ToElements()
            )

            bad_tags = []
            bad_family_names = set()

            for tag in tags:
                family_name = _get_family_name(doc, tag)
                if family_name == required_family:
                    continue
                bad_tags.append(tag)
                bad_family_names.add(family_name or "?")

            if not bad_tags:
                continue

            issues.append(
                QCIssue(
                    element_id=bad_tags[0].Id,
                    category=self.category,
                    rule_name=self.name,
                    severity=self.severity,
                    description=(
                        "Remplacer la famille de tag {} par '{}' : {} "
                        "tag(s) non conforme(s) ({}).".format(
                            label,
                            required_family,
                            len(bad_tags),
                            ", ".join(sorted(bad_family_names)),
                        )
                    ),
                )
            )

        return issues
