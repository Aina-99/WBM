# -*- coding: utf-8 -*-
"""Controle : le parametre "Project Number" doit contenir exactement
18 chiffres et correspondre au numero de projet du nom de fichier."""

import re

from Autodesk.Revit.DB import BuiltInParameter

from wbm_qc.models import QCIssue, SEVERITY_ERROR
from wbm_qc.registry import QCRule, register_rule
from wbm_qc.utils import parse_project_filename

_PROJECT_NUMBER_PATTERN = re.compile(r"^\d{18}$")


@register_rule
class ProjectNumberRule(QCRule):
    rule_id = "project_number_consistency"
    name = "Coherence du numero de projet"
    category = "Informations projet"
    severity = SEVERITY_ERROR
    description = (
        "Verifie que le parametre 'Project Number' contient exactement "
        "18 chiffres et correspond au numero de projet du nom de fichier."
    )

    def check(self, doc):
        issues = []
        info = doc.ProjectInformation
        param = info.get_Parameter(BuiltInParameter.PROJECT_NUMBER)
        project_number = (param.AsString() or "").strip() if param else ""

        if not _PROJECT_NUMBER_PATTERN.match(project_number):
            issues.append(
                QCIssue(
                    element_id=info.Id,
                    category=self.category,
                    rule_name=self.name,
                    severity=self.severity,
                    description=(
                        "Corriger 'Project Number' : 18 chiffres requis "
                        "(actuel '{}').".format(project_number or "vide")
                    ),
                )
            )

        filename_number, _ = parse_project_filename(doc)
        if filename_number is not None and project_number != filename_number:
            issues.append(
                QCIssue(
                    element_id=info.Id,
                    category=self.category,
                    rule_name=self.name,
                    severity=self.severity,
                    description=(
                        "Aligner 'Project Number' ('{}') sur le fichier "
                        "('{}').".format(project_number or "vide", filename_number)
                    ),
                )
            )

        return issues
