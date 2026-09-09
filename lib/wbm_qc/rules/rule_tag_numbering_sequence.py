# -*- coding: utf-8 -*-
"""Controle : l'increment (3 derniers chiffres) de Number/Mark doit etre
unique et former une sequence continue 001..N, reinitialisee a 1 par
niveau. Les valeurs qui ne respectent pas le format de base sont deja
signalees par rule_tag_naming_convention et sont ignorees ici."""

from collections import defaultdict

from Autodesk.Revit.DB import FilteredElementCollector

from wbm_qc.models import QCIssue, SEVERITY_ERROR
from wbm_qc.registry import QCRule, register_rule
from wbm_qc.tags import TAG_TYPES, extract_suffix, get_element_level, get_value


@register_rule
class TagNumberingSequenceRule(QCRule):
    rule_id = "tag_numbering_sequence"
    name = "Sequence d'incrementation des tags"
    category = "Tags"
    severity = SEVERITY_ERROR
    description = "Increments dupliques ou manquants dans la sequence 001..N par niveau."

    def check(self, doc):
        issues = []

        for tag_type in TAG_TYPES:
            elements = (
                FilteredElementCollector(doc)
                .OfCategory(tag_type.element_category)
                .WhereElementIsNotElementType()
                .ToElements()
            )

            groups = defaultdict(list)
            for element in elements:
                level = get_element_level(doc, element)
                if level is None:
                    continue
                value = get_value(element, tag_type.value_param)
                suffix = extract_suffix(value)
                if suffix is None:
                    continue
                groups[level.Name].append((suffix, element, value))

            for level_name, items in groups.items():
                counts = defaultdict(list)
                for suffix, element, value in items:
                    counts[suffix].append((element, value))

                for suffix, occurrences in counts.items():
                    if len(occurrences) <= 1:
                        continue
                    for element, value in occurrences:
                        issues.append(
                            QCIssue(
                                element_id=element.Id,
                                category=self.category,
                                rule_name=self.name,
                                severity=self.severity,
                                description=(
                                    "Renumeroter {} '{}' (Id {}) : "
                                    "doublon niveau {}.".format(
                                        tag_type.label,
                                        value,
                                        element.Id.IntegerValue,
                                        level_name,
                                    )
                                ),
                            )
                        )

                expected = set(range(1, len(items) + 1))
                missing = sorted(expected - set(counts.keys()))
                if missing:
                    anchor_element = items[0][1]
                    issues.append(
                        QCIssue(
                            element_id=anchor_element.Id,
                            category=self.category,
                            rule_name=self.name,
                            severity=self.severity,
                            description=(
                                "Combler {} niveau {} : increment(s) {} "
                                "manquant(s).".format(
                                    tag_type.label,
                                    level_name,
                                    ", ".join("%03d" % m for m in missing),
                                )
                            ),
                        )
                    )

        return issues
