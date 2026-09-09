# -*- coding: utf-8 -*-
"""Code-behind de la fenetre de previsualisation Door Numbering (Beta).

L'interface (PreviewWindow.xaml) reste entierement definie en XAML,
conformement a la regle du projet : ce module ne fait que la piloter
(donnees, selection, application des Mark).
"""

import os

from System.Collections.Generic import List
from Autodesk.Revit.DB import ElementId

from pyrevit import forms

from wbm_numbering.door_numbering import apply_marks


def _family_name(element):
    try:
        return element.Symbol.Family.Name
    except Exception:
        return "-"


class DoorRowVM(object):
    """Objet expose au binding WPF pour une ligne de la previsualisation."""

    def __init__(self, rank, door):
        self.Rank = rank
        self.Mark = door.mark
        self.Id = door.element.Id.IntegerValue
        self.Family = _family_name(door.element)
        self.FromRoom = door.from_room.Number if door.from_room else "(exterieur)"
        self.ToRoom = door.to_room.Number if door.to_room else "-"
        self.element_id = door.element.Id


class DoorNumberingPreviewWindow(forms.WPFWindow):
    def __init__(self, xaml_file, doc, uidoc, ordered_doors):
        forms.WPFWindow.__init__(self, xaml_file)
        self.doc = doc
        self.uidoc = uidoc
        self.ordered_doors = ordered_doors
        self.rows = [DoorRowVM(i + 1, d) for i, d in enumerate(ordered_doors)]
        self.grid_preview.ItemsSource = self.rows
        self.lbl_status.Text = (
            "{} porte(s) a numeroter. Verifiez l'ordre avant de valider, "
            "en particulier les pieces a plusieurs portes.".format(len(self.rows))
        )

    def on_row_selected(self, sender, args):
        row = self.grid_preview.SelectedItem
        if not row:
            return
        try:
            ids = List[ElementId]([row.element_id])
            self.uidoc.Selection.SetElementIds(ids)
            self.uidoc.ShowElements(row.element_id)
        except Exception:
            pass

    def on_apply_click(self, sender, args):
        confirmed = forms.alert(
            "Appliquer les {} valeurs Mark proposees au modele ?".format(
                len(self.ordered_doors)
            ),
            yes=True,
            no=True,
        )
        if not confirmed:
            return
        apply_marks(self.doc, self.ordered_doors)
        self.lbl_status.Text = "Mark applique sur {} porte(s).".format(
            len(self.ordered_doors)
        )
        forms.alert("Numerotation appliquee.")

    def on_close_click(self, sender, args):
        self.Close()


def show_preview_window(doc, uidoc, ordered_doors):
    """Cree et affiche la fenetre de previsualisation (modale)."""
    xaml_file = os.path.join(os.path.dirname(__file__), "PreviewWindow.xaml")
    window = DoorNumberingPreviewWindow(xaml_file, doc, uidoc, ordered_doors)
    window.ShowDialog()
    return window
