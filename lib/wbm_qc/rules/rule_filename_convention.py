# -*- coding: utf-8 -*-
"""Controle : le nom du fichier Revit doit respecter la convention WBM
"{18 chiffres numero de projet}_{YYYYMMDD date}.rvt".

Les autres controles (numero de projet, date d'emission) s'appuient
sur ce meme parsing : si le nom de fichier est invalide, ils ne
generent pas d'anomalie de comparaison redondante, cette regle etant
la seule responsable de signaler le probleme de nommage lui-meme.
"""

from wbm_qc.models import QCIssue, SEVERITY_ERROR
from wbm_qc.registry import QCRule, register_rule
from wbm_qc.utils import parse_project_filename


@register_rule
class FilenameConventionRule(QCRule):
    rule_id = "filename_convention"
    name = "Convention de nommage du fichier"
    category = "Informations projet"
    severity = SEVERITY_ERROR
    description = (
        "Verifie que le nom du fichier respecte la convention WBM : "
        "'{18 chiffres numero de projet}_{YYYYMMDD date}.rvt'."
    )

    def check(self, doc):
        project_number, _ = parse_project_filename(doc)
        if project_number is not None:
            return []

        info = doc.ProjectInformation
        return [
            QCIssue(
                element_id=info.Id,
                category=self.category,
                rule_name=self.name,
                severity=self.severity,
                description=(
                    "Renommer '{}' : format attendu "
                    "'{{18 chiffres}}_{{YYYYMMDD}}'.".format(doc.Title)
                ),
            )
        ]
