# -*- coding: utf-8 -*-
"""Controle : le nombre d'elements (pieces, portes, fenetres) doit
correspondre au nombre de tags. Signale les elements sans tag et les
tags orphelins (sans element rattache)."""

from Autodesk.Revit.DB import FilteredElementCollector

from wbm_qc.models import QCIssue, SEVERITY_ERROR
from wbm_qc.registry import QCRule, register_rule
from wbm_qc.tags import TAG_TYPES, get_tagged_element_ids


@register_rule
class TagCountMatchRule(QCRule):
    rule_id = "tag_count_match"
    name = "Correspondance elements / tags"
    category = "Tags"
    severity = SEVERITY_ERROR
    description = "Ajouter les tags manquants, supprimer les tags orphelins."

    def check(self, doc):
        issues = []

        for tag_type in TAG_TYPES:
            elements = (
                FilteredElementCollector(doc)
                .OfCategory(tag_type.element_category)
                .WhereElementIsNotElementType()
                .ToElements()
            )
            tags = (
                FilteredElementCollector(doc)
                .OfCategory(tag_type.tag_category)
                .WhereElementIsNotElementType()
                .ToElements()
            )

            tagged_ids = set()
            orphan_tags = []
            for tag in tags:
                host_ids = get_tagged_element_ids(tag)
                if not host_ids:
                    orphan_tags.append(tag)
                for host_id in host_ids:
                    tagged_ids.add(host_id.IntegerValue)

            for element in elements:
                if element.Id.IntegerValue in tagged_ids:
                    continue
                issues.append(
                    QCIssue(
                        element_id=element.Id,
                        category=self.category,
                        rule_name=self.name,
                        severity=self.severity,
                        description=(
                            "Ajouter le tag {} manquant (Id "
                            "{}).".format(tag_type.label, element.Id.IntegerValue)
                        ),
                    )
                )

            for tag in orphan_tags:
                issues.append(
                    QCIssue(
                        element_id=tag.Id,
                        category=self.category,
                        rule_name=self.name,
                        severity=self.severity,
                        description=(
                            "Supprimer le tag {} orphelin (Id "
                            "{}).".format(tag_type.label, tag.Id.IntegerValue)
                        ),
                    )
                )

        return issues
