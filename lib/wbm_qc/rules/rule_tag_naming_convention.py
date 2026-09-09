# -*- coding: utf-8 -*-
"""Controle : Number (pieces) / Mark (portes, fenetres) doivent suivre
"{Niveau}.NNN" (pieces), "T.{Niveau}.NNN" (portes) ou "F.{Niveau}.NNN"
(fenetres), NNN = 3 chiffres. Voir wbm_qc.tags pour la convention."""

from Autodesk.Revit.DB import FilteredElementCollector

from wbm_qc.models import QCIssue, SEVERITY_ERROR
from wbm_qc.registry import QCRule, register_rule
from wbm_qc.tags import TAG_TYPES, build_tag_pattern, get_element_level, get_value


@register_rule
class TagNamingConventionRule(QCRule):
    rule_id = "tag_naming_convention"
    name = "Convention de nommage des tags"
    category = "Tags"
    severity = SEVERITY_ERROR
    description = "Number/Mark doivent suivre '[T.|F.]Niveau.NNN' (3 chiffres)."

    def check(self, doc):
        issues = []

        for tag_type in TAG_TYPES:
            elements = (
                FilteredElementCollector(doc)
                .OfCategory(tag_type.element_category)
                .WhereElementIsNotElementType()
                .ToElements()
            )

            for element in elements:
                level = get_element_level(doc, element)
                value = get_value(element, tag_type.value_param)

                if level is None:
                    issues.append(
                        QCIssue(
                            element_id=element.Id,
                            category=self.category,
                            rule_name=self.name,
                            severity=self.severity,
                            description=(
                                "Assigner un niveau : {} '{}' (Id "
                                "{}).".format(
                                    tag_type.label, value or "?", element.Id.IntegerValue
                                )
                            ),
                        )
                    )
                    continue

                pattern = build_tag_pattern(tag_type.prefix, level.Name)
                if pattern.match(value):
                    continue

                issues.append(
                    QCIssue(
                        element_id=element.Id,
                        category=self.category,
                        rule_name=self.name,
                        severity=self.severity,
                        description=(
                            "Corriger {} '{}' (Id {}) : attendu "
                            "'{}{}.NNN'.".format(
                                tag_type.label,
                                value or "vide",
                                element.Id.IntegerValue,
                                tag_type.prefix,
                                level.Name,
                            )
                        ),
                    )
                )

        return issues
