# -*- coding: utf-8 -*-
"""Window Numbering (Beta).

Ouvre la fenetre de previsualisation (PreviewWindow.xaml), qui regroupe
la saisie du prefixe et du repere d'entree, le calcul du numero "Mark"
propose pour les fenetres de la vue active (voir
wbm_numbering.window_numbering) et l'application au modele, avant
d'ecrire quoi que ce soit.

Ce script ne contient aucune logique metier : il verifie juste que la
vue active est exploitable, puis ouvre la fenetre (preview_window).
Pour ajuster la regle de numerotation, voir
WBM.extension/lib/wbm_numbering/window_numbering.py.
"""

from pyrevit import revit, forms, script

from wbm_numbering.revit_context import ApiContextRunner

from preview_window import show_preview_window

doc = revit.doc
uidoc = revit.uidoc
view = revit.active_view

output = script.get_output()
output.close_others()

level = view.GenLevel
if level is None:
    forms.alert(
        "La vue active '{}' n'est pas associee a un niveau. Ouvrez une "
        "vue en plan pour numeroter ses fenetres.".format(view.Name),
        exitscript=True,
    )

# Doit etre cree ici : ExternalEvent.Create exige un contexte API valide,
# que la fenetre non modale n'a plus une fois ce script termine.
api_runner = ApiContextRunner()

show_preview_window(doc, uidoc, view, api_runner)
