# -*- coding: utf-8 -*-
"""Moteur d'execution des regles de controle qualite.

run_checks() decouvre et execute toutes les regles enregistrees (ou un
sous-ensemble via rule_filter) et agrege les anomalies (QCIssue) ainsi
que les erreurs d'execution eventuelles, sans jamais interrompre le
controle global si une regle plante.
"""

# force l'import du package rules pour declencher l'enregistrement de
# toutes les regles disponibles (voir wbm_qc/rules/__init__.py)
import wbm_qc.rules  # noqa: F401

from wbm_qc.registry import get_registered_rules


def list_available_rules():
    """Retourne les classes de regles disponibles, pour peupler un
    filtre / une liste de selection dans l'UI."""
    return get_registered_rules()


def run_checks(doc, rule_filter=None, progress=None):
    """Execute les regles de controle qualite sur le document Revit.

    doc          : Autodesk.Revit.DB.Document
    rule_filter  : iterable de rule_id a executer, ou None pour tout executer
    progress     : objet exposant update_progress(value, max_value)
                   (compatible pyrevit.forms.ProgressBar), optionnel

    Retourne (issues, rule_errors) :
        issues      : list[QCIssue]
        rule_errors : list[(rule_name, message)] pour les regles ayant
                      leve une exception pendant leur execution
    """
    rules = get_registered_rules()
    if rule_filter is not None:
        rule_filter = set(rule_filter)
        rules = [r for r in rules if r.rule_id in rule_filter]

    rules = [r for r in rules if getattr(r, "enabled", True)]

    issues = []
    rule_errors = []
    total = len(rules)

    for index, rule_cls in enumerate(rules):
        if progress is not None:
            try:
                progress.update_progress(index + 1, total)
            except Exception:
                pass

        rule = rule_cls()
        try:
            found = rule.check(doc) or []
            issues.extend(found)
        except Exception as ex:
            rule_errors.append((rule.name, str(ex)))

    return issues, rule_errors
