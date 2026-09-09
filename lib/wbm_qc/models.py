# -*- coding: utf-8 -*-
"""Modeles de donnees du moteur de controle qualite."""


class QCIssue(object):
    """Represente une anomalie detectee par une regle de controle.

    element_id : Autodesk.Revit.DB.ElementId ou None si l'anomalie ne
                  pointe pas vers un element unique (ex: probleme global).
    """

    def __init__(self, element_id, category, rule_name, severity, description):
        self.element_id = element_id
        self.category = category
        self.rule_name = rule_name
        self.severity = severity
        self.description = description

    def __repr__(self):
        return "<QCIssue [{}] {} - {}>".format(
            self.severity, self.rule_name, self.description
        )


# Niveaux de severite standard, du plus au moins bloquant.
SEVERITY_ERROR = "Erreur"
SEVERITY_WARNING = "Avertissement"
SEVERITY_INFO = "Information"

SEVERITY_ORDER = {
    SEVERITY_ERROR: 0,
    SEVERITY_WARNING: 1,
    SEVERITY_INFO: 2,
}
