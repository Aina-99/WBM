# -*- coding: utf-8 -*-
"""Door Numbering (Beta).

Calcule un numero "Mark" propose pour les portes de la vue active,
selon la convention WBM (voir wbm_numbering.door_numbering), puis
affiche le resultat dans une fenetre de previsualisation
(PreviewWindow.xaml) avant d'ecrire quoi que ce soit dans le modele.

Ce script ne contient aucune logique metier : il orchestre le calcul
(wbm_numbering) et la fenetre (preview_window). Pour ajuster la regle
de numerotation, voir WBM.extension/lib/wbm_numbering/door_numbering.py.
"""

from pyrevit import revit, forms, script

from wbm_numbering.door_numbering import (
    build_order,
    assign_marks,
    collect_doors,
    find_entry_point,
)

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
        "vue en plan pour numeroter ses portes.".format(view.Name),
        exitscript=True,
    )

prefix = forms.ask_for_string(
    default="T", prompt="Prefixe de numerotation", title="Door Numbering (Beta)"
)
if not prefix:
    script.exit()

entry_marker = forms.ask_for_string(
    default="M360_Entry",
    prompt="Texte identifiant le repere d'entree (annotation visible dans la vue)",
    title="Door Numbering (Beta)",
)
if entry_marker is None:
    script.exit()

doors = collect_doors(doc, view)
if not doors:
    forms.alert("Aucune porte trouvee dans la vue active.", exitscript=True)

entry_point = find_entry_point(doc, view, entry_marker) if entry_marker else None
if entry_point is None:
    forms.alert(
        "Repere d'entree '{}' introuvable dans la vue active : les portes "
        "sans FromRoom seront positionnees sans reference geometrique "
        "d'entree (voir la previsualisation).".format(entry_marker)
    )

ordered = build_order(doors, entry_point)
assign_marks(ordered, prefix, level.Name)

show_preview_window(doc, uidoc, ordered)
