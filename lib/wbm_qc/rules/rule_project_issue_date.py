# -*- coding: utf-8 -*-
"""Controle : le parametre "Project Issue Date" (format YYYYMMDD) doit
correspondre a la date du jour et a la date du nom de fichier (format
YYMMDD, convention WBM : "{18 chiffres}_{YYMMDD}.rvt")."""

import datetime

from Autodesk.Revit.DB import BuiltInParameter

from wbm_qc.models import QCIssue, SEVERITY_ERROR
from wbm_qc.registry import QCRule, register_rule
from wbm_qc.utils import parse_project_filename


@register_rule
class ProjectIssueDateRule(QCRule):
    rule_id = "project_issue_date_consistency"
    name = "Coherence de la date d'emission"
    category = "Informations projet"
    severity = SEVERITY_ERROR
    description = (
        "Project Issue Date (YYYYMMDD) doit correspondre a la date du "
        "jour et a la date du nom de fichier (YYMMDD)."
    )

    def check(self, doc):
        info = doc.ProjectInformation
        param = info.get_Parameter(BuiltInParameter.PROJECT_ISSUE_DATE)
        issue_date = (param.AsString() or "").strip() if param else ""

        today_full = datetime.date.today().strftime("%Y%m%d")
        _, filename_date = parse_project_filename(doc)
        filename_date_full = ("20" + filename_date) if filename_date else None

        values = {
            "Project Issue Date": issue_date or "vide",
            "aujourd'hui": today_full,
        }
        if filename_date_full is not None:
            values["nom de fichier"] = filename_date_full

        if len(set(values.values())) <= 1:
            return []

        detail = ", ".join(
            "{}={}".format(label, value) for label, value in sorted(values.items())
        )
        return [
            QCIssue(
                element_id=info.Id,
                category=self.category,
                rule_name=self.name,
                severity=self.severity,
                description="Corriger la date d'emission (YYYYMMDD) : {}.".format(detail),
            )
        ]
