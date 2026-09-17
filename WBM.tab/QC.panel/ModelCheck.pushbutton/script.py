# -*- coding: utf-8 -*-
"""Contrôle Modèle.

Exécute toutes les règles de contrôle qualité enregistrées dans
wbm_qc.rules sur le modèle Revit actif, puis affiche les anomalies
détectées dans une fenêtre de résultats interactive (ResultsWindow.xaml).

Ce script ne contient aucune logique metier : il se contente
d'orchestrer le moteur (wbm_qc) et la fenetre (results_window). Pour
ajouter un nouveau controle, voir WBM.extension/lib/wbm_qc/rules/.
"""

from pyrevit import revit, forms, script

from wbm_qc.engine import run_checks
from wbm_numbering.revit_context import ApiContextRunner

from results_window import show_results_window

doc = revit.doc
uidoc = revit.uidoc

output = script.get_output()
output.close_others()

with forms.ProgressBar(title="Contrôle du modèle en cours... ({value} / {max_value})") as pb:
    issues, rule_errors = run_checks(doc, progress=pb)

if rule_errors:
    print("Certaines règles n'ont pas pu être exécutées :")
    for rule_name, message in rule_errors:
        print(" - {} : {}".format(rule_name, message))

# Doit etre cree ici : ExternalEvent.Create exige un contexte API valide,
# que la fenetre non modale n'a plus une fois ce script termine.
api_runner = ApiContextRunner()

show_results_window(doc, uidoc, api_runner, issues, rule_errors)
